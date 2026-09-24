import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

def main():
    print("==================================================")
    print(" オンラインDB (Supabase) vs ローカルDB (SQLite) 突合調査")
    print("==================================================")

    # 1. 接続情報の読み込み
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        with open('.streamlit/secrets.toml', 'rb') as f:
            secrets = tomllib.load(f)
        db_conf = secrets['database']
    except Exception as e:
        print(f"ERROR: secrets.toml の読み込みに失敗しました: {e}")
        return

    # 2. オンラインDB 接続
    try:
        r_conn = psycopg2.connect(
            host=db_conf['host'],
            port=db_conf.get('port', 5432),
            dbname=db_conf['dbname'],
            user=db_conf['user'],
            password=db_conf['password'],
            sslmode='require'
        )
        rc = r_conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"ERROR: オンラインDBへの接続に失敗しました: {e}")
        return

    # 3. ローカルDB 接続
    try:
        l_conn = sqlite3.connect('local_mahjong_v2_new.db')
        l_conn.row_factory = sqlite3.Row
        lc = l_conn.cursor()
    except Exception as e:
        print(f"ERROR: ローカルDBへの接続に失敗しました: {e}")
        r_conn.close()
        return

    print("\n--- [1] games テーブル総レコード数 ---")
    rc.execute("SELECT COUNT(*) AS cnt FROM games;")
    r_total = rc.fetchone()['cnt']
    lc.execute("SELECT COUNT(*) AS cnt FROM games;")
    l_total = lc.fetchone()['cnt']
    print(f"  オンライン: {r_total} 件")
    print(f"  ローカル  : {l_total} 件")

    print("\n--- [2] games.rule_name_snapshot の内訳比較 ---")
    rc.execute("SELECT rule_name_snapshot, COUNT(*) AS cnt FROM games GROUP BY rule_name_snapshot ORDER BY cnt DESC;")
    r_rules = {r['rule_name_snapshot']: r['cnt'] for r in rc.fetchall()}
    lc.execute("SELECT rule_name_snapshot, COUNT(*) AS cnt FROM games GROUP BY rule_name_snapshot ORDER BY cnt DESC;")
    l_rules = {r['rule_name_snapshot']: r['cnt'] for r in lc.fetchall()}

    all_keys = sorted(set(r_rules.keys()) | set(l_rules.keys()))
    print(f"{'ルールスナップショット名':<30} | {'オンライン':<10} | {'ローカル':<10}")
    print("-" * 56)
    for k in all_keys:
        r_cnt = r_rules.get(k, 0)
        l_cnt = l_rules.get(k, 0)
        print(f"{str(k):<30} | {r_cnt:<10} | {l_cnt:<10}")

    print("\n--- [3] 最新5対局の突合 (played_at 降順) ---")
    rc.execute("SELECT game_id, played_at, rule_name_snapshot FROM games ORDER BY played_at DESC LIMIT 5;")
    r_recent = rc.fetchall()
    lc.execute("SELECT game_id, played_at, rule_name_snapshot FROM games ORDER BY played_at DESC LIMIT 5;")
    l_recent = lc.fetchall()

    print("【オンライン最新5件】")
    for r in r_recent:
        print(f"  ID: {r['game_id']} | 日時: {r['played_at']} | ルール: {r['rule_name_snapshot']}")

    print("【ローカル最新5件】")
    for r in l_recent:
        print(f"  ID: {r['game_id']} | 日時: {r['played_at']} | ルール: {r['rule_name_snapshot']}")

    print("\n--- [4] rule_templates の比較 ---")
    rc.execute("SELECT rule_id, name, kind, is_archived FROM rule_templates ORDER BY rule_id;")
    r_tmpl = rc.fetchall()
    lc.execute("SELECT rule_id, name, kind, is_archived FROM rule_templates ORDER BY rule_id;")
    l_tmpl = lc.fetchall()
    print(f"  オンライン ルール数: {len(r_tmpl)}")
    print(f"  ローカル   ルール数: {len(l_tmpl)}")
    for rt in r_tmpl:
        print(f"  (オンライン) ID: {rt['rule_id']} | 名前: {rt['name']} | 種別: {rt['kind']} | アーカイブ: {rt['is_archived']}")

    r_conn.close()
    l_conn.close()
    print("\n==================================================")
    print(" 調査完了")
    print("==================================================")

if __name__ == '__main__':
    main()
