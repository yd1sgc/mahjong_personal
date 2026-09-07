import sqlite3
import shutil
import os
import sys

# 既存の app.py を経由せずともパスがわかるように固定、または引数
DB_PATH = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db"
BACKUP_PATH = DB_PATH + ".bak"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        sys.exit(1)

    print(f"Backing up database to {BACKUP_PATH}...")
    shutil.copy2(DB_PATH, BACKUP_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        c.execute("PRAGMA foreign_keys = OFF;")
        
        # 移行先テーブルの作成
        c.execute('''CREATE TABLE IF NOT EXISTS games_new (
            game_id INTEGER PRIMARY KEY,
            date TEXT,
            is_synced INTEGER DEFAULT 0,
            selected_group_id TEXT,
            rule_name_snapshot TEXT,
            rule_schema_version INTEGER DEFAULT 1,
            applied_rule_json TEXT
        )''')

        # 既存のカラム一覧を取得
        c.execute("PRAGMA table_info(games)")
        existing_columns = {row[1] for row in c.fetchall()}

        # 安全なデータ移行クエリの構築
        cols_to_copy = ["game_id", "date", "is_synced"]
        if "selected_group_id" in existing_columns:
            cols_to_copy.append("selected_group_id")
        if "rule_name_snapshot" in existing_columns:
            cols_to_copy.append("rule_name_snapshot")
        if "rule_schema_version" in existing_columns:
            cols_to_copy.append("rule_schema_version")
        if "applied_rule_json" in existing_columns:
            cols_to_copy.append("applied_rule_json")

        cols_str = ", ".join(cols_to_copy)
        
        print(f"Copying data for columns: {cols_str}")
        c.execute(f"INSERT INTO games_new ({cols_str}) SELECT {cols_str} FROM games")

        # 入れ替え
        print("Dropping old games table and renaming...")
        c.execute("DROP TABLE games")
        c.execute("ALTER TABLE games_new RENAME TO games")

        conn.commit()
        print("Migration completed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        print("Restoring from backup...")
        conn.close()
        shutil.copy2(BACKUP_PATH, DB_PATH)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
