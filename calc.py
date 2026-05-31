import pandas as pd
import streamlit as st
import math
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

# 3. 素点の計算方法 (True=整数に丸める, False=小数点のまま)
ROUND_INTEGER = False

# ==========================================

# メンバー設定 (新規対局の選択肢用)
MEMBERS = ["リョウト", "ユウダイ", "マサキ", "クノ", 
    "ｵｯﾁｬﾝ", "フルタ", "カツトシ", "ルイ", 
    "シュン", "キド", "さ", "し", "す", "せ", "そ"]

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

@st.cache_data
def analyze_stats(df_games, df_rounds):
    """ 詳細成績計算 """
    if df_games.empty: return pd.DataFrame()

    # データ内に存在する全プレイヤー名を自動取得
    all_players = pd.unique(df_games[['p1_name', 'p2_name', 'p3_name', 'p4_name']].values.ravel('K'))
    valid_players = [p for p in all_players if pd.notna(p) and str(p).strip() != ""]

    stats = {name: {
        "試合数": 0, "総合pt": 0.0, "順位合計": 0, "素点合計": 0,
        "1着": 0, "2着": 0, "3着": 0, "4着": 0,
        "局数": 0, "和了": 0, "放銃": 0, "副露": 0, 
        "リーチ": 0, "リーチ後和了": 0,
        "和了点": 0, "放銃点": 0
    } for name in valid_players}

    # 1. 試合データの集計
    for _, row in df_games.iterrows():
        for i in range(1, 5):
            if f'p{i}_name' not in row: continue
            
            name = row[f'p{i}_name']
            if name in stats:
                score = row.get(f'p{i}_score', 25000)
                rank = row.get(f'p{i}_rank', 0)
                
                stats[name]["試合数"] += 1
                stats[name]["総合pt"] += calc_special_point(score, rank)
                
                # 素点計算: (持ち点 - 返し点+5000) / 1000
                # ここで上で定義した RETURN_POINT を使います
                stats[name]["素点合計"] += (score - RETURN_POINT+5000) / 1000
                
                if rank > 0:
                    stats[name]["順位合計"] += rank
                    stats[name][f"{rank}着"] += 1

    # 2. 局データの集計
    if not df_rounds.empty:
        has_riichi = 'riichi_names' in df_rounds.columns
        target_ids = df_games['game_id'].unique()
        df_r = df_rounds[df_rounds['game_id'].isin(target_ids)]
        
        for _, r in df_r.iterrows():
            winner = r.get('winner', '')
            
            riichi_players = []
            if has_riichi:
                r_names = r.get('riichi_names', '')
                if pd.notna(r_names) and isinstance(r_names, str):
                    riichi_players = r_names.split(',')

            for m in stats.keys():
                stats[m]["局数"] += 1
                f_names = r.get('furo_names', '')
                if pd.notna(f_names) and isinstance(f_names, str) and m in f_names:
                    stats[m]["副露"] += 1
                
                if m in riichi_players:
                    stats[m]["リーチ"] += 1
                    if m == winner:
                        stats[m]["リーチ後和了"] += 1
            
            if winner in stats:
                stats[winner]["和了"] += 1
                stats[winner]["和了点"] += r.get('score', 0)
                
            loser = r.get('loser', '')
            if loser in stats:
                stats[loser]["放銃"] += 1
                stats[loser]["放銃点"] += r.get('score', 0)

    # 3. 結果リスト作成
    data = []
    for n, d in stats.items():
        g, k = d["試合数"], d["局数"]
        r_count = d["リーチ"]
        if g == 0: continue
        
        data.append({
            "名前": n,
            "試合数": g,
            "総合pt": d["総合pt"],
            "素点": d["素点合計"],
            "平均順位": d["順位合計"] / g,
            "連対率": (d["1着"] + d["2着"]) / g * 100,
            "ラス回避率": (d["1着"] + d["2着"] + d["3着"]) / g * 100,
            "和了率": (d["和了"] / k * 100) if k else 0,
            "放銃率": (d["放銃"] / k * 100) if k else 0,
            "副露率": (d["副露"] / k * 100) if k else 0,
            "リーチ率": (d["リーチ"] / k * 100) if k else 0,
            "リーチ成功率": (d["リーチ後和了"] / r_count * 100) if r_count else 0,
            "平均和了": (d["和了点"] / d["和了"]) if d["和了"] else 0,
            "平均放銃": (d["放銃点"] / d["放銃"]) if d["放銃"] else 0,
            "1着率": d["1着"]/g*100, "2着率": d["2着"]/g*100, 
            "3着率": d["3着"]/g*100, "4着率": d["4着"]/g*100
        })
    return pd.DataFrame(data)