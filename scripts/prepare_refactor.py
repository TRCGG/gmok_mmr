"""CLI entrypoint for splitting notebook-like MMR source into layered modules."""

from __future__ import annotations

import argparse
from pathlib import Path

from mmr_refactor import write_sections


def main() -> None:
    """Parse CLI args, run section split, and print generated file list."""
    parser = argparse.ArgumentParser(
        description="Split notebook-like JSON source into function-oriented Python files."
    )
    parser.add_argument("input", help="Path to notebook-like .py file")
    parser.add_argument(
        "-o",
        "--out-dir",
        default="refactored_sources",
        help="Directory to write split source files",
    )
    args = parser.parse_args()

    written = write_sections(args.input, args.out_dir)

    print(f"[done] created {len(written)} files at: {Path(args.out_dir).resolve()}")
    for path in written:
        print(f" - {path}")


if __name__ == "__main__":
    main()
