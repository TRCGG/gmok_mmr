"""Section splitter for converting mixed notebook cells into layered Python modules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .notebook_loader import get_cell_text, iter_cells


@dataclass
class Section:
    """Container for one logical notebook section.

    Attributes:
        title: Normalized section title derived from markdown header.
        code_blocks: Ordered code cell contents that belong to this section.
    """

    title: str
    code_blocks: list[str] = field(default_factory=list)


HEADER_PATTERN = re.compile(r"^#+\s*(.+)$")

# Data-engineering friendly output layout (medallion-inspired + analytics/reporting split)
SECTION_LAYOUT: dict[int, tuple[str, str]] = {
    1: ("01_bronze_ingestion", "environment_setup"),
    2: ("01_bronze_ingestion", "load_raw_match_data"),
    3: ("02_silver_validation", "validate_missing_and_outliers"),
    4: ("02_silver_feature_prep", "derive_position_weights"),
    5: ("02_silver_feature_prep", "compute_game_impact_score"),
    6: ("03_analytics_validation", "inspect_position_distribution"),
    7: ("02_silver_feature_prep", "normalize_game_impact_by_outcome"),
    8: ("03_analytics_validation", "validate_normalization_results"),
    9: ("03_gold_match_features", "build_team_contribution_metrics"),
    10: ("03_gold_mmr", "compute_mmr_elo_pipeline"),
    11: ("03_gold_serving", "build_user_summary_tables"),
    12: ("04_analytics_reporting", "generate_player_style_report"),
}


def slugify(text: str) -> str:
    """Convert raw header text into a safe snake-case slug."""
    slug = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", text.strip()).strip("_").lower()
    return slug or "section"


def split_notebook_by_markdown_headers(notebook_path: str | Path) -> list[Section]:
    """Group code cells by nearest markdown header.

    Args:
        notebook_path: Notebook-like `.py` JSON file path.

    Returns:
        Ordered list of `Section` objects with grouped code blocks.
    """
    sections: list[Section] = []
    current = Section(title="00_bootstrap")

    for _, cell in iter_cells(notebook_path):
        cell_type = cell.get("cell_type")
        text = get_cell_text(cell).strip()

        if cell_type == "markdown":
            first_line = text.splitlines()[0] if text else ""
            matched = HEADER_PATTERN.match(first_line)
            if matched:
                if current.code_blocks:
                    sections.append(current)
                current = Section(title=slugify(matched.group(1)))
        elif cell_type == "code" and text:
            current.code_blocks.append(text)

    if current.code_blocks:
        sections.append(current)

    return sections


def _resolve_output_path(out_dir: Path, index: int, section_title: str) -> Path:
    """Resolve output file path using predefined DE layer mapping.

    Falls back to `99_misc` if no mapping exists for a section index.
    """
    folder_name, file_name = SECTION_LAYOUT.get(
        index,
        ("99_misc", f"{index:02d}_{slugify(section_title)}"),
    )
    return out_dir / folder_name / f"{index:02d}_{file_name}.py"


def write_sections(notebook_path: str | Path, out_dir: str | Path) -> list[Path]:
    """Write section-split Python files into layered folders.

    Args:
        notebook_path: Source notebook-like `.py` JSON file.
        out_dir: Root output directory for generated section files.

    Returns:
        List of written file paths in creation order.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    sections = split_notebook_by_markdown_headers(notebook_path)

    for i, section in enumerate(sections, start=1):
        path = _resolve_output_path(out_dir, i, section.title)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n\n\n".join(section.code_blocks).rstrip() + "\n"
        path.write_text(body, encoding="utf-8")
        written.append(path)

    return written
