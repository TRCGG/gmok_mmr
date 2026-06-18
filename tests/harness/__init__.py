"""테스트/로컬 실행용 하네스.

운영 MMR 서비스(`src/mmr`)는 백엔드 API로만 데이터를 주고받는다.
이 패키지는 백엔드 연동 전 단계에서 DB에 직접 접근/적재하며 전체 흐름을
검증하기 위한 임시 입출력 도구를 모아둔다. 백엔드 연동이 끝나면 통째로 삭제한다.

- ``config``       : 입출력(DB/API) 라우팅 설정
- ``data_loader``  : 원천 player-game 데이터 로드
- ``data_writer``  : 계산 결과 저장
- ``db_test``      : PostgreSQL 직접 접근 repository/baseline/run_logger
"""
