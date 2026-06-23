import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

# ==========================================
# ⚙️ 計算ルール設定エリア
# ==========================================

# 1. 基準点（返し点）
# 30000点返しなら 30000, 25000点返しなら 25000
RETURN_POINT = 30000

# 2. 順位点（ウマ + オカ）
# [1位, 2位, 3位, 4位] のポイント
# Mリーグ準拠: {1: 50, 2: 10, 3: -10, 4: -30}
# 一般的な10-30: {1: 40, 2: 10, 3: -10, 4: -20}
# ゴットー(5-10): {1: 30, 2: 5, 3: -5, 4: -10}
UMA_SETTINGS = {
    1: 30,
    2: 5,
    3: -5,
    4: -10
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
    else: base = 8000

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


def calc_special_point(score, rank):
    """ ウマ・オカ計算 (設定反映版) """
    # 素点の計算: (持ち点 - 返し点) / 1000
    base_pt = (score - RETURN_POINT) / 1000
    
    # 設定されたウマを取得
    uma_pt = UMA_SETTINGS.get(rank, 0)
    
    # 合計
    total = base_pt + uma_pt
    
    # 整数丸め設定がある場合
    if ROUND_INTEGER:
        return int(Decimal(str(total)).quantize(Decimal('0'), rounding=ROUND_HALF_UP))
    else:
        # 小数点第1位まで
        return round(total, 1)

def analyze_stats(df_games, df_rounds):
    """成績計算。(ゲーム集計DF, ラウンド集計DF, 詳細記録試合数) を返す"""
    if df_games.empty:
        return pd.DataFrame(), pd.DataFrame(), 0

    all_players = pd.unique(df_games[['p1_name', 'p2_name', 'p3_name', 'p4_name']].values.ravel('K'))
    valid_players = [p for p in all_players if pd.notna(p) and str(p).strip() != ""]

    # ── 1. ゲームレベル集計（全試合対象）──────────────────────
    game_stats = {name: {
        "試合数": 0, "総合pt": 0.0, "オカなし総合pt": 0.0, "順位合計": 0,
        "1着": 0, "2着": 0, "3着": 0, "4着": 0,
    } for name in valid_players}

    for _, row in df_games.iterrows():
        for i in range(1, 5):
            name = row.get(f'p{i}_name')
            if name not in game_stats:
                continue
            score = row.get(f'p{i}_score', 25000)
            rank = row.get(f'p{i}_rank', 0)
            game_stats[name]["試合数"] += 1
            game_stats[name]["総合pt"] += calc_special_point(score, rank)
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

    # game_id → 参加プレイヤーセット のマップ（局数の誤計上を防ぐ）
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
        "リーチ": 0, "リーチ後和了": 0,
        "和了点": 0, "放銃点": 0,
        "流局": 0, "テンパイ": 0, "チョンボ": 0,
    } for name in valid_players}

    has_riichi = 'riichi_names' in df_rounds.columns
    has_win_type = 'win_type' in df_rounds.columns
    df_r = df_rounds[df_rounds['game_id'].isin(round_game_ids)]

    for _, r in df_r.iterrows():
        game_id = r['game_id']
        game_players = game_players_map.get(game_id, set())
        winner = r.get('winner', '') or ''
        loser = r.get('loser', '') or ''
        win_type = (r.get('win_type', '') or '') if has_win_type else ''

        # チョンボは局数に含めず別カウント
        if win_type == 'chombo':
            if winner in round_stats:
                round_stats[winner]["チョンボ"] += 1
            continue

        riichi_players = []
        if has_riichi:
            r_names = r.get('riichi_names', '')
            if pd.notna(r_names) and isinstance(r_names, str):
                riichi_players = [x for x in r_names.split(',') if x]

        # 流局判定: win_type が ryukyoku、または旧データ（winner/loser が両方空）
        is_ryukyoku = win_type == 'ryukyoku' or (not winner and not loser and win_type == '')

        if is_ryukyoku:
            tenpai_str = r.get('tenpai_names', '') or ''
            tenpai_players = [x for x in tenpai_str.split(',') if x] if isinstance(tenpai_str, str) else []

        for m in round_stats.keys():
            if m not in game_players:
                continue
            round_stats[m]["局数"] += 1
            f_names = r.get('furo_names', '')
            if pd.notna(f_names) and isinstance(f_names, str) and m in f_names:
                round_stats[m]["副露"] += 1
            if m in riichi_players:
                round_stats[m]["リーチ"] += 1
                if m == winner:
                    round_stats[m]["リーチ後和了"] += 1
            if is_ryukyoku:
                round_stats[m]["流局"] += 1
                if m in tenpai_players:
                    round_stats[m]["テンパイ"] += 1

        if winner and winner in round_stats:
            round_stats[winner]["和了"] += 1
            round_stats[winner]["和了点"] += r.get('score', 0)
            # ツモ判定: win_type=='tsumo' または 旧データ(loserが空)で推定
            is_tsumo = win_type == 'tsumo' or (win_type in ('', None) and not loser)
            if is_tsumo:
                round_stats[winner]["ツモ"] += 1
        if loser and loser in round_stats:
            round_stats[loser]["放銃"] += 1
            round_stats[loser]["放銃点"] += r.get('score', 0)

    round_data = []
    for n, d in round_stats.items():
        k = d["局数"]
        if k == 0:
            continue
        r_count = d["リーチ"]
        row = {
            "名前": n,
            "和了率": round(d["和了"] / k * 100, 1),
            "放銃率": round(d["放銃"] / k * 100, 1),
            "副露率": round(d["副露"] / k * 100, 1),
            "リーチ率": round(d["リーチ"] / k * 100, 1),
            "リーチ成功率": round(d["リーチ後和了"] / r_count * 100, 1) if r_count else 0,
            "平均和了": round(d["和了点"] / d["和了"]) if d["和了"] else 0,
            "平均放銃": round(d["放銃点"] / d["放銃"]) if d["放銃"] else 0,
            "ツモ率": round(d["ツモ"] / d["和了"] * 100, 1) if d["和了"] else 0.0,
        }
        if d["流局"] > 0:
            row["テンパイ率"] = round(d["テンパイ"] / d["流局"] * 100, 1)
        else:
            row["テンパイ率"] = 0.0
        if d["チョンボ"] > 0:
            row["チョンボ数"] = d["チョンボ"]
        round_data.append(row)
    df_round_stats = pd.DataFrame(round_data)

    return df_game_stats, df_round_stats, n_round_games