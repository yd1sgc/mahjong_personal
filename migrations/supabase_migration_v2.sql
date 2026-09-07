-- ==============================================================================
-- Supabase (PostgreSQL) Migration Script: V2 Normalized Architecture
-- Version: 2.0.0
-- Description:
--   1. 第3正規形・UUID v7・完全縦持ち構造への移行
--   2. members (UUID), groups (UUID), group_memberships, rule_templates (JSONB)
--   3. games (UUID), game_participants, rounds (UUID), round_seats
--   4. drafts (JSONB)
--   5. 旧テーブル（V1）の安全退避およびインデックス作成
-- ==============================================================================

BEGIN;

-- 1. スキーマバージョンメタテーブル
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_meta (key, value)
VALUES ('schema_version', '2.0.0')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();

-- 2. 旧テーブルの安全退避（INTEGER ID の旧テーブルが存在する場合）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'games' AND column_name = 'game_id' AND data_type = 'integer'
    ) THEN
        ALTER TABLE games RENAME TO games_v1_backup;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'rounds' AND column_name = 'id' AND data_type = 'integer'
    ) THEN
        ALTER TABLE rounds RENAME TO rounds_v1_backup;
    END IF;
END $$;

-- 3. マスタテーブル群
CREATE TABLE IF NOT EXISTS members (
    member_id TEXT PRIMARY KEY,
    member_name TEXT NOT NULL,
    is_guest INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    display_id TEXT,
    group_name TEXT NOT NULL,
    default_rule_id TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS group_memberships (
    group_id TEXT NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    member_id TEXT NOT NULL REFERENCES members(member_id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, member_id)
);

CREATE TABLE IF NOT EXISTS rule_templates (
    rule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    config_json JSONB NOT NULL,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. 対局・成績テーブル群（完全縦持ち）
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    played_at TIMESTAMPTZ NOT NULL,
    group_id TEXT REFERENCES groups(group_id) ON DELETE SET NULL,
    rule_name_snapshot TEXT NOT NULL,
    rule_config_snapshot JSONB NOT NULL,
    game_mode TEXT NOT NULL DEFAULT 'detail',
    sync_target INTEGER NOT NULL DEFAULT 1,
    is_synced INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS game_participants (
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    member_id TEXT NOT NULL REFERENCES members(member_id) ON DELETE RESTRICT,
    player_name_snapshot TEXT NOT NULL,
    final_score INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    point NUMERIC(6,1) NOT NULL,
    was_group_member INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (game_id, seat)
);

CREATE TABLE IF NOT EXISTS rounds (
    round_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    round_index INTEGER NOT NULL,
    kyoku_name TEXT NOT NULL,
    honba INTEGER NOT NULL DEFAULT 0,
    riichi_sticks INTEGER NOT NULL DEFAULT 0,
    result_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS round_seats (
    round_id TEXT NOT NULL REFERENCES rounds(round_id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    member_id TEXT NOT NULL REFERENCES members(member_id) ON DELETE RESTRICT,
    base_point INTEGER NOT NULL DEFAULT 0,
    honba_point INTEGER NOT NULL DEFAULT 0,
    kyotaku_point INTEGER NOT NULL DEFAULT 0,
    penalty_point INTEGER NOT NULL DEFAULT 0,
    score_delta INTEGER NOT NULL DEFAULT 0,
    chip_delta INTEGER NOT NULL DEFAULT 0,
    han INTEGER,
    fu INTEGER,
    is_winner INTEGER NOT NULL DEFAULT 0,
    is_loser INTEGER NOT NULL DEFAULT 0,
    is_riichi INTEGER NOT NULL DEFAULT 0,
    is_furo INTEGER NOT NULL DEFAULT 0,
    is_tenpai INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (round_id, seat)
);

-- 5. ドラフト（下書き）テーブル
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    state_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. パフォーマンスインデックス
CREATE INDEX IF NOT EXISTS idx_games_played_at ON games(played_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_group ON games(group_id);
CREATE INDEX IF NOT EXISTS idx_game_participants_member ON game_participants(member_id);
CREATE INDEX IF NOT EXISTS idx_game_participants_rank ON game_participants(rank);
CREATE INDEX IF NOT EXISTS idx_rounds_game_id ON rounds(game_id, round_index);
CREATE INDEX IF NOT EXISTS idx_round_seats_member ON round_seats(member_id);

-- 7. 公式ルールプリセットのシード投入
INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
VALUES 
(
    'preset_m_league', 'Mリーグルール', 'official', 1,
    '{"basic": {"init_score": 25000, "return_score": 30000, "uma": [30, 10, -10, -30], "rounding_type": "四捨五入"}, "detail": {"tobi_end": "none", "agari_yame": "none", "honba_pt": 300, "riichi_pt": 1000, "game_length": "hanchan"}}'::jsonb,
    0
),
(
    'preset_standard', '一般アリアリ（ゴットー）', 'official', 1,
    '{"basic": {"init_score": 25000, "return_score": 30000, "uma": [10, 5, -5, -10], "rounding_type": "五捨六入"}, "detail": {"tobi_end": "under_zero", "agari_yame": "top_only", "honba_pt": 300, "riichi_pt": 1000, "game_length": "hanchan"}}'::jsonb,
    0
),
(
    'preset_saikouisen', '最高位戦日本プロ麻雀協会', 'official', 1,
    '{"basic": {"init_score": 30000, "return_score": 30000, "uma": [30, 10, -10, -30], "rounding_type": "四捨五入"}, "detail": {"tobi_end": "none", "agari_yame": "none", "honba_pt": 300, "riichi_pt": 1000, "game_length": "hanchan"}}'::jsonb,
    0
)
ON CONFLICT (rule_id) DO NOTHING;

COMMIT;
