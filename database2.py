import json
import os
import sqlite3
import pandas as pd
import streamlit as st
from contextlib import contextmanager
from datetime import datetime

try:
    import psycopg2
except ImportError:
    psycopg2 = None

IS_LOCAL = st.secrets.get("local_mode", False)
# テスト開発用データベース（本番mahjong_local.dbを100%保護するための分離ファイル）
SQLITE_PATH = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_test.db" if IS_LOCAL else None

IDENTITY_SCHEMA_VERSION = 1


def _table_exists(cursor, table_name):
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def _add_column_if_missing(cursor, table_name, column_name, column_type):
    columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def migrate_local_identity_schema(conn):
    """ID中心のローカルスキーマへ移行する。

    呼び出し元が渡したSQLite接続だけを変更する。アプリ起動時には実行しないため、
    実在DBへの適用はバックアップ・確認後に明示的に行う。
    """
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = OFF")

    c.execute('''CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')

    # 既存のgames列は保持し、対局時点の不変情報だけを追加する。
    if _table_exists(c, "games"):
        _add_column_if_missing(c, "games", "selected_group_id", "TEXT")
        _add_column_if_missing(c, "games", "rule_name_snapshot", "TEXT")
        _add_column_if_missing(c, "games", "rule_schema_version", "INTEGER")

    # 旧membersは名前にUNIQUE制約があり、同名の別人を表現できない。
    # 旧データを同じmember_idでコピーしてから、安全に制約を外す。
    legacy_members = "members_legacy_identity_v1"
    if _table_exists(c, "members"):
        members_sql = c.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='members'"
        ).fetchone()[0] or ""
        if "UNIQUE" in members_sql.upper() and not _table_exists(c, legacy_members):
            c.execute(f"ALTER TABLE members RENAME TO {legacy_members}")

    c.execute('''CREATE TABLE IF NOT EXISTS members (
        member_id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_name TEXT NOT NULL,
        is_archived INTEGER NOT NULL DEFAULT 0
    )''')

    if _table_exists(c, legacy_members):
        c.execute(f'''INSERT OR IGNORE INTO members (member_id, member_name, is_archived)
            SELECT member_id, member_name, 0 FROM {legacy_members}''')
        c.execute(f"DROP TABLE {legacy_members}")

    if c.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 0:
        from constants import MEMBERS
        c.executemany(
            "INSERT INTO members (member_name) VALUES (?)",
            [(name,) for name in MEMBERS]
        )

    c.execute('''CREATE TABLE IF NOT EXISTS groups (
        group_id TEXT PRIMARY KEY,
        group_name TEXT NOT NULL,
        default_rule_id TEXT,
        is_archived INTEGER NOT NULL DEFAULT 0
    )''')
    if _table_exists(c, "member_groups"):
        c.execute('''INSERT OR IGNORE INTO groups
            (group_id, group_name, default_rule_id, is_archived)
            SELECT group_id, group_name, default_rule_id, 0 FROM member_groups''')

    c.execute('''CREATE TABLE IF NOT EXISTS group_memberships (
        group_id TEXT NOT NULL,
        member_id INTEGER NOT NULL,
        PRIMARY KEY (group_id, member_id),
        FOREIGN KEY (group_id) REFERENCES groups(group_id),
        FOREIGN KEY (member_id) REFERENCES members(member_id)
    )''')
    if _table_exists(c, "group_members"):
        legacy_links = c.execute(
            "SELECT group_id, member_name FROM group_members"
        ).fetchall()
        for group_id, member_name in legacy_links:
            member = c.execute(
                "SELECT member_id FROM members WHERE member_name=? ORDER BY member_id LIMIT 1",
                (member_name,)
            ).fetchone()
            if member is None:
                c.execute("INSERT INTO members (member_name) VALUES (?)", (member_name,))
                member_id = c.lastrowid
            else:
                member_id = member[0]
            c.execute(
                "INSERT OR IGNORE INTO group_memberships (group_id, member_id) VALUES (?, ?)",
                (group_id, member_id)
            )

    c.execute('''CREATE TABLE IF NOT EXISTS game_participants (
        game_id INTEGER NOT NULL,
        seat INTEGER NOT NULL CHECK (seat BETWEEN 1 AND 4),
        member_id INTEGER,
        display_name_snapshot TEXT NOT NULL,
        score INTEGER,
        rank INTEGER,
        was_group_member INTEGER CHECK (was_group_member IN (0, 1) OR was_group_member IS NULL),
        PRIMARY KEY (game_id, seat),
        FOREIGN KEY (member_id) REFERENCES members(member_id)
    )''')

    if _table_exists(c, "games"):
        for seat in range(1, 5):
            rows = c.execute(
                f"""SELECT game_id, p{seat}_name, p{seat}_score, p{seat}_rank
                    FROM games WHERE p{seat}_name IS NOT NULL AND TRIM(p{seat}_name) != ''"""
            ).fetchall()
            for game_id, name, score, rank in rows:
                member = c.execute(
                    "SELECT member_id FROM members WHERE member_name=? ORDER BY member_id LIMIT 1",
                    (name,)
                ).fetchone()
                c.execute('''INSERT OR IGNORE INTO game_participants
                    (game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member)
                    VALUES (?, ?, ?, ?, ?, ?, NULL)''',
                    (game_id, seat, member[0] if member else None, name, score, rank)
                )

    c.execute('''CREATE TABLE IF NOT EXISTS rule_templates (
        rule_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        config_json TEXT NOT NULL,
        is_archived INTEGER NOT NULL DEFAULT 0
    )''')
    
    if _table_exists(c, "rules"):
        c.execute('''INSERT OR IGNORE INTO rule_templates
            (rule_id, name, kind, version, config_json, is_archived)
            SELECT rule_id, rule_name, 'custom', 1, config_json, 0 FROM rules
        ''')
    
    # Seed official templates
    for p in OFFICIAL_PRESETS:
        config_str = json.dumps(p["config"], ensure_ascii=False)
        c.execute('''INSERT INTO rule_templates
            (rule_id, name, kind, version, config_json, is_archived)
            VALUES (?, ?, 'official', 1, ?, 0)
            ON CONFLICT(rule_id) DO UPDATE SET
            name=excluded.name, config_json=excluded.config_json, is_archived=0
        ''', (p["rule_id"], p["rule_name"], config_str))

    c.execute('''INSERT INTO schema_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value''',
        ("identity_schema_version", str(IDENTITY_SCHEMA_VERSION))
    )


def get_local_connection():
    return sqlite3.connect(SQLITE_PATH)


@contextmanager
def _local_db():
    conn = get_local_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("オンラインDB接続には psycopg2-binary が必要です")
    try:
        db = st.secrets["database"]
    except KeyError:
        raise RuntimeError("Streamlit secrets に [database] セクションがありません") from None
    return psycopg2.connect(
        host=db["host"],
        port=int(db["port"]),
        user=db["user"],
        password=db["password"],
        dbname=db["dbname"],
        connect_timeout=3
    )


@contextmanager
def _remote_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fetch_df(conn, query, params=None):
    c = conn.cursor()
    c.execute(query, params or ())
    rows = c.fetchall()
    cols = [desc[0] for desc in c.description]
    return pd.DataFrame(rows, columns=cols)


def _str(v):
    return v if v is not None else ""


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def get_local_unsynced_games():
    if not IS_LOCAL:
        return pd.DataFrame()
    try:
        if not os.path.exists(SQLITE_PATH):
            return pd.DataFrame()
        with _local_db() as conn:
            return _fetch_df(conn, "SELECT * FROM games WHERE is_synced = 0 ORDER BY game_id DESC")
    except Exception:
        return pd.DataFrame()


def init_local_db():
    if not IS_LOCAL:
        return
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    with _local_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            date TEXT,
            p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
            p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
            p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
            p4_name TEXT, p4_score INTEGER, p4_rank INTEGER,
            is_synced INTEGER DEFAULT 0,
            group_id TEXT DEFAULT 'all',
            rule_id TEXT DEFAULT 'm_league',
            applied_rule_json TEXT
        )''')
        for col_def in [("group_id", "TEXT DEFAULT 'all'"), ("rule_id", "TEXT DEFAULT 'm_league'"), ("applied_rule_json", "TEXT")]:
            try:
                c.execute(f"ALTER TABLE games ADD COLUMN {col_def[0]} {col_def[1]}")
            except Exception:
                pass
        c.execute('''CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            kyoku_name TEXT,
            winner TEXT,
            loser TEXT,
            score INTEGER,
            furo_names TEXT DEFAULT '',
            riichi_names TEXT DEFAULT '',
            riichi_count INTEGER DEFAULT 0,
            tenpai_names TEXT DEFAULT '',
            win_type TEXT DEFAULT '',
            is_synced INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS rules (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            config_json TEXT NOT NULL
        )''')
        # デフォルトルールのシードデータ
        c.execute("SELECT COUNT(*) FROM rules")
        if c.fetchone()[0] == 0:
            default_rules = [
                ("m_league", "Mリーグルール", 1, json.dumps({
                    "init_score": 25000, "return_score": 30000,
                    "uma": [50, 10, -10, -30], "description": "25,000点持ち/30,000点返し (ウマ +50/+10/-10/-30)"
                })),
                ("standard_10_30", "一般10-30", 0, json.dumps({
                    "init_score": 25000, "return_score": 30000,
                    "uma": [40, 10, -10, -20], "description": "25,000点持ち/30,000点返し (ウマ +40/+10/-10/-20)"
                })),
                ("gotto_5_10", "ゴットー (5-10)", 0, json.dumps({
                    "init_score": 25000, "return_score": 30000,
                    "uma": [30, 5, -5, -10], "description": "25,000点持ち/30,000点返し (ウマ +30/+5/-5/-10)"
                })),
                ("no_uma_no_oka", "ノーウマ・オカなし", 0, json.dumps({
                    "init_score": 30000, "return_score": 30000,
                    "uma": [0, 0, 0, 0], "description": "30,000点持ち/30,000点返し (ウマなし)"
                }))
            ]
            c.executemany("INSERT INTO rules VALUES (?, ?, ?, ?)", default_rules)

        c.execute('''CREATE TABLE IF NOT EXISTS member_groups (
            group_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            default_rule_id TEXT DEFAULT 'm_league'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS group_members (
            group_id TEXT NOT NULL,
            member_name TEXT NOT NULL,
            PRIMARY KEY (group_id, member_name)
        )''')
        migrate_local_identity_schema(conn)
        c.execute('''CREATE TABLE IF NOT EXISTS members (
            member_id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_name TEXT NOT NULL UNIQUE
        )''')
        # 初期メンバーの登録（未登録の場合）
        c.execute("SELECT COUNT(*) FROM members")
        if c.fetchone()[0] == 0:
            from constants import MEMBERS
            for m in MEMBERS:
                c.execute("INSERT OR IGNORE INTO members (member_name) VALUES (?)", (m,))


def check_connectivity():
    try:
        with _remote_db() as conn:
            pass
        st.session_state["online"] = True
        return True
    except Exception:
        st.session_state["online"] = False
        return False


def get_pending_count():
    if not IS_LOCAL:
        return 0
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM games WHERE is_synced = 0")
        return c.fetchone()[0]


def sync_to_supabase():
    if not IS_LOCAL:
        return 0
    local_conn = get_local_connection()
    remote_conn = None
    try:
        lc = local_conn.cursor()
        lc.execute("SELECT * FROM games WHERE is_synced = 0 ORDER BY game_id")
        games = lc.fetchall()

        if not games:
            return 0

        remote_conn = get_connection()
        rc = remote_conn.cursor()
        rc.execute("SELECT COALESCE(MAX(game_id), 0) FROM games")
        max_remote_id = rc.fetchone()[0]

        synced_count = 0
        for game in games:
            local_game_id = game[0]
            max_remote_id += 1
            new_game_id = max_remote_id

            rc.execute('''INSERT INTO games (game_id, date,
                p1_name, p1_score, p1_rank,
                p2_name, p2_score, p2_rank,
                p3_name, p3_score, p3_rank,
                p4_name, p4_score, p4_rank
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (
                new_game_id, game[1],
                game[2], game[3], game[4],
                game[5], game[6], game[7],
                game[8], game[9], game[10],
                game[11], game[12], game[13]
            ))

            lc.execute("SELECT * FROM rounds WHERE game_id=? AND is_synced=0", (local_game_id,))
            for r in lc.fetchall():
                rc.execute('''INSERT INTO rounds (
                    game_id, kyoku_name, winner, loser, score,
                    furo_names, riichi_names, riichi_count, tenpai_names, win_type
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (
                    new_game_id, r[2], r[3], r[4], r[5],
                    r[6], r[7], r[8], r[9], r[10]
                ))
            lc.execute("UPDATE rounds SET is_synced=1 WHERE game_id=?", (local_game_id,))
            lc.execute("UPDATE games SET is_synced=1 WHERE game_id=?", (local_game_id,))
            synced_count += 1

        remote_conn.commit()
        local_conn.commit()
        return synced_count
    except Exception:
        if remote_conn:
            remote_conn.rollback()
        raise
    finally:
        if remote_conn:
            remote_conn.close()
        local_conn.close()


def mark_as_synced(game_id=None):
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        if game_id:
            c.execute("UPDATE games SET is_synced = 1 WHERE game_id = ?", (game_id,))
            c.execute("UPDATE rounds SET is_synced = 1 WHERE game_id = ?", (game_id,))
        else:
            c.execute("UPDATE games SET is_synced = 1")
            c.execute("UPDATE rounds SET is_synced = 1")


def init_db():
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            date TEXT,
            p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
            p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
            p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
            p4_name TEXT, p4_score INTEGER, p4_rank INTEGER,
            group_id TEXT DEFAULT 'all',
            rule_id TEXT DEFAULT 'm_league',
            applied_rule_json TEXT
        )''')
        c.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS group_id TEXT DEFAULT 'all'")
        c.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS rule_id TEXT DEFAULT 'm_league'")
        c.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS applied_rule_json TEXT")
        c.execute('''CREATE TABLE IF NOT EXISTS rounds (
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
        )''')
        c.execute("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS tenpai_names TEXT DEFAULT ''")
        c.execute("ALTER TABLE rounds ADD COLUMN IF NOT EXISTS win_type TEXT DEFAULT ''")
        c.execute('''CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            state_json JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )''')


def clear_cache():
    """データ更新時に一瞬で古いキャッシュを全消去して最新DBを0秒反映させる安全関数"""
    try:
        st.cache_data.clear()
    except Exception:
        pass


def save_game(date_str, scores, players, local=False, rule_id="m_league", group_id="all", rule_config=None, player_member_ids=None):
    sorted_p = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    rule_json_str = json.dumps(rule_config, ensure_ascii=False) if rule_config else None
    if player_member_ids is None:
        player_member_ids = {}

    if local:
        with _local_db() as conn:
            c = conn.cursor()
            
            rule_name_snap = rule_config.get('rule_name', rule_id) if rule_config else rule_id

            c.execute('''INSERT INTO games (date,
                p1_name, p1_score, p1_rank,
                p2_name, p2_score, p2_rank,
                p3_name, p3_score, p3_rank,
                p4_name, p4_score, p4_rank,
                is_synced, group_id, rule_id, applied_rule_json, rule_name_snapshot, selected_group_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                date_str,
                sorted_p[0][0], sorted_p[0][1], 1,
                sorted_p[1][0], sorted_p[1][1], 2,
                sorted_p[2][0], sorted_p[2][1], 3,
                sorted_p[3][0], sorted_p[3][1], 4,
                0, group_id, rule_id, rule_json_str, rule_name_snap, group_id
            ))
            next_id = c.lastrowid
            
            for rank, (name, score) in enumerate(sorted_p, start=1):
                seat = players.index(name) + 1 if name in players else rank
                m_id = player_member_ids.get(name)
                c.execute('''INSERT INTO game_participants 
                    (game_id, seat, member_id, display_name_snapshot, score, rank)
                    VALUES (?, ?, ?, ?, ?, ?)''', 
                    (next_id, seat, m_id, name, score, rank))

        clear_cache()
        return next_id
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO games (date,
            p1_name, p1_score, p1_rank,
            p2_name, p2_score, p2_rank,
            p3_name, p3_score, p3_rank,
            p4_name, p4_score, p4_rank,
            group_id, rule_id, applied_rule_json
        ) VALUES (%s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s) RETURNING game_id''', (
            date_str,
            sorted_p[0][0], sorted_p[0][1], 1,
            sorted_p[1][0], sorted_p[1][1], 2,
            sorted_p[2][0], sorted_p[2][1], 3,
            sorted_p[3][0], sorted_p[3][1], 4,
            group_id, rule_id, rule_json_str
        ))
        next_id = c.fetchone()[0]
    clear_cache()
    return next_id


def save_round(game_id, kyoku_name, winner, loser, score, furo, riichi, win_type="", tenpai=None, local=False):
    furo_str = ",".join(furo) if isinstance(furo, list) else ""
    tenpai_str = ",".join(tenpai) if isinstance(tenpai, list) else ""
    if isinstance(riichi, list):
        riichi_names_str = ",".join(riichi)
        riichi_cnt = len(riichi)
    else:
        riichi_names_str = ""
        riichi_cnt = int(riichi)
    if local:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO rounds (
                game_id, kyoku_name, winner, loser, score,
                furo_names, riichi_names, riichi_count, tenpai_names, win_type, is_synced
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
                game_id, kyoku_name, winner, loser, score,
                furo_str, riichi_names_str, riichi_cnt, tenpai_str, win_type, 0
            ))
        return
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO rounds (
            game_id, kyoku_name, winner, loser, score,
            furo_names, riichi_names, riichi_count, tenpai_names, win_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", (
            game_id, kyoku_name, winner, loser, score,
            furo_str, riichi_names_str, riichi_cnt, tenpai_str, win_type
        ))


@st.cache_data(ttl=300)
def get_games_data(year_filter=None):
    if IS_LOCAL:
        with _local_db() as conn:
            query = '''
            SELECT 
                g.game_id, g.date, g.group_id, 
                COALESCE(g.rule_name_snapshot, g.rule_id) AS rule_id, 
                g.applied_rule_json, g.is_synced,
                MAX(CASE WHEN gp.seat = 1 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p1_name,
                MAX(CASE WHEN gp.seat = 1 THEN gp.score END) AS p1_score,
                MAX(CASE WHEN gp.seat = 1 THEN gp.rank END) AS p1_rank,
                MAX(CASE WHEN gp.seat = 2 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p2_name,
                MAX(CASE WHEN gp.seat = 2 THEN gp.score END) AS p2_score,
                MAX(CASE WHEN gp.seat = 2 THEN gp.rank END) AS p2_rank,
                MAX(CASE WHEN gp.seat = 3 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p3_name,
                MAX(CASE WHEN gp.seat = 3 THEN gp.score END) AS p3_score,
                MAX(CASE WHEN gp.seat = 3 THEN gp.rank END) AS p3_rank,
                MAX(CASE WHEN gp.seat = 4 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p4_name,
                MAX(CASE WHEN gp.seat = 4 THEN gp.score END) AS p4_score,
                MAX(CASE WHEN gp.seat = 4 THEN gp.rank END) AS p4_rank
            FROM games g
            LEFT JOIN game_participants gp ON g.game_id = gp.game_id
            LEFT JOIN members m ON gp.member_id = m.member_id
            GROUP BY g.game_id
            ORDER BY g.game_id DESC
            '''
            df = _fetch_df(conn, query)
    else:
        with _remote_db() as conn:
            df = _fetch_df(conn, "SELECT * FROM games ORDER BY game_id DESC")
    if df.empty:
        return df

    df['date'] = pd.to_datetime(df['date'], format='mixed')
    df = df.sort_values('game_id')
    df['match_no'] = range(1, len(df) + 1)

    if year_filter and year_filter != "全期間":
        df = df[df['date'].dt.year == int(year_filter)]

    return df.sort_values('game_id', ascending=False)


@st.cache_data(ttl=300)
def get_rounds_data():
    if IS_LOCAL:
        with _local_db() as conn:
            return _fetch_df(conn, "SELECT * FROM rounds")
    with _remote_db() as conn:
        return _fetch_df(conn, "SELECT * FROM rounds")


def load_all_games():
    if IS_LOCAL:
        with _local_db() as conn:
            query = '''
            SELECT 
                g.game_id, g.date, g.group_id, 
                COALESCE(g.rule_name_snapshot, g.rule_id) AS rule_id, 
                g.applied_rule_json, g.is_synced,
                MAX(CASE WHEN gp.seat = 1 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p1_name,
                MAX(CASE WHEN gp.seat = 1 THEN gp.score END) AS p1_score,
                MAX(CASE WHEN gp.seat = 1 THEN gp.rank END) AS p1_rank,
                MAX(CASE WHEN gp.seat = 2 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p2_name,
                MAX(CASE WHEN gp.seat = 2 THEN gp.score END) AS p2_score,
                MAX(CASE WHEN gp.seat = 2 THEN gp.rank END) AS p2_rank,
                MAX(CASE WHEN gp.seat = 3 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p3_name,
                MAX(CASE WHEN gp.seat = 3 THEN gp.score END) AS p3_score,
                MAX(CASE WHEN gp.seat = 3 THEN gp.rank END) AS p3_rank,
                MAX(CASE WHEN gp.seat = 4 THEN COALESCE(m.member_name, gp.display_name_snapshot) END) AS p4_name,
                MAX(CASE WHEN gp.seat = 4 THEN gp.score END) AS p4_score,
                MAX(CASE WHEN gp.seat = 4 THEN gp.rank END) AS p4_rank
            FROM games g
            LEFT JOIN game_participants gp ON g.game_id = gp.game_id
            LEFT JOIN members m ON gp.member_id = m.member_id
            GROUP BY g.game_id
            '''
            return _fetch_df(conn, query)
    with _remote_db() as conn:
        return _fetch_df(conn, "SELECT * FROM games")


def save_all_games(df):
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM games")
        for _, row in df.iterrows():
            c.execute('''INSERT INTO games (game_id, date,
                p1_name, p1_score, p1_rank,
                p2_name, p2_score, p2_rank,
                p3_name, p3_score, p3_rank,
                p4_name, p4_score, p4_rank
            ) VALUES (%s, %s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s)''', (
                _int(row['game_id']), _str(row.get('date')),
                _str(row.get('p1_name')), _int(row.get('p1_score')), _int(row.get('p1_rank')),
                _str(row.get('p2_name')), _int(row.get('p2_score')), _int(row.get('p2_rank')),
                _str(row.get('p3_name')), _int(row.get('p3_score')), _int(row.get('p3_rank')),
                _str(row.get('p4_name')), _int(row.get('p4_score')), _int(row.get('p4_rank')),
            ))


def load_all_rounds():
    if IS_LOCAL:
        with _local_db() as conn:
            return _fetch_df(conn, "SELECT * FROM rounds")
    with _remote_db() as conn:
        return _fetch_df(conn, "SELECT * FROM rounds")


def save_all_rounds(df):
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM rounds")
        for _, row in df.iterrows():
            c.execute('''INSERT INTO rounds (
                game_id, kyoku_name, winner, loser, score,
                furo_names, riichi_names, riichi_count, tenpai_names, win_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', (
                _int(row.get('game_id')),
                _str(row.get('kyoku_name')), _str(row.get('winner')), _str(row.get('loser')),
                _int(row.get('score', 0)),
                _str(row.get('furo_names')), _str(row.get('riichi_names')),
                _int(row.get('riichi_count', 0)),
                _str(row.get('tenpai_names')), _str(row.get('win_type')),
            ))


def update_game_scores(game_id, scores_dict):
    sorted_p = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
    name_to_rank = {name: rank for rank, (name, _) in enumerate(sorted_p, 1)}
    if IS_LOCAL:
        with _local_db() as conn:
            c = conn.cursor()
            query = '''
            SELECT 
                MAX(CASE WHEN gp.seat = 1 THEN COALESCE(m.member_name, gp.display_name_snapshot) END),
                MAX(CASE WHEN gp.seat = 2 THEN COALESCE(m.member_name, gp.display_name_snapshot) END),
                MAX(CASE WHEN gp.seat = 3 THEN COALESCE(m.member_name, gp.display_name_snapshot) END),
                MAX(CASE WHEN gp.seat = 4 THEN COALESCE(m.member_name, gp.display_name_snapshot) END)
            FROM game_participants gp
            LEFT JOIN members m ON gp.member_id = m.member_id
            WHERE gp.game_id = ?
            '''
            c.execute(query, (game_id,))
            row = c.fetchone()
            if row:
                for slot in range(1, 5):
                    name = row[slot - 1]
                    if name in scores_dict:
                        c.execute(
                            f"UPDATE games SET p{slot}_score=?, p{slot}_rank=? WHERE game_id=?",
                            (scores_dict[name], name_to_rank[name], game_id)
                        )
                        c.execute(
                            "UPDATE game_participants SET score=?, rank=? WHERE game_id=? AND seat=?",
                            (scores_dict[name], name_to_rank[name], game_id, slot)
                        )
        return
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute("SELECT p1_name, p2_name, p3_name, p4_name FROM games WHERE game_id=%s", (game_id,))
        row = c.fetchone()
        if row:
            for slot in range(1, 5):
                name = row[slot - 1]
                if name in scores_dict:
                    c.execute(
                        f"UPDATE games SET p{slot}_score=%s, p{slot}_rank=%s WHERE game_id=%s",
                        (scores_dict[name], name_to_rank[name], game_id)
                    )


def delete_game(game_id):
    if IS_LOCAL:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM games WHERE game_id=?", (game_id,))
            c.execute("DELETE FROM rounds WHERE game_id=?", (game_id,))
            c.execute("DELETE FROM game_participants WHERE game_id=?", (game_id,))
        return
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM games WHERE game_id=%s", (game_id,))
        c.execute("DELETE FROM rounds WHERE game_id=%s", (game_id,))


def save_draft(state_dict):
    if IS_LOCAL:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO drafts (id, state_json, updated_at)
                VALUES ('current', ?, datetime('now', 'localtime'))
                ON CONFLICT (id)
                DO UPDATE SET state_json = excluded.state_json, updated_at = datetime('now', 'localtime')
            """, (json.dumps(state_dict, ensure_ascii=False),))
    else:
        with _remote_db() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO drafts (id, state_json, updated_at)
                VALUES ('current', %s::jsonb, now())
                ON CONFLICT (id)
                DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = now()
            """, (json.dumps(state_dict, ensure_ascii=False),))


def load_draft():
    try:
        if IS_LOCAL:
            with _local_db() as conn:
                c = conn.cursor()
                c.execute("SELECT state_json, updated_at FROM drafts WHERE id = 'current'")
                row = c.fetchone()
                if row:
                    state = json.loads(row[0])
                    updated_at = datetime.fromisoformat(row[1])
                    return state, updated_at
        else:
            with _remote_db() as conn:
                c = conn.cursor()
                c.execute("SELECT state_json, updated_at FROM drafts WHERE id = 'current'")
                row = c.fetchone()
                if row:
                    state = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    return state, row[1]
        return None, None
    except Exception:
        return None, None


def delete_draft():
    try:
        if IS_LOCAL:
            with _local_db() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM drafts WHERE id = 'current'")
        else:
            with _remote_db() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM drafts WHERE id = 'current'")
        return True
    except Exception:
        return False


@st.cache_data(ttl=300)
def load_rounds_by_game(game_id):
    if IS_LOCAL:
        with _local_db() as conn:
            return _fetch_df(conn, "SELECT * FROM rounds WHERE game_id=? ORDER BY id", (game_id,))
    else:
        with _remote_db() as conn:
            return _fetch_df(conn, "SELECT * FROM rounds WHERE game_id=%s ORDER BY id", (game_id,))


def update_round(round_id, fields):
    """fields: dict of {column: value}"""
    if IS_LOCAL:
        with _local_db() as conn:
            c = conn.cursor()
            set_clause = ", ".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE rounds SET {set_clause} WHERE id=?",
                      list(fields.values()) + [round_id])
    else:
        with _remote_db() as conn:
            c = conn.cursor()
            set_clause = ", ".join(f"{k}=%s" for k in fields)
            c.execute(f"UPDATE rounds SET {set_clause} WHERE id=%s",
                      list(fields.values()) + [round_id])


def import_games_from_df(df):
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COALESCE(MAX(game_id), 0) + 1 FROM games")
        next_id = c.fetchone()[0]
        count = 0
        for _, row in df.iterrows():
            players = [
                (str(row['p1_name']), int(row['p1_score'])),
                (str(row['p2_name']), int(row['p2_score'])),
                (str(row['p3_name']), int(row['p3_score'])),
                (str(row['p4_name']), int(row['p4_score'])),
            ]
            sorted_p = sorted(players, key=lambda x: x[1], reverse=True)
            name_to_rank = {name: rank for rank, (name, _) in enumerate(sorted_p, 1)}
            c.execute('''INSERT INTO games (game_id, date,
                p1_name, p1_score, p1_rank,
                p2_name, p2_score, p2_rank,
                p3_name, p3_score, p3_rank,
                p4_name, p4_score, p4_rank
            ) VALUES (%s, %s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s)''', (
                next_id, str(row['date']),
                players[0][0], players[0][1], name_to_rank[players[0][0]],
                players[1][0], players[1][1], name_to_rank[players[1][0]],
                players[2][0], players[2][1], name_to_rank[players[2][0]],
                players[3][0], players[3][1], name_to_rank[players[3][0]],
            ))
            next_id += 1
            count += 1
    return count


# ── ルール管理関数 ─────────────────────────────────────────

OFFICIAL_PRESETS = [
    {
        "rule_id": "preset_m_league",
        "display_id": "PRESET-01",
        "rule_name": "Mリーグルール",
        "is_default": 0,
        "is_official": True,
        "config": {
            "basic": {"player_count": 4, "init_score": 25000, "return_score": 30000, "uma": [50, 10, -10, -30], "oka_type": "top_takes_all", "rate_note": "1000点＝1.0pt", "rounding_type": "五捨六入"},
            "detail": {"kuitan": True, "atozuke": True, "aka_dora": "3枚", "dora_setting": "all", "kuikae": "forbidden", "tobi_end": "none", "west_extension": "none", "agari_yame": True, "renchan_rule": "tenpai", "dubron": "atama_hane", "pao": True, "chombo_rule": "mangan_pay", "house_notes": "Mリーグ公式規則準拠"}
        }
    },
    {
        "rule_id": "preset_standard_ari",
        "display_id": "PRESET-02",
        "rule_name": "一般アリアリ標準",
        "is_default": 0,
        "is_official": True,
        "config": {
            "basic": {"player_count": 4, "init_score": 25000, "return_score": 30000, "uma": [50, 10, -10, -30], "oka_type": "top_takes_all", "rate_note": "1000点＝1.0pt (×0.2)", "rounding_type": "五捨六入"},
            "detail": {"kuitan": True, "atozuke": True, "aka_dora": "3枚", "dora_setting": "all", "kuikae": "forbidden", "tobi_end": "under_zero", "west_extension": "under_30000", "agari_yame": True, "renchan_rule": "tenpai", "dubron": "atama_hane", "pao": True, "chombo_rule": "mangan_pay", "house_notes": "一般的なセット麻雀ルール"}
        }
    },
    {
        "rule_id": "preset_saikouike",
        "display_id": "PRESET-03",
        "rule_name": "最高位戦公式ルール",
        "is_default": 0,
        "is_official": True,
        "config": {
            "basic": {"player_count": 4, "init_score": 30000, "return_score": 30000, "uma": [30, 10, -10, -30], "oka_type": "none", "rate_note": "オカなし", "rounding_type": "五捨六入"},
            "detail": {"kuitan": True, "atozuke": True, "aka_dora": "なし", "dora_setting": "all", "kuikae": "forbidden", "tobi_end": "none", "west_extension": "none", "agari_yame": False, "renchan_rule": "tenpai", "dubron": "atama_hane", "pao": True, "chombo_rule": "mangan_pay", "house_notes": "最高位戦日本プロ麻雀協会公式ルール"}
        }
    }
]


def get_rule_templates(include_archived=False):
    """公式・カスタムのルールテンプレートを取得"""
    if not IS_LOCAL:
        return OFFICIAL_PRESETS
    try:
        with _local_db() as conn:
            c = conn.cursor()
            query = "SELECT rule_id, name, kind, config_json, is_archived FROM rule_templates"
            if not include_archived:
                query += " WHERE is_archived = 0"
            query += " ORDER BY kind DESC, rule_id ASC" # 'official' then 'custom'
            c.execute(query)
            rows = c.fetchall()
            
            results = []
            for r in rows:
                try:
                    cfg = json.loads(r[3])
                except Exception:
                    cfg = {}
                results.append({
                    "rule_id": r[0],
                    "rule_name": r[1],
                    "kind": r[2],
                    "config": cfg,
                    "is_archived": bool(r[4])
                })
            return results
    except Exception:
        return OFFICIAL_PRESETS


def save_custom_rule(rule_id, rule_name, config_dict):
    """カスタムルールテンプレートを保存"""
    if not IS_LOCAL or rule_id.startswith("preset_"):
        return
    with _local_db() as conn:
        c = conn.cursor()
        config_str = json.dumps(config_dict, ensure_ascii=False)
        c.execute('''
            INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
            VALUES (?, ?, 'custom', 1, ?, 0)
            ON CONFLICT(rule_id) DO UPDATE SET
                name=excluded.name,
                config_json=excluded.config_json,
                is_archived=0,
                version=version+1
        ''', (rule_id, rule_name, config_str))


def archive_rule(rule_id):
    """カスタムルールをアーカイブ"""
    if not IS_LOCAL or rule_id.startswith("preset_"):
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE rule_templates SET is_archived = 1 WHERE rule_id = ?", (rule_id,))


# ── グループ管理関数 ────────────────────────────────────────

def get_groups():
    """登録済みグループの一覧を取得 (メンバーリスト付き、G01/G02等の表示用ID追加)"""
    if not IS_LOCAL:
        return []
    try:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("SELECT group_id, group_name, default_rule_id FROM groups WHERE is_archived = 0 ORDER BY rowid ASC, group_name ASC")
            group_rows = c.fetchall()
            groups = []
            for idx, (g_id, g_name, r_id) in enumerate(group_rows):
                c.execute("SELECT member_id FROM group_memberships WHERE group_id = ?", (g_id,))
                members = [m[0] for m in c.fetchall()]
                groups.append({
                    "display_id": f"G{idx + 1:02d}",
                    "group_id": g_id,
                    "group_name": g_name,
                    "default_rule_id": r_id,
                    "members": members
                })
            return groups
    except Exception:
        return []


def save_group(group_id, group_name, default_rule_id, member_list):
    """グループの作成・更新"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO groups (group_id, group_name, default_rule_id, is_archived)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(group_id) DO UPDATE SET
                group_name=excluded.group_name,
                default_rule_id=excluded.default_rule_id,
                is_archived=0
        ''', (group_id, group_name, default_rule_id))
        
        c.execute("DELETE FROM group_memberships WHERE group_id = ?", (group_id,))
        for m in member_list:
            if m is not None:
                c.execute("INSERT INTO group_memberships (group_id, member_id) VALUES (?, ?)",
                          (group_id, m))


def delete_group(group_id):
    """グループの削除"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE groups SET is_archived = 1 WHERE group_id = ?", (group_id,))


# ── メンバーマスター管理関数 ──────────────────────────────

def get_all_members():
    """全メンバーを取得 (ID順)"""
    if not IS_LOCAL:
        from constants import MEMBERS
        return [{"member_id": i + 1, "member_name": m} for i, m in enumerate(MEMBERS)]
    try:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("SELECT member_id, member_name FROM members WHERE is_archived = 0 ORDER BY member_id ASC")
            rows = c.fetchall()
            if not rows:
                from constants import MEMBERS
                for m in MEMBERS:
                    c.execute("INSERT OR IGNORE INTO members (member_name, is_archived) VALUES (?, 0)", (m,))
                c.execute("SELECT member_id, member_name FROM members WHERE is_archived = 0 ORDER BY member_id ASC")
                rows = c.fetchall()
            return [{"member_id": r[0], "member_name": r[1]} for r in rows]
    except Exception:
        from constants import MEMBERS
        return [{"member_id": i + 1, "member_name": m} for i, m in enumerate(MEMBERS)]


def add_member(member_name):
    """新規メンバーを追加し、生成されたmember_idを返す"""
    if not IS_LOCAL or not member_name or not str(member_name).strip():
        return None
    name = str(member_name).strip()
    try:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO members (member_name, is_archived) VALUES (?, 0)", (name,))
            return c.lastrowid
    except Exception:
        return None


def delete_member(member_id):
    """メンバーの削除 (アーカイブ化)"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE members SET is_archived = 1 WHERE member_id = ?", (member_id,))



