import os
import sys
import shutil
import sqlite3
import json
import gc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

import database2 as db
import game_logic
from views.round_edit import _restore_game_state_from_db

def run_tests():
    print("=== 対局編集・安全性インターロック検証テスト開始 ===")
    real_db_path = os.path.join(BASE_DIR, "local_mahjong_v2_new.db")
    test_db_path = os.path.join(BASE_DIR, "test_interlock_temp.db")
    
    # 1. テスト用DBを一時複製
    shutil.copy2(real_db_path, test_db_path)
    db.init_config(is_local=True, sqlite_path=test_db_path)

    try:
        # --- テスト1: get_game_details で yakuman_records が取得できるか ---
        with db.get_local_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT y.game_id 
                FROM yakuman_records y 
                JOIN rounds r ON y.game_id = r.game_id 
                GROUP BY y.game_id 
                LIMIT 1
            """)
            row = c.fetchone()
            assert row is not None, "局記録を持つ役満レコードが存在しません"
            yakuman_game_id = row[0]

        details = db.get_game_details(yakuman_game_id)
        assert "yakuman_records" in details, "get_game_details に yakuman_records が含まれていません"
        assert len(details["yakuman_records"]) > 0, "yakuman_records の件数が 0 件です"
        y_name = details["yakuman_records"][0]["yakuman_name"]
        print(f"[PASS] テスト1: get_game_details yakuman_records 取得成功 (game_id: {yakuman_game_id}, 役満: {y_name})")

        # --- テスト2: 局修正保存シミュレーションで役満と恒等式が維持されるか ---
        game_state, players, p_mids, p_was_mems, rule_cfg = _restore_game_state_from_db(details)
        final_scores = dict(game_state.scores)

        payload = game_logic.build_v2_game_payload(
            game_state=game_state,
            players=players,
            scores=final_scores,
            group_id=details.get("group_id"),
            rule_id="standard",
            rule_config=rule_cfg,
            player_member_ids=p_mids,
            player_was_group_member=p_was_mems,
            date_str=str(details.get("played_at")),
            game_id=yakuman_game_id,
            yakuman_list=details.get("yakuman_records", [])
        )

        db.update_game_record_atomic(yakuman_game_id, payload)

        # 保存後の検証
        new_details = db.get_game_details(yakuman_game_id)
        assert len(new_details["yakuman_records"]) == len(details["yakuman_records"]), "update_game_record_atomic 後に役満レコードが消失しました"
        assert new_details["is_synced"] == 0, "局修正後に is_synced が 0 に更新されていません"

        # 恒等式検証
        with db.get_local_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT rs.round_id, rs.seat, rs.base_point, rs.honba_point, rs.kyotaku_point, rs.penalty_point, rs.score_delta
                FROM round_seats rs
                JOIN rounds r ON rs.round_id = r.round_id
                WHERE r.game_id = ?
            """, (yakuman_game_id,))
            for s in c.fetchall():
                delta_sum = (s[2] or 0) + (s[3] or 0) + (s[4] or 0) + (s[5] or 0)
                assert delta_sum == s[6], f"恒等式破綻: round_id={s[0]}, seat={s[1]}, delta_sum={delta_sum}, recorded={s[6]}"
        print(f"[PASS] テスト2: 局修正・不可分置換シミュレーション成功 (役満保持 & 恒等式完全成立 & is_synced=0)")

        # --- テスト3: push_games_to_remote インターロック検証 ---
        # テスト用の安全モック: 万が一インターロックを抜けても実リモート送信を阻止する
        orig_sb_request = db._sb_request
        def mock_sb_request(endpoint, method="GET", payload=None, params=None, extra_headers=None):
            raise RuntimeError(f"テスト中の意図しない実リモート送信呼び出しをブロックしました: {method} {endpoint}")
        db._sb_request = mock_sb_request

        try:
            # 3-A. 恒等式破綻の阻止
            with db.get_local_connection() as conn:
                c = conn.cursor()
                c.execute("UPDATE games SET sync_target = 1, is_synced = 0 WHERE game_id = ?", (yakuman_game_id,))
                # 意図的に score_delta を1点ズラして恒等式を破綻させる
                c.execute("""
                    UPDATE round_seats SET score_delta = score_delta + 100
                    WHERE round_id = (SELECT round_id FROM rounds WHERE game_id = ? LIMIT 1) AND seat = 1
                """, (yakuman_game_id,))
                conn.commit()

            interlock_triggered = False
            try:
                db.push_games_to_remote([yakuman_game_id])
            except Exception as e:
                if "座席恒等式が破綻しています" in str(e):
                    interlock_triggered = True
                else:
                    print(f"[UNEXPECTED EXCEPTION 3-A] {e}")
            assert interlock_triggered, "恒等式破綻データが push インターロックで阻止されませんでした"
            print("[PASS] テスト3-A: 恒等式破綻データの Push 阻止インターロック検証成功")

            # 3-B. ゼロサム破綻の阻止
            # 恒等式を修復し、持ち点合計を崩す
            with db.get_local_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE round_seats SET score_delta = score_delta - 100
                    WHERE round_id = (SELECT round_id FROM rounds WHERE game_id = ? LIMIT 1) AND seat = 1
                """, (yakuman_game_id,))
                c.execute("UPDATE game_participants SET final_score = final_score + 1000 WHERE game_id = ? AND seat = 1", (yakuman_game_id,))
                conn.commit()

            interlock_zero_sum_triggered = False
            try:
                db.push_games_to_remote([yakuman_game_id])
            except Exception as e:
                if "規定値" in str(e) and "一致しません" in str(e):
                    interlock_zero_sum_triggered = True
                else:
                    print(f"[UNEXPECTED EXCEPTION 3-B] {e}")
            assert interlock_zero_sum_triggered, "ゼロサム破綻データが push インターロックで阻止されませんでした"
            print("[PASS] テスト3-B: ゼロサム破綻データの Push 阻止インターロック検証成功")
        finally:
            db._sb_request = orig_sb_request

    finally:
        # ガベージコレクションを明示的に実行して SQLite 接続を解放
        gc.collect()
        db.init_config(is_local=True, sqlite_path=real_db_path)
        if os.path.exists(test_db_path):
            try:
                os.remove(test_db_path)
                print("[INFO] テスト用一時DBクリーンアップ完了")
            except Exception as e:
                print(f"[WARN] テスト用一時DB削除スキップ: {e}")

    print("=== 全テスト正常終了 ===")

if __name__ == "__main__":
    run_tests()
