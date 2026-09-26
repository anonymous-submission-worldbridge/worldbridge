#!/usr/bin/env python3
"""Report actual HY-World artifacts without creating unstarted run directories."""

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

from datetime import datetime, timezone
from pathlib import Path
import json
import sys

BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES))
import baselines.methods.hyworld.run as matrix

LABELS = {
    "panorama": "panoramic generation",
    "trajectory_planning": "trajectory planning",
    "trajectory_rendering": "trajectory rendering",
    "world_expansion": "World Stereo Expansion",
    "gs_data": "GS data",
    "gs_training": "Training 3DGS",
    "render": "Unified rendering",
}


def main():
    result_root = BASELINES / "results/hyworld2"
    state_path = result_root / "supervisor_state.json"
    supervisor = json.loads(state_path.read_text()) if state_path.exists() else {}
    report = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "supervisor": supervisor,
        "domains": {},
        "rating_source": "AI proxy, not human ratings",
    }
    for domain in ("indoor", "urban"):
        counts = {
            phase: {
                "expected": 10 if phase == "pilot" else 100,
                "prepared": 0,
                **{stage: 0 for stage in (*matrix.STAGES, "render")},
            }
            for phase in ("pilot", "formal")
        }
        for spec in matrix.HY.load_specs(domain):
            for seed in range(4):
                run = (
                    matrix.HY.DATA_ROOT
                    / domain
                    / "hyworld2"
                    / spec["spec_id"]
                    / f"seed_{seed}"
                )
                if not (run / "run_manifest.json").is_file():
                    continue
                stages = matrix.stage_state(run / "scene/native")
                stages["render"] = (run / "SUCCESS").is_file()
                phases = ["formal"]
                if spec["spec_index"] in matrix.HY.PILOT_SPEC_INDICES and seed in (
                    0,
                    1,
                ):
                    phases.append("pilot")
                for phase in phases:
                    counts[phase]["prepared"] += 1
                    for stage, complete in stages.items():
                        counts[phase][stage] += int(complete)
        report["domains"][domain] = counts
    warmup = result_root / "checkpoint_cache_warmup.json"
    if warmup.exists():
        report["cache_warmup"] = json.loads(warmup.read_text())
    matrix.atomic_json(result_root / "progress.json", report)
    lines = [
        "# HY-World 2.0 Actual Execution Progress",
        "",
        f"Update time: {report['updated_at_utc']}",
        "",
        f"Queue: `{supervisor.get('status', 'unknown')}`; Stage: `{supervisor.get('stage', 'unknown')}`"
        f"PID: `{supervisor.get('pid', 'unknown')}`.",
        "",
        f"Current idle card: {supervisor.get('current_idle', [])}; Card with continuous idle time meeting criteria:"
        f"{supervisor.get('stable_idle', [])}; The current stage requires {supervisor.get('needed', 4)} sheets.",
        "",
        "| Stage | Indoor Pilot /10 | Urban Pilot /10 | Indoor full matrix /100 | Urban full matrix /100 |",
        "|---|---:|---:|---:|---:|",
    ]
    for stage, label in {"prepared": "Input is ready.", **LABELS}.items():
        values = [
            report["domains"][d][p][stage]
            for d, p in (
                ("indoor", "pilot"),
                ("urban", "pilot"),
                ("indoor", "formal"),
                ("urban", "formal"),
            )
        ]
        lines.append(f"| {label} | " + " | ".join(map(str, values)) + " |")
    lines.extend(
        [
            "",
            "Pilot runs are a subset of the full matrix for the same specifications and seeds. The two counting scopes in the table above must not be added together."
            "The number of input preparations in the total matrix does not indicate that an official experiment has been started.",
            "",
        ]
    )
    if "cache_warmup" in report:
        w = report["cache_warmup"]
        lines.extend(
            [
                f"Local weight cache preheating: `{w['status']}`, read {w['read_bytes']/2**30:.2f} "
                f"{w['total_bytes']/2**30:.2f} GiB, completing {len(w['completed_shards'])}/32 shards.",
                "",
            ]
        )
    lines.extend(
        [
            "Two subjective indicators will be scored by an AI proxy with user consent; the remaining five items will continue to use the frozen evaluation protocol."
            "Only after completing the formal matrix and having all seven indicators filled out will data be entered.",
            "",
            "Detailed log: `../../hyworld2_runtime/logs/resume_supervisor_20260905.log`"
            "Each stage's raw logs are retained alongside each scene's manifest.",
            "",
        ]
    )
    (result_root / "PROGRESS.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
