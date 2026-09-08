import os
import sqlite3
import pandas as pd
from datetime import datetime
import tempfile
from contextlib import contextmanager

import database2 as db


@contextmanager
def _temp_test_db():
    fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.init_config(is_local=True, sqlite_path=temp_path, remote_db_kwargs=None)
    db.init_local_db()
    try:
        yield temp_path
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_db_initialization():
    """初期化処理によって必要なテーブル群が作成されるかを検証"""
    with _temp_test_db() as temp_path:
        conn = sqlite3.connect(temp_path)
        c = conn.cursor()
        tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()

        assert "games" in tables
        assert "game_participants" in tables
        assert "members" in tables
        assert "groups" in tables
        assert "rule_templates" in tables
        assert "schema_meta" in tables


def test_save_and_get_games_compatibility():
    """保存処理(save_game)と取得処理(get_games_data)が、新スキーマ移行後も旧仕様と同じ結果を返すかを検証"""
    with _temp_test_db():
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scores = {
            "テストA": 40000,
            "テストB": 30000,
            "テストC": 20000,
            "テストD": 10000
        }
        players = ["テストA", "テストB", "テストC", "テストD"]

        rule_config = {
            "rule_name": "test_rule"
        }

        # ダミー対局データの保存
        game_id = db.save_game(
            date_str=date_str,
            scores=scores,
            players=players,
            local=True,
            rule_id="test_rule",
            group_id="test_group",
            rule_config=rule_config
        )

        assert game_id is not None

        # 対局データの取得
        df = db.get_games_data()

        assert not df.empty
        assert len(df) == 1

        row = df.iloc[0]

        assert row["p1_name"] == "テストA"
        assert row["p1_score"] == 40000
        assert row["p1_rank"] == 1

        assert row["p4_name"] == "テストD"
        assert row["p4_score"] == 10000
        assert row["p4_rank"] == 4

        assert row["rule_name_snapshot"] == "test_rule"
        assert row["group_id"] == "test_group"


def test_import_games_from_df_v2_compliance():
    """CSV取込でUUID解決、ウマオカpt算出、集計SQLとの結合が正常に行われるかを検証"""
    with _temp_test_db():
        # 1. 既存メンバーを1名だけ作成
        existing_m_id = db.add_member("既存プレイヤーA")

        # 2. CSV用DataFrameの作成 (1名は既存、3名は新規未登録)
        df_csv = pd.DataFrame([{
            "game_id": "",
            "date": "2026-09-09 12:00:00",
            "p1_name": "既存プレイヤーA", "p1_score": 45000,
            "p2_name": "新規プレイヤーB", "p2_score": 30000,
            "p3_name": "新規プレイヤーC", "p3_score": 15000,
            "p4_name": "新規プレイヤーD", "p4_score": 10000,
        }])

        rule_config = {
            "rule_name": "Mリーグルール",
            "basic": {"init_score": 25000, "return_score": 30000, "oka": 20.0, "uma": [50, 10, -10, -30]}
        }

        count = db.import_games_from_df(df_csv, rule_config=rule_config, auto_guest=False)
        assert count == 1

        # 3. DB内容の検証
        members = db.get_all_members()
        mem_dict = {m["member_name"]: m["member_id"] for m in members}
        assert "既存プレイヤーA" in mem_dict
        assert mem_dict["既存プレイヤーA"] == existing_m_id
        assert "新規プレイヤーB" in mem_dict
        assert "新規プレイヤーC" in mem_dict
        assert "新規プレイヤーD" in mem_dict

        # participants の member_id が正規の UUID であることを確認
        df_games = db.get_games_data()
        assert len(df_games) == 1
        gid = df_games.iloc[0]["game_id"]

        details = db.get_game_details(gid)
        parts = details["participants"]
        assert len(parts) == 4

        # 1位の pt は Mリーグ基準で 45000点 -> (45-30) + 30(uma) + 20(oka) = +65.0
        p1 = next(p for p in parts if p["player_name_snapshot"] == "既存プレイヤーA")
        assert p1["member_id"] == existing_m_id
        assert p1["rank"] == 1
        assert p1["point"] == 65.0

        # 成績集計SQL (get_game_stats_summary) で除外されず4名とも集計されることを検証
        df_stats = db.get_game_stats_summary()
        assert not df_stats.empty
        stats_names = df_stats["名前"].tolist()
        assert "既存プレイヤーA" in stats_names
        assert "新規プレイヤーB" in stats_names
        assert "新規プレイヤーC" in stats_names
        assert "新規プレイヤーD" in stats_names


def test_export_rounds_data_completeness():
    """load_all_rounds が座席別データを欠損なく完全なカラム構成で取得できるかを検証"""
    with _temp_test_db():
        m1 = db.add_member("プレイヤーA")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")

        payload = {
            "played_at": "2026-09-09 12:00:00",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {"basic": {"init_score": 25000}},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 33000, "rank": 1, "point": 13.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 27000, "rank": 2, "point": 7.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 25000, "rank": 3, "point": -15.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 15000, "rank": 4, "point": -35.0, "was_group_member": 1},
            ],
            "rounds": [
                {
                    "round_index": 0,
                    "kyoku_name": "東1局",
                    "honba": 0,
                    "riichi_sticks": 0,
                    "result_type": "ron",
                    "seats": [
                        {"seat": 1, "member_id": m1, "score_delta": 8000, "base_point": 8000, "is_winner": 1, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 1},
                        {"seat": 2, "member_id": m2, "score_delta": -8000, "base_point": -8000, "is_winner": 0, "is_loser": 1, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                        {"seat": 3, "member_id": m3, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                        {"seat": 4, "member_id": m4, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                    ]
                }
            ]
        }
        db.save_game_record(payload)

        df_exp = db.load_all_rounds()
        assert not df_exp.empty
        assert len(df_exp) == 4  # 1局につき4座席

        required_cols = [
            "round_id", "game_id", "round_index", "kyoku_name", "honba", "riichi_sticks", "result_type",
            "seat", "member_id", "member_name", "base_point", "score_delta", "is_winner", "is_loser"
        ]
        for col in required_cols:
            assert col in df_exp.columns


