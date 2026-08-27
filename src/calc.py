import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

# ==========================================
#  計算ルール設定エリア
# ==========================================

# 1. 基準点（返し点）
RETURN_POINT = 30000

# 2. 順位点（ウマ + オカ）
UMA_SETTINGS = {
    1: 50,
    2: 10,
    3: -10,
    4: -30
}

# 3. 配給原点（オカなし計算に使用）
INIT_SCORE = 25000

# 4. 素点の計算方法 (True=整数に丸める, False=小数点のまま)
ROUND_INTEGER = False

# ==========================================


def calculate_score(han, fu, is_dealer, is_tsumo):
    """ 翻数・符数から点数を計算 """
    if han < 5:
        basic_points = fu * (2 ** (2 + han))
        base = 2000 if basic_points >= 2000 else basic_points
    elif han < 6: base = 2000
    elif han < 8: base = 3000
    elif han < 11: base = 4000
    elif han < 13: base = 6000
    elif han < 26: base = 8000
    else: base = 16000

    def round_up(n): return ((n + 99) // 100) * 100

    if is_tsumo:
        if is_dealer:
            return round_up(base * 2) * 3, 0, round_up(base * 2)
        else:
            return round_up(base * 2) + round_up(base) * 2, round_up(base * 2), round_up(base)
    else:
        return (round_up(base * 6) if is_dealer else round_up(base * 4)), 0, 0


def calc_oka_nashi_point(score, rank):
    """オカなし版（配給原点返し + 1位からオカ分を除外、ゼロサム維持）"""
    oka = (RETURN_POINT - INIT_SCORE) * 4 / 1000  # = 20pt
    base_pt = (score - INIT_SCORE) / 1000
    uma_pt = UMA_SETTINGS.get(rank, 0) - (oka if rank == 1 else 0)
    total = base_pt + uma_pt
    if ROUND_INTEGER:
        return int(Decimal(str(total)).quantize(Decimal('0'), rounding=ROUND_HALF_UP))
    else:
        return round(total, 1)


def calc_special_point(score, rank, rule_config=None, chombo_count=0):
    """ ウマ・オカ計算 (ルール設定動的反映版・チョンボ減算対応) """
    chombo_penalty = 0

    if rule_config and isinstance(rule_config, dict):
        b_cfg = rule_config.get("basic", rule_config)
        d_cfg = rule_config.get("detail", {})
        
        if d_cfg.get("chombo_rule") == "pt_penalty":
            chombo_penalty = d_cfg.get("chombo_pt", 20) * chombo_count

        ret_pt = b_cfg.get("return_score", RETURN_POINT)
        uma_list = b_cfg.get("uma", [50, 10, -10, -30])
        uma_pt = uma_list[rank - 1] if 1 <= rank <= len(uma_list) else 0
        base_pt = (score - ret_pt) / 1000
        total = base_pt + uma_pt - chombo_penalty
        if ROUND_INTEGER:
            return int(Decimal(str(total)).quantize(Decimal('0'), rounding=ROUND_HALF_UP))
        else:
            return round(total, 1)

    # 素点の計算: (持ち点 - 返し点) / 1000
    base_pt = (score - RETURN_POINT) / 1000
    uma_pt = UMA_SETTINGS.get(rank, 0)
    total = base_pt + uma_pt
    if ROUND_INTEGER:
        return int(Decimal(str(total)).quantize(Decimal('0'), rounding=ROUND_HALF_UP))
    else:
        return round(total, 1)


def get_chombo_counts(df_rounds):
    counts = {}
    if not df_rounds.empty and 'win_type' in df_rounds.columns:
        for _, r in df_rounds[df_rounds['win_type'] == 'chombo'].iterrows():
            key = (r['game_id'], r.get('winner', ''))
            counts[key] = counts.get(key, 0) + 1
    return counts

def analyze_stats(df_games, df_rounds):
    """成績計算。(ゲーム集計DF, ラウンド集計DF, 詳細記録試合数) を返す"""
    if df_games.empty:
        return pd.DataFrame(), pd.DataFrame(), 0

    all_players = pd.unique(df_games[['p1_name', 'p2_name', 'p3_name', 'p4_name']].values.ravel('K'))
    valid_players = [p for p in all_players if pd.notna(p) and str(p).strip() != ""]

    chombo_counts = get_chombo_counts(df_rounds)

    # ── 1. ゲームレベル集計（全試合対象）──────────────────────
    game_stats = {name: {
        "試合数": 0, "総合pt": 0.0, "オカなし総合pt": 0.0, "順位合計": 0,
        "1着": 0, "2着": 0, "3着": 0, "4着": 0,
    } for name in valid_players}

    for _, row in df_games.iterrows():
        # 対局ごとのルールスナップショット解読
        cfg = None
        rule_json = row.get('applied_rule_json')
        if pd.notna(rule_json) and isinstance(rule_json, str) and rule_json.strip():
            try:
                import json
                cfg = json.loads(rule_json)
            except Exception:
                cfg = None

        for i in range(1, 5):
            name = row.get(f'p{i}_name')
            if name not in game_stats:
                continue
            score = row.get(f'p{i}_score', 25000)
            rank = row.get(f'p{i}_rank', 0)
            c_count = chombo_counts.get((row['game_id'], name), 0)
            game_stats[name]["試合数"] += 1
            game_stats[name]["総合pt"] += calc_special_point(score, rank, rule_config=cfg, chombo_count=c_count)
            game_stats[name]["オカなし総合pt"] += calc_oka_nashi_point(score, rank)
            if rank > 0:
                game_stats[name]["順位合計"] += rank
                game_stats[name][f"{rank}着"] += 1

    game_data = []
    for n, d in game_stats.items():
        g = d["試合数"]
        if g == 0:
            continue
        game_data.append({
            "名前": n,
            "試合数": g,
            "総合pt": round(d["総合pt"], 1),
            "オカなし総合pt": round(d["オカなし総合pt"], 1),
            "平均順位": round(d["順位合計"] / g, 2),
            "連対率": round((d["1着"] + d["2着"]) / g * 100, 1),
            "ラス回避率": round((d["1着"] + d["2着"] + d["3着"]) / g * 100, 1),
            "1着率": round(d["1着"] / g * 100, 1),
            "2着率": round(d["2着"] / g * 100, 1),
            "3着率": round(d["3着"] / g * 100, 1),
            "4着率": round(d["4着"] / g * 100, 1),
        })
    df_game_stats = pd.DataFrame(game_data)

    # ── 2. ラウンドレベル集計（詳細記録あり試合のみ）──────────
    if df_rounds.empty:
        return df_game_stats, pd.DataFrame(), 0

    round_game_ids = set(df_rounds['game_id'].unique())
    df_games_with_rounds = df_games[df_games['game_id'].isin(round_game_ids)]
    n_round_games = len(df_games_with_rounds)

    if n_round_games == 0:
        return df_game_stats, pd.DataFrame(), 0

    game_players_map = {}
    for _, game_row in df_games_with_rounds.iterrows():
        gid = game_row['game_id']
        game_players_map[gid] = {
            str(game_row[f'p{i}_name']).strip()
            for i in range(1, 5)
            if pd.notna(game_row.get(f'p{i}_name')) and str(game_row[f'p{i}_name']).strip()
        }

    round_stats = {name: {
        "局数": 0, "和了": 0, "ツモ": 0, "放銃": 0, "副露": 0,
        "リーチ": 0, "リーチ後和了": 0, "リーチ後放銃": 0,
        "副露和了": 0, "副露放銃": 0, "ダマ和了": 0,
        "立直和了点": 0, "副露和了点": 0, "ダマ和了点": 0,
        "被リーチ放銃": 0, "被副露放銃": 0, "被ダマ放銃": 0,
        "和了点": 0, "放銃点": 0,
        "流局": 0, "テンパイ": 0, "ノーテン罰符収支": 0, "供託収支": 0, "チョンボ": 0,
    } for name in valid_players}

    has_riichi = 'riichi_names' in df_rounds.columns
    has_win_type = 'win_type' in df_rounds.columns
    valid_game_ids = set(df_games_with_rounds['game_id'])
    
    # 供託持ち越しのため時系列ソート必須
    df_r = df_rounds[df_rounds['game_id'].isin(valid_game_ids)].sort_values(['game_id', 'id'])
    
    # ゲームごとのトッププレイヤーと座席順マップ作成
    game_top_player_map = {}
    game_players_list_map = {}
    for _, game_row in df_games_with_rounds.iterrows():
        gid = game_row['game_id']
        players = []
        max_score = -999999
        top_p = None
        for i in range(1, 5):
            p_name = str(game_row.get(f'p{i}_name', '')).strip()
            if not p_name or pd.isna(game_row.get(f'p{i}_name')):
                continue
            players.append(p_name)
            score = float(game_row.get(f'p{i}_score', 0))
            if score > max_score:
                max_score = score
                top_p = p_name
        game_players_list_map[gid] = players
        game_top_player_map[gid] = top_p

    current_game_id = None
    riichi_stick_pool = 0

    for _, r in df_r.iterrows():
        game_id = r['game_id']
        game_players = game_players_map.get(game_id, set())
        game_players_list = game_players_list_map.get(game_id, [])
        
        # 試合が切り替わった時の供託トップ取り処理
        if current_game_id != game_id:
            if current_game_id is not None and riichi_stick_pool > 0:
                top_p = game_top_player_map.get(current_game_id)
                if top_p and top_p in round_stats:
                    round_stats[top_p]["供託収支"] += riichi_stick_pool * 1000
            current_game_id = game_id
            riichi_stick_pool = 0

        winner = r.get('winner', '') or ''
        loser = r.get('loser', '') or ''
        win_type = (r.get('win_type', '') or '') if has_win_type else ''

        if win_type == 'chombo':
            if winner in round_stats:
                round_stats[winner]["チョンボ"] += 1
            continue

        furo_players = []
        f_names = r.get('furo_names', '')
        if pd.notna(f_names) and isinstance(f_names, str):
            furo_players = [x for x in f_names.split(',') if x]

        riichi_players = []
        if has_riichi:
            r_names = r.get('riichi_names', '')
            if pd.notna(r_names) and isinstance(r_names, str):
                riichi_players = [x for x in r_names.split(',') if x]

        is_ryukyoku = win_type == 'ryukyoku' or (not winner and not loser and win_type == '')

        if is_ryukyoku:
            tenpai_str = r.get('tenpai_names', '') or ''
            tenpai_players = [x for x in tenpai_str.split(',') if x] if isinstance(tenpai_str, str) else []

            active_tenpai = [p for p in tenpai_players if p in game_players]
            active_noten = [p for p in game_players if p not in tenpai_players]
            n_t, n_n = len(active_tenpai), len(active_noten)
            if 0 < n_t < 4:
                get_pt = 3000 // n_t
                pay_pt = 3000 // n_n
                for tp in active_tenpai:
                    if tp in round_stats:
                        round_stats[tp]["ノーテン罰符収支"] += get_pt
                for np in active_noten:
                    if np in round_stats:
                        round_stats[np]["ノーテン罰符収支"] -= pay_pt

        for m in round_stats.keys():
            if m not in game_players:
                continue
            round_stats[m]["局数"] += 1
            if m in furo_players:
                round_stats[m]["副露"] += 1
            if m in riichi_players:
                round_stats[m]["リーチ"] += 1
                round_stats[m]["供託収支"] -= 1000
                riichi_stick_pool += 1
            if is_ryukyoku:
                round_stats[m]["流局"] += 1
                if m in tenpai_players:
                    round_stats[m]["テンパイ"] += 1

        if win_type == 'multi_ron':
            multi_wins_json = r.get('multi_wins_json')
            import json
            multi_wins = []
            if pd.notna(multi_wins_json) and multi_wins_json:
                try:
                    multi_wins = json.loads(multi_wins_json)
                except Exception:
                    pass
            
            if multi_wins:
                total_score = 0
                mw_winners = []
                
                # ダブロン時の頭ハネ（上家取り）判定
                loser_idx = game_players_list.index(loser) if loser in game_players_list else 0
                def distance(p):
                    idx = game_players_list.index(p) if p in game_players_list else 0
                    return (idx - loser_idx) % 4
                closest_winner = min([wd.get("winner", "") for wd in multi_wins], key=distance) if multi_wins else ""
                
                if closest_winner and closest_winner in round_stats:
                    round_stats[closest_winner]["供託収支"] += riichi_stick_pool * 1000
                riichi_stick_pool = 0
                
                for w in multi_wins:
                    mw = w.get("winner")
                    ms = w.get("points_data", {}).get("total", 0)
                    if not mw: continue
                    mw_winners.append(mw)
                    total_score += ms
                    
                    if mw in round_stats:
                        round_stats[mw]["和了"] += 1
                        round_stats[mw]["和了点"] += ms
                        if mw in riichi_players:
                            round_stats[mw]["リーチ後和了"] += 1
                            round_stats[mw]["立直和了点"] += ms
                        if mw in furo_players:
                            round_stats[mw]["副露和了"] += 1
                            round_stats[mw]["副露和了点"] += ms
                        if mw not in riichi_players and mw not in furo_players:
                            round_stats[mw]["ダマ和了"] += 1
                            round_stats[mw]["ダマ和了点"] += ms
                
                if loser and loser in round_stats:
                    round_stats[loser]["放銃"] += 1
                    round_stats[loser]["放銃点"] += total_score
                    if loser in riichi_players:
                        round_stats[loser]["リーチ後放銃"] += 1
                    if loser in furo_players:
                        round_stats[loser]["副露放銃"] += 1
                        
                    if any(w in riichi_players for w in mw_winners):
                        round_stats[loser]["被リーチ放銃"] += 1
                    elif any(w in furo_players for w in mw_winners):
                        round_stats[loser]["被副露放銃"] += 1
                    else:
                        round_stats[loser]["被ダマ放銃"] += 1
                
                continue

        if winner and winner in round_stats:
            score = r.get('score', 0)
            round_stats[winner]["和了"] += 1
            round_stats[winner]["和了点"] += score
            is_tsumo = win_type == 'tsumo' or (win_type in ('', None) and not loser)
            if is_tsumo:
                round_stats[winner]["ツモ"] += 1

            if winner in riichi_players:
                round_stats[winner]["リーチ後和了"] += 1
                round_stats[winner]["立直和了点"] += score
            if winner in furo_players:
                round_stats[winner]["副露和了"] += 1
                round_stats[winner]["副露和了点"] += score
            if winner not in riichi_players and winner not in furo_players:
                round_stats[winner]["ダマ和了"] += 1
                round_stats[winner]["ダマ和了点"] += score
                
            # 通常和了時の供託回収
            if win_type in ('ron', 'tsumo'):
                round_stats[winner]["供託収支"] += riichi_stick_pool * 1000
                riichi_stick_pool = 0

        if loser and loser in round_stats:
            round_stats[loser]["放銃"] += 1
            round_stats[loser]["放銃点"] += r.get('score', 0)

            if loser in riichi_players:
                round_stats[loser]["リーチ後放銃"] += 1
            if loser in furo_players:
                round_stats[loser]["副露放銃"] += 1

            if winner in riichi_players:
                round_stats[loser]["被リーチ放銃"] += 1
            elif winner in furo_players:
                round_stats[loser]["被副露放銃"] += 1
            else:
                round_stats[loser]["被ダマ放銃"] += 1

    # 最後のゲームの残存供託処理
    if current_game_id is not None and riichi_stick_pool > 0:
        top_p = game_top_player_map.get(current_game_id)
        if top_p and top_p in round_stats:
            round_stats[top_p]["供託収支"] += riichi_stick_pool * 1000

    round_data = []
    for n, d in round_stats.items():
        k = d["局数"]
        if k == 0:
            continue
        r_count = d["リーチ"]
        f_count = d["副露"]
        w_count = d["和了"]
        h_count = d["放銃"]

        avg_win = round(d["和了点"] / w_count) if w_count else 0
        avg_lose = round(d["放銃点"] / h_count) if h_count else 0
        efficiency = round(avg_win / avg_lose, 2) if (avg_win and avg_lose) else 0.0

        row = {
            "名前": n,
            "局数": k,
            "和了率": round(w_count / k * 100, 1),
            "ツモ率": round(d["ツモ"] / w_count * 100, 1) if w_count else 0.0,
            "放銃率": round(h_count / k * 100, 1),
            "和銃差": round((w_count - h_count) / k * 100, 1),
            "流局時聴牌率": round(d["テンパイ"] / d["流局"] * 100, 1) if d["流局"] > 0 else 0.0,
            "ノーテン罰符収支": d["ノーテン罰符収支"],
            "供託収支": d["供託収支"],
            "副露率": round(f_count / k * 100, 1),
            "リーチ率": round(r_count / k * 100, 1),
            "立直和了率": round(d["リーチ後和了"] / r_count * 100, 1) if r_count else 0.0,
            "立直放銃率": round(d["リーチ後放銃"] / r_count * 100, 1) if r_count else 0.0,
            "副露和了率": round(d["副露和了"] / f_count * 100, 1) if f_count else 0.0,
            "副露放銃率": round(d["副露放銃"] / f_count * 100, 1) if f_count else 0.0,
            "ダマ和了率": round(d["ダマ和了"] / w_count * 100, 1) if w_count else 0.0,
            "被リーチ放銃率": round(d["被リーチ放銃"] / h_count * 100, 1) if h_count else 0.0,
            "被副露放銃率": round(d["被副露放銃"] / h_count * 100, 1) if h_count else 0.0,
            "被ダマ放銃率": round(d["被ダマ放銃"] / h_count * 100, 1) if h_count else 0.0,
            "平均和了": avg_win,
            "平均放銃": avg_lose,
            "立直平均打点": round(d["立直和了点"] / d["リーチ後和了"]) if d["リーチ後和了"] else 0,
            "副露平均打点": round(d["副露和了点"] / d["副露和了"]) if d["副露和了"] else 0,
            "ダマ平均打点": round(d["ダマ和了点"] / d["ダマ和了"]) if d["ダマ和了"] else 0,
            "打点効率": efficiency,
        }
        if d["チョンボ"] > 0:
            row["チョンボ数"] = d["チョンボ"]
        round_data.append(row)
    df_round_stats = pd.DataFrame(round_data)

    return df_game_stats, df_round_stats, n_round_games