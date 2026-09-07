import sqlite3
import sys

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
        valid_tsumo = [48000, 36000, 24000, 18000, 12000, 11700, 9600, 7800, 6000, 4800, 3900, 2900, 2400, 2100, 1500]
        if is_tsumo: return score in valid_tsumo
        return score in valid_ron
    else:
        valid_ron = [32000, 24000, 16000, 12000, 8000, 7700, 6400, 5200, 3900, 3200, 2600, 2000, 1600, 1300, 1000]
        valid_tsumo = [32000, 24000, 16000, 12000, 8000, 7700, 6400, 5200, 4000, 3900, 3200, 2700, 2600, 2000, 1600, 1500, 1300, 1100, 1000]
        if is_tsumo: return score in valid_tsumo
        return score in valid_ron

def find_dealer_map(rounds):
    dealer_map = {}
    
    # 手がかり1: 連荘
    for i in range(len(rounds) - 1):
        kyoku, w_seat, score, w_type = rounds[i]
        next_kyoku = rounds[i+1][0]
        if kyoku == next_kyoku and w_seat is not None:
            if w_type in ('ron', 'tsumo'):
                k_num = int(kyoku[1]) if len(kyoku)>=3 and kyoku[1].isdigit() else 1
                dealer_map[k_num] = w_seat

    # 手がかり2: 親特有の点数
    oya_scores = [2900, 5800, 11600, 18000, 24000, 36000, 48000]
    oya_tsumos = [18000, 24000, 36000, 48000]
    for kyoku, w_seat, score, w_type in rounds:
        if w_seat is not None:
            k_num = int(kyoku[1]) if len(kyoku)>=3 and kyoku[1].isdigit() else 1
            if w_type == 'ron' and score in oya_scores:
                dealer_map[k_num] = w_seat
            elif w_type == 'tsumo':
                actual = get_actual_tsumo_score(score, True) # 仮に親として計算
                if actual in oya_tsumos:
                    dealer_map[k_num] = w_seat

    # 特定できなかった局の補完
    used_seats = set(dealer_map.values())
    
    # 完全にシャッフルされているゲーム（Game 250等）で特定漏れがある場合、
    # 記録順（Seat 1〜4）に沿ったデフォルト割り当てを試みる
    if len(dealer_map) == 0:
        return {1: 1, 2: 2, 3: 3, 4: 4}
        
    for k in range(1, 5):
        if k not in dealer_map:
            # もしデフォルト席(k)がまだ使われていなければそれを当てる
            if k not in used_seats:
                dealer_map[k] = k
                used_seats.add(k)
            else:
                for s in range(1, 5):
                    if s not in used_seats:
                        dealer_map[k] = s
                        used_seats.add(s)
                        break
                        
    return dealer_map

def main():
    conn = sqlite3.connect(r'C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db')
    c = conn.cursor()
    
    c.execute('SELECT game_id FROM games')
    game_ids = [row[0] for row in c.fetchall()]
    
    unexplained = []
    
    for g_id in game_ids:
        # 座席情報の取得
        c.execute('SELECT seat, display_name_snapshot FROM game_participants WHERE game_id=?', (g_id,))
        seat_to_name = {row[0]: row[1] for row in c.fetchall()}
        name_to_seat = {row[1]: row[0] for row in seat_to_name.items()}
        
        c.execute('SELECT kyoku_name, winner, score, win_type FROM rounds WHERE game_id=? ORDER BY id', (g_id,))
        db_rounds = c.fetchall()
        
        # ラウンド情報を整形
        rounds_info = []
        for r in db_rounds:
            kyoku, w_name, score, w_type = r
            w_seat = name_to_seat.get(w_name)
            rounds_info.append((kyoku, w_seat, score, w_type))
            
        # 親マップの取得
        dealer_map = find_dealer_map(rounds_info)
        
        # 検証
        for kyoku, w_seat, score, w_type in rounds_info:
            if w_seat is None or w_type not in ('ron', 'tsumo'):
                continue
                
            k_num = int(kyoku[1]) if len(kyoku)>=3 and kyoku[1].isdigit() else 1
            dealer_seat = dealer_map.get(k_num, k_num)
            is_dealer = (w_seat == dealer_seat)
            
            actual_score = score
            if w_type == 'tsumo':
                actual_score = get_actual_tsumo_score(score, is_dealer)
                
            if not is_valid_score(actual_score, is_dealer, w_type == 'tsumo'):
                unexplained.append({
                    'game_id': g_id,
                    'kyoku': kyoku,
                    'w_seat': w_seat,
                    'dealer_seat': dealer_seat,
                    'is_dealer': is_dealer,
                    'score': score,
                    'actual_score': actual_score,
                    'type': w_type,
                    'dealer_map': dealer_map
                })
                
    print(f'Total Unexplained Rounds: {len(unexplained)}')
    for u in unexplained[:20]:
        print(u)

if __name__ == '__main__':
    main()
