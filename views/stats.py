import streamlit as st
import pandas as pd
import database2 as db
import calc


def show_stats():
    st.title("成績")
    df_all = db.get_games_data()

    year_options = ["全期間"]
    if not df_all.empty and 'date' in df_all.columns:
        years = sorted(df_all['date'].dt.year.dropna().unique().astype(int), reverse=True)
        year_options += [str(y) for y in years]
    selected_year = st.selectbox("集計期間", year_options, key="stats_year")

    df_games = db.get_games_data(year_filter=selected_year)
    df_rounds = db.get_rounds_data()

    if df_games.empty:
        st.info("記録がまだありません。対局を終局・記録すると反映されます。")
        if st.button("戻る", use_container_width=True):
            st.session_state.view = "setup"
            st.rerun()
        return

    all_names = pd.unique(df_games[['p1_name', 'p2_name', 'p3_name', 'p4_name']].values.ravel('K'))
    real_members = sorted([p for p in all_names if pd.notna(p) and str(p).strip()])

    game_stats, round_stats, n_round_games = calc.analyze_stats(df_games, df_rounds)

    df_sorted = df_games.sort_values("game_id").reset_index(drop=True)
    rows = []
    for _, row in df_sorted.iterrows():
        for i in range(1, 5):
            name = row.get(f"p{i}_name")
            if pd.isna(name) or not str(name).strip():
                continue
            score = int(row[f"p{i}_score"])
            rank = int(row[f"p{i}_rank"])
            rows.append({
                "game_id": row["game_id"],
                "date": row["date"],
                "name": str(name).strip(),
                "score": score,
                "rank": rank,
                "pt": calc.calc_special_point(score, rank),
            })
    df_results = pd.DataFrame(rows)

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

    # ── 詳細成績テーブル ──────────────────────────────────
    if not round_stats.empty:
        st.subheader(f"詳細成績（詳細記録 {n_round_games}試合を集計）")
        round_cols = ["名前", "和了率", "ツモ率", "放銃率", "副露率", "リーチ率",
                      "リーチ成功率", "テンパイ率", "平均和了", "平均放銃"]
        show_cols = [c for c in round_cols if c in round_stats.columns]
        st.dataframe(
            round_stats[show_cols].sort_values("和了率", ascending=False),
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
    st.caption("行が自分、列が相手。数値は同卓時のpt差合計。赤=得意、青=苦手。")
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
    selected_ids = st.multiselect(
        "集計するゲームIDを選択",
        options=all_game_ids,
        format_func=lambda gid: f"#{int(gid)}  {df_history[df_history['#']==int(gid)]['日付'].values[0]}  {df_history[df_history['#']==int(gid)]['1位'].values[0]}",
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

    if st.button("戻る", use_container_width=True):
        st.session_state.view = "setup"
        st.rerun()
