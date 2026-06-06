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

    conn.commit()
    conn.close()

def save_game(date_str, scores, players):
    sorted_p = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO games (date, 
        p1_name, p1_score, p1_rank,
        p2_name, p2_score, p2_rank,
        p3_name, p3_score, p3_rank,
        p4_name, p4_score, p4_rank
    ) VALUES (?, ?,?,?, ?,?,?, ?,?,?, ?,?,?)''', (
        date_str,
        sorted_p[0][0], sorted_p[0][1], 1,
        sorted_p[1][0], sorted_p[1][1], 2,
        sorted_p[2][0], sorted_p[2][1], 3,
        sorted_p[3][0], sorted_p[3][1], 4
    ))
    gid = c.lastrowid
    conn.commit()
    conn.close()
    return gid

 # database.py の save_round 関数をこれに置き換え
def save_round(game_id, kyoku_name, winner, loser, score, furo, riichi):
    # furo と riichi はリストで渡ってくる想定
    furo_str = ",".join(furo) if isinstance(furo, list) else ""
    
    # ★ここを修正：riichiがリストなら名前を連結して保存する
    if isinstance(riichi, list):
        riichi_names_str = ",".join(riichi)
        riichi_cnt = len(riichi)
    else:
        # 以前のデータとの互換性用
        riichi_names_str = "" 
        riichi_cnt = int(riichi)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # riichi_names という新しい列にもデータを入れます
    c.execute("""INSERT INTO rounds (
        game_id, kyoku_name, winner, loser, score, furo_names, riichi_names, riichi_count
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
        game_id, kyoku_name, winner, loser, score, furo_str, riichi_names_str, riichi_cnt
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

    df['date'] = pd.to_datetime(df['date'])
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