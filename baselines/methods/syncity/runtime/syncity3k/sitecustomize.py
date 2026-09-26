"""Offline repository-to-snapshot mapping for the SynCity 3000 workers.

Python imports ``sitecustomize`` during interpreter startup.  Keeping this
small compatibility shim on the worker's PYTHONPATH lets the pristine upstream
source continue using its repository IDs while every load resolves to the
pinned, pre-verified snapshots below ``baselines/checkpoints/syncity3k``.
"""

from __future__ import annotations

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


import importlib.util
import sys
import types
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
HUB = BASELINES_ROOT / "checkpoints/syncity3k/huggingface/hub"
SNAPSHOTS = {
    "black-forest-labs/FLUX.1-dev": HUB
    / "models--black-forest-labs--FLUX.1-dev/snapshots/3de623fc3c33e44ffbe2bad470d0f45bccf2eb21",
    "alimama-creative/FLUX.1-dev-Controlnet-Inpainting-Beta": HUB
    / "models--alimama-creative--FLUX.1-dev-Controlnet-Inpainting-Beta/snapshots/4c71e88b32ab247b3c2518803224c7c6473dbeb9",
    "microsoft/TRELLIS-image-large": HUB
    / "models--microsoft--TRELLIS-image-large/snapshots/25e0d31ffbebe4b5a97464dd851910efc3002d96",
    "paulengstler/syncity-3k": HUB
    / "models--paulengstler--syncity-3k/snapshots/cf11932c4067612e8254b7fe0be95430a8dffdbd",
}


def local_repository(value):
    path = SNAPSHOTS.get(str(value))
    return str(path) if path is not None else value


def install_hub_mapping() -> None:
    import huggingface_hub

    original_hf_hub_download = huggingface_hub.hf_hub_download
    original_snapshot_download = huggingface_hub.snapshot_download

    def mapped_hf_hub_download(repo_id, filename, *args, **kwargs):
        snapshot = SNAPSHOTS.get(str(repo_id))
        if snapshot is not None:
            target = snapshot / filename
            if not target.is_file():
                raise FileNotFoundError(f"Pinned SynCity asset is missing: {target}")
            return str(target)
        return original_hf_hub_download(repo_id, filename, *args, **kwargs)

    def mapped_snapshot_download(repo_id, *args, **kwargs):
        snapshot = SNAPSHOTS.get(str(repo_id))
        if snapshot is not None:
            if not snapshot.is_dir():
                raise FileNotFoundError(
                    f"Pinned SynCity snapshot is missing: {snapshot}"
                )
            return str(snapshot)
        return original_snapshot_download(repo_id, *args, **kwargs)

    huggingface_hub.hf_hub_download = mapped_hf_hub_download
    huggingface_hub.snapshot_download = mapped_snapshot_download


def install_diffusers_mapping() -> None:
    from diffusers import DiffusionPipeline
    from diffusers.models.modeling_utils import ModelMixin

    original_model_load = ModelMixin.from_pretrained.__func__
    original_pipeline_load = DiffusionPipeline.from_pretrained.__func__

    def mapped_model_load(cls, pretrained_model_name_or_path, *args, **kwargs):
        return original_model_load(
            cls, local_repository(pretrained_model_name_or_path), *args, **kwargs
        )

    def mapped_pipeline_load(cls, pretrained_model_name_or_path, *args, **kwargs):
        return original_pipeline_load(
            cls, local_repository(pretrained_model_name_or_path), *args, **kwargs
        )

    ModelMixin.from_pretrained = classmethod(mapped_model_load)
    DiffusionPipeline.from_pretrained = classmethod(mapped_pipeline_load)


def install_torch_hub_mapping() -> None:
    """Resolve TRELLIS' DINOv2 dependency from the pinned local hub clone.

    ``torch.hub.load('facebookresearch/dinov2', ...)`` contacts GitHub even
    when the repository and checkpoint already exist in ``TORCH_HOME``.  That
    validation request breaks the deliberately offline formal runs.  Mapping
    the single upstream repository ID to its audited local clone keeps the
    upstream call site unchanged and prevents accidental network traffic.
    """
    import torch.hub

    original_load = torch.hub.load
    local_dinov2 = (
        BASELINES_ROOT / "checkpoints/syncity3k/torch/hub/facebookresearch_dinov2_main"
    )

    def mapped_load(repo_or_dir, model, *args, **kwargs):
        if str(repo_or_dir) == "facebookresearch/dinov2":
            if not (local_dinov2 / "hubconf.py").is_file():
                raise FileNotFoundError(
                    f"Pinned SynCity DINOv2 repository is missing: {local_dinov2}"
                )
            kwargs.pop("source", None)
            kwargs.pop("trust_repo", None)
            kwargs.pop("skip_validation", None)
            return original_load(
                str(local_dinov2), model, *args, source="local", **kwargs
            )
        return original_load(repo_or_dir, model, *args, **kwargs)

    torch.hub.load = mapped_load


def install_unused_nvdiffrast_stub() -> None:
    """Satisfy TRELLIS's eager mesh-renderer import on Gaussian-only runs.

    SynCity's color pass requests alpha rendering, which selects gsplat.  The
    same utility module nevertheless imports MeshRenderer eagerly, and that
    optional class imports nvdiffrast.  A deliberately attribute-free stub
    permits the unused class definition to load; any accidental mesh-renderer
    call still fails immediately instead of silently changing the algorithm.
    """
    if importlib.util.find_spec("nvdiffrast") is not None:
        return
    # Let Kaolin perform its normal optional-dependency probe while the module
    # is genuinely absent; otherwise it assumes the stub is a full renderer.
    import kaolin  # noqa: F401

    package = types.ModuleType("nvdiffrast")
    package.__path__ = []
    torch_module = types.ModuleType("nvdiffrast.torch")
    package.torch = torch_module
    sys.modules["nvdiffrast"] = package
    sys.modules["nvdiffrast.torch"] = torch_module


install_hub_mapping()
install_diffusers_mapping()
install_torch_hub_mapping()
install_unused_nvdiffrast_stub()
