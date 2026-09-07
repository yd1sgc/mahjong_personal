import os
import sys

# src ディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import database2 as db
import calc

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_mahjong_v2_new.db')
assert os.path.exists(DB_PATH), f"DB not found: {DB_PATH}"
db.init_config(is_local=True, sqlite_path=DB_PATH)

def main():
    print("=== Testing Stats Regression on V2 Schema ===")
    
    # 1. 試合成績
    print("\n[1] Testing get_game_stats_summary...")
    df_game_stats = db.get_game_stats_summary()
    print(f"Total rows: {len(df_game_stats)}")
    assert not df_game_stats.empty, "df_game_stats should not be empty!"
    print("Columns:", list(df_game_stats.columns))
    print(df_game_stats.head(3))
    
    total_pt = df_game_stats["総合pt"].sum()
    print(f"Total PT across all players: {total_pt:.1f}")
    assert abs(total_pt) < 10.0, f"Total PT should be close to 0, got {total_pt}"

    # 2. リザルトデータ
    print("\n[2] Testing get_results_data...")
    df_results = db.get_results_data()
    print(f"Total participant records: {len(df_results)}")
    assert len(df_results) == 1104, f"Expected 1104 participant records, got {len(df_results)}"
    print("Columns:", list(df_results.columns))
    print(df_results.head(3))

    # 3. 局詳細集計
    print("\n[3] Testing get_round_stats_summary...")
    df_round_stats, n_round_games = db.get_round_stats_summary()
    print(f"Total players in round stats: {len(df_round_stats)}, n_round_games: {n_round_games}")
    assert not df_round_stats.empty, "df_round_stats should not be empty!"
    assert n_round_games > 0, "n_round_games should be > 0!"
    print("Columns:", list(df_round_stats.columns))
    print(df_round_stats.head(3))

    # 4. calc.analyze_stats インターフェース互換性
    print("\n[4] Testing calc.analyze_stats interface...")
    g_stats, r_stats, n_games = calc.analyze_stats()
    assert len(g_stats) == len(df_game_stats)
    assert len(r_stats) == len(df_round_stats)
    assert n_games == n_round_games

    print("\n>>> ALL STATS REGRESSION TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    main()
