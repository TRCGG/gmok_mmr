-- TODO: 현재 미사용. 추후 정리(삭제처리) 예정.
CREATE TABLE League (
	game_id VARCHAR(128) PRIMARY KEY, 		-- 리플파일이름  
	raw_data JSONB NOT NULL,		    -- 원시데이터
	hash_data VARCHAR(128) NOT NULL,        -- raw_data hash값으로 변환(중복데이터 체크용)
	guild_id VARCHAR(128) NOT NULL, 		-- 디스코드 길드 ID
	game_date TIMESTAMP NOT NULL, 		-- 게임 날짜 
	game_type CHAR(1) DEFAULT 1,	 -- 게임유형 내전(1)/대회(2)
	create_user VARCHAR(128) NOT NULL, 
	create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	delete_yn CHAR(1) DEFAULT 'N'
);

CREATE TABLE Player (
    player_id VARCHAR(64) PRIMARY KEY,     -- 고유 ID (PLR_1)
    riot_name VARCHAR(128) NOT NULL,        -- 메인 라이엇 이름
    riot_name_tag VARCHAR(128) NOT NULL,    -- 메인 라이엇 태그
    guild_id VARCHAR(128) NOT NULL,         -- 길드 ID
    puuid VARCHAR(64) NOT NULL, 		    -- puuid
    main_player_id VARCHAR(64),             -- 부캐일 경우 본캐 player_id 
	create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	delete_yn CHAR(1) DEFAULT 'N'
);

CREATE TABLE Player_game (
    player_game_id VARCHAR(64) PRIMARY KEY,         -- 고유 ID (PLG_1)
    player_id VARCHAR(64) NOT NULL,                 -- player_id FK
    champion_id VARCHAR(16) NOT NULL,               -- champion_id FK
    game_id VARCHAR(128) NOT NULL,                   -- 게임 ID
    game_date TIMESTAMP NOT NULL,                    -- 게임 날짜
    game_team VARCHAR(8) NOT NULL,                    -- 게임 팀
    game_result VARCHAR(4) NOT NULL,                  -- 게임 결과 (승/패)
    game_type CHAR(1) NOT NULL,                    -- 게임 유형 (내전/대회)
    position VARCHAR(16) NOT NULL,                     -- 포지션
    kill INTEGER NOT NULL,                      -- 킬 수
    death INTEGER NOT NULL,                     -- 데스 수
    assist INTEGER NOT NULL,                    -- 어시스트 수
    gold INTEGER NOT NULL,                      -- 획득한 골드
    ccing INTEGER NOT NULL,                     -- CC (군중 제어 시간)
    time_played INTEGER NOT NULL,               -- 플레이 시간 (초 단위)
    total_damage_champions INTEGER NOT NULL,    -- 가한 총 피해
    total_damage_taken INTEGER NOT NULL,        -- 받은 총 피해
    vision_score INTEGER NOT NULL,              -- 시야 점수
    vision_bought INTEGER NOT NULL,             -- 구매한 핑와 개수
    penta_kills INTEGER NOT NULL,                -- 펜타킬 수
	create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	delete_yn CHAR(1) DEFAULT 'N'
);

CREATE TABLE Champion(
	champion_id VARCHAR(16) PRIMARY KEY, -- 고유 ID (CHN_1)
	champ_name VARCHAR(128) NOT NULL,
	champ_name_eng VARCHAR(128) NOT NULL,
	create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	delete_yn CHAR(1) DEFAULT 'N'
);

CREATE TABLE Guild(
	guild_id VARCHAR(128) PRIMARY KEY, -- 고유 ID (GUD_1)
	guild_name VARCHAR(128) NOT NULL,
	create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	delete_yn CHAR(1) DEFAULT 'N'
);

-- 쳄피언
INSERT INTO Champion (champion_id, champ_name, champ_name_eng)
VALUES
    ('CHN_1', '아트록스', 'aatrox'),
    ('CHN_2', '아리', 'ahri'),
    ('CHN_3', '아칼리', 'akali'),
    ('CHN_4', '아크샨', 'akshan'),
    ('CHN_5', '알리스타', 'alistar'),
    ('CHN_6', '아무무', 'amumu'),
    ('CHN_7', '애니', 'annie'),
    ('CHN_8', '애니비아', 'anivia'),
    ('CHN_9', '아펠리오스', 'aphelios'),
    ('CHN_10', '애쉬', 'ashe'),
    ('CHN_11', '아우렐리온솔', 'aurelionsol'),
    ('CHN_12', '오로라', 'aurora'),
    ('CHN_13', '암베사', 'ambessa'),
    ('CHN_14', '아지르', 'azir'),
    ('CHN_15', '바드', 'bard'),
    ('CHN_16', '벨베스', 'belveth'),
    ('CHN_17', '블리츠크랭크', 'blitzcrank'),
    ('CHN_18', '브랜드', 'brand'),
    ('CHN_19', '브라움', 'braum'),
    ('CHN_20', '브라이어', 'briar'),
    ('CHN_21', '케이틀린', 'caitlyn'),
    ('CHN_22', '카밀', 'camille'),
    ('CHN_23', '카시오페아', 'cassiopeia'),
    ('CHN_24', '초가스', 'chogath'),
    ('CHN_25', '코르키', 'corki'),
    ('CHN_26', '다리우스', 'darius'),
    ('CHN_27', '다이애나', 'diana'),
    ('CHN_28', '드레이븐', 'draven'),
    ('CHN_29', '문도박사', 'drmundo'),
    ('CHN_30', '에코', 'ekko'),
    ('CHN_31', '엘리스', 'elise'),
    ('CHN_32', '이블린', 'evelynn'),
    ('CHN_33', '이즈리얼', 'ezreal'),
    ('CHN_34', '피들스틱', 'fiddlesticks'),
    ('CHN_35', '피오라', 'fiora'),
    ('CHN_36', '피즈', 'fizz'),
    ('CHN_37', '갈리오', 'galio'),
    ('CHN_38', '가렌', 'garen'),
    ('CHN_39', '나르', 'gnar'),
    ('CHN_40', '그라가스', 'gragas'),
    ('CHN_41', '그레이브즈', 'graves'),
    ('CHN_42', '갱플랭크', 'gangplank'),
    ('CHN_43', '그웬', 'gwen'),
    ('CHN_44', '헤카림', 'hecarim'),
    ('CHN_45', '하이머딩거', 'heimerdinger'),
    ('CHN_46', '흐웨이', 'hwei'),
    ('CHN_47', '일라오이', 'illaoi'),
    ('CHN_48', '이렐리아', 'irelia'),
    ('CHN_49', '아이번', 'ivern'),
    ('CHN_50', '잔나', 'janna'),
    ('CHN_51', '자르반4세', 'jarvaniv'),
    ('CHN_52', '잭스', 'jax'),
    ('CHN_53', '제이스', 'jayce'),
    ('CHN_54', '진', 'jhin'),
    ('CHN_55', '징크스', 'jinx'),
    ('CHN_56', '카이사', 'kaisa'),
    ('CHN_57', '칼리스타', 'kalista'),
    ('CHN_58', '카르마', 'karma'),
    ('CHN_59', '카서스', 'karthus'),
    ('CHN_60', '카사딘', 'kassadin'),
    ('CHN_61', '카타리나', 'katarina'),
    ('CHN_62', '케일', 'kayle'),
    ('CHN_63', '케인', 'kayn'),
    ('CHN_64', '케넨', 'kennen'),
    ('CHN_65', '카직스', 'khazix'),
    ('CHN_66', '킨드레드', 'kindred'),
    ('CHN_67', '클레드', 'kled'),
    ('CHN_68', '코그모', 'kogmaw'),
    ('CHN_69', '크산테', 'ksante'),
    ('CHN_70', '르블랑', 'leblanc'),
    ('CHN_71', '리신', 'leesin'),
    ('CHN_72', '레오나', 'leona'),
    ('CHN_73', '릴리아', 'lillia'),
    ('CHN_74', '리산드라', 'lissandra'),
    ('CHN_75', '루시안', 'lucian'),
    ('CHN_76', '룰루', 'lulu'),
    ('CHN_77', '럭스', 'lux'),
    ('CHN_78', '말파이트', 'malphite'),
    ('CHN_79', '마오카이', 'maokai'),
    ('CHN_80', '미스포츈', 'missfortune'),
    ('CHN_81', '오공', 'monkeyking'),
    ('CHN_82', '모데카이저', 'mordekaiser'),
    ('CHN_83', '모르가나', 'morgana'),
    ('CHN_84', '마스터이', 'masteryi'),
    ('CHN_85', '말자하', 'malzahar'),
    ('CHN_86', '밀리오', 'milio'),
    ('CHN_87', '멜', 'mel'),
    ('CHN_88', '나미', 'nami'),
    ('CHN_89', '나서스', 'nasus'),
    ('CHN_90', '나피리', 'naafiri'),
    ('CHN_91', '노틸러스', 'nautilus'),
    ('CHN_92', '니코', 'neeko'),
    ('CHN_93', '니달리', 'nidalee'),
    ('CHN_94', '녹턴', 'nocturne'),
    ('CHN_95', '누누', 'nunu'),
    ('CHN_96', '닐라', 'nilah'),
    ('CHN_97', '올라프', 'olaf'),
    ('CHN_98', '오리아나', 'orianna'),
    ('CHN_99', '오른', 'ornn'),
    ('CHN_100', '판테온', 'pantheon'),
    ('CHN_101', '뽀삐', 'poppy'),
    ('CHN_102', '파이크', 'pyke'),
    ('CHN_103', '키아나', 'qiyana'),
    ('CHN_104', '퀸', 'quinn'),
    ('CHN_105', '라칸', 'rakan'),
    ('CHN_106', '람머스', 'rammus'),
    ('CHN_107', '렉사이', 'reksai'),
    ('CHN_108', '렐', 'rell'),
    ('CHN_109', '레넥톤', 'renekton'),
    ('CHN_110', '렝가', 'rengar'),
    ('CHN_111', '럼블', 'rumble'),
    ('CHN_112', '라이즈', 'ryze'),
    ('CHN_113', '레나타', 'renata'),
    ('CHN_114', '리븐', 'riven'),
    ('CHN_115', '사미라', 'samira'),
    ('CHN_116', '세주아니', 'sejuani'),
    ('CHN_117', '세나', 'senna'),
    ('CHN_118', '세라핀', 'seraphine'),
    ('CHN_119', '세트', 'sett'),
    ('CHN_120', '샤코', 'shaco'),
    ('CHN_121', '쉔', 'shen'),
    ('CHN_122', '쉬바나', 'shyvana'),
    ('CHN_123', '신지드', 'singed'),
    ('CHN_124', '사이온', 'sion'),
    ('CHN_125', '시비르', 'sivir'),
    ('CHN_126', '스카너', 'skarner'),
    ('CHN_127', '스몰더', 'smolder'),
    ('CHN_128', '소나', 'sona'),
    ('CHN_129', '소라카', 'soraka'),
    ('CHN_130', '스웨인', 'swain'),
    ('CHN_131', '사일러스', 'sylas'),
    ('CHN_132', '신드라', 'syndra'),
    ('CHN_133', '탐켄치', 'tahmkench'),
    ('CHN_134', '탈리야', 'taliyah'),
    ('CHN_135', '탈론', 'talon'),
    ('CHN_136', '타릭', 'taric'),
    ('CHN_137', '티모', 'teemo'),
    ('CHN_138', '쓰레쉬', 'thresh'),
    ('CHN_139', '트리스타나', 'tristana'),
    ('CHN_140', '트런들', 'trundle'),
    ('CHN_141', '트린다미어', 'tryndamere'),
    ('CHN_142', '트페', 'twistedfate'),
    ('CHN_143', '트위치', 'twitch'),
    ('CHN_144', '우디르', 'udyr'),
    ('CHN_145', '우르곳', 'urgot'),
    ('CHN_146', '바루스', 'varus'),
    ('CHN_147', '베인', 'vayne'),
    ('CHN_148', '베이가', 'veigar'),
    ('CHN_149', '벨코즈', 'velkoz'),
    ('CHN_150', '벡스', 'vex'),
    ('CHN_151', '바이', 'vi'),
    ('CHN_152', '비에고', 'viego'),
    ('CHN_153', '빅토르', 'viktor'),
    ('CHN_154', '블라디미르', 'vladimir'),
    ('CHN_155', '볼리베어', 'volibear'),
    ('CHN_156', '워윅', 'warwick'),
    ('CHN_157', '자야', 'xayah'),
    ('CHN_158', '제라스', 'xerath'),
    ('CHN_159', '신짜오', 'xinzhao'),
    ('CHN_160', '야스오', 'yasuo'),
    ('CHN_161', '요네', 'yone'),
    ('CHN_162', '요릭', 'yorick'),
    ('CHN_163', '유미', 'yuumi'),
    ('CHN_164', '자크', 'zac'),
    ('CHN_165', '제드', 'zed'),
    ('CHN_166', '제리', 'zeri'),
    ('CHN_167', '직스', 'ziggs'),
    ('CHN_168', '질리언', 'zilean'),
    ('CHN_169', '조이', 'zoe'),
    ('CHN_170', '자이라', 'zyra');

-- 트리거
CREATE OR REPLACE FUNCTION fn_parse_league_rawdata()
RETURNS TRIGGER AS $$
BEGIN
    -- Player 테이블에 삽입
    INSERT INTO Player (player_id, riot_name, riot_name_tag, guild_id, puuid, create_date, update_date)
    SELECT DISTINCT
        'PLR_' || (COALESCE((SELECT MAX(CAST(SUBSTRING(player_id FROM 5) AS INTEGER)) FROM Player), 0) + 
                   ROW_NUMBER() OVER (ORDER BY (SELECT NULL))) AS player_id,
        TRIM(REPLACE(REPLACE(data ->> 'RIOT_ID_GAME_NAME', 'й', 'n'), ' ', '')) AS riot_name,
        TRIM(REPLACE(REPLACE(data ->> 'RIOT_ID_TAG_LINE', 'й', 'n'), ' ', '')) AS riot_name_tag,
        NEW.guild_id AS guild_id,
        data ->> 'PUUID' AS puuid,
        NOW() AS create_date,
        NOW() AS update_date
--    FROM jsonb_array_elements(NEW.raw_data) AS player
    From jsonb_array_elements(NEW.raw_data::jsonb) AS data
    WHERE NOT EXISTS (
        SELECT 1 FROM Player 
        WHERE riot_name = TRIM(REPLACE(REPLACE(data ->> 'RIOT_ID_GAME_NAME', 'й', 'n'), ' ', ''))
        AND riot_name_tag = TRIM(REPLACE(REPLACE(data ->> 'RIOT_ID_TAG_LINE', 'й', 'n'), ' ', ''))
        AND delete_yn = 'N'
        AND guild_id = NEW.guild_id
    );

    -- Player_game 테이블에 삽입
    INSERT INTO Player_game (
        player_game_id, player_id, champion_id, game_id, game_date, game_team, 
        game_result, game_type, position, kill, death, assist, gold, ccing, time_played, 
        total_damage_champions, total_damage_taken, vision_score, vision_bought, penta_kills, 
        create_date, update_date
    )
    SELECT 
        'PLG_' || (COALESCE((SELECT MAX(CAST(SUBSTRING(player_game_id FROM 5) AS INTEGER)) FROM Player_game), 0) + 
                   ROW_NUMBER() OVER (ORDER BY (SELECT NULL))) AS player_game_id,
        ( SELECT COALESCE(main_player_id, player_id)
          FROM Player
          WHERE delete_yn = 'N'
          AND guild_id = NEW.guild_id
          AND riot_name = TRIM(REPLACE(REPLACE(game ->> 'RIOT_ID_GAME_NAME', 'й', 'n'), ' ', ''))
          AND riot_name_tag = TRIM(REPLACE(REPLACE(game ->> 'RIOT_ID_TAG_LINE', 'й', 'n'), ' ', ''))
        ),
        COALESCE(
            ( SELECT champion_id
              FROM Champion
              WHERE champ_name_eng = LOWER(TRIM(game ->> 'SKIN'))
              AND delete_yn = 'N'
            ),
            LOWER(TRIM(game ->> 'SKIN'))
        ),
        NEW.game_id,
        NEW.game_date,
        CASE game ->> 'TEAM' 
            WHEN '100' THEN 'blue' 
            WHEN '200' THEN 'red' 
            ELSE game ->> 'TEAM' 
        END,
        CASE game ->> 'WIN' 
            WHEN 'Win' THEN '승' 
            ELSE '패' 
        END,
        NEW.game_type,
        CASE game ->> 'INDIVIDUAL_POSITION' 
            WHEN 'JUNGLE' THEN 'JUG' 
            WHEN 'BOTTOM' THEN 'ADC' 
            WHEN 'UTILITY' THEN 'SUP' 
            WHEN 'MIDDLE' THEN 'MID' 
            ELSE game ->> 'INDIVIDUAL_POSITION' 
        END,
        (game ->> 'CHAMPIONS_KILLED')::INTEGER,
        (game ->> 'NUM_DEATHS')::INTEGER,
        (game ->> 'ASSISTS')::INTEGER,
        (game ->> 'GOLD_EARNED')::INTEGER,
        (game ->> 'TIME_CCING_OTHERS')::INTEGER,
        (game ->> 'TIME_PLAYED')::INTEGER,
        (game ->> 'TOTAL_DAMAGE_DEALT_TO_CHAMPIONS')::INTEGER,
        (game ->> 'TOTAL_DAMAGE_TAKEN')::INTEGER,
        (game ->> 'VISION_SCORE')::INTEGER,
        (game ->> 'VISION_WARDS_BOUGHT_IN_GAME')::INTEGER,
        (game ->> 'PENTA_KILLS')::INTEGER,
        NOW(),
        NOW()
    FROM jsonb_array_elements(NEW.raw_data) AS game;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_insert_league
AFTER INSERT ON League
FOR EACH ROW
EXECUTE FUNCTION fn_parse_league_rawdata();