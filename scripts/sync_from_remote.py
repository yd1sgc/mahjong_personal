import sys
import os
import sqlite3

# プロジェクトルートのsrcディレクトリをパスに追加
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

import database2 as db

# secrets.tomlからDB接続情報を読み込むためのダミー初期化処理
import streamlit as st
try:
    remote_db_kwargs = dict(st.secrets["database"])
except KeyError:
    print("Error: secrets.toml に [database] セクションが見つかりません。")
    sys.exit(1)

local_db_path = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db"

# database2をローカルモードとして初期化
db.init_config(
    is_local=True,
    sqlite_path=local_db_path,
    remote_db_kwargs=remote_db_kwargs
)

def sync_from_remote():
    print(f"リモートDBからローカルDB ({local_db_path}) への同期を開始します...")
    
    # リモート接続のテスト
    try:
        remote_conn = db.get_connection()
    except Exception as e:
        print(f"リモートDBへの接続に失敗しました: {e}")
        sys.exit(1)
        
    print("リモートDBへの接続に成功しました。")

    # ローカルDBファイルのバックアップ・削除
    if os.path.exists(local_db_path):
        backup_path = local_db_path + ".bak"
        print(f"既存のローカルDBをバックアップします: {backup_path}")
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.rename(local_db_path, backup_path)
    
    # ローカルDBの初期化
    print("ローカルDBを初期化します...")
    db.init_local_db()
    
    local_conn = db.get_local_connection()
    lc = local_conn.cursor()
    rc = remote_conn.cursor()

    try:
        # テーブルの一覧と移行処理
        tables = [
            "members",
            "groups",
            "group_memberships",
            "rule_templates",
            "games",
            "game_participants",
            "rounds"
        ]

        for table in tables:
            print(f"テーブル '{table}' のデータをコピー中...")
            
            # リモートから全件取得
            rc.execute(f"SELECT * FROM {table}")
            rows = rc.fetchall()
            
            if not rows:
                print(f"  > データなし")
                continue
                
            # カラム名の取得
            col_names = [desc[0] for desc in rc.description]
            placeholders = ",".join(["?"] * len(col_names))
            
            # JSONB型の文字列変換対応などが必要な場合があるが、psycopg2のデフォルトでdictまたはstrとして取れる
            # SQLiteに入れるためには、dict等は文字列化する
            processed_rows = []
            for row in rows:
                processed_row = []
                for val in row:
                    if isinstance(val, dict) or isinstance(val, list):
                        import json
                        processed_row.append(json.dumps(val, ensure_ascii=False))
                    else:
                        processed_row.append(val)
                processed_rows.append(tuple(processed_row))
                
            # ローカル側の一旦クリア (初期化で空のはずだが念のため)
            lc.execute(f"DELETE FROM {table}")
            
            # 挿入
            col_names_str = ",".join(col_names)
            query = f"INSERT INTO {table} ({col_names_str}) VALUES ({placeholders})"
            lc.executemany(query, processed_rows)
            
            print(f"  > {len(rows)} 件コピー完了")

        # drafts テーブルはリセットされているので空のままとする
        
        # is_synced フラグをすべて1にする
        lc.execute("UPDATE games SET is_synced = 1")
        lc.execute("UPDATE rounds SET is_synced = 1")

        local_conn.commit()
        print("\n同期が正常に完了しました。")

    except Exception as e:
        local_conn.rollback()
        print(f"\nエラーが発生しました: {e}")
        # リストア処理
        local_conn.close()
        local_conn = None
        if os.path.exists(local_db_path + ".bak"):
            if os.path.exists(local_db_path):
                os.remove(local_db_path)
            os.rename(local_db_path + ".bak", local_db_path)
            print("ローカルDBをバックアップから復元しました。")
    finally:
        if local_conn:
            local_conn.close()
        if remote_conn:
            remote_conn.close()

if __name__ == "__main__":
    sync_from_remote()
