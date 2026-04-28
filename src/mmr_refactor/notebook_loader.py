"""Utilities for reading and iterating notebook-like JSON stored in `.py` files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def load_notebook_like_py(path: str | Path) -> dict[str, Any]:
    """Read a notebook-like `.py` file and return the parsed JSON object.

    Args:
        path: Path to a file that contains Jupyter notebook JSON text.

    Returns:
        Parsed notebook dictionary with keys such as `cells` and `metadata`.
    """
    notebook_path = Path(path)
    return json.loads(notebook_path.read_text(encoding="utf-8"))


def iter_cells(path: str | Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield all cells from the notebook in original order.

    Args:
        path: Path to a notebook-like JSON file.

    Yields:
        `(index, cell)` tuple for each notebook cell.
    """
    notebook = load_notebook_like_py(path)
    for idx, cell in enumerate(notebook.get("cells", [])):
        yield idx, cell


def get_cell_text(cell: dict[str, Any]) -> str:
    """Normalize a notebook cell's `source` field into a single text blob.

    Args:
        cell: A notebook cell dictionary.

    Returns:
        Cell text joined as one string regardless of whether `source` is a list or string.
    """
    source = cell.get("source", [])
    if isinstance(source, str):
        return source
    return "".join(source)
