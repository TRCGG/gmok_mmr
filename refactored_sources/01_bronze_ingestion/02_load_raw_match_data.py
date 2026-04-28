mmr_df = "C:/Users/PC/Desktop/김필준/data/2026 난민_0415.csv"


try:
    mmr_df = pd.read_csv(mmr_df, encoding='utf-8', on_bad_lines='skip')
    print("UTF-8 인코딩으로 데이터 로드에 성공했습니다.")
except UnicodeDecodeError:
    mmr_df = pd.read_csv(mmr_df, encoding='cp949', on_bad_lines='skip')
    print("CP949 인코딩으로 데이터 로드에 성공했습니다.")
