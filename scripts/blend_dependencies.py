"""Inspect Blender dependency paths without loading meshes or running scene code.

Supports legacy and version-1 Blender headers and seekable Zstandard frames.
Only block headers, DNA, and dependency ID blocks are decoded.
"""
from __future__ import annotations
import bisect
from collections import OrderedDict
import io
import mmap
from pathlib import Path
import re
import struct
import zstandard


class BlendReader:
    def __init__(self, path):
        self.file = Path(path).open("rb")
        self.file.seek(0, 2)
        self.size = self.file.tell()
        self.file.seek(0)
        magic = self.file.read(7)
        self.frames = None
        self.cache = OrderedDict()
        self.mapping = None
        self.raw_offset = -1
        self.raw_buffer = b""
        if magic != b"BLENDER":
            self.file.seek(-9, 2)
            count, descriptor, end = struct.unpack("<IBI", self.file.read(9))
            if end != 0x8F92EAB1:
                raise ValueError("Unsupported compressed Blender stream")
            stride = 12 if descriptor & 0x80 else 8
            self.file.seek(-(9 + count * stride), 2)
            table = self.file.read(count * stride)
            self.frames = []
            self.offsets = []
            compressed = 0
            decoded = 0
            for i in range(count):
                csize, dsize = struct.unpack_from("<II", table, i * stride)
                self.frames.append((compressed, csize, dsize))
                self.offsets.append(decoded)
                compressed += csize
                decoded += dsize
            self.size = decoded
        header = self.read(0, 17)
        if not header.startswith(b"BLENDER"):
            raise ValueError("Invalid Blender header")
        if header[7:8] in (b"-", b"_"):
            self.pointer = 8 if header[7:8] == b"-" else 4
            self.endian = "<" if header[8:9] == b"v" else ">"
            self.header_size = 12
            self.block = struct.Struct(
                self.endian + ("4siQii" if self.pointer == 8 else "4siIii")
            )
            self.modern = False
            self.version = int(header[9:12])
        else:
            if header[7:13] != b"17-01v":
                raise ValueError("Unknown Blender header version")
            self.pointer = 8
            self.endian = "<"
            self.header_size = 17
            self.block = struct.Struct("<4siQqq")
            self.modern = True
            self.version = int(header[13:17])

    def raw_read(self, offset, length):
        if not (
            self.raw_offset <= offset
            and offset + length <= self.raw_offset + len(self.raw_buffer)
        ):
            self.file.seek(offset)
            self.raw_offset = offset
            self.raw_buffer = self.file.read(max(length, 64 * 1024 * 1024))
        start = offset - self.raw_offset
        return self.raw_buffer[start : start + length]

    def read(self, offset, length):
        if not self.frames:
            return self.raw_read(offset, length)
        chunks = []
        while length > 0 and offset < self.size:
            index = bisect.bisect_right(self.offsets, offset) - 1
            if index not in self.cache:
                position, csize, dsize = self.frames[index]
                data = zstandard.ZstdDecompressor().decompress(
                    self.raw_read(position, csize), max_output_size=dsize
                )
                if len(data) != dsize:
                    raise ValueError("Zstandard frame size mismatch")
                self.cache[index] = data
                if len(self.cache) > 4:
                    self.cache.popitem(last=False)
            data = self.cache[index]
            self.cache.move_to_end(index)
            start = offset - self.offsets[index]
            take = min(length, len(data) - start)
            if take <= 0:
                raise ValueError("Invalid seek table")
            chunks.append(data[start : start + take])
            offset += take
            length -= take
        return b"".join(chunks)

    def close(self):
        if self.mapping is not None:
            self.mapping.close()
        self.file.close()


def parse_dna(data, endian, pointer):
    offset = 0

    def tag(value):
        nonlocal offset
        if data[offset : offset + 4] != value:
            raise ValueError("Invalid DNA section")
        offset += 4

    def number(fmt):
        nonlocal offset
        result = struct.unpack_from(endian + fmt, data, offset)
        offset += struct.calcsize(fmt)
        return result[0] if len(result) == 1 else result

    def strings():
        nonlocal offset
        count = number("I")
        out = []
        for _ in range(count):
            end = data.index(b"\0", offset)
            out.append(data[offset:end].decode())
            offset = end + 1
        offset = (offset + 3) & ~3
        return out

    tag(b"SDNA")
    tag(b"NAME")
    names = strings()
    tag(b"TYPE")
    types = strings()
    tag(b"TLEN")
    lengths = [number("H") for _ in types]
    offset = (offset + 3) & ~3
    tag(b"STRC")
    count = number("I")
    structures = []
    for _ in range(count):
        ti, fields = number("HH")
        position = 0
        entries = {}
        for _ in range(fields):
            ft, fn = number("HH")
            name = names[fn]
            elements = 1
            for dim in re.findall(r"\[(\d+)\]", name):
                elements *= int(dim)
            size = (pointer if "*" in name else lengths[ft]) * elements
            key = re.sub(r"\[.*", "", name).lstrip("*")
            entries[key] = {
                "offset": position,
                "size": size,
                "type": types[ft],
                "pointer": "*" in name,
            }
            position += size
        if position != lengths[ti]:
            raise ValueError("DNA layout size mismatch: " + types[ti])
        structures.append({"name": types[ti], "fields": entries, "size": lengths[ti]})
    return structures


def inspect(path):
    reader = BlendReader(path)
    try:
        offset = reader.header_size
        blocks = []
        dna = None
        block_count = 0
        wanted = {b"IM", b"LI", b"VF", b"SO", b"CF", b"MC", b"VO"}
        while offset + reader.block.size <= reader.size:
            values = reader.block.unpack(reader.read(offset, reader.block.size))
            if reader.modern:
                code, sdna, addr, size, count = values
            else:
                code, size, addr, sdna, count = values
            payload = offset + reader.block.size
            if size < 0 or payload + size > reader.size:
                raise ValueError("Invalid block extent")
            if code == b"DNA1":
                dna = reader.read(payload, size)
            if code.rstrip(b"\0") in wanted:
                blocks.append(
                    (code, sdna, addr, payload, size, reader.read(payload, size))
                )
            block_count += 1
            if code == b"ENDB":
                break
            offset = payload + size
        if dna is None:
            raise ValueError("Missing DNA block")
        schemas = parse_dna(dna, reader.endian, reader.pointer)
        by_name = {s["name"]: s for s in schemas}
        result = []
        pointer_fmt = reader.endian + ("Q" if reader.pointer == 8 else "I")
        for code, sdna, addr, payload, size, data in blocks:
            schema = schemas[sdna]
            fields = schema["fields"]
            kind = schema["name"]
            field = "filepath" if "filepath" in fields else "name"
            if field not in fields:
                continue
            entry = fields[field]
            if entry["type"] != "char" or entry["pointer"]:
                continue
            raw = data[entry["offset"] : entry["offset"] + entry["size"]].split(
                b"\0", 1
            )[0]
            value = raw.decode("utf-8", errors="surrogateescape")
            packed = False
            if "packedfile" in fields:
                at = fields["packedfile"]["offset"]
                packed = bool(struct.unpack_from(pointer_fmt, data, at)[0])
            if "packedfiles" in fields:
                at = fields["packedfiles"]["offset"]
                packed |= bool(struct.unpack_from(pointer_fmt, data, at)[0])
            library = 0
            if "id" in fields and "ID" in by_name and "lib" in by_name["ID"]["fields"]:
                at = fields["id"]["offset"] + by_name["ID"]["fields"]["lib"]["offset"]
                library = struct.unpack_from(pointer_fmt, data, at)[0]
            if value and value != "<builtin>":
                result.append(
                    {
                        "kind": kind,
                        "path": value,
                        "packed": packed,
                        "offset": payload + entry["offset"],
                        "capacity": entry["size"],
                        "block_address": addr,
                        "library_address": library,
                    }
                )
        return {
            "version": reader.version,
            "compressed": bool(reader.frames),
            "block_count": block_count,
            "dependencies": result,
        }
    finally:
        reader.close()
