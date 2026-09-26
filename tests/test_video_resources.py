"""Video input failures must release native capture handles."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "module,method",
    [
        ("worldbridge/postprocess/reflect.py", "_process_video"),
        ("worldbridge/metrics/hrs.py", "sample_frames"),
    ],
)
def test_empty_video_releases_capture(module, method):
    # These methods are independent of the optional HTTP/model clients. Compile
    # them with postponed annotations so the test needs no model or video codec.
    tree = ast.parse((ROOT / module).read_text())
    function = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == method
    )
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    compiled = ast.fix_missing_locations(
        ast.Module(body=[future, function], type_ignores=[])
    )
    released = []
    capture = SimpleNamespace(
        get=lambda _: 0, isOpened=lambda: True, release=lambda: released.append(True)
    )
    namespace = {
        "os": SimpleNamespace(path=SimpleNamespace(exists=lambda _: True)),
        "cv2": SimpleNamespace(VideoCapture=lambda _: capture, CAP_PROP_FRAME_COUNT=7),
    }
    exec(compile(compiled, module, "exec"), namespace)
    with pytest.raises(ValueError):
        namespace[method](None, "empty.mp4")
    assert released == [True]
