import sqlite3
import pandas as pd

def check_db(db_path, v2=False):
    print(f"\n=== {db_path} ===")
    try:
        with sqlite3.connect(db_path) as conn:
            if v2:
                games = pd.read_sql("SELECT game_id, played_at FROM games ORDER BY played_at DESC LIMIT 2", conn)
                print("Games:")
                print(games)
                for gid in games['game_id']:
                    print(f"\nGame ID: {gid}")
                    print(pd.read_sql(f"SELECT seat, member_id, player_name_snapshot, rank, final_score FROM game_participants WHERE game_id='{gid}' ORDER BY seat", conn))
                    print(pd.read_sql(f"SELECT round_index, kyoku_name, result_type FROM rounds WHERE game_id='{gid}' ORDER BY round_index", conn))
            else:
                games = pd.read_sql("SELECT game_id, date, p1_name, p2_name, p3_name, p4_name FROM games ORDER BY date DESC LIMIT 2", conn)
                print("Games:")
                print(games)
                for gid in games['game_id']:
                    print(f"\nGame ID: {gid}")
                    try:
                        print(pd.read_sql(f"SELECT seat, display_name_snapshot, rank, score FROM game_participants WHERE game_id='{gid}' ORDER BY seat", conn))
                    except:
                        pass
                    print(pd.read_sql(f"SELECT id, kyoku_name, win_type, winner FROM rounds WHERE game_id='{gid}' ORDER BY id", conn))
    except Exception as e:
        print(e)

check_db('local_mahjong.db', False)
check_db('local_mahjong_v2.db', True)
