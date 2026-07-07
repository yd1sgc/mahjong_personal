import streamlit as st
import pandas as pd
from datetime import datetime
import database2 as db
import calc
import game_logic
from constants import KO_RON, OYA_RON, KO_TSUMO, OYA_TSUMO, HOUSE_RULES


def _show_rules_expander():
    with st.expander("ルール確認"):
        for category, rules in HOUSE_RULES.items():
            st.markdown(f"**{category}**  \n" + "  \n".join(rules))


def show_game():
    idx = st.session_state.round_idx
    top_score = max(st.session_state.scores.values())

    end_reason = None
    if idx >= 12:
        end_reason = "西4局終了（北入りなし）"
    elif idx >= 8 and top_score >= 30000:
        end_reason = f"トップ {top_score:,}点（30,000点以上）"

    if end_reason:
        st.info(f"終局条件：{end_reason}")
        if st.button("終局・記録する", type="primary", use_container_width=True):
            st.session_state.input_mode = "endgame"
            st.rerun()
        if st.button("↩ 元に戻す",
                     disabled=not st.session_state.undo_stack,
                     use_container_width=True):
            game_logic.undo_last()
            st.rerun()
        return

    if idx == 8:
        st.warning(f"西入り　トップ {top_score:,}点（30,000点未満）")

    players = st.session_state.players
    scores = st.session_state.scores
    diff_target = st.session_state.diff_target
    riichi_declared = st.session_state.riichi_declared
    furo_declared = st.session_state.furo_declared
    dealer = game_logic.get_dealer()

    if st.session_state.get("draft_save_error"):
        st.caption("下書き保存失敗（通信エラー）")
        st.session_state.pop("draft_save_error", None)

    kyoku_str = f"{game_logic.get_round_name()} {st.session_state.honba}本場"
    kyotaku_str = f"供託{st.session_state.riichi_stick}本"
    diff_text = f"{diff_target} 基準の点差表示中" if diff_target else "　"
    diff_color = "#888" if diff_target else "transparent"
    st.markdown(
        f"**{kyoku_str}**　{kyotaku_str}　親: {dealer}"
        f"<br><small style='color:{diff_color};'>{diff_text}</small>",
        unsafe_allow_html=True,
    )

    for p in players:
        score = scores[p]
        is_riichi = p in riichi_declared
        is_furo = p in furo_declared
        is_diff_base = (diff_target == p)
        in_diff_mode = bool(diff_target) and not is_diff_base

        tags = []
        if p == dealer:
            tags.append("★")
        if is_riichi:
            tags.append("立")
        tag_str = " ".join(tags)

        col_p, col_f, col_r = st.columns([4, 1, 1])

        with col_p:
            name_label = f"{tag_str + ' ' if tag_str else ''}{p}"
            if in_diff_mode:
                diff = score - scores[diff_target]
                sign = "+" if diff >= 0 else ""
                color_name = "blue" if diff >= 0 else "red"
                label = f"{name_label}\n\n:{color_name}[{sign}{diff:,}]"
                st.button(label, key=f"p_{p}", use_container_width=True)
            else:
                if st.button(f"{name_label}\n\n{score:,}", key=f"p_{p}", use_container_width=True):
                    st.session_state.diff_target = None if is_diff_base else p
                    st.rerun()

        with col_f:
            label_f = "副\n✓" if is_furo else "副\n　"
            if st.button(label_f, key=f"f_{p}",
                         type="primary" if is_furo else "secondary",
                         disabled=is_riichi,
                         use_container_width=True):
                if is_furo:
                    st.session_state.furo_declared.remove(p)
                else:
                    st.session_state.furo_declared.append(p)
                st.rerun()

        with col_r:
            if is_riichi:
                st.button("立\n✓", key=f"r_{p}", type="primary",
                          use_container_width=True)
            else:
                can_riichi = not is_furo
                if st.button("立\n　", key=f"r_{p}",
                             disabled=not can_riichi, use_container_width=True):
                    game_logic.declare_riichi(p)
                    st.rerun()

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("和了", type="primary", use_container_width=True):
            st.session_state.input_mode = "win"
            st.session_state.win_step = 0
            st.session_state.win_data = {}
            st.rerun()
    with c2:
        if st.button("流局", use_container_width=True):
            st.session_state.input_mode = "ryukyoku"
            st.session_state.tenpai_selection = list(riichi_declared)
            st.rerun()

    st.divider()

    if st.button("↩ 元に戻す",
                 disabled=not st.session_state.undo_stack,
                 use_container_width=True):
        game_logic.undo_last()
        st.rerun()

    with st.expander("その他の操作"):
        c3, c4 = st.columns(2)
        with c3:
            if st.button("チョンボ", use_container_width=True):
                st.session_state.input_mode = "chombo"
                st.rerun()
        with c4:
            if st.button("局を修正", use_container_width=True):
                st.session_state.input_mode = "edit_history"
                st.rerun()

    _show_rules_expander()

    st.divider()
    if st.session_state.confirm_endgame:
        st.warning("本当に終局しますか？")
        c_yes, c_no = st.columns(2)
        with c_yes:
            if st.button("はい、終局する", type="primary", use_container_width=True):
                st.session_state.confirm_endgame = False
                st.session_state.input_mode = "endgame"
                st.rerun()
        with c_no:
            if st.button("キャンセル", use_container_width=True):
                st.session_state.confirm_endgame = False
                st.rerun()
    else:
        if st.button("終局・記録する", use_container_width=True):
            st.session_state.confirm_endgame = True
            st.rerun()


def show_win_input():
    players = st.session_state.players
    step = st.session_state.win_step
    data = st.session_state.win_data

    if step == 0:
        st.title("誰が和了？")
        for p in players:
            mark = "  ★" if p == game_logic.get_dealer() else ""
            if st.button(f"{p}{mark}", key=f"w_{p}",
                         type="primary", use_container_width=True):
                data["winner"] = p
                data["is_dealer"] = (p == game_logic.get_dealer())
                st.session_state.win_step = 1
                st.rerun()

    elif step == 1:
        st.title(f"{data['winner']}  ロン？ ツモ？")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("ロン", type="primary", use_container_width=True):
                data["win_type"] = "ron"
                st.session_state.win_step = 2
                st.rerun()
        with c2:
            if st.button("ツモ", type="primary", use_container_width=True):
                data["win_type"] = "tsumo"
                st.session_state.win_step = 2
                st.rerun()

    elif step == 2:
        st.title("点数は？")
        is_dealer = data["is_dealer"]
        win_type = data["win_type"]

        if win_type == "ron":
            presets = OYA_RON if is_dealer else KO_RON
            cols = st.columns(3)
            for i, (label, pts) in enumerate(presets):
                with cols[i % 3]:
                    if st.button(label, key=f"pts_{pts}", use_container_width=True):
                        data["points_data"] = {"total": pts}
                        st.session_state.win_step = 3
                        st.rerun()
        else:
            if is_dealer:
                presets = OYA_TSUMO
                cols = st.columns(2)
                for i, (label, each) in enumerate(presets):
                    with cols[i % 2]:
                        if st.button(label, key=f"pts_{each}", use_container_width=True):
                            game_logic.apply_win(data["winner"], "tsumo",
                                                 {"each_pays": each, "total": each * 3})
                            st.rerun()
            else:
                presets = KO_TSUMO
                cols = st.columns(2)
                for i, (label, ko_p, oya_p) in enumerate(presets):
                    with cols[i % 2]:
                        if st.button(label, key=f"pts_{ko_p}_{oya_p}", use_container_width=True):
                            game_logic.apply_win(data["winner"], "tsumo",
                                                 {"ko_pays": ko_p, "oya_pays": oya_p,
                                                  "total": ko_p * 2 + oya_p})
                            st.rerun()

        with st.expander("翻・符で計算"):
            han = st.number_input("翻", min_value=1, max_value=13, value=3, key="han_in")
            fu = st.selectbox("符", [20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110],
                              index=2, key="fu_in")
            _total, _oya_p, _ko_p = calc.calculate_score(han, fu, is_dealer,
                                                          win_type == "tsumo")
            if win_type == "ron":
                st.info(f"{_total:,}点")
            elif is_dealer:
                st.info(f"{_ko_p:,}点オール")
            else:
                st.info(f"子{_ko_p:,}点 / 親{_oya_p:,}点")
            if st.button("この点数で使う", key="calc_apply"):
                if win_type == "ron":
                    data["points_data"] = {"total": _total}
                    st.session_state.win_step = 3
                else:
                    if is_dealer:
                        pd_ = {"each_pays": _ko_p, "total": _total}
                    else:
                        pd_ = {"ko_pays": _ko_p, "oya_pays": _oya_p, "total": _total}
                    game_logic.apply_win(data["winner"], "tsumo", pd_)
                st.rerun()

    elif step == 3:
        st.title("放銃者は？")
        winner = data["winner"]
        for p in players:
            if p != winner:
                if st.button(p, key=f"loser_{p}",
                             type="primary", use_container_width=True):
                    game_logic.apply_win(winner, data["win_type"], data["points_data"], loser=p)
                    st.rerun()

    st.divider()
    if st.button("キャンセル", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.session_state.win_step = 0
        st.session_state.win_data = {}
        st.rerun()


def show_ryukyoku_input():
    st.title("流局")
    players = st.session_state.players
    riichi_declared = st.session_state.riichi_declared
    tenpai_sel = st.session_state.tenpai_selection

    st.subheader("テンパイ / ノーテンを選択")

    for p in players:
        is_riichi = p in riichi_declared
        is_tenpai = p in tenpai_sel
        if is_riichi:
            st.button(f"{p}  テンパイ（リーチ）", disabled=True,
                      type="primary", use_container_width=True, key=f"ts_{p}")
        else:
            label = f"{p}  テンパイ" if is_tenpai else f"{p}  ノーテン"
            if st.button(label, key=f"ts_{p}",
                         type="primary" if is_tenpai else "secondary",
                         use_container_width=True):
                if is_tenpai:
                    tenpai_sel.remove(p)
                else:
                    tenpai_sel.append(p)
                st.rerun()

    n_t = len(tenpai_sel)
    n_n = 4 - n_t
    if 0 < n_t < 4:
        st.info(f"テンパイ {n_t}人: 各 +{3000 // n_t}点 / ノーテン {n_n}人: 各 -{3000 // n_n}点")
    else:
        st.info("点数移動なし（全員テンパイ または 全員ノーテン）")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("確定", type="primary", use_container_width=True):
            tenpai = list(tenpai_sel)
            del st.session_state["tenpai_selection"]
            game_logic.apply_ryukyoku(tenpai)
            st.rerun()
    with c2:
        if st.button("キャンセル", use_container_width=True):
            del st.session_state["tenpai_selection"]
            st.session_state.input_mode = "normal"
            st.rerun()


def show_chombo_input():
    st.title("チョンボ")
    players = st.session_state.players
    dealer = game_logic.get_dealer()

    st.subheader("チョンボしたプレイヤーを選択")
    for p in players:
        if p == dealer:
            label = f"★ {p}（親）　→ 子3人に各4,000点"
        else:
            label = f"{p}　→ 親に4,000点・子2人に各2,000点"
        if st.button(label, key=f"chombo_{p}", use_container_width=True):
            game_logic.apply_chombo(p)
            st.rerun()

    if st.button("キャンセル", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.rerun()


def show_edit_history():
    st.title("局履歴の修正")
    st.caption("記録内容の修正のみ。点数の変更は「元に戻す」を使用してください。")

    history = st.session_state.round_history
    if not history:
        st.info("まだ局の記録がありません。")
        if st.button("戻る", use_container_width=True):
            st.session_state.input_mode = "normal"
            st.rerun()
        return

    type_label = {"ron": "ロン", "tsumo": "ツモ", "ryukyoku": "流局", "chombo": "チョンボ"}
    rows = []
    for r in history:
        rows.append({
            "局": r["kyoku_name"],
            "種別": type_label.get(r["win_type"], r["win_type"]),
            "和了": r.get("winner", ""),
            "放銃": r.get("loser", ""),
            "点数": r.get("score", 0),
            "リーチ": ",".join(r.get("riichi", [])),
            "副露": ",".join(r.get("furo", [])),
            "テンパイ": ",".join(r.get("tenpai", [])),
        })

    edited = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "種別": st.column_config.SelectboxColumn(
                "種別", options=["ロン", "ツモ", "流局", "チョンボ"], width="small"
            ),
            "点数": st.column_config.NumberColumn("点数", min_value=0, step=100),
        },
        hide_index=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("保存", type="primary", use_container_width=True):
            rev = {"ロン": "ron", "ツモ": "tsumo", "流局": "ryukyoku", "チョンボ": "chombo"}
            new_history = []
            for _, row in edited.iterrows():
                wt = rev.get(str(row["種別"]), "ron")
                new_history.append({
                    "kyoku_name": str(row["局"]),
                    "winner": str(row["和了"]) if row["和了"] else "",
                    "loser": str(row["放銃"]) if row["放銃"] else "",
                    "win_type": wt,
                    "score": int(row["点数"]) if pd.notna(row["点数"]) else 0,
                    "riichi": [x.strip() for x in str(row["リーチ"]).split(",") if x.strip()],
                    "furo": [x.strip() for x in str(row["副露"]).split(",") if x.strip()],
                    "tenpai": [x.strip() for x in str(row["テンパイ"]).split(",") if x.strip()],
                })
            st.session_state.round_history = new_history
            st.session_state.input_mode = "normal"
            game_logic.autosave_draft()
            st.rerun()
    with c2:
        if st.button("キャンセル", use_container_width=True):
            st.session_state.input_mode = "normal"
            st.rerun()


def show_endgame():
    st.title("終局")
    players = st.session_state.players
    scores = dict(st.session_state.scores)

    riichi_bonus = st.session_state.riichi_stick * 1000
    if riichi_bonus > 0:
        top_p = max(players, key=lambda p: scores[p])
        scores[top_p] += riichi_bonus
        st.info(f"供託 {st.session_state.riichi_stick}本（{riichi_bonus:,}点）を {top_p} に加算します")

    sorted_p = sorted(players, key=lambda p: scores[p], reverse=True)

    st.subheader("最終結果")
    for i, p in enumerate(sorted_p):
        pt = calc.calc_special_point(scores[p], i + 1)
        st.write(f"{i + 1}位: **{p}**　{scores[p]:,}点　({pt:+.1f}pt)")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("記録して終了", type="primary", use_container_width=True):
            st.session_state.scores = scores
            st.session_state.riichi_stick = 0
            date_str = datetime.now().strftime("%Y-%m-%d")
            if st.session_state.get("online", True):
                game_id = db.save_game(date_str, scores, players)
                for r in st.session_state.round_history:
                    db.save_round(game_id, r["kyoku_name"], r["winner"], r["loser"],
                                  r["score"], r["furo"], r["riichi"],
                                  win_type=r.get("win_type", ""),
                                  tenpai=r.get("tenpai", []))
            else:
                game_id = db.save_game_local(date_str, scores, players)
                for r in st.session_state.round_history:
                    db.save_round_local(game_id, r["kyoku_name"], r["winner"], r["loser"],
                                        r["score"], r["furo"], r["riichi"],
                                        win_type=r.get("win_type", ""),
                                        tenpai=r.get("tenpai", []))
            db.get_games_data.clear()
            db.get_rounds_data.clear()
            result_rows = [
                {"rank": i + 1, "name": p, "score": scores[p],
                 "pt": calc.calc_special_point(scores[p], i + 1)}
                for i, p in enumerate(sorted_p)
            ]
            st.session_state.last_result = {"game_id": game_id, "date": date_str, "rows": result_rows}
            db.delete_draft()
            st.session_state.pop("draft_data", None)
            st.session_state.pop("draft_time", None)
            game_logic.reset_game()
            st.session_state.view = "result"
            st.rerun()
    with c2:
        if st.button("記録せず終了", use_container_width=True):
            st.session_state["confirm_discard"] = True
            st.rerun()

    if st.session_state.get("confirm_discard"):
        st.warning("本当に終了しますか？下書きも削除されます。")
        cy, cn = st.columns(2)
        with cy:
            if st.button("削除して終了", type="primary", use_container_width=True):
                db.delete_draft()
                st.session_state.pop("draft_data", None)
                st.session_state.pop("draft_time", None)
                game_logic.reset_game()
                st.rerun()
        with cn:
            if st.button("キャンセル", use_container_width=True):
                st.session_state["confirm_discard"] = False
                st.rerun()

    if st.button("戻る（対局続行）", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.rerun()
