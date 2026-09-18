import os
import sqlite3
import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import database2 as db


def _create_v2_test_local_db():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    db.init_config(is_local=True, sqlite_path=tmp.name)
    db.init_local_db()
    return tmp.name


def test_selective_push_and_backup_protection():
    """sync_target=1 の対局のみPushされ、sync_target=0 はPushされないこと"""
    db_path = _create_v2_test_local_db()

    mock_remote_conn = MagicMock()
    mock_remote_cursor = MagicMock()
    mock_remote_conn.cursor.return_value = mock_remote_cursor
    mock_remote_cursor.fetchall.return_value = []

    @contextmanager
    def mock_remote_db_cm():
        yield mock_remote_conn

    try:
        # 1. メンバー・グループ作成
        m1 = db.add_member("プレイヤーA")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")
        grp_id = db.add_group("テストグループ", "m_league")

        # 2. sync_target = 1 の対局（オンライン同期対象）
        g1 = {
            "group_id": grp_id, "rule_id": "m_league", "rule_name_snapshot": "Mリーグ",
            "rule_config_snapshot": {}, "played_at": "2026-09-07 10:00:00",
            "sync_target": 1
        }
        parts1 = [
            {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 40000, "rank": 1, "point": 50.0},
            {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 30000, "rank": 2, "point": 10.0},
            {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 20000, "rank": 3, "point": -10.0},
            {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 10000, "rank": 4, "point": -30.0},
        ]
        gid1 = db.save_game_record(g1, parts1, [])

        # 3. sync_target = 0 の対局（ローカル限定対局）
        g2 = {
            "group_id": grp_id, "rule_id": "m_league", "rule_name_snapshot": "Mリーグ",
            "rule_config_snapshot": {}, "played_at": "2026-09-07 11:00:00",
            "sync_target": 0
        }
        parts2 = list(parts1)
        gid2 = db.save_game_record(g2, parts2, [])

        # モック接続を適用して push_games_to_remote を実行
        with patch("database2.IS_LOCAL", True), \
             patch("database2.SQLITE_PATH", db_path), \
             patch("database2._remote_db", mock_remote_db_cm):

            pushed = db.push_games_to_remote()
            assert pushed == 1, f"Expected 1 pushed game, got {pushed}"

            # ローカルDBの同期フラグ確認
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT is_synced FROM games WHERE game_id = ?", (gid1,))
            assert c.fetchone()[0] == 1, "gid1 (sync_target=1) should be marked is_synced=1"

            c.execute("SELECT is_synced FROM games WHERE game_id = ?", (gid2,))
            assert c.fetchone()[0] == 0, "gid2 (sync_target=0) should remain is_synced=0"
            conn.close()

            # リモート側に gid1 のみが送信されたことを確認
            calls = mock_remote_cursor.execute.call_args_list
            inserted_gids = []
            for call in calls:
                sql = call[0][0]
                if "INSERT INTO games" in sql:
                    params = call[0][1]
                    inserted_gids.append(params[0])

            assert gid1 in inserted_gids, "gid1 should be sent to remote"
            assert gid2 not in inserted_gids, "gid2 (local only) must NOT be sent to remote"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_full_pull_restores_games():
    """リモートにあってローカルにない対局が全件Pullされること"""
    db_path = _create_v2_test_local_db()

    mock_remote_conn = MagicMock()
    mock_remote_cursor = MagicMock()
    mock_remote_conn.cursor.return_value = mock_remote_cursor

    remote_gid = db.generate_uuid7()
    remote_yid = db.generate_uuid7()
    # リモート対局
    mock_remote_cursor.fetchall.side_effect = [
        # 1. games 一覧
        [(remote_gid, "2026-09-07 12:00:00", "all", "Mリーグ", "{}", "detail")],
        # 2. participants
        [
            (1, "m1", "プレイヤーA", 35000, 1, 55.0, 1),
            (2, "m2", "プレイヤーB", 25000, 2, 5.0, 1),
            (3, "m3", "プレイヤーC", 22000, 3, -18.0, 1),
            (4, "m4", "プレイヤーD", 18000, 4, -42.0, 1),
        ],
        # 3. rounds
        [],
        # 4. yakuman_records
        [(remote_yid, None, "m1", "国士無双", "2026-09-07 12:30:00")]
    ]

    @contextmanager
    def mock_remote_db_cm():
        yield mock_remote_conn

    try:
        with patch("database2.IS_LOCAL", True), \
             patch("database2.SQLITE_PATH", db_path), \
             patch("database2._remote_db", mock_remote_db_cm):

            pulled = db.pull_games_from_remote()
            assert pulled == 1, f"Expected 1 pulled game, got {pulled}"

            # ローカルDBにリモート対局および役満記録が保存されたか検証
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM games WHERE game_id = ?", (remote_gid,))
            assert c.fetchone()[0] == 1
            c.execute("SELECT COUNT(*) FROM game_participants WHERE game_id = ?", (remote_gid,))
            assert c.fetchone()[0] == 4
            c.execute("SELECT yakuman_name FROM yakuman_records WHERE game_id = ?", (remote_gid,))
            row = c.fetchone()
            assert row is not None and row[0] == "国士無双"
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_yakuman_records_sync_push():
    """ローカルの役満記録が正しくリモートへPushされること"""
    db_path = _create_v2_test_local_db()

    mock_remote_conn = MagicMock()
    mock_remote_cursor = MagicMock()
    mock_remote_conn.cursor.return_value = mock_remote_cursor
    mock_remote_cursor.fetchall.return_value = []

    @contextmanager
    def mock_remote_db_cm():
        yield mock_remote_conn

    try:
        m1 = db.add_member("役満太郎")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")
        grp_id = db.add_group("テストグループ", "m_league")

        g1 = {
            "group_id": grp_id, "rule_id": "m_league", "rule_name_snapshot": "Mリーグ",
            "rule_config_snapshot": {}, "played_at": "2026-09-18 10:00:00",
            "sync_target": 1
        }
        parts1 = [
            {"seat": 1, "member_id": m1, "player_name_snapshot": "役満太郎", "final_score": 60000, "rank": 1, "point": 80.0},
            {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 25000, "rank": 2, "point": 5.0},
            {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 10000, "rank": 3, "point": -30.0},
            {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 5000, "rank": 4, "point": -55.0},
        ]
        gid = db.save_game_record(g1, parts1, [])

        # 役満レコードを手動追加
        yid = db.generate_uuid7()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO yakuman_records (id, game_id, round_id, member_id, yakuman_name)
            VALUES (?, ?, NULL, ?, ?)
        """, (yid, gid, m1, "大三元"))
        conn.commit()
        conn.close()

        with patch("database2.IS_LOCAL", True), \
             patch("database2.SQLITE_PATH", db_path), \
             patch("database2._remote_db", mock_remote_db_cm):

            pushed = db.push_games_to_remote([gid])
            assert pushed == 1

            # リモートへのSQL呼び出しを検証
            calls = mock_remote_cursor.execute.call_args_list
            yakuman_inserted = False
            for call in calls:
                sql = call[0][0]
                if "INSERT INTO yakuman_records" in sql:
                    params = call[0][1]
                    assert params[0] == yid
                    assert params[1] == gid
                    assert params[3] == m1
                    assert params[4] == "大三元"
                    yakuman_inserted = True

            assert yakuman_inserted, "yakuman_records should be pushed to remote"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

