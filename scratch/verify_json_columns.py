import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

db_path = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== 1. GAMES テーブルの applied_rule_json 確認 (本日追加分 ID 269～276) ===")
cur.execute("""
    SELECT game_id, date, rule_name_snapshot, 
           CASE WHEN applied_rule_json IS NULL THEN 'NULL'
                WHEN applied_rule_json = '' THEN 'EMPTY'
                ELSE 'OK (長さ ' || length(applied_rule_json) || ' 文字)' END,
           substr(applied_rule_json, 1, 80)
    FROM games 
    WHERE game_id >= 269 
    ORDER BY game_id ASC;
""")
for r in cur.fetchall():
    print(f"Game {r[0]} ({r[1]}): {r[3]} | 先頭: {r[4]}...")

print("\n=== 2. ROUNDS テーブルの multi_wins_json 確認 ===")
cur.execute("""
    SELECT game_id, kyoku_name, win_type, multi_wins_json 
    FROM rounds 
    WHERE game_id >= 269 AND multi_wins_json IS NOT NULL AND multi_wins_json != ''
    ORDER BY id ASC;
""")
rows = cur.fetchall()
print(f"本日追加分の multi_wins_json 保持局数: {len(rows)} 件")
for r in rows:
    print(f"  Game {r[0]} {r[1]} ({r[2]}): {r[3]}")

print("\n=== 3. RULE_TEMPLATES の config_json 確認 ===")
cur.execute("SELECT rule_id, name, length(config_json) FROM rule_templates;")
for r in cur.fetchall():
    print(f"  Rule: {r[0]} ({r[1]}): {r[2]} 文字")

print("\n=== 4. 全 276 試合の applied_rule_json 保持件数 ===")
cur.execute("SELECT COUNT(*) FROM games WHERE applied_rule_json IS NOT NULL AND applied_rule_json != '';")
cnt = cur.fetchone()[0]
print(f"applied_rule_json 保持試合数: {cnt} / 276 件")

conn.close()
