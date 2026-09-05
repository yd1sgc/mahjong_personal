import json
import cache_utils
import streamlit as st
import pandas as pd
from datetime import datetime
import database2 as db
import calc
import game_logic
from constants import KO_RON, OYA_RON, KO_TSUMO, OYA_TSUMO, generate_rule_description

def with_normal_mode(func):
    """状態確定後に自動で input_mode を 'normal' に戻す高階関数"""
    def wrapper(*args, **kwargs):
        func(*args, **kwargs)
        st.session_state.input_mode = "normal"
    return wrapper

def _show_rules_expander():
    with st.expander("ルール確認"):
        config = st.session_state.get("current_rule_config")
        rule_desc = generate_rule_description(config)
        for category, rules in rule_desc.items():
            st.markdown(f"**{category}**  \n" + "  \n".join(rules))


def show_game():
    end_reason = st.session_state.game_state.check_game_end()

    if end_reason:
        st.info(f"終局条件：{end_reason}")
        if st.button("終局・記録する", type="primary", use_container_width=True):
            st.session_state.input_mode = "endgame"
            st.rerun()
        if st.button(" 元に戻す",
                     disabled=not st.session_state.game_state.undo_stack,
                     use_container_width=True):
            st.session_state.game_state.undo_last()
            st.rerun()
        return

    idx = st.session_state.game_state.round_idx
    if idx == 8:
        top_score = max(st.session_state.game_state.scores.values())
        st.warning(f"西入り　トップ {top_score:,}点（30,000点未満）")

    players = st.session_state.game_state.players
    scores = st.session_state.game_state.scores
    diff_target = st.session_state.diff_target
    riichi_declared = st.session_state.game_state.riichi_declared
    furo_declared = st.session_state.game_state.furo_declared
    dealer = st.session_state.game_state.get_dealer()

    if st.session_state.get("draft_save_error"):
        st.caption("下書き保存失敗（通信エラー）")
        st.session_state.pop("draft_save_error", None)

    round_name = st.session_state.game_state.get_round_name()
    honba_str = f"{st.session_state.game_state.honba}本場"
    kyotaku_str = f"供託{st.session_state.game_state.riichi_stick}本"
    st.markdown(
        f"<div style='font-size:20px; font-weight:bold; margin-top:6px; margin-bottom:14px; padding-top:4px; display:flex; align-items:center; flex-wrap:wrap; gap:10px;'>"
        f"<span>{round_name}</span>"
        f"<span style='color:#ffaa00; background:#332200; padding:4px 10px; border-radius:6px; font-size:18px;'>{honba_str}</span>"
        f"<span style='color:#00e5ff; background:#002233; padding:4px 10px; border-radius:6px; font-size:18px;'>{kyotaku_str}</span>"
        f"<span style='font-size:18px; opacity:0.9; margin-left:auto;'>親: {dealer}</span></div>",
        unsafe_allow_html=True,
    )

    def _toggle_diff(player, is_base):
        st.session_state.diff_target = None if is_base else player

    def _toggle_furo(player, is_furo):
        if is_furo:
            st.session_state.game_state.furo_declared.remove(player)
        else:
            st.session_state.game_state.furo_declared.append(player)
        game_logic.autosave_draft()

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
            else:
                label = f"{name_label}\n\n{score:,}"

            st.button(label, key=f"p_{p}", use_container_width=True,
                      on_click=_toggle_diff, args=(p, is_diff_base))

        with col_f:
            label_f = "副\n" if is_furo else "副\n　"
            st.button(label_f, key=f"f_{p}",
                      type="primary" if is_furo else "secondary",
                      disabled=is_riichi,
                      use_container_width=True,
                      on_click=_toggle_furo, args=(p, is_furo))

        with col_r:
            if is_riichi:
                st.button("立\n", key=f"r_{p}", type="primary",
                          use_container_width=True)
            else:
                can_riichi = not is_furo
                st.button("立\n　", key=f"r_{p}",
                          disabled=not can_riichi, use_container_width=True,
                          on_click=st.session_state.game_state.declare_riichi, args=(p,))

    def _goto_win():
        st.session_state.input_mode = "win"
        st.session_state.win_step = 0
        st.session_state.win_data = {}

    def _goto_ryukyoku():
        st.session_state.input_mode = "ryukyoku"
        st.session_state.tenpai_selection = list(st.session_state.game_state.riichi_declared)

    def _goto_chombo():
        st.session_state.input_mode = "chombo"

    def _goto_edit():
        st.session_state.input_mode = "edit_history"

    c1, c2 = st.columns(2)
    with c1:
        st.button("和了", type="primary", use_container_width=True, on_click=_goto_win)
    with c2:
        st.button("流局", use_container_width=True, on_click=_goto_ryukyoku)

    st.button(" 元に戻す", disabled=not st.session_state.game_state.undo_stack,
              use_container_width=True, on_click=st.session_state.game_state.undo_last)

    with st.expander("その他の操作"):
        c3, c4 = st.columns(2)
        with c3:
            st.button("チョンボ", use_container_width=True, on_click=_goto_chombo)
        with c4:
            st.button("局を修正", use_container_width=True, on_click=_goto_edit)

    _show_rules_expander()

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
    players = st.session_state.game_state.players
    step = st.session_state.win_step
    data = st.session_state.win_data

    if step == 0:
        st.title("誰が和了？")
        def _set_winner(p, is_dealer):
            data["winner"] = p
            data["is_dealer"] = is_dealer
            st.session_state.win_step = 1

        for p in players:
            mark = " ★" if p == st.session_state.game_state.get_dealer() else ""
            st.button(f"{p}{mark}", key=f"w_{p}",
                      type="primary", use_container_width=True,
                      on_click=_set_winner, args=(p, p == st.session_state.game_state.get_dealer()))
                
        st.write("---")
        
        dubron_rule = st.session_state.get("current_rule_config", {}).get("detail", {}).get("dubron", "atama_hane")
        allow_multi = dubron_rule in ["atama_hane_kyotaku", "split"]
        
        def _set_multi(num):
            data["multi_win_mode"] = True
            data["num_winners"] = num
            data["winners_data"] = []
            st.session_state.win_step = 10

        if allow_multi:
            c1, c2 = st.columns(2)
            with c1:
                st.button("ダブロン", use_container_width=True, on_click=_set_multi, args=(2,))
            with c2:
                st.button("トリロン", use_container_width=True, on_click=_set_multi, args=(3,))

    # 単独和了のフロー (step 1 ~ 3)
    elif step == 1:
        st.title(f"{data['winner']}  ロン？ ツモ？")
        def _set_win_type(wt):
            data["win_type"] = wt
            st.session_state.win_step = 2

        c1, c2 = st.columns(2)
        with c1:
            st.button("ロン", type="primary", use_container_width=True, on_click=_set_win_type, args=("ron",))
        with c2:
            st.button("ツモ", type="primary", use_container_width=True, on_click=_set_win_type, args=("tsumo",))

    elif step == 2:
        st.title("点数は？")
        is_dealer = data["is_dealer"]
        win_type = data["win_type"]

        def _set_ron_pts(pts):
            data["points_data"] = {"total": pts}
            st.session_state.win_step = 3
        
        def _apply_tsumo(pts_data):
            with_normal_mode(st.session_state.game_state.apply_win)(data["winner"], "tsumo", pts_data)

        if win_type == "ron":
            presets = OYA_RON if is_dealer else KO_RON
            cols = st.columns(3)
            for i, (label, pts) in enumerate(presets):
                with cols[i % 3]:
                    st.button(label, key=f"pts_{pts}", use_container_width=True, on_click=_set_ron_pts, args=(pts,))
        else:
            if is_dealer:
                presets = OYA_TSUMO
                cols = st.columns(2)
                for i, (label, each) in enumerate(presets):
                    with cols[i % 2]:
                        st.button(label, key=f"pts_{each}", use_container_width=True, on_click=_apply_tsumo, args=({"each_pays": each, "total": each * 3},))
            else:
                presets = KO_TSUMO
                cols = st.columns(2)
                for i, (label, ko_p, oya_p) in enumerate(presets):
                    with cols[i % 2]:
                        st.button(label, key=f"pts_{ko_p}_{oya_p}", use_container_width=True, on_click=_apply_tsumo, args=({"ko_pays": ko_p, "oya_pays": oya_p, "total": ko_p * 2 + oya_p},))

        with st.expander("翻・符で計算"):
            han_opts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, "13 (役満)", "26 (ダブル役満)"]
            sel_han = st.selectbox("翻", han_opts, index=2, key="han_in")
            if sel_han == "13 (役満)":
                han = 13
            elif sel_han == "26 (ダブル役満)":
                han = 26
            else:
                han = int(sel_han)

            fu = st.selectbox("符", [20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110], index=2, key="fu_in")
            _total, _oya_p, _ko_p = calc.calculate_score(han, fu, is_dealer, win_type == "tsumo")
            if win_type == "ron":
                st.info(f"{_total:,}点")
            elif is_dealer:
                st.info(f"{_ko_p:,}点オール")
            else:
                st.info(f"子{_ko_p:,}点 / 親{_oya_p:,}点")
            
            def _apply_calc(wt, is_dl, total, ko, oya):
                if wt == "ron":
                    data["points_data"] = {"total": total}
                    st.session_state.win_step = 3
                else:
                    if is_dl:
                        pd_ = {"each_pays": ko, "total": total}
                    else:
                        pd_ = {"ko_pays": ko, "oya_pays": oya, "total": total}
                    with_normal_mode(st.session_state.game_state.apply_win)(data["winner"], "tsumo", pd_)

            st.button("この点数で使う", key="calc_apply", on_click=_apply_calc, args=(win_type, is_dealer, _total, _ko_p, _oya_p))

    elif step == 3:
        st.title("放銃者は？")
        winner = data["winner"]
        for p in players:
            if p != winner:
                st.button(p, key=f"loser_{p}", type="primary", use_container_width=True, on_click=with_normal_mode(st.session_state.game_state.apply_win), args=(winner, data["win_type"], data["points_data"], p))

    # ダブロン・トリロンのフロー (step 10 ~ 12)
    elif step == 10:
        st.title("誰が放銃？（ダブロン/トリロン）")
        def _set_multi_loser(p):
            data["loser"] = p
            st.session_state.win_step = 11

        for p in players:
            st.button(p, key=f"m_loser_{p}", type="primary", use_container_width=True, on_click=_set_multi_loser, args=(p,))
                
    elif step == 11:
        nth = len(data["winners_data"]) + 1
        st.title(f"{nth}人目の和了者は？")
        loser = data["loser"]
        already_won = [wd["winner"] for wd in data["winners_data"]]
        
        def _set_multi_winner(p, is_dl):
            data["current_winner"] = p
            data["current_is_dealer"] = is_dl
            st.session_state.win_step = 12
            
        for p in players:
            if p != loser and p not in already_won:
                mark = " ★" if p == st.session_state.game_state.get_dealer() else ""
                st.button(f"{p}{mark}", key=f"m_w_{p}", type="primary", use_container_width=True, on_click=_set_multi_winner, args=(p, p == st.session_state.game_state.get_dealer()))
                    
    elif step == 12:
        cw = data["current_winner"]
        st.title(f"{cw} の点数は？")
        is_dealer = data["current_is_dealer"]
        presets = OYA_RON if is_dealer else KO_RON
        cols = st.columns(3)
        
        def _add_multi_win(pts):
            data["winners_data"].append({
                "winner": cw,
                "points_data": {"total": pts}
            })
            if len(data["winners_data"]) >= data["num_winners"]:
                with_normal_mode(st.session_state.game_state.apply_multi_win)(data["winners_data"], data["loser"])
            else:
                st.session_state.win_step = 11
            
        for i, (label, pts) in enumerate(presets):
            with cols[i % 3]:
                st.button(label, key=f"m_pts_{pts}", use_container_width=True, on_click=_add_multi_win, args=(pts,))

        with st.expander("翻・符で計算"):
            han_opts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, "13 (役満)", "26 (ダブル役満)"]
            sel_han = st.selectbox("翻", han_opts, index=2, key="m_han_in")
            han = 13 if sel_han == "13 (役満)" else (26 if sel_han == "26 (ダブル役満)" else int(sel_han))
            fu = st.selectbox("符", [20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110], index=2, key="m_fu_in")
            _total, _, _ = calc.calculate_score(han, fu, is_dealer, False)
            st.info(f"{_total:,}点")
            st.button("この点数で使う", key="m_calc_apply", on_click=_add_multi_win, args=(_total,))

    st.divider()
    def _cancel_win():
        st.session_state.input_mode = "normal"
        st.session_state.win_step = 0
        st.session_state.win_data = {}
    st.button("キャンセル", use_container_width=True, on_click=_cancel_win)


def show_ryukyoku_input():
    st.title("流局")
    players = st.session_state.game_state.players
    riichi_declared = st.session_state.game_state.riichi_declared
    
    if "tenpai_selection" not in st.session_state:
        st.session_state.tenpai_selection = list(riichi_declared)
    tenpai_sel = st.session_state.tenpai_selection

    st.subheader("テンパイ / ノーテンを選択")

    def _toggle_tenpai(p, is_tenpai):
        if is_tenpai:
            tenpai_sel.remove(p)
        else:
            tenpai_sel.append(p)

    for p in players:
        is_riichi = p in riichi_declared
        is_tenpai = p in tenpai_sel
        if is_riichi:
            st.button(f"{p}  テンパイ（リーチ）", disabled=True,
                      type="primary", use_container_width=True, key=f"ts_{p}")
        else:
            label = f"{p}  テンパイ" if is_tenpai else f"{p}  ノーテン"
            st.button(label, key=f"ts_{p}",
                      type="primary" if is_tenpai else "secondary",
                      use_container_width=True,
                      on_click=_toggle_tenpai, args=(p, is_tenpai))

    n_t = len(tenpai_sel)
    n_n = 4 - n_t
    if 0 < n_t < 4:
        bappu = st.session_state.get("current_rule_config", {}).get("detail", {}).get("noten_bappu_pt", 3000)
        st.info(f"テンパイ {n_t}人: 各 +{bappu // n_t}点 / ノーテン {n_n}人: 各 -{bappu // n_n}点")
    else:
        st.info("点数移動なし（全員テンパイ または 全員ノーテン）")

    def _confirm_ryukyoku():
        tenpai = list(tenpai_sel)
        del st.session_state["tenpai_selection"]
        with_normal_mode(st.session_state.game_state.apply_ryukyoku)(tenpai)
        
    def _cancel_ryukyoku():
        del st.session_state["tenpai_selection"]
        st.session_state.input_mode = "normal"

    c1, c2 = st.columns(2)
    with c1:
        st.button("確定", type="primary", use_container_width=True, on_click=_confirm_ryukyoku)
    with c2:
        st.button("キャンセル", use_container_width=True, on_click=_cancel_ryukyoku)

    cfg_detail = st.session_state.get("current_rule_config", {}).get("detail", {})
    mid_ryukyoku_opts = {}
    if cfg_detail.get("kyushu", "renchan") != "none": mid_ryukyoku_opts["kyushu"] = "九種九牌"
    if cfg_detail.get("sufon", "none") != "none": mid_ryukyoku_opts["sufon"] = "四風子連打"
    if cfg_detail.get("sujin_riichi", "none") != "none": mid_ryukyoku_opts["sujin_riichi"] = "四家立直"
    if cfg_detail.get("sukan", "allowed_single") != "none": mid_ryukyoku_opts["sukan"] = "四槓散了"
    
    if mid_ryukyoku_opts:
        st.write("---")
        st.subheader("途中流局")
        sel_mid = st.selectbox("途中流局の理由", list(mid_ryukyoku_opts.keys()), format_func=lambda x: mid_ryukyoku_opts[x])
        
        def _confirm_mid_ryukyoku(reason):
            tenpai = list(tenpai_sel)
            del st.session_state["tenpai_selection"]
            with_normal_mode(st.session_state.game_state.apply_mid_ryukyoku)(reason, tenpai_players=tenpai)
            
        st.button("途中流局で確定", type="primary", use_container_width=True, on_click=_confirm_mid_ryukyoku, args=(sel_mid,))

def show_chombo_input():
    st.title("チョンボ")
    players = st.session_state.game_state.players
    dealer = st.session_state.game_state.get_dealer()

    m_base = st.session_state.get("current_rule_config", {}).get("detail", {}).get("mangan_base_pt", 8000)
    oya_pay = m_base // 2
    ko_pay = m_base // 4

    st.subheader("チョンボしたプレイヤーを選択")
    for p in players:
        if p == dealer:
            label = f" {p}（親）　→ 子3人に各{oya_pay:,}点"
        else:
            label = f"{p}　→ 親に{oya_pay:,}点・子2人に各{ko_pay:,}点"
        st.button(label, key=f"chombo_{p}", use_container_width=True, on_click=with_normal_mode(st.session_state.game_state.apply_chombo), args=(p,))

    def _cancel_chombo():
        st.session_state.input_mode = "normal"
    st.button("キャンセル", use_container_width=True, on_click=_cancel_chombo)


def show_edit_history():
    st.title("局履歴の修正")
    st.caption("修正内容に応じて全体の点数・本場・供託が自動再計算されます。")

    history = st.session_state.game_state.round_history
    if not history:
        st.info("まだ局の記録がありません。")
        if st.button("戻る", use_container_width=True):
            st.session_state.input_mode = "normal"
            st.rerun()
        return

    players = st.session_state.game_state.players

    # 1. これまでの対局履歴（一覧表示）
    type_label = {"ron": "ロン", "tsumo": "ツモ", "ryukyoku": "流局", "chombo": "チョンボ"}
    rows = []
    for r in history:
        rows.append({
            "局": r["kyoku_name"],
            "種別": type_label.get(r["win_type"], r["win_type"]),
            "和了/対象": r.get("winner", ""),
            "放銃者": r.get("loser", ""),
            "基本点": r.get("score", 0),
            "リーチ": ",".join(r.get("riichi", [])),
            "副露": ",".join(r.get("furo", [])),
            "聴牌": ",".join(r.get("tenpai", [])),
        })

    st.subheader("対局履歴一覧")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("局データの編集")

    # 2. 修正対象局の選択
    round_labels = [f"【第{i+1}局】{r['kyoku_name']} ({type_label.get(r['win_type'], r['win_type'])})"
                    for i, r in enumerate(history)]
    sel_idx = st.selectbox("修正する局を選択してください", range(len(history)),
                           format_func=lambda i: round_labels[i], key="in_game_edit_idx")

    target_r = history[sel_idx]

    # 3. フォーム入力
    with st.form("in_game_round_edit_form"):
        col1, col2 = st.columns(2)
        with col1:
            type_opts = ["ron", "tsumo", "ryukyoku", "chombo"]
            type_names = {"ron": "ロン", "tsumo": "ツモ", "ryukyoku": "流局", "chombo": "チョンボ"}
            cur_type = target_r.get("win_type", "ron")
            new_type = st.selectbox(
                "和了/精算種別", type_opts,
                index=type_opts.index(cur_type) if cur_type in type_opts else 0,
                format_func=lambda x: type_names.get(x, x),
                key="ige_type"
            )

            p_opts = [""] + players
            cur_winner = target_r.get("winner", "")
            new_winner = st.selectbox(
                "和了者（チョンボ時は対象者）", p_opts,
                index=p_opts.index(cur_winner) if cur_winner in p_opts else 0,
                key="ige_winner"
            )

        with col2:
            new_score = st.number_input(
                "基本点数 (本場除く)",
                value=int(target_r.get("score", 0)), step=100,
                key="ige_score"
            )

            cur_loser = target_r.get("loser", "")
            new_loser = st.selectbox(
                "放銃者 (ロンのみ)", p_opts,
                index=p_opts.index(cur_loser) if cur_loser in p_opts else 0,
                key="ige_loser"
            )

        st.write("**リーチ宣言者**")
        old_riichi = target_r.get("riichi", [])
        cols_r = st.columns(4)
        new_riichi = [p for i, p in enumerate(players)
                      if cols_r[i].checkbox(p, value=(p in old_riichi), key=f"ige_ri_{p}")]

        st.write("**副露（ポン・チー・カン）**")
        old_furo = target_r.get("furo", [])
        cols_f = st.columns(4)
        new_furo = [p for i, p in enumerate(players)
                    if cols_f[i].checkbox(p, value=(p in old_furo), key=f"ige_fu_{p}")]

        st.write("**聴牌者（流局時のみ）**")
        old_tenpai = target_r.get("tenpai", [])
        cols_t = st.columns(4)
        new_tenpai = [p for i, p in enumerate(players)
                      if cols_t[i].checkbox(p, value=(p in old_tenpai), key=f"ige_te_{p}")]

        submitted = st.form_submit_button("修正内容を保存・再計算する", type="primary", use_container_width=True)

    if submitted:
        history[sel_idx]["win_type"] = new_type
        history[sel_idx]["winner"] = new_winner
        history[sel_idx]["loser"] = new_loser if new_type == "ron" else ""
        history[sel_idx]["score"] = int(new_score)
        history[sel_idx]["riichi"] = new_riichi
        history[sel_idx]["furo"] = new_furo
        history[sel_idx]["tenpai"] = new_tenpai if new_type == "ryukyoku" else []

        st.session_state.game_state.round_history = history
        st.session_state.game_state.recalculate_state()
        st.session_state.input_mode = "normal"
        st.success("局のデータを修正し、点数・本場・供託を再計算しました。")
        st.rerun()

    if st.button("キャンセル（戻る）", use_container_width=True):
        st.session_state.input_mode = "normal"
        st.rerun()



def show_endgame():
    st.title("終局")
    players = st.session_state.game_state.players
    scores = dict(st.session_state.game_state.scores)

    riichi_bonus = st.session_state.game_state.riichi_stick * 1000
    if riichi_bonus > 0:
        top_p = max(players, key=lambda p: scores[p])
        scores[top_p] += riichi_bonus
        st.info(f"供託 {st.session_state.game_state.riichi_stick}本（{riichi_bonus:,}点）を {top_p} に加算します")

    sorted_p = sorted(players, key=lambda p: scores[p], reverse=True)

    r_config = st.session_state.get("current_rule_config")
    st.subheader("最終結果")
    for i, p in enumerate(sorted_p):
        c_count = sum(1 for r in st.session_state.game_state.round_history if r.get("win_type") == "chombo" and r.get("winner") == p)
        pt = calc.calc_special_point(scores[p], i + 1, rule_config=r_config, chombo_count=c_count)
        st.write(f"{i + 1}位: **{p}**　{scores[p]:,}点　({pt:+.1f}pt)")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("記録して終了", type="primary", use_container_width=True):
            st.session_state.game_state.scores = scores
            st.session_state.game_state.riichi_stick = 0
            date_str = datetime.now().strftime("%Y-%m-%d")
            
            group_id = st.session_state.get("current_group_id", "all")
            groups = cache_utils.get_groups()
            chosen_group = next((g for g in groups if g["group_id"] == group_id), None)
            target_members_ids = chosen_group.get("members", []) if chosen_group else []
            
            player_was_group_member = {}
            for p in players:
                m_id = st.session_state.get("player_member_ids", {}).get(p)
                player_was_group_member[p] = 1 if (m_id and m_id in target_members_ids) else 0
                
            game_id = db.save_game(
                date_str, scores, players, local=db.IS_LOCAL,
                rule_id=st.session_state.get("current_rule_id", "m_league"),
                group_id=group_id,
                rule_config=r_config,
                player_member_ids=st.session_state.get("player_member_ids"),
                player_was_group_member=player_was_group_member
            )
            for r in st.session_state.game_state.round_history:
                multi_wins_json = None
                if "multi_wins" in r and r["multi_wins"]:
                    multi_wins_json = json.dumps(r["multi_wins"], ensure_ascii=False)
                
                db.save_round(game_id, r["kyoku_name"], r.get("winner", ""), r.get("loser", ""),
                              r.get("score", 0), r.get("furo", []), r.get("riichi", []),
                              win_type=r.get("win_type", ""),
                              tenpai=r.get("tenpai", []),
                              multi_wins_json=multi_wins_json,
                              local=db.IS_LOCAL)
            st.cache_data.clear()
            result_rows = []
            for i, p in enumerate(sorted_p):
                c_count = sum(1 for r in st.session_state.game_state.round_history if r.get("win_type") == "chombo" and r.get("winner") == p)
                result_rows.append({
                    "rank": i + 1, 
                    "name": p, 
                    "score": scores[p],
                    "pt": calc.calc_special_point(scores[p], i + 1, rule_config=r_config, chombo_count=c_count)
                })
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
