import uuid
import streamlit as st
import database2 as db
import constants
from constants import generate_rule_description, DEFAULT_RULE_CONFIG


def _normalize_config(raw_cfg):
    """旧データ構造(平坦なdict)を拡張データ構造へ安全変換"""
    if not isinstance(raw_cfg, dict):
        return DEFAULT_RULE_CONFIG.copy()

    if "basic" in raw_cfg and "detail" in raw_cfg:
        return raw_cfg

    def_cfg = DEFAULT_RULE_CONFIG.copy()
    b = def_cfg["basic"].copy()
    d = def_cfg["detail"].copy()

    b["init_score"] = raw_cfg.get("init_score", 25000)
    b["return_score"] = raw_cfg.get("return_score", 30000)
    b["uma"] = raw_cfg.get("uma", [50, 10, -10, -30])
    d["tobi_penalty_pt"] = raw_cfg.get("tobi_penalty", 0)
    d["house_notes"] = raw_cfg.get("note", "")

    return {"basic": b, "detail": d}


def show_rule_manage():
    c_h1, c_h2 = st.columns([1, 3])
    with c_h1:
        if st.button("🏠 ホーム", use_container_width=True, key="rule_back_home"):
            st.session_state.view = "home"
            st.rerun()
    with c_h2:
        st.markdown("### ⚙️ ルール作成・詳細管理")

    st.caption("対局で適用するルール（持ち点・ウマ・アリアリルール・特殊ペナルティ等）を細かくカスタマイズ・管理できます。")
    st.divider()

    if "editing_rule_id" not in st.session_state:
        st.session_state.editing_rule_id = None
    if "rule_page_mode" not in st.session_state:
        st.session_state.rule_page_mode = "list"

    if "rule_flash_message" in st.session_state:
        st.success(st.session_state.rule_flash_message)
        del st.session_state.rule_flash_message

    all_rules = db.get_rule_templates(include_archived=False)
    official_presets = [r for r in all_rules if r["kind"] == "official"]
    custom_rules = [r for r in all_rules if r["kind"] == "custom"]

    if st.session_state.rule_page_mode == "list":
        show_rule_list(official_presets, custom_rules)
    elif st.session_state.rule_page_mode == "edit":
        show_rule_edit(custom_rules)


def show_rule_list(official_presets, custom_rules):
    # ── 1. 公式システムテンプレート (編集不可 / 複製可) ───────
    st.subheader("🏆 公式システムテンプレート (編集不可・複製作成のみ可)")
    st.caption("有名団体や標準ルールの固定定義です。「複製作成」ボタンを押すと下のフォームに内容が読み込まれます。")

    for p in official_presets:
        p_id = p["rule_id"]
        disp_id = p.get("display_id", "PRESET")
        p_name = p["rule_name"]
        norm_cfg = _normalize_config(p.get("config", {}))
        b_cfg = norm_cfg["basic"]
        d_cfg = norm_cfg["detail"]
        uma = b_cfg.get("uma", [50, 10, -10, -30])
        uma_str = f"{uma[0]:+}, {uma[1]:+}, {uma[2]:+}, {uma[3]:+}"

        with st.container():
            cp1, cp2 = st.columns([3, 1])
            with cp1:
                st.markdown(f"**[{disp_id}] {p_name}** 🔒")
                st.caption(f"{b_cfg.get('init_score', 25000):,}点持ち / {b_cfg.get('return_score', 30000):,}点返し | ウマ: [{uma_str}] | {d_cfg.get('house_notes', '')}")
            with cp2:
                if st.button("📋 複製作成", key=f"copy_p_{p_id}", use_container_width=True):
                    st.session_state.form_preset_data = {
                        "rule_name": f"{p_name} (カスタム)",
                        "config": norm_cfg
                    }
                    st.session_state.editing_rule_id = None
                    st.session_state.rule_page_mode = "edit"
                    st.rerun()
        st.divider()

    # ── 2. カスタムルール一覧 (R01, R02... 編集可) ─────────────
    st.subheader("📋 マイカスタムルール一覧")

    if st.button("➕ 新規カスタムルールを作成", use_container_width=True, type="primary"):
        st.session_state.rule_page_mode = "edit"
        st.session_state.editing_rule_id = None
        st.session_state.pop("form_preset_data", None)
        st.rerun()
    st.write("")

    if not custom_rules:
        st.info("カスタムルールは登録されていません。上のボタンから新規作成してください。")
    else:
        for r in custom_rules:
            r_id = r["rule_id"]
            disp_id = r.get("display_id", "R--")
            r_name = r["rule_name"]
            norm_cfg = _normalize_config(r.get("config", {}))
            b_cfg = norm_cfg["basic"]
            d_cfg = norm_cfg["detail"]

            init_s = b_cfg.get("init_score", 25000)
            ret_s = b_cfg.get("return_score", 30000)
            uma = b_cfg.get("uma", [50, 10, -10, -30])
            uma_str = f"{uma[0]:+}, {uma[1]:+}, {uma[2]:+}, {uma[3]:+}"
            tobi_str = "トビあり" if d_cfg.get("tobi_end") != "none" else "トビなし"

            with st.container():
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.markdown(f"**[{disp_id}] {r_name}**")
                    st.caption(f"{init_s:,}点持ち / {ret_s:,}点返し | ウマ: [{uma_str}] | {tobi_str}")
                with c2:
                    st.empty() # Placeholder for alignment
                with c3:
                    if st.button("編集", key=f"edit_{r_id}", use_container_width=True):
                        st.session_state.editing_rule_id = r_id
                        st.session_state.rule_page_mode = "edit"
                        st.rerun()

            st.divider()


def show_rule_edit(custom_rules):
    if st.button("⬅️ 一覧へ戻る", key="rule_back_list"):
        st.session_state.rule_page_mode = "list"
        st.session_state.editing_rule_id = None
        st.rerun()
    st.divider()

    # ── 3. ルール作成 / 編集フォーム (案A: 縦並びアコーディオン) ──
    target_rule = None
    if st.session_state.editing_rule_id:
        target_rule = next((r for r in custom_rules if r["rule_id"] == st.session_state.editing_rule_id), None)

    is_edit = target_rule is not None
    next_rid_str = target_rule.get("display_id", f"R{len(custom_rules) + 1:02d}") if is_edit else f"R{len(custom_rules) + 1:02d}"
    form_title = f"✏️ ルール編集: [{next_rid_str}] {target_rule['rule_name']}" if is_edit else f"➕ 新規ルール作成 (割り当てID: {next_rid_str})"
    st.subheader(form_title)

    # 初期値のセット
    if "form_preset_data" in st.session_state:
        p_data = st.session_state.pop("form_preset_data")
        default_name = p_data["rule_name"]
        init_cfg = p_data.get("config", DEFAULT_RULE_CONFIG.copy())
    elif is_edit:
        default_name = target_rule["rule_name"]
        init_cfg = _normalize_config(target_rule["config"])
    else:
        default_name = ""
        init_cfg = DEFAULT_RULE_CONFIG.copy()

    b_init = init_cfg.get("basic", {})
    d_init = init_cfg.get("detail", {})

    rule_name_in = st.text_input("ルール名称", value=default_name, placeholder="例: Mリーグルール、金曜アリアリなど", key="rf_name")

    # アコーディオン 1: ⚙️ 基本設定
    with st.expander("▼ 【アコーディオン 1】 ⚙️ 基本設定 (持ち点・返し点・ウマ・端数処理)", expanded=True):
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            init_score_in = st.number_input("持ち点 (配給原点)", value=int(b_init.get("init_score", 25000)), step=1000, key="rf_init")
        with col_s2:
            return_score_in = st.number_input("返し点 (原点)", value=int(b_init.get("return_score", 30000)), step=1000, key="rf_ret")

        st.markdown("**順位点 (ウマ / pt)**")
        default_uma = b_init.get("uma", [50, 10, -10, -30])
        cu1, cu2, cu3, cu4 = st.columns(4)
        with cu1:
            uma1 = st.number_input("1位", value=int(default_uma[0]), step=5, key="rf_uma1")
        with cu2:
            uma2 = st.number_input("2位", value=int(default_uma[1]), step=5, key="rf_uma2")
        with cu3:
            uma3 = st.number_input("3位", value=int(default_uma[2] if len(default_uma) > 2 else -10), step=5, key="rf_uma3")
        with cu4:
            uma4 = st.number_input("4位", value=int(default_uma[3] if len(default_uma) > 3 else -30), step=5, key="rf_uma4")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            rate_note_in = st.text_input("レート・換算メモ", value=b_init.get("rate_note", "1000点＝1.0pt"), placeholder="例: 1000点＝1pt (×0.2) 等", key="rf_rate")
        with col_b2:
            rounding_in = st.selectbox("端数処理方式", options=["五捨六入", "四捨五入", "切捨て", "切上げ", "小数点第一位維持"], index=0, key="rf_round")

    # アコーディオン 2: 🀄 アリアリ・ドラ設定
    with st.expander("▼ 【アコーディオン 2】 🀄 アリアリ・ドラ設定 (喰いタン・後付け・赤牌・喰い替え)", expanded=False):
        cd1, cd2, cd3 = st.columns(3)
        with cd1:
            kuitan_in = st.checkbox("喰いタンあり", value=bool(d_init.get("kuitan", True)), key="rf_kuitan")
            atozuke_in = st.checkbox("後付けあり", value=bool(d_init.get("atozuke", True)), key="rf_atozuke")
        with cd2:
            aka_in = st.selectbox("赤牌枚数", options=["3枚", "4枚", "なし"], index=["3枚", "4枚", "なし"].index(d_init.get("aka_dora", "3枚")) if d_init.get("aka_dora") in ["3枚", "4枚", "なし"] else 0, key="rf_aka")
        with cd3:
            kuikae_in = st.selectbox("喰い替え", options=["不可 (禁止)", "可"], index=0 if d_init.get("kuikae", "forbidden") == "forbidden" else 1, key="rf_kuikae")

    # アコーディオン 3: 🔄 進行・流局・終局条件
    with st.expander("▼ 【アコーディオン 3】 🔄 進行・流局・終局条件 (トビ・西入・途中流局・連荘)", expanded=False):
        cg1, cg2, cg3 = st.columns(3)
        with cg1:
            tobi_in = st.selectbox("トビ (ハコ) 終了", options=["0点未満で終了", "0点以下で終了", "トビなし (継続)"], index=0 if d_init.get("tobi_end") == "under_zero" else (1 if d_init.get("tobi_end") == "zero_or_less" else 2), key="rf_tobi_end")
        with cg2:
            west_in = st.selectbox("西入・延長", options=["トップ30,000点未満で西入 (サドンデス)", "なし (オーラスで必ず終了)", "南4局固定"], index=0 if d_init.get("west_extension") == "under_30000" else (1 if d_init.get("west_extension") == "none" else 2), key="rf_west")
        with cg3:
            renchan_in = st.selectbox("親連荘条件", options=["聴牌連荘", "和了連荘", "ノーテン連荘"], index=0 if d_init.get("renchan_rule") == "tenpai" else (1 if d_init.get("renchan_rule") == "agari" else 2), key="rf_renchan")

        col_y1, col_y2 = st.columns(2)
        with col_y1:
            agari_yame_in = st.checkbox("アガリ止め・テンパイ止めあり", value=bool(d_init.get("agari_yame", True)), key="rf_agariyame")
        with col_y2:
            tsumoban_in = st.checkbox("ツモ番なしリーチ許可", value=bool(d_init.get("tsumoban_none_riichi", False)), key="rf_tsumoban")

        st.markdown("**途中流局（九種九牌・四風連打など）**")
        mid_ryukyoku_in = st.selectbox("途中流局の扱い", options=["あり（連荘）", "あり（親流れ/流局）", "なし（そのまま続行）"], index=0 if d_init.get("kyushu") == "renchan" else (1 if d_init.get("kyushu") == "ryukyoku" else 2), key="rf_mid_ryukyoku")


    # アコーディオン 4: 🏆 ダブロン・役満・チョンボ
    with st.expander("▼ 【アコーディオン 4】 🏆 ダブロン・役満・チョンボ (ダブロン・パオ・チョンボ)", expanded=False):
        ct1, ct2 = st.columns(2)
        with ct1:
            dubron_in = st.selectbox("ダブロン・トリロン", options=["なし (頭ハネ/上家取り)", "あり (供託は頭ハネ)", "あり (供託全分配)"], index=0 if d_init.get("dubron") == "atama_hane" else (1 if d_init.get("dubron") == "atama_hane_kyotaku" else 2), key="rf_dubron")
            pao_in = st.checkbox("パオ (責任払い) あり", value=bool(d_init.get("pao", True)), key="rf_pao")
        with ct2:
            chombo_in = st.selectbox("チョンボ扱い", options=["満貫払い", "対局後Pt直減算", "アガリ放棄のみ"], index=0 if d_init.get("chombo_rule") == "mangan_pay" else (1 if d_init.get("chombo_rule") == "pt_penalty" else 2), key="rf_chombo")
            chombo_pt_in = st.number_input("チョンボ時減算Pt (直減算時)", value=int(d_init.get("chombo_pt", 20)), step=5, key="rf_chombopt")

        cx1, cx2 = st.columns(2)
        with cx1:
            yakuman_mult_in = st.checkbox("役満複合・数え役満あり", value=bool(d_init.get("yakuman_multiple", True)), key="rf_ymult")
        with cx2:
            kokushi_ankan_in = st.checkbox("国士無双の暗カンアガリあり", value=bool(d_init.get("kokushi_ankan_win", True)), key="rf_kokushi")

    # アコーディオン 5: 📝 ハウスルールメモ
    with st.expander("▼ 【アコーディオン 5】 📝 ハウスルール補足メモ", expanded=False):
        house_notes_in = st.text_area("ハウスルール補足メモ", value=d_init.get("house_notes", ""), placeholder="例: 農作業優先ルール、独自のローカル決め事など", key="rf_notes")

    # リアルタイムプレビューオブジェクト作成
    preview_config = {
        "basic": {
            "init_score": int(init_score_in),
            "return_score": int(return_score_in),
            "uma": [int(uma1), int(uma2), int(uma3), int(uma4)],
            "rate_note": rate_note_in,
            "rounding_type": rounding_in,
        },
        "detail": {
            "kuitan": kuitan_in,
            "atozuke": atozuke_in,
            "aka_dora": aka_in,
            "kuikae": "forbidden" if "不可" in kuikae_in else "allowed",
            "tobi_end": "under_zero" if "0点未満" in tobi_in else ("zero_or_less" if "0点以下" in tobi_in else "none"),
            "west_extension": "under_30000" if "西入" in west_in else ("none" if "なし" in west_in else "fixed_nan4"),
            "renchan_rule": "tenpai" if "聴牌" in renchan_in else ("agari" if "和了" in renchan_in else "noten"),
            "agari_yame": agari_yame_in,
            "tsumoban_none_riichi": tsumoban_in,
            "kyushu": "renchan" if "連荘" in mid_ryukyoku_in else ("ryukyoku" if "親流れ" in mid_ryukyoku_in else "none"),
            "sufon": "renchan" if "連荘" in mid_ryukyoku_in else ("ryukyoku" if "親流れ" in mid_ryukyoku_in else "none"),
            "sujin_riichi": "renchan" if "連荘" in mid_ryukyoku_in else ("ryukyoku" if "親流れ" in mid_ryukyoku_in else "none"),
            "sukan": "renchan" if "連荘" in mid_ryukyoku_in else ("ryukyoku" if "親流れ" in mid_ryukyoku_in else "none"),
            "dubron": "atama_hane" if "なし" in dubron_in else ("atama_hane_kyotaku" if "供託は頭ハネ" in dubron_in else "split"),
            "pao": pao_in,
            "chombo_rule": "mangan_pay" if "満貫" in chombo_in else ("pt_penalty" if "直減算" in chombo_in else "agari_hoki"),
            "chombo_pt": int(chombo_pt_in),
            "yakuman_multiple": yakuman_mult_in,
            "kokushi_ankan_win": kokushi_ankan_in,
            "house_notes": house_notes_in,
        }
    }

    st.write("")
    with st.expander("📖 ルール確認文章 リアルタイムプレビュー", expanded=True):
        st.caption("※対局画面等で表示される自動組み立て文章のプレビューです。")
        preview_desc = generate_rule_description(preview_config)
        for cat, lines in preview_desc.items():
            st.markdown(f"**{cat}**  \n" + "  \n".join(lines))
            st.write("")

    st.write("")
    st.divider()

    # 保存 / キャンセル / 削除ボタン
    if is_edit:
        cs1, cs2, cs3 = st.columns(3)
    else:
        cs1, cs2 = st.columns(2)

    with cs1:
        if st.button("💾 このルールを保存する", type="primary", use_container_width=True, key="rf_save_all"):
            if not rule_name_in.strip():
                st.error("ルール名を入力してください")
            else:
                r_id = target_rule["rule_id"] if is_edit else f"rule_{uuid.uuid4().hex[:8]}"
                db.save_custom_rule(r_id, rule_name_in.strip(), preview_config)
                st.session_state.rule_flash_message = f"ルール「[{next_rid_str}] {rule_name_in.strip()}」を保存しました"
                st.session_state.editing_rule_id = None
                st.session_state.rule_page_mode = "list"
                st.rerun()

    if is_edit:
        with cs2:
            del_key = f"confirm_del_{target_rule['rule_id']}"
            if st.session_state.get(del_key, False):
                st.error("本当に削除しますか？")
                cd1, cd2 = st.columns(2)
                with cd1:
                    if st.button("はい", type="primary", use_container_width=True, key="rf_del_yes"):
                        db.archive_rule(target_rule["rule_id"])
                        st.session_state.rule_flash_message = f"ルール「{target_rule['rule_name']}」を削除しました"
                        st.session_state.editing_rule_id = None
                        st.session_state.rule_page_mode = "list"
                        st.session_state[del_key] = False
                        st.rerun()
                with cd2:
                    if st.button("いいえ", use_container_width=True, key="rf_del_no"):
                        st.session_state[del_key] = False
                        st.rerun()
            else:
                if st.button("🗑️ 削除", type="secondary", use_container_width=True, key="rf_del_rule"):
                    st.session_state[del_key] = True
                    st.rerun()
        with cs3:
            if st.button("キャンセル", use_container_width=True, key="rf_cancel_all"):
                st.session_state.editing_rule_id = None
                st.session_state.rule_page_mode = "list"
                st.rerun()
    else:
        with cs2:
            if st.button("キャンセル", use_container_width=True, key="rf_cancel_all"):
                st.session_state.editing_rule_id = None
                st.session_state.rule_page_mode = "list"
                st.rerun()
