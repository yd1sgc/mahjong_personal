import sqlite3

from database2 import migrate_local_identity_schema


def _create_legacy_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript('''
        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            date TEXT,
            p1_name TEXT, p1_score INTEGER, p1_rank INTEGER,
            p2_name TEXT, p2_score INTEGER, p2_rank INTEGER,
            p3_name TEXT, p3_score INTEGER, p3_rank INTEGER,
            p4_name TEXT, p4_score INTEGER, p4_rank INTEGER,
            is_synced INTEGER DEFAULT 0,
            group_id TEXT DEFAULT 'all',
            rule_id TEXT DEFAULT 'm_league',
            applied_rule_json TEXT
        );
        CREATE TABLE members (
            member_id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE member_groups (
            group_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            default_rule_id TEXT DEFAULT 'm_league'
        );
        CREATE TABLE group_members (
            group_id TEXT NOT NULL,
            member_name TEXT NOT NULL,
            PRIMARY KEY (group_id, member_name)
        );
        CREATE TABLE rules (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            config_json TEXT NOT NULL
        );
    ''')
    conn.execute("INSERT INTO rules VALUES ('rule_old1', 'Old Custom', 1, '{}')")

    conn.execute("INSERT INTO members (member_name) VALUES ('Alice')")
    conn.execute("INSERT INTO members (member_name) VALUES ('Bob')")
    conn.execute(
        "INSERT INTO member_groups VALUES ('group_shinseki', '親族麻雀', 'm_league')"
    )
    conn.executemany(
        "INSERT INTO group_members VALUES ('group_shinseki', ?)",
        [('Alice',), ('Bob',)]
    )
    conn.execute('''INSERT INTO games (game_id, date, p1_name, p1_score, p1_rank, p2_name, p2_score, p2_rank, p3_name, p3_score, p3_rank, p4_name, p4_score, p4_rank, is_synced) VALUES
        (1, '2026-08-04', 'Alice', 35000, 1, 'Bob', 25000, 2,
         'Guest', 22000, 3, 'Carol', 18000, 4, 0)''')
    return conn


def test_identity_migration_preserves_legacy_game_and_creates_participants():
    conn = _create_legacy_db()

    migrate_local_identity_schema(conn)

    # 旧列は残り、アプリ切替前でも過去データを失わない。
    game = conn.execute(
        "SELECT p1_name, p4_name, selected_group_id FROM games WHERE game_id=1"
    ).fetchone()
    assert game == ('Alice', 'Carol', None)

    participants = conn.execute('''SELECT seat, display_name_snapshot, score, rank,
        was_group_member FROM game_participants WHERE game_id=1 ORDER BY seat''').fetchall()
    assert participants == [
        (1, 'Alice', 35000, 1, None),
        (2, 'Bob', 25000, 2, None),
        (3, 'Guest', 22000, 3, None),
        (4, 'Carol', 18000, 4, None),
    ]


def test_identity_migration_links_groups_by_member_id_and_allows_duplicate_names():
    conn = _create_legacy_db()

    migrate_local_identity_schema(conn)

    linked_names = conn.execute('''SELECT m.member_name
        FROM group_memberships gm
        JOIN members m ON m.member_id = gm.member_id
        WHERE gm.group_id = 'group_shinseki'
        ORDER BY m.member_name''').fetchall()
    assert linked_names == [('Alice',), ('Bob',)]

    conn.execute("INSERT INTO members (member_name) VALUES ('Alice')")
    assert conn.execute(
        "SELECT COUNT(*) FROM members WHERE member_name='Alice'"
    ).fetchone()[0] == 2

    version = conn.execute(
        "SELECT value FROM schema_meta WHERE key='identity_schema_version'"
    ).fetchone()[0]
    assert version == '1'

def test_identity_migration_creates_rule_templates():
    conn = _create_legacy_db()

    migrate_local_identity_schema(conn)

    # 1. Official presets should be seeded
    official = conn.execute("SELECT rule_id FROM rule_templates WHERE kind='official' AND rule_id='preset_m_league'").fetchone()
    assert official is not None, "m_league preset should be seeded as official"

    # 2. Legacy rules should be migrated as 'custom'
    legacy = conn.execute("SELECT rule_id, name, kind, is_archived FROM rule_templates WHERE rule_id='rule_old1'").fetchone()
    assert legacy == ('rule_old1', 'Old Custom', 'custom', 0)

def test_save_game_inserts_participants():
    from database2 import save_game
    conn = _create_legacy_db()
    migrate_local_identity_schema(conn)

    # Monkeypatch the DB context to use our test connection
    import database2
    from contextlib import contextmanager
    @contextmanager
    def mock_local_db():
        yield conn
    
    original_db = database2._local_db
    database2._local_db = mock_local_db
    
    try:
        # We need members in the DB to map them
        alice_id = conn.execute("SELECT member_id FROM members WHERE member_name='Alice'").fetchone()[0]
        bob_id = conn.execute("SELECT member_id FROM members WHERE member_name='Bob'").fetchone()[0]
        
        scores = {"Alice": 40000, "Bob": 30000, "Charlie": 20000, "Dave": 10000}
        players = ["Alice", "Bob", "Charlie", "Dave"]
        player_member_ids = {"Alice": alice_id, "Bob": bob_id, "Charlie": None, "Dave": None}
        
        game_id = save_game("2026-08-05", scores, players, local=True, player_member_ids=player_member_ids)
        
        participants = conn.execute("SELECT seat, member_id, display_name_snapshot, score, rank FROM game_participants WHERE game_id=? ORDER BY seat", (game_id,)).fetchall()
        
        assert participants == [
            (1, alice_id, 'Alice', 40000, 1),
            (2, bob_id, 'Bob', 30000, 2),
            (3, None, 'Charlie', 20000, 3),
            (4, None, 'Dave', 10000, 4)
        ]
    finally:
        database2._local_db = original_db
