import sqlite3
import json
import time
import os

def generate_uuid7():
    # UUID v7 互換の文字列生成 (ミリ秒タイムスタンプ + ランダム)
    ts = int(time.time() * 1000)
    ts_hex = f"{ts:012x}"
    rand_hex = os.urandom(10).hex()
    return f"{ts_hex[:8]}-{ts_hex[8:12]}-7{rand_hex[:3]}-8{rand_hex[3:6]}-{rand_hex[6:]}"

def predict_han_fu(score, is_dealer):
    # 基本点(score)からハン・符を予測する
    # ※あくまで確率の高い組み合わせを返す。完全に特定は不可能。
    if score == 0: return None, None
    s = abs(score)
    if is_dealer:
        # 親の点数
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
        if s == 2400: return 2, 25
        if s == 2000: return 2, 20  # ツモピンフ等
        if s == 1500: return 1, 30
    else:
        # 子の点数
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
        if s == 2600: return 2, 40
        if s == 2000: return 2, 30
        if s == 1600: return 2, 25
        if s == 1300: return 1, 40
        if s == 1000: return 1, 30
    return None, None

OLD_DB_PATH = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db"
NEW_DB_PATH = r"C:\Users\segu1\MyFiles\開発\repos\mahjong_personal\local_mahjong_v2.db"

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
        print(f"Removed existing {NEW_DB_PATH}")

    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_conn.row_factory = sqlite3.Row
    old_c = old_conn.cursor()

    new_conn = sqlite3.connect(NEW_DB_PATH)
    new_c = new_conn.cursor()

    init_new_db(new_c)
    
    print("Migrating Master Data...")

    # 1. ルールテンプレート
    old_c.execute("SELECT * FROM rules")
    rule_map = {} # old_id -> new_uuid
    for r in old_c.fetchall():
        new_id = generate_uuid7()
        rule_map[r['rule_id']] = new_id
        new_c.execute(
            "INSERT INTO rule_templates (rule_id, name, kind, config_json) VALUES (?, ?, ?, ?)",
            (new_id, r['rule_name'], 'official' if r['is_default'] else 'custom', r['config_json'])
        )
        
    # 2. メンバーマスタ
    old_c.execute("SELECT * FROM members")
    member_map = {} # name -> new_uuid (旧メンバーはnameが実質IDだった)
    for m in old_c.fetchall():
        name = m['member_name']
        new_id = generate_uuid7()
        member_map[name] = new_id
        is_archived = m['is_archived'] if 'is_archived' in m.keys() else 0
        new_c.execute(
            "INSERT INTO members (member_id, member_name, is_guest, is_archived) VALUES (?, ?, 0, ?)",
            (new_id, name, is_archived)
        )
    
    # 未登録ゲストの抽出
    def get_or_create_member(name):
        name = name.strip() if name else ""
        if not name: return None
        if name in member_map:
            return member_map[name]
        new_id = generate_uuid7()
        member_map[name] = new_id
        new_c.execute(
            "INSERT INTO members (member_id, member_name, is_guest) VALUES (?, ?, 1)",
            (new_id, name)
        )
        return new_id

    # 3. グループマスタ
    try:
        old_c.execute("SELECT * FROM groups")
        has_groups = True
    except sqlite3.OperationalError:
        has_groups = False

    group_map = {} # old_id -> new_uuid
    if has_groups:
        old_c.execute("SELECT * FROM groups")
        for g in old_c.fetchall():
            new_id = generate_uuid7()
            group_map[g['group_id']] = new_id
            old_r_id = g['default_rule_id']
            new_r_id = rule_map.get(old_r_id)
            is_arc = g['is_archived'] if 'is_archived' in g.keys() else 0
            new_c.execute(
                "INSERT INTO groups (group_id, display_id, group_name, default_rule_id, is_archived) VALUES (?, ?, ?, ?, ?)",
                (new_id, g['display_id'] if 'display_id' in g.keys() else None, g['group_name'], new_r_id, is_arc)
            )
            
        old_c.execute("SELECT * FROM group_memberships")
        for gm in old_c.fetchall():
            # 古いgroup_membershipsのmember_idは整数ID。名前を引いてから新UUIDへ変換
            old_c.execute("SELECT member_name FROM members WHERE member_id=?", (gm['member_id'],))
            m_row = old_c.fetchone()
            if m_row:
                m_name = m_row['member_name']
                if m_name in member_map and gm['group_id'] in group_map:
                    new_c.execute(
                        "INSERT INTO group_memberships (group_id, member_id) VALUES (?, ?)",
                        (group_map[gm['group_id']], member_map[m_name])
                    )
    
    print("Migrating Games and Rounds (Simulating matches)...")
    
    # 4. 対局データ
    old_c.execute("SELECT * FROM games")
    games = old_c.fetchall()
    
    for g in games:
        game_id_old = g['game_id']
        game_id_new = generate_uuid7()
        
        rule_cfg_json = g['applied_rule_json']
        if not rule_cfg_json:
            rule_cfg_json = "{}" # 後で補完できるならする
            
        old_group_id = g['group_id'] if 'group_id' in g.keys() else 'all'
        new_group_id = group_map.get(old_group_id)
            
        new_c.execute(
            "INSERT INTO games (game_id, played_at, group_id, rule_name_snapshot, rule_config_snapshot, is_synced) VALUES (?, ?, ?, ?, ?, ?)",
            (game_id_new, g['date'], new_group_id, g['rule_id'] if 'rule_id' in g.keys() else 'unknown', rule_cfg_json, 1)
        )
        
        # 参加者
        seats_info = {}
        old_c.execute("SELECT * FROM game_participants WHERE game_id=?", (game_id_old,))
        for p in old_c.fetchall():
            s = p['seat']
            name = p['display_name_snapshot']
            if name:
                m_id = get_or_create_member(name)
                was_member = p['was_group_member'] if 'was_group_member' in p.keys() and p['was_group_member'] is not None else 0
                new_c.execute("""
                    INSERT INTO game_participants 
                    (game_id, seat, member_id, player_name_snapshot, final_score, rank, point, was_group_member)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (game_id_new, s, m_id, name, p['score'], p['rank'], 0.0, was_member))
                seats_info[name] = {'seat': s, 'm_id': m_id}

        # 局の逆算シミュレーション
        old_c.execute("SELECT * FROM rounds WHERE game_id=? ORDER BY id", (game_id_old,))
        rounds_old = old_c.fetchall()
        
        round_idx = 0
        honba = 0
        riichi_sticks = 0
        
        for ro in rounds_old:
            r_type = ro['win_type'] or 'ron'
            if r_type == '': r_type = 'ron'
            if r_type == 'mid_ryukyoku': r_type = 'ryukyoku' # 簡単のため
            
            winner = ro['winner'] or ''
            loser = ro['loser'] or ''
            score = int(ro['score']) if ro['score'] else 0
            
            furo_list = [n.strip() for n in ro['furo_names'].split(',')] if ro['furo_names'] else []
            riichi_list = [n.strip() for n in ro['riichi_names'].split(',')] if ro['riichi_names'] else []
            tenpai_list = [n.strip() for n in ro['tenpai_names'].split(',')] if ro['tenpai_names'] else []
            
            # 親の特定 (1~4)
            k_name = ro['kyoku_name']
            if k_name and len(k_name) >= 3 and k_name[1].isdigit():
                dealer_seat = int(k_name[1])
            else:
                dealer_seat = (round_idx % 4) + 1
                
            dealer_name = None
            for n, info in seats_info.items():
                if info['seat'] == dealer_seat:
                    dealer_name = n
            
            # 立直棒徴収
            for p_name in riichi_list:
                riichi_sticks += 1
                
            round_id_new = generate_uuid7()
            new_c.execute("""
                INSERT INTO rounds (round_id, game_id, round_index, kyoku_name, honba, riichi_sticks, result_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (round_id_new, game_id_new, round_idx, ro['kyoku_name'], honba, riichi_sticks, r_type))
            
            dealer_continues = False
            
            # 点数移動用の変数 (seat -> info)
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
                if winner == dealer_name:
                    dealer_continues = True
                    
            elif r_type == 'tsumo':
                if w_seat:
                    if winner == dealer_name:
                        # 親ツモ
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
                        # 子ツモ
                        ko_pay = int(((score / 4) + 99) // 100 * 100)
                        oya_pay = score - ko_pay * 2
                        # 補正（2000点のような手入力対応）
                        if oya_pay < ko_pay:
                            oya_pay = ko_pay * 2
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
                
            elif r_type == 'multi_ron':
                mw_json = ro['multi_wins_json']
                if mw_json:
                    mws = json.loads(mw_json)
                    closest_dist = 99
                    head_bump_seat = None
                    for mw in mws:
                        w_n = mw['winner']
                        if w_n in seats_info:
                            ws = seats_info[w_n]['seat']
                            deltas[ws]['is_w'] = 1
                            pt = mw['points_data']['total']
                            deltas[ws]['base'] += pt
                            deltas[ws]['honba'] += honba * 300
                            if l_seat:
                                deltas[l_seat]['base'] -= pt
                                deltas[l_seat]['honba'] -= honba * 300
                            if w_n == dealer_name: dealer_continues = True
                            
                            dist = (ws - l_seat) % 4 if l_seat else 0
                            if dist < closest_dist and dist > 0:
                                closest_dist = dist
                                head_bump_seat = ws
                    if head_bump_seat:
                        deltas[head_bump_seat]['kyotaku'] += riichi_sticks * 1000
                riichi_sticks = 0
            
            elif r_type == 'ryukyoku':
                tenpai_cnt = len(tenpai_list)
                if 0 < tenpai_cnt < 4:
                    bappu = 3000
                    for p_name, info in seats_info.items():
                        s = info['seat']
                        if p_name in tenpai_list:
                            deltas[s]['penalty'] += bappu // tenpai_cnt
                        else:
                            deltas[s]['penalty'] -= bappu // (4 - tenpai_cnt)
                if dealer_name in tenpai_list:
                    dealer_continues = True
            
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

            # レコード保存
            for p_name, info in seats_info.items():
                s = info['seat']
                d = deltas[s]
                # 立直宣言の-1000
                if d['is_r']:
                    d['kyotaku'] -= 1000
                
                total = d['base'] + d['honba'] + d['kyotaku'] + d['penalty']
                
                # ハンと符の予測
                han, fu = None, None
                if d['is_w']:
                    han, fu = predict_han_fu(d['base'], (s == dealer_seat))
                    
                new_c.execute("""
                    INSERT INTO round_seats 
                    (round_id, seat, member_id, base_point, honba_point, kyotaku_point, penalty_point, score_delta, chip_delta, han, fu,
                     is_winner, is_loser, is_riichi, is_furo, is_tenpai)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    round_id_new, s, info['m_id'], d['base'], d['honba'], d['kyotaku'], d['penalty'], total, 0, han, fu,
                    d['is_w'], d['is_l'], d['is_r'], d['is_f'], d['is_t']
                ))

            # 次局の準備
            if r_type == 'chombo':
                pass
            elif r_type == 'ryukyoku':
                honba += 1
                if not dealer_continues:
                    round_idx += 1
            else:
                if dealer_continues:
                    honba += 1
                else:
                    round_idx += 1
                    honba = 0

    new_conn.commit()
    print("Migration completed successfully!")

if __name__ == "__main__":
    main()
