-- Align existing mmr_user_summary columns with the position codes emitted by MMR.
-- Run once against databases created with the old bottom/middle/jungle/utility names.
BEGIN;

ALTER TABLE mmr_user_summary RENAME COLUMN bottom_mmr TO adc_mmr;
ALTER TABLE mmr_user_summary RENAME COLUMN bottom_winrate TO adc_winrate;
ALTER TABLE mmr_user_summary RENAME COLUMN bottom_games TO adc_games;

ALTER TABLE mmr_user_summary RENAME COLUMN middle_mmr TO mid_mmr;
ALTER TABLE mmr_user_summary RENAME COLUMN middle_winrate TO mid_winrate;
ALTER TABLE mmr_user_summary RENAME COLUMN middle_games TO mid_games;

ALTER TABLE mmr_user_summary RENAME COLUMN jungle_mmr TO jug_mmr;
ALTER TABLE mmr_user_summary RENAME COLUMN jungle_winrate TO jug_winrate;
ALTER TABLE mmr_user_summary RENAME COLUMN jungle_games TO jug_games;

ALTER TABLE mmr_user_summary RENAME COLUMN utility_mmr TO sup_mmr;
ALTER TABLE mmr_user_summary RENAME COLUMN utility_winrate TO sup_winrate;
ALTER TABLE mmr_user_summary RENAME COLUMN utility_games TO sup_games;

COMMIT;
