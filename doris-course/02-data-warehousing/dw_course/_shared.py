"""Load existing course components without starting the other course's runtime."""

import importlib.util
import sys
from pathlib import Path


def load_component(name):
    if name not in {"quiz", "doris_client"}:
        raise ValueError("Unknown shared course component")
    module_name = f"dw_course._shared_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    source = (
        Path(__file__).resolve().parents[2]
        / "01-real-time-analytics/doris_course"
        / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[module_name]
        raise
    return module
