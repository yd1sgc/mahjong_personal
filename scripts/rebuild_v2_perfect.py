import sqlite3
import json
import time
import os
import re

OLD_DB_PATH = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db"
NEW_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_mahjong_v2.db')

def generate_uuid7():
    ts = int(time.time() * 1000)
    ts_hex = f"{ts:012x}"
    rand_hex = os.urandom(10).hex()
    return f"{ts_hex[:8]}-{ts_hex[8:12]}-7{rand_hex[:3]}-8{rand_hex[3:6]}-{rand_hex[6:]}"

def predict_han_fu(score, is_dealer):
    if score == 0: return None, None
    s = abs(score)
    if is_dealer:
        if s >= 48000: return 13, None
        if s >= 36000: return 11, None
        if s >= 24000: return 8, None
        if s >= 18000: return 6, 30
        if s >= 12000: return 4, 40
        if s == 11600: return 4, 30
        if s == 9600: return 4, 25
        if s == 7700: return 3, 40
        if s == 5800: return 3, 30
        if s == 4800: return 3, 25
        if s == 3900: return 3, 30
        if s == 2900: return 2, 30
    else:
        if s >= 32000: return 13, None
        if s >= 24000: return 11, None
        if s >= 16000: return 8, None
        if s >= 12000: return 6, 30
        if s >= 8000: return 4, 40
        if s == 7700: return 4, 30
        if s == 6400: return 4, 25
        if s == 5200: return 3, 40
        if s == 3900: return 3, 30
        if s == 3200: return 3, 25
        if s == 2600: return 3, 30
        if s == 2000: return 2, 30
        if s == 1300: return 1, 40
        if s == 1000: return 1, 30
    return None, None

def get_correct_round_index(kyoku_name):
    if not kyoku_name:
        return 0
    wind_map = {"東": 0, "南": 1, "西": 2, "北": 3}
    match = re.search(r'(東|南|西|北)[^\d1-4]*([1-4１-４])', kyoku_name)
    if match:
        wind = match.group(1)
        num_str = match.group(2)
        num_str = num_str.translate(str.maketrans('１２３４', '1234'))
        num = int(num_str)
        return wind_map[wind] * 4 + (num - 1)
    return 0

def get_actual_tsumo_score(score, is_dealer):
    if is_dealer:
        ko_pay = int(((score / 3) + 99) // 100 * 100)
        return ko_pay * 3
    else:
        ko_pay = int(((score / 4) + 99) // 100 * 100)
        oya_pay = score - ko_pay * 2
        if oya_pay < ko_pay: oya_pay = ko_pay * 2
        return ko_pay * 2 + oya_pay

def find_dealer_map(rounds_info):
    dealer_map = {}
    for i in range(len(rounds_info) - 1):
        kyoku, w_seat, score, w_type = rounds_info[i]
        next_kyoku = rounds_info[i+1][0]
        if kyoku == next_kyoku and w_seat is not None:
            if w_type in ('ron', 'tsumo'):
                k_num = get_correct_round_index(kyoku)
                # Ensure we only map East 1-4 (0,1,2,3) to seats 1-4
                if k_num < 4:
                    dealer_map[k_num + 1] = w_seat

    oya_scores = [2900, 5800, 11600, 18000, 24000, 36000, 48000]
    oya_tsumos = [18000, 24000, 36000, 48000]
    for kyoku, w_seat, score, w_type in rounds_info:
        if w_seat is not None:
            k_num = get_correct_round_index(kyoku)
            if k_num < 4:
                if w_type == 'ron' and score in oya_scores:
                    dealer_map[k_num + 1] = w_seat
                elif w_type == 'tsumo':
                    actual = get_actual_tsumo_score(score, True)
                    if actual in oya_tsumos:
                        dealer_map[k_num + 1] = w_seat

    used_seats = set(dealer_map.values())
    if len(dealer_map) == 0:
        return {1: 1, 2: 2, 3: 3, 4: 4}
        
    for k in range(1, 5):
        if k not in dealer_map:
            for s in range(1, 5):
                if s not in used_seats:
                    dealer_map[k] = s
                    used_seats.add(s)
                    break
    return dealer_map

def init_new_db(c):
    c.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER)")
    c.execute("INSERT INTO schema_meta VALUES (2)")
    c.execute("""CREATE TABLE IF NOT EXISTS members (
        member_id TEXT PRIMARY KEY, member_name TEXT UNIQUE NOT NULL,
        is_guest INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS rule_templates (
        rule_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        kind TEXT CHECK(kind IN ('official', 'custom')), config_json TEXT,
        is_archived INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS groups (
        group_id TEXT PRIMARY KEY, display_id TEXT UNIQUE,
        group_name TEXT NOT NULL, default_rule_id TEXT,
        is_archived INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS group_memberships (
        group_id TEXT, member_id TEXT, PRIMARY KEY (group_id, member_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS games (
        game_id TEXT PRIMARY KEY, played_at TEXT NOT NULL, group_id TEXT,
        rule_name_snapshot TEXT, rule_config_snapshot TEXT,
        game_mode TEXT CHECK(game_mode IN ('simple', 'detail')) DEFAULT 'detail',
        is_synced INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS game_participants (
        game_id TEXT, seat INTEGER, member_id TEXT,
        player_name_snapshot TEXT, final_score INTEGER, rank INTEGER,
        point REAL, was_group_member INTEGER DEFAULT 0,
        PRIMARY KEY (game_id, seat))""")
    c.execute("""CREATE TABLE IF NOT EXISTS rounds (
        round_id TEXT PRIMARY KEY, game_id TEXT, round_index INTEGER,
        kyoku_name TEXT, honba INTEGER DEFAULT 0, riichi_sticks INTEGER DEFAULT 0,
        result_type TEXT, result_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS round_seats (
        round_id TEXT, seat INTEGER, member_id TEXT,
        base_point INTEGER DEFAULT 0, honba_point INTEGER DEFAULT 0,
        kyotaku_point INTEGER DEFAULT 0, penalty_point INTEGER DEFAULT 0,
        score_delta INTEGER DEFAULT 0, chip_delta INTEGER DEFAULT 0,
        han INTEGER, fu INTEGER, is_winner INTEGER DEFAULT 0,
        is_loser INTEGER DEFAULT 0, is_riichi INTEGER DEFAULT 0,
        is_furo INTEGER DEFAULT 0, is_tenpai INTEGER DEFAULT 0,
        PRIMARY KEY (round_id, seat))""")

def main():
    if os.path.exists(NEW_DB_PATH):
        os.remove(NEW_DB_PATH)
        print(f"Removed existing {NEW_DB_PATH}")

    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_conn.row_factory = sqlite3.Row
    old_c = old_conn.cursor()

    new_conn = sqlite3.connect(NEW_DB_PATH)
    new_c = new_conn.cursor()

    init_new_db(new_c)
    
    print("Migrating Master Data...")
    old_c.execute("SELECT * FROM rules")
    rule_map = {}
    for r in old_c.fetchall():
        new_id = generate_uuid7()
        rule_map[r['rule_id']] = new_id
        new_c.execute(
            "INSERT INTO rule_templates (rule_id, name, kind, config_json) VALUES (?, ?, ?, ?)",
            (new_id, r['rule_name'], 'official' if r['is_default'] else 'custom', r['config_json'])
        )
        
    old_c.execute("SELECT * FROM members")
    member_map = {}
    for m in old_c.fetchall():
        name = m['member_name']
        new_id = generate_uuid7()
        member_map[name] = new_id
        is_arc = m['is_archived'] if 'is_archived' in m.keys() else 0
        new_c.execute(
            "INSERT INTO members (member_id, member_name, is_guest, is_archived) VALUES (?, ?, 0, ?)",
            (new_id, name, is_arc)
        )
    
    def get_or_create_member(name):
        name = name.strip() if name else ""
        if not name: return None
        if name in member_map:
            return member_map[name]
        new_id = generate_uuid7()
        member_map[name] = new_id
        new_c.execute("INSERT INTO members (member_id, member_name, is_guest) VALUES (?, ?, 1)", (new_id, name))
        return new_id

    try:
        old_c.execute("SELECT * FROM groups")
        has_groups = True
    except sqlite3.OperationalError:
        has_groups = False

    group_map = {}
    if has_groups:
        old_c.execute("SELECT * FROM groups")
        for g in old_c.fetchall():
            new_id = generate_uuid7()
            group_map[g['group_id']] = new_id
            new_r_id = rule_map.get(g['default_rule_id'])
            is_arc = g['is_archived'] if 'is_archived' in g.keys() else 0
            d_id = g['display_id'] if 'display_id' in g.keys() else None
            new_c.execute(
                "INSERT INTO groups (group_id, display_id, group_name, default_rule_id, is_archived) VALUES (?, ?, ?, ?, ?)",
                (new_id, d_id, g['group_name'], new_r_id, is_arc)
            )
        old_c.execute("SELECT * FROM group_memberships")
        for gm in old_c.fetchall():
            old_c.execute("SELECT member_name FROM members WHERE member_id=?", (gm['member_id'],))
            m_row = old_c.fetchone()
            if m_row and m_row['member_name'] in member_map and gm['group_id'] in group_map:
                new_c.execute(
                    "INSERT INTO group_memberships (group_id, member_id) VALUES (?, ?)",
                    (group_map[gm['group_id']], member_map[m_row['member_name']])
                )
    
    print("Migrating Games and Rounds (Perfecting Seat Orders)...")
    old_c.execute("SELECT * FROM games")
    games = old_c.fetchall()
    
    for g in games:
        game_id_old = g['game_id']
        game_id_new = generate_uuid7()
        
        rule_cfg_json = g['applied_rule_json']
        if not rule_cfg_json: rule_cfg_json = "{}"
        
        old_group_id = g['group_id'] if 'group_id' in g.keys() else 'all'
        new_group_id = group_map.get(old_group_id)
        
        new_c.execute(
            "INSERT INTO games (game_id, played_at, group_id, rule_name_snapshot, rule_config_snapshot, is_synced) VALUES (?, ?, ?, ?, ?, ?)",
            (game_id_new, g['date'], new_group_id, g['rule_id'] if 'rule_id' in g.keys() else 'unknown', rule_cfg_json, 1)
        )
        
        old_c.execute("SELECT * FROM game_participants WHERE game_id=?", (game_id_old,))
        raw_participants = old_c.fetchall()
        
        old_c.execute("SELECT * FROM rounds WHERE game_id=? ORDER BY id", (game_id_old,))
        rounds_old = old_c.fetchall()
        
        if not rounds_old:
            for p in raw_participants:
                m_id = get_or_create_member(p['display_name_snapshot'])
                wm = p['was_group_member'] if 'was_group_member' in p.keys() and p['was_group_member'] is not None else 0
                new_c.execute("""
                    INSERT INTO game_participants 
                    (game_id, seat, member_id, player_name_snapshot, final_score, rank, point, was_group_member)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (game_id_new, p['seat'], m_id, p['display_name_snapshot'], p['score'], p['rank'], 0.0, wm))
            new_c.execute("UPDATE games SET game_mode='simple' WHERE game_id=?", (game_id_new,))
            continue

        seat_to_name = {p['seat']: p['display_name_snapshot'] for p in raw_participants}
        name_to_seat = {v:k for k,v in seat_to_name.items()}
        
        rounds_info = []
        for ro in rounds_old:
            w_seat = name_to_seat.get(ro['winner']) if ro['winner'] else None
            rounds_info.append((ro['kyoku_name'], w_seat, int(ro['score']) if ro['score'] else 0, ro['win_type'] or 'ron'))
            
        dealer_map = find_dealer_map(rounds_info)
        # dealer_map gives: new_seat -> old_seat
        old_to_new = {old_s: new_s for new_s, old_s in dealer_map.items()}
        
        seats_info = {}
        for p in raw_participants:
            old_s = p['seat']
            new_s = old_to_new.get(old_s, old_s)
            name = p['display_name_snapshot']
            if name:
                m_id = get_or_create_member(name)
                wm = p['was_group_member'] if 'was_group_member' in p.keys() and p['was_group_member'] is not None else 0
                new_c.execute("""
                    INSERT INTO game_participants 
                    (game_id, seat, member_id, player_name_snapshot, final_score, rank, point, was_group_member)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (game_id_new, new_s, m_id, name, p['score'], p['rank'], 0.0, wm))
                seats_info[name] = {'seat': new_s, 'm_id': m_id}

        round_idx = 0
        honba = 0
        riichi_sticks = 0
        
        for ro in rounds_old:
            r_type = ro['win_type'] or 'ron'
            if r_type == '': r_type = 'ron'
            if r_type == 'mid_ryukyoku': r_type = 'ryukyoku'
            
            winner = ro['winner'] or ''
            loser = ro['loser'] or ''
            score = int(ro['score']) if ro['score'] else 0
            
            furo_list = [n.strip() for n in ro['furo_names'].split(',')] if ro['furo_names'] else []
            riichi_list = [n.strip() for n in ro['riichi_names'].split(',')] if ro['riichi_names'] else []
            tenpai_list = [n.strip() for n in ro['tenpai_names'].split(',')] if ro['tenpai_names'] else []
            
            k_name = ro['kyoku_name']
            round_idx = get_correct_round_index(k_name)
            dealer_seat = (round_idx % 4) + 1
            
            dealer_name = None
            for n, info in seats_info.items():
                if info['seat'] == dealer_seat:
                    dealer_name = n
            
            for p_name in riichi_list:
                riichi_sticks += 1
                
            round_id_new = generate_uuid7()
            
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
                    
            elif r_type == 'tsumo':
                if w_seat:
                    if winner == dealer_name:
                        ko_pay = int(((score / 3) + 99) // 100 * 100)
                        deltas[w_seat]['base'] += ko_pay * 3
                        for s in range(1, 5):
                            if s != w_seat: deltas[s]['base'] -= ko_pay
                    else:
                        ko_pay = int(((score / 4) + 99) // 100 * 100)
                        oya_pay = score - (ko_pay * 2)
                        if oya_pay < ko_pay: oya_pay = ko_pay * 2
                        deltas[w_seat]['base'] += oya_pay + ko_pay * 2
                        for s in range(1, 5):
                            if s != w_seat:
                                pay = oya_pay if s == dealer_seat else ko_pay
                                deltas[s]['base'] -= pay
                    deltas[w_seat]['honba'] += honba * 300
                    for s in range(1, 5):
                        if s != w_seat: deltas[s]['honba'] -= honba * 100
                    deltas[w_seat]['kyotaku'] += riichi_sticks * 1000
                riichi_sticks = 0
                
            elif r_type == 'ryukyoku':
                t_count = len(tenpai_list)
                if 0 < t_count < 4:
                    get_p = 3000 // t_count
                    pay_p = 3000 // (4 - t_count)
                    for p_name, info in seats_info.items():
                        s = info['seat']
                        if p_name in tenpai_list: deltas[s]['penalty'] += get_p
                        else: deltas[s]['penalty'] -= pay_p
                        
            elif r_type == 'chombo':
                w_seat = seats_info[winner]['seat'] if winner in seats_info else None
                if w_seat:
                    if winner == dealer_name:
                        for s in range(1, 5):
                            if s != w_seat:
                                deltas[w_seat]['penalty'] -= 4000
                                deltas[s]['penalty'] += 4000
                    else:
                        for s in range(1, 5):
                            if s != w_seat:
                                pay = 4000 if s == dealer_seat else 2000
                                deltas[w_seat]['penalty'] -= pay
                                deltas[s]['penalty'] += pay
            
            # calculate honba for next round
            if r_type == 'ron' and winner == dealer_name: honba += 1
            elif r_type == 'tsumo' and winner == dealer_name: honba += 1
            elif r_type == 'ryukyoku' or r_type == 'chombo': honba += 1
            else: honba = 0
            
            new_c.execute("""
                INSERT INTO rounds (round_id, game_id, round_index, kyoku_name, honba, riichi_sticks, result_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (round_id_new, game_id_new, round_idx, ro['kyoku_name'], honba, riichi_sticks, r_type))

            for s in range(1, 5):
                d = deltas[s]
                m_id = next((info['m_id'] for info in seats_info.values() if info['seat'] == s), None)
                score_delta = d['base'] + d['honba'] + d['kyotaku'] + d['penalty']
                han, fu = None, None
                if d['is_w']:
                    han, fu = predict_han_fu(score, s == dealer_seat)
                
                new_c.execute("""
                    INSERT INTO round_seats 
                    (round_id, seat, member_id, base_point, honba_point, kyotaku_point, penalty_point, score_delta, chip_delta, han, fu, is_winner, is_loser, is_riichi, is_furo, is_tenpai)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (round_id_new, s, m_id, d['base'], d['honba'], d['kyotaku'], d['penalty'], score_delta, 0, han, fu, d['is_w'], d['is_l'], d['is_r'], d['is_f'], d['is_t']))

    new_conn.commit()
    new_conn.close()
    old_conn.close()
    print("Done! Local DB perfectly rebuilt.")

if __name__ == '__main__':
    main()
