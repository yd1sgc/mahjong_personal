import pandas as pd
import json
from decimal import Decimal, ROUND_HALF_UP

# ==========================================
#  計算ルール設定エリア
# ==========================================

RETURN_POINT = 30000
UMA_SETTINGS = {1: 50, 2: 10, 3: -10, 4: -30}
INIT_SCORE = 25000
ROUND_INTEGER = False

def calculate_score(han, fu, is_dealer, is_tsumo):
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
        if is_dealer: return round_up(base * 2) * 3, 0, round_up(base * 2)
        else: return round_up(base * 2) + round_up(base) * 2, round_up(base * 2), round_up(base)
    else:
        return (round_up(base * 6) if is_dealer else round_up(base * 4)), 0, 0


def calc_oka_nashi_point(score, rank):
    oka = (RETURN_POINT - INIT_SCORE) * 4 / 1000
    base_pt = (score - INIT_SCORE) / 1000
    uma_pt = UMA_SETTINGS.get(rank, 0) - (oka if rank == 1 else 0)
    total = base_pt + uma_pt
    if ROUND_INTEGER: return int(Decimal(str(total)).quantize(Decimal('0'), rounding=ROUND_HALF_UP))
    else: return round(total, 1)


def calc_special_point(score, rank, rule_config=None, chombo_count=0):
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
    else:
        base_pt = (score - RETURN_POINT) / 1000
        uma_pt = UMA_SETTINGS.get(rank, 0)
        total = base_pt + uma_pt

    if ROUND_INTEGER: return int(Decimal(str(total)).quantize(Decimal('0'), rounding=ROUND_HALF_UP))
    else: return round(total, 1)


def get_chombo_counts(df_rounds):
    counts = {}
    if not df_rounds.empty and 'win_type' in df_rounds.columns:
        for _, r in df_rounds[df_rounds['win_type'] == 'chombo'].iterrows():
            key = (r['game_id'], r.get('winner', ''))
            counts[key] = counts.get(key, 0) + 1
    return counts


def _calc_game_stats(df_games, chombo_counts):
    def parse_rule(x):
        if pd.notna(x) and isinstance(x, str) and x.strip():
            try: return json.loads(x)
            except Exception: pass
        return None

    df_games = df_games.copy()
    df_games['parsed_rule'] = df_games['applied_rule_json'].apply(parse_rule)

    records = []
    for _, row in df_games.iterrows():
        cfg = row['parsed_rule']
        gid = row['game_id']
        for i in range(1, 5):
            name = row.get(f'p{i}_name')
            if pd.isna(name) or not str(name).strip(): continue
            name = str(name).strip()
            score = float(row.get(f'p{i}_score', 25000))
            rank = int(row.get(f'p{i}_rank', 0))
            c_count = chombo_counts.get((gid, name), 0)
            records.append({
                "name": name,
                "score": score,
                "rank": rank,
                "pt": calc_special_point(score, rank, rule_config=cfg, chombo_count=c_count),
                "oka_nashi": calc_oka_nashi_point(score, rank)
            })

    if not records:
        return pd.DataFrame()

    df_p = pd.DataFrame(records)
    agg_df = df_p.groupby("name").agg(
        試合数=("name", "count"),
        総合pt=("pt", "sum"),
        オカなし総合pt=("oka_nashi", "sum"),
        順位合計=("rank", lambda x: x[x > 0].sum()),
        着1=("rank", lambda x: (x == 1).sum()),
        着2=("rank", lambda x: (x == 2).sum()),
        着3=("rank", lambda x: (x == 3).sum()),
        着4=("rank", lambda x: (x == 4).sum()),
    ).reset_index()

    g = agg_df["試合数"]
    agg_df["平均順位"] = (agg_df["順位合計"] / g).round(2)
    agg_df["連対率"] = ((agg_df["着1"] + agg_df["着2"]) / g * 100).round(1)
    agg_df["ラス回避率"] = ((agg_df["着1"] + agg_df["着2"] + agg_df["着3"]) / g * 100).round(1)
    agg_df["1着率"] = (agg_df["着1"] / g * 100).round(1)
    agg_df["2着率"] = (agg_df["着2"] / g * 100).round(1)
    agg_df["3着率"] = (agg_df["着3"] / g * 100).round(1)
    agg_df["4着率"] = (agg_df["着4"] / g * 100).round(1)

    agg_df["総合pt"] = agg_df["総合pt"].round(1)
    agg_df["オカなし総合pt"] = agg_df["オカなし総合pt"].round(1)

    return agg_df.rename(columns={"name": "名前"}).drop(columns=["着1", "着2", "着3", "着4", "順位合計"])


def _calc_round_stats(df_games_with_rounds, df_rounds, valid_players):
    game_players_map = {}
    game_top_player_map = {}
    game_players_list_map = {}

    for _, row in df_games_with_rounds.iterrows():
        gid = row['game_id']
        players = []
        max_score = -999999
        top_p = None
        for i in range(1, 5):
            p_name = str(row.get(f'p{i}_name', '')).strip()
            if not p_name or pd.isna(row.get(f'p{i}_name')): continue
            players.append(p_name)
            score = float(row.get(f'p{i}_score', 0))
            if score > max_score:
                max_score, top_p = score, p_name
        game_players_list_map[gid] = players
        game_top_player_map[gid] = top_p
        game_players_map[gid] = set(players)

    round_stats = {name: {
        "局数": 0, "和了": 0, "ツモ": 0, "放銃": 0, "副露": 0,
        "リーチ": 0, "リーチ後和了": 0, "リーチ後放銃": 0,
        "副露和了": 0, "副露放銃": 0, "ダマ和了": 0,
        "立直和了点": 0, "副露和了点": 0, "ダマ和了点": 0,
        "被リーチ放銃": 0, "被副露放銃": 0, "被ダマ放銃": 0,
        "和了点": 0, "放銃点": 0,
        "流局": 0, "テンパイ": 0, "ノーテン罰符収支": 0, "供託収支": 0, "チョンボ": 0,
    } for name in valid_players}

    current_game_id = None
    riichi_stick_pool = 0

    df_r = df_rounds[df_rounds['game_id'].isin(set(df_games_with_rounds['game_id']))].sort_values(['game_id', 'id'])
    has_riichi = 'riichi_names' in df_r.columns
    has_win_type = 'win_type' in df_r.columns

    # 事前パース
    def parse_multi_wins(x):
        if isinstance(x, str) and x.strip():
            try: return json.loads(x)
            except Exception: pass
        elif isinstance(x, list): return x
        return []
    
    if 'multi_wins_json' in df_r.columns:
        df_r['parsed_multi_wins'] = df_r['multi_wins_json'].apply(parse_multi_wins)
    else:
        df_r['parsed_multi_wins'] = [[] for _ in range(len(df_r))]

    for _, r in df_r.iterrows():
        game_id = r['game_id']
        game_players = game_players_map.get(game_id, set())
        game_players_list = game_players_list_map.get(game_id, [])

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

        furo_players = [x for x in str(r.get('furo_names', '')).split(',') if x]
        riichi_players = [x for x in str(r.get('riichi_names', '')).split(',') if x] if has_riichi else []

        is_ryukyoku = win_type == 'ryukyoku' or (not winner and not loser and win_type == '')

        if is_ryukyoku:
            tenpai_players = [x for x in str(r.get('tenpai_names', '')).split(',') if x]
            active_tenpai = [p for p in tenpai_players if p in game_players]
            active_noten = [p for p in game_players if p not in tenpai_players]
            n_t, n_n = len(active_tenpai), len(active_noten)
            if 0 < n_t < 4:
                for tp in active_tenpai:
                    if tp in round_stats: round_stats[tp]["ノーテン罰符収支"] += 3000 // n_t
                for np in active_noten:
                    if np in round_stats: round_stats[np]["ノーテン罰符収支"] -= 3000 // n_n

        for m in round_stats.keys():
            if m not in game_players: continue
            round_stats[m]["局数"] += 1
            if m in furo_players: round_stats[m]["副露"] += 1
            if m in riichi_players:
                round_stats[m]["リーチ"] += 1
                round_stats[m]["供託収支"] -= 1000
                riichi_stick_pool += 1
            if is_ryukyoku:
                round_stats[m]["流局"] += 1
                if m in tenpai_players: round_stats[m]["テンパイ"] += 1

        if win_type == 'multi_ron':
            multi_wins = r['parsed_multi_wins']
            if multi_wins:
                total_score = 0
                mw_winners = []
                loser_idx = game_players_list.index(loser) if loser in game_players_list else 0
                def distance(p):
                    return (game_players_list.index(p) - loser_idx) % 4 if p in game_players_list else 0
                
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
                    if loser in riichi_players: round_stats[loser]["リーチ後放銃"] += 1
                    if loser in furo_players: round_stats[loser]["副露放銃"] += 1
                        
                    if any(w in riichi_players for w in mw_winners): round_stats[loser]["被リーチ放銃"] += 1
                    elif any(w in furo_players for w in mw_winners): round_stats[loser]["被副露放銃"] += 1
                    else: round_stats[loser]["被ダマ放銃"] += 1
            continue

        if winner and winner in round_stats:
            score = r.get('score', 0)
            round_stats[winner]["和了"] += 1
            round_stats[winner]["和了点"] += score
            if win_type == 'tsumo' or (not win_type and not loser):
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
                
            if win_type in ('ron', 'tsumo'):
                round_stats[winner]["供託収支"] += riichi_stick_pool * 1000
                riichi_stick_pool = 0

        if loser and loser in round_stats:
            round_stats[loser]["放銃"] += 1
            round_stats[loser]["放銃点"] += r.get('score', 0)
            if loser in riichi_players: round_stats[loser]["リーチ後放銃"] += 1
            if loser in furo_players: round_stats[loser]["副露放銃"] += 1

            if winner in riichi_players: round_stats[loser]["被リーチ放銃"] += 1
            elif winner in furo_players: round_stats[loser]["被副露放銃"] += 1
            else: round_stats[loser]["被ダマ放銃"] += 1

    if current_game_id is not None and riichi_stick_pool > 0:
        top_p = game_top_player_map.get(current_game_id)
        if top_p and top_p in round_stats:
            round_stats[top_p]["供託収支"] += riichi_stick_pool * 1000

    round_data = []
    for n, d in round_stats.items():
        k = d["局数"]
        if k == 0: continue
        r_c, f_c, w_c, h_c = d["リーチ"], d["副露"], d["和了"], d["放銃"]
        avg_win = round(d["和了点"] / w_c) if w_c else 0
        avg_lose = round(d["放銃点"] / h_c) if h_c else 0
        
        row = {
            "名前": n, "局数": k,
            "和了率": round(w_c / k * 100, 1),
            "ツモ率": round(d["ツモ"] / w_c * 100, 1) if w_c else 0.0,
            "放銃率": round(h_c / k * 100, 1),
            "和銃差": round((w_c - h_c) / k * 100, 1),
            "流局時聴牌率": round(d["テンパイ"] / d["流局"] * 100, 1) if d["流局"] > 0 else 0.0,
            "ノーテン罰符収支": d["ノーテン罰符収支"],
            "供託収支": d["供託収支"],
            "副露率": round(f_c / k * 100, 1),
            "リーチ率": round(r_c / k * 100, 1),
            "立直和了率": round(d["リーチ後和了"] / r_c * 100, 1) if r_c else 0.0,
            "立直放銃率": round(d["リーチ後放銃"] / r_c * 100, 1) if r_c else 0.0,
            "副露和了率": round(d["副露和了"] / f_c * 100, 1) if f_c else 0.0,
            "副露放銃率": round(d["副露放銃"] / f_c * 100, 1) if f_c else 0.0,
            "ダマ和了率": round(d["ダマ和了"] / w_c * 100, 1) if w_c else 0.0,
            "被リーチ放銃率": round(d["被リーチ放銃"] / h_c * 100, 1) if h_c else 0.0,
            "被副露放銃率": round(d["被副露放銃"] / h_c * 100, 1) if h_c else 0.0,
            "被ダマ放銃率": round(d["被ダマ放銃"] / h_c * 100, 1) if h_c else 0.0,
            "平均和了": avg_win, "平均放銃": avg_lose,
            "立直平均打点": round(d["立直和了点"] / d["リーチ後和了"]) if d["リーチ後和了"] else 0,
            "副露平均打点": round(d["副露和了点"] / d["副露和了"]) if d["副露和了"] else 0,
            "ダマ平均打点": round(d["ダマ和了点"] / d["ダマ和了"]) if d["ダマ和了"] else 0,
            "打点効率": round(avg_win / avg_lose, 2) if (avg_win and avg_lose) else 0.0,
        }
        if d["チョンボ"] > 0: row["チョンボ数"] = d["チョンボ"]
        round_data.append(row)
        
    return pd.DataFrame(round_data)


def analyze_stats(df_games, df_rounds):
    if df_games.empty:
        return pd.DataFrame(), pd.DataFrame(), 0

    all_players = pd.unique(df_games[['p1_name', 'p2_name', 'p3_name', 'p4_name']].values.ravel('K'))
    valid_players = [p for p in all_players if pd.notna(p) and str(p).strip() != ""]

    chombo_counts = get_chombo_counts(df_rounds)

    df_game_stats = _calc_game_stats(df_games, chombo_counts)

    if df_rounds.empty:
        return df_game_stats, pd.DataFrame(), 0

    round_game_ids = set(df_rounds['game_id'].unique())
    df_games_with_rounds = df_games[df_games['game_id'].isin(round_game_ids)]
    n_round_games = len(df_games_with_rounds)

    if n_round_games == 0:
        return df_game_stats, pd.DataFrame(), 0

    df_round_stats = _calc_round_stats(df_games_with_rounds, df_rounds, valid_players)

    return df_game_stats, df_round_stats, n_round_games