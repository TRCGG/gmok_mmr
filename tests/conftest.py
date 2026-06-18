from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"        # 운영 패키지 `mmr`
TESTS = ROOT / "tests"    # 테스트 하네스 패키지 `harness`

for path in (SRC, TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
