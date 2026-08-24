import streamlit as st
import database2 as db



def _set_view(v):
    import streamlit as st
    st.session_state.view = v

def _resume_draft(draft):
    import streamlit as st
    for k, v in draft.items():
        st.session_state[k] = v
    st.session_state["draft_data"] = None
    st.session_state["draft_time"] = None

def _discard_draft():
    import streamlit as st
    import database2 as db
    db.delete_draft()
    st.session_state["draft_data"] = None
    st.session_state["draft_time"] = None

def show_home():

    # ホーム画面用のカスタムCSS（太字のみ指定）
    st.markdown("""
    <style>
    div.stButton > button p {
        font-weight: 700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ドラフト（中断中の対局）がある場合の再開・破棄案内
    draft = st.session_state.get("draft_data")
    if draft and draft.get("game_active") and draft.get("game_mode") == "detail":
        draft_time = st.session_state.get("draft_time")
        time_str = draft_time.strftime("%m/%d %H:%M") if draft_time else "不明"
        st.warning(f"{time_str} の対局が中断されています。再開しますか？")
        
        st.button("再開する", type="primary", use_container_width=True, key="home_draft_resume", on_click=_resume_draft, args=(draft,))
            
        st.write("")
        
        st.button("破棄する", use_container_width=True, key="home_draft_discard", on_click=_discard_draft)
            
        st.divider()

    st.title("麻雀スコア")
    st.caption("ホーム画面")
    st.divider()

    # メインボタン: 対局を始める
    st.button("対局を始める", type="primary", use_container_width=True, key="home_start_game", on_click=_set_view, args=("setup",))

    st.write("")

    # 成績を見る
    st.button("成績を見る", use_container_width=True, key="home_view_stats", on_click=_set_view, args=("stats",))

    st.write("")

    # グループ管理
    st.button("グループ管理", use_container_width=True, key="home_group_mgmt", on_click=_set_view, args=("group_manage",))

    st.write("")

    # ルール作成
    st.button("ルール作成", use_container_width=True, key="home_rule_mgmt", on_click=_set_view, args=("rule_manage",))

    st.write("")

    # データ管理
    st.button("データ管理", use_container_width=True, key="home_data_manage", on_click=_set_view, args=("data_manage",))
