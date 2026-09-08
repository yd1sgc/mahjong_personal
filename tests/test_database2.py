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

