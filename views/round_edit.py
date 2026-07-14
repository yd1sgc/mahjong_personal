import streamlit as st
import database2 as db


def _parse_names(s):
    if not s or not isinstance(s, str):
        return []
    return [x.strip() for x in s.split(',') if x.strip()]


def _tenpai_payments(tenpai_list, all_players):
    n = len(tenpai_list)
    tenpai_set = set(tenpai_list)
    if n == 0 or n == 4:
        return {p: 0 for p in all_players}
    noten = [p for p in all_players if p not in tenpai_set]
    tenpai_receive = 3000 // n
    noten_pay = 3000 // len(noten)
    return {p: (tenpai_receive if p in tenpai_set else -noten_pay) for p in all_players}


def _find_next_winner(df_rounds, current_idx):
    for i in range(current_idx + 1, len(df_rounds)):
        row = df_rounds.iloc[i]
        if row.get('winner') and row.get('win_type') not in ('ryukyoku', 'chombo', ''):
            return row
    return None


def calc_deltas(old_row, new_vals, all_players, df_rounds, round_idx):
    game_deltas = {p: 0 for p in all_players}

    old_winner = old_row.get('winner', '') or ''
    old_loser  = old_row.get('loser', '') or ''
    old_score  = int(old_row.get('score', 0) or 0)
    old_type   = old_row.get('win_type', '') or ''
    old_riichi = _parse_names(old_row.get('riichi_names', ''))
    old_tenpai = _parse_names(old_row.get('tenpai_names', ''))

    new_winner = new_vals['winner']
    new_loser  = new_vals['loser']
    new_score  = new_vals['score']
    new_type   = new_vals['win_type']
    new_riichi = new_vals['riichi_list']
    new_tenpai = new_vals['tenpai_list']

    # ── 1. リーチ変更 ────────────────────────────────────────
    # scoreフィールドにリーチ棒は含まれないため、ゲームスコアのみ調整
    for player in (set(new_riichi) - set(old_riichi)):  # 追加
        game_deltas[player] -= 1000
        if new_type != 'ryukyoku' and new_winner:
            game_deltas[new_winner] += 1000
        else:
            next_row = _find_next_winner(df_rounds, round_idx)
            if next_row is not None and str(next_row['winner']) in game_deltas:
                game_deltas[str(next_row['winner'])] += 1000

    for player in (set(old_riichi) - set(new_riichi)):  # 削除
        game_deltas[player] += 1000
        if new_type != 'ryukyoku' and new_winner:
            game_deltas[new_winner] -= 1000
        else:
            next_row = _find_next_winner(df_rounds, round_idx)
            if next_row is not None and str(next_row['winner']) in game_deltas:
                game_deltas[str(next_row['winner'])] -= 1000

    # ── 2. 聴牌変更（流局のみ） ──────────────────────────────
    if old_type == 'ryukyoku':
        for p, amt in _tenpai_payments(old_tenpai, all_players).items():
            game_deltas[p] -= amt
    if new_type == 'ryukyoku':
        for p, amt in _tenpai_payments(new_tenpai, all_players).items():
            game_deltas[p] += amt

    # ── 3. 和了・放銃・点数の変更 ────────────────────────────
    # 旧状態を巻き戻す
    if old_type == 'ron':
        if old_winner: game_deltas[old_winner] -= old_score
        if old_loser:  game_deltas[old_loser]  += old_score
    elif old_type == 'tsumo' and old_winner:
        game_deltas[old_winner] -= old_score
        others = [p for p in all_players if p != old_winner]
        if others:
            per = old_score // len(others)
            for p in others:
                game_deltas[p] += per

    # 新状態を適用
    if new_type == 'ron':
        if new_winner: game_deltas[new_winner] += new_score
        if new_loser:  game_deltas[new_loser]  -= new_score
    elif new_type == 'tsumo' and new_winner:
        game_deltas[new_winner] += new_score
        others = [p for p in all_players if p != new_winner]
        if others:
            per = new_score // len(others)
            for p in others:
                game_deltas[p] -= per

    return game_deltas


def show_round_edit():
    st.subheader("局修正")

    df_games = db.load_all_games()
    if df_games.empty:
        st.info("記録がありません。")
        return

    def game_label(row):
        return f"#{int(row['game_id'])} {row['date']}  {row['p1_name']}/{row['p2_name']}/{row['p3_name']}/{row['p4_name']}"

    options = {int(r['game_id']): game_label(r) for _, r in df_games.iterrows()}
    sel_id = st.selectbox("試合を選択", list(options.keys()),
                          format_func=lambda x: options[x], key="re_game_id")

    game_row = df_games[df_games['game_id'] == sel_id].iloc[0]
    players = [str(game_row[f'p{i}_name']) for i in range(1, 5)]
    game_scores = {str(game_row[f'p{i}_name']): int(game_row[f'p{i}_score']) for i in range(1, 5)}

    df_rounds = db.load_rounds_by_game(sel_id)
    if df_rounds.empty:
        st.info("この試合の局記録がありません。")
        return

    # 局一覧（読み取り専用）
    st.dataframe(
        df_rounds[['kyoku_name', 'winner', 'loser', 'win_type', 'score',
                   'riichi_names', 'furo_names', 'tenpai_names']].rename(columns={
            'kyoku_name': '局', 'winner': '和了者', 'loser': '放銃者',
            'win_type': '種別', 'score': '点数（基本）',
            'riichi_names': 'リーチ', 'furo_names': '副露', 'tenpai_names': '聴牌',
        }),
        use_container_width=True, hide_index=True
    )

    # 修正する局を選択
    round_labels = {
        int(row['id']): f"{row['kyoku_name']}  {row['winner'] or '流局'}"
        for _, row in df_rounds.iterrows()
    }
    sel_round_id = st.selectbox("修正する局を選択", list(round_labels.keys()),
                                format_func=lambda x: round_labels[x], key="re_round_id")

    round_row = df_rounds[df_rounds['id'] == sel_round_id].iloc[0].to_dict()
    round_idx = df_rounds.index.get_loc(df_rounds[df_rounds['id'] == sel_round_id].index[0])

    st.divider()

    # 編集フォーム
    with st.form("round_edit_form"):
        col1, col2 = st.columns(2)
        with col1:
            winner_opts = [''] + players
            cur_winner = round_row.get('winner', '') or ''
            new_winner = st.selectbox(
                "和了者", winner_opts,
                index=winner_opts.index(cur_winner) if cur_winner in winner_opts else 0,
                key="re_winner"
            )
            new_score = st.number_input("点数（基本）", value=int(round_row.get('score', 0) or 0), step=100, key="re_score")
        with col2:
            loser_opts = [''] + players
            cur_loser = round_row.get('loser', '') or ''
            new_loser = st.selectbox(
                "放銃者", loser_opts,
                index=loser_opts.index(cur_loser) if cur_loser in loser_opts else 0,
                key="re_loser"
            )
            type_opts = ['ron', 'tsumo', 'ryukyoku', 'chombo']
            cur_type = round_row.get('win_type', '') or 'ron'
            new_type = st.selectbox(
                "種別", type_opts,
                index=type_opts.index(cur_type) if cur_type in type_opts else 0,
                key="re_type"
            )

        old_riichi = _parse_names(round_row.get('riichi_names', ''))
        old_furo   = _parse_names(round_row.get('furo_names', ''))
        old_tenpai = _parse_names(round_row.get('tenpai_names', ''))

        st.write("リーチ")
        cols = st.columns(4)
        new_riichi = [p for i, p in enumerate(players)
                      if cols[i].checkbox(p, value=(p in old_riichi), key=f"re_ri_{p}")]

        st.write("副露")
        cols = st.columns(4)
        new_furo = [p for i, p in enumerate(players)
                    if cols[i].checkbox(p, value=(p in old_furo), key=f"re_fu_{p}")]

        st.write("聴牌（流局時）")
        cols = st.columns(4)
        new_tenpai = [p for i, p in enumerate(players)
                      if cols[i].checkbox(p, value=(p in old_tenpai), key=f"re_te_{p}")]

        submitted = st.form_submit_button("変更を確認する", type="primary", use_container_width=True)

    if submitted:
        new_vals = {
            'winner': new_winner, 'loser': new_loser,
            'score': int(new_score), 'win_type': new_type,
            'riichi_list': new_riichi, 'tenpai_list': new_tenpai,
        }
        deltas = calc_deltas(round_row, new_vals, players, df_rounds, round_idx)
        new_game_scores = {p: game_scores[p] + deltas.get(p, 0) for p in players}
        st.session_state['re_preview'] = {
            'round_id': sel_round_id,
            'game_id': int(sel_id),
            'new_round_fields': {
                'winner': new_winner, 'loser': new_loser,
                'score': int(new_score), 'win_type': new_type,
                'riichi_names': ','.join(new_riichi),
                'riichi_count': len(new_riichi),
                'furo_names': ','.join(new_furo),
                'tenpai_names': ','.join(new_tenpai),
            },
            'deltas': deltas,
            'new_game_scores': new_game_scores,
            'game_scores': game_scores,
            'players': players,
        }
        st.rerun()

    # プレビュー表示
    preview = st.session_state.get('re_preview')
    if preview and preview.get('round_id') == sel_round_id:
        st.divider()
        st.subheader("スコア影響プレビュー")

        deltas = preview['deltas']
        new_game_scores = preview['new_game_scores']
        has_change = any(d != 0 for d in deltas.values())

        if not has_change:
            st.info("スコアへの影響はありません（統計のみ変更）。")
        else:
            for p in preview['players']:
                d = deltas.get(p, 0)
                sign = '+' if d > 0 else ''
                old_s = preview['game_scores'][p]
                new_s = new_game_scores[p]
                if d != 0:
                    st.write(f"**{p}**: {old_s:,} → {new_s:,}（{sign}{d:,}）")
                else:
                    st.write(f"{p}: {old_s:,}（変化なし）")

        total = sum(new_game_scores.values())
        ok = (total == 100000)
        if not ok:
            st.error(f"合計 {total:,}点。100,000点にならないため保存できません。")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("保存する", type="primary", disabled=not ok, use_container_width=True):
                db.update_round(preview['round_id'], preview['new_round_fields'])
                if has_change:
                    db.update_game_scores(preview['game_id'], preview['new_game_scores'])
                db.get_games_data.clear()
                db.get_rounds_data.clear()
                db.load_rounds_by_game.clear()
                del st.session_state['re_preview']
                st.success("保存しました。")
                st.rerun()
        with col2:
            if st.button("キャンセル", use_container_width=True):
                del st.session_state['re_preview']
                st.rerun()
