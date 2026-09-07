import sys
import os
import re

# srcディレクトリへのパスを通す
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

try:
    import streamlit as st
    import database2 as db
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

def get_correct_round_index(kyoku_name):
    """
    局名（例: "東1局", "南3局 1本場"）から正しいround_indexを逆算する。
    東1局 -> 0, 東2局 -> 1, ..., 南1局 -> 4, 西1局 -> 8
    """
    if not kyoku_name:
        return None
        
    wind_map = {"東": 0, "南": 1, "西": 2, "北": 3}
    match = re.search(r'(東|南|西|北)[^\d1-4]*([1-4１-４])', kyoku_name)
    if match:
        wind = match.group(1)
        num_str = match.group(2)
        # 全角数字が混ざっていた場合を考慮して半角に変換
        num_str = num_str.translate(str.maketrans('１２３４', '1234'))
        num = int(num_str)
        return wind_map[wind] * 4 + (num - 1)
    return None

def main():
    try:
        remote_db_kwargs = dict(st.secrets["database"])
    except KeyError:
        print("Error: secrets.toml に [database] セクションが見つかりません。")
        sys.exit(1)

    db.init_config(is_local=False, remote_db_kwargs=remote_db_kwargs)
    
    print("オンラインDBに接続しています...")
    conn = None
    try:
        conn = db.get_connection()
        c = conn.cursor()
        
        # 全てのラウンド情報を取得
        c.execute("SELECT round_id, kyoku_name, round_index FROM rounds")
        rounds = c.fetchall()
        
        updates = []
        for r_id, kyoku_name, current_idx in rounds:
            correct_idx = get_correct_round_index(kyoku_name)
            if correct_idx is not None and correct_idx != current_idx:
                updates.append((correct_idx, r_id))
                
        if not updates:
            print("修正が必要なデータは見つかりませんでした。")
            return
            
        print(f"インデックスのズレを {len(updates)} 件検出しました。修正を実行します...")
        
        # 修正を一括適用
        c.executemany("UPDATE rounds SET round_index = %s WHERE round_id = %s", updates)
        conn.commit()
        
        print("正常にすべての修正が完了しました！")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
