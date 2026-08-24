import streamlit as st
import database2 as db


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
        
        if st.button("再開する", type="primary", use_container_width=True, key="home_draft_resume"):
            for k, v in draft.items():
                st.session_state[k] = v
            st.session_state["draft_data"] = None
            st.session_state["draft_time"] = None
            st.rerun()
            
        st.write("")
        
        if st.button("破棄する", use_container_width=True, key="home_draft_discard"):
            db.delete_draft()
            st.session_state["draft_data"] = None
            st.session_state["draft_time"] = None
            st.rerun()
            
        st.divider()

    st.title("麻雀スコア")
    st.caption("ホーム画面")
    st.divider()

    # メインボタン: 対局を始める
    if st.button("対局を始める", type="primary", use_container_width=True, key="home_start_game"):
        st.session_state.view = "setup"
        st.rerun()

    st.write("")

    # 成績を見る
    if st.button("成績を見る", use_container_width=True, key="home_view_stats"):
        st.session_state.view = "stats"
        st.rerun()

    st.write("")

    # グループ管理
    if st.button("グループ管理", use_container_width=True, key="home_group_mgmt"):
        st.session_state.view = "group_manage"
        st.rerun()

    st.write("")

    # ルール作成
    if st.button("ルール作成", use_container_width=True, key="home_rule_mgmt"):
        st.session_state.view = "rule_manage"
        st.rerun()

    st.write("")

    # データ管理
    if st.button("データ管理", use_container_width=True, key="home_data_manage"):
        st.session_state.view = "data_manage"
        st.rerun()
