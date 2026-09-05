import sys
import os
import streamlit as st
import game_logic
import views.home as home_view
import database2 as db

class MockDatabaseDraft:
    """本番DBに一切アクセスせず、メモリ上だけでドラフト操作を完結・検証するモック"""
    def __init__(self):
        self.draft = None
        self.save_count = 0
        self.delete_count = 0

    def save_draft(self, state_dict):
        self.draft = state_dict
        self.save_count += 1

    def load_draft(self):
        return self.draft, None

    def delete_draft(self):
        self.draft = None
        self.delete_count += 1


class TestInterruptionRecovery:
    """対局中断・セッション喪失・復元を包括的に検証するテストスイート"""

    def setup_method(self):
        st.session_state.clear()
        self.mock_db = MockDatabaseDraft()
        self.orig_save = getattr(db, "save_draft", None)
        self.orig_load = getattr(db, "load_draft", None)
        self.orig_delete = getattr(db, "delete_draft", None)

        db.save_draft = self.mock_db.save_draft
        db.load_draft = self.mock_db.load_draft
        db.delete_draft = self.mock_db.delete_draft

        self.cfg = {
            "basic": {
                "init_score": 25000,
                "return_score": 30000,
                "uma": [50, 10, -10, -30],
                "rounding_type": "五捨六入"
            },
            "detail": {
                "noten_bappu_pt": 3000,
                "mangan_base_pt": 8000,
                "chombo_rule": "mangan_pay",
                "renchan_rule": "tenpai",
                "west_extension": "under_30000",
                "tobi_end": "under_zero"
            }
        }
        self.players = ["フルタ", "オッチャン", "リョウト", "シュン"]
        st.session_state.game_state = game_logic.GameState(self.players, 25000, self.cfg)
        st.session_state.game_active = True
        st.session_state.current_rule_config = self.cfg
        st.session_state.current_rule_id = "rule_test"
        st.session_state.current_group_id = "group_test"
        st.session_state.view = "game"
        st.session_state.input_mode = "normal"

    def teardown_method(self):
        if self.orig_save: db.save_draft = self.orig_save
        if self.orig_load: db.load_draft = self.orig_load
        if self.orig_delete: db.delete_draft = self.orig_delete

    def test_all_10_actions_trigger_draft_autosave(self):
        """リーチ、鳴き、ツモ、ロン、ダブロン、流局、途中流局、チョンボ、Undo、履歴修正の全10操作で保存されること"""
        self.setup_method()
        gs = st.session_state.game_state
        initial_saves = self.mock_db.save_count

        # 1. リーチ宣言
        gs.declare_riichi("フルタ")
        assert self.mock_db.save_count == initial_saves + 1
        assert "フルタ" in self.mock_db.draft["game_state_data"]["riichi_declared"]
        assert self.mock_db.draft["input_mode"] == "normal"

        # 2. 副露トグル
        gs.furo_declared.append("オッチャン")
        game_logic.autosave_draft()
        assert self.mock_db.save_count == initial_saves + 2
        assert "オッチャン" in self.mock_db.draft["game_state_data"]["furo_declared"]

        # 3. ツモ和了 (東1局)
        gs.apply_win("フルタ", "tsumo", {"total": 3000}) # 1000 all
        assert self.mock_db.save_count == initial_saves + 3
        assert self.mock_db.draft["input_mode"] == "normal"
        assert self.mock_db.draft["view"] == "game"

        # 4. ロン和了 (東1局1本場連荘)
        gs.apply_win("リョウト", "ron", {"total": 2000}, loser="シュン")
        assert self.mock_db.save_count == initial_saves + 4

        # 5. 通常流局 (東2局)
        gs.apply_ryukyoku(["オッチャン"])
        assert self.mock_db.save_count == initial_saves + 5

        # 6. 途中流局 (東2局1本場連荘)
        gs.apply_mid_ryukyoku("sufon", tenpai_players=[])
        assert self.mock_db.save_count == initial_saves + 6

        # 7. ダブロン
        wins = [
            {"winner": "オッチャン", "points_data": {"total": 3900}},
            {"winner": "リョウト", "points_data": {"total": 5200}}
        ]
        gs.apply_multi_win(wins, loser="フルタ")
        assert self.mock_db.save_count == initial_saves + 7

        # 8. チョンボ
        gs.apply_chombo("シュン")
        assert self.mock_db.save_count == initial_saves + 8

        # 9. Undo (1局戻す)
        undone = gs.undo_last()
        assert undone is True
        assert self.mock_db.save_count == initial_saves + 9

        # 10. 局履歴の編集・再計算
        gs.round_history[0]["score"] = 6000
        gs.recalculate_state()
        assert self.mock_db.save_count == initial_saves + 10

        self.teardown_method()

    def test_crash_and_full_recovery_simulation(self):
        """対局途中で突然メモリが完全破棄されても、直前の局状態・ルール設定・通常画面に100%復帰すること"""
        self.setup_method()
        gs = st.session_state.game_state

        # 複数局進行
        gs.declare_riichi("フルタ")
        gs.apply_win("フルタ", "tsumo", {"total": 6000}) # 親満 2000 all + 供託1000
        gs.declare_riichi("オッチャン")
        gs.apply_win("シュン", "ron", {"total": 8000}, loser="オッチャン")

        expected_scores = dict(gs.scores)
        expected_round_idx = gs.round_idx
        expected_honba = gs.honba
        expected_history_len = len(gs.round_history)

        # 最新ドラフト取得
        saved_draft = self.mock_db.draft
        assert saved_draft is not None
        assert saved_draft["view"] == "game"
        assert saved_draft["input_mode"] == "normal"

        # === クラッシュ発生 (メモリの完全破棄) ===
        st.session_state.clear()
        assert "game_state" not in st.session_state
        assert "current_rule_config" not in st.session_state

        # === 復元実行 ===
        game_logic.restore_state_from_draft(saved_draft)

        assert "game_state" in st.session_state
        restored_gs = st.session_state.game_state
        assert isinstance(restored_gs, game_logic.GameState)
        assert restored_gs.scores == expected_scores
        assert restored_gs.round_idx == expected_round_idx
        assert restored_gs.honba == expected_honba
        assert len(restored_gs.round_history) == expected_history_len
        assert st.session_state.view == "game"
        assert st.session_state.input_mode == "normal"
        # カスタムルールが保持されていること
        assert st.session_state.current_rule_config["basic"]["uma"] == [50, 10, -10, -30]
        assert st.session_state.current_rule_config["detail"]["noten_bappu_pt"] == 3000

        self.teardown_method()

    def test_resume_from_home_view(self):
        """ホーム画面の「対局を再開する」経由でも GameState が完全復元されること"""
        self.setup_method()
        gs = st.session_state.game_state
        gs.declare_riichi("リョウト")
        gs.apply_win("リョウト", "tsumo", {"total": 4000})

        saved_draft = self.mock_db.draft
        st.session_state.clear()
        st.session_state.view = "home"
        st.session_state.draft_data = saved_draft

        # ホーム画面の再開ボタンを呼び出し
        home_view._resume_draft(saved_draft)

        assert "game_state" in st.session_state
        assert isinstance(st.session_state.game_state, game_logic.GameState)
        assert st.session_state.view == "game"
        assert st.session_state.input_mode == "normal"
        assert st.session_state.game_state.scores["リョウト"] == 25000 - 1000 + 4000 + 1000

        self.teardown_method()

    def test_cleanup_on_reset(self):
        """リセット時にドラフトが確実に削除されること"""
        self.setup_method()
        game_logic.autosave_draft()
        assert self.mock_db.draft is not None

        game_logic.reset_game()
        assert self.mock_db.delete_count >= 1
        assert self.mock_db.draft is None
        assert st.session_state.view == "setup"
        assert "game_state" not in st.session_state

        self.teardown_method()
