import streamlit as st
import database2 as db
import copy

class GameState:
    def __init__(self, players, init_score, rule_config):
        self.players = list(players)
        self.init_score = init_score
        self.rule_config = rule_config or {}
        
        self.scores = {p: init_score for p in self.players}
        self.round_idx = 0
        self.honba = 0
        self.riichi_stick = 0
        
        self.round_history = []
        self.riichi_declared = []
        self.furo_declared = []
        self.undo_stack = []

    @classmethod
    def from_dict(cls, data):
        players = data.get("players", [])
        init_score = data.get("init_score", 25000)
        rule_config = data.get("rule_config", {})
        obj = cls(players, init_score, rule_config)
        obj.scores = data.get("scores", {p: init_score for p in players})
        obj.round_idx = data.get("round_idx", 0)
        obj.honba = data.get("honba", 0)
        obj.riichi_stick = data.get("riichi_stick", 0)
        obj.round_history = data.get("round_history", [])
        obj.riichi_declared = data.get("riichi_declared", [])
        obj.furo_declared = data.get("furo_declared", [])
        obj.undo_stack = data.get("undo_stack", [])
        return obj

    def to_dict(self):
        return {
            "players": self.players,
            "init_score": self.init_score,
            "rule_config": self.rule_config,
            "scores": self.scores,
            "round_idx": self.round_idx,
            "honba": self.honba,
            "riichi_stick": self.riichi_stick,
            "round_history": self.round_history,
            "riichi_declared": self.riichi_declared,
            "furo_declared": self.furo_declared,
            "undo_stack": self.undo_stack[-3:],
        }

    def get_dealer(self):
        return self.players[self.round_idx % 4]

    def get_round_name(self, idx=None):
        i = idx if idx is not None else self.round_idx
        wind = ["東", "南", "西"][min(i // 4, 2)]
        return f"{wind}{(i % 4) + 1}局"

    def save_snapshot(self):
        snap = {
            "riichi_declared": list(self.riichi_declared),
            "furo_declared": list(self.furo_declared),
            "round_history": copy.deepcopy(self.round_history),
        }
        self.undo_stack.append(snap)
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)

    def undo_last(self):
        if not self.undo_stack:
            return False
        snap = self.undo_stack.pop()
        self.riichi_declared = snap.get("riichi_declared", [])
        self.furo_declared = snap.get("furo_declared", [])
        self.round_history = snap.get("round_history", [])
        self.recalculate_state()
        return True

    def recalculate_state(self):
        if not self.players:
            return
        
        self.scores = {p: self.init_score for p in self.players}
        self.riichi_stick = 0
        self.honba = 0
        self.round_idx = 0

        for r in self.round_history:
            dealer = self.players[self.round_idx % 4]
            wind = ["東", "南", "西"][min(self.round_idx // 4, 2)]
            r["kyoku_name"] = f"{wind}{(self.round_idx % 4) + 1}局"

            # リーチ処理
            for p in r.get("riichi", []):
                if p in self.scores:
                    self.scores[p] -= 1000
                    self.riichi_stick += 1

            win_type = r.get("win_type", "")
            winner = r.get("winner", "")
            loser = r.get("loser", "")
            score = r.get("score", 0)
            
            dealer_continues = False

            if win_type == "ron":
                total = score + self.honba * 300
                if loser in self.scores:
                    self.scores[loser] -= total
                if winner in self.scores:
                    self.scores[winner] += total + self.riichi_stick * 1000
                self.riichi_stick = 0
                if winner == dealer:
                    dealer_continues = True

            elif win_type == "tsumo":
                if winner == dealer:
                    each = (score // 3) + self.honba * 100
                    for p in self.players:
                        if p != winner:
                            self.scores[p] -= each
                            self.scores[winner] += each
                    self.scores[winner] += self.riichi_stick * 1000
                    dealer_continues = True
                else:
                    base_ko_pay = int(((score / 4) + 99) // 100 * 100)
                    base_oya_pay = score - (base_ko_pay * 2)
                    oya_pay = base_oya_pay + self.honba * 100
                    ko_pay = base_ko_pay + self.honba * 100
                    for p in self.players:
                        if p == winner:
                            continue
                        pay = oya_pay if p == dealer else ko_pay
                        self.scores[p] -= pay
                        self.scores[winner] += pay
                    self.scores[winner] += self.riichi_stick * 1000
                self.riichi_stick = 0

            elif win_type == "ryukyoku":
                tenpai = r.get("tenpai", [])
                noten = [p for p in self.players if p not in tenpai]
                n_t, n_n = len(tenpai), len(noten)
                if 0 < n_t < 4:
                    bappu = self.rule_config.get("detail", {}).get("noten_bappu_pt", 3000)
                    each_noten = bappu // n_n
                    each_tenpai = bappu // n_t
                    for p in noten:
                        self.scores[p] -= each_noten
                    for p in tenpai:
                        self.scores[p] += each_tenpai
                
                renchan_rule = self.rule_config.get("detail", {}).get("renchan_rule", "tenpai")
                if renchan_rule == "tenpai":
                    dealer_continues = (dealer in tenpai)
                elif renchan_rule == "agari":
                    dealer_continues = False
                elif renchan_rule == "noten":
                    dealer_continues = True

            elif win_type == "chombo":
                chombo_p = winner
                detail_cfg = self.rule_config.get("detail", {})
                chombo_rule = detail_cfg.get("chombo_rule", "mangan_pay")
                if chombo_rule == "mangan_pay":
                    m_base = detail_cfg.get("mangan_base_pt", 8000)
                    oya_pay = m_base // 2
                    ko_pay = m_base // 4
                    if chombo_p == dealer:
                        for p in self.players:
                            if p != chombo_p:
                                self.scores[chombo_p] -= oya_pay
                                self.scores[p] += oya_pay
                    else:
                        for p in self.players:
                            if p == chombo_p:
                                continue
                            elif p == dealer:
                                self.scores[chombo_p] -= oya_pay
                                self.scores[p] += oya_pay
                            else:
                                self.scores[chombo_p] -= ko_pay
                                self.scores[p] += ko_pay
                dealer_continues = True

            elif win_type == "multi_ron":
                wins_data = r.get("multi_wins", [])
                loser_idx = self.players.index(loser) if loser in self.players else 0
                def distance(p):
                    idx = self.players.index(p) if p in self.players else 0
                    return (idx - loser_idx) % 4
                
                closest_winner = min([wd["winner"] for wd in wins_data], key=distance) if wins_data else ""
                is_dealer_won = False
                
                for wd in wins_data:
                    w = wd["winner"]
                    pts = wd["points_data"]["total"] + self.honba * 300
                    if loser in self.scores:
                        self.scores[loser] -= pts
                    if w in self.scores:
                        self.scores[w] += pts
                    if w == dealer:
                        is_dealer_won = True
                        
                if closest_winner in self.scores:
                    self.scores[closest_winner] += self.riichi_stick * 1000
                self.riichi_stick = 0
                if is_dealer_won:
                    dealer_continues = True
                    
            elif win_type == "mid_ryukyoku":
                ryukyoku_type = r.get("ryukyoku_type", "other")
                dealer_continues = True
                if ryukyoku_type != "other" and self.rule_config.get("detail", {}).get(ryukyoku_type) == "ryukyoku":
                    dealer_continues = False

            if win_type == "chombo":
                pass
            elif win_type in ("ryukyoku", "mid_ryukyoku"):
                self.honba += 1
                if not dealer_continues:
                    self.round_idx += 1
            else:
                if dealer_continues:
                    self.honba += 1
                else:
                    self.round_idx += 1
                    self.honba = 0

        # 進行中の局のリーチ宣言を反映
        for p in self.riichi_declared:
            if p in self.scores:
                self.scores[p] -= 1000
                self.riichi_stick += 1
        autosave_draft()

    def record_round(self, winner, loser, win_type, score, tenpai=None):
        self.round_history.append({
            "kyoku_name": self.get_round_name(),
            "winner": winner or "",
            "loser": loser or "",
            "win_type": win_type,
            "score": score,
            "riichi": list(self.riichi_declared),
            "furo": list(self.furo_declared),
            "tenpai": tenpai or [],
        })

    def declare_riichi(self, player):
        self.save_snapshot()
        if player not in self.riichi_declared:
            self.riichi_declared.append(player)
        self.recalculate_state()

    def apply_win(self, winner, win_type, points_data, loser=None):
        self.save_snapshot()
        self.record_round(winner, loser, win_type, points_data.get("total", 0))
        self.riichi_declared = []
        self.furo_declared = []
        self.recalculate_state()

    def check_game_end(self):
        detail = self.rule_config.get("detail", {})
        
        tobi_end = detail.get("tobi_end", "under_zero")
        if tobi_end == "under_zero":
            for p, s in self.scores.items():
                if s < 0:
                    return f"飛び終了（{p} が0点未満）"
        elif tobi_end == "zero_or_less":
            for p, s in self.scores.items():
                if s <= 0:
                    return f"飛び終了（{p} が0点以下）"
                    
        top_score = max(self.scores.values())
        top_players = [p for p, s in self.scores.items() if s == top_score]
        
        west_ext = detail.get("west_extension", "under_30000")
        b_cfg = self.rule_config.get("basic", {})
        ret_score = b_cfg.get("return_score", 30000)
        
        if self.round_idx >= 7: # 南4局以降
            dealer = self.players[self.round_idx % 4]
            if top_score >= ret_score or (west_ext in ["none", "fixed_nan4"]):
                if dealer in top_players:
                    if self.round_history:
                        last_round = self.round_history[-1]
                        if last_round["kyoku_name"] == self.get_round_name(self.round_idx):
                            if detail.get("agari_yame", True):
                                win_t = last_round.get("win_type", "")
                                if win_t in ("ron", "tsumo") and last_round.get("winner") == dealer:
                                    return "アガリやめ（親トップ）"
                                elif win_t == "multi_ron" and any(wd.get("winner") == dealer for wd in last_round.get("multi_wins", [])):
                                    return "アガリやめ（親トップ）"
                            if detail.get("tenpai_yame", True):
                                if last_round.get("win_type") == "ryukyoku" and dealer in last_round.get("tenpai", []):
                                    return "テンパイやめ（親トップ）"
        if west_ext == "none" or west_ext == "fixed_nan4":
            if self.round_idx >= 8:
                return "南4局終了"
        else:
            if top_score >= ret_score:
                if self.round_idx == 8 and len([r for r in self.round_history if r["kyoku_name"].startswith("西")]) == 0:
                    return f"南4局終了（トップ {top_score:,}点）"
                elif self.round_idx >= 8:
                    return f"サドンデス終了（トップ {top_score:,}点）"
            elif self.round_idx >= 12:
                return "西4局終了（北入りなし）"
                
        return None

    def apply_ryukyoku(self, tenpai_players):
        self.save_snapshot()
        self.record_round(None, None, "ryukyoku", 0, tenpai=tenpai_players)
        self.riichi_declared = []
        self.furo_declared = []
        self.recalculate_state()

    def apply_mid_ryukyoku(self, ryukyoku_type, tenpai_players=None):
        self.save_snapshot()
        self.round_history.append({
            "kyoku_name": self.get_round_name(),
            "winner": "",
            "loser": "",
            "win_type": "mid_ryukyoku",
            "score": 0,
            "ryukyoku_type": ryukyoku_type,
            "riichi": list(self.riichi_declared),
            "furo": list(self.furo_declared),
            "tenpai": tenpai_players or [],
        })
        self.riichi_declared = []
        self.furo_declared = []
        self.recalculate_state()

    def apply_multi_win(self, wins_data, loser):
        self.save_snapshot()
        loser_idx = self.players.index(loser) if loser in self.players else 0
        def distance(p):
            idx = self.players.index(p) if p in self.players else 0
            return (idx - loser_idx) % 4
            
        closest_winner = min([wd["winner"] for wd in wins_data], key=distance) if wins_data else ""
            
        self.round_history.append({
            "kyoku_name": self.get_round_name(),
            "winner": closest_winner,
            "loser": loser,
            "win_type": "multi_ron",
            "score": 0,
            "multi_wins": wins_data,
            "riichi": list(self.riichi_declared),
            "furo": list(self.furo_declared),
            "tenpai": [],
        })
        self.riichi_declared = []
        self.furo_declared = []
        self.recalculate_state()

    def apply_chombo(self, player):
        self.save_snapshot()
        self.record_round(player, None, "chombo", 0)
        self.riichi_declared = []
        self.furo_declared = []
        self.recalculate_state()


def autosave_draft():
    if not st.session_state.get("game_active"):
        return
    
    gs = st.session_state.get("game_state")
    state = {
        "view": st.session_state.get("view", "setup"),
        "game_active": True,
        "game_mode": st.session_state.get("game_mode", "detail"),
        "input_mode": st.session_state.get("input_mode", "normal"),
        "current_rule_id": st.session_state.get("current_rule_id"),
        "current_group_id": st.session_state.get("current_group_id"),
        "player_member_ids": st.session_state.get("player_member_ids", {}),
    }
    if gs:
        state["game_state_data"] = gs.to_dict()
    if st.session_state.get("current_rule_config"):
        state["current_rule_config"] = st.session_state.get("current_rule_config")

    try:
        db.save_draft(state)
    except Exception as e:
        st.session_state["draft_save_error"] = str(e)


def restore_state_from_draft(draft_state):
    """ドラフトデータから st.session_state を復元し、GameStateを再構築する"""
    if not draft_state or not draft_state.get("game_active"):
        return
        
    for k, v in draft_state.items():
        if k == "game_state_data":
            st.session_state["game_state"] = GameState.from_dict(v)
        else:
            st.session_state[k] = v
            
    # 旧バージョンのドラフトデータに対する互換性対応
    if "game_state" not in st.session_state and "players" in draft_state:
        rule_config = draft_state.get("current_rule_config", {})
        init_score = rule_config.get("basic", {}).get("init_score", rule_config.get("init_score", 25000))
        
        compat_data = {
            "players": draft_state.get("players", []),
            "init_score": init_score,
            "rule_config": rule_config,
            "scores": draft_state.get("scores", {}),
            "round_idx": draft_state.get("round_idx", 0),
            "honba": draft_state.get("honba", 0),
            "riichi_stick": draft_state.get("riichi_stick", 0),
            "round_history": draft_state.get("round_history", []),
            "riichi_declared": draft_state.get("riichi_declared", []),
            "furo_declared": draft_state.get("furo_declared", []),
            "undo_stack": draft_state.get("undo_stack", []),
        }
        st.session_state["game_state"] = GameState.from_dict(compat_data)

    if "game_state" in st.session_state and st.session_state["game_state"].rule_config:
        st.session_state["current_rule_config"] = st.session_state["game_state"].rule_config

def reset_game():
    """対局データの完全一括リセット"""
    keys = [
        "game_active", "game_state", "diff_target",
        "input_mode", "win_step", "win_data",
        "selected_players", "tenpai_selection", "confirm_endgame", "confirm_discard",
        "draft_save_error", "draft_data", "draft_time",
        "players", "scores", "round_idx", "honba", "riichi_stick", "riichi_declared", "furo_declared", "undo_stack", "round_history" # Legacy keys just in case
    ]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.view = "setup"
    db.delete_draft()
