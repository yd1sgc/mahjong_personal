import sys, os, sqlite3
import streamlit as st
sys.path.append(os.path.join(os.getcwd(), 'src'))
import database2 as db

local_db = r'C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db'
remote_secrets = dict(st.secrets['database'])
db.init_config(is_local=False, remote_db_kwargs=remote_secrets)

# Fetch local games 264-268
l_conn = sqlite3.connect(local_db)
lc = l_conn.cursor()

local_targets = [264, 265, 266, 267, 268]
local_game_data = {} 

for gid in local_targets:
    lc.execute('SELECT display_name_snapshot, score FROM game_participants WHERE game_id = ?', (gid,))
    participants = frozenset((row[0], row[1]) for row in lc.fetchall())
    local_game_data[gid] = participants

l_conn.close()

# Fetch remote games
remote_game_data = {}
with db._remote_db() as r_conn:
    rc = r_conn.cursor()
    rc.execute('SELECT game_id, display_name_snapshot, score FROM game_participants')
    for row in rc.fetchall():
        rgid, name, score = row
        if rgid not in remote_game_data:
            remote_game_data[rgid] = set()
        remote_game_data[rgid].add((name, score))

for rgid in remote_game_data:
    remote_game_data[rgid] = frozenset(remote_game_data[rgid])

# Compare
missing_online = []
found_online = []
for lgid, l_participants in local_game_data.items():
    found_rgid = None
    for rgid, r_participants in remote_game_data.items():
        if l_participants == r_participants:
            found_rgid = rgid
            break
    if not found_rgid:
        missing_online.append(lgid)
    else:
        found_online.append((lgid, found_rgid))

print(f"Games found online: {found_online}")
print(f"Missing online: {missing_online}")
