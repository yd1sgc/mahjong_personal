import streamlit as st
import database2 as db
from views.setup import show_setup, show_simple_input, show_result
from views.game import (show_game, show_win_input, show_ryukyoku_input,
                        show_chombo_input, show_edit_history, show_endgame)
from views.stats import show_stats
from views.data_manage import show_data_manage

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
/* トップパディング削減 */
.block-container {
    padding-top: 2.5rem !important;
}
/* divider の余白削減 */
hr {
    margin-top: 0.5rem !important;
    margin-bottom: 0.5rem !important;
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


# ── 初期化 ────────────────────────────────────────────────

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
        "confirm_endgame": False,
        "confirm_discard": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session()

if "db_initialized" not in st.session_state:
    db.init_db()
    if db.IS_LOCAL:
        db.init_local_db()
    st.session_state["db_initialized"] = True

if db.IS_LOCAL and "online" not in st.session_state:
    db.check_connectivity()
if not db.IS_LOCAL:
    st.session_state["online"] = True

if "draft_data" not in st.session_state:
    draft_state, draft_time = db.load_draft()
    st.session_state["draft_data"] = draft_state
    st.session_state["draft_time"] = draft_time


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
