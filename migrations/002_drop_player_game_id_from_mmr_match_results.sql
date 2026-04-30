-- player_game_id is not needed in the row-level MMR result table.
-- Existing databases that already applied migration 001 can apply this safely.

ALTER TABLE mmr_match_results
    DROP COLUMN IF EXISTS player_game_id;
