"""`.py` 파일에 저장된 notebook 형태 JSON을 읽고 순회하는 유틸리티."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def load_notebook_like_py(path: str | Path) -> dict[str, Any]:
    """notebook 형태 `.py` 파일을 읽어 JSON 객체로 반환한다.

    인자:
        path: Jupyter notebook JSON 텍스트가 들어 있는 파일 경로.

    반환:
        `cells`, `metadata` 같은 key를 가진 notebook dictionary.
    """
    notebook_path = Path(path)
    return json.loads(notebook_path.read_text(encoding="utf-8"))


def iter_cells(path: str | Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """notebook의 모든 cell을 원본 순서대로 반환한다.

    인자:
        path: notebook 형태 JSON 파일 경로.

    생성:
        각 notebook cell에 대한 `(index, cell)` tuple.
    """
    notebook = load_notebook_like_py(path)
    for idx, cell in enumerate(notebook.get("cells", [])):
        yield idx, cell


def get_cell_text(cell: dict[str, Any]) -> str:
    """notebook cell의 `source` 필드를 하나의 문자열로 정규화한다.

    인자:
        cell: notebook cell dictionary.

    반환:
        `source`가 list 또는 string인지와 무관하게 하나로 합친 cell 텍스트.
    """
    source = cell.get("source", [])
    if isinstance(source, str):
        return source
    return "".join(source)
