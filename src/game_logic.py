import streamlit as st
import database2 as db


def get_round_name(idx=None):
    i = idx if idx is not None else st.session_state.round_idx
    wind = ["東", "南", "西"][min(i // 4, 2)]
    return f"{wind}{(i % 4) + 1}局"


def get_dealer():
    return st.session_state.players[st.session_state.round_idx % 4]


def save_snapshot():
    snap = {
        "riichi_declared": list(st.session_state.riichi_declared),
        "furo_declared": list(st.session_state.furo_declared),
        "round_history": list(st.session_state.round_history),
    }
    st.session_state.undo_stack.append(snap)
    if len(st.session_state.undo_stack) > 80:
        st.session_state.undo_stack.pop(0)


def undo_last():
    if not st.session_state.undo_stack:
        return False
    snap = st.session_state.undo_stack.pop()
    st.session_state.riichi_declared = snap.get("riichi_declared", [])
    st.session_state.furo_declared = snap.get("furo_declared", [])
    st.session_state.round_history = snap.get("round_history", [])
    st.session_state.diff_target = None
    recalculate_state()
    return True


def _parse_kyoku_idx(kyoku_name):
    if not kyoku_name or len(kyoku_name) < 3:
        return 0
    wind_map = {"東": 0, "南": 1, "西": 2}
    w = wind_map.get(kyoku_name[0], 0)
    try:
        num = int(kyoku_name[1]) - 1
    except ValueError:
        num = 0
    return w * 4 + num


def recalculate_state():
    players = st.session_state.players
    if not players:
        return
    active_cfg = st.session_state.get("current_rule_config", {})
    b_cfg = active_cfg.get("basic", active_cfg)
    init_score_val = b_cfg.get("init_score", 25000)
    scores = {p: init_score_val for p in players}
    riichi_stick = 0
    honba = 0
    current_round_idx = 0

    for i, r in enumerate(st.session_state.round_history):
        dealer = players[current_round_idx % 4]
        wind = ["東", "南", "西"][min(current_round_idx // 4, 2)]
        r["kyoku_name"] = f"{wind}{(current_round_idx % 4) + 1}局"

        # リーチ処理
        riichi_list = r.get("riichi", [])
        for p in riichi_list:
            if p in scores:
                scores[p] -= 1000
                riichi_stick += 1

        win_type = r.get("win_type", "")
        winner = r.get("winner", "")
        loser = r.get("loser", "")
        score = r.get("score", 0)
        
        dealer_continues = False

        if win_type == "ron":
            total = score + honba * 300
            if loser in scores:
                scores[loser] -= total
            if winner in scores:
                scores[winner] += total + riichi_stick * 1000
            riichi_stick = 0
            if winner == dealer:
                dealer_continues = True

        elif win_type == "tsumo":
            if winner == dealer:
                each = (score // 3) + honba * 100
                for p in players:
                    if p != winner:
                        scores[p] -= each
                        scores[winner] += each
                scores[winner] += riichi_stick * 1000
                dealer_continues = True
            else:
                oya_pay = int(((score / 2) + 99) // 100 * 100) + honba * 100
                ko_pay = int(((score / 4) + 99) // 100 * 100) + honba * 100
                for p in players:
                    if p == winner:
                        continue
                    pay = oya_pay if p == dealer else ko_pay
                    scores[p] -= pay
                    scores[winner] += pay
                scores[winner] += riichi_stick * 1000
            riichi_stick = 0

        elif win_type == "ryukyoku":
            tenpai = r.get("tenpai", [])
            noten = [p for p in players if p not in tenpai]
            n_t, n_n = len(tenpai), len(noten)
            if 0 < n_t < 4:
                bappu = active_cfg.get("detail", {}).get("noten_bappu_pt", 3000)
                each_noten = bappu // n_n
                each_tenpai = bappu // n_t
                for p in noten:
                    scores[p] -= each_noten
                for p in tenpai:
                    scores[p] += each_tenpai
            
            renchan_rule = active_cfg.get("detail", {}).get("renchan_rule", "tenpai")
            if renchan_rule == "tenpai":
                dealer_continues = (dealer in tenpai)
            elif renchan_rule == "agari":
                dealer_continues = False
            elif renchan_rule == "noten":
                dealer_continues = True

        elif win_type == "chombo":
            chombo_p = winner
            detail_cfg = active_cfg.get("detail", {})
            chombo_rule = detail_cfg.get("chombo_rule", "mangan_pay")
            if chombo_rule == "mangan_pay":
                m_base = detail_cfg.get("mangan_base_pt", 8000)
                oya_pay = m_base // 2
                ko_pay = m_base // 4
                if chombo_p == dealer:
                    for p in players:
                        if p != chombo_p:
                            scores[chombo_p] -= oya_pay
                            scores[p] += oya_pay
                else:
                    for p in players:
                        if p == chombo_p:
                            continue
                        elif p == dealer:
                            scores[chombo_p] -= oya_pay
                            scores[p] += oya_pay
                        else:
                            scores[chombo_p] -= ko_pay
                            scores[p] += ko_pay
            dealer_continues = True

        elif win_type == "multi_ron":
            wins_data = r.get("multi_wins", [])
            loser_idx = players.index(loser) if loser in players else 0
            def distance(p):
                idx = players.index(p) if p in players else 0
                return (idx - loser_idx) % 4
            
            closest_winner = min([wd["winner"] for wd in wins_data], key=distance) if wins_data else ""
            is_dealer_won = False
            
            for wd in wins_data:
                w = wd["winner"]
                pts = wd["points_data"]["total"] + honba * 300
                if loser in scores:
                    scores[loser] -= pts
                if w in scores:
                    scores[w] += pts
                if w == dealer:
                    is_dealer_won = True
                    
            if closest_winner in scores:
                scores[closest_winner] += riichi_stick * 1000
            riichi_stick = 0
            if is_dealer_won:
                dealer_continues = True
                
        elif win_type == "mid_ryukyoku":
            ryukyoku_type = r.get("ryukyoku_type", "other")
            dealer_continues = True
            if ryukyoku_type != "other" and active_cfg.get("detail", {}).get(ryukyoku_type) == "ryukyoku":
                dealer_continues = False

        if dealer_continues:
            honba += 1
        else:
            current_round_idx += 1
            honba = 0

    # 進行中の局のリーチ宣言を反映
    for p in st.session_state.get("riichi_declared", []):
        if p in scores:
            scores[p] -= 1000
            riichi_stick += 1

    st.session_state.scores = scores
    st.session_state.riichi_stick = riichi_stick
    st.session_state.honba = honba
    st.session_state.round_idx = current_round_idx
    autosave_draft()



def record_round(winner, loser, win_type, score, tenpai=None):
    st.session_state.round_history.append({
        "kyoku_name": get_round_name(),
        "winner": winner or "",
        "loser": loser or "",
        "win_type": win_type,
        "score": score,
        "riichi": list(st.session_state.riichi_declared),
        "furo": list(st.session_state.furo_declared),
        "tenpai": tenpai or [],
    })


def declare_riichi(player):
    save_snapshot()
    if player not in st.session_state.riichi_declared:
        st.session_state.riichi_declared.append(player)
    recalculate_state()





def apply_win(winner, win_type, points_data, loser=None):
    save_snapshot()
    record_round(winner, loser, win_type, points_data.get("total", 0))
    st.session_state.riichi_declared = []
    st.session_state.furo_declared = []
    st.session_state.input_mode = "normal"
    recalculate_state()


def check_game_end():
    """ルールに基づいてゲームが終了条件を満たしているかチェックし、終了理由を返す。満たしていない場合はNone"""
    scores = st.session_state.scores
    round_idx = st.session_state.round_idx
    rule_config = st.session_state.get("current_rule_config", {})
    detail = rule_config.get("detail", {})
    
    # トビ判定
    tobi_end = detail.get("tobi_end", "under_zero")
    if tobi_end == "under_zero":
        for p, s in scores.items():
            if s < 0:
                return f"飛び終了（{p} が0点未満）"
    elif tobi_end == "zero_or_less":
        for p, s in scores.items():
            if s <= 0:
                return f"飛び終了（{p} が0点以下）"
                
    # トップの点数とプレイヤー
    top_score = max(scores.values())
    top_players = [p for p, s in scores.items() if s == top_score]
    
    west_ext = detail.get("west_extension", "under_30000")
    b_cfg = rule_config.get("basic", {})
    ret_score = b_cfg.get("return_score", 30000)
    
    # アガリやめ・テンパイやめの判定
    if round_idx >= 7: # 南4局以降
        dealer = st.session_state.players[round_idx % 4]
        # 終了に必要なスコアを満たしているか (西入なしなら常に満たす)
        if top_score >= ret_score or (west_ext in ["none", "fixed_nan4"]):
            if dealer in top_players:
                if st.session_state.round_history:
                    last_round = st.session_state.round_history[-1]
                    # kyoku_nameから現在の局と同じか確認 (連荘による同じ局名か)
                    if last_round["kyoku_name"] == get_round_name(round_idx):
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
        if round_idx >= 8:
            return "南4局終了"
    else: # under_return_score (legacy name under_30000)
        if top_score >= ret_score:
            if round_idx == 8 and len([r for r in st.session_state.round_history if r["kyoku_name"].startswith("西")]) == 0:
                return f"南4局終了（トップ {top_score:,}点）"
            elif round_idx >= 8:
                return f"サドンデス終了（トップ {top_score:,}点）"
        elif round_idx >= 12:
            return "西4局終了（北入りなし）"
            
    return None


def apply_ryukyoku(tenpai_players):
    save_snapshot()
    record_round(None, None, "ryukyoku", 0, tenpai=tenpai_players)
    st.session_state.riichi_declared = []
    st.session_state.furo_declared = []
    st.session_state.input_mode = "normal"
    recalculate_state()


def apply_mid_ryukyoku(ryukyoku_type, tenpai_players=None):
    save_snapshot()
    st.session_state.round_history.append({
        "kyoku_name": get_round_name(),
        "winner": "",
        "loser": "",
        "win_type": "mid_ryukyoku",
        "score": 0,
        "ryukyoku_type": ryukyoku_type,
        "riichi": list(st.session_state.riichi_declared),
        "furo": list(st.session_state.furo_declared),
        "tenpai": tenpai_players or [],
    })
    
    st.session_state.riichi_declared = []
    st.session_state.furo_declared = []
    st.session_state.input_mode = "normal"
    recalculate_state()


def apply_multi_win(wins_data, loser):
    save_snapshot()
    players = st.session_state.players
    loser_idx = players.index(loser) if loser in players else 0
    def distance(p):
        idx = players.index(p) if p in players else 0
        return (idx - loser_idx) % 4
        
    closest_winner = min([wd["winner"] for wd in wins_data], key=distance) if wins_data else ""
        
    st.session_state.round_history.append({
        "kyoku_name": get_round_name(),
        "winner": closest_winner,
        "loser": loser,
        "win_type": "multi_ron",
        "score": 0,
        "multi_wins": wins_data,
        "riichi": list(st.session_state.riichi_declared),
        "furo": list(st.session_state.furo_declared),
        "tenpai": [],
    })
    
    st.session_state.riichi_declared = []
    st.session_state.furo_declared = []
    st.session_state.input_mode = "normal"
    recalculate_state()



def apply_chombo(player):
    save_snapshot()
    record_round(player, None, "chombo", 0)
    st.session_state.riichi_declared = []
    st.session_state.furo_declared = []
    st.session_state.input_mode = "normal"
    recalculate_state()


def autosave_draft():
    if not st.session_state.get("game_active"):
        return
    state = {
        "view": st.session_state.get("view", "setup"),
        "game_active": True,
        "players": list(st.session_state.get("players", [])),
        "scores": dict(st.session_state.get("scores", {})),
        "round_idx": st.session_state.get("round_idx", 0),
        "honba": st.session_state.get("honba", 0),
        "riichi_stick": st.session_state.get("riichi_stick", 0),
        "riichi_declared": list(st.session_state.get("riichi_declared", [])),
        "furo_declared": list(st.session_state.get("furo_declared", [])),
        "round_history": list(st.session_state.get("round_history", [])),
        "undo_stack": list(st.session_state.get("undo_stack", [])[-3:]),
        "game_mode": st.session_state.get("game_mode", "detail"),
        "input_mode": st.session_state.get("input_mode", "normal"),
    }
    try:
        db.save_draft(state)
    except Exception as e:
        st.session_state["draft_save_error"] = str(e)


def reset_game():
    """対局データの完全一括リセット"""
    keys = [
        "game_active", "players", "scores", "round_idx", "honba",
        "riichi_stick", "riichi_declared", "furo_declared", "diff_target",
        "input_mode", "win_step", "win_data", "undo_stack", "round_history",
        "selected_players", "tenpai_selection", "confirm_endgame", "confirm_discard",
        "draft_save_error", "draft_data", "draft_time",
    ]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.view = "setup"
    db.delete_draft()


