import sqlite3

v1_conn = sqlite3.connect(r'C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db')
v2_conn = sqlite3.connect(r'C:\Users\segu1\MyFiles\開発\repos\mahjong_personal\local_mahjong_v2.db')

v1_count = v1_conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
v2_count = v2_conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

print(f"V1 games: {v1_count}")
print(f"V2 games: {v2_count}")

v1_dates = v1_conn.execute("SELECT MAX(date) FROM games").fetchone()[0]
v2_dates = v2_conn.execute("SELECT MAX(played_at) FROM games").fetchone()[0]

print(f"V1 max date: {v1_dates}")
print(f"V2 max date: {v2_dates}")
