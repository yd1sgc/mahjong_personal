import streamlit as st
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
import database2 as db
from views.setup import show_setup, show_simple_input, show_result
from views.game import (show_game, show_win_input, show_ryukyoku_input,
                        show_chombo_input, show_edit_history, show_endgame)
from views.stats import show_stats
from views.data_manage import show_data_manage
from views.home import show_home
from views.rule_manage import show_rule_manage
from views.group_manage import show_group_manage

st.set_page_config(
    page_title="麻雀スコア",
    page_icon="",
    layout="centered",
    initial_sidebar_state="collapsed",
)

is_local_mode = st.secrets.get("local_mode", False)
local_db_path = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db" if is_local_mode else None
try:
    remote_db_kwargs = dict(st.secrets["database"])
except KeyError:
    remote_db_kwargs = None

db.init_config(
    is_local=is_local_mode,
    sqlite_path=local_db_path,
    remote_db_kwargs=remote_db_kwargs
)

st.markdown("""
<style>
.stButton > button {
    min-height: 48px;
    font-size: 18px !important;
    font-weight: 700 !important;
    border-radius: 10px;
    padding: 6px 4px !important;
}
.stButton > button p {
    font-size: 18px !important;
    font-weight: 700 !important;
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
    margin-top: 0.15rem !important;
    margin-bottom: 0.15rem !important;
}
/* スマホ: パディング削減 */
@media (max-width: 640px) {
    .block-container {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    [data-testid="stHorizontalBlock"],
    [data-testid="stColumns"] {
        gap: 0.15rem !important;
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
/* 対局画面の水平ブロック・要素間のみ縦ギャップを極小化 */
[data-testid="stHorizontalBlock"] {
    margin-bottom: 0.15rem !important;
}
[data-testid="stHorizontalBlock"] [data-testid="stElementContainer"] {
    margin-bottom: 0 !important;
}
/* 単体縦並びボタン（和了者・放銃者・流局などの選択画面）は押しやすい間隔を保持 */
.main [data-testid="stElementContainer"]:has(> .stButton) {
    margin-bottom: 0.5rem;
}
[data-testid="stHorizontalBlock"] [data-testid="stElementContainer"]:has(> .stButton) {
    margin-bottom: 0 !important;
}
/* プレイヤー列ボタン（3列行の1列目）: 名前・点数を2行スタイル */
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
  [data-testid="stColumn"]:first-child .stButton > button p {
    margin: 0 !important;
    line-height: 1.25;
}
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
  [data-testid="stColumn"]:first-child .stButton > button p:first-child:not(:last-child) {
    font-size: 15px !important;
    font-weight: 700 !important;
    color: inherit !important;
    opacity: 0.95;
}
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
  [data-testid="stColumn"]:first-child .stButton > button p:last-child:not(:first-child) {
    font-size: 22px !important;
    font-weight: 800 !important;
}
</style>
""", unsafe_allow_html=True)


# ── 初期化 ────────────────────────────────────────────────

def init_session():
    defaults = {
        "view": "home" if is_local_mode else "stats",
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
    if is_local_mode:
        db.init_local_db()
    else:
        db.init_db()
    st.session_state["db_initialized"] = True

if is_local_mode and "online" not in st.session_state:
    st.session_state["online"] = db.check_connectivity()
if not is_local_mode:
    st.session_state["online"] = True

if "draft_data" not in st.session_state:
    draft_state, draft_time = db.load_draft()
    st.session_state["draft_data"] = draft_state
    st.session_state["draft_time"] = draft_time
    if draft_state and draft_state.get("game_active"):
        for k, v in draft_state.items():
            st.session_state[k] = v



# ── 認証 ───────────────────────────────────────────────────

def check_auth():
    if is_local_mode or st.session_state.get("authed"):
        return True
    st.title("麻雀スコア")
    pw = st.text_input("パスワード", type="password")
    if pw:
        if pw == st.secrets.get("app_password"):
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


import game_logic

# ── 安全な対局状態コンテナの1回初期化 ──────────────────────────
game_logic.init_game_container()

# ── ルーター ──────────────────────────────────────────────

view = st.session_state.view
mode = st.session_state.input_mode

if view == "stats":
    show_stats()
elif not check_auth():
    pass
elif view == "home":
    show_home()
elif view == "setup":
    show_setup()
elif view == "group_manage":
    show_group_manage()
elif view == "rule_manage":
    show_rule_manage()
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
