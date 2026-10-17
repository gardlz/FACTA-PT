"""Safe removal of the temporary training directories: no checkpoint is kept, and a path is
deleted only if it contains a temporary marker and no protected segment.
"""

import shutil
from pathlib import Path

# Path segments that mark a directory as temporary, and segments that are never deleted.
_TEMP_MARKERS = ("tmp", "adapters", "checkpoints")
_PROTECTED = ("outputs", "predictions", "metrics", "data", "configs")


def _is_safe_to_delete(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & set(_PROTECTED):
        return False
    return bool(parts & set(_TEMP_MARKERS))


def safe_rmtree(temp_dir) -> bool:
    """Delete temp_dir only if it looks temporary. Returns True if it was deleted."""
    path = Path(temp_dir).resolve()
    if not path.exists():
        return False
    if not _is_safe_to_delete(path):
        print(f"[cleanup] RECUSADO apagar (não parece temporário): {path}")
        return False
    shutil.rmtree(path, ignore_errors=True)
    print(f"[cleanup] apagado: {path}")
    return True
