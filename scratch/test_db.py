import psycopg2

try:
    conn = psycopg2.connect(
        host='aws-1-ap-northeast-1.pooler.supabase.com',
        port=6543,
        user='postgres.llmhnkuljhwjpvcbawea',
        password='#$8,zLpMX2Z_cn&',
        dbname='postgres'
    )
    c = conn.cursor()
    c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    print("Tables:", [row[0] for row in c.fetchall()])
except Exception as e:
    print(f"Error: {e}")
