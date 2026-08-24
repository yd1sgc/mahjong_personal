import streamlit as st
import pandas as pd
import database2 as db
from views.round_edit import show_round_edit


def show_data_manage():
    st.title("データ管理")

    if db.IS_LOCAL:
        pending = db.get_pending_count()
        if not st.session_state.get("online", True):
            st.warning(f"オフラインモード。未同期の試合: {pending}件")
        elif pending > 0:
            st.info(f"未同期の試合が {pending}件 あります。")

    tab1, tab2, tab3, tab4 = st.tabs(["エクスポート", "CSV取込", "データ編集・削除", "同期"])

    with tab1:
        st.subheader("CSVエクスポート")
        st.caption("全データをダウンロードしてバックアップできます。")

        df_games_exp = db.load_all_games()
        df_rounds_exp = db.load_all_rounds()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("試合数", len(df_games_exp))
            if not df_games_exp.empty:
                st.download_button(
                    "games.csv",
                    data=df_games_exp.to_csv(index=False).encode("utf-8-sig"),
                    file_name="mahjong_games.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
        with col2:
            st.metric("局数", len(df_rounds_exp))
            if not df_rounds_exp.empty:
                st.download_button(
                    "rounds.csv",
                    data=df_rounds_exp.to_csv(index=False).encode("utf-8-sig"),
                    file_name="mahjong_rounds.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        if df_games_exp.empty:
            st.info("エクスポートできる記録がありません。")

    with tab2:
        st.subheader("CSVファイル取込")
        st.caption("形式: game_id, date, p1_name, p1_score, p2_name, p2_score, p3_name, p3_score, p4_name, p4_score（ヘッダーなし）")
        uploaded = st.file_uploader("CSVファイルを選択", type="csv", key="csv_upload")
        if uploaded:
            try:
                df = pd.read_csv(uploaded, header=None,
                                 names=["game_id", "date",
                                        "p1_name", "p1_score",
                                        "p2_name", "p2_score",
                                        "p3_name", "p3_score",
                                        "p4_name", "p4_score"])
                st.dataframe(df.head(10), use_container_width=True)
                st.caption(f"計 {len(df)}件（先頭10件表示）")
                if st.button("取込む", type="primary", use_container_width=True):
                    count = db.import_games_from_df(df)
                    st.cache_data.clear()
                    st.success(f"{count}件を取込みました。")
                    st.rerun()
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

    with tab3:
        st.subheader("データ編集・削除")
        df_games = db.load_all_games()
        if df_games.empty:
            st.info("記録がありません。")
        else:
            def game_label(row):
                return f"#{int(row['game_id'])} {row['date']}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

            options = {int(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
            sel_id = st.selectbox("対象の試合を選択してください", list(options.keys()),
                                  format_func=lambda x: options[x], key="edit_dm_game_id")

            action_mode = st.radio(
                "操作項目を選択",
                ["① 最終スコア直接修正", "② 各局の詳細修正", "③ 試合データの削除"],
                horizontal=True,
                key="dm_action_mode"
            )

            st.divider()

            if action_mode == "① 最終スコア直接修正":
                st.caption("最終結果のスコア（点数）を直接入力して修正します。合計100,000点が必要です。")
                row = df_games[df_games['game_id'] == sel_id].iloc[0]
                new_scores = {}
                for i in range(1, 5):
                    name = row[f'p{i}_name']
                    new_scores[name] = st.number_input(
                        name, value=int(row[f'p{i}_score']), step=100, key=f"edit_score_{i}"
                    )
                total = sum(new_scores.values())
                ok = (total == 100000)
                st.caption(f"合計: {total:,}点")
                if st.button("スコアを保存", type="primary", disabled=not ok, use_container_width=True):
                    db.update_game_scores(sel_id, new_scores)
                    st.cache_data.clear()
                    st.success("スコアを保存しました。")
                    st.rerun()

            elif action_mode == "② 各局の詳細修正":
                st.caption("特定局の和了者・放銃者・点数等を修正します。最終スコアにも差分が自動反映されます。")
                show_round_edit(selected_game_id=sel_id)

            elif action_mode == "③ 試合データの削除":
                st.caption("この試合のデータを完全に削除します。")
                row = df_games[df_games['game_id'] == sel_id].iloc[0]
                for i in range(1, 5):
                    rank = int(row.get(f'p{i}_rank', i))
                    st.write(f"{rank}位: {row[f'p{i}_name']}  {int(row[f'p{i}_score']):,}点")
                confirm_input = st.text_input(
                    f"削除確認：ゲームID「{int(sel_id)}」を入力してください",
                    placeholder=str(int(sel_id)), key="del_confirm_id"
                )
                confirmed = confirm_input.strip() == str(int(sel_id))
                if st.button("この試合を削除する", type="primary",
                             disabled=not confirmed, use_container_width=True):
                    db.delete_game(int(sel_id))
                    st.cache_data.clear()
                    st.success(f"Game #{sel_id} を削除しました。")
                    st.rerun()

    with tab4:
        st.subheader("Supabaseへの同期")
        if not db.IS_LOCAL:
            st.info("同期機能はローカル起動時のみ使用できます。")
        else:
            pending_now = db.get_pending_count()
            if pending_now == 0:
                st.success("未同期のデータはありません。")
            else:
                st.warning(f"未同期の試合: {pending_now}件")
                c1, c2 = st.columns(2)
                with c1:
                    if st.session_state.get("online", True):
                        if st.button("今すぐ同期する", type="primary", use_container_width=True):
                            try:
                                n = db.sync_to_supabase()
                                st.cache_data.clear()
                                st.success(f"{n}件の試合をSupabaseに同期しました。")
                                st.rerun()
                            except Exception as e:
                                st.error(f"同期に失敗しました: {e}")
                    else:
                        st.info("オンラインになってから同期してください。")
                with c2:
                    if st.button("送信せずに完了扱いにする（スキップ）", use_container_width=True):
                        db.mark_as_synced()
                        st.cache_data.clear()
                        st.success("未同期のデータを送信スキップ（完了扱い）にしました。")
                        st.rerun()


    if st.button("戻る", use_container_width=True):
        st.session_state.view = "setup"
        st.rerun()
