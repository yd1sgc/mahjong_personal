import os
import psycopg2
import toml

def apply_supabase_schema():
    # 接続情報の読み込み
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    with open(secrets_path, "r", encoding="utf-8") as f:
        db_config = toml.load(f)["database"]

    sql_path = os.path.join("migrations", "supabase_migration_v1.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    print("Supabase に接続し、マイグレーションを実行します...")
    conn = psycopg2.connect(**db_config)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print(" Supabase のスキーマ移行（supabase_migration_v1.sql）が正常に完了しました。")
    except Exception as e:
        conn.rollback()
        print(f" マイグレーション実行中にエラーが発生しました:\n{e}")
    finally:
        conn.close()

if __name__ == "__main__":
    apply_supabase_schema()
