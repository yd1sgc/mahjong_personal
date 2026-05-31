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
    color: rgba(255,255,255,0.65) !important;
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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()
db.init_db()


# ── ゲームロジック ────────────────────────────────────────

def get_round_name(idx=None):
    i = idx if idx is not None else st.session_state.round_idx
    wind = ["東", "南", "西", "北"][i // 4]
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

    if len(selected) == 4:
        if st.button("対局スタート", type="primary", use_container_width=True):
            st.session_state.players = list(selected)
            st.session_state.scores = {p: INIT_SCORE for p in selected}
            st.session_state.game_active = True
            st.session_state.selected_players = []
            st.rerun()
    else:
        st.button("対局スタート", type="primary", use_container_width=True,
                  disabled=True)

    if st.button("成績を見る", use_container_width=True):
        st.session_state.view = "stats"
        st.rerun()


# ── 画面: 対局中メイン ────────────────────────────────────

def show_game():
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

    c3, c4 = st.columns(2)
    with c3:
        if st.button("局を修正", use_container_width=True):
            st.session_state.input_mode = "edit_history"
            st.rerun()
    with c4:
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

    type_label = {"ron": "ロン", "tsumo": "ツモ", "ryukyoku": "流局"}
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
                "種別", options=["ロン", "ツモ", "流局"], width="small"
            ),
            "点数": st.column_config.NumberColumn("点数", min_value=0, step=100),
        },
        hide_index=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("保存", type="primary", use_container_width=True):
            rev = {"ロン": "ron", "ツモ": "tsumo", "流局": "ryukyoku"}
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
    scores = st.session_state.scores
    sorted_p = sorted(players, key=lambda p: scores[p], reverse=True)

    st.subheader("最終結果")
    for i, p in enumerate(sorted_p):
        pt = calc.calc_special_point(scores[p], i + 1)
        st.write(f"{i + 1}位: **{p}**　{scores[p]:,}点　({pt:+.1f}pt)")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("記録して終了", type="primary", use_container_width=True):
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            game_id = db.save_game(date_str, scores, players)
            for r in st.session_state.round_history:
                db.save_round(game_id, r["kyoku_name"], r["winner"], r["loser"],
                              r["score"], r["furo"], r["riichi"])
            st.success("記録しました！")
            reset_game()
            st.rerun()
    with c2:
        if st.button("記録せず終了", use_container_width=True):
            reset_game()
            st.rerun()

    if st.button("戻る（対局続行）", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.rerun()


# ── 画面: 成績 ────────────────────────────────────────────

def show_stats():
    st.title("成績")
    df_games = db.get_games_data()
    df_rounds = db.get_rounds_data()

    if df_games.empty:
        st.info("記録がまだありません。対局を終局・記録すると反映されます。")
    else:
        df_stats = calc.analyze_stats(df_games, df_rounds)
        if not df_stats.empty:
            show_cols = [c for c in [
                "名前", "試合数", "平均順位", "総合pt",
                "和了率", "放銃率", "リーチ率", "副露率", "連対率",
            ] if c in df_stats.columns]
            st.dataframe(
                df_stats[show_cols].sort_values("総合pt", ascending=False),
                use_container_width=True,
            )

        st.subheader("対局履歴")
        st.dataframe(df_games.head(20), use_container_width=True)

    if st.button("戻る", use_container_width=True):
        st.session_state.view = "setup"
        st.rerun()


# ── ルーター ──────────────────────────────────────────────

view = st.session_state.view
mode = st.session_state.input_mode

if view == "stats":
    show_stats()
elif not st.session_state.game_active:
    show_setup()
elif mode == "win":
    show_win_input()
elif mode == "ryukyoku":
    show_ryukyoku_input()
elif mode == "edit_history":
    show_edit_history()
elif mode == "endgame":
    show_endgame()
else:
    show_game()
