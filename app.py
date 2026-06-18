import streamlit as st
import database2 as db
import calc
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="麻雀スコア",
    page_icon="🀄",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stButton > button {
    min-height: 44px;
    font-size: 16px;
    font-weight: bold;
    border-radius: 10px;
}
/* 列コンテナ: 折り返しなし・ギャップ縮小 */
[data-testid="stHorizontalBlock"],
[data-testid="stColumns"] {
    flex-wrap: nowrap !important;
    align-items: stretch !important;
    gap: 0.5rem !important;
}
/* 列自体: 縮小可能 + flex列として縦に伸ばす */
[data-testid="column"],
[data-testid="stColumn"] {
    min-width: 0 !important;
    flex-shrink: 1 !important;
    display: flex !important;
    flex-direction: column !important;
}
/* stColumn直下のdiv（element-container）を縦いっぱいに */
[data-testid="stColumn"] > div,
[data-testid="column"] > div {
    flex: 1;
    display: flex !important;
    flex-direction: column !important;
    min-height: 0;
}
/* ボタンラッパーを縦いっぱいに */
[data-testid="stHorizontalBlock"] .stButton {
    flex: 1;
    display: flex !important;
    flex-direction: column !important;
}
/* ボタン本体を縦いっぱいに */
[data-testid="stHorizontalBlock"] .stButton > button {
    flex: 1 !important;
    min-height: 44px;
}
/* スマホ: パディング削減 */
@media (max-width: 640px) {
    .block-container {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    [data-testid="stHorizontalBlock"],
    [data-testid="stColumns"] {
        gap: 0.25rem !important;
    }
    [data-testid="column"],
    [data-testid="stColumn"] {
        min-width: 0 !important;
        flex-shrink: 1 !important;
    }
    /* 2列グリッドのみ均等幅に強制（3列以上は比率を維持） */
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(2):last-child) > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"]:has(> [data-testid="column"]:nth-child(2):last-child) > [data-testid="column"] {
        flex: 1 1 0% !important;
    }
}
/* プレイヤー列ボタン（3列行の1列目）: 名前・点数を2行スタイル */
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
  [data-testid="stColumn"]:first-child .stButton > button p {
    margin: 0 !important;
    line-height: 1.3;
}
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
  [data-testid="stColumn"]:first-child .stButton > button p:first-child {
    font-size: 13px !important;
    font-weight: normal !important;
    color: inherit !important;
    opacity: 0.6;
}
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
  [data-testid="stColumn"]:first-child .stButton > button p:last-child {
    font-size: 18px !important;
}
</style>
""", unsafe_allow_html=True)

# ── 定数 ──────────────────────────────────────────────────

MEMBERS = [
    "リョウト", "ユウダイ", "マサキ", "クノ", "オッチャン",
    "フルタ", "カツトシ", "ルイ", "シュン", "キド",
]
INIT_SCORE = 25000

KO_RON = [
    ("1000", 1000), ("1300", 1300), ("2000", 2000), ("2600", 2600),
    ("3900", 3900), ("5200", 5200), ("7700", 7700),
    ("満貫\n8000", 8000), ("跳満\n12000", 12000), ("倍満\n16000", 16000),
    ("三倍満\n24000", 24000), ("役満\n32000", 32000),
]
OYA_RON = [
    ("1500", 1500), ("2000", 2000), ("2900", 2900), ("3900", 3900),
    ("5800", 5800), ("7700", 7700), ("11600", 11600),
    ("満貫\n12000", 12000), ("跳満\n18000", 18000), ("倍満\n24000", 24000),
    ("三倍満\n36000", 36000), ("役満\n48000", 48000),
]
KO_TSUMO = [
    ("各300\n親500", 300, 500),
    ("各500\n親1000", 500, 1000),
    ("各700\n親1300", 700, 1300),
    ("各1000\n親2000", 1000, 2000),
    ("満貫\n各2000\n親4000", 2000, 4000),
    ("跳満\n各3000\n親6000", 3000, 6000),
    ("倍満\n各4000\n親8000", 4000, 8000),
    ("役満\n各8000\n親16000", 8000, 16000),
]
OYA_TSUMO = [
    ("各500", 500), ("各1000", 1000),
    ("各2000", 2000), ("各2900", 2900),
    ("満貫\n各4000", 4000), ("跳満\n各6000", 6000),
    ("倍満\n各8000", 8000), ("役満\n各16000", 16000),
]


# ── セッション初期化 ───────────────────────────────────────

def init_session():
    defaults = {
        "view": "setup",
        "game_active": False,
        "players": [],
        "scores": {},
        "round_idx": 0,
        "honba": 0,
        "riichi_stick": 0,
        "riichi_declared": [],
        "furo_declared": [],
        "diff_target": None,
        "input_mode": "normal",
        "win_step": 0,
        "win_data": {},
        "undo_stack": [],
        "round_history": [],
        "selected_players": [],
        "game_mode": "detail",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()
db.init_db()


# ── ゲームロジック ────────────────────────────────────────

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
    if len(st.session_state.undo_stack) > 20:
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
    return True

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

def apply_chombo(player):
    save_snapshot()
    players = st.session_state.players
    scores = st.session_state.scores
    dealer = get_dealer()

    if player == dealer:
        # 親チョンボ: 子3人に各4000点
        for p in players:
            if p != player:
                scores[player] -= 4000
                scores[p] += 4000
    else:
        # 子チョンボ: 親に4000点、他の子に各2000点
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


def reset_game():
    keys = [
        "game_active", "players", "scores", "round_idx", "honba",
        "riichi_stick", "riichi_declared", "furo_declared", "diff_target",
        "input_mode", "win_step", "win_data", "undo_stack", "round_history",
        "selected_players", "tenpai_selection",
    ]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.view = "setup"


# ── 画面: 対局設定 ────────────────────────────────────────

def show_setup():
    st.markdown("### 麻雀スコア")

    selected = st.session_state.selected_players
    wind_labels = ["東", "南", "西", "北"]

    # 選択済みプレイヤーを2行×2列で表示（タップで解除）
    for row in range(2):
        cols = st.columns(2)
        for col_idx in range(2):
            i = row * 2 + col_idx
            wind = wind_labels[i]
            with cols[col_idx]:
                if i < len(selected):
                    if st.button(f"{wind}: {selected[i]}", key=f"slot_{i}",
                                 type="primary", use_container_width=True):
                        selected.pop(i)
                        st.rerun()
                else:
                    st.button(f"{wind}: —", key=f"slot_{i}",
                              disabled=True, use_container_width=True)

    st.divider()

    # メンバー選択（2列グリッド）
    grid = st.columns(2)
    for i, m in enumerate(MEMBERS):
        with grid[i % 2]:
            is_sel = m in selected
            order = selected.index(m) + 1 if is_sel else None
            label = f"[{order}] {m}" if is_sel else m
            if st.button(label, key=f"sel_{m}",
                         type="primary" if is_sel else "secondary",
                         use_container_width=True):
                if is_sel:
                    selected.remove(m)
                elif len(selected) < 4:
                    selected.append(m)
                st.rerun()

    # ゲスト追加
    guest_name = st.text_input("ゲスト名", placeholder="ゲスト名を入力してEnter",
                               key="guest_input")
    if guest_name:
        if st.button("ゲストを追加",
                     disabled=(len(selected) >= 4 or guest_name in selected)):
            selected.append(guest_name)
            st.rerun()

    st.divider()

    ready = len(selected) == 4
    c1, c2 = st.columns(2)
    with c1:
        if st.button("詳細モード", type="primary",
                     disabled=not ready, use_container_width=True):
            st.session_state.players = list(selected)
            st.session_state.scores = {p: INIT_SCORE for p in selected}
            st.session_state.game_active = True
            st.session_state.game_mode = "detail"
            st.session_state.selected_players = []
            st.rerun()
    with c2:
        if st.button("結果のみ", disabled=not ready, use_container_width=True):
            st.session_state.players = list(selected)
            st.session_state.game_mode = "simple"
            st.session_state.selected_players = []
            st.session_state.view = "simple_input"
            st.rerun()

    c3, c4 = st.columns(2)
    with c3:
        if st.button("成績を見る", use_container_width=True):
            st.session_state.view = "stats"
            st.rerun()
    with c4:
        if st.button("データ管理", use_container_width=True):
            st.session_state.view = "data_manage"
            st.rerun()


# ── 画面: 結果のみ入力 ───────────────────────────────────

def show_simple_input():
    st.title("スコア入力")
    players = st.session_state.get("players", [])
    if not players:
        st.session_state.view = "setup"
        st.rerun()
        return

    st.caption("4人の合計が100,000点になるよう入力してください")

    scores = {}
    for p in players:
        scores[p] = st.number_input(p, value=0, step=100, key=f"simple_{p}")

    total = sum(scores.values())
    remainder = 100000 - total
    st.caption(f"合計: {total:,}点　　残り: {remainder:,}点")

    ok = (total == 100000)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("記録する", type="primary", disabled=not ok,
                     use_container_width=True):
            sorted_p = sorted(players, key=lambda p: scores[p], reverse=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            game_id = db.save_game(date_str, scores, players)
            result_rows = [
                {"rank": i + 1, "name": p, "score": scores[p],
                 "pt": calc.calc_special_point(scores[p], i + 1)}
                for i, p in enumerate(sorted_p)
            ]
            st.session_state.last_result = {
                "game_id": game_id, "date": date_str, "rows": result_rows
            }
            reset_game()
            st.session_state.view = "result"
            st.rerun()
    with c2:
        if st.button("キャンセル", use_container_width=True):
            st.session_state.view = "setup"
            st.rerun()


# ── 画面: 対局中メイン ────────────────────────────────────

def show_game():
    # ─ 終局・西入り判定 ──────────────────────────────────
    idx = st.session_state.round_idx
    top_score = max(st.session_state.scores.values())

    end_reason = None
    if idx >= 12:
        end_reason = "西4局終了（北入りなし）"
    elif idx >= 8 and top_score >= 30000:
        end_reason = f"トップ {top_score:,}点（30,000点以上）"

    if end_reason:
        st.info(f"終局条件：{end_reason}")
        if st.button("終局・記録する", type="primary", use_container_width=True):
            st.session_state.input_mode = "endgame"
            st.rerun()
        if st.button("↩ 元に戻す",
                     disabled=not st.session_state.undo_stack,
                     use_container_width=True):
            undo_last()
            st.rerun()
        return

    if idx == 8:
        st.warning(f"西入り　トップ {top_score:,}点（30,000点未満）")

    # ────────────────────────────────────────────────────
    players = st.session_state.players
    scores = st.session_state.scores
    diff_target = st.session_state.diff_target
    riichi_declared = st.session_state.riichi_declared
    furo_declared = st.session_state.furo_declared
    dealer = get_dealer()

    # ヘッダー（1行でコンパクトに）
    kyoku_str = f"{get_round_name()} {st.session_state.honba}本場"
    kyotaku_str = f"供託{st.session_state.riichi_stick}本"
    diff_text = f"{diff_target} 基準の点差表示中" if diff_target else "　"
    diff_color = "#888" if diff_target else "transparent"
    st.markdown(
        f"**{kyoku_str}**　{kyotaku_str}　親: {dealer}"
        f"<br><small style='color:{diff_color};'>{diff_text}</small>",
        unsafe_allow_html=True,
    )

    st.divider()

    # プレイヤーカード
    for p in players:
        score = scores[p]
        is_riichi = p in riichi_declared
        is_furo = p in furo_declared
        is_diff_base = (diff_target == p)
        in_diff_mode = bool(diff_target) and not is_diff_base

        tags = []
        if p == dealer:
            tags.append("★")
        if is_riichi:
            tags.append("立")
        tag_str = " ".join(tags)

        col_p, col_f, col_r = st.columns([4, 1, 1])

        with col_p:
            name_label = f"{tag_str + ' ' if tag_str else ''}{p}"
            if in_diff_mode:
                diff = score - scores[diff_target]
                sign = "+" if diff >= 0 else ""
                color_name = "blue" if diff >= 0 else "red"
                label = f"{name_label}\n\n:{color_name}[{sign}{diff:,}]"
                st.button(label, key=f"p_{p}", use_container_width=True)
            else:
                if st.button(f"{name_label}\n\n{score:,}", key=f"p_{p}", use_container_width=True):
                    st.session_state.diff_target = None if is_diff_base else p
                    st.rerun()

        # 副ボタン（リーチ中は押せない・2行で縦幅統一）
        with col_f:
            label_f = "副\n✓" if is_furo else "副\n　"
            if st.button(label_f, key=f"f_{p}",
                         type="primary" if is_furo else "secondary",
                         disabled=is_riichi,
                         use_container_width=True):
                if is_furo:
                    st.session_state.furo_declared.remove(p)
                else:
                    st.session_state.furo_declared.append(p)
                st.rerun()

        # 立ボタン（フウロ中・点数不足は押せない・リーチ中は赤く表示）
        with col_r:
            if is_riichi:
                # disabled外し → primary（赤）のまま表示。クリックしても何も起きない
                st.button("立\n✓", key=f"r_{p}", type="primary",
                          use_container_width=True)
            else:
                can_riichi = not is_furo
                if st.button("立\n　", key=f"r_{p}",
                             disabled=not can_riichi, use_container_width=True):
                    declare_riichi(p)
                    st.rerun()

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("和了", type="primary", use_container_width=True):
            st.session_state.input_mode = "win"
            st.session_state.win_step = 0
            st.session_state.win_data = {}
            st.rerun()
    with c2:
        if st.button("流局", use_container_width=True):
            st.session_state.input_mode = "ryukyoku"
            st.session_state.tenpai_selection = list(riichi_declared)
            st.rerun()

    c3, c4, c5 = st.columns(3)
    with c3:
        if st.button("チョンボ", use_container_width=True):
            st.session_state.input_mode = "chombo"
            st.rerun()
    with c4:
        if st.button("局を修正", use_container_width=True):
            st.session_state.input_mode = "edit_history"
            st.rerun()
    with c5:
        if st.button("↩ 元に戻す",
                     disabled=not st.session_state.undo_stack,
                     use_container_width=True):
            undo_last()
            st.rerun()

    st.divider()
    if st.button("終局・記録する", use_container_width=True):
        st.session_state.input_mode = "endgame"
        st.rerun()


# ── 画面: 和了入力 ────────────────────────────────────────

def show_win_input():
    players = st.session_state.players
    step = st.session_state.win_step
    data = st.session_state.win_data

    if step == 0:
        st.title("誰が和了？")
        for p in players:
            mark = "  ★" if p == get_dealer() else ""
            if st.button(f"{p}{mark}", key=f"w_{p}",
                         type="primary", use_container_width=True):
                data["winner"] = p
                data["is_dealer"] = (p == get_dealer())
                st.session_state.win_step = 1
                st.rerun()

    elif step == 1:
        st.title(f"{data['winner']}  ロン？ ツモ？")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("ロン", type="primary", use_container_width=True):
                data["win_type"] = "ron"
                st.session_state.win_step = 2
                st.rerun()
        with c2:
            if st.button("ツモ", type="primary", use_container_width=True):
                data["win_type"] = "tsumo"
                st.session_state.win_step = 2
                st.rerun()

    elif step == 2:
        st.title("点数は？")
        is_dealer = data["is_dealer"]
        win_type = data["win_type"]

        if win_type == "ron":
            presets = OYA_RON if is_dealer else KO_RON
            cols = st.columns(3)
            for i, (label, pts) in enumerate(presets):
                with cols[i % 3]:
                    if st.button(label, key=f"pts_{pts}", use_container_width=True):
                        data["points_data"] = {"total": pts}
                        st.session_state.win_step = 3
                        st.rerun()
        else:
            if is_dealer:
                presets = OYA_TSUMO
                cols = st.columns(2)
                for i, (label, each) in enumerate(presets):
                    with cols[i % 2]:
                        if st.button(label, key=f"pts_{each}", use_container_width=True):
                            apply_win(data["winner"], "tsumo",
                                      {"each_pays": each, "total": each * 3})
                            st.rerun()
            else:
                presets = KO_TSUMO
                cols = st.columns(2)
                for i, (label, ko_p, oya_p) in enumerate(presets):
                    with cols[i % 2]:
                        if st.button(label, key=f"pts_{ko_p}_{oya_p}", use_container_width=True):
                            apply_win(data["winner"], "tsumo",
                                      {"ko_pays": ko_p, "oya_pays": oya_p,
                                       "total": ko_p * 2 + oya_p})
                            st.rerun()

        with st.expander("翻・符で計算"):
            han = st.number_input("翻", min_value=1, max_value=13, value=3, key="han_in")
            fu = st.selectbox("符", [20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110],
                              index=2, key="fu_in")
            if st.button("この点数で使う", key="calc_apply"):
                total, oya_p, ko_p = calc.calculate_score(han, fu, is_dealer,
                                                           win_type == "tsumo")
                if win_type == "ron":
                    data["points_data"] = {"total": total}
                    st.session_state.win_step = 3
                else:
                    if is_dealer:
                        pd_ = {"each_pays": ko_p, "total": total}
                    else:
                        pd_ = {"ko_pays": ko_p, "oya_pays": oya_p, "total": total}
                    apply_win(data["winner"], "tsumo", pd_)
                st.rerun()

    elif step == 3:
        st.title("放銃者は？")
        winner = data["winner"]
        for p in players:
            if p != winner:
                if st.button(p, key=f"loser_{p}",
                             type="primary", use_container_width=True):
                    apply_win(winner, data["win_type"], data["points_data"], loser=p)
                    st.rerun()

    st.divider()
    if st.button("キャンセル", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.session_state.win_step = 0
        st.session_state.win_data = {}
        st.rerun()


# ── 画面: 流局入力 ────────────────────────────────────────

def show_ryukyoku_input():
    st.title("流局")
    players = st.session_state.players
    riichi_declared = st.session_state.riichi_declared
    tenpai_sel = st.session_state.tenpai_selection

    st.subheader("テンパイ / ノーテンを選択")

    for p in players:
        is_riichi = p in riichi_declared
        is_tenpai = p in tenpai_sel
        if is_riichi:
            st.button(f"{p}  テンパイ（リーチ）", disabled=True,
                      type="primary", use_container_width=True, key=f"ts_{p}")
        else:
            label = f"{p}  テンパイ" if is_tenpai else f"{p}  ノーテン"
            if st.button(label, key=f"ts_{p}",
                         type="primary" if is_tenpai else "secondary",
                         use_container_width=True):
                if is_tenpai:
                    tenpai_sel.remove(p)
                else:
                    tenpai_sel.append(p)
                st.rerun()

    n_t = len(tenpai_sel)
    n_n = 4 - n_t
    if 0 < n_t < 4:
        st.info(f"テンパイ {n_t}人: 各 +{3000 // n_t}点 / ノーテン {n_n}人: 各 -{3000 // n_n}点")
    else:
        st.info("点数移動なし（全員テンパイ または 全員ノーテン）")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("確定", type="primary", use_container_width=True):
            tenpai = list(tenpai_sel)
            del st.session_state["tenpai_selection"]
            apply_ryukyoku(tenpai)
            st.rerun()
    with c2:
        if st.button("キャンセル", use_container_width=True):
            del st.session_state["tenpai_selection"]
            st.session_state.input_mode = "normal"
            st.rerun()


# ── 画面: チョンボ ────────────────────────────────────────

def show_chombo_input():
    st.title("チョンボ")
    players = st.session_state.players
    dealer = get_dealer()

    st.subheader("チョンボしたプレイヤーを選択")
    for p in players:
        if p == dealer:
            label = f"★ {p}（親）　→ 子3人に各4,000点"
        else:
            label = f"{p}　→ 親に4,000点・子2人に各2,000点"
        if st.button(label, key=f"chombo_{p}", use_container_width=True):
            apply_chombo(p)
            st.rerun()

    if st.button("キャンセル", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.rerun()


# ── 画面: 局履歴修正 ──────────────────────────────────────

def show_edit_history():
    st.title("局履歴の修正")
    st.caption("記録内容の修正のみ。点数の変更は「元に戻す」を使用してください。")

    history = st.session_state.round_history
    if not history:
        st.info("まだ局の記録がありません。")
        if st.button("戻る", use_container_width=True):
            st.session_state.input_mode = "normal"
            st.rerun()
        return

    type_label = {"ron": "ロン", "tsumo": "ツモ", "ryukyoku": "流局", "chombo": "チョンボ"}
    rows = []
    for r in history:
        rows.append({
            "局": r["kyoku_name"],
            "種別": type_label.get(r["win_type"], r["win_type"]),
            "和了": r.get("winner", ""),
            "放銃": r.get("loser", ""),
            "点数": r.get("score", 0),
            "リーチ": ",".join(r.get("riichi", [])),
            "副露": ",".join(r.get("furo", [])),
            "テンパイ": ",".join(r.get("tenpai", [])),
        })

    edited = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "種別": st.column_config.SelectboxColumn(
                "種別", options=["ロン", "ツモ", "流局", "チョンボ"], width="small"
            ),
            "点数": st.column_config.NumberColumn("点数", min_value=0, step=100),
        },
        hide_index=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("保存", type="primary", use_container_width=True):
            rev = {"ロン": "ron", "ツモ": "tsumo", "流局": "ryukyoku", "チョンボ": "chombo"}
            new_history = []
            for _, row in edited.iterrows():
                wt = rev.get(str(row["種別"]), "ron")
                new_history.append({
                    "kyoku_name": str(row["局"]),
                    "winner": str(row["和了"]) if row["和了"] else "",
                    "loser": str(row["放銃"]) if row["放銃"] else "",
                    "win_type": wt,
                    "score": int(row["点数"]) if pd.notna(row["点数"]) else 0,
                    "riichi": [x.strip() for x in str(row["リーチ"]).split(",") if x.strip()],
                    "furo": [x.strip() for x in str(row["副露"]).split(",") if x.strip()],
                    "tenpai": [x.strip() for x in str(row["テンパイ"]).split(",") if x.strip()],
                })
            st.session_state.round_history = new_history
            st.session_state.input_mode = "normal"
            st.rerun()
    with c2:
        if st.button("キャンセル", use_container_width=True):
            st.session_state.input_mode = "normal"
            st.rerun()


# ── 画面: 終局 ────────────────────────────────────────────

def show_endgame():
    st.title("終局")
    players = st.session_state.players
    scores = dict(st.session_state.scores)

    riichi_bonus = st.session_state.riichi_stick * 1000
    if riichi_bonus > 0:
        top_p = max(players, key=lambda p: scores[p])
        scores[top_p] += riichi_bonus
        st.info(f"供託 {st.session_state.riichi_stick}本（{riichi_bonus:,}点）を {top_p} に加算します")

    sorted_p = sorted(players, key=lambda p: scores[p], reverse=True)

    st.subheader("最終結果")
    for i, p in enumerate(sorted_p):
        pt = calc.calc_special_point(scores[p], i + 1)
        st.write(f"{i + 1}位: **{p}**　{scores[p]:,}点　({pt:+.1f}pt)")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("記録して終了", type="primary", use_container_width=True):
            st.session_state.scores = scores
            st.session_state.riichi_stick = 0
            date_str = datetime.now().strftime("%Y-%m-%d")
            game_id = db.save_game(date_str, scores, players)
            for r in st.session_state.round_history:
                db.save_round(game_id, r["kyoku_name"], r["winner"], r["loser"],
                              r["score"], r["furo"], r["riichi"],
                              win_type=r.get("win_type", ""),
                              tenpai=r.get("tenpai", []))
            result_rows = [
                {"rank": i + 1, "name": p, "score": scores[p],
                 "pt": calc.calc_special_point(scores[p], i + 1)}
                for i, p in enumerate(sorted_p)
            ]
            st.session_state.last_result = {"game_id": game_id, "date": date_str, "rows": result_rows}
            reset_game()
            st.session_state.view = "result"
            st.rerun()
    with c2:
        if st.button("記録せず終了", use_container_width=True):
            reset_game()
            st.rerun()

    if st.button("戻る（対局続行）", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.rerun()


# ── 画面: 対局結果確認 ────────────────────────────────────

def show_result():
    result = st.session_state.get("last_result", {})
    st.title("対局結果")
    if result:
        st.caption(f"Game #{result['game_id']}　{result['date']}")
        st.divider()
        for row in result["rows"]:
            st.write(f"{row['rank']}位: **{row['name']}**　{row['score']:,}点　({row['pt']:+.1f}pt)")
    st.divider()
    if st.button("閉じる", type="primary", use_container_width=True):
        st.session_state.view = "setup"
        st.rerun()


# ── 画面: 成績 ────────────────────────────────────────────

def show_stats():
    st.title("成績")
    df_all = db.get_games_data()

    year_options = ["全期間"]
    if not df_all.empty and 'date' in df_all.columns:
        years = sorted(df_all['date'].dt.year.dropna().unique().astype(int), reverse=True)
        year_options += [str(y) for y in years]
    selected_year = st.selectbox("集計期間", year_options, key="stats_year")

    df_games = db.get_games_data(year_filter=selected_year)
    df_rounds = db.get_rounds_data()

    if df_games.empty:
        st.info("記録がまだありません。対局を終局・記録すると反映されます。")
        if st.button("戻る", use_container_width=True):
            st.session_state.view = "setup"
            st.rerun()
        return

    # 実際に参加しているメンバー一覧
    all_names = pd.unique(df_games[['p1_name','p2_name','p3_name','p4_name']].values.ravel('K'))
    real_members = sorted([p for p in all_names if pd.notna(p) and str(p).strip()])

    game_stats, round_stats, n_round_games = calc.analyze_stats(df_games, df_rounds)

    # ── 試合成績テーブル ──────────────────────────────────
    if not game_stats.empty:
        st.subheader("試合成績")
        game_cols = ["名前", "試合数", "総合pt", "平均順位",
                     "連対率", "ラス回避率", "1着率", "2着率", "3着率", "4着率"]
        show_cols = [c for c in game_cols if c in game_stats.columns]
        st.dataframe(
            game_stats[show_cols].sort_values("総合pt", ascending=False),
            use_container_width=True, hide_index=True,
        )

    # ── 詳細成績テーブル ──────────────────────────────────
    if not round_stats.empty:
        st.subheader(f"詳細成績（詳細記録 {n_round_games}試合を集計）")
        round_cols = ["名前", "和了率", "放銃率", "副露率", "リーチ率",
                      "リーチ成功率", "平均和了", "平均放銃"]
        show_cols = [c for c in round_cols if c in round_stats.columns]
        st.dataframe(
            round_stats[show_cols].sort_values("和了率", ascending=False),
            use_container_width=True, hide_index=True,
        )

    # ── 総合ポイント推移グラフ ────────────────────────────
    st.divider()
    st.subheader("総合ポイント推移")
    df_sorted = df_games.sort_values("game_id").reset_index(drop=True)
    cumulative_scores = {name: [0] for name in real_members}
    match_labels = ["G000"]
    for i, row in df_sorted.iterrows():
        match_labels.append(f"G{i+1:03}")
        game_pts = {
            row['p1_name']: calc.calc_special_point(row['p1_score'], row['p1_rank']),
            row['p2_name']: calc.calc_special_point(row['p2_score'], row['p2_rank']),
            row['p3_name']: calc.calc_special_point(row['p3_score'], row['p3_rank']),
            row['p4_name']: calc.calc_special_point(row['p4_score'], row['p4_rank']),
        }
        for name in real_members:
            cumulative_scores[name].append(cumulative_scores[name][-1] + game_pts.get(name, 0))
    df_chart = pd.DataFrame(cumulative_scores, index=match_labels)

    top5 = game_stats.sort_values("総合pt", ascending=False)['名前'].tolist()[:5] if not game_stats.empty else []
    default_sel = [m for m in top5 if m in real_members]
    selected = st.multiselect("表示メンバー", options=real_members,
                              default=default_sel, key="chart_sel")
    if selected:
        st.line_chart(df_chart[selected])

    # ── レコード ──────────────────────────────────────────
    st.divider()
    st.subheader("レコード")
    all_scores = []
    for _, row in df_sorted.iterrows():
        d = row['date']
        date_str = d.strftime('%Y-%m-%d') if pd.notna(d) else "日付不明"
        for i in range(1, 5):
            all_scores.append([row[f'p{i}_name'], int(row[f'p{i}_score']), date_str])
    df_scores_all = pd.DataFrame(all_scores, columns=['名前', '点数', '日付'])

    c1, c2 = st.columns(2)
    with c1:
        st.caption("最高スコア Top5")
        st.dataframe(df_scores_all.sort_values('点数', ascending=False).head(5).reset_index(drop=True),
                     hide_index=True, use_container_width=True)
        st.caption("最低スコア Top5")
        st.dataframe(df_scores_all.sort_values('点数').head(5).reset_index(drop=True),
                     hide_index=True, use_container_width=True)
    with c2:
        st.caption("連勝記録（2連勝以上）")
        streak_data = []
        for p in real_members:
            my_games = df_sorted[
                (df_sorted['p1_name']==p)|(df_sorted['p2_name']==p)|
                (df_sorted['p3_name']==p)|(df_sorted['p4_name']==p)
            ]
            max_streak = cur = 0
            for _, row in my_games.iterrows():
                rank = next((row[f'p{i}_rank'] for i in range(1,5) if row[f'p{i}_name']==p), 0)
                if rank == 1:
                    cur += 1
                    max_streak = max(max_streak, cur)
                else:
                    cur = 0
            if max_streak >= 2:
                streak_data.append({'名前': p, '最大連勝': max_streak})
        if streak_data:
            df_streak = pd.DataFrame(streak_data).sort_values('最大連勝', ascending=False).reset_index(drop=True)
            st.dataframe(df_streak, hide_index=True, use_container_width=True)
        else:
            st.info("2連勝以上の記録はまだありません")

    # ── 相性マトリクス ────────────────────────────────────
    st.divider()
    st.subheader("相性マトリクス（直接対決）")
    st.caption("行が自分、列が相手。数値は同卓時のpt差合計。赤=得意、青=苦手。")
    matrix_data = {p: {q: 0.0 for q in real_members} for p in real_members}
    for _, row in df_sorted.iterrows():
        p_res = {
            row['p1_name']: calc.calc_special_point(row['p1_score'], row['p1_rank']),
            row['p2_name']: calc.calc_special_point(row['p2_score'], row['p2_rank']),
            row['p3_name']: calc.calc_special_point(row['p3_score'], row['p3_rank']),
            row['p4_name']: calc.calc_special_point(row['p4_score'], row['p4_rank']),
        }
        players_in_game = [p for p in p_res if p in matrix_data]
        for p_me in players_in_game:
            for p_enemy in players_in_game:
                if p_me != p_enemy:
                    matrix_data[p_me][p_enemy] += p_res[p_me] - p_res[p_enemy]
    df_matrix = pd.DataFrame(matrix_data).T
    default_matrix = real_members[:5] if len(real_members) >= 5 else real_members
    target = st.multiselect("分析対象", options=real_members,
                            default=default_matrix, key="matrix_sel")
    if target:
        df_show_matrix = df_matrix.loc[target, target]
        st.dataframe(
            df_show_matrix.style.background_gradient(cmap='coolwarm_r', axis=None).format("{:+.1f}"),
            use_container_width=True,
        )

    # ── 対局履歴 ──────────────────────────────────────────
    st.divider()
    st.subheader("対局履歴")

    # 整形テーブル：順位順に並び替えて1行1試合で表示
    history_rows = []
    for _, row in df_games.sort_values("game_id", ascending=False).iterrows():
        players = sorted(
            [(row[f'p{i}_rank'], row[f'p{i}_name'], row[f'p{i}_score'],
              calc.calc_special_point(row[f'p{i}_score'], row[f'p{i}_rank']))
             for i in range(1, 5)],
            key=lambda x: x[0]
        )
        d = row['date']
        date_str = d.strftime('%Y-%m-%d') if pd.notna(d) else "日付不明"
        history_rows.append({
            "#": int(row['game_id']),
            "日付": date_str,
            "1位": f"{players[0][1]} ({players[0][3]:+.1f})",
            "2位": f"{players[1][1]} ({players[1][3]:+.1f})",
            "3位": f"{players[2][1]} ({players[2][3]:+.1f})",
            "4位": f"{players[3][1]} ({players[3][3]:+.1f})",
        })
    df_history = pd.DataFrame(history_rows)
    st.dataframe(df_history, use_container_width=True, hide_index=True)

    # ── 複数試合の合計集計 ────────────────────────────────
    st.divider()
    st.subheader("選択試合の合計集計")
    all_game_ids = df_games.sort_values("game_id", ascending=False)["game_id"].tolist()
    selected_ids = st.multiselect(
        "集計するゲームIDを選択",
        options=all_game_ids,
        format_func=lambda gid: f"#{int(gid)}  {df_history[df_history['#']==int(gid)]['日付'].values[0]}  {df_history[df_history['#']==int(gid)]['1位'].values[0]}",
        key="agg_game_ids",
    )
    if selected_ids:
        agg: dict = {}
        counts: dict = {}
        for _, row in df_games[df_games["game_id"].isin(selected_ids)].iterrows():
            for i in range(1, 5):
                name = row[f'p{i}_name']
                pt = calc.calc_special_point(row[f'p{i}_score'], row[f'p{i}_rank'])
                agg[name] = agg.get(name, 0.0) + pt
                counts[name] = counts.get(name, 0) + 1
        df_agg = pd.DataFrame([
            {"名前": name, "合計pt": f"{agg[name]:+.1f}", "参加試合数": counts[name]}
            for name in sorted(agg, key=lambda n: agg[n], reverse=True)
        ])
        st.caption(f"{len(selected_ids)}試合の合計")
        st.dataframe(df_agg, use_container_width=True, hide_index=True)

    if st.button("戻る", use_container_width=True):
        st.session_state.view = "setup"
        st.rerun()


# ── 画面: データ管理 ──────────────────────────────────────

def show_data_manage():
    st.title("データ管理")
    tab1, tab2, tab3 = st.tabs(["CSV取込", "スコア修正", "試合削除"])

    with tab1:
        st.subheader("CSVファイル取込")
        st.caption("形式: game_id, date, p1_name, p1_score, p2_name, p2_score, p3_name, p3_score, p4_name, p4_score（ヘッダーなし）")
        uploaded = st.file_uploader("CSVファイルを選択", type="csv", key="csv_upload")
        if uploaded:
            try:
                df = pd.read_csv(uploaded, header=None,
                                 names=["game_id", "date",
                                        "p1_name", "p1_score",
                                        "p2_name", "p2_score",
                                        "p3_name", "p3_score",
                                        "p4_name", "p4_score"])
                st.dataframe(df.head(10), use_container_width=True)
                st.caption(f"計 {len(df)}件（先頭10件表示）")
                if st.button("取込む", type="primary", use_container_width=True):
                    count = db.import_games_from_df(df)
                    st.success(f"{count}件を取込みました。")
                    st.rerun()
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

    with tab2:
        st.subheader("スコア修正")
        df_games = db.load_all_games()
        if df_games.empty:
            st.info("記録がありません。")
        else:
            def game_label(row):
                return f"#{int(row['game_id'])} {row['date']}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

            options = {int(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
            sel_id = st.selectbox("試合を選択", list(options.keys()),
                                  format_func=lambda x: options[x], key="edit_game_id")
            row = df_games[df_games['game_id'] == sel_id].iloc[0]
            new_scores = {}
            for i in range(1, 5):
                name = row[f'p{i}_name']
                new_scores[name] = st.number_input(
                    name, value=int(row[f'p{i}_score']), step=100, key=f"edit_score_{i}")
            total = sum(new_scores.values())
            ok = (total == 100000)
            st.caption(f"合計: {total:,}点")
            if st.button("保存", type="primary", disabled=not ok, use_container_width=True):
                db.update_game_scores(sel_id, new_scores)
                st.success("保存しました。")
                st.rerun()

    with tab3:
        st.subheader("試合削除")
        df_games = db.load_all_games()
        if df_games.empty:
            st.info("記録がありません。")
        else:
            def game_label(row):
                return f"#{int(row['game_id'])} {row['date']}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

            options = {int(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
            sel_id = st.selectbox("削除する試合を選択", list(options.keys()),
                                  format_func=lambda x: options[x], key="del_game_id")
            row = df_games[df_games['game_id'] == sel_id].iloc[0]
            for i in range(1, 5):
                rank = int(row.get(f'p{i}_rank', i))
                st.write(f"{rank}位: {row[f'p{i}_name']}  {int(row[f'p{i}_score']):,}点")
            confirmed = st.checkbox("削除を確認する", key="del_confirm")
            if st.button("この試合を削除", type="primary",
                         disabled=not confirmed, use_container_width=True):
                db.delete_game(int(sel_id))
                st.success(f"Game #{sel_id} を削除しました。")
                st.rerun()

    if st.button("戻る", use_container_width=True):
        st.session_state.view = "setup"
        st.rerun()


# ── ルーター ──────────────────────────────────────────────

view = st.session_state.view
mode = st.session_state.input_mode

if view == "stats":
    show_stats()
elif view == "result":
    show_result()
elif view == "data_manage":
    show_data_manage()
elif view == "simple_input":
    show_simple_input()
elif not st.session_state.game_active:
    show_setup()
elif mode == "win":
    show_win_input()
elif mode == "ryukyoku":
    show_ryukyoku_input()
elif mode == "chombo":
    show_chombo_input()
elif mode == "edit_history":
    show_edit_history()
elif mode == "endgame":
    show_endgame()
else:
    show_game()
