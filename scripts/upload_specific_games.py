import sys, os, sqlite3
import streamlit as st
sys.path.append(os.path.join(os.getcwd(), 'src'))
import database2 as db

local_db = r'C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db'
remote_secrets = dict(st.secrets['database'])
db.init_config(is_local=False, remote_db_kwargs=remote_secrets)

TARGET_GAMES = (267, 268)

l_conn = sqlite3.connect(local_db)
lc = l_conn.cursor()

lc.execute('SELECT game_id, date, group_id, rule_id, applied_rule_json, selected_group_id, rule_name_snapshot, rule_schema_version FROM games WHERE game_id IN (?, ?) ORDER BY game_id', TARGET_GAMES)
games = lc.fetchall()

lc.execute('SELECT game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member FROM game_participants WHERE game_id IN (?, ?) ORDER BY game_id, seat', TARGET_GAMES)
participants = lc.fetchall()

lc.execute('SELECT game_id, kyoku_name, winner, loser, score, furo_names, riichi_names, riichi_count, tenpai_names, win_type, multi_wins_json FROM rounds WHERE game_id IN (?, ?) ORDER BY game_id, id', TARGET_GAMES)
rounds = lc.fetchall()

group_ids = set([g[2] for g in games] + [g[5] for g in games])
group_ids.discard(None)
rule_ids = set([g[3] for g in games])
rule_ids.discard(None)
member_ids = set([p[2] for p in participants])
member_ids.discard(None)

local_groups = []
for gid in group_ids:
    lc.execute('SELECT group_id, display_id, group_name, default_rule_id, is_archived FROM groups WHERE group_id = ?', (gid,))
    r = lc.fetchone()
    if r: local_groups.append(r)

local_rules = []
for rid in rule_ids:
    lc.execute('SELECT rule_id, name, kind, version, config_json, is_archived FROM rule_templates WHERE rule_id = ?', (rid,))
    r = lc.fetchone()
    if r: local_rules.append(r)

local_members = []
for mid in member_ids:
    lc.execute('SELECT member_id, member_name, is_archived FROM members WHERE member_id = ?', (mid,))
    r = lc.fetchone()
    if r: local_members.append(r)

l_conn.close()

remote_conn = db.get_connection()
rc = remote_conn.cursor()

try:
    for m in local_members:
        rc.execute('''
            INSERT INTO members (member_id, member_name, is_archived)
            VALUES (%s, %s, %s)
            ON CONFLICT (member_id) DO UPDATE SET
                member_name = EXCLUDED.member_name,
                is_archived = EXCLUDED.is_archived
        ''', m)

    for g in local_groups:
        rc.execute('''
            INSERT INTO groups (group_id, display_id, group_name, default_rule_id, is_archived)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (group_id) DO UPDATE SET
                display_id = EXCLUDED.display_id,
                group_name = EXCLUDED.group_name,
                default_rule_id = EXCLUDED.default_rule_id,
                is_archived = EXCLUDED.is_archived
        ''', g)

    for r in local_rules:
        config_json = r[4] if r[4] else None
        rc.execute('''
            INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (rule_id) DO UPDATE SET
                name = EXCLUDED.name,
                kind = EXCLUDED.kind,
                version = EXCLUDED.version,
                config_json = EXCLUDED.config_json,
                is_archived = EXCLUDED.is_archived
        ''', (r[0], r[1], r[2], r[3], config_json, r[5]))

    rc.execute("SELECT COALESCE(MAX(game_id), 0) FROM games")
    max_remote_id = rc.fetchone()[0]

    remote_game_id_map = {}
    for g in games:
        local_gid = g[0]
        max_remote_id += 1
        new_gid = max_remote_id
        remote_game_id_map[local_gid] = new_gid
        
        applied_rule_json = g[4] if g[4] else None
        rc.execute('''
            INSERT INTO games (
                game_id, date, group_id, rule_id, applied_rule_json,
                selected_group_id, rule_name_snapshot, rule_schema_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (new_gid, g[1], g[2], g[3], applied_rule_json, g[5], g[6], g[7]))

    for p in participants:
        local_gid = p[0]
        new_gid = remote_game_id_map[local_gid]
        rc.execute('''
            INSERT INTO game_participants (
                game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (new_gid, p[1], p[2], p[3], p[4], p[5], p[6]))

    for r in rounds:
        local_gid = r[0]
        new_gid = remote_game_id_map[local_gid]
        multi_wins_json = r[10] if r[10] else None
        
        rc.execute('''
            INSERT INTO rounds (
                game_id, kyoku_name, winner, loser, score,
                furo_names, riichi_names, riichi_count, tenpai_names, win_type, multi_wins_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ''', (new_gid, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], multi_wins_json))

    remote_conn.commit()
    print("SUCCESS: Target games successfully copied to remote.")
    for l_id, r_id in remote_game_id_map.items():
        print(f"  Local Game ID: {l_id} -> Remote Game ID: {r_id}")

except Exception as e:
    remote_conn.rollback()
    print(f"FAILED: {e}")
finally:
    rc.close()
    remote_conn.close()
