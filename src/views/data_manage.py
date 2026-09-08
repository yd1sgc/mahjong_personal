import json
from datetime import datetime, time
import pandas as pd
import streamlit as st
import database2 as db
import cache_utils
import calc
from views.round_edit import show_round_edit


def _set_view(v):
    st.session_state.view = v


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

    # ── TAB 1: エクスポート ─────────────────────────────────────
    with tab1:
        st.subheader("CSVエクスポート")
        st.caption("全対局一覧および全局座席別実績データをダウンロードしてバックアップできます。")

        df_games_exp = db.load_all_games()
        df_rounds_exp = db.load_all_rounds()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("試合数", len(df_games_exp))
            if not df_games_exp.empty:
                st.download_button(
                    "対局一覧CSV (games.csv)",
                    data=df_games_exp.to_csv(index=False).encode("utf-8-sig"),
                    file_name="mahjong_games.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
        with col2:
            st.metric("局実績レコード数", len(df_rounds_exp))
            if not df_rounds_exp.empty:
                st.download_button(
                    "詳細局実績CSV (rounds.csv)",
                    data=df_rounds_exp.to_csv(index=False).encode("utf-8-sig"),
                    file_name="mahjong_rounds.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        if df_games_exp.empty:
            st.info("エクスポートできる記録がありません。")

    # ── TAB 2: CSV取込 ──────────────────────────────────────────
    with tab2:
        st.subheader("CSVファイル取込")
        if not db.IS_LOCAL:
            st.warning("⚠️ CSVファイル取込は、正本であるローカル端末（PC環境）でのみ実行できます。")
        else:
            st.caption("形式: game_id, date, p1_name, p1_score, p2_name, p2_score, p3_name, p3_score, p4_name, p4_score（ヘッダーなし）")

            c_r1, c_r2 = st.columns(2)
            with c_r1:
                rule_tmps = cache_utils.get_rule_templates()
                rule_opts = {r["rule_id"]: r["name"] for r in rule_tmps} if rule_tmps else {"standard": "標準ルール"}
                sel_rule_id = st.selectbox("適用ルール", list(rule_opts.keys()),
                                           format_func=lambda x: rule_opts[x], key="csv_rule_sel")
                sel_template = next((r for r in rule_tmps if r["rule_id"] == sel_rule_id), None) if rule_tmps else None
                rule_cfg_for_import = sel_template.get("config_json", {}) if sel_template else {}
                if isinstance(rule_cfg_for_import, str):
                    try:
                        rule_cfg_for_import = json.loads(rule_cfg_for_import)
                    except Exception:
                        rule_cfg_for_import = {}

            with c_r2:
                guest_mode = st.radio("未登録プレイヤーの登録種別", ["通常メンバーとして登録", "ゲストとして登録"],
                                      horizontal=True, key="csv_guest_mode")
                auto_guest = (guest_mode == "ゲストとして登録")

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
                    if st.button("この内容を取り込む", type="primary", use_container_width=True):
                        count = db.import_games_from_df(df, rule_config=rule_cfg_for_import, auto_guest=auto_guest)
                        st.cache_data.clear()
                        st.success(f"{count}件の対局を安全に取り込みました（ウマオカpt自動算出・UUID紐付け完了）。")
                        st.rerun()
                except Exception as e:
                    st.error(f"読み込みエラー: {e}")

    # ── TAB 3: データ編集・削除 ──────────────────────────────────
    with tab3:
        st.subheader("データ編集・削除")
        if not db.IS_LOCAL:
            st.warning("⚠️ データの削除・局修正・基本情報編集は、正本であるローカル端末（PC環境）でのみ実行できます。")
        else:
            df_games = db.get_games_data()
            if df_games.empty:
                st.info("記録がありません。")
            else:
                def game_label(row):
                    gid_short = str(row['game_id'])[:8]
                    d = row.get('date', '')
                    d_str = d.strftime('%Y-%m-%d') if pd.notna(d) and hasattr(d, 'strftime') else str(d)[:10]
                    return f"[{gid_short}] {d_str}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

                options = {str(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
                sel_id = st.selectbox("対象の試合を選択してください", list(options.keys()),
                                      format_func=lambda x: options[x], key="edit_dm_game_id")

                action_mode = st.radio(
                    "操作項目を選択",
                    ["① 試合データの削除", "② 過去対局の局修正", "③ 試合基本情報の編集（日時・最終スコア・メンバー）"],
                    horizontal=True,
                    key="dm_action_mode"
                )

                st.divider()

                # ① 試合データの削除
                if action_mode == "① 試合データの削除":
                    row = df_games[df_games['game_id'] == sel_id].iloc[0]
                    st.warning("⚠️ この試合をローカル端末から削除します。（※操作直前に自動バックアップが作成されます）")
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
                        db.backup_local_db_snapshot()
                        db.delete_game(str(sel_id))
                        st.cache_data.clear()
                        st.success(f"Game [{short_id}] をローカルから削除しました。")
                        st.rerun()

                # ② 過去対局の局修正
                elif action_mode == "② 過去対局の局修正":
                    show_round_edit(selected_game_id=sel_id)

                # ③ 試合基本情報の編集
                elif action_mode == "③ 試合基本情報の編集（日時・最終スコア・メンバー）":
                    game_dict = db.get_game_details(sel_id)
                    if not game_dict:
                        st.error("指定された試合データが見つかりません。")
                    else:
                        st.write("#### 試合基本情報の修正")
                        is_detail_game = (game_dict.get("game_mode") == "detail" and bool(game_dict.get("rounds")))
                        if is_detail_game:
                            st.info("ℹ️ この試合には局ごとの詳細記録が存在します。局ごとの点数や和了者を変更したい場合は「② 過去対局の局修正」をご利用ください。")

                        # 日時編集
                        cur_played_at = str(game_dict.get("played_at", ""))
                        try:
                            dt_obj = datetime.strptime(cur_played_at[:19], "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            dt_obj = datetime.now()

                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            new_d = st.date_input("対局日", value=dt_obj.date(), key="dm_edit_date")
                        with col_d2:
                            new_t = st.time_input("対局時刻", value=dt_obj.time(), key="dm_edit_time")

                        new_played_at = f"{new_d.strftime('%Y-%m-%d')} {new_t.strftime('%H:%M:%S')}"

                        # メンバー・素点入力
                        all_members = cache_utils.get_all_members()
                        mem_id_to_name = {m["member_id"]: m["member_name"] for m in all_members}
                        mem_options = list(mem_id_to_name.keys())

                        parts = sorted(game_dict.get("participants", []), key=lambda x: x.get("seat", 1))
                        rule_cfg = game_dict.get("rule_config_snapshot") or {}
                        if isinstance(rule_cfg, str):
                            try:
                                rule_cfg = json.loads(rule_cfg)
                            except Exception:
                                rule_cfg = {}

                        st.write("**参加者4名のメンバー選択と最終持ち点**")
                        new_parts_input = []
                        score_inputs = []

                        seat_cols = st.columns(4)
                        for idx, p in enumerate(parts):
                            seat_num = p.get("seat", idx + 1)
                            cur_mid = p.get("member_id")
                            cur_score = int(p.get("final_score", 25000))

                            with seat_cols[idx]:
                                st.caption(f"座席 {seat_num} ({['東', '南', '西', '北'][idx]}家)")
                                default_mid_idx = mem_options.index(cur_mid) if cur_mid in mem_options else 0
                                sel_m = st.selectbox(
                                    f"席{seat_num} メンバー", mem_options,
                                    index=default_mid_idx,
                                    format_func=lambda x: mem_id_to_name.get(x, x),
                                    key=f"dm_edit_m_{seat_num}"
                                )
                                s_val = st.number_input(
                                    f"席{seat_num} 素点", value=cur_score, step=100,
                                    key=f"dm_edit_s_{seat_num}"
                                )
                                score_inputs.append(int(s_val))
                                new_parts_input.append({
                                    "seat": seat_num,
                                    "member_id": sel_m,
                                    "player_name_snapshot": mem_id_to_name.get(sel_m, f"P{seat_num}"),
                                    "final_score": int(s_val),
                                    "was_group_member": p.get("was_group_member", 1)
                                })

                        total_score = sum(score_inputs)
                        expected_total = rule_cfg.get("basic", {}).get("init_score", 25000) * 4
                        is_zero_sum = (total_score == expected_total)

                        st.write("---")
                        if not is_zero_sum:
                            st.error(f"持ち点合計: {total_score:,}点（規定の {expected_total:,}点 ゼロサムを満たしていません。保存できません）")
                        else:
                            st.success(f"持ち点合計: {total_score:,}点（ゼロサム確認済み）")

                            # 着順・pt再計算プレビュー
                            sorted_parts = sorted(new_parts_input, key=lambda x: x["final_score"], reverse=True)
                            st.write("**新素点による確定着順・精算ptプレビュー**")
                            prev_cols = st.columns(4)
                            for rank, sp in enumerate(sorted_parts, start=1):
                                calc_pt = calc.calc_point(sp["final_score"], rank, rule_cfg) if rule_cfg else 0.0
                                sp["rank"] = rank
                                sp["point"] = calc_pt
                                with prev_cols[rank - 1]:
                                    st.metric(
                                        label=f"{rank}位: {sp['player_name_snapshot']}",
                                        value=f"{sp['final_score']:,}点",
                                        delta=f"{calc_pt:+.1f}pt"
                                    )

                        allow_save = is_zero_sum
                        if is_detail_game:
                            confirm_detail_override = st.checkbox(
                                "局履歴と最終素点の差異が発生することを了承し、基本情報を強制上書きする",
                                key="dm_confirm_override"
                            )
                            allow_save = allow_save and confirm_detail_override

                        if st.button("基本情報の変更をデータベースへ保存する", type="primary",
                                     disabled=not allow_save, use_container_width=True):
                            # 保存実行
                            db.update_game_basic_info(sel_id, new_played_at, new_parts_input)
                            st.cache_data.clear()
                            st.success("試合の基本情報（日時・メンバー・最終持ち点・着順・pt）を不可分更新しました。")
                            st.rerun()

    # ── TAB 4: 同期 ─────────────────────────────────────────────
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

            st.caption("※メンバー・グループ・ルールは常に双方向で自動マージされます。ローカルで修正した対局はオンライン側にも上書き送信されます。")

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
