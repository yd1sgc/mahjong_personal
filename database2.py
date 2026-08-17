import json
import os
import sqlite3
import psycopg2
import pandas as pd
import streamlit as st
from contextlib import contextmanager
from datetime import datetime

IS_LOCAL = st.secrets.get("local_mode", False)
SQLITE_PATH = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db" if IS_LOCAL else None


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


def save_game(date_str, scores, players, local=False, rule_id="m_league", group_id="all", rule_config=None):
    sorted_p = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    rule_json_str = json.dumps(rule_config, ensure_ascii=False) if rule_config else None
    if local:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("SELECT COALESCE(MAX(game_id), 0) + 1 FROM games")
            next_id = c.fetchone()[0]
            c.execute('''INSERT INTO games (game_id, date,
                p1_name, p1_score, p1_rank,
                p2_name, p2_score, p2_rank,
                p3_name, p3_score, p3_rank,
                p4_name, p4_score, p4_rank,
                is_synced, group_id, rule_id, applied_rule_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                next_id, date_str,
                sorted_p[0][0], sorted_p[0][1], 1,
                sorted_p[1][0], sorted_p[1][1], 2,
                sorted_p[2][0], sorted_p[2][1], 3,
                sorted_p[3][0], sorted_p[3][1], 4,
                0, group_id, rule_id, rule_json_str
            ))
        return next_id
    with _remote_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COALESCE(MAX(game_id), 0) + 1 FROM games")
        next_id = c.fetchone()[0]
        c.execute('''INSERT INTO games (game_id, date,
            p1_name, p1_score, p1_rank,
            p2_name, p2_score, p2_rank,
            p3_name, p3_score, p3_rank,
            p4_name, p4_score, p4_rank,
            group_id, rule_id, applied_rule_json
        ) VALUES (%s, %s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s)''', (
            next_id, date_str,
            sorted_p[0][0], sorted_p[0][1], 1,
            sorted_p[1][0], sorted_p[1][1], 2,
            sorted_p[2][0], sorted_p[2][1], 3,
            sorted_p[3][0], sorted_p[3][1], 4,
            group_id, rule_id, rule_json_str
        ))
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
            df = _fetch_df(conn, "SELECT * FROM games ORDER BY game_id DESC")
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
            return _fetch_df(conn, "SELECT * FROM games")
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
            c.execute("SELECT p1_name, p2_name, p3_name, p4_name FROM games WHERE game_id=?", (game_id,))
            row = c.fetchone()
            if row:
                for slot in range(1, 5):
                    name = row[slot - 1]
                    if name in scores_dict:
                        c.execute(
                            f"UPDATE games SET p{slot}_score=?, p{slot}_rank=? WHERE game_id=?",
                            (scores_dict[name], name_to_rank[name], game_id)
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

def get_rules():
    """登録済みルールの一覧をリストで取得"""
    default_fallback = [
        {"rule_id": "m_league", "rule_name": "Mリーグルール", "is_default": 1,
         "config": {"init_score": 25000, "return_score": 30000, "uma": [50, 10, -10, -30]}},
        {"rule_id": "standard_10_30", "rule_name": "一般10-30", "is_default": 0,
         "config": {"init_score": 25000, "return_score": 30000, "uma": [40, 10, -10, -20]}},
        {"rule_id": "gotto_5_10", "rule_name": "ゴットー (5-10)", "is_default": 0,
         "config": {"init_score": 25000, "return_score": 30000, "uma": [30, 5, -5, -10]}},
        {"rule_id": "no_uma_no_oka", "rule_name": "ノーウマ・オカなし", "is_default": 0,
         "config": {"init_score": 30000, "return_score": 30000, "uma": [0, 0, 0, 0]}},
    ]
    if not IS_LOCAL:
        return default_fallback

    try:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("SELECT rule_id, rule_name, is_default, config_json FROM rules ORDER BY is_default DESC, rule_name")
            rows = c.fetchall()
            if not rows:
                return default_fallback
            results = []
            for r in rows:
                try:
                    cfg = json.loads(r[3])
                except Exception:
                    cfg = {}
                results.append({
                    "rule_id": r[0],
                    "rule_name": r[1],
                    "is_default": r[2],
                    "config": cfg
                })
            return results
    except Exception:
        return default_fallback


def save_rule(rule_id, rule_name, config_dict, is_default=False):
    """ルールの作成・更新"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        if is_default:
            c.execute("UPDATE rules SET is_default = 0")
        config_str = json.dumps(config_dict, ensure_ascii=False)
        c.execute('''
            INSERT INTO rules (rule_id, rule_name, is_default, config_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                rule_name=excluded.rule_name,
                is_default=excluded.is_default,
                config_json=excluded.config_json
        ''', (rule_id, rule_name, 1 if is_default else 0, config_str))


def delete_rule(rule_id):
    """ルールの削除"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM rules WHERE rule_id = ?", (rule_id,))


def set_default_rule(rule_id):
    """デフォルトルールの変更"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE rules SET is_default = 0")
        c.execute("UPDATE rules SET is_default = 1 WHERE rule_id = ?", (rule_id,))


# ── グループ管理関数 ────────────────────────────────────────

def get_groups():
    """登録済みグループの一覧を取得 (メンバーリスト付き)"""
    if not IS_LOCAL:
        return []
    try:
        with _local_db() as conn:
            c = conn.cursor()
            c.execute("SELECT group_id, group_name, default_rule_id FROM member_groups ORDER BY group_name")
            group_rows = c.fetchall()
            groups = []
            for g_id, g_name, r_id in group_rows:
                c.execute("SELECT member_name FROM group_members WHERE group_id = ? ORDER BY member_name", (g_id,))
                members = [m[0] for m in c.fetchall()]
                groups.append({
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
            INSERT INTO member_groups (group_id, group_name, default_rule_id)
            VALUES (?, ?, ?)
            ON CONFLICT(group_id) DO UPDATE SET
                group_name=excluded.group_name,
                default_rule_id=excluded.default_rule_id
        ''', (group_id, group_name, default_rule_id))
        
        c.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
        for m in member_list:
            if m and str(m).strip():
                c.execute("INSERT INTO group_members (group_id, member_name) VALUES (?, ?)",
                          (group_id, str(m).strip()))


def delete_group(group_id):
    """グループの削除"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM member_groups WHERE group_id = ?", (group_id,))
        c.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))


