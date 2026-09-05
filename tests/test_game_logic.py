import sys
import streamlit as st
import game_logic

class TestGameLogic:
    def setup_method(self):
        st.session_state.clear()
        cfg = {
            "basic": {"init_score": 25000},
            "detail": {
                "noten_bappu_pt": 3000,
                "mangan_base_pt": 8000,
                "chombo_rule": "mangan_pay",
                "renchan_rule": "tenpai"
            }
        }
        st.session_state.current_rule_config = cfg
        gs = game_logic.GameState(["P1", "P2", "P3", "P4"], 25000, cfg)
        st.session_state.game_state = gs
        st.session_state.game_active = True

    def test_ryukyoku_default_bappu(self):
        self.setup_method()
        st.session_state.game_state.round_history.append({
            "kyoku_name": "東1局",
            "win_type": "ryukyoku",
            "tenpai": ["P1", "P2"]
        })
        st.session_state.game_state.recalculate_state()
        # テンパイ2人、ノーテン2人。1人1500点移動
        assert st.session_state.game_state.scores["P1"] == 26500
        assert st.session_state.game_state.scores["P3"] == 23500
        
    def test_ryukyoku_custom_bappu(self):
        self.setup_method()
        # 罰符を 4000 に変更
        st.session_state.current_rule_config["detail"]["noten_bappu_pt"] = 4000
        st.session_state.game_state.round_history.append({
            "kyoku_name": "東1局",
            "win_type": "ryukyoku",
            "tenpai": ["P1"] # 1人テンパイ
        })
        st.session_state.game_state.recalculate_state()
        # テンパイ1人に4000、他3人が-1333 (4000 // 3 = 1333)
        assert st.session_state.game_state.scores["P1"] == 29000
        assert st.session_state.game_state.scores["P2"] == 23667

    def test_chombo_mangan_pay(self):
        self.setup_method()
        st.session_state.game_state.round_history.append({
            "kyoku_name": "東1局",
            "win_type": "chombo",
            "winner": "P2" # 子のチョンボ
        })
        st.session_state.game_state.recalculate_state()
        # 子が親(P1)に4000、子(P3,P4)に2000
        assert st.session_state.game_state.scores["P2"] == 17000
        assert st.session_state.game_state.scores["P1"] == 29000
        assert st.session_state.game_state.scores["P3"] == 27000

    def test_chombo_custom_mangan_base(self):
        self.setup_method()
        st.session_state.current_rule_config["detail"]["mangan_base_pt"] = 12000
        st.session_state.game_state.round_history.append({
            "kyoku_name": "東1局",
            "win_type": "chombo",
            "winner": "P1" # 親のチョンボ
        })
        st.session_state.game_state.recalculate_state()
        # 親が子全員に 12000 // 2 = 6000 支払い (合計 18000)
        assert st.session_state.game_state.scores["P1"] == 7000
        assert st.session_state.game_state.scores["P2"] == 31000

    def test_check_game_end_tobi(self):
        self.setup_method()
        st.session_state.game_state.scores["P4"] = -100
        # tobi_end: under_zero (default) -> should return tobi reason
        res = st.session_state.game_state.check_game_end()
        assert res is not None
        assert "飛び終了" in res

    def test_check_game_end_agari_yame(self):
        self.setup_method()
        st.session_state.game_state.round_idx = 7 # 南4局
        st.session_state.game_state.scores = {"P1": 31000, "P2": 25000, "P3": 24000, "P4": 20000}
        st.session_state.current_rule_config["basic"]["return_score"] = 30000
        st.session_state.current_rule_config["detail"]["agari_yame"] = True
        # P4が親だが、トップはP1のケース -> P4和了でも終了しない。ここではP4(親)がトップになったケースを作る。
        st.session_state.game_state.scores = {"P1": 25000, "P2": 25000, "P3": 20000, "P4": 31000}
        # 親が和了した履歴を作る
        st.session_state.game_state.round_history = [{
            "kyoku_name": "南4局",
            "win_type": "ron",
            "winner": "P4",
            "loser": "P1",
            "score": 1000
        }]
        res = st.session_state.game_state.check_game_end()
        assert res is not None
        assert "アガリやめ" in res

    def test_check_game_end_west_extension_sudden_death(self):
        self.setup_method()
        st.session_state.game_state.round_idx = 7 # 南4局終了時
        st.session_state.game_state.scores = {"P1": 29000, "P2": 28000, "P3": 23000, "P4": 20000}
        st.session_state.current_rule_config["detail"]["west_extension"] = "under_30000"
        st.session_state.current_rule_config["basic"]["return_score"] = 30000
        # トップが30000未満なので西入するはず（Noneを返す）
        res = st.session_state.game_state.check_game_end()
        assert res is None

        # 西1局（round_idx=8）でトップが30000を超えた場合
        st.session_state.game_state.round_idx = 8
        st.session_state.game_state.scores["P1"] = 32000
        res = st.session_state.game_state.check_game_end()
        assert res is not None
        assert "サドンデス終了" in res or "終了" in res

    def test_apply_mid_ryukyoku(self):
        self.setup_method()
        st.session_state.current_rule_config["detail"]["kyushu"] = "renchan"
        st.session_state.game_state.apply_mid_ryukyoku("kyushu")
        # renchanなら本場が1つ増え、局は進まない
        assert st.session_state.game_state.honba == 1
        assert st.session_state.game_state.round_idx == 0

        # ryukyoku設定なら親流れ（局が進む）
        self.setup_method()
        st.session_state.current_rule_config["detail"]["kyushu"] = "ryukyoku"
        st.session_state.game_state.apply_mid_ryukyoku("kyushu")
        assert st.session_state.game_state.honba == 1
        assert st.session_state.game_state.round_idx == 1

    def test_apply_multi_win_dubron_kyotaku(self):
        self.setup_method()
        st.session_state.game_state.round_history.append({
            "kyoku_name": "東1局",
            "win_type": "ryukyoku",
            "tenpai": ["P1", "P2", "P3", "P4"],
            "riichi_players": ["P1"] # P1がリーチして流局した（供託1本持ち越し）
        })
        st.session_state.game_state.recalculate_state()
        
        # P3が放銃、P1(親)とP2がダブロン
        wins_data = [
            {"winner": "P1", "points_data": {"total": 5800}},
            {"winner": "P2", "points_data": {"total": 3900}}
        ]
        st.session_state.game_state.apply_multi_win(wins_data, loser="P3")
        # 上家取り: 放銃者P3から見て、順番は P4 -> P1 -> P2。このうち和了者はP1とP2なので、P1が一番近い(上家)。
        # P1に供託が入るはず。
        # 1本場なので、各和了点に+300点が加算される
        assert st.session_state.game_state.scores["P3"] == 25000 - 5800 - 300 - 3900 - 300
        assert st.session_state.game_state.scores["P1"] == 25000 + 5800 + 300 + 1000 - 1000 # 供託含む。直前リーチで-1000
        assert st.session_state.game_state.scores["P2"] == 25000 + 3900 + 300
        # 親(P1)が和了したので連荘するはず
        assert st.session_state.game_state.round_idx == 0
        assert st.session_state.game_state.honba == 2 # 1本場からさらに連荘で2本場へ

    def test_renchan_rule(self):
        self.setup_method()
        st.session_state.current_rule_config["detail"]["renchan_rule"] = "agari"
        # テンパイ流局の場合、アガリ連荘なら親流れになるはず
        # 親はP1
        st.session_state.game_state.apply_ryukyoku(["P1", "P2"])
        assert st.session_state.game_state.round_idx == 1 # 局が進む

        self.setup_method()
        st.session_state.current_rule_config["detail"]["renchan_rule"] = "tenpai"
        # テンパイ連荘なら連荘するはず
        st.session_state.game_state.apply_ryukyoku(["P1", "P2"])
        assert st.session_state.game_state.round_idx == 0 # 局は進まない
        assert st.session_state.game_state.honba == 1

    def test_draft_autosave_and_restore(self):
        self.setup_method()
        saved_payloads = []
        import database2 as db
        original_save = getattr(db, "save_draft", None)
        try:
            db.save_draft = lambda payload: saved_payloads.append(payload)
            # 1. リーチ宣言でドラフト保存されること
            st.session_state.game_state.declare_riichi("P2")
            assert len(saved_payloads) >= 1
            last_draft = saved_payloads[-1]
            assert "game_state_data" in last_draft
            assert "current_rule_config" in last_draft

            # 2. 和了でドラフト保存されること
            st.session_state.game_state.apply_win("P1", "ron", {"total": 3900}, loser="P2")
            assert len(saved_payloads) >= 2
            draft_after_win = saved_payloads[-1]

            # 3. セッションをクリアしてドラフトから復元できること
            st.session_state.clear()
            assert "game_state" not in st.session_state
            assert "current_rule_config" not in st.session_state

            game_logic.restore_state_from_draft(draft_after_win)
            assert "game_state" in st.session_state
            assert isinstance(st.session_state.game_state, game_logic.GameState)
            assert st.session_state.game_state.scores["P1"] == 25000 + 3900 + 1000  # 供託1本含む
            assert st.session_state.current_rule_config["detail"]["noten_bappu_pt"] == 3000
        finally:
            if original_save is not None:
                db.save_draft = original_save
