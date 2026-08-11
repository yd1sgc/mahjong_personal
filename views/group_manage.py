import uuid
import streamlit as st
import database2 as db
from constants import MEMBERS


def show_group_manage():
    c_h1, c_h2 = st.columns([1, 3])
    with c_h1:
        if st.button("🏠 ホーム", use_container_width=True, key="grp_back_home"):
            st.session_state.view = "home"
            st.rerun()
    with c_h2:
        st.markdown("### 👥 メンバーグループ管理")

    st.caption("よく一緒に打つメンバーやルールをグループとして登録・管理できます。")
    st.divider()

    groups = db.get_groups()
    rules = db.get_rules()
    rule_map = {r["rule_id"]: r["rule_name"] for r in rules}

    if "editing_group_id" not in st.session_state:
        st.session_state.editing_group_id = None

    # ── 1. 登録済みグループ一覧 ──────────────────────────────
    st.subheader("📋 登録済みグループ一覧")

    if not groups:
        st.info("登録されているグループはまだありません。下のフォームから作成してください。")
    else:
        for g in groups:
            g_id = g["group_id"]
            g_name = g["group_name"]
            r_id = g.get("default_rule_id", "m_league")
            r_name = rule_map.get(r_id, "標準ルール")
            members = g.get("members", [])
            mem_str = "、".join(members) if members else "メンバー未登録"

            with st.container():
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**{g_name}** （{len(members)}名）")
                    st.caption(f"標準ルール: {r_name} | メンバー: {mem_str}")
                with c2:
                    cb1, cb2 = st.columns(2)
                    with cb1:
                        if st.button("編集", key=f"grp_edit_{g_id}", use_container_width=True):
                            st.session_state.editing_group_id = g_id
                            st.rerun()
                    with cb2:
                        if st.button("削除", key=f"grp_del_{g_id}", use_container_width=True):
                            db.delete_group(g_id)
                            if st.session_state.editing_group_id == g_id:
                                st.session_state.editing_group_id = None
                            st.rerun()

            st.divider()

    # ── 2. グループ作成 / 編集フォーム ───────────────────────
    target_group = None
    if st.session_state.editing_group_id:
        target_group = next((g for g in groups if g["group_id"] == st.session_state.editing_group_id), None)

    is_edit = target_group is not None
    form_title = f"✏️ グループ編集: {target_group['group_name']}" if is_edit else "➕ 新規グループ作成"
    st.subheader(form_title)

    default_gname = target_group["group_name"] if is_edit else ""
    default_rid = target_group.get("default_rule_id", "m_league") if is_edit else (rules[0]["rule_id"] if rules else "m_league")
    default_mems = set(target_group["members"]) if is_edit else set()

    gname_in = st.text_input("グループ名", value=default_gname, placeholder="例: 金曜麻雀部、会社仲間など", key="gf_name")

    # デフォルトルール選択
    rule_options = [r["rule_id"] for r in rules]
    def_idx = rule_options.index(default_rid) if default_rid in rule_options else 0
    rule_sel = st.selectbox(
        "このグループの標準ルール",
        options=rule_options,
        index=def_idx,
        format_func=lambda rid: rule_map.get(rid, rid),
        key="gf_rule"
    )

    st.markdown("**所属メンバーの選択**")
    # 定義済みメンバーリスト ＋ 既存の追加メンバー
    all_known_members = sorted(list(set(MEMBERS) | default_mems))

    selected_members = []
    m_cols = st.columns(2)
    for i, m in enumerate(all_known_members):
        with m_cols[i % 2]:
            checked = st.checkbox(m, value=(m in default_mems), key=f"gf_mem_{m}")
            if checked:
                selected_members.append(m)

    # メンバー手動追加
    new_mem = st.text_input("新規メンバーを追加", placeholder="登録されていない新しいメンバー名を入力", key="gf_add_mem")
    if new_mem and new_mem.strip() not in selected_members:
        selected_members.append(new_mem.strip())

    st.write("")

    cs1, cs2 = st.columns(2)
    with cs1:
        if st.button("保存する", type="primary", use_container_width=True, key="gf_save"):
            if not gname_in.strip():
                st.error("グループ名を入力してください")
            else:
                g_id = target_group["group_id"] if is_edit else f"group_{uuid.uuid4().hex[:8]}"
                db.save_group(g_id, gname_in.strip(), rule_sel, selected_members)
                st.session_state.editing_group_id = None
                st.success(f"グループ「{gname_in}」を保存しました")
                st.rerun()
    with cs2:
        if is_edit:
            if st.button("編集キャンセル", use_container_width=True, key="gf_cancel"):
                st.session_state.editing_group_id = None
                st.rerun()
