import os
import sqlite3
import tempfile
import database2 as db


def _create_v2_test_db():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    db.init_config(is_local=True, sqlite_path=tmp.name)
    db.init_local_db()
    return tmp.name


def test_v2_schema_initialization():
    """新V2スキーマの全テーブルおよびインデックスが正常に構築されること"""
    db_path = _create_v2_test_db()
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = set(r[0] for r in c.fetchall())

        expected_tables = {
            "members", "groups", "group_memberships", "rule_templates",
            "games", "game_participants", "rounds", "round_seats", "drafts"
        }
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"
        conn.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_uuid7_generation():
    """UUID v7 が正常に生成され、時系列ソート可能なフォーマットであること"""
    import time
    u1 = db.generate_uuid7()
    time.sleep(0.005)
    u2 = db.generate_uuid7()
    assert isinstance(u1, str) and len(u1) == 36
    assert isinstance(u2, str) and len(u2) == 36
    assert u1 != u2
    assert u1 < u2



def test_v2_save_game_and_cascade_delete():
    """不可分トランザクションでの対局保存と、カスケード削除の完全動作"""
    db_path = _create_v2_test_db()
    try:
        m1 = db.add_member("プレイヤーA")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")
        grp_id = db.add_group("テストグループ", "m_league")

        game_data = {
            "group_id": grp_id,
            "rule_id": "m_league",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {"basic": {"init_score": 25000}},
            "played_at": "2026-09-07 20:00:00",
            "created_by": "tester"
        }
        participants = [
            {"member_id": m1, "initial_seat": "east", "final_score": 35000, "rank": 1, "point": 55.0, "is_guest": 0},
            {"member_id": m2, "initial_seat": "south", "final_score": 25000, "rank": 2, "point": 5.0, "is_guest": 0},
            {"member_id": m3, "initial_seat": "west", "final_score": 22000, "rank": 3, "point": -18.0, "is_guest": 0},
            {"member_id": m4, "initial_seat": "north", "final_score": 18000, "rank": 4, "point": -42.0, "is_guest": 0},
        ]
        rounds_data = [
            {
                "round_number": 1,
                "honba": 0,
                "riichi_sticks": 0,
                "result_type": "ron",
                "winning_point": 3900,
                "seats": [
                    {"member_id": m1, "seat_wind": "east", "is_dealer": 1, "is_winner": 1, "is_loser": 0, "is_riichi": 1, "is_furo": 0, "is_tenpai": 1, "base_point": 3900, "kyotaku_point": 0, "penalty_point": 0},
                    {"member_id": m2, "seat_wind": "south", "is_dealer": 0, "is_winner": 0, "is_loser": 1, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "base_point": -3900, "kyotaku_point": 0, "penalty_point": 0},
                    {"member_id": m3, "seat_wind": "west", "is_dealer": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "base_point": 0, "kyotaku_point": 0, "penalty_point": 0},
                    {"member_id": m4, "seat_wind": "north", "is_dealer": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "base_point": 0, "kyotaku_point": 0, "penalty_point": 0},
                ]
            }
        ]

        saved_gid = db.save_game_record(game_data, participants, rounds_data)
        assert saved_gid is not None and len(saved_gid) == 36

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM game_participants WHERE game_id = ?", (saved_gid,))
        assert c.fetchone()[0] == 4
        c.execute("SELECT COUNT(*) FROM rounds WHERE game_id = ?", (saved_gid,))
        assert c.fetchone()[0] == 1
        c.execute("SELECT COUNT(*) FROM round_seats rs JOIN rounds r ON rs.round_id = r.round_id WHERE r.game_id = ?", (saved_gid,))
        assert c.fetchone()[0] == 4
        conn.close()

        db.delete_game(saved_gid)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM games WHERE game_id = ?", (saved_gid,))
        assert c.fetchone()[0] == 0
        c.execute("SELECT COUNT(*) FROM game_participants WHERE game_id = ?", (saved_gid,))
        assert c.fetchone()[0] == 0
        c.execute("SELECT COUNT(*) FROM rounds WHERE game_id = ?", (saved_gid,))
        assert c.fetchone()[0] == 0
        c.execute("SELECT COUNT(*) FROM round_seats")
        assert c.fetchone()[0] == 0
        conn.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_v2_transaction_rollback():
    """保存中に例外が発生した場合に一切の残骸データを残さずロールバックすること"""
    db_path = _create_v2_test_db()
    try:
        m1 = db.add_member("プレイヤーX")
        m2 = db.add_member("プレイヤーY")
        m3 = db.add_member("プレイヤーZ")
        m4 = db.add_member("プレイヤーW")
        grp_id = db.add_group("ロールバックグループ", "m_league")

        game_data = {
            "group_id": grp_id,
            "rule_id": "m_league",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {},
            "played_at": "2026-09-07 21:00:00",
            "created_by": "tester"
        }
        participants = [
            {"member_id": m1, "initial_seat": "east", "final_score": 30000, "rank": 1, "point": 50.0, "is_guest": 0},
            {"member_id": m2, "initial_seat": "south", "final_score": 25000, "rank": 2, "point": 10.0, "is_guest": 0},
            {"member_id": m3, "initial_seat": "west", "final_score": 25000, "rank": 3, "point": -10.0, "is_guest": 0},
            {"member_id": m4, "initial_seat": "north", "final_score": 20000, "rank": 4, "point": -30.0, "is_guest": 0},
        ]
        corrupt_rounds = [
            {
                "round_number": 1,
                "honba": 0,
                "riichi_sticks": 0,
                "result_type": "tsumo",
                "winning_point": 3000,
                "seats": [
                    {"member_id": None, "seat_wind": "east"}
                ]
            }
        ]

        try:
            db.save_game_record(game_data, participants, corrupt_rounds)
            assert False, "Should raise exception due to NOT NULL constraint"
        except Exception:
            pass

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM games")
        assert c.fetchone()[0] == 0
        c.execute("SELECT COUNT(*) FROM game_participants")
        assert c.fetchone()[0] == 0
        conn.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
