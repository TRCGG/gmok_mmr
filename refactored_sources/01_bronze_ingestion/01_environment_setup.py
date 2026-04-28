"""환경 세팅 및 공통 import.

NOTE: Jupyter 매직 명령(`!pip install`, `%config`)은 일반 `python` 실행 시
SyntaxError가 발생하므로 제거. 패키지 설치는 `requirements.txt` 참고:

    pip install -r requirements.txt
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import scipy.stats as stats
import statsmodels.api as sm

try:
    import koreanize_matplotlib  # noqa: F401  (한글 폰트 자동 적용)
except ImportError:
    # 한글 폰트 미설치 환경에서도 파이프라인은 동작
    pass

# Jupyter 환경에서만 적용되는 retina 설정 — 일반 스크립트에서는 무시
try:
    from IPython import get_ipython

    ip = get_ipython()
    if ip is not None:
        ip.run_line_magic("config", "InlineBackend.figure_format = 'retina'")
except ImportError:
    pass
