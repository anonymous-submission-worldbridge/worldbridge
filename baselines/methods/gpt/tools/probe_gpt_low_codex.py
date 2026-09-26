#!/usr/bin/env python3
"""Probe GPT-6 Astra with the exact Low transport and reasoning setting."""

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))

import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def main():
    parent = ROOT / "results/gpt6_astra_low/codex_probe"
    parent.mkdir(parents=True, exist_ok=True)
    index = 1
    while (parent / f"attempt_{index:02d}").exists():
        index += 1
    output = parent / f"attempt_{index:02d}"
    work = ROOT / "work/gpt6_astra_low/codex_probe"
    output.mkdir(parents=True)
    work.mkdir(parents=True, exist_ok=True)
    command = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--model",
        "gpt-6-astra",
        "-c",
        'model_reasoning_effort="low"',
        "--json",
        "-C",
        str(work),
        "-o",
        str(output / "response.txt"),
        "This is a model connectivity test. Do not use tools, read files, or change files. Reply with exactly ASTRA_LOW_CONNECTIVITY_OK.",
    ]
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_requested": "gpt-6-astra",
        "reasoning_effort": "low",
        "command": command,
        "codex_version": subprocess.check_output(
            ["codex", "--version"], text=True
        ).strip(),
        "auth_mode": "saved_codex_chatgpt_login",
        "timeout_s": 120,
    }
    with (output / "events.jsonl").open("w") as stdout, (output / "stderr.log").open(
        "w"
    ) as stderr:
        try:
            completed = subprocess.run(
                command, stdout=stdout, stderr=stderr, timeout=120
            )
            report["exit_code"] = completed.returncode
        except subprocess.TimeoutExpired:
            report.update(exit_code=None, timeout=True)
        except OSError as error:
            report.update(
                exit_code=None, launch_error=type(error).__name__ + ": " + str(error)
            )
    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    response = output / "response.txt"
    report["success"] = (
        report["exit_code"] == 0
        and response.exists()
        and response.read_text().strip() == "ASTRA_LOW_CONNECTIVITY_OK"
    )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["success"]:
        print((output / "stderr.log").read_text()[-4000:])
        print((output / "events.jsonl").read_text()[-6000:])
    return 0 if report["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
