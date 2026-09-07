import sqlite3
import itertools

def get_actual_tsumo_score(score, is_dealer):
    if is_dealer:
        ko_pay = int(((score / 3) + 99) // 100 * 100)
        return ko_pay * 3
    else:
        ko_pay = int(((score / 4) + 99) // 100 * 100)
        oya_pay = score - ko_pay * 2
        if oya_pay < ko_pay:
            oya_pay = ko_pay * 2
        return ko_pay * 2 + oya_pay

def is_valid_score(score, is_dealer, is_tsumo):
    if score == 0: return True
    if is_dealer:
        valid_ron = [48000, 36000, 24000, 18000, 12000, 11600, 9600, 7700, 5800, 4800, 3900, 2900, 2400, 2000, 1500]
        valid_tsumo = [48000, 36000, 24000, 18000, 12000, 11700, 9600, 7800, 6000, 4800, 3900, 3000, 2900, 2400, 2100, 1500]
        if is_tsumo: return score in valid_tsumo
        return score in valid_ron
    else:
        valid_ron = [32000, 24000, 16000, 12000, 8000, 7700, 6400, 5200, 3900, 3200, 2600, 2000, 1600, 1300, 1000]
        valid_tsumo = [32000, 24000, 16000, 12000, 8000, 7700, 6400, 5200, 4000, 3900, 3200, 2700, 2600, 2000, 1600, 1500, 1300, 1100, 1000]
        if is_tsumo: return score in valid_tsumo
        return score in valid_ron

def evaluate_dealer_map(rounds_info, dealer_map):
    # 与えられた親順序(dealer_map)でシミュレーションし、不一致(NULL)の数を返す
    errors = 0
    error_details = []
    
    for kyoku, w_seat, score, w_type in rounds_info:
        if w_seat is None or w_type not in ('ron', 'tsumo'):
            continue
            
        k_num = int(kyoku[1]) if len(kyoku)>=3 and kyoku[1].isdigit() else 1
        dealer_seat = dealer_map[k_num]
        is_dealer = (w_seat == dealer_seat)
        
        actual_score = score
        if w_type == 'tsumo':
            actual_score = get_actual_tsumo_score(score, is_dealer)
            
        if not is_valid_score(actual_score, is_dealer, w_type == 'tsumo'):
            errors += 1
            error_details.append(f"Kyoku:{kyoku} WinnerSeat:{w_seat} IsDealer:{is_dealer} Score:{actual_score}")
            
    return errors, error_details

def main():
    conn = sqlite3.connect(r'C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db')
    c = conn.cursor()
    
    c.execute('SELECT game_id FROM games')
    game_ids = [row[0] for row in c.fetchall()]
    
    total_unexplained = 0
    
    # 4人の席順の全パターン (1,2,3,4 の順列)
    perms = list(itertools.permutations([1, 2, 3, 4]))
    
    for g_id in game_ids:
        c.execute('SELECT seat, display_name_snapshot FROM game_participants WHERE game_id=?', (g_id,))
        name_to_seat = {row[1]: row[0] for row in c.fetchall()}
        
        c.execute('SELECT kyoku_name, winner, score, win_type FROM rounds WHERE game_id=? ORDER BY id', (g_id,))
        db_rounds = c.fetchall()
        
        rounds_info = []
        for r in db_rounds:
            kyoku, w_name, score, w_type = r
            if w_name:
                w_seat = name_to_seat.get(w_name)
                rounds_info.append((kyoku, w_seat, score, w_type))
                
        if not rounds_info:
            continue
            
        # デフォルトの席順 (1->1, 2->2, 3->3, 4->4) で評価
        default_map = {1: 1, 2: 2, 3: 3, 4: 4}
        best_errors, best_details = evaluate_dealer_map(rounds_info, default_map)
        best_map = default_map
        
        # もしデフォルトでエラーがあったら、全パターンを試す
        if best_errors > 0:
            for p in perms:
                d_map = {1: p[0], 2: p[1], 3: p[2], 4: p[3]}
                errs, details = evaluate_dealer_map(rounds_info, d_map)
                if errs < best_errors:
                    best_errors = errs
                    best_details = details
                    best_map = d_map
                if best_errors == 0:
                    break # 完璧な順序が見つかったら終了
                    
        total_unexplained += best_errors
        
        if best_errors > 0:
            print(f"Game {g_id}: {best_errors} errors remaining even with best dealer_map {best_map}")
            for d in best_details:
                print("  ", d)
                
    print(f"\nTotal Unexplained Rounds Across All Games: {total_unexplained}")

if __name__ == '__main__':
    main()
