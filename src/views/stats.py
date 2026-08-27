import cache_utils
import streamlit as st
def _set_view(v):
    import streamlit as st
    st.session_state.view = v

import pandas as pd
import database2 as db
import calc


def show_stats():
    c_t1, c_t2 = st.columns([2, 2])
    with c_t1:
        st.title("成績")
    with c_t2:
        st.markdown("<div style='margin-top: 1.2rem;'>", unsafe_allow_html=True)
        if st.button(" ホーム画面へ", type="primary", use_container_width=True, key="top_to_home"):
            st.session_state.view = "home"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    df_all = cache_utils.get_games_data()

    # ── フィルター選択エリア ─────────────────────────────────
    groups = cache_utils.get_groups()
    rules = cache_utils.get_rule_templates(include_archived=True)
    
    def _stats_rule_label(r):
        if r.get("rule_id") == "all":
            return r["rule_name"]
        tag = "公式" if r.get("kind") == "official" else "カスタム"
        return f"【{tag}】{r['rule_name']}"

    rule_map = {r["rule_id"]: _stats_rule_label(r) for r in rules}

    grp_options = [{"group_id": "all", "group_name": "全グループ (全体)", "members": []}] + groups
    rule_options = [{"rule_id": "all", "rule_name": "全ルール (全体)", "kind": "all"}] + rules

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        sel_grp_name = st.selectbox(" グループ", [g["group_name"] for g in grp_options], key="stats_grp_sel")
        chosen_grp = next((g for g in grp_options if g["group_name"] == sel_grp_name), grp_options[0])
    with col_f2:
        rule_disp_names = [_stats_rule_label(r) for r in rule_options]
        sel_rule_disp = st.selectbox(" ルール", rule_disp_names, key="stats_rule_sel")
        chosen_rule = next((r for r in rule_options if _stats_rule_label(r) == sel_rule_disp), rule_options[0])

    col_f3, col_f4 = st.columns(2)
    with col_f3:
        year_options = ["全期間"]
        if not df_all.empty and 'date' in df_all.columns:
            years = sorted(df_all['date'].dt.year.dropna().unique().astype(int), reverse=True)
            year_options += [str(y) for y in years]
        selected_year = st.selectbox("集計期間", year_options, key="stats_year")
    with col_f4:
        st.markdown("<div style='margin-top: 1.6rem;'>", unsafe_allow_html=True)
        include_guests = st.checkbox(" ゲストも表示する", value=(chosen_grp["group_id"] == "all"), key="stats_include_guests")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    df_games = cache_utils.get_games_data(year_filter=selected_year)
    df_rounds = cache_utils.get_rounds_data()

    # ルールおよびグループでの対局データ絞り込み (DBカラムが存在する場合)
    if not df_games.empty:
        if chosen_rule["rule_id"] != "all" and "rule_id" in df_games.columns:
            df_games = df_games[df_games["rule_id"] == chosen_rule["rule_id"]]
        if chosen_grp["group_id"] != "all" and "group_id" in df_games.columns:
            df_games = df_games[df_games["group_id"] == chosen_grp["group_id"]]

    if df_games.empty:
        st.info("条件に一致する対局記録がありません。")
        if st.button(" ホーム画面へ", type="primary", use_container_width=True, key="empty_to_home"):
            st.session_state.view = "home"
            st.rerun()
        return

    all_names = pd.unique(df_games[['p1_name', 'p2_name', 'p3_name', 'p4_name']].values.ravel('K'))
    real_members = sorted([p for p in all_names if pd.notna(p) and str(p).strip()])

    game_stats, round_stats, n_round_games = calc.analyze_stats(df_games, df_rounds)

    # グループメンバーによる成績表フィルタリング (ゲスト非表示時)
    if chosen_grp["group_id"] != "all" and not include_guests:
        valid_games = []
        # フォールバック用に現在のメンバー名を取得
        all_members = cache_utils.get_all_members()
        id_to_name = {m["member_id"]: m["member_name"] for m in all_members}
        grp_mems_names = set(id_to_name[m_id] for m_id in chosen_grp.get("members", []) if m_id in id_to_name)
        
        for _, row in df_games.iterrows():
            is_all_members = True
            for i in range(1, 5):
                p_name = row.get(f"p{i}_name")
                if pd.isna(p_name) or not str(p_name).strip():
                    continue
                
                was_member = row.get(f"p{i}_was_group_member")
                if pd.notna(was_member):
                    if int(was_member) == 0:
                        is_all_members = False
                        break
                else:
                    # pX_was_group_member が未設定（過去データ等）の場合は現在のメンバーで判定
                    if p_name not in grp_mems_names:
                        is_all_members = False
                        break
                        
            if is_all_members:
                valid_games.append(row["game_id"])
        
        df_games = df_games[df_games["game_id"].isin(valid_games)]
        
        # 再計算
        game_stats, round_stats, n_round_games = calc.analyze_stats(df_games, df_rounds)

    chombo_counts = calc.get_chombo_counts(df_rounds)
    df_sorted = df_games.sort_values("game_id").reset_index(drop=True)
    rows = []
    for _, row in df_sorted.iterrows():
        cfg = None
        rule_json = row.get("applied_rule_json")
        if pd.notna(rule_json) and isinstance(rule_json, str) and rule_json.strip():
            try:
                import json
                cfg = json.loads(rule_json)
            except Exception:
                cfg = None

        for i in range(1, 5):
            name = row.get(f"p{i}_name")
            if pd.isna(name) or not str(name).strip():
                continue
            score = int(row[f"p{i}_score"])
            rank = int(row[f"p{i}_rank"])
            n_str = str(name).strip()
            c_count = chombo_counts.get((row["game_id"], n_str), 0)
            rows.append({
                "game_id": row["game_id"],
                "date": row["date"],
                "name": n_str,
                "score": score,
                "rank": rank,
                "pt": calc.calc_special_point(score, rank, rule_config=cfg, chombo_count=c_count),
            })
    df_results = pd.DataFrame(rows, columns=["game_id", "date", "name", "score", "rank", "pt"])

    # ── 試合成績テーブル ──────────────────────────────────
    if not game_stats.empty:
        st.subheader("試合成績")
        game_cols = ["名前", "試合数", "総合pt", "オカなし総合pt", "平均順位",
                     "連対率", "ラス回避率", "1着率", "2着率", "3着率", "4着率"]
        show_cols = [c for c in game_cols if c in game_stats.columns]
        st.dataframe(
            game_stats[show_cols].sort_values("総合pt", ascending=False),
            use_container_width=True, hide_index=True,
        )

    # ── 詳細成績テーブル (5タブ分割: コンパクトUI) ─────────
    if not round_stats.empty:
        st.subheader(f"詳細成績（詳細記録 {n_round_games}試合を集計）")
        tab_basic, tab_datan, tab_syubi, tab_riichi, tab_furo = st.tabs([
            "基本", "打点", "守備", "立直", "副露"
        ])

        with tab_basic:
            cols = ["名前", "局数", "和了率", "ツモ率", "放銃率", "和銃差", "流局時聴牌率", "ノーテン罰符収支", "供託収支"]
            show_cols = [c for c in cols if c in round_stats.columns]
            st.dataframe(
                round_stats[show_cols].sort_values("和了率", ascending=False),
                use_container_width=True, hide_index=True,
            )

        with tab_datan:
            cols = ["名前", "平均和了", "立直平均打点", "副露平均打点", "ダマ平均打点", "打点効率"]
            show_cols = [c for c in cols if c in round_stats.columns]
            st.dataframe(
                round_stats[show_cols].sort_values("平均和了", ascending=False),
                use_container_width=True, hide_index=True,
            )

        with tab_syubi:
            cols = ["名前", "放銃率", "被リーチ放銃率", "被副露放銃率", "被ダマ放銃率", "平均放銃"]
            show_cols = [c for c in cols if c in round_stats.columns]
            st.dataframe(
                round_stats[show_cols].sort_values("放銃率", ascending=True),
                use_container_width=True, hide_index=True,
            )

        with tab_riichi:
            cols = ["名前", "リーチ率", "立直和了率", "立直放銃率"]
            show_cols = [c for c in cols if c in round_stats.columns]
            st.dataframe(
                round_stats[show_cols].sort_values("立直和了率", ascending=False),
                use_container_width=True, hide_index=True,
            )

        with tab_furo:
            cols = ["名前", "副露率", "副露和了率", "副露放銃率", "ダマ和了率"]
            show_cols = [c for c in cols if c in round_stats.columns]
            st.dataframe(
                round_stats[show_cols].sort_values("副露率", ascending=False),
                use_container_width=True, hide_index=True,
            )

    # ── 総合ポイント推移グラフ ────────────────────────────
    st.divider()
    st.subheader("総合ポイント推移")
    game_ids_sorted = df_sorted["game_id"].tolist()
    df_pivot = (
        df_results.pivot_table(index="game_id", columns="name", values="pt", aggfunc="sum")
        .reindex(game_ids_sorted)
        .fillna(0)
    )
    df_cumsum = df_pivot.cumsum()
    df_cumsum.index = [f"G{i+1:03}" for i in range(len(game_ids_sorted))]
    zero_row = pd.DataFrame(0, index=["G000"], columns=df_cumsum.columns)
    df_chart = pd.concat([zero_row, df_cumsum])

    top5 = game_stats.sort_values("総合pt", ascending=False)['名前'].tolist()[:5] if not game_stats.empty else []
    default_sel = [m for m in top5 if m in df_chart.columns]
    selected = st.multiselect("表示メンバー", options=real_members,
                              default=default_sel, key="chart_sel")
    if selected:
        st.line_chart(df_chart[[c for c in selected if c in df_chart.columns]])

    # ── レコード ──────────────────────────────────────────
    st.divider()
    st.subheader("レコード")
    df_scores_all = (
        df_results
        .assign(日付=df_results["date"].apply(
            lambda d: d.strftime('%Y-%m-%d') if pd.notna(d) else "日付不明"
        ))
        [["name", "score", "日付"]]
        .rename(columns={"name": "名前", "score": "点数"})
    )

    c1, c2 = st.columns(2)
    with c1:
        st.caption("最高スコア Top5")
        st.dataframe(df_scores_all.sort_values('点数', ascending=False).head(5).reset_index(drop=True),
                     hide_index=True, use_container_width=True)
        st.caption("最低スコア Top5")
        st.dataframe(df_scores_all.sort_values('点数').head(5).reset_index(drop=True),
                     hide_index=True, use_container_width=True)
    with c2:
        st.caption("連勝記録（2連勝以上）")
        streak_data = []
        for p in real_members:
            p_ranks = df_results[df_results["name"] == p].sort_values("game_id")["rank"]
            max_streak = cur = 0
            for rank in p_ranks:
                if rank == 1:
                    cur += 1
                    max_streak = max(max_streak, cur)
                else:
                    cur = 0
            if max_streak >= 2:
                streak_data.append({'名前': p, '最大連勝': max_streak})
        if streak_data:
            df_streak = pd.DataFrame(streak_data).sort_values('最大連勝', ascending=False).reset_index(drop=True)
            st.dataframe(df_streak, hide_index=True, use_container_width=True)
        else:
            st.info("2連勝以上の記録はまだありません")

    # ── 相性マトリクス ────────────────────────────────────
    st.divider()
    st.subheader("相性マトリクス（直接対決）")
    st.caption("行: 自分 / 列: 相手（同卓時のpt差合計） 青: 得意 / 赤: 苦手")
    df_m = df_results[df_results["name"].isin(real_members)][["game_id", "name", "pt"]]
    df_pairs = (
        df_m.merge(df_m, on="game_id", suffixes=("_me", "_enemy"))
        .query("name_me != name_enemy")
        .assign(diff=lambda d: d["pt_me"] - d["pt_enemy"])
    )
    df_matrix = (
        df_pairs.groupby(["name_me", "name_enemy"])["diff"].sum()
        .unstack(fill_value=0)
        .reindex(index=real_members, columns=real_members, fill_value=0)
    )
    default_matrix = real_members[:5] if len(real_members) >= 5 else real_members
    target = st.multiselect("分析対象", options=real_members,
                            default=default_matrix, key="matrix_sel")
    if target:
        df_show_matrix = df_matrix.loc[target, target]
        st.dataframe(
            df_show_matrix.style.background_gradient(cmap='coolwarm_r', axis=None).format("{:+.1f}"),
            use_container_width=True,
        )

    # ── 対局履歴 ──────────────────────────────────────────
    st.divider()
    st.subheader("対局履歴")

    df_unsynced = db.get_local_unsynced_games()
    if not df_unsynced.empty:
        st.warning(f"未同期のデータが {len(df_unsynced)} 件あります（データ管理 → 同期タブから送信できます）")
        df_unsynced['date'] = pd.to_datetime(df_unsynced['date'], format='mixed', errors='coerce')
        unsync_rows = []
        for _, row in df_unsynced.iterrows():
            players = sorted(
                [(row[f'p{i}_rank'], row[f'p{i}_name'], row[f'p{i}_score'],
                  calc.calc_special_point(row[f'p{i}_score'], row[f'p{i}_rank']))
                 for i in range(1, 5)],
                key=lambda x: x[0]
            )
            d = row['date']
            date_str = d.strftime('%Y-%m-%d') if pd.notna(d) else "日付不明"
            unsync_rows.append({
                "日付": date_str,
                "1位": f"{players[0][1]} ({players[0][3]:+.1f})",
                "2位": f"{players[1][1]} ({players[1][3]:+.1f})",
                "3位": f"{players[2][1]} ({players[2][3]:+.1f})",
                "4位": f"{players[3][1]} ({players[3][3]:+.1f})",
            })
        st.dataframe(pd.DataFrame(unsync_rows), use_container_width=True, hide_index=True)
        st.divider()

    history_rows = []
    for gid, g in df_results.groupby("game_id"):
        g_sorted = g.sort_values("rank").reset_index(drop=True)
        if len(g_sorted) < 4:
            continue
        d = g_sorted.iloc[0]["date"]
        history_rows.append({
            "#": int(gid),
            "日付": d.strftime('%Y-%m-%d') if pd.notna(d) else "日付不明",
            "1位": f"{g_sorted.iloc[0]['name']} ({g_sorted.iloc[0]['pt']:+.1f})",
            "2位": f"{g_sorted.iloc[1]['name']} ({g_sorted.iloc[1]['pt']:+.1f})",
            "3位": f"{g_sorted.iloc[2]['name']} ({g_sorted.iloc[2]['pt']:+.1f})",
            "4位": f"{g_sorted.iloc[3]['name']} ({g_sorted.iloc[3]['pt']:+.1f})",
        })
    df_history = pd.DataFrame(sorted(history_rows, key=lambda r: r["#"], reverse=True))
    st.dataframe(df_history, use_container_width=True, hide_index=True)

    # ── 複数試合の合計集計 ────────────────────────────────
    st.divider()
    st.subheader("選択試合の合計集計")
    all_game_ids = df_games.sort_values("game_id", ascending=False)["game_id"].tolist()
    def _format_game_id(gid):
        rows = df_history[df_history['#'] == int(gid)]
        if rows.empty:
            return f"#{int(gid)}  データ不明"
        return f"#{int(gid)}  {rows['日付'].values[0]}  {rows['1位'].values[0]}"

    selected_ids = st.multiselect(
        "集計するゲームIDを選択",
        options=all_game_ids,
        format_func=_format_game_id,
        key="agg_game_ids",
    )
    if selected_ids:
        df_sel = df_results[df_results["game_id"].isin(selected_ids)]
        df_agg = (
            df_sel.groupby("name")
            .agg(合計pt=("pt", "sum"), 参加試合数=("game_id", "count"))
            .reset_index()
            .rename(columns={"name": "名前"})
            .sort_values("合計pt", ascending=False)
        )
        df_agg["合計pt"] = df_agg["合計pt"].apply(lambda x: f"{x:+.1f}")
        st.caption(f"{len(selected_ids)}試合の合計")
        st.dataframe(df_agg, use_container_width=True, hide_index=True)

    if st.button(" ホーム画面へ", type="primary", use_container_width=True, key="bottom_to_home"):
        st.session_state.view = "home"
        st.rerun()
