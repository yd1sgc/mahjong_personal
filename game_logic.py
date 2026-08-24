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
        "scores": dict(st.session_state.scores),
        "round_idx": st.session_state.round_idx,
        "honba": st.session_state.honba,
        "riichi_stick": st.session_state.riichi_stick,
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
    st.session_state.scores = snap["scores"]
    st.session_state.round_idx = snap["round_idx"]
    st.session_state.honba = snap["honba"]
    st.session_state.riichi_stick = snap["riichi_stick"]
    st.session_state.riichi_declared = snap["riichi_declared"]
    st.session_state.furo_declared = snap["furo_declared"]
    st.session_state.round_history = snap["round_history"]
    st.session_state.diff_target = None
    autosave_draft()
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


def recalculate_from_history():
    players = st.session_state.players
    if not players:
        return
    scores = {p: 25000 for p in players}
    riichi_stick = 0
    honba = 0

    for r in st.session_state.round_history:
        k_idx = _parse_kyoku_idx(r.get("kyoku_name", ""))
        dealer = players[k_idx % 4]

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

        if win_type == "ron":
            total = score + honba * 300
            if loser in scores:
                scores[loser] -= total
            if winner in scores:
                scores[winner] += total + riichi_stick * 1000
            riichi_stick = 0
            if winner == dealer:
                honba += 1
            else:
                honba = 0

        elif win_type == "tsumo":
            if winner == dealer:
                each = (score // 3) + honba * 100
                for p in players:
                    if p != winner:
                        scores[p] -= each
                        scores[winner] += each
                scores[winner] += riichi_stick * 1000
                honba += 1
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
                honba = 0
            riichi_stick = 0

        elif win_type == "ryukyoku":
            tenpai = r.get("tenpai", [])
            noten = [p for p in players if p not in tenpai]
            n_t, n_n = len(tenpai), len(noten)
            if 0 < n_t < 4:
                each_noten = 3000 // n_n
                each_tenpai = 3000 // n_t
                for p in noten:
                    scores[p] -= each_noten
                for p in tenpai:
                    scores[p] += each_tenpai
            honba += 1

        elif win_type == "chombo":
            chombo_p = winner
            if chombo_p == dealer:
                for p in players:
                    if p != chombo_p:
                        scores[chombo_p] -= 4000
                        scores[p] += 4000
            else:
                for p in players:
                    if p == chombo_p:
                        continue
                    elif p == dealer:
                        scores[chombo_p] -= 4000
                        scores[p] += 4000
                    else:
                        scores[chombo_p] -= 2000
                        scores[p] += 2000

    st.session_state.scores = scores
    st.session_state.riichi_stick = riichi_stick
    st.session_state.honba = honba
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
    st.session_state.scores[player] -= 1000
    st.session_state.riichi_stick += 1
    if player not in st.session_state.riichi_declared:
        st.session_state.riichi_declared.append(player)
    autosave_draft()


def end_round(dealer_continues):
    if dealer_continues:
        st.session_state.honba += 1
    else:
        st.session_state.round_idx += 1
        st.session_state.honba = 0
    st.session_state.riichi_declared = []
    st.session_state.furo_declared = []
    st.session_state.input_mode = "normal"


def apply_win(winner, win_type, points_data, loser=None):
    save_snapshot()
    scores = st.session_state.scores
    players = st.session_state.players
    honba = st.session_state.honba
    is_dealer = (winner == get_dealer())

    if win_type == "ron":
        total = points_data["total"] + honba * 300
        scores[loser] -= total
        scores[winner] += total + st.session_state.riichi_stick * 1000
    else:
        if is_dealer:
            each = points_data["each_pays"] + honba * 100
            for p in players:
                if p != winner:
                    scores[p] -= each
                    scores[winner] += each
        else:
            ko_pay = points_data["ko_pays"] + honba * 100
            oya_pay = points_data["oya_pays"] + honba * 100
            dealer = get_dealer()
            for p in players:
                if p == winner:
                    continue
                pay = oya_pay if p == dealer else ko_pay
                scores[p] -= pay
                scores[winner] += pay
        scores[winner] += st.session_state.riichi_stick * 1000

    record_round(winner, loser, win_type, points_data.get("total", 0))
    st.session_state.riichi_stick = 0
    end_round(dealer_continues=is_dealer)
    autosave_draft()


def apply_ryukyoku(tenpai_players):
    save_snapshot()
    scores = st.session_state.scores
    players = st.session_state.players
    noten = [p for p in players if p not in tenpai_players]
    n_t, n_n = len(tenpai_players), len(noten)

    if 0 < n_t < 4:
        each_noten_pay = 3000 // n_n
        each_tenpai_get = 3000 // n_t
        for p in noten:
            scores[p] -= each_noten_pay
        for p in tenpai_players:
            scores[p] += each_tenpai_get

    record_round(None, None, "ryukyoku", 0, tenpai=tenpai_players)
    dealer = get_dealer()
    st.session_state.honba += 1
    if dealer not in tenpai_players:
        st.session_state.round_idx += 1
    st.session_state.riichi_declared = []
    st.session_state.furo_declared = []
    st.session_state.input_mode = "normal"
    autosave_draft()


def apply_chombo(player):
    save_snapshot()
    players = st.session_state.players
    scores = st.session_state.scores
    dealer = get_dealer()

    if player == dealer:
        for p in players:
            if p != player:
                scores[player] -= 4000
                scores[p] += 4000
    else:
        for p in players:
            if p == player:
                continue
            elif p == dealer:
                scores[player] -= 4000
                scores[p] += 4000
            else:
                scores[player] -= 2000
                scores[p] += 2000

    record_round(player, None, "chombo", 0)
    st.session_state.input_mode = "normal"
    autosave_draft()


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


from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class GameStateContainer:
    active: bool = False
    mode: str = "detail"
    players: List[str] = field(default_factory=list)
    scores: Dict[str, int] = field(default_factory=dict)
    round_idx: int = 0
    honba: int = 0
    riichi_stick: int = 0
    riichi_declared: List[str] = field(default_factory=list)
    furo_declared: List[str] = field(default_factory=list)
    round_history: List[Dict[str, Any]] = field(default_factory=list)
    undo_stack: List[Dict[str, Any]] = field(default_factory=list)
    input_mode: str = "normal"
    group_id: str = "all"
    rule_id: str = "m_league"
    rule_config: Dict[str, Any] = field(default_factory=dict)


def init_game_container():
    """対局コンテナの安全な1回限り初期化 (イベント衝突なし)"""
    if "game_container" not in st.session_state:
        st.session_state.game_container = GameStateContainer()


def reset_game():
    """対局データの完全一括リセット"""
    st.session_state.game_container = GameStateContainer()
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


