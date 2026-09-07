import psycopg2
import pandas as pd

try:
    conn = psycopg2.connect(
        host='aws-1-ap-northeast-1.pooler.supabase.com',
        port=6543,
        user='postgres.llmhnkuljhwjpvcbawea',
        password='#$8,zLpMX2Z_cn&',
        dbname='postgres'
    )
    
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = [r[0] for r in cur.fetchall()]
    print("Tables:", tables)
    
    if 'game_participants' in tables:
        print("\n--- V2 Schema Detected ---")
        games = pd.read_sql("SELECT game_id, played_at FROM games ORDER BY played_at DESC LIMIT 1", conn)
        print("Latest Game:")
        print(games)
        if not games.empty:
            gid = games.iloc[0]['game_id']
            print("\nParticipants:")
            print(pd.read_sql(f"SELECT seat, member_id, rank, final_score FROM game_participants WHERE game_id='{gid}' ORDER BY seat", conn))
            print("\nRounds:")
            print(pd.read_sql(f"SELECT round_id, round_index, kyoku_name, honba, result_type FROM rounds WHERE game_id='{gid}' ORDER BY round_index", conn))
    else:
        print("\n--- V1 Schema Detected ---")
        
except Exception as e:
    print(f"Error: {e}")
