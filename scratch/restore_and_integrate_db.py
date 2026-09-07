import os
import shutil
import sqlite3
import tomllib
import psycopg2
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

local_dir = r"C:\Users\segu1\OneDrive\mahjong_personal"
bak_path = os.path.join(local_dir, "mahjong_local.db.bak")
target_db_path = os.path.join(local_dir, "mahjong_local.db")
safe_permanent_bak = os.path.join(local_dir, "麻雀バックアップ", "mahjong_local_master_268games.db")
secrets_path = r"c:\Users\segu1\MyFiles\開発\repos\mahjong_personal\.streamlit\secrets.toml"

print("=== 1. バックアップファイルの恒久保存と作業DBの準備 ===")
# 念のため元の268件バックアップを麻雀バックアップフォルダに永久保存コピー
os.makedirs(os.path.dirname(safe_permanent_bak), exist_ok=True)
if not os.path.exists(safe_permanent_bak):
    shutil.copy2(bak_path, safe_permanent_bak)
    print(f">> 元バックアップを恒久保管しました: {safe_permanent_bak}")

# 作業対象の mahjong_local.db を bak から復元コピー
if os.path.exists(target_db_path):
    # 現在の19件版を一時退避
    shutil.copy2(target_db_path, target_db_path + ".old_19games")
shutil.copy2(bak_path, target_db_path)
print(f">> {target_db_path} に268件バックアップを復元配置しました。")

# ローカルDB接続
l_conn = sqlite3.connect(target_db_path)
lc = l_conn.cursor()

# リモートDB接続
with open(secrets_path, "rb") as f:
    sec = tomllib.load(f)["database"]
r_conn = psycopg2.connect(**sec)
rc = r_conn.cursor()

print("\n=== 2. オンラインDBからの本日8試合抽出と新IDマッピング ===")
# 本日の8試合（オンラインID順）
online_ids = [21, 22, 23, 24, 25, 26, 28, 29]
id_mapping = {}
start_new_id = 269

for i, old_id in enumerate(online_ids):
    new_id = start_new_id + i
    id_mapping[old_id] = new_id
    print(f"  オンライン ID {old_id}  ==>  ローカル新 ID {new_id}")

try:
    # ── A. games テーブルの移植 ──
    # ローカルの games カラム取得
    lc.execute("PRAGMA table_info(games);")
    l_games_cols = [c[1] for c in lc.fetchall()]
    print("\nローカル games カラム:", l_games_cols)

    # リモートの games カラム取得
    rc.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'games' ORDER BY ordinal_position;")
    r_games_cols = [c[0] for c in rc.fetchall()]

    # 共通カラム（game_id を除く）
    common_cols = [c for c in r_games_cols if c in l_games_cols and c != "game_id"]

    for old_id in online_ids:
        new_id = id_mapping[old_id]
        rc.execute(f"SELECT {','.join(common_cols)} FROM games WHERE game_id = %s;", (old_id,))
        row = rc.fetchone()
        
        insert_cols = ["game_id"] + common_cols
        if "is_synced" in l_games_cols:
            insert_cols.append("is_synced")
            vals = [new_id] + list(row) + [1]
        else:
            vals = [new_id] + list(row)
            
        placeholders = ",".join(["?"] * len(vals))
        lc.execute(f"INSERT INTO games ({','.join(insert_cols)}) VALUES ({placeholders});", vals)
    print(f">> games テーブルに本日分 {len(online_ids)} 件を挿入完了。")

    # ── B. game_participants テーブルの移植 ──
    lc.execute("PRAGMA table_info(game_participants);")
    l_p_cols = [c[1] for c in lc.fetchall()]
    rc.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'game_participants' ORDER BY ordinal_position;")
    r_p_cols = [c[0] for c in rc.fetchall()]
    p_common_cols = [c for c in r_p_cols if c in l_p_cols and c != "game_id"]

    total_p_inserted = 0
    for old_id in online_ids:
        new_id = id_mapping[old_id]
        rc.execute(f"SELECT {','.join(p_common_cols)} FROM game_participants WHERE game_id = %s ORDER BY seat;", (old_id,))
        p_rows = rc.fetchall()
        for prow in p_rows:
            insert_cols = ["game_id"] + p_common_cols
            vals = [new_id] + list(prow)
            placeholders = ",".join(["?"] * len(vals))
            lc.execute(f"INSERT INTO game_participants ({','.join(insert_cols)}) VALUES ({placeholders});", vals)
            total_p_inserted += 1
    print(f">> game_participants テーブルに {total_p_inserted} 件を挿入完了。")

    # ── C. rounds テーブルの移植 ──
    lc.execute("PRAGMA table_info(rounds);")
    l_r_cols = [c[1] for c in lc.fetchall()]
    rc.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'rounds' ORDER BY ordinal_position;")
    r_r_cols = [c[0] for c in rc.fetchall()]
    # id と game_id を除く共通カラム
    r_common_cols = [c for c in r_r_cols if c in l_r_cols and c not in ("id", "game_id")]

    total_r_inserted = 0
    for old_id in online_ids:
        new_id = id_mapping[old_id]
        rc.execute(f"SELECT {','.join(r_common_cols)} FROM rounds WHERE game_id = %s ORDER BY id ASC;", (old_id,))
        round_rows = rc.fetchall()
        for rrow in round_rows:
            insert_cols = ["game_id"] + r_common_cols
            row_vals = []
            for val in rrow:
                if isinstance(val, (dict, list)):
                    row_vals.append(json.dumps(val, ensure_ascii=False))
                else:
                    row_vals.append(val)
            vals = [new_id] + row_vals
            if "is_synced" in l_r_cols:
                insert_cols.append("is_synced")
                vals.append(1)
            placeholders = ",".join(["?"] * len(vals))
            lc.execute(f"INSERT INTO rounds ({','.join(insert_cols)}) VALUES ({placeholders});", vals)
            total_r_inserted += 1
    print(f">> rounds テーブルに {total_r_inserted} 件を挿入完了。")

    # ── コミット ──
    l_conn.commit()
    print("\n>> 全テーブルのコミットが正常に完了しました！")

    # ── D. 検証 ──
    print("\n=== 3. 統合後の完全性検証 ===")
    lc.execute("SELECT COUNT(*) FROM games;")
    total_games = lc.fetchone()[0]
    lc.execute("SELECT MIN(game_id), MAX(game_id) FROM games;")
    min_gid, max_gid = lc.fetchone()
    lc.execute("SELECT DISTINCT game_id FROM games ORDER BY game_id ASC;")
    all_gids = [r[0] for r in lc.fetchall()]

    expected_gids = list(range(1, 277))
    is_perfect_sequence = (all_gids == expected_gids)

    print(f"全対局件数: {total_games} 件 (想定: 276 件)")
    print(f"ID 範囲: [{min_gid} ～ {max_gid}] (想定: 1 ～ 276)")
    print(f"1 ～ 276 抜けなし完全連番一致: {is_perfect_sequence}")

    lc.execute("SELECT COUNT(*) FROM game_participants;")
    print(f"参加者総件数: {lc.fetchone()[0]} 件 (想定: 276 * 4 = 1104 件)")

    lc.execute("SELECT COUNT(*) FROM rounds;")
    print(f"局詳細総件数: {lc.fetchone()[0]} 件 (既存 229 + 本日 71 = 300 件)")

except Exception as e:
    l_conn.rollback()
    print(f"エラー発生のためロールバックしました: {e}")
    sys.exit(1)
finally:
    l_conn.close()
    r_conn.close()
