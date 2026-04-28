"""원시 매치 데이터 로드.

현재: PostgreSQL DB 에서 조회 (`mmr_refactor.data_loader`).
TODO: 추후 백엔드 API 호출 버전으로 전환 예정.
       전환 시 `data_loader._load_match_from_api()` 사용.

이전 CSV 직접 로드 방식 (참고용, 사용하지 않음):
    csv_path = "C:/Users/PC/Desktop/김필준/data/2026 난민_0415.csv"
    try:
        mmr_df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip')
    except UnicodeDecodeError:
        mmr_df = pd.read_csv(csv_path, encoding='cp949', on_bad_lines='skip')
"""

from mmr_refactor.data_loader import load_match_dataframe

mmr_df = load_match_dataframe()
print(f"매치 로그 {len(mmr_df):,}건 로드 완료.")
