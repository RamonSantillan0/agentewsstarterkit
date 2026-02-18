from __future__ import annotations

import importlib
import uuid
from typing import Any, Callable


def import_from_path(path: str) -> Callable[..., Any]:
    """
    path: "module.submodule:function"
    """
    if ":" not in path:
        raise ValueError(f"Invalid import path: {path}")
    mod, fn = path.split(":", 1)
    module = importlib.import_module(mod)
    func = getattr(module, fn, None)
    if not callable(func):
        raise ValueError(f"Provider function not callable: {path}")
    return func


def new_request_id() -> str:
    return uuid.uuid4().hex