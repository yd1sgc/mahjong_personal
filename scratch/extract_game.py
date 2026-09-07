import sqlite3
import json

conn = sqlite3.connect('local_mahjong_v2.db')
conn.row_factory = sqlite3.Row
game_id = '01a07816-7c5a-7b8f-85da-a572a81360e61c'

res = {
    'games': [dict(x) for x in conn.execute('SELECT * FROM games WHERE game_id=?', (game_id,))],
    'game_participants': [dict(x) for x in conn.execute('SELECT gp.*, m.member_name FROM game_participants gp JOIN members m ON gp.member_id = m.member_id WHERE gp.game_id=?', (game_id,))],
    'rounds': [dict(x) for x in conn.execute('SELECT * FROM rounds WHERE game_id=?', (game_id,))],
    'round_seats': [dict(x) for x in conn.execute('SELECT s.*, m.member_name FROM round_seats s JOIN rounds r ON s.round_id = r.round_id JOIN members m ON s.member_id = m.member_id WHERE r.game_id=?', (game_id,))]
}

with open('game_257_data.json', 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
