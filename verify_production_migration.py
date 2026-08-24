import os
import sys
import types
import sqlite3

# Mock streamlit if not installed
if "streamlit" not in sys.modules:
    mock_st = types.ModuleType("streamlit")
    mock_st.secrets = {"local_mode": True}
    mock_st.cache_data = lambda *args, **kwargs: (lambda f: f)
    mock_st.session_state = {}
    sys.modules["streamlit"] = mock_st

import database2

def verify_prod():
    db_path = r"C:\Users\segu1\OneDrive\mahjong_personal\mahjong_local.db"
    assert os.path.exists(db_path), f"DB file not found at {db_path}"
    
    print(f"Applying migration to production database: {db_path}...")
    conn = sqlite3.connect(db_path)
    database2.migrate_local_identity_schema(conn)
    conn.commit()
    
    c = conn.cursor()
    
    # 1. Check tables
    tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"\nTables present: {tables}")
    
    # 2. Check counts
    games_count = c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    participants_count = c.execute("SELECT COUNT(*) FROM game_participants").fetchone()[0]
    members_count = c.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    groups_count = c.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
    rules_count = c.execute("SELECT COUNT(*) FROM rule_templates").fetchone()[0]
    rounds_count = c.execute("SELECT COUNT(*) FROM rounds").fetchone()[0] if "rounds" in tables else 0
    
    print("\n--- Production Data Summary ---")
    print(f"Total games: {games_count}")
    print(f"Total game_participants: {participants_count} (Expected: ~{games_count * 4})")
    print(f"Total members: {members_count}")
    print(f"Total groups: {groups_count}")
    print(f"Total rule templates: {rules_count}")
    print(f"Total rounds: {rounds_count}")
    
    # 3. Check sample game
    sample_game = c.execute("SELECT game_id, date, p1_name, p1_score, p2_name, p2_score FROM games ORDER BY game_id LIMIT 1").fetchone()
    if sample_game:
        g_id = sample_game[0]
        print(f"\nSample Game #{g_id}: {sample_game[1]} | P1: {sample_game[2]} ({sample_game[3]}) | P2: {sample_game[4]} ({sample_game[5]})")
        parts = c.execute("SELECT seat, display_name_snapshot, score, rank, member_id FROM game_participants WHERE game_id=? ORDER BY seat", (g_id,)).fetchall()
        print(f"Sample Participants for Game #{g_id}:")
        for p in parts:
            print(f"  Seat {p[0]}: {p[1]} | Score: {p[2]} | Rank: {p[3]} | Member ID: {p[4]}")
            
    conn.close()
    print("\nMigration and verification completed successfully!")

if __name__ == "__main__":
    verify_prod()
