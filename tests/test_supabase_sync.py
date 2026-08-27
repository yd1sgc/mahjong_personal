import os
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock
import database2


def _create_test_local_db_file():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    database2.migrate_local_identity_schema(conn)
    
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            kyoku_name TEXT,
            winner TEXT,
            loser TEXT,
            score INTEGER,
            furo_names TEXT DEFAULT '',
            riichi_names TEXT DEFAULT '',
            riichi_count INTEGER DEFAULT 0,
            tenpai_names TEXT DEFAULT '',
            win_type TEXT DEFAULT '',
            multi_wins_json TEXT DEFAULT '[]',
            ryukyoku_type TEXT DEFAULT '',
            is_synced INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            date TEXT,
            p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
            p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
            p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
            p4_name TEXT, p4_score INTEGER, p4_rank INTEGER,
            is_synced INTEGER DEFAULT 0,
            group_id TEXT DEFAULT 'all',
            rule_id TEXT DEFAULT 'm_league',
            applied_rule_json TEXT,
            selected_group_id TEXT,
            rule_name_snapshot TEXT,
            rule_schema_version INTEGER DEFAULT 1
        )
    ''')
    
    # Insert a group
    c.execute("INSERT OR REPLACE INTO groups (group_id, group_name, default_rule_id, is_archived) VALUES ('grp_test', 'Test Group', 'm_league', 0)")
    
    # Insert members
    c.execute("INSERT OR REPLACE INTO members (member_id, member_name, is_archived) VALUES (1, 'Alice', 0)")
    c.execute("INSERT OR REPLACE INTO members (member_id, member_name, is_archived) VALUES (2, 'Bob', 0)")
    c.execute("INSERT OR REPLACE INTO group_memberships (group_id, member_id) VALUES ('grp_test', 1)")
    
    # Insert unsynced game
    c.execute('''
        INSERT INTO games (game_id, date, p1_name, p1_score, p1_rank, p2_name, p2_score, p2_rank,
                           p3_name, p3_score, p3_rank, p4_name, p4_score, p4_rank,
                           is_synced, group_id, rule_id, applied_rule_json, selected_group_id, rule_name_snapshot)
        VALUES (101, '2026-08-23', 'Alice', 45000, 1, 'Bob', 25000, 2, 'Charlie', 20000, 3, 'Dave', 10000, 4,
                0, 'grp_test', 'preset_m_league', '{"basic":{}}', 'grp_test', 'Mリーグルール')
    ''')
    
    # Insert participants
    c.execute('''
        INSERT OR REPLACE INTO game_participants (game_id, seat, member_id, display_name_snapshot, score, rank, was_group_member)
        VALUES (101, 1, 1, 'Alice', 45000, 1, 1),
               (101, 2, 2, 'Bob', 25000, 2, 1),
               (101, 3, NULL, 'Charlie', 20000, 3, 0),
               (101, 4, NULL, 'Dave', 10000, 4, 0)
    ''')
    
    # Insert round
    c.execute('''
        INSERT INTO rounds (game_id, kyoku_name, winner, loser, score, furo_names, riichi_names, riichi_count, tenpai_names, win_type, is_synced)
        VALUES (101, '東1局', 'Alice', 'Dave', 8000, '', 'Alice', 1, 'Alice', 'ron', 0)
    ''')
    
    conn.commit()
    conn.close()
    return tmp.name


def test_sync_to_supabase_executes_queries_and_marks_synced():
    db_path = _create_test_local_db_file()
    
    # Mock remote connection & cursor
    mock_remote_conn = MagicMock()
    mock_remote_cursor = MagicMock()
    mock_remote_conn.cursor.return_value = mock_remote_cursor
    
    # Return max game_id = 50 for COALESCE(MAX(game_id), 0)
    mock_remote_cursor.fetchone.return_value = [50]
    
    try:
        with patch("database2.IS_LOCAL", True), \
             patch("database2.SQLITE_PATH", db_path), \
             patch("database2.get_local_connection", lambda: sqlite3.connect(db_path)), \
             patch("database2.get_connection", return_value=mock_remote_conn):
            
            synced_count = database2.sync_to_supabase()
            
            assert synced_count == 1
            
            # Verify local game and round are marked is_synced = 1
            verify_conn = sqlite3.connect(db_path)
            c = verify_conn.cursor()
            game_synced = c.execute("SELECT is_synced FROM games WHERE game_id=101").fetchone()[0]
            assert game_synced == 1
            
            round_synced = c.execute("SELECT is_synced FROM rounds WHERE game_id=101").fetchone()[0]
            assert round_synced == 1
            verify_conn.close()
            
            # Verify remote DB queries were executed
            calls = mock_remote_cursor.execute.call_args_list
            sql_statements = [call[0][0] for call in calls]
            
            # Check master data sync queries
            assert any("INSERT INTO members" in sql for sql in sql_statements)
            assert any("INSERT INTO groups" in sql for sql in sql_statements)
            assert any("INSERT INTO group_memberships" in sql for sql in sql_statements)
            assert any("INSERT INTO rule_templates" in sql for sql in sql_statements)
            
            # Check games and game_participants and rounds insert queries
            assert any("INSERT INTO games" in sql for sql in sql_statements)
            assert any("INSERT INTO game_participants" in sql for sql in sql_statements)
            assert any("INSERT INTO rounds" in sql for sql in sql_statements)
            
            # Verify commit was called
            mock_remote_conn.commit.assert_called_once()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_migration_sql_file_exists_and_contains_expected_tables():
    sql_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", "supabase_migration_v1.sql")
    assert os.path.exists(sql_path), "Migration SQL file should exist"
    
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    expected_keywords = [
        "CREATE TABLE IF NOT EXISTS schema_meta",
        "CREATE TABLE IF NOT EXISTS members",
        "CREATE TABLE IF NOT EXISTS groups",
        "CREATE TABLE IF NOT EXISTS group_memberships",
        "CREATE TABLE IF NOT EXISTS rule_templates",
        "CREATE TABLE IF NOT EXISTS game_participants",
        "ALTER TABLE games ADD COLUMN IF NOT EXISTS selected_group_id",
        "ALTER TABLE games ADD COLUMN IF NOT EXISTS rule_name_snapshot",
        "INSERT INTO game_participants",
        "INSERT INTO rule_templates",
    ]
    for kw in expected_keywords:
        assert kw in sql_content, f"SQL content should contain {kw}"
