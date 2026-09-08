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


def test_update_game_record_atomic_and_backup():
    """update_game_record_atomic による局データ・参加者データの不可分置換とゼロサムバリデーションを検証"""
    with _temp_test_db():
        m1 = db.add_member("プレイヤーA")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")

        initial_payload = {
            "played_at": "2026-09-09 10:00:00",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {"basic": {"init_score": 25000}},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 33000, "rank": 1, "point": 13.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 17000, "rank": 4, "point": -33.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 25000, "rank": 2, "point": 5.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 25000, "rank": 3, "point": -5.0, "was_group_member": 1},
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
        game_id = db.save_game_record(initial_payload)

        # 修正ペイロード: 和了者をAからCに変更 (A:25000, B:17000, C:33000, D:25000)
        updated_payload = {
            "rule_config_snapshot": {"basic": {"init_score": 25000}},
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 25000, "rank": 2, "point": 5.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 17000, "rank": 4, "point": -33.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 33000, "rank": 1, "point": 13.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 25000, "rank": 3, "point": -5.0, "was_group_member": 1},
            ],
            "rounds": [
                {
                    "round_index": 0,
                    "kyoku_name": "東1局",
                    "honba": 0,
                    "riichi_sticks": 0,
                    "result_type": "ron",
                    "seats": [
                        {"seat": 1, "member_id": m1, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                        {"seat": 2, "member_id": m2, "score_delta": -8000, "base_point": -8000, "is_winner": 0, "is_loser": 1, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                        {"seat": 3, "member_id": m3, "score_delta": 8000, "base_point": 8000, "is_winner": 1, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 1},
                        {"seat": 4, "member_id": m4, "score_delta": 0, "base_point": 0, "is_winner": 0, "is_loser": 0, "is_riichi": 0, "is_furo": 0, "is_tenpai": 0},
                    ]
                }
            ]
        }

        db.update_game_record_atomic(game_id, updated_payload)

        # 検証: Cが1位、Aが2位になっていること
        details = db.get_game_details(game_id)
        assert details["game_id"] == game_id
        assert details["is_synced"] == 0  # 未同期リセット

        parts = {p["player_name_snapshot"]: p for p in details["participants"]}
        assert parts["プレイヤーC"]["final_score"] == 33000
        assert parts["プレイヤーC"]["rank"] == 1
        assert parts["プレイヤーA"]["final_score"] == 25000

        # round_seats で和了者がCになっていること
        r_seats = details["rounds"][0]["seats"]
        winner_seat = next(s for s in r_seats if s["is_winner"] == 1)
        assert winner_seat["member_id"] == m3

        # 不正な合計点数 (99,000点) で更新しようとした場合に ValueError で拒絶されること
        bad_payload = dict(updated_payload)
        bad_payload["participants"] = [
            {"seat": 1, "member_id": m1, "final_score": 24000, "rank": 2, "point": 0},
            {"seat": 2, "member_id": m2, "final_score": 17000, "rank": 4, "point": 0},
            {"seat": 3, "member_id": m3, "final_score": 33000, "rank": 1, "point": 0},
            {"seat": 4, "member_id": m4, "final_score": 25000, "rank": 3, "point": 0},
        ]
        try:
            db.update_game_record_atomic(game_id, bad_payload)
            assert False, "合計点不正で例外が発生しませんでした"
        except ValueError:
            pass  # 正常に拒絶された


def test_update_game_basic_info_atomic_and_backup():
    """update_game_basic_info による日時・素点更新とゼロサム検証"""
    with _temp_test_db():
        m1 = db.add_member("プレイヤーA")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")

        payload = {
            "played_at": "2026-09-09 10:00:00",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {},
            "game_mode": "simple",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 25000, "rank": 1, "point": 0.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 25000, "rank": 2, "point": 0.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 25000, "rank": 3, "point": 0.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 25000, "rank": 4, "point": 0.0, "was_group_member": 1},
            ],
            "rounds": []
        }
        game_id = db.save_game_record(payload)

        new_date = "2026-09-09 18:30:00"
        new_participants = [
            {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 40000, "rank": 1, "point": 50.0, "was_group_member": 1},
            {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 30000, "rank": 2, "point": 10.0, "was_group_member": 1},
            {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 20000, "rank": 3, "point": -10.0, "was_group_member": 1},
            {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 10000, "rank": 4, "point": -50.0, "was_group_member": 1},
        ]
        db.update_game_basic_info(game_id, new_date, new_participants)

        details = db.get_game_details(game_id)
        assert details["played_at"] == new_date
        assert details["is_synced"] == 0

        parts = {p["player_name_snapshot"]: p for p in details["participants"]}
        assert parts["プレイヤーA"]["final_score"] == 40000
        assert parts["プレイヤーA"]["point"] == 50.0
        assert parts["プレイヤーD"]["final_score"] == 10000


def test_round_edit_multi_ron_recalculation():
    """局修正においてダブロン（multi_ron）へ修正した際、GameState復元・再計算・DB更新が正常に機能するかを検証"""
    with _temp_test_db():
        m1 = db.add_member("プレイヤーA")
        m2 = db.add_member("プレイヤーB")
        m3 = db.add_member("プレイヤーC")
        m4 = db.add_member("プレイヤーD")
        players = ["プレイヤーA", "プレイヤーB", "プレイヤーC", "プレイヤーD"]
        player_mids = {"プレイヤーA": m1, "プレイヤーB": m2, "プレイヤーC": m3, "プレイヤーD": m4}

        initial_payload = {
            "played_at": "2026-09-09 10:00:00",
            "rule_name_snapshot": "Mリーグルール",
            "rule_config_snapshot": {"basic": {"init_score": 25000}},
            "game_mode": "detail",
            "participants": [
                {"seat": 1, "member_id": m1, "player_name_snapshot": "プレイヤーA", "final_score": 33000, "rank": 1, "point": 13.0, "was_group_member": 1},
                {"seat": 2, "member_id": m2, "player_name_snapshot": "プレイヤーB", "final_score": 17000, "rank": 4, "point": -33.0, "was_group_member": 1},
                {"seat": 3, "member_id": m3, "player_name_snapshot": "プレイヤーC", "final_score": 25000, "rank": 2, "point": 5.0, "was_group_member": 1},
                {"seat": 4, "member_id": m4, "player_name_snapshot": "プレイヤーD", "final_score": 25000, "rank": 3, "point": -5.0, "was_group_member": 1},
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
        game_id = db.save_game_record(initial_payload)

        # 局修正ロジックのシミュレーション: DBから GameState を復元
        game_dict = db.get_game_details(game_id)
        from views.round_edit import _restore_game_state_from_db
        gstate, p_list, p_mids, p_was_mem, r_cfg = _restore_game_state_from_db(game_dict)

        # 東1局を「ダブロン (A: 8000点, C: 4000点, 放銃者: B)」に修正
        updated_round = dict(gstate.round_history[0])
        updated_round["win_type"] = "multi_ron"
        updated_round["winner"] = ""
        updated_round["loser"] = "プレイヤーB"
        updated_round["score"] = 0
        updated_round["multi_wins"] = [
            {"winner": "プレイヤーA", "points_data": {"total": 8000}},
            {"winner": "プレイヤーC", "points_data": {"total": 4000}}
        ]
        gstate.round_history[0] = updated_round
        gstate.recalculate_state()

        # スコア検証: A: 25000 + 8000 = 33000, B: 25000 - 12000 = 13000, C: 25000 + 4000 = 29000, D: 25000
        assert gstate.scores["プレイヤーA"] == 33000
        assert gstate.scores["プレイヤーB"] == 13000
        assert gstate.scores["プレイヤーC"] == 29000
        assert gstate.scores["プレイヤーD"] == 25000
        assert sum(gstate.scores.values()) == 100000

        # payload 構築して保存
        import game_logic
        payload = game_logic.build_v2_game_payload(
            game_state=gstate,
            players=p_list,
            scores=gstate.scores,
            group_id=None,
            rule_id="m_league",
            rule_config=r_cfg,
            player_member_ids=p_mids,
            player_was_group_member=p_was_mem,
            date_str="2026-09-09 10:00:00",
            game_id=game_id
        )
        db.update_game_record_atomic(game_id, payload)

        # 保存後の検証
        saved_details = db.get_game_details(game_id)
        saved_round = saved_details["rounds"][0]
        assert saved_round["result_type"] == "multi_ron"

        saved_seats = {s["seat"]: s for s in saved_round["seats"]}
        assert saved_seats[1]["is_winner"] == 1
        assert saved_seats[1]["base_point"] == 8000
        assert saved_seats[3]["is_winner"] == 1
        assert saved_seats[3]["base_point"] == 4000
        assert saved_seats[2]["is_loser"] == 1
        assert saved_seats[2]["score_delta"] == -12000

        # 再度復元しても multi_ron として正常に復元できること
        restored_state2, _, _, _, _ = _restore_game_state_from_db(saved_details)
        assert restored_state2.round_history[0]["win_type"] == "multi_ron"
        assert len(restored_state2.round_history[0]["multi_wins"]) == 2


