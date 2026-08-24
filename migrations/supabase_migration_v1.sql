-- ==============================================================================
-- Supabase (PostgreSQL) Migration Script: Identity, Rules, and Participants Schema
-- Version: 1
-- Description:
--   1. schema_meta テーブルの作成（バージョン管理）
--   2. games テーブルの拡張（selected_group_id, rule_name_snapshot 等）
--   3. members テーブルの作成（メンバーID管理、表示名重複対応）
--   4. groups / group_memberships テーブルの作成（グループ・所属管理）
--   5. rule_templates テーブルの作成（公式・カスタムルールのテンプレート管理）
--   6. game_participants テーブルの作成（対局参加者・席順・スコア・順位の正規化）
--   7. 既存の games テーブルから game_participants への過去データ非破壊移行
--   8. 公式ルールテンプレート（Mリーグ、一般アリアリ、最高位戦）の初期シード投入
-- ==============================================================================

-- 1. メタ情報テーブル
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 2. 既存 games テーブルの拡張（カラムが存在しない場合のみ追加）
CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY,
    date TEXT,
    p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
    p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
    p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
    p4_name TEXT, p4_score INTEGER, p4_rank INTEGER,
    group_id TEXT DEFAULT 'all',
    rule_id TEXT DEFAULT 'm_league',
    applied_rule_json TEXT
);

ALTER TABLE games ADD COLUMN IF NOT EXISTS selected_group_id TEXT;
ALTER TABLE games ADD COLUMN IF NOT EXISTS rule_name_snapshot TEXT;
ALTER TABLE games ADD COLUMN IF NOT EXISTS rule_schema_version INTEGER DEFAULT 1;
ALTER TABLE games ADD COLUMN IF NOT EXISTS applied_rule_json TEXT;

-- rounds テーブルの安全確保
CREATE TABLE IF NOT EXISTS rounds (
    id SERIAL PRIMARY KEY,
    game_id INTEGER,
    kyoku_name TEXT,
    winner TEXT,
    loser TEXT,
    score INTEGER,
    furo_names TEXT,
    riichi_names TEXT,
    riichi_count INTEGER,
    tenpai_names TEXT DEFAULT '',
    win_type TEXT DEFAULT ''
);
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS tenpai_names TEXT DEFAULT '';
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS win_type TEXT DEFAULT '';

-- drafts テーブルの安全確保
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    state_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. メンバーマスターテーブル
CREATE TABLE IF NOT EXISTS members (
    member_id BIGSERIAL PRIMARY KEY,
    member_name TEXT NOT NULL,
    is_archived INTEGER NOT NULL DEFAULT 0
);

-- 4. グループおよびグループ所属テーブル
CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    group_name TEXT NOT NULL,
    default_rule_id TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS group_memberships (
    group_id TEXT NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    member_id BIGINT NOT NULL REFERENCES members(member_id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, member_id)
);

-- 5. ルールテンプレートテーブル
CREATE TABLE IF NOT EXISTS rule_templates (
    rule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    config_json JSONB NOT NULL,
    is_archived INTEGER NOT NULL DEFAULT 0
);

-- 6. 対局参加者テーブル
CREATE TABLE IF NOT EXISTS game_participants (
    game_id INTEGER NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    seat INTEGER NOT NULL CHECK (seat BETWEEN 1 AND 4),
    member_id BIGINT REFERENCES members(member_id) ON DELETE SET NULL,
    display_name_snapshot TEXT NOT NULL,
    score INTEGER,
    rank INTEGER,
    was_group_member INTEGER CHECK (was_group_member IN (0, 1) OR was_group_member IS NULL),
    PRIMARY KEY (game_id, seat)
);

-- 7. 既存対局データ（games）から game_participants への安全なデータ移行
-- Seat 1
INSERT INTO game_participants (game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member)
SELECT 
    g.game_id,
    1 AS seat,
    m.member_id,
    g.p1_name AS display_name_snapshot,
    g.p1_score AS score,
    g.p1_rank AS rank,
    NULL AS was_group_member
FROM games g
LEFT JOIN members m ON m.member_name = g.p1_name AND m.is_archived = 0
WHERE g.p1_name IS NOT NULL AND TRIM(g.p1_name) != ''
ON CONFLICT (game_id, seat) DO NOTHING;

-- Seat 2
INSERT INTO game_participants (game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member)
SELECT 
    g.game_id,
    2 AS seat,
    m.member_id,
    g.p2_name AS display_name_snapshot,
    g.p2_score AS score,
    g.p2_rank AS rank,
    NULL AS was_group_member
FROM games g
LEFT JOIN members m ON m.member_name = g.p2_name AND m.is_archived = 0
WHERE g.p2_name IS NOT NULL AND TRIM(g.p2_name) != ''
ON CONFLICT (game_id, seat) DO NOTHING;

-- Seat 3
INSERT INTO game_participants (game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member)
SELECT 
    g.game_id,
    3 AS seat,
    m.member_id,
    g.p3_name AS display_name_snapshot,
    g.p3_score AS score,
    g.p3_rank AS rank,
    NULL AS was_group_member
FROM games g
LEFT JOIN members m ON m.member_name = g.p3_name AND m.is_archived = 0
WHERE g.p3_name IS NOT NULL AND TRIM(g.p3_name) != ''
ON CONFLICT (game_id, seat) DO NOTHING;

-- Seat 4
INSERT INTO game_participants (game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member)
SELECT 
    g.game_id,
    4 AS seat,
    m.member_id,
    g.p4_name AS display_name_snapshot,
    g.p4_score AS score,
    g.p4_rank AS rank,
    NULL AS was_group_member
FROM games g
LEFT JOIN members m ON m.member_name = g.p4_name AND m.is_archived = 0
WHERE g.p4_name IS NOT NULL AND TRIM(g.p4_name) != ''
ON CONFLICT (game_id, seat) DO NOTHING;

-- 8. 公式ルールテンプレートのシード投入
INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
VALUES
(
    'preset_m_league',
    'Mリーグルール',
    'official',
    1,
    '{"basic": {"player_count": 4, "init_score": 25000, "return_score": 30000, "uma": [50, 10, -10, -30], "oka_type": "top_takes_all", "rate_note": "1000点＝1.0pt", "rounding_type": "五捨六入"}, "detail": {"kuitan": true, "atozuke": true, "aka_dora": "3枚", "dora_setting": "all", "kuikae": "forbidden", "tobi_end": "none", "west_extension": "none", "agari_yame": true, "renchan_rule": "tenpai", "dubron": "atama_hane", "pao": true, "chombo_rule": "mangan_pay", "house_notes": "Mリーグ公式規則準拠"}}'::jsonb,
    0
),
(
    'preset_standard_ari',
    '一般アリアリ標準',
    'official',
    1,
    '{"basic": {"player_count": 4, "init_score": 25000, "return_score": 30000, "uma": [50, 10, -10, -30], "oka_type": "top_takes_all", "rate_note": "1000点＝1.0pt (×0.2)", "rounding_type": "五捨六入"}, "detail": {"kuitan": true, "atozuke": true, "aka_dora": "3枚", "dora_setting": "all", "kuikae": "forbidden", "tobi_end": "under_zero", "west_extension": "under_30000", "agari_yame": true, "renchan_rule": "tenpai", "dubron": "atama_hane", "pao": true, "chombo_rule": "mangan_pay", "house_notes": "一般的なセット麻雀ルール"}}'::jsonb,
    0
),
(
    'preset_saikouike',
    '最高位戦公式ルール',
    'official',
    1,
    '{"basic": {"player_count": 4, "init_score": 30000, "return_score": 30000, "uma": [30, 10, -10, -30], "oka_type": "none", "rate_note": "オカなし", "rounding_type": "五捨六入"}, "detail": {"kuitan": true, "atozuke": true, "aka_dora": "なし", "dora_setting": "all", "kuikae": "forbidden", "tobi_end": "none", "west_extension": "none", "agari_yame": false, "renchan_rule": "tenpai", "dubron": "atama_hane", "pao": true, "chombo_rule": "mangan_pay", "house_notes": "最高位戦日本プロ麻雀協会公式ルール"}}'::jsonb,
    0
),
(
    'rule_shinseki',
    '親族麻雀ルール',
    'custom',
    1,
    '{"basic": {"player_count": 4, "init_score": 25000, "return_score": 30000, "uma": [50, 10, -10, -30], "oka_type": "top_takes_all", "rate_note": "1000点＝1.0pt", "rounding_type": "goshagokyu"}, "detail": {"kuitan": true, "atozuke": true, "aka_dora": "3枚", "dora_setting": "all", "kuikae": "forbidden", "kyushu": "renchan", "sufon": "none", "sujin_riichi": "none", "sukan": "allowed_single", "nagashi_mangan": "mangan_renchan", "dubron": "atama_hane", "furiten_tsumo": true, "tsumoban_none_riichi": false, "ippatsu": true, "renho": "none", "tobi_end": "under_zero", "tobi_penalty_pt": 0, "west_extension": "under_30000", "agari_yame": true, "tenpai_yame": true, "renchan_rule": "tenpai", "yakuman_multiple": true, "kokushi_ankan_win": true, "pao": true, "chombo_rule": "mangan_pay", "chombo_pt": 20, "house_notes": ""}}'::jsonb,
    0
)
ON CONFLICT (rule_id) DO UPDATE SET
    name = EXCLUDED.name,
    config_json = EXCLUDED.config_json,
    is_archived = 0;

-- 旧重複 m_league カスタムルールの削除
DELETE FROM rule_templates WHERE rule_id = 'm_league' AND kind = 'custom';

-- 9. スキーマバージョンの記録
INSERT INTO schema_meta (key, value)
VALUES ('identity_schema_version', '1')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
