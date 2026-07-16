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

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["エクスポート", "CSV取込", "スコア修正", "試合削除", "同期", "局修正"])

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
                    db.get_games_data.clear()
                    st.success(f"{count}件を取込みました。")
                    st.rerun()
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

    with tab3:
        st.subheader("スコア修正")
        df_games = db.load_all_games()
        if df_games.empty:
            st.info("記録がありません。")
        else:
            def game_label(row):
                return f"#{int(row['game_id'])} {row['date']}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

            options = {int(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
            sel_id = st.selectbox("試合を選択", list(options.keys()),
                                  format_func=lambda x: options[x], key="edit_game_id")
            row = df_games[df_games['game_id'] == sel_id].iloc[0]
            new_scores = {}
            for i in range(1, 5):
                name = row[f'p{i}_name']
                new_scores[name] = st.number_input(
                    name, value=int(row[f'p{i}_score']), step=100, key=f"edit_score_{i}")
            total = sum(new_scores.values())
            ok = (total == 100000)
            st.caption(f"合計: {total:,}点")
            if st.button("保存", type="primary", disabled=not ok, use_container_width=True):
                db.update_game_scores(sel_id, new_scores)
                db.get_games_data.clear()
                st.success("保存しました。")
                st.rerun()

    with tab4:
        st.subheader("試合削除")
        df_games = db.load_all_games()
        if df_games.empty:
            st.info("記録がありません。")
        else:
            def game_label(row):
                return f"#{int(row['game_id'])} {row['date']}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

            options = {int(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
            sel_id = st.selectbox("削除する試合を選択", list(options.keys()),
                                  format_func=lambda x: options[x], key="del_game_id")
            row = df_games[df_games['game_id'] == sel_id].iloc[0]
            for i in range(1, 5):
                rank = int(row.get(f'p{i}_rank', i))
                st.write(f"{rank}位: {row[f'p{i}_name']}  {int(row[f'p{i}_score']):,}点")
            confirm_input = st.text_input(
                f"削除確認：ゲームID「{int(sel_id)}」を入力してください",
                placeholder=str(int(sel_id)), key="del_confirm_id"
            )
            confirmed = confirm_input.strip() == str(int(sel_id))
            if st.button("この試合を削除", type="primary",
                         disabled=not confirmed, use_container_width=True):
                db.delete_game(int(sel_id))
                db.get_games_data.clear()
                db.get_rounds_data.clear()
                st.success(f"Game #{sel_id} を削除しました。")
                st.rerun()

    with tab5:
        st.subheader("Supabaseへの同期")
        if not db.IS_LOCAL:
            st.info("同期機能はローカル起動時のみ使用できます。")
        else:
            pending_now = db.get_pending_count()
            if pending_now == 0:
                st.success("未同期のデータはありません。")
            else:
                st.warning(f"未同期の試合: {pending_now}件")
                if st.session_state.get("online", True):
                    if st.button("今すぐ同期する", type="primary", use_container_width=True):
                        try:
                            n = db.sync_to_supabase()
                            db.get_games_data.clear()
                            db.get_rounds_data.clear()
                            st.success(f"{n}件の試合をSupabaseに同期しました。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"同期に失敗しました: {e}")
                else:
                    st.info("オンラインになってから同期してください。")

    with tab6:
        show_round_edit()

    if st.button("戻る", use_container_width=True):
        st.session_state.view = "setup"
        st.rerun()
