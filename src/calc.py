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

calc_point = calc_special_point



def get_chombo_counts(df_rounds):
    """チョンボ回数の集計（下位互換性のため保持）"""
    counts = {}
    if not df_rounds.empty and 'win_type' in df_rounds.columns:
        for _, r in df_rounds[df_rounds['win_type'] == 'chombo'].iterrows():
            key = (r['game_id'], r.get('winner', ''))
            counts[key] = counts.get(key, 0) + 1
    return counts


def analyze_stats(df_games=None, df_rounds=None, group_id=None, rule_id=None, year=None, include_guests=True):
    """
    成績集計メイン関数。
    新V2スキーマの SQL 集計（database2.py）を活用して高速・正確に算出する。
    """
    import database2 as db

    # 新スキーマの直接集計関数を呼び出す
    df_game_stats = db.get_game_stats_summary(
        group_id=group_id,
        rule_id=rule_id,
        year=year,
        include_guests=include_guests
    )

    df_round_stats, n_round_games = db.get_round_stats_summary(
        group_id=group_id,
        rule_id=rule_id,
        year=year,
        include_guests=include_guests
    )

    return df_game_stats, df_round_stats, n_round_games