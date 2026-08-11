import streamlit as st
from datetime import datetime
import database2 as db
import calc
import game_logic
from constants import MEMBERS, INIT_SCORE, HOUSE_RULES


def _show_rules_expander():
    with st.expander("ルール確認"):
        for category, rules in HOUSE_RULES.items():
            st.markdown(f"**{category}**  \n" + "  \n".join(rules))


def show_setup():
    draft = st.session_state.get("draft_data")
    if draft and draft.get("game_active") and draft.get("game_mode") == "detail":
        draft_time = st.session_state.get("draft_time")
        time_str = draft_time.strftime("%m/%d %H:%M") if draft_time else "不明"
        st.warning(f"{time_str} の対局が中断されています。再開しますか？")
        cr, cd = st.columns(2)
        with cr:
            if st.button("再開する", type="primary", use_container_width=True, key="draft_resume"):
                for k, v in draft.items():
                    st.session_state[k] = v
                st.session_state["draft_data"] = None
                st.session_state["draft_time"] = None
                st.rerun()
            if st.button("破棄する", use_container_width=True, key="draft_discard"):
                db.delete_draft()
                st.session_state["draft_data"] = None
                st.session_state["draft_time"] = None
                st.rerun()
        st.divider()

    ch1, ch2 = st.columns([1, 3])
    with ch1:
        if st.button("🏠 ホーム", use_container_width=True, key="setup_back_home"):
            st.session_state.view = "home"
            st.rerun()
    with ch2:
        st.markdown("### 対局メンバー・ルール選択")

    # ── グループ＆ルール選択 ──────────────────────────────────
    groups = db.get_groups()
    rules = db.get_rules()
    rule_map = {r["rule_id"]: r["rule_name"] for r in rules}

    group_options = [{"group_id": "all", "group_name": "全メンバー (グループ指定なし)", "members": MEMBERS, "default_rule_id": "m_league"}] + groups

    # セッション状態の初期化
    if "selected_group_id" not in st.session_state:
        st.session_state.selected_group_id = "all"
    if "active_rule_id" not in st.session_state:
        st.session_state.active_rule_id = rules[0]["rule_id"] if rules else "m_league"

    col_g, col_r = st.columns(2)
    with col_g:
        grp_names = [g["group_name"] for g in group_options]
        cur_g_idx = next((idx for idx, g in enumerate(group_options) if g["group_id"] == st.session_state.selected_group_id), 0)
        sel_g_name = st.selectbox("👥 グループ選択", options=grp_names, index=cur_g_idx, key="setup_grp_select")
        
        chosen_group = next((g for g in group_options if g["group_name"] == sel_g_name), group_options[0])
        if chosen_group["group_id"] != st.session_state.selected_group_id:
            st.session_state.selected_group_id = chosen_group["group_id"]
            # グループ変更時にデフォルトルールを自動適用
            if chosen_group.get("default_rule_id") and chosen_group["default_rule_id"] in rule_map:
                st.session_state.active_rule_id = chosen_group["default_rule_id"]
            st.rerun()

    with col_r:
        r_ids = [r["rule_id"] for r in rules]
        cur_r_idx = r_ids.index(st.session_state.active_rule_id) if st.session_state.active_rule_id in r_ids else 0
        sel_r_id = st.selectbox("⚙️ 適用ルール", options=r_ids, index=cur_r_idx, format_func=lambda x: rule_map.get(x, x), key="setup_rule_select")
        if sel_r_id != st.session_state.active_rule_id:
            st.session_state.active_rule_id = sel_r_id
            st.rerun()

    st.divider()

    # ── 席順スロット表示 ────────────────────────────────────
    selected = st.session_state.selected_players
    wind_labels = ["東", "南", "西", "北"]

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

    # ── メンバーボタン一覧 ───────────────────────────────────
    target_members = chosen_group.get("members", MEMBERS)
    if not target_members:
        target_members = MEMBERS

    show_all = st.checkbox("全登録メンバーを表示する", value=(chosen_group["group_id"] == "all"), key="setup_show_all_mems")
    display_members = MEMBERS if show_all else target_members

    grid = st.columns(2)
    for i, m in enumerate(display_members):
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

    guest_name = st.text_input("➕ ゲストを追加", placeholder="ゲスト名を入力してEnter",
                               key="guest_input")
    if guest_name:
        if st.button("ゲストを追加する",
                     disabled=(len(selected) >= 4 or guest_name in selected)):
            selected.append(guest_name)
            st.rerun()

    st.divider()

    ready = len(selected) == 4
    c1, c2 = st.columns(2)
    with c1:
        if st.button("詳細モードで開始", type="primary",
                     disabled=not ready, use_container_width=True):
            st.session_state.players = list(selected)
            # 選択中のルールの配給原点 (init_score) を使用
            active_cfg = next((r["config"] for r in rules if r["rule_id"] == st.session_state.active_rule_id), {})
            init_score_val = active_cfg.get("init_score", INIT_SCORE)
            st.session_state.scores = {p: init_score_val for p in selected}
            st.session_state.game_active = True
            st.session_state.game_mode = "detail"
            st.session_state.selected_players = []
            game_logic.autosave_draft()
            st.rerun()
    with c2:
        if st.button("結果のみ入力", disabled=not ready, use_container_width=True):
            st.session_state.players = list(selected)
            st.session_state.game_mode = "simple"
            st.session_state.game_active = True
            st.session_state.selected_players = []
            st.session_state.view = "simple_input"
            game_logic.autosave_draft()
            st.rerun()

    _show_rules_expander()


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
            game_id = db.save_game(date_str, scores, players, local=db.IS_LOCAL)
            db.get_games_data.clear()
            result_rows = [
                {"rank": i + 1, "name": p, "score": scores[p],
                 "pt": calc.calc_special_point(scores[p], i + 1)}
                for i, p in enumerate(sorted_p)
            ]
            st.session_state.last_result = {
                "game_id": game_id, "date": date_str, "rows": result_rows
            }
            game_logic.reset_game()
            st.session_state.view = "result"
            st.rerun()
    with c2:
        if st.button("キャンセル", use_container_width=True):
            game_logic.reset_game()
            st.rerun()



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
        st.session_state.view = "home"
        st.rerun()
