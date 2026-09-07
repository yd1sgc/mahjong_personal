import sys
import os
import streamlit as st

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
import database2 as db

try:
    remote_db_kwargs = dict(st.secrets["database"])
except KeyError:
    print("Error: secrets.toml に [database] セクションが見つかりません。")
    sys.exit(1)

db.init_config(
    is_local=False,
    remote_db_kwargs=remote_db_kwargs
)

def migrate_remote():
    print("オンラインDB（PostgreSQL）からレガシーカラムを削除します...")
    conn = None
    try:
        conn = db.get_connection()
        conn.autocommit = True
        c = conn.cursor()

        columns_to_drop = ["group_id", "rule_id"]

        for col in columns_to_drop:
            try:
                print(f"Dropping column {col} from games...")
                c.execute(f"ALTER TABLE games DROP COLUMN IF EXISTS {col};")
                print(f"  -> Successfully dropped {col}.")
            except Exception as e:
                print(f"  -> Error dropping {col}: {e}")

        print("\nオンラインDBのマイグレーションが正常に完了しました。")
    except Exception as e:
        print(f"接続または実行中にエラーが発生しました: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    migrate_remote()
