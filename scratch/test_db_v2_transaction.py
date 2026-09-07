import sys
import os
import json
import sqlite3

# src へのパスを通す
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
import database2 as db

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_mahjong_v2_new.db')
assert os.path.exists(DB_PATH), f"DB not found: {DB_PATH}"

print(f"Testing database2 with {DB_PATH}...")
db.init_config(is_local=True, sqlite_path=DB_PATH)

# 1. メンバー取得テスト
members = db.get_all_members()
print(f"[PASS] get_all_members: {len(members)} rows")
assert len(members) >= 10, "Members count is too low"

# 2. グループ取得テスト
groups = db.get_all_groups()
print(f"[PASS] get_all_groups: {len(groups)} rows")
assert len(groups) >= 1, "Groups count is too low"

# 3. ルール取得テスト
rules = db.get_rule_templates()
print(f"[PASS] get_rule_templates: {len(rules)} rows")
assert len(rules) >= 5, "Rules count is too low"

# 4. 対局データ一覧取得テスト
games_df = db.get_games_data()
print(f"[PASS] get_games_data: {len(games_df)} rows")
assert len(games_df) == 276, f"Expected 276 games, got {len(games_df)}"

# 5. 不可分トランザクション保存テスト（正常系）
test_game_id = db.generate_uuid7()
m_ids = [members.iloc[i]["member_id"] for i in range(4)]
m_names = [members.iloc[i]["member_name"] for i in range(4)]

test_payload = {
    "game_id": test_game_id,
    "played_at": "2026-09-07 22:30:00",
    "group_id": groups.iloc[0]["group_id"],
    "rule_name_snapshot": "テストルール",
    "rule_config_snapshot": {"basic": {"init_score": 25000, "return_score": 30000}},
    "game_mode": "detail",
    "participants": [
        {"seat": 1, "member_id": m_ids[0], "player_name_snapshot": m_names[0], "final_score": 40000, "rank": 1, "point": 50.0, "was_group_member": 1},
        {"seat": 2, "member_id": m_ids[1], "player_name_snapshot": m_names[1], "final_score": 30000, "rank": 2, "point": 10.0, "was_group_member": 1},
        {"seat": 3, "member_id": m_ids[2], "player_name_snapshot": m_names[2], "final_score": 20000, "rank": 3, "point": -10.0, "was_group_member": 1},
        {"seat": 4, "member_id": m_ids[3], "player_name_snapshot": m_names[3], "final_score": 10000, "rank": 4, "point": -50.0, "was_group_member": 1},
    ],
    "rounds": [
        {
            "round_index": 0,
            "kyoku_name": "東1局",
            "honba": 0,
            "riichi_sticks": 0,
            "result_type": "ron",
            "seats": [
                {"seat": 1, "member_id": m_ids[0], "base_point": 8000, "honba_point": 0, "kyotaku_point": 0, "penalty_point": 0, "score_delta": 8000, "chip_delta": 0, "han": 4, "fu": 30, "is_winner": 1, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                {"seat": 2, "member_id": m_ids[1], "base_point": 0, "honba_point": 0, "kyotaku_point": 0, "penalty_point": 0, "score_delta": 0, "chip_delta": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                {"seat": 3, "member_id": m_ids[2], "base_point": 0, "honba_point": 0, "kyotaku_point": 0, "penalty_point": 0, "score_delta": 0, "chip_delta": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                {"seat": 4, "member_id": m_ids[3], "base_point": -8000, "honba_point": 0, "kyotaku_point": 0, "penalty_point": 0, "score_delta": -8000, "chip_delta": 0, "is_winner": 0, "is_loser": 1, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
            ]
        }
    ]
}

saved_gid = db.save_game_record(test_payload)
assert saved_gid == test_game_id, "Returned game_id does not match"
print(f"[PASS] save_game_record: {saved_gid}")

# 詳細取得検証
details = db.get_game_details(test_game_id)
assert len(details.get("participants", [])) == 4, "Participants count != 4"
assert len(details.get("rounds", [])) == 1, "Rounds count != 1"
assert len(details["rounds"][0].get("seats", [])) == 4, "Seats count != 4"
print(f"[PASS] get_game_details verified")

# 削除テスト
db.delete_game(test_game_id)
assert db.get_game_details(test_game_id) == {}, "Game not deleted"
print(f"[PASS] delete_game verified")

# 6. 不可分トランザクション ロールバックテスト（異常系）
bad_game_id = db.generate_uuid7()
bad_payload = {
    "game_id": bad_game_id,
    "played_at": "2026-09-07 22:35:00",
    "group_id": groups.iloc[0]["group_id"],
    "rule_name_snapshot": "エラーテスト",
    "rule_config_snapshot": {},
    "game_mode": "detail",
    "participants": [
        {"seat": 1, "member_id": m_ids[0], "player_name_snapshot": m_names[0], "final_score": 40000, "rank": 1, "point": 50.0},
        {"seat": 2, "member_id": m_ids[1], "player_name_snapshot": m_names[1], "final_score": 30000, "rank": 2, "point": 10.0},
        {"seat": 3, "member_id": m_ids[2], "player_name_snapshot": m_names[2], "final_score": 20000, "rank": 3, "point": -10.0},
        {"seat": 4, "member_id": m_ids[3], "player_name_snapshot": m_names[3], "final_score": 10000, "rank": 4, "point": -50.0},
    ],
    "rounds": [
        {
            "round_index": 0,
            "kyoku_name": "東1局",
            "result_type": "ron",
            # 意図的に seats で不正な型/キー欠落を発生させる
            "seats": [
                {"seat": "INVALID_SEAT_INT_TYPE_ERROR"}
            ]
        }
    ]
}

rollback_ok = False
try:
    db.save_game_record(bad_payload)
except Exception as e:
    rollback_ok = True
    print(f"[PASS] Exception correctly raised during bad save: {type(e).__name__}")

assert rollback_ok, "Exception was not raised for bad payload"

# ロールバック後に games テーブルに bad_game_id が残っていないことを検証
with db._local_db() as conn:
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM games WHERE game_id = ?", (bad_game_id,))
    assert c.fetchone()[0] == 0, "Transaction rollback failed: game header was saved"
    c.execute("SELECT COUNT(*) FROM game_participants WHERE game_id = ?", (bad_game_id,))
    assert c.fetchone()[0] == 0, "Transaction rollback failed: participants were saved"
    c.execute("SELECT COUNT(*) FROM rounds WHERE game_id = ?", (bad_game_id,))
    assert c.fetchone()[0] == 0, "Transaction rollback failed: rounds were saved"

print("[PASS] Rollback verification successful: zero orphan rows remain")

# 7. 下書き（ドラフト）保存・取得・削除テスト
test_draft = json.dumps({"test_key": "draft_value_123"})
db.save_draft(test_draft, "test_draft_id")
retrieved_draft = db.get_draft("test_draft_id")
assert retrieved_draft == test_draft, "Draft value mismatch"
db.delete_draft("test_draft_id")
assert db.get_draft("test_draft_id") is None, "Draft was not deleted"
print("[PASS] Draft lifecycle verified")

print("\nALL V2 DATABASE TESTS PASSED SUCCESSFULLY!")
