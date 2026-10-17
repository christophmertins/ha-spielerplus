"""Shared pytest fixtures.

Home Assistant is not installed locally (and needs Python 3.13, while this
test venv runs 3.14). The integration's pure modules are therefore loaded
directly as a synthetic package named ``spielerplus`` so their relative
imports resolve without executing ``custom_components/spielerplus/__init__.py``
(which imports Home Assistant).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "spielerplus"

# Dependencies first: models → const → logic → parser → api.
_MODULES = ("models", "const", "logic", "parser", "api")


@pytest.fixture(scope="session")
def sp():
    """Load the integration's importable modules as a package."""
    package = types.ModuleType("spielerplus")
    package.__path__ = [str(PKG)]
    sys.modules["spielerplus"] = package

    loaded: dict[str, object] = {}
    for name in _MODULES:
        spec = importlib.util.spec_from_file_location(
            f"spielerplus.{name}", PKG / f"{name}.py"
        )
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise ImportError(f"cannot load {name} from {PKG}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"spielerplus.{name}"] = module
        spec.loader.exec_module(module)
        setattr(package, name, module)
        loaded[name] = module

    return types.SimpleNamespace(**loaded)


@pytest.fixture(scope="session")
def models(sp):
    return sp.models


@pytest.fixture(scope="session")
def const(sp):
    return sp.const


@pytest.fixture(scope="session")
def logic(sp):
    return sp.logic


@pytest.fixture(scope="session")
def parser(sp):
    return sp.parser


@pytest.fixture(scope="session")
def api(sp):
    return sp.api
