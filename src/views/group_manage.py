import cache_utils
import uuid
import streamlit as st
def _set_view(v):
    import streamlit as st
    st.session_state.view = v

import database2 as db


def show_group_manage():
    st.write("")
    st.write("")
    _, c_center, _ = st.columns([1, 2, 1])
    with c_center:
        st.button(" ホーム", use_container_width=True, key="grp_back_home", on_click=_set_view, args=("home",))

    st.caption("グループ管理")
    st.divider()

    groups = cache_utils.get_groups()
    rules = cache_utils.get_rule_templates()
    rule_map = {r["rule_id"]: r["rule_name"] for r in rules}
    all_members = cache_utils.get_all_members()

    if "editing_group_id" not in st.session_state:
        st.session_state.editing_group_id = None

    tab_new, tab_list = st.tabs([" 新規グループ作成", " 登録済みグループの編集・選択"])

    # ──────────────────────────────────────────────────────────
    # TAB 1: 新規グループ作成
    # ──────────────────────────────────────────────────────────
    with tab_new:
        next_gid_str = f"G{len(groups) + 1:02d}"
        gname_new = st.text_input(f"グループ名 (ID: {next_gid_str})", key="t1_gname")

        st.divider()

        # 新規メンバーその場登録
        c_m1, c_m2 = st.columns([3, 1])
        with c_m1:
            new_mname = st.text_input("新規メンバー登録", placeholder="新規メンバー名", label_visibility="collapsed", key="tab1_new_mname")
        with c_m2:
            if st.button("＋ メンバー追加", type="primary", use_container_width=True, key="tab1_add_mbtn"):
                if new_mname and new_mname.strip():
                    new_id = db.add_member(new_mname.strip())
                    st.cache_data.clear()
                    if new_id is not None:
                        st.success(f"メンバー「{new_mname.strip()}」をID登録しました")
                        st.rerun()
                    else:
                        st.error("メンバーの登録に失敗しました")
                else:
                    st.warning("名前を入力してください")

        selected_members_new = []
        m_cols1 = st.columns(2)
        for i, m in enumerate(all_members):
            m_label = f"#{m['member_id']:02d} {m['member_name']}"
            with m_cols1[i % 2]:
                if st.checkbox(m_label, key=f"t1_mem_{m['member_id']}"):
                    selected_members_new.append(m["member_id"])

        st.divider()

        
        col_r1, col_r2 = st.columns([3, 1])
        with col_r1:
            rule_options = [r["rule_id"] for r in rules]
            rule_sel_new = st.selectbox(
                "適用する標準ルール",
                options=rule_options,
                index=0,
                format_func=lambda rid: rule_map.get(rid, rid),
                key="t1_rule"
            )
        with col_r2:
            st.write("")
            st.write("")
            st.button(" ルール作成へ", use_container_width=True, key="t1_to_rule", on_click=_set_view, args=("rule_manage",))

        st.divider()

        
        cs1, cs2 = st.columns(2)
        with cs1:
            if st.button(" このグループで対局を開始する", type="primary", use_container_width=True, key="t1_save_play"):
                if not gname_new.strip():
                    st.error("グループ名を入力してください")
                else:
                    new_gid = f"group_{uuid.uuid4().hex[:8]}"
                    db.save_group(new_gid, gname_new.strip(), rule_sel_new, selected_members_new)
                    st.cache_data.clear()
                    st.session_state.selected_group_id = new_gid
                    st.session_state.active_rule_id = rule_sel_new
                    st.session_state.view = "setup"
                    st.rerun()
        with cs2:
            if st.button(" 保存のみ", use_container_width=True, key="t1_save_only"):
                if not gname_new.strip():
                    st.error("グループ名を入力してください")
                else:
                    new_gid = f"group_{uuid.uuid4().hex[:8]}"
                    db.save_group(new_gid, gname_new.strip(), rule_sel_new, selected_members_new)
                    st.cache_data.clear()
                    st.success(f"グループ「{gname_new}」を作成しました")
                    st.rerun()

    # ──────────────────────────────────────────────────────────
    # TAB 2: 登録済みグループの編集・選択
    # ──────────────────────────────────────────────────────────
    with tab_list:
        st.subheader(" 登録済みグループ一覧")

        if not groups:
            st.info("登録されているグループはありません。「 新規グループ作成」タブから作成してください。")
        else:
            for g in groups:
                g_id = g["group_id"]
                disp_gid = g.get("display_id", "G--")
                g_name = g["group_name"]
                r_id = g.get("default_rule_id", "m_league")
                r_name = rule_map.get(r_id, "標準ルール")
                members = g.get("members", [])
                mem_name_map = {m["member_id"]: m["member_name"] for m in all_members}
                mem_names = [mem_name_map[mid] for mid in members if mid in mem_name_map]
                mem_str = "、".join(mem_names) if mem_names else "メンバー未登録"

                with st.container():
                    c1, c2 = st.columns([3, 2])
                    with c1:
                        st.markdown(f"**[{disp_gid}] {g_name}** （{len(members)}名）")
                        st.caption(f"標準ルール: {r_name} | メンバー: {mem_str}")
                    with c2:
                        if st.button("編集", key=f"t2_edit_{g_id}", type="primary", use_container_width=True):
                            st.session_state.editing_group_id = g_id
                            st.rerun()

                st.divider()

        # 編集フォーム表示
        if st.session_state.editing_group_id:
            target_g = next((g for g in groups if g["group_id"] == st.session_state.editing_group_id), None)
            if target_g:
                t_dispid = target_g.get("display_id", "G--")
                st.markdown(f"---")
                gname_edit = st.text_input(f"グループ名 (ID: {t_dispid})", value=target_g["group_name"], key="t2_gname_edit")
                
                st.divider()
                cur_mems = set(target_g["members"])
                
                c_em1, c_em2 = st.columns([3, 1])
                with c_em1:
                    edit_new_mname = st.text_input("新規メンバー追加", placeholder="メンバー名入力", label_visibility="collapsed", key="t2_edit_new_mem")
                with c_em2:
                    if st.button("＋ メンバー追加", type="primary", use_container_width=True, key="t2_edit_add_mbtn"):
                        if edit_new_mname and edit_new_mname.strip():
                            new_id = db.add_member(edit_new_mname.strip())
                            st.cache_data.clear()
                            if new_id is not None:
                                cur_mems.add(new_id)
                                db.save_group(target_g["group_id"], target_g["group_name"], target_g.get("default_rule_id", "m_league"), list(cur_mems))
                                st.cache_data.clear()
                                st.rerun()

                selected_mems_edit = []
                m_cols2 = st.columns(2)
                for i, m in enumerate(all_members):
                    m_label = f"#{m['member_id']:02d} {m['member_name']}"
                    with m_cols2[i % 2]:
                        if st.checkbox(m_label, value=(m["member_id"] in cur_mems), key=f"t2_emem_{m['member_id']}"):
                            selected_mems_edit.append(m["member_id"])

                st.divider()

                
                col_er1, col_er2 = st.columns([3, 1])
                with col_er1:
                    rule_options = [r["rule_id"] for r in rules]
                    cur_r_id = target_g.get("default_rule_id", "m_league")
                    def_eidx = rule_options.index(cur_r_id) if cur_r_id in rule_options else 0
                    rule_sel_edit = st.selectbox("適用する標準ルール", options=rule_options, index=def_eidx, format_func=lambda rid: rule_map.get(rid, rid), key="t2_rule_edit")
                with col_er2:
                    st.write("")
                    st.write("")
                    st.button(" ルール作成へ", use_container_width=True, key="t2_to_rule", on_click=_set_view, args=("rule_manage",))

                st.divider()

                
                ce1, ce2, ce3 = st.columns([2, 2, 1])
                with ce1:
                    if st.button(" 変更保存して対局へ", type="primary", use_container_width=True, key="t2_save_play"):
                        if not gname_edit.strip():
                            st.error("グループ名を入力してください")
                        else:
                            db.save_group(target_g["group_id"], gname_edit.strip(), rule_sel_edit, selected_mems_edit)
                            st.cache_data.clear()
                            st.session_state.editing_group_id = None
                            st.session_state.selected_group_id = target_g["group_id"]
                            st.session_state.active_rule_id = rule_sel_edit
                            st.session_state.view = "setup"
                            st.rerun()
                with ce2:
                    if st.button("保存のみ", use_container_width=True, key="t2_save_only"):
                        if not gname_edit.strip():
                            st.error("グループ名を入力してください")
                        else:
                            db.save_group(target_g["group_id"], gname_edit.strip(), rule_sel_edit, selected_mems_edit)
                            st.cache_data.clear()
                            st.session_state.editing_group_id = None
                            st.success("グループ情報を更新しました")
                            st.rerun()
                with ce3:
                    if st.button("キャンセル", use_container_width=True, key="t2_cancel"):
                        st.session_state.editing_group_id = None
                        st.rerun()


