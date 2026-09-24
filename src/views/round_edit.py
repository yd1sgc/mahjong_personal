import json
import streamlit as st
import pandas as pd
import database2 as db
import game_logic
from game_logic import GameState
import calc


def _restore_game_state_from_db(game_dict: dict):
    """DBの詳細対局辞書から GameState オブジェクトを復元する（ダブロン・チョンボ完全対応）。"""
    parts = sorted(game_dict.get("participants", []), key=lambda x: x.get("seat", 1))
    players = [p.get("player_name_snapshot") or f"P{p.get('seat', 1)}" for p in parts]
    player_member_ids = {p.get("player_name_snapshot"): p.get("member_id") for p in parts}
    player_was_group_member = {p.get("player_name_snapshot"): p.get("was_group_member", 1) for p in parts}
    seat_to_name = {p.get("seat", idx + 1): (p.get("player_name_snapshot") or f"P{p.get('seat', idx + 1)}") for idx, p in enumerate(parts)}

    rule_cfg = game_dict.get("rule_config_snapshot") or {}
    if isinstance(rule_cfg, str):
        try:
            rule_cfg = json.loads(rule_cfg)
        except Exception:
            rule_cfg = {}

    init_score = rule_cfg.get("basic", {}).get("init_score", 25000)
    game_state = GameState(players, init_score, rule_cfg)

    round_history = []
    for r in sorted(game_dict.get("rounds", []), key=lambda x: x.get("round_index", 0)):
        seats = sorted(r.get("seats", []), key=lambda x: x.get("seat", 1))

        winners = [seat_to_name.get(s.get("seat")) for s in seats if s.get("is_winner") == 1]
        loser = next((seat_to_name.get(s.get("seat")) for s in seats if s.get("is_loser") == 1), "")
        riichi = [seat_to_name.get(s.get("seat")) for s in seats if s.get("is_riichi") == 1]
        furo = [seat_to_name.get(s.get("seat")) for s in seats if s.get("is_furo") == 1]
        tenpai = [seat_to_name.get(s.get("seat")) for s in seats if s.get("is_tenpai") == 1]

        raw_type = r.get("result_type", "ron")
        multi_wins = []

        if len(winners) >= 2 or raw_type == "multi_ron":
            w_type = "multi_ron"
            for s in seats:
                if s.get("is_winner") == 1:
                    pname = seat_to_name.get(s.get("seat"))
                    multi_wins.append({
                        "winner": pname,
                        "points_data": {"total": int(s.get("base_point", 0))}
                    })
            score_val = 0
            winner_val = ""
        elif len(winners) == 1:
            w_type = raw_type if raw_type in ("ron", "tsumo") else "ron"
            winner_val = winners[0]
            score_val = next((int(s.get("base_point", 0)) for s in seats if s.get("is_winner") == 1), 0)
        elif raw_type == "chombo":
            w_type = "chombo"
            winner_val = loser or (winners[0] if winners else "")
            score_val = next((abs(int(s.get("penalty_point", 0))) for s in seats if s.get("penalty_point", 0) != 0), 8000)
        else:
            w_type = raw_type
            winner_val = ""
            score_val = 0

        round_history.append({
            "kyoku_name": r.get("kyoku_name", "東1局"),
            "win_type": w_type,
            "winner": winner_val,
            "loser": loser,
            "score": score_val,
            "riichi": riichi,
            "furo": furo,
            "tenpai": tenpai,
            "multi_wins": multi_wins,
            "honba": int(r.get("honba", 0)),
            "starting_riichi_sticks": int(r.get("riichi_sticks", 0))
        })

    game_state.round_history = round_history
    game_state.recalculate_state()

    return game_state, players, player_member_ids, player_was_group_member, rule_cfg


def show_round_edit(selected_game_id=None):
    st.subheader("過去対局の局修正")
    st.caption("局の結果や点数を修正すると、それ以降の本場・供託・最終持ち点・着順・ptが自動連鎖再計算されます。")

    df_games = db.load_all_games()
    if df_games.empty:
        st.info("記録がありません。")
        return

    def game_label(row):
        gid_short = str(row['game_id'])[:8]
        d = row.get('date', '')
        d_str = d.strftime('%Y-%m-%d') if pd.notna(d) and hasattr(d, 'strftime') else str(d)[:10]
        return f"[{gid_short}] {d_str}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

    options = {str(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
    opt_keys = list(options.keys())

    default_idx = 0
    if selected_game_id and str(selected_game_id) in opt_keys:
        default_idx = opt_keys.index(str(selected_game_id))

    sel_id = st.selectbox("試合を選択してください", opt_keys, index=default_idx,
                          format_func=lambda x: options[x], key="re_v2_game_id")

    game_dict = db.get_game_details(sel_id)
    if not game_dict:
        st.error("指定された試合データが見つかりません。")
        return

    rounds_in_db = game_dict.get("rounds", [])
    if not rounds_in_db:
        st.warning("この対局には局ごとの詳細記録がありません（シンプル入力または旧データ）。「基本情報の編集」をご利用ください。")
        return

    game_state, players, player_member_ids, player_was_group_member, rule_cfg = _restore_game_state_from_db(game_dict)

    # 1. 局一覧テーブル表示
    table_rows = []
    for idx, r in enumerate(game_state.round_history):
        w_type = r.get("win_type", "")
        if w_type == "multi_ron":
            type_label = "ダブロン"
            winner_str = ", ".join(f"{w['winner']}({w['points_data']['total']:,})" for w in r.get("multi_wins", []))
            score_str = "-"
        elif w_type == "ron":
            type_label = "ロン"
            winner_str = r.get("winner", "")
            score_str = f"{r.get('score', 0):,}点"
        elif w_type == "tsumo":
            type_label = "ツモ"
            winner_str = r.get("winner", "")
            score_str = f"{r.get('score', 0):,}点"
        elif w_type == "chombo":
            type_label = "チョンボ"
            winner_str = r.get("winner", "")
            score_str = f"{r.get('score', 0):,}点"
        else:
            type_label = "流局"
            winner_str = "-"
            score_str = "-"

        table_rows.append({
            "局": f"{r.get('kyoku_name')} {r.get('honba', 0)}本場",
            "種別": type_label,
            "和了者": winner_str,
            "放銃者": r.get("loser", "") or "-",
            "基本点": score_str,
            "供託本数": r.get("starting_riichi_sticks", 0),
            "リーチ": ", ".join(r.get("riichi", [])) or "-",
            "副露": ", ".join(r.get("furo", [])) or "-",
            "聴牌": ", ".join(r.get("tenpai", [])) or "-"
        })

    st.write("▼ 局履歴一覧")
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    # 2. 修正対象局の選択
    round_labels = {
        i: f"{r.get('kyoku_name')} {r.get('honba', 0)}本場 ({table_rows[i]['種別']}: {table_rows[i]['和了者']})"
        for i, r in enumerate(game_state.round_history)
    }
    sel_idx = st.selectbox("修正する局を選択してください", list(round_labels.keys()),
                           format_func=lambda x: round_labels[x], key="re_v2_round_idx")

    target_r = game_state.round_history[sel_idx]

    st.divider()
    st.write(f"#### 局の修正フォーム: {round_labels[sel_idx]}")

    type_options = ["ron", "tsumo", "multi_ron", "ryukyoku", "chombo"]
    type_names = {"ron": "ロン", "tsumo": "ツモ", "multi_ron": "ダブロン", "ryukyoku": "流局", "chombo": "チョンボ"}

    cur_type = target_r.get("win_type", "ron")
    if cur_type not in type_options:
        cur_type = "ryukyoku"

    with st.form("round_edit_form_v2"):
        c1, c2 = st.columns(2)
        with c1:
            new_type = st.selectbox(
                "和了・精算種別", type_options,
                index=type_options.index(cur_type),
                format_func=lambda x: type_names[x],
                key="re_form_type"
            )

        with c2:
            p_opts = [""] + players
            cur_loser = target_r.get("loser", "")
            loser_disabled = (new_type in ("tsumo", "ryukyoku"))
            new_loser = st.selectbox(
                "放銃者（ロン・ダブロン時のみ）", p_opts,
                index=p_opts.index(cur_loser) if cur_loser in p_opts else 0,
                disabled=loser_disabled,
                key="re_form_loser"
            )

        new_multi_wins = []
        new_winner = ""
        new_score = 0

        # 和了者・点数入力
        if new_type == "multi_ron":
            st.write("**ダブロン和了者と各和了点数（基本点・本場除く）**")
            existing_multi = {w["winner"]: w["points_data"]["total"] for w in target_r.get("multi_wins", [])}
            c_cols = st.columns(4)
            for i, p in enumerate(players):
                with c_cols[i]:
                    is_w = st.checkbox(f"{p} 和了", value=(p in existing_multi), key=f"re_mw_chk_{p}")
                    if is_w:
                        pts = st.number_input(f"{p} 点数", value=int(existing_multi.get(p, 8000)), step=100, key=f"re_mw_pts_{p}")
                        new_multi_wins.append({
                            "winner": p,
                            "points_data": {"total": int(pts)}
                        })
        elif new_type in ("ron", "tsumo", "chombo"):
            c3, c4 = st.columns(2)
            with c3:
                cur_winner = target_r.get("winner", "")
                winner_label = "チョンボ対象者" if new_type == "chombo" else "和了者"
                new_winner = st.selectbox(
                    winner_label, players,
                    index=players.index(cur_winner) if cur_winner in players else 0,
                    key="re_form_winner"
                )
            with c4:
                cur_score = int(target_r.get("score", 8000) or 8000)
                score_label = "満貫基本点（通常8,000）" if new_type == "chombo" else "基本点数（本場除く）"
                new_score = st.number_input(score_label, value=cur_score, step=100, key="re_form_score")

        st.write("**リーチ宣言者**")
        cols_r = st.columns(4)
        old_riichi = target_r.get("riichi", [])
        new_riichi = [p for i, p in enumerate(players)
                      if cols_r[i].checkbox(p, value=(p in old_riichi), key=f"re_r_{p}")]

        st.write("**副露（ポン・チー・カン）**")
        cols_f = st.columns(4)
        old_furo = target_r.get("furo", [])
        new_furo = [p for i, p in enumerate(players)
                    if cols_f[i].checkbox(p, value=(p in old_furo), key=f"re_f_{p}")]

        st.write("**聴牌者（流局時のみ有効）**")
        cols_t = st.columns(4)
        old_tenpai = target_r.get("tenpai", [])
        new_tenpai = [p for i, p in enumerate(players)
                      if cols_t[i].checkbox(p, value=(p in old_tenpai), disabled=(new_type != "ryukyoku"), key=f"re_t_{p}")]

        submitted = st.form_submit_button("修正内容を確認する（再計算プレビュー）", type="primary", use_container_width=True)

    if submitted:
        # 新しい局情報を作成
        updated_round = dict(target_r)
        updated_round["win_type"] = new_type
        updated_round["winner"] = new_winner
        updated_round["loser"] = new_loser if new_type in ("ron", "multi_ron") else ""
        updated_round["score"] = int(new_score)
        updated_round["riichi"] = new_riichi
        updated_round["furo"] = new_furo
        updated_round["tenpai"] = new_tenpai if new_type == "ryukyoku" else []
        updated_round["multi_wins"] = new_multi_wins if new_type == "multi_ron" else []

        # クローンした GameState に適用して再計算
        test_history = [dict(r) for r in game_state.round_history]
        test_history[sel_idx] = updated_round

        test_state = GameState(players, game_state.init_score, rule_cfg)
        test_state.round_history = test_history
        test_state.recalculate_state()

        # プレビュー情報を session_state に退避
        st.session_state["re_v2_preview"] = {
            "game_id": sel_id,
            "target_idx": sel_idx,
            "updated_round": updated_round,
            "old_scores": dict(game_state.scores),
            "new_scores": dict(test_state.scores),
            "test_history": test_history,
            "test_state": test_state.to_dict(),
        }
        st.rerun()

    # 3. プレビュー表示と確定保存
    preview = st.session_state.get("re_v2_preview")
    if preview and preview.get("game_id") == sel_id and preview.get("target_idx") == sel_idx:
        st.divider()
        st.write("### スコア影響プレビュー")

        old_s = preview["old_scores"]
        new_s = preview["new_scores"]

        p_cols = st.columns(4)
        for i, p in enumerate(players):
            diff = new_s[p] - old_s[p]
            diff_str = f"({diff:+:,}点)" if diff != 0 else "(変動なし)"
            color_str = "blue" if diff > 0 else ("red" if diff < 0 else "gray")
            with p_cols[i]:
                st.metric(label=p, value=f"{new_s[p]:,}点", delta=f"{diff:+:,}点" if diff != 0 else None)

        total_new = sum(new_s.values())
        expected_total = game_state.init_score * 4
        is_zero_sum = (total_new == expected_total)

        if not is_zero_sum:
            st.error(f"持ち点合計が {total_new:,}点 となり、規定の {expected_total:,}点（ゼロサム）を満たしていません。保存できません。")
        else:
            st.success(f"持ち点合計 {total_new:,}点（ゼロサム確認済み）")

        c_save, c_cancel = st.columns(2)
        with c_save:
            if st.button("この修正内容をデータベースへ保存する", type="primary", disabled=not is_zero_sum, use_container_width=True):
                # GameState 復元
                final_state = GameState.from_dict(preview["test_state"])
                final_scores = preview["new_scores"]

                # 新しい V2 ペイロードを構築
                payload = game_logic.build_v2_game_payload(
                    game_state=final_state,
                    players=players,
                    scores=final_scores,
                    group_id=game_dict.get("group_id"),
                    rule_id=rule_cfg.get("rule_name", "standard"),
                    rule_config=rule_cfg,
                    player_member_ids=player_member_ids,
                    player_was_group_member=player_was_group_member,
                    date_str=str(game_dict.get("played_at")),
                    game_id=sel_id,
                    yakuman_list=game_dict.get("yakuman_records", [])
                )

                # 不可分置換実行
                db.update_game_record_atomic(sel_id, payload)
                st.cache_data.clear()
                del st.session_state["re_v2_preview"]
                st.success("局の修正および以降の全スコア・着順・ptの再計算を保存しました。")
                st.rerun()

        with c_cancel:
            if st.button("修正を取り消す（キャンセル）", use_container_width=True):
                del st.session_state["re_v2_preview"]
                st.rerun()
