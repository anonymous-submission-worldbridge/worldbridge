"""Read-only host-side resource diagnostics for this task's Blender workers."""
import json
import os
from pathlib import Path

records = []
for directory in Path("/proc").iterdir():
    if not directory.name.isdigit():
        continue
    try:
        if directory.stat().st_uid != os.getuid():
            continue
        command = (
            (directory / "cmdline")
            .read_bytes()
            .replace(b"\0", b" ")
            .decode(errors="replace")
        )
        if (
            "urban_v1_full_13-dynamic2/render_packs" not in command
            or "blender" not in command
        ):
            continue
        groups = (directory / "cgroup").read_text()
        item = {
            "pid": int(directory.name),
            "command": command,
            "cgroup": groups,
            "limits": (directory / "limits").read_text(),
        }
        item["memory"] = {
            line.split(":")[0]: line.split(":")[1].strip()
            for line in (directory / "status").read_text().splitlines()
            if line.startswith(("VmRSS:", "VmPeak:", "VmHWM:"))
        }
        item["group_memory"] = []
        for group in groups.splitlines():
            if not group.startswith("0::"):
                continue
            path = Path("/sys/fs/cgroup") / group[3:].lstrip("/")
            while path != Path("/sys/fs/cgroup"):
                item["group_memory"].append(
                    {
                        "path": str(path),
                        **{
                            n: (path / n).read_text()
                            for n in ("memory.max", "memory.events", "memory.current")
                            if (path / n).exists()
                        },
                    }
                )
                path = path.parent
        records.append(item)
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
output = (
    Path(__file__).resolve().parents[1]
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic2/process_limits.json"
)
output.write_text(json.dumps(records, indent=2))
print(json.dumps(records, indent=2), flush=True)
