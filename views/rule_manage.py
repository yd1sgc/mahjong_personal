import uuid
import streamlit as st
import database2 as db


def show_rule_manage():
    c_h1, c_h2 = st.columns([1, 3])
    with c_h1:
        if st.button("🏠 ホーム", use_container_width=True, key="rule_back_home"):
            st.session_state.view = "home"
            st.rerun()
    with c_h2:
        st.markdown("### ⚙️ ルール作成・管理")

    st.caption("対局で適用するルール（持ち点・返し点・ウマなど）を登録・管理できます。")
    st.divider()

    rules = db.get_rules()

    # 編集対象のセッション管理
    if "editing_rule_id" not in st.session_state:
        st.session_state.editing_rule_id = None

    # ── 1. 登録済みルール一覧 ────────────────────────────────
    st.subheader("📋 登録済みルール一覧")

    for r in rules:
        r_id = r["rule_id"]
        r_name = r["rule_name"]
        is_def = r.get("is_default", 0)
        cfg = r.get("config", {})
        init_s = cfg.get("init_score", 25000)
        ret_s = cfg.get("return_score", 30000)
        uma = cfg.get("uma", [0, 0, 0, 0])
        uma_str = f"{uma[0]:+}, {uma[1]:+}, {uma[2]:+}, {uma[3]:+}"

        with st.container():
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                badge = " 🏆 【標準ルール】" if is_def else ""
                st.markdown(f"**{r_name}**{badge}")
                st.caption(f"{init_s:,}点持ち / {ret_s:,}点返し | ウマ: [{uma_str}]")
            with c2:
                if not is_def:
                    if st.button("標準に設定", key=f"set_def_{r_id}", use_container_width=True):
                        db.set_default_rule(r_id)
                        st.success(f"「{r_name}」を標準ルールに設定しました")
                        st.rerun()
            with c3:
                cb1, cb2 = st.columns(2)
                with cb1:
                    if st.button("編集", key=f"edit_{r_id}", use_container_width=True):
                        st.session_state.editing_rule_id = r_id
                        st.rerun()
                with cb2:
                    if not is_def and len(rules) > 1:
                        if st.button("削除", key=f"del_{r_id}", use_container_width=True):
                            db.delete_rule(r_id)
                            if st.session_state.editing_rule_id == r_id:
                                st.session_state.editing_rule_id = None
                            st.rerun()

        st.divider()

    # ── 2. ルール作成 / 編集フォーム ─────────────────────────
    target_rule = None
    if st.session_state.editing_rule_id:
        target_rule = next((r for r in rules if r["rule_id"] == st.session_state.editing_rule_id), None)

    is_edit = target_rule is not None
    form_title = f"✏️ ルール編集: {target_rule['rule_name']}" if is_edit else "➕ 新規ルール作成"
    st.subheader(form_title)

    default_name = target_rule["rule_name"] if is_edit else ""
    default_cfg = target_rule["config"] if is_edit else {}
    default_init = default_cfg.get("init_score", 25000)
    default_ret = default_cfg.get("return_score", 30000)
    default_uma = default_cfg.get("uma", [50, 10, -10, -30])

    rule_name_in = st.text_input("ルール名", value=default_name, placeholder="例: Mリーグルール、ゴットーなど", key="rf_name")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        init_score_in = st.number_input("持ち点 (配給原点)", value=int(default_init), step=1000, key="rf_init")
    with col_s2:
        return_score_in = st.number_input("返し点 (原点)", value=int(default_ret), step=1000, key="rf_ret")

    st.markdown("**順位点 (ウマ / pt)**")
    cu1, cu2, cu3, cu4 = st.columns(4)
    with cu1:
        uma1 = st.number_input("1位", value=int(default_uma[0]), step=5, key="rf_uma1")
    with cu2:
        uma2 = st.number_input("2位", value=int(default_uma[1]), step=5, key="rf_uma2")
    with cu3:
        uma3 = st.number_input("3位", value=int(default_uma[2]), step=5, key="rf_uma3")
    with cu4:
        uma4 = st.number_input("4位", value=int(default_uma[3]), step=5, key="rf_uma4")

    # ➕ 将来の拡張項目用アコーディオンエリア
    with st.expander("➕ 詳細・特殊ルール設定 (将来拡張用)"):
        st.caption("※今後追加される飛賞や特殊ルール設定の拡張領域です。")
        tobi_pen = st.number_input("トビ賞ペナルティ (pt)", value=int(default_cfg.get("tobi_penalty", 0)), step=5, key="rf_tobi")
        note_text = st.text_area("ルールメモ", value=default_cfg.get("note", ""), placeholder="ルールの補足メモを入力できます", key="rf_note")

    st.write("")

    cs1, cs2 = st.columns(2)
    with cs1:
        if st.button("保存する", type="primary", use_container_width=True, key="rf_save"):
            if not rule_name_in.strip():
                st.error("ルール名を入力してください")
            else:
                r_id = target_rule["rule_id"] if is_edit else f"rule_{uuid.uuid4().hex[:8]}"
                cfg_dict = {
                    "init_score": int(init_score_in),
                    "return_score": int(return_score_in),
                    "uma": [int(uma1), int(uma2), int(uma3), int(uma4)],
                    "tobi_penalty": int(tobi_pen),
                    "note": note_text,
                }
                is_def = target_rule.get("is_default", 0) if is_edit else (1 if len(rules) == 0 else 0)
                db.save_rule(r_id, rule_name_in.strip(), cfg_dict, is_default=bool(is_def))
                st.session_state.editing_rule_id = None
                st.success(f"ルール「{rule_name_in}」を保存しました")
                st.rerun()
    with cs2:
        if is_edit:
            if st.button("編集キャンセル", use_container_width=True, key="rf_cancel"):
                st.session_state.editing_rule_id = None
                st.rerun()
