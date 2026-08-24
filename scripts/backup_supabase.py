import os
import sqlite3
import pandas as pd
import psycopg2
import toml

def backup_supabase_to_sqlite():
    # 1. 接続情報の読み込み
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    if not os.path.exists(secrets_path):
        print("secrets.toml が見つかりません。")
        return
        
    with open(secrets_path, "r", encoding="utf-8") as f:
        secrets = toml.load(f)
        
    db_config = secrets.get("database", {})
    if not db_config:
        print("databaseの設定が見つかりません。")
        return

    # 2. Supabase(PostgreSQL) に接続
    print("Supabase に接続しています...")
    try:
        pg_conn = psycopg2.connect(**db_config)
    except Exception as e:
        print(f"Supabaseへの接続に失敗しました: {e}")
        return

    # 3. SQLiteバックアップDBの作成
    backup_db_path = r"C:\Users\segu1\OneDrive\mahjong_personal\supabase_backup_20260824.db"
    if os.path.exists(backup_db_path):
        os.remove(backup_db_path)
    sqlite_conn = sqlite3.connect(backup_db_path)

    # 4. publicスキーマのテーブル一覧を取得
    query_tables = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE';
    """
    
    tables_df = pd.read_sql_query(query_tables, pg_conn)
    tables = tables_df['table_name'].tolist()
    
    print(f"以下のテーブルをバックアップします: {tables}")

    # 5. 各テーブルのデータをpandas経由でSQLiteにコピー
    for table in tables:
        try:
            print(f"[{table}] テーブルをコピー中...")
            df = pd.read_sql_query(f"SELECT * FROM {table}", pg_conn)
            df.to_sql(table, sqlite_conn, if_exists="replace", index=False)
            print(f"  -> {len(df)} 件のレコードを保存しました。")
        except Exception as e:
            print(f"  -> {table} のバックアップ中にエラーが発生しました: {e}")

    # 6. クリーンアップ
    pg_conn.close()
    sqlite_conn.close()
    
    print(f"バックアップ完了: {backup_db_path}")

if __name__ == "__main__":
    backup_supabase_to_sqlite()
