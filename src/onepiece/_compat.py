"""Compatibility helpers for supported dependency ranges."""

from __future__ import annotations

import logging
import sys

import numpy as np

logger = logging.getLogger(__name__)

# np.trapz was removed in NumPy 2.0 in favour of np.trapezoid.
trapezoid = getattr(np, "trapezoid", None) or np.trapz


def install_numpy_pickle_compat() -> None:
    """Alias NumPy 2 module paths so NumPy 1 can unpickle NumPy 2 arrays.

    Legacy OnePiece HDF files store pickled objects (ASE Atoms, arrays) whose
    module paths differ between NumPy 1 (``numpy.core``) and NumPy 2
    (``numpy._core``). On NumPy 1 environments, register the new names as
    aliases so those pickles resolve. On NumPy 2, ``numpy._core`` already
    exists and the aliasing is skipped. The preloads make sure modules
    referenced by the pickles are importable before unpickling starts.
    """
    for module_name in ("ase.constraints", "scipy.linalg", "sympy", "tables"):
        try:
            __import__(module_name)
        except Exception as exc:
            logger.debug("Optional compatibility preload for %s skipped: %s", module_name, exc)

    if hasattr(np, "_core"):
        return
    import numpy.core as numpy_core

    sys.modules.setdefault("numpy._core", numpy_core)
    sys.modules.setdefault("numpy._core.multiarray", numpy_core.multiarray)
    sys.modules.setdefault("numpy._core.numeric", numpy_core.numeric)
