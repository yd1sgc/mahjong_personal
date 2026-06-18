import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mahjong_v3_complete.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 試合テーブル
    c.execute('''CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
        p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
        p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
        p4_name TEXT, p4_score INTEGER, p4_rank INTEGER
    )''')
    
    # 局テーブル（ここに必要な列をすべて定義）
    c.execute('''CREATE TABLE IF NOT EXISTS rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER,
        kyoku_name TEXT,
        winner TEXT,
        loser TEXT,
        score INTEGER,
        furo_names TEXT,
        riichi_names TEXT,
        riichi_count INTEGER
    )''')
    
    # tenpai_names 列が古いDBに存在しない場合は追加
    try:
        c.execute("ALTER TABLE rounds ADD COLUMN tenpai_names TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    # win_type 列が古いDBに存在しない場合は追加
    try:
        c.execute("ALTER TABLE rounds ADD COLUMN win_type TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    conn.commit()
    conn.close()

def save_game(date_str, scores, players):
    sorted_p = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(game_id), 0) + 1 FROM games")
    next_id = c.fetchone()[0]
    c.execute('''INSERT INTO games (game_id, date,
        p1_name, p1_score, p1_rank,
        p2_name, p2_score, p2_rank,
        p3_name, p3_score, p3_rank,
        p4_name, p4_score, p4_rank
    ) VALUES (?, ?, ?,?,?, ?,?,?, ?,?,?, ?,?,?)''', (
        next_id, date_str,
        sorted_p[0][0], sorted_p[0][1], 1,
        sorted_p[1][0], sorted_p[1][1], 2,
        sorted_p[2][0], sorted_p[2][1], 3,
        sorted_p[3][0], sorted_p[3][1], 4
    ))
    conn.commit()
    conn.close()
    return next_id

 # database.py の save_round 関数をこれに置き換え
def save_round(game_id, kyoku_name, winner, loser, score, furo, riichi, win_type="", tenpai=None):
    furo_str = ",".join(furo) if isinstance(furo, list) else ""
    tenpai_str = ",".join(tenpai) if isinstance(tenpai, list) else ""

    if isinstance(riichi, list):
        riichi_names_str = ",".join(riichi)
        riichi_cnt = len(riichi)
    else:
        riichi_names_str = ""
        riichi_cnt = int(riichi)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO rounds (
        game_id, kyoku_name, winner, loser, score,
        furo_names, riichi_names, riichi_count, tenpai_names, win_type
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
        game_id, kyoku_name, winner, loser, score,
        furo_str, riichi_names_str, riichi_cnt, tenpai_str, win_type
    ))
    conn.commit()
    conn.close()

def update_round_game_id(game_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE rounds SET game_id=? WHERE game_id=0", (game_id,))
    conn.commit()
    conn.close()

def get_games_data(year_filter=None):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM games ORDER BY game_id DESC", conn)
    conn.close()
    if df.empty: return df

    df['date'] = pd.to_datetime(df['date'], format='mixed')
    df = df.sort_values('game_id')
    df['match_no'] = range(1, len(df) + 1)
    
    if year_filter and year_filter != "全期間":
        df = df[df['date'].dt.year == int(year_filter)]
    
    return df.sort_values('game_id', ascending=False)

def get_rounds_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM rounds", conn)
    conn.close()
    return df

def apply_year_split():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE games SET date='2024-12-31' WHERE game_id<=69")
    c.execute("UPDATE games SET date='2025-01-01' WHERE game_id>=70")
    conn.commit()
    conn.close()

# --- 編集用追加機能 ---
def load_all_games():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM games", conn)
    conn.close()
    return df

def save_all_games(df):
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('games', conn, if_exists='replace', index=False)
    conn.close()

def load_all_rounds():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM rounds", conn)
    conn.close()
    return df

def save_all_rounds(df):
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('rounds', conn, if_exists='replace', index=False)
    conn.close()

def update_game_scores(game_id, scores_dict):
    sorted_p = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
    name_to_rank = {name: rank for rank, (name, _) in enumerate(sorted_p, 1)}
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()

def delete_game(game_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM games WHERE game_id=?", (game_id,))
    conn.execute("DELETE FROM rounds WHERE game_id=?", (game_id,))
    conn.commit()
    conn.close()

def import_games_from_df(df):
    conn = sqlite3.connect(DB_PATH)
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
        ) VALUES (?, ?, ?,?,?, ?,?,?, ?,?,?, ?,?,?)''', (
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