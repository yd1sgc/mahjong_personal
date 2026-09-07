import sqlite3
import itertools
import os

def get_actual_tsumo_score(score, is_dealer):
    if is_dealer:
        ko_pay = int(((score / 3) + 99) // 100 * 100)
        return ko_pay * 3
    else:
        ko_pay = int(((score / 4) + 99) // 100 * 100)
        oya_pay = score - ko_pay * 2
        if oya_pay < ko_pay: oya_pay = ko_pay * 2
        return ko_pay * 2 + oya_pay

def is_valid_score(score, is_dealer, is_tsumo):
    if score == 0: return True
    if is_dealer:
        valid_ron = [48000, 36000, 24000, 18000, 12000, 11600, 9600, 7700, 5800, 4800, 3900, 2900, 2400, 2000, 1500]
        valid_tsumo = [48000, 36000, 24000, 18000, 12000, 11700, 9600, 7800, 6000, 4800, 3900, 3000, 2900, 2400, 2100, 1500]
        return score in valid_tsumo if is_tsumo else score in valid_ron
    else:
        valid_ron = [32000, 24000, 16000, 12000, 8000, 7700, 6400, 5200, 3900, 3200, 2600, 2000, 1600, 1300, 1000]
        valid_tsumo = [32000, 24000, 16000, 12000, 8000, 7700, 6400, 5200, 4000, 3900, 3200, 2700, 2600, 2000, 1600, 1500, 1300, 1100, 1000]
        return score in valid_tsumo if is_tsumo else score in valid_ron

def evaluate_dealer_map(rounds_info, dealer_map):
    errors = 0
    for kyoku, w_seat, score, w_type, _ in rounds_info:
        if w_seat is None or w_type not in ('ron', 'tsumo'): continue
        k_num = int(kyoku[1]) if len(kyoku)>=3 and kyoku[1].isdigit() else 1
        dealer_seat = dealer_map[k_num]
        is_dealer = (w_seat == dealer_seat)
        actual_score = get_actual_tsumo_score(score, is_dealer) if w_type == 'tsumo' else score
        if not is_valid_score(actual_score, is_dealer, w_type == 'tsumo'):
            errors += 1
    return errors

def predict_han_fu_full(score, is_dealer, is_tsumo):
    s = abs(score)
    if s == 0: return "-", "-"
    
    actual = get_actual_tsumo_score(s, is_dealer) if is_tsumo else s
    
    if is_dealer:
        if actual >= 48000: return 13, "役満"
        if actual >= 36000: return 11, "三倍満"
        if actual >= 24000: return 8, "倍満"
        if actual >= 18000: return 6, "跳満"
        if actual >= 12000: return 4, "満貫"
        if actual == 11600 or actual == 11700: return 4, 30
        if actual == 9600: return 4, 25
        if actual == 7800 or actual == 7700: return 3, 40
        if actual == 6000 or actual == 5800: return 3, 30
        if actual == 4800: return 3, 25
        if actual == 3900: return 2, 40
        if actual == 3000 or actual == 2900: return 2, 30
        if actual == 2400: return 2, 25
        if actual == 2100 or actual == 2000: return 2, 20
        if actual == 1500: return 1, 30
    else:
        if actual >= 32000: return 13, "役満"
        if actual >= 24000: return 11, "三倍満"
        if actual >= 16000: return 8, "倍満"
        if actual >= 12000: return 6, "跳満"
        if actual >= 8000: return 4, "満貫"
        if actual == 7700: return 4, 30
        if actual == 6400: return 4, 25
        if actual == 5200: return 3, 40
        if actual == 4000 or actual == 3900: return 3, 30
        if actual == 3200: return 3, 25
        if actual == 2700 or actual == 2600: return 2, 40
        if actual == 2000: return 2, 30
        if actual == 1600: return 2, 25
        if actual == 1500 or actual == 1300: return 1, 40
        if actual == 1100 or actual == 1000: return 1, 30
    return "?", "?"

def main():
    conn = sqlite3.connect(r'C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db')
    c = conn.cursor()
    
    target_games = [248, 250, 257] # 異常データ代表
    perms = list(itertools.permutations([1, 2, 3, 4]))
    
    out_path = r'C:\Users\segu1\.gemini\antigravity\brain\c773d87e-0d37-4d60-aca9-16afeba55235\restored_preview.md'
    
    with open(out_path, 'a', encoding='utf-8') as f:
        for g_id in target_games:
            f.write(f"\n## GameID {g_id}\n")
            
            c.execute('SELECT seat, display_name_snapshot FROM game_participants WHERE game_id=? ORDER BY seat', (g_id,))
            seats = c.fetchall()
            name_to_seat = {row[1]: row[0] for row in seats}
            f.write(f"**記録された座席**: " + ", ".join([f"{s[0]}:{s[1]}" for s in seats]) + "\n\n")
            
            c.execute('SELECT kyoku_name, winner, score, win_type, loser FROM rounds WHERE game_id=? ORDER BY id', (g_id,))
            db_rounds = c.fetchall()
            
            rounds_info = []
            for r in db_rounds:
                if r[1]: rounds_info.append((r[0], name_to_seat.get(r[1]), r[2], r[3], r[4]))
                else: rounds_info.append((r[0], None, r[2], r[3], r[4]))
                    
            best_errors = 999
            best_map = {}
            for p in perms:
                d_map = {1: p[0], 2: p[1], 3: p[2], 4: p[3]}
                errs = evaluate_dealer_map(rounds_info, d_map)
                if errs < best_errors:
                    best_errors = errs
                    best_map = d_map
                    
            f.write(f"**特定された真の親の回り方**: 東1局(Seat {best_map[1]}) → 東2局(Seat {best_map[2]}) → 東3局(Seat {best_map[3]}) → 東4局(Seat {best_map[4]})\n\n")
            f.write("| 局名 | 和了者 | 判定 | 手役 | ツモ/ロン | 元の入力点数 | 補正後点数 | 予測ハン | 予測符 |\n")
            f.write("|---|---|---|---|---|---|---|---|---|\n")
            
            for kyoku, w_seat, score, w_type, loser in rounds_info:
                if w_seat is None:
                    continue
                k_num = int(kyoku[1]) if len(kyoku)>=3 and kyoku[1].isdigit() else 1
                dealer_seat = best_map[k_num]
                is_dealer = (w_seat == dealer_seat)
                
                oyako = "親" if is_dealer else "子"
                w_name = [s[1] for s in seats if s[0] == w_seat][0]
                
                actual_score = get_actual_tsumo_score(score, is_dealer) if w_type == 'tsumo' else score
                han, fu = predict_han_fu_full(score, is_dealer, w_type == 'tsumo')
                
                f.write(f"| {kyoku} | {w_name}(Seat {w_seat}) | **{oyako}** | {w_type} | {score} | {actual_score} | **{han}** | **{fu}** |\n")

if __name__ == '__main__':
    main()
