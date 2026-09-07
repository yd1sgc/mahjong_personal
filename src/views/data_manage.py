import streamlit as st
def _set_view(v):
    import streamlit as st
    st.session_state.view = v

import pandas as pd
import database2 as db
from views.round_edit import show_round_edit


def show_data_manage():
    st.title("データ管理")
    
    _, c_center, _ = st.columns([1, 2, 1])
    with c_center:
        st.button(" ホーム", use_container_width=True, key="data_back_home", on_click=_set_view, args=("home",))
    
    st.divider()
    
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
        df_games = db.get_games_data()
        if df_games.empty:
            st.info("記録がありません。")
        else:
            def game_label(row):
                gid_short = str(row['game_id'])[:8]
                d = row.get('date', '')
                d_str = d.strftime('%Y-%m-%d') if pd.notna(d) and hasattr(d, 'strftime') else str(d)[:10]
                return f"[{gid_short}] {d_str}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

            options = {r['game_id']: game_label(r) for _, r in df_games.iterrows()}
            sel_id = st.selectbox("対象の試合を選択してください", list(options.keys()),
                                  format_func=lambda x: options[x], key="edit_dm_game_id")

            action_mode = st.radio(
                "操作項目を選択",
                ["① 試合データの削除"],
                horizontal=True,
                key="dm_action_mode"
            )

            row = df_games[df_games['game_id'] == sel_id].iloc[0]

            if action_mode == "① 試合データの削除":
                st.warning("⚠️ この試合をローカル端末から削除します。（※オンラインにバックアップがある場合、オンライン側のデータは保護されます）")
                for i in range(1, 5):
                    rank = int(row.get(f'p{i}_rank', i))
                    st.write(f"{rank}位: {row[f'p{i}_name']}  {int(row[f'p{i}_score']):,}点")
                
                short_id = str(sel_id)[:8]
                confirm_input = st.text_input(
                    f"削除確認：ID先頭8文字「{short_id}」を入力してください",
                    placeholder=short_id, key="del_confirm_id"
                )
                confirmed = confirm_input.strip() == short_id
                if st.button("この試合をローカルから削除する", type="primary",
                             disabled=not confirmed, use_container_width=True):
                    db.delete_game(str(sel_id))
                    st.cache_data.clear()
                    st.success(f"Game [{short_id}] をローカルから削除しました。")
                    st.rerun()

    with tab4:
        st.subheader("オンライン（Supabase）との双方向同期")
        if not db.IS_LOCAL:
            st.info("同期機能はローカル端末での起動時のみ使用できます。")
        else:
            status = db.get_sync_status_summary()
            pending_push = status.get("pending_push", 0)
            local_only = status.get("local_only", 0)
            synced = status.get("synced", 0)

            c_s1, c_s2, c_s3 = st.columns(3)
            with c_s1:
                st.metric("オンライン未送信", f"{pending_push}件")
            with c_s2:
                st.metric("ローカル限定", f"{local_only}件")
            with c_s3:
                st.metric("同期済み", f"{synced}件")

            st.caption("※メンバー・グループ・ルールは常に双方向で自動マージされます。オンライン上の対局はすべてローカルへ取り込まれます。")

            st.divider()

            if st.session_state.get("online", True):
                if st.button("🔄 今すぐ全体同期を実行する（Pull & Push）", type="primary", use_container_width=True):
                    try:
                        res = db.sync_all()
                        st.cache_data.clear()
                        st.success(f"同期完了！ オンラインから {res.get('pulled', 0)}件 取得、オンラインへ {res.get('pushed', 0)}件 送信しました。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"同期に失敗しました: {e}")
            else:
                st.info("オンライン接続時に同期を実行してください。")

            if pending_push > 0:
                if st.button("未送信データを送信スキップ（完了扱い）にする", use_container_width=True):
                    db.mark_as_synced()
                    st.cache_data.clear()
                    st.success("未送信データを送信完了扱いに更新しました。")
                    st.rerun()



    st.button("戻る", use_container_width=True, on_click=_set_view, args=("setup",))
