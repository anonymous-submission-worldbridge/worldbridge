"""Lossless seekable-Zstandard storage compatible with Blender .blend files."""
import hashlib
import struct
from pathlib import Path
import zstandard

FRAME_SIZE = 2 * 1024 * 1024


def compress_copy(source, destination):
    """Preserve every uncompressed byte while creating Blender-native frames."""
    table = []
    digest = hashlib.sha256()
    size = 0
    compressor = zstandard.ZstdCompressor(level=1)
    with Path(source).open("rb") as reader, Path(destination).open("wb") as writer:
        while block := reader.read(FRAME_SIZE):
            digest.update(block)
            size += len(block)
            encoded = compressor.compress(block)
            writer.write(encoded)
            table.append((len(encoded), len(block)))
        length = len(table) * 8 + 9
        writer.write(struct.pack("<II", 0x184D2A5E, length))
        for compressed, decoded in table:
            writer.write(struct.pack("<II", compressed, decoded))
        writer.write(struct.pack("<IBI", len(table), 0, 0x8F92EAB1))
    return digest.hexdigest(), size


class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.hash = hashlib.sha256()
        self.bytes = 0

    def read(self, size=-1):
        data = self.stream.read(size)
        self.hash.update(data)
        self.bytes += len(data)
        return data

    def readinto(self, buffer):
        n = self.stream.readinto(buffer)
        if n:
            self.hash.update(memoryview(buffer)[:n])
            self.bytes += n
        return n


def decoded_digest(path, include_storage=False):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        counted = HashingReader(stream)
        with zstandard.ZstdDecompressor().stream_reader(
            counted, read_across_frames=True
        ) as decoded:
            while block := decoded.read(8 * 1024 * 1024):
                digest.update(block)
                size += len(block)
    if counted.bytes != Path(path).stat().st_size:
        raise RuntimeError("Incomplete compressed-file verification")
    result = (digest.hexdigest(), size)
    return (*result, counted.hash.hexdigest()) if include_storage else result
