import sqlite3
import json
import time
import os
import itertools
import re

def generate_uuid7():
    ts = int(time.time() * 1000)
    ts_hex = f"{ts:012x}"
    rand_hex = os.urandom(10).hex()
    return f"{ts_hex[:8]}-{ts_hex[8:12]}-7{rand_hex[:3]}-8{rand_hex[3:6]}-{rand_hex[6:]}"

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

def get_k_num(kyoku_name):
    if not kyoku_name: return 1
    match = re.search(r'([1-4１-４])', kyoku_name)
    if match:
        num = match.group(1).translate(str.maketrans('１２３４', '1234'))
        return int(num)
    return 1

def evaluate_dealer_map(rounds_info, dealer_map):
    errors = 0
    for kyoku, w_seat, score, w_type in rounds_info:
        if w_seat is None or w_type not in ('ron', 'tsumo'): continue
        k_num = get_k_num(kyoku)
        dealer_seat = dealer_map[k_num]
        is_dealer = (w_seat == dealer_seat)
        actual_score = get_actual_tsumo_score(score, is_dealer) if w_type == 'tsumo' else score
        if not is_valid_score(actual_score, is_dealer, w_type == 'tsumo'):
            errors += 1
    return errors

def predict_han_fu_full(score, is_dealer, is_tsumo):
    s = abs(score)
    if s == 0: return None, None
    actual = get_actual_tsumo_score(s, is_dealer) if is_tsumo else s
    
    if is_dealer:
        if actual >= 48000: return 13, None
        if actual >= 36000: return 11, None
        if actual >= 24000: return 8, None
        if actual >= 18000: return 6, 30
        if actual >= 12000: return 4, 40
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
        if actual >= 32000: return 13, None
        if actual >= 24000: return 11, None
        if actual >= 16000: return 8, None
        if actual >= 12000: return 6, 30
        if actual >= 8000: return 4, 40
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
    return None, None

OLD_DB_PATH = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db"
NEW_DB_PATH = r"C:\Users\segu1\MyFiles\開発\repos\mahjong_personal\local_mahjong_v2_new.db"

def init_new_db(c):
    c.executescript('''
    CREATE TABLE members (
        member_id VARCHAR(36) PRIMARY KEY,
        member_name VARCHAR(255) NOT NULL,
        is_guest INTEGER NOT NULL DEFAULT 0,
        is_archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE groups (
        group_id VARCHAR(36) PRIMARY KEY,
        display_id VARCHAR(32),
        group_name VARCHAR(255) NOT NULL,
        default_rule_id VARCHAR(36),
        is_archived INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE group_memberships (
        group_id VARCHAR(36) NOT NULL,
        member_id VARCHAR(36) NOT NULL,
        joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (group_id, member_id)
    );
    CREATE TABLE rule_templates (
        rule_id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        kind VARCHAR(32) NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        config_json TEXT NOT NULL,
        is_archived INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE games (
        game_id VARCHAR(36) PRIMARY KEY,
        played_at TEXT NOT NULL,
        group_id VARCHAR(36),
        rule_name_snapshot VARCHAR(255) NOT NULL,
        rule_config_snapshot TEXT NOT NULL,
        game_mode VARCHAR(32) NOT NULL DEFAULT 'detail',
        is_synced INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE game_participants (
        game_id VARCHAR(36) NOT NULL,
        seat INTEGER NOT NULL,
        member_id VARCHAR(36) NOT NULL,
        player_name_snapshot VARCHAR(255) NOT NULL,
        final_score INTEGER NOT NULL,
        rank INTEGER NOT NULL,
        point REAL NOT NULL,
        was_group_member INTEGER NOT NULL,
        PRIMARY KEY (game_id, seat)
    );
    CREATE TABLE rounds (
        round_id VARCHAR(36) PRIMARY KEY,
        game_id VARCHAR(36) NOT NULL,
        round_index INTEGER NOT NULL,
        kyoku_name VARCHAR(64) NOT NULL,
        honba INTEGER NOT NULL DEFAULT 0,
        riichi_sticks INTEGER NOT NULL DEFAULT 0,
        result_type VARCHAR(32) NOT NULL
    );
    CREATE TABLE round_seats (
        round_id VARCHAR(36) NOT NULL,
        seat INTEGER NOT NULL,
        member_id VARCHAR(36) NOT NULL,
        base_point INTEGER NOT NULL DEFAULT 0,
        honba_point INTEGER NOT NULL DEFAULT 0,
        kyotaku_point INTEGER NOT NULL DEFAULT 0,
        penalty_point INTEGER NOT NULL DEFAULT 0,
        score_delta INTEGER NOT NULL DEFAULT 0,
        chip_delta INTEGER NOT NULL DEFAULT 0,
        han INTEGER,
        fu INTEGER,
        is_winner INTEGER NOT NULL DEFAULT 0,
        is_loser INTEGER NOT NULL DEFAULT 0,
        is_riichi INTEGER NOT NULL DEFAULT 0,
        is_furo INTEGER NOT NULL DEFAULT 0,
        is_tenpai INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (round_id, seat)
    );
    ''')

def main():
    if os.path.exists(NEW_DB_PATH):
        os.remove(NEW_DB_PATH)

    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_conn.row_factory = sqlite3.Row
    old_c = old_conn.cursor()

    new_conn = sqlite3.connect(NEW_DB_PATH)
    new_c = new_conn.cursor()

    init_new_db(new_c)

    old_c.execute("SELECT member_id as id, member_name as name FROM members")
    member_map = {}
    for r in old_c.fetchall():
        m_id = generate_uuid7()
        member_map[r['name']] = m_id
        new_c.execute("INSERT INTO members (member_id, member_name) VALUES (?, ?)", (m_id, r['name']))
        
    group_id = generate_uuid7()
    new_c.execute("INSERT INTO groups (group_id, group_name) VALUES (?, ?)", (group_id, "Personal Group"))
    
    for m_id in member_map.values():
        new_c.execute("INSERT INTO group_memberships (group_id, member_id) VALUES (?, ?)", (group_id, m_id))

    old_c.execute("SELECT * FROM games ORDER BY date")
    games = old_c.fetchall()
    
    perms = list(itertools.permutations([1, 2, 3, 4]))

    for g in games:
        game_id_new = generate_uuid7()
        rule_cfg = g['applied_rule_json'] if g['applied_rule_json'] else '{}'
        new_c.execute("""
            INSERT INTO games (game_id, played_at, group_id, rule_name_snapshot, rule_config_snapshot)
            VALUES (?, ?, ?, ?, ?)
        """, (game_id_new, g['date'] + " 00:00:00", group_id, g['rule_name_snapshot'], rule_cfg))
        
        old_c.execute("SELECT * FROM game_participants WHERE game_id=? ORDER BY seat", (g['game_id'],))
        participants = old_c.fetchall()
        seats_info = {}
        for p in participants:
            p_name = p['display_name_snapshot']
            m_id = member_map.get(p_name)
            if not m_id:
                m_id = generate_uuid7()
                member_map[p_name] = m_id
                new_c.execute("INSERT INTO members (member_id, member_name) VALUES (?, ?)", (m_id, p_name))
            
            seats_info[p_name] = {'seat': p['seat'], 'm_id': m_id}
            new_c.execute("""
                INSERT INTO game_participants (game_id, seat, member_id, player_name_snapshot, final_score, rank, point, was_group_member)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id_new, p['seat'], m_id, p_name, p['score'], p['rank'], 0.0, 1))
            
        old_c.execute("SELECT * FROM rounds WHERE game_id=? ORDER BY id", (g['game_id'],))
        rounds = old_c.fetchall()
        
        rounds_for_eval = []
        for ro in rounds:
            w_name = ro['winner']
            w_seat = seats_info[w_name]['seat'] if w_name in seats_info else None
            rounds_for_eval.append((ro['kyoku_name'], w_seat, ro['score'], ro['win_type']))
            
        best_errors = 999
        best_map = {1:1, 2:2, 3:3, 4:4}
        if rounds_for_eval:
            best_errors = evaluate_dealer_map(rounds_for_eval, best_map)
            if best_errors > 0:
                for perm in perms:
                    d_map = {1: perm[0], 2: perm[1], 3: perm[2], 4: perm[3]}
                    errs = evaluate_dealer_map(rounds_for_eval, d_map)
                    if errs < best_errors:
                        best_errors = errs
                        best_map = d_map
                    if best_errors == 0:
                        break

        round_idx = 0
        honba = 0
        riichi_sticks = 0
        
        for ro in rounds:
            k_num = get_k_num(ro['kyoku_name'])
            dealer_seat = best_map[k_num]
            
            winner = ro['winner']
            loser = ro['loser']
            score = ro['score']
            r_type = ro['win_type']
            
            riichi_list = [n.strip() for n in ro['riichi_names'].split(',')] if ro['riichi_names'] else []
            furo_list = [n.strip() for n in ro['furo_names'].split(',')] if ro['furo_names'] else []
            tenpai_list = [n.strip() for n in ro['tenpai_names'].split(',')] if ro['tenpai_names'] else []
            
            dealer_name = None
            for n, info in seats_info.items():
                if info['seat'] == dealer_seat:
                    dealer_name = n
                    
            for p_name in riichi_list: riichi_sticks += 1
                
            round_id_new = generate_uuid7()
            new_c.execute("""
                INSERT INTO rounds (round_id, game_id, round_index, kyoku_name, honba, riichi_sticks, result_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (round_id_new, game_id_new, round_idx, ro['kyoku_name'], honba, riichi_sticks, r_type))
            
            dealer_continues = False
            deltas = {s: {'base':0, 'honba':0, 'kyotaku':0, 'penalty':0, 'is_w':0, 'is_l':0, 'is_r':0, 'is_f':0, 'is_t':0} for s in range(1, 5)}
            
            for p_name, info in seats_info.items():
                s = info['seat']
                if p_name in riichi_list: deltas[s]['is_r'] = 1
                if p_name in furo_list: deltas[s]['is_f'] = 1
                if p_name in tenpai_list: deltas[s]['is_t'] = 1
                if p_name == winner: deltas[s]['is_w'] = 1
                if p_name == loser: deltas[s]['is_l'] = 1
            
            w_seat = seats_info[winner]['seat'] if winner in seats_info else None
            l_seat = seats_info[loser]['seat'] if loser in seats_info else None
            
            if r_type == 'ron':
                if w_seat and l_seat:
                    deltas[w_seat]['base'] += score
                    deltas[l_seat]['base'] -= score
                    deltas[w_seat]['honba'] += honba * 300
                    deltas[l_seat]['honba'] -= honba * 300
                    deltas[w_seat]['kyotaku'] += riichi_sticks * 1000
                riichi_sticks = 0
                if winner == dealer_name: dealer_continues = True
                    
            elif r_type == 'tsumo':
                if w_seat:
                    if winner == dealer_name:
                        ko_pay = int(((score / 3) + 99) // 100 * 100)
                        actual_total = ko_pay * 3
                        for s in range(1, 5):
                            if s != w_seat:
                                deltas[s]['base'] -= ko_pay
                                deltas[s]['honba'] -= honba * 100
                        deltas[w_seat]['base'] += actual_total
                        deltas[w_seat]['honba'] += honba * 300
                        dealer_continues = True
                    else:
                        ko_pay = int(((score / 4) + 99) // 100 * 100)
                        oya_pay = score - ko_pay * 2
                        if oya_pay < ko_pay: oya_pay = ko_pay * 2
                        actual_total = ko_pay * 2 + oya_pay
                        for s in range(1, 5):
                            if s != w_seat:
                                pay = oya_pay if s == dealer_seat else ko_pay
                                deltas[s]['base'] -= pay
                                deltas[s]['honba'] -= honba * 100
                        deltas[w_seat]['base'] += actual_total
                        deltas[w_seat]['honba'] += honba * 300
                    deltas[w_seat]['kyotaku'] += riichi_sticks * 1000
                riichi_sticks = 0
                
            elif r_type == 'ryukyoku':
                tenpai_cnt = len(tenpai_list)
                if 0 < tenpai_cnt < 4:
                    bappu = 3000
                    for p_name, info in seats_info.items():
                        s = info['seat']
                        if p_name in tenpai_list: deltas[s]['penalty'] += bappu // tenpai_cnt
                        else: deltas[s]['penalty'] -= bappu // (4 - tenpai_cnt)
                if dealer_name in tenpai_list: dealer_continues = True
            
            elif r_type == 'chombo':
                if w_seat:
                    oya_pay = 4000
                    ko_pay = 2000
                    if winner == dealer_name:
                        for s in range(1, 5):
                            if s != w_seat:
                                deltas[w_seat]['penalty'] -= oya_pay
                                deltas[s]['penalty'] += oya_pay
                    else:
                        for s in range(1, 5):
                            if s != w_seat:
                                pay = oya_pay if s == dealer_seat else ko_pay
                                deltas[w_seat]['penalty'] -= pay
                                deltas[s]['penalty'] += pay
                dealer_continues = True

            for p_name, info in seats_info.items():
                s = info['seat']
                d = deltas[s]
                if d['is_r']: d['kyotaku'] -= 1000
                total = d['base'] + d['honba'] + d['kyotaku'] + d['penalty']
                
                han, fu = None, None
                if d['is_w']:
                    han, fu = predict_han_fu_full(d['base'], (s == dealer_seat), r_type == 'tsumo')
                    
                new_c.execute("""
                    INSERT INTO round_seats 
                    (round_id, seat, member_id, base_point, honba_point, kyotaku_point, penalty_point, score_delta, chip_delta, han, fu,
                     is_winner, is_loser, is_riichi, is_furo, is_tenpai)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    round_id_new, s, info['m_id'], d['base'], d['honba'], d['kyotaku'], d['penalty'], total, 0, han, fu,
                    d['is_w'], d['is_l'], d['is_r'], d['is_f'], d['is_t']
                ))

            if r_type == 'chombo': pass
            elif r_type == 'ryukyoku':
                honba += 1
                if not dealer_continues: round_idx += 1
            else:
                if dealer_continues: honba += 1
                else: round_idx += 1; honba = 0

    new_conn.commit()
    print("Migration completed successfully!")

if __name__ == "__main__":
    main()
