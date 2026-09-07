import sqlite3
import pandas as pd

print("=== local_mahjong_v2.db ===")
try:
    with sqlite3.connect('local_mahjong_v2.db') as conn:
        games = pd.read_sql("SELECT * FROM games ORDER BY played_at DESC LIMIT 1", conn)
        print("Game:")
        print(games[['game_id', 'played_at']])
        if not games.empty:
            gid = games.iloc[0]['game_id']
            print("Participants:")
            print(pd.read_sql(f"SELECT seat, member_id, rank, final_score FROM game_participants WHERE game_id='{gid}' ORDER BY seat", conn))
            print("Rounds:")
            print(pd.read_sql(f"SELECT round_index, kyoku_name, result_type FROM rounds WHERE game_id='{gid}' ORDER BY round_index", conn))
except Exception as e:
    print(e)

print("\n=== local_mahjong.db ===")
try:
    with sqlite3.connect('local_mahjong.db') as conn:
        games = pd.read_sql("SELECT * FROM games ORDER BY date DESC LIMIT 1", conn)
        print("Game:")
        print(games[['game_id', 'date', 'p1_name', 'p2_name', 'p3_name', 'p4_name']])
        if not games.empty:
            gid = games.iloc[0]['game_id']
            print("Rounds:")
            print(pd.read_sql(f"SELECT id, kyoku_name, win_type, winner FROM rounds WHERE game_id='{gid}' ORDER BY id", conn))
except Exception as e:
    print(e)
