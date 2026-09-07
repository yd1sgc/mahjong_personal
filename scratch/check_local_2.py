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

def check_db_summary(db_path):
    print(f"\n==========================================")
    print(f"=== DB: {db_path} ===")
    print(f"==========================================")
    try:
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
            print("--- Table Counts ---")
            for t in tables:
                cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t}: {cnt} rows")
            
            print("\n--- Members (First 5) ---")
            print(pd.read_sql("SELECT * FROM members LIMIT 5", conn))
            
            print("\n--- Groups ---")
            print(pd.read_sql("SELECT * FROM groups", conn))
            
            print("\n--- Rule Templates ---")
            print(pd.read_sql("SELECT rule_id, name, kind, version, is_archived FROM rule_templates", conn))
            
            print("\n--- Latest Game ---")
            games = pd.read_sql("SELECT * FROM games ORDER BY played_at DESC LIMIT 1", conn)
            print(games)
            if not games.empty:
                gid = games.iloc[0]['game_id']
                print(f"\n--- Participants for Latest Game ({gid}) ---")
                print(pd.read_sql(f"SELECT seat, member_id, player_name_snapshot, rank, final_score, point FROM game_participants WHERE game_id='{gid}' ORDER BY seat", conn))
                
                print(f"\n--- Rounds for Latest Game ({gid}) ---")
                rounds = pd.read_sql(f"SELECT round_id, round_index, kyoku_name, honba, riichi_sticks, result_type FROM rounds WHERE game_id='{gid}' ORDER BY round_index", conn)
                print(rounds)
                if not rounds.empty:
                    rid = rounds.iloc[0]['round_id']
                    print(f"\n--- Round Seats for First Round ({rid}) ---")
                    print(pd.read_sql(f"SELECT * FROM round_seats WHERE round_id='{rid}' ORDER BY seat", conn))
    except Exception as e:
        print("Error:", e)

check_db_summary('local_mahjong_v2_new.db')

