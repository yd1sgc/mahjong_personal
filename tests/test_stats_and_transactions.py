import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime

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


def test_save_game_record_transaction_and_draft_deletion():
    """対局確定保存時に全テーブルへ整合して保存され、ドラフトが確実に消去されること"""
    with _temp_test_db() as temp_path:
        # メンバーとグループを作成
        m1 = db.add_member("プレイヤーA")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")
        grp_id = db.add_group("テストグループ", "m_league")

        # 対局中を模してドラフトを保存
        db.save_draft({"game_active": True, "round_idx": 1})
        draft_state, _ = db.load_draft()
        assert draft_state is not None
        assert draft_state.get("game_active") is True

        # save_game_record のペイロード構築
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "played_at": date_str,
            "group_id": grp_id,
            "rule_id": "m_league",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {"basic": {"init_score": 25000}},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 40000, "rank": 1, "point": 50.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 30000, "rank": 2, "point": 10.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 20000, "rank": 3, "point": -10.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 10000, "rank": 4, "point": -50.0, "was_group_member": 1},
            ],
            "rounds": [
                {
                    "round_index": 0,
                    "kyoku_name": "東1局",
                    "honba": 0,
                    "riichi_sticks": 0,
                    "result_type": "ron",
                    "seats": [
                        {"seat": 1, "member_id": m1, "score_delta": 8000, "base_point": 8000, "is_winner": 1, "is_loser": 0, "is_riichi": 1, "is_furo": 0, "is_tenpai": 1, "han": 4, "fu": 30},
                        {"seat": 2, "member_id": m2, "score_delta": -8000, "base_point": -8000, "is_winner": 0, "is_loser": 1, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 3, "member_id": m3, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 4, "member_id": m4, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 1, "is_tenpai": 0, "han": 0, "fu": 0},
                    ]
                }
            ]
        }

        game_id = db.save_game_record(payload)
        assert game_id is not None

        # 確定後にドラフトを削除（実アプリと同じシーケンス）
        db.delete_draft()
        post_draft, _ = db.load_draft()
        assert post_draft is None

        # 各テーブルに保存されていることを確認
        conn = sqlite3.connect(temp_path)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM games WHERE game_id = ?", (game_id,))
        assert c.fetchone()[0] == 1

        c.execute("SELECT count(*) FROM game_participants WHERE game_id = ?", (game_id,))
        assert c.fetchone()[0] == 4

        c.execute("SELECT count(*) FROM rounds WHERE game_id = ?", (game_id,))
        assert c.fetchone()[0] == 1

        c.execute("SELECT count(*) FROM round_seats WHERE member_id = ?", (m1,))
        assert c.fetchone()[0] == 1
        conn.close()


def test_game_and_round_stats_summary_accuracy():
    """半荘成績および局スタッツの集計SQLが正確な数値を返すこと"""
    with _temp_test_db():
        m1 = db.add_member("集計A")
        m2 = db.add_member("集計B")
        m3 = db.add_member("集計C")
        m4 = db.add_member("集計D")
        grp_id = db.add_group("集計グループ", "m_league")

        # 1戦目: m1が1位(+50.0), m2が2位(+10.0), m3が3位(-10.0), m4が4位(-50.0)
        p1 = {
            "played_at": "2026-09-01 10:00:00",
            "group_id": grp_id,
            "rule_id": "m_league",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "集計A", "final_score": 40000, "rank": 1, "point": 50.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "集計B", "final_score": 30000, "rank": 2, "point": 10.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "集計C", "final_score": 20000, "rank": 3, "point": -10.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "集計D", "final_score": 10000, "rank": 4, "point": -50.0, "was_group_member": 1},
            ],
            "rounds": [
                {
                    "round_index": 0,
                    "kyoku_name": "東1局",
                    "honba": 0,
                    "riichi_sticks": 0,
                    "result_type": "ron",
                    "seats": [
                        {"seat": 1, "member_id": m1, "score_delta": 8000, "base_point": 8000, "is_winner": 1, "is_loser": 0, "is_riichi": 1, "is_furo": 0, "is_tenpai": 1, "han": 4, "fu": 30},
                        {"seat": 2, "member_id": m2, "score_delta": -8000, "base_point": -8000, "is_winner": 0, "is_loser": 1, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 3, "member_id": m3, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 4, "member_id": m4, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 1, "is_tenpai": 0, "han": 0, "fu": 0},
                    ]
                }
            ]
        }
        db.save_game_record(p1)

        # 2戦目: m1が2位(+10.0), m2が1位(+50.0), m3が4位(-50.0), m4が3位(-10.0)
        p2 = {
            "played_at": "2026-09-01 12:00:00",
            "group_id": grp_id,
            "rule_id": "m_league",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "集計A", "final_score": 30000, "rank": 2, "point": 10.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "集計B", "final_score": 40000, "rank": 1, "point": 50.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "集計C", "final_score": 10000, "rank": 4, "point": -50.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "集計D", "final_score": 20000, "rank": 3, "point": -10.0, "was_group_member": 1},
            ],
            "rounds": [
                {
                    "round_index": 0,
                    "kyoku_name": "東1局",
                    "honba": 0,
                    "riichi_sticks": 0,
                    "result_type": "ron",
                    "seats": [
                        {"seat": 1, "member_id": m1, "score_delta": -3900, "base_point": -3900, "is_winner": 0, "is_loser": 1, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 2, "member_id": m2, "score_delta": 3900, "base_point": 3900, "is_winner": 1, "is_loser": 0, "is_riichi": 0, "is_furo": 1, "is_tenpai": 1, "han": 2, "fu": 30},
                        {"seat": 3, "member_id": m3, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 4, "member_id": m4, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                    ]
                }
            ]
        }
        db.save_game_record(p2)

        # ── 1. 半荘サマリー集計 (get_game_stats_summary) の検証
        df_game = db.get_game_stats_summary(group_id=grp_id)
        assert not df_game.empty
        assert len(df_game) == 4

        row_a = df_game[df_game["名前"] == "集計A"].iloc[0]
        assert row_a["試合数"] == 2
        assert row_a["1着率"] == 50.0
        assert row_a["2着率"] == 50.0
        assert row_a["3着率"] == 0.0
        assert row_a["4着率"] == 0.0
        assert row_a["総合pt"] == 60.0
        assert row_a["平均順位"] == 1.5

        # ── 2. 局スタッツ集計 (get_round_stats_summary) の検証
        df_round, n_games = db.get_round_stats_summary(group_id=grp_id)
        assert not df_round.empty
        assert n_games == 2

        r_a = df_round[df_round["名前"] == "集計A"].iloc[0]
        assert r_a["局数"] == 2
        assert r_a["和了率"] == 50.0
        assert r_a["放銃率"] == 50.0
        assert r_a["リーチ率"] == 50.0
        assert r_a["平均和了"] == 8000
        assert r_a["平均放銃"] == 3900


def test_group_and_guest_filter_logic():
    """グループ指定およびゲスト含む/含まないフィルターの正確性"""
    with _temp_test_db():
        m1 = db.add_member("正規A")
        m2 = db.add_member("正規B")
        m3 = db.add_member("正規C")
        m_guest = db.add_member("ゲストX", is_guest=1)
        grp_id = db.add_group("フィルターテスト部", "m_league")

        # ゲスト同卓の対局 (was_group_member=0)
        p_guest = {
            "played_at": "2026-09-02 10:00:00",
            "group_id": grp_id,
            "rule_id": "m_league",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "正規A", "final_score": 40000, "rank": 1, "point": 50.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "正規B", "final_score": 30000, "rank": 2, "point": 10.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "正規C", "final_score": 20000, "rank": 3, "point": -10.0, "was_group_member": 1},
                {"seat": 4, "member_id": m_guest, "player_name_snapshot": "ゲストX", "final_score": 10000, "rank": 4, "point": -50.0, "was_group_member": 0},
            ]
        }
        db.save_game_record(p_guest)

        # ゲストを除外する場合 (include_guests=False)
        # ゲスト本人のみが集計から除外され、正規メンバーのみ3名が返る
        df_no_guest = db.get_game_stats_summary(group_id=grp_id, include_guests=False)
        assert not df_no_guest.empty
        assert len(df_no_guest) == 3
        assert "ゲストX" not in df_no_guest["名前"].values
        assert "正規A" in df_no_guest["名前"].values

        # ゲストを含める場合 (include_guests=True)
        # ゲストを含めた全4名が返る
        df_with_guest = db.get_game_stats_summary(group_id=grp_id, include_guests=True)
        assert not df_with_guest.empty
        assert len(df_with_guest) == 4
        assert "ゲストX" in df_with_guest["名前"].values


def test_zero_division_and_empty_stats_safety():
    """データが空、または和了・放銃・流局が0回の場合でもZeroDivisionErrorが発生しないこと"""
    with _temp_test_db():
        # 1. 完全空DBでの集計
        df_empty_game = db.get_game_stats_summary()
        assert df_empty_game.empty

        df_empty_round, n_games = db.get_round_stats_summary()
        assert df_empty_round.empty
        assert n_games == 0

        # 2. 誰も和了・放銃していない流局のみの対局（全員和了0、放銃0）
        m1 = db.add_member("全員流局A")
        m2 = db.add_member("全員流局B")
        m3 = db.add_member("全員流局C")
        m4 = db.add_member("全員流局D")
        grp_id = db.add_group("流局グループ", "m_league")

        payload = {
            "played_at": "2026-09-03 10:00:00",
            "group_id": grp_id,
            "rule_id": "m_league",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "全員流局A", "final_score": 25000, "rank": 1, "point": 0.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "全員流局B", "final_score": 25000, "rank": 2, "point": 0.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "全員流局C", "final_score": 25000, "rank": 3, "point": 0.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "全員流局D", "final_score": 25000, "rank": 4, "point": 0.0, "was_group_member": 1},
            ],
            "rounds": [
                {
                    "round_index": 0,
                    "kyoku_name": "東1局",
                    "honba": 0,
                    "riichi_sticks": 0,
                    "result_type": "ryukyoku",
                    "seats": [
                        {"seat": 1, "member_id": m1, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 2, "member_id": m2, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 3, "member_id": m3, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                        {"seat": 4, "member_id": m4, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0, "han": 0, "fu": 0},
                    ]
                }
            ]
        }
        db.save_game_record(payload)

        # 和了率・放銃率などのゼロ除算が発生せず正常に計算されること
        df_round, n_games = db.get_round_stats_summary(group_id=grp_id)
        assert not df_round.empty
        assert n_games == 1
        r1 = df_round.iloc[0]
        assert r1["和了率"] == 0.0
        assert r1["放銃率"] == 0.0
        assert r1["平均和了"] == 0
        assert r1["平均放銃"] == 0
