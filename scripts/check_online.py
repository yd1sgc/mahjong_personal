import psycopg2

try:
    conn = psycopg2.connect(
        host='aws-1-ap-northeast-1.pooler.supabase.com',
        port=5432,
        user='postgres.llmhnkuljhwjpvcbawea',
        password='#$8,zLpMX2Z_cn&',
        dbname='postgres'
    )
    c = conn.cursor()
    
    # gamesテーブルのカラムを確認
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='games'")
    print('--- games columns ---')
    print([row[0] for row in c.fetchall()])
    
    # 2026-08-15 付近のゲームを抽出
    c.execute("SELECT * FROM games WHERE date >= '2026-08-08' AND date <= '2026-08-16'")
    games = c.fetchall()
    
    # カラム名を取得
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='games'")
    cols = [row[0] for row in c.fetchall()]
    
    print('\n--- games ---')
    for g in games:
        g_dict = dict(zip(cols, g))
        print(f"GameID: {g_dict.get('game_id')}, Date: {g_dict.get('date')}")
        # p1_name等があれば表示
        for k in ['p1_name', 'p2_name', 'p3_name', 'p4_name']:
            if k in g_dict:
                print(f"  {k}: {g_dict[k]}")
                
        # このゲームのラウンドを確認
        c.execute("SELECT * FROM rounds WHERE game_id=%s ORDER BY id", (g_dict.get('game_id'),))
        rounds = c.fetchall()
        c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='rounds'")
        r_cols = [row[0] for row in c.fetchall()]
        
        for r in rounds:
            r_dict = dict(zip(r_cols, r))
            print(f"  Round: {r_dict.get('kyoku_name')} Winner: {r_dict.get('winner')} Loser: {r_dict.get('loser')} Score: {r_dict.get('score')} Type: {r_dict.get('win_type')}")

except Exception as e:
    print(f"Error: {e}")
