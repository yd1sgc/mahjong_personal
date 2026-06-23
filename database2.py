import os
import sqlite3
import psycopg2
import pandas as pd
import streamlit as st

IS_LOCAL = st.secrets.get("local_mode", False)
SQLITE_PATH = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db" if IS_LOCAL else None


def get_local_connection():
    return sqlite3.connect(SQLITE_PATH)


def get_local_unsynced_games():
    if not IS_LOCAL:
        return pd.DataFrame()
    try:
        if not os.path.exists(SQLITE_PATH):
            return pd.DataFrame()
        conn = get_local_connection()
        df = _fetch_df(conn, "SELECT * FROM games WHERE is_synced = 0 ORDER BY game_id DESC")
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def init_local_db():
    if not IS_LOCAL:
        return
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    conn = get_local_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY,
        date TEXT,
        p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
        p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
        p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
        p4_name TEXT, p4_score INTEGER, p4_rank INTEGER,
        is_synced INTEGER DEFAULT 0
    )''')
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
    conn.commit()
    conn.close()


def check_connectivity():
    try:
        conn = get_connection()
        conn.close()
        st.session_state["online"] = True
        return True
    except Exception:
        st.session_state["online"] = False
        return False


def save_game_local(date_str, scores, players):
    sorted_p = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    conn = get_local_connection()
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(game_id), 0) + 1 FROM games")
    next_id = c.fetchone()[0]
    c.execute('''INSERT INTO games (game_id, date,
        p1_name, p1_score, p1_rank,
        p2_name, p2_score, p2_rank,
        p3_name, p3_score, p3_rank,
        p4_name, p4_score, p4_rank,
        is_synced
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        next_id, date_str,
        sorted_p[0][0], sorted_p[0][1], 1,
        sorted_p[1][0], sorted_p[1][1], 2,
        sorted_p[2][0], sorted_p[2][1], 3,
        sorted_p[3][0], sorted_p[3][1], 4,
        0
    ))
    conn.commit()
    conn.close()
    return next_id


def save_round_local(game_id, kyoku_name, winner, loser, score, furo, riichi, win_type="", tenpai=None):
    furo_str = ",".join(furo) if isinstance(furo, list) else ""
    tenpai_str = ",".join(tenpai) if isinstance(tenpai, list) else ""
    if isinstance(riichi, list):
        riichi_names_str = ",".join(riichi)
        riichi_cnt = len(riichi)
    else:
        riichi_names_str = ""
        riichi_cnt = int(riichi)
    conn = get_local_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO rounds (
        game_id, kyoku_name, winner, loser, score,
        furo_names, riichi_names, riichi_count, tenpai_names, win_type, is_synced
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
        game_id, kyoku_name, winner, loser, score,
        furo_str, riichi_names_str, riichi_cnt, tenpai_str, win_type, 0
    ))
    conn.commit()
    conn.close()


def get_pending_count():
    if not IS_LOCAL:
        return 0
    conn = get_local_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM games WHERE is_synced = 0")
    count = c.fetchone()[0]
    conn.close()
    return count


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


def get_connection():
    try:
        db = st.secrets["database"]
    except Exception:
        return psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    return psycopg2.connect(
        host=db["host"],
        port=int(db["port"]),
        user=db["user"],
        password=db["password"],
        dbname=db["dbname"]
    )


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


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY,
        date TEXT,
        p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
        p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
        p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
        p4_name TEXT, p4_score INTEGER, p4_rank INTEGER
    )''')

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

    conn.commit()
    conn.close()


def save_game(date_str, scores, players):
    sorted_p = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(game_id), 0) + 1 FROM games")
    next_id = c.fetchone()[0]
    c.execute('''INSERT INTO games (game_id, date,
        p1_name, p1_score, p1_rank,
        p2_name, p2_score, p2_rank,
        p3_name, p3_score, p3_rank,
        p4_name, p4_score, p4_rank
    ) VALUES (%s, %s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s)''', (
        next_id, date_str,
        sorted_p[0][0], sorted_p[0][1], 1,
        sorted_p[1][0], sorted_p[1][1], 2,
        sorted_p[2][0], sorted_p[2][1], 3,
        sorted_p[3][0], sorted_p[3][1], 4
    ))
    conn.commit()
    conn.close()
    return next_id


def save_round(game_id, kyoku_name, winner, loser, score, furo, riichi, win_type="", tenpai=None):
    furo_str = ",".join(furo) if isinstance(furo, list) else ""
    tenpai_str = ",".join(tenpai) if isinstance(tenpai, list) else ""

    if isinstance(riichi, list):
        riichi_names_str = ",".join(riichi)
        riichi_cnt = len(riichi)
    else:
        riichi_names_str = ""
        riichi_cnt = int(riichi)

    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO rounds (
        game_id, kyoku_name, winner, loser, score,
        furo_names, riichi_names, riichi_count, tenpai_names, win_type
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", (
        game_id, kyoku_name, winner, loser, score,
        furo_str, riichi_names_str, riichi_cnt, tenpai_str, win_type
    ))
    conn.commit()
    conn.close()


@st.cache_data(ttl=300)
def get_games_data(year_filter=None):
    conn = get_connection()
    df = _fetch_df(conn, "SELECT * FROM games ORDER BY game_id DESC")
    conn.close()
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
    conn = get_connection()
    df = _fetch_df(conn, "SELECT * FROM rounds")
    conn.close()
    return df


def load_all_games():
    conn = get_connection()
    df = _fetch_df(conn, "SELECT * FROM games")
    conn.close()
    return df


def save_all_games(df):
    conn = get_connection()
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
    conn.commit()
    conn.close()


def load_all_rounds():
    conn = get_connection()
    df = _fetch_df(conn, "SELECT * FROM rounds")
    conn.close()
    return df


def save_all_rounds(df):
    conn = get_connection()
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
    conn.commit()
    conn.close()


def update_game_scores(game_id, scores_dict):
    sorted_p = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
    name_to_rank = {name: rank for rank, (name, _) in enumerate(sorted_p, 1)}
    conn = get_connection()
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
    conn.commit()
    conn.close()


def delete_game(game_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM games WHERE game_id=%s", (game_id,))
    c.execute("DELETE FROM rounds WHERE game_id=%s", (game_id,))
    conn.commit()
    conn.close()


def import_games_from_df(df):
    conn = get_connection()
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
    conn.commit()
    conn.close()
    return count
