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
        with cd:
            if st.button("破棄する", use_container_width=True, key="draft_discard"):
                db.delete_draft()
                st.session_state["draft_data"] = None
                st.session_state["draft_time"] = None
                st.rerun()
        st.divider()

    st.markdown("### 麻雀スコア")

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

    guest_name = st.text_input("ゲスト名", placeholder="ゲスト名を入力してEnter",
                               key="guest_input")
    if guest_name:
        if st.button("ゲストを追加",
                     disabled=(len(selected) >= 4 or guest_name in selected)):
            selected.append(guest_name)
            st.rerun()

    st.divider()

    ready = len(selected) == 4
    c1, c2 = st.columns(2)
    with c1:
        if st.button("詳細モード", type="primary",
                     disabled=not ready, use_container_width=True):
            st.session_state.players = list(selected)
            st.session_state.scores = {p: INIT_SCORE for p in selected}
            st.session_state.game_active = True
            st.session_state.game_mode = "detail"
            st.session_state.selected_players = []
            game_logic.autosave_draft()
            st.rerun()
    with c2:
        if st.button("結果のみ", disabled=not ready, use_container_width=True):
            st.session_state.players = list(selected)
            st.session_state.game_mode = "simple"
            st.session_state.selected_players = []
            st.session_state.view = "simple_input"
            st.rerun()

    c3, c4 = st.columns(2)
    with c3:
        if st.button("成績を見る", use_container_width=True):
            st.session_state.view = "stats"
            st.rerun()
    with c4:
        if st.button("データ管理", use_container_width=True):
            st.session_state.view = "data_manage"
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
            if st.session_state.get("online", True):
                game_id = db.save_game(date_str, scores, players)
            else:
                game_id = db.save_game_local(date_str, scores, players)
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
            st.session_state.view = "setup"
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
        st.session_state.view = "setup"
        st.rerun()
