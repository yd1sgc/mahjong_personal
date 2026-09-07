import json
import os
import sqlite3
import time
import pandas as pd
from contextlib import contextmanager
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

# 設定は init_config() により外部(app.py等)から注入される
IS_LOCAL = False
SQLITE_PATH = None
REMOTE_DB_KWARGS = None


def init_config(is_local=False, sqlite_path=None, remote_db_kwargs=None):
    global IS_LOCAL, SQLITE_PATH, REMOTE_DB_KWARGS
    IS_LOCAL = is_local
    SQLITE_PATH = sqlite_path
    REMOTE_DB_KWARGS = remote_db_kwargs


def generate_uuid7() -> str:
    """ミリ秒タイムスタンプベースの UUID v7 (36文字文字列) を生成する。"""
    ts = int(time.time() * 1000)
    ts_hex = f"{ts:012x}"
    rand_hex = os.urandom(10).hex()
    return f"{ts_hex[:8]}-{ts_hex[8:12]}-7{rand_hex[:3]}-8{rand_hex[3:6]}-{rand_hex[6:]}"


def get_local_connection():
    if not SQLITE_PATH:
        raise RuntimeError("SQLITE_PATH が設定されていません")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _local_db():
    conn = get_local_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection():
    if psycopg2 is None:
        raise RuntimeError("オンラインDB接続には psycopg2-binary が必要です")
    if not REMOTE_DB_KWARGS:
        raise RuntimeError("リモートDB設定が初期化されていません")
    kwargs = dict(REMOTE_DB_KWARGS)
    if "connect_timeout" not in kwargs:
        kwargs["connect_timeout"] = 3
    return psycopg2.connect(**kwargs)


@contextmanager
def _remote_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _db(local=None):
    """local引数または IS_LOCAL の設定に応じてローカルまたはリモートのコンテキストを返す。"""
    use_local = IS_LOCAL if local is None else local
    if use_local:
        with _local_db() as conn:
            yield conn
    else:
        with _remote_db() as conn:
            yield conn


def _fetch_df(conn, query, params=None):
    c = conn.cursor()
    c.execute(query, params or ())
    rows = c.fetchall()
    if hasattr(c, "description") and c.description:
        cols = [desc[0] for desc in c.description]
        # sqlite3.Row またはタプルのリストから DataFrame を生成
        dict_rows = [dict(r) if isinstance(r, sqlite3.Row) else r for r in rows]
        return pd.DataFrame(dict_rows, columns=cols)
    return pd.DataFrame()


# ==============================================================================
#  不可分トランザクション対局保存API
# ==============================================================================

def save_game_record(game_data: dict, local=None) -> str:
    """対局ヘッダ、参加者4名、局データ、局座席データを不可分に一括保存する。"""
    game_id = game_data.get("game_id") or generate_uuid7()
    played_at = game_data.get("played_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_id = game_data.get("group_id")
    rule_name_snap = game_data.get("rule_name_snapshot") or "標準ルール"
    rule_cfg = game_data.get("rule_config_snapshot", {})
    rule_cfg_str = json.dumps(rule_cfg, ensure_ascii=False) if isinstance(rule_cfg, dict) else str(rule_cfg)
    game_mode = game_data.get("game_mode", "detail")
    participants = game_data.get("participants", [])
    rounds = game_data.get("rounds", [])

    if len(participants) != 4:
        raise ValueError(f"対局参加者は4名必須です (現在: {len(participants)}名)")

    use_local = IS_LOCAL if local is None else local
    ph = "?" if use_local else "%s"

    with _db(local=local) as conn:

        c = conn.cursor()

        # 1. games テーブルへの INSERT
        c.execute(f"""
            INSERT INTO games (
                game_id, played_at, group_id, rule_name_snapshot,
                rule_config_snapshot, game_mode, is_synced
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (game_id, played_at, group_id, rule_name_snap, rule_cfg_str, game_mode, 0 if IS_LOCAL else 1))

        # 2. game_participants テーブルへの INSERT (4行)
        for p in participants:
            c.execute(f"""
                INSERT INTO game_participants (
                    game_id, seat, member_id, player_name_snapshot,
                    final_score, rank, point, was_group_member
                ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """, (
                game_id, p["seat"], p["member_id"], p["player_name_snapshot"],
                int(p["final_score"]), int(p["rank"]), float(p["point"]), int(p.get("was_group_member", 1))
            ))

        # 3. rounds / round_seats テーブルへの INSERT (詳細対局時)
        if game_mode == "detail" and rounds:
            for r in rounds:
                round_id = r.get("round_id") or generate_uuid7()
                c.execute(f"""
                    INSERT INTO rounds (
                        round_id, game_id, round_index, kyoku_name,
                        honba, riichi_sticks, result_type
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """, (
                    round_id, game_id, int(r["round_index"]), r["kyoku_name"],
                    int(r.get("honba", 0)), int(r.get("riichi_sticks", 0)), r["result_type"]
                ))

                for s in r.get("seats", []):
                    c.execute(f"""
                        INSERT INTO round_seats (
                            round_id, seat, member_id, base_point, honba_point,
                            kyotaku_point, penalty_point, score_delta, chip_delta,
                            han, fu, is_winner, is_loser, is_riichi, is_furo, is_tenpai
                        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """, (
                        round_id, int(s["seat"]), s["member_id"],
                        int(s.get("base_point", 0)), int(s.get("honba_point", 0)),
                        int(s.get("kyotaku_point", 0)), int(s.get("penalty_point", 0)),
                        int(s.get("score_delta", 0)), int(s.get("chip_delta", 0)),
                        s.get("han"), s.get("fu"),
                        int(s.get("is_winner", 0)), int(s.get("is_loser", 0)),
                        int(s.get("is_riichi", 0)), int(s.get("is_furo", 0)),
                        int(s.get("is_tenpai", 0))
                    ))

    return game_id


def delete_game(game_id: str):
    """対局および関連する参加者・局・座席データを完全削除する。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        # 1. 局IDを取得
        c.execute(f"SELECT round_id FROM rounds WHERE game_id = {ph}", (game_id,))
        round_ids = [r[0] for r in c.fetchall()]
        
        # 2. round_seats 削除
        for rid in round_ids:
            c.execute(f"DELETE FROM round_seats WHERE round_id = {ph}", (rid,))
            
        # 3. rounds 削除
        c.execute(f"DELETE FROM rounds WHERE game_id = {ph}", (game_id,))
        
        # 4. game_participants 削除
        c.execute(f"DELETE FROM game_participants WHERE game_id = {ph}", (game_id,))
        
        # 5. games 削除
        c.execute(f"DELETE FROM games WHERE game_id = {ph}", (game_id,))


# ==============================================================================
#  対局取得・一覧API
# ==============================================================================

def get_games_data(year_filter=None, group_id=None):
    """対局一覧および4席の確定成績を結合した DataFrame を取得する。"""
    query = """
    SELECT 
        g.game_id,
        g.played_at AS date,
        g.group_id,
        g.rule_name_snapshot,
        g.rule_config_snapshot,
        g.game_mode,
        g.is_synced,
        MAX(CASE WHEN gp.seat = 1 THEN gp.player_name_snapshot END) AS p1_name,
        MAX(CASE WHEN gp.seat = 1 THEN gp.final_score END) AS p1_score,
        MAX(CASE WHEN gp.seat = 1 THEN gp.rank END) AS p1_rank,
        MAX(CASE WHEN gp.seat = 1 THEN gp.point END) AS p1_point,
        MAX(CASE WHEN gp.seat = 1 THEN gp.was_group_member END) AS p1_was_group_member,
        MAX(CASE WHEN gp.seat = 2 THEN gp.player_name_snapshot END) AS p2_name,
        MAX(CASE WHEN gp.seat = 2 THEN gp.final_score END) AS p2_score,
        MAX(CASE WHEN gp.seat = 2 THEN gp.rank END) AS p2_rank,
        MAX(CASE WHEN gp.seat = 2 THEN gp.point END) AS p2_point,
        MAX(CASE WHEN gp.seat = 2 THEN gp.was_group_member END) AS p2_was_group_member,
        MAX(CASE WHEN gp.seat = 3 THEN gp.player_name_snapshot END) AS p3_name,
        MAX(CASE WHEN gp.seat = 3 THEN gp.final_score END) AS p3_score,
        MAX(CASE WHEN gp.seat = 3 THEN gp.rank END) AS p3_rank,
        MAX(CASE WHEN gp.seat = 3 THEN gp.point END) AS p3_point,
        MAX(CASE WHEN gp.seat = 3 THEN gp.was_group_member END) AS p3_was_group_member,
        MAX(CASE WHEN gp.seat = 4 THEN gp.player_name_snapshot END) AS p4_name,
        MAX(CASE WHEN gp.seat = 4 THEN gp.final_score END) AS p4_score,
        MAX(CASE WHEN gp.seat = 4 THEN gp.rank END) AS p4_rank,
        MAX(CASE WHEN gp.seat = 4 THEN gp.point END) AS p4_point,
        MAX(CASE WHEN gp.seat = 4 THEN gp.was_group_member END) AS p4_was_group_member
    FROM games g
    LEFT JOIN game_participants gp ON g.game_id = gp.game_id
    GROUP BY g.game_id
    ORDER BY g.played_at DESC
    """
    with _db() as conn:
        df = _fetch_df(conn, query)

    if df.empty:
        return df

    df['date'] = pd.to_datetime(df['date'], format='mixed')
    df = df.sort_values('date')
    df['match_no'] = range(1, len(df) + 1)

    if group_id and group_id != "all":
        df = df[df['group_id'] == group_id]

    if year_filter and year_filter != "全期間":
        df = df[df['date'].dt.year == int(year_filter)]

    return df.sort_values('date', ascending=False)


def load_all_games():
    """管理画面等で使用する全対局一覧 DataFrame を取得する。"""
    return get_games_data()


def get_game_details(game_id: str) -> dict:
    """指定した対局の完全情報（ヘッダ、参加者4名、全局・全座席データ）を取得する。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        # 1. games
        c.execute(f"SELECT * FROM games WHERE game_id = {ph}", (game_id,))
        game_row = c.fetchone()
        if not game_row:
            return {}
        game_dict = dict(game_row)

        # 2. participants
        c.execute(f"SELECT * FROM game_participants WHERE game_id = {ph} ORDER BY seat", (game_id,))
        game_dict["participants"] = [dict(r) for r in c.fetchall()]

        # 3. rounds
        c.execute(f"SELECT * FROM rounds WHERE game_id = {ph} ORDER BY round_index", (game_id,))
        rounds = [dict(r) for r in c.fetchall()]

        for r in rounds:
            c.execute(f"SELECT * FROM round_seats WHERE round_id = {ph} ORDER BY seat", (r["round_id"],))
            r["seats"] = [dict(s) for s in c.fetchall()]

        game_dict["rounds"] = rounds
        return game_dict


def get_rounds_data(game_id=None):
    """局データおよび座席データを結合した DataFrame を取得する。"""
    ph = "?" if IS_LOCAL else "%s"
    query = """
    SELECT 
        r.round_id, r.game_id, r.round_index, r.kyoku_name,
        r.honba, r.riichi_sticks, r.result_type,
        rs.seat, rs.member_id, m.member_name,
        rs.base_point, rs.honba_point, rs.kyotaku_point, rs.penalty_point,
        rs.score_delta, rs.chip_delta, rs.han, rs.fu,
        rs.is_winner, rs.is_loser, rs.is_riichi, rs.is_furo, rs.is_tenpai
    FROM rounds r
    JOIN round_seats rs ON r.round_id = rs.round_id
    JOIN members m ON rs.member_id = m.member_id
    """
    params = None
    if game_id:
        query += f" WHERE r.game_id = {ph} ORDER BY r.round_index, rs.seat"
        params = (game_id,)
    else:
        query += " ORDER BY r.round_id, rs.seat"

    with _db() as conn:
        return _fetch_df(conn, query, params)


# ==============================================================================
#  メンバー管理 CRUD
# ==============================================================================

def get_all_members(include_archived=False):
    """全メンバー一覧を取得する。"""
    query = "SELECT * FROM members"
    if not include_archived:
        query += " WHERE is_archived = 0"
    query += " ORDER BY member_name"
    with _db() as conn:
        return _fetch_df(conn, query)


def add_member(member_name: str, is_guest=0) -> str:
    """新メンバーを登録し、生成された UUID v7 を返す。"""
    member_id = generate_uuid7()
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"""
            INSERT INTO members (member_id, member_name, is_guest, is_archived)
            VALUES ({ph}, {ph}, {ph}, 0)
        """, (member_id, member_name.strip(), int(is_guest)))
    return member_id


def archive_member(member_id: str):
    """メンバーをアーカイブ（論理削除）する。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE members SET is_archived = 1 WHERE member_id = {ph}", (member_id,))


# ==============================================================================
#  グループ管理 CRUD
# ==============================================================================

def get_all_groups(include_archived=False):
    """全グループ一覧を取得する。"""
    query = "SELECT * FROM groups"
    if not include_archived:
        query += " WHERE is_archived = 0"
    query += " ORDER BY display_id, group_name"
    with _db() as conn:
        return _fetch_df(conn, query)


def get_group_members(group_id: str) -> list:
    """指定グループに所属するメンバーIDの一覧を返す。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"SELECT member_id FROM group_memberships WHERE group_id = {ph}", (group_id,))
        return [r[0] for r in c.fetchall()]


def save_group(group_id: str, group_name: str, default_rule_id: str, member_ids: list, display_id=None) -> str:
    """グループ情報および所属メンバーを一括保存・更新する。"""
    ph = "?" if IS_LOCAL else "%s"
    gid = group_id or generate_uuid7()
    with _db() as conn:
        c = conn.cursor()
        if IS_LOCAL:
            c.execute(f"""
                INSERT INTO groups (group_id, display_id, group_name, default_rule_id, is_archived)
                VALUES ({ph}, {ph}, {ph}, {ph}, 0)
                ON CONFLICT(group_id) DO UPDATE SET
                    display_id = excluded.display_id,
                    group_name = excluded.group_name,
                    default_rule_id = excluded.default_rule_id,
                    is_archived = 0
            """, (gid, display_id, group_name.strip(), default_rule_id))
        else:
            c.execute(f"""
                INSERT INTO groups (group_id, display_id, group_name, default_rule_id, is_archived)
                VALUES ({ph}, {ph}, {ph}, {ph}, 0)
                ON CONFLICT(group_id) DO UPDATE SET
                    display_id = EXCLUDED.display_id,
                    group_name = EXCLUDED.group_name,
                    default_rule_id = EXCLUDED.default_rule_id,
                    is_archived = 0
            """, (gid, display_id, group_name.strip(), default_rule_id))

        # 所属メンバーの再設定
        c.execute(f"DELETE FROM group_memberships WHERE group_id = {ph}", (gid,))
        for mid in member_ids:
            c.execute(f"""
                INSERT INTO group_memberships (group_id, member_id)
                VALUES ({ph}, {ph})
            """, (gid, mid))

    return gid


def archive_group(group_id: str):
    """グループをアーカイブする。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE groups SET is_archived = 1 WHERE group_id = {ph}", (group_id,))


# ==============================================================================
#  ルールテンプレート CRUD
# ==============================================================================

def get_rule_templates(include_archived=False):
    """全ルールテンプレート一覧を取得する。"""
    query = "SELECT * FROM rule_templates"
    if not include_archived:
        query += " WHERE is_archived = 0"
    query += " ORDER BY kind DESC, name ASC"
    with _db() as conn:
        return _fetch_df(conn, query)


def save_custom_rule(rule_id: str, name: str, config: dict) -> str:
    """カスタムルールテンプレートを保存・更新する。"""
    rid = rule_id or f"rule_{generate_uuid7()[:8]}"
    cfg_str = json.dumps(config, ensure_ascii=False) if isinstance(config, dict) else str(config)
    ph = "?" if IS_LOCAL else "%s"

    with _db() as conn:
        c = conn.cursor()
        if IS_LOCAL:
            c.execute(f"""
                INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
                VALUES ({ph}, {ph}, 'custom', 1, {ph}, 0)
                ON CONFLICT(rule_id) DO UPDATE SET
                    name = excluded.name,
                    config_json = excluded.config_json,
                    is_archived = 0
            """, (rid, name.strip(), cfg_str))
        else:
            c.execute(f"""
                INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
                VALUES ({ph}, {ph}, 'custom', 1, {ph}, 0)
                ON CONFLICT(rule_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    config_json = EXCLUDED.config_json,
                    is_archived = 0
            """, (rid, name.strip(), cfg_str))

    return rid


def archive_rule(rule_id: str):
    """ルールテンプレートをアーカイブする。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE rule_templates SET is_archived = 1 WHERE rule_id = {ph}", (rule_id,))


# ==============================================================================
#  下書き（ドラフト）管理
# ==============================================================================

def save_draft(state_json: str, draft_id="current_game"):
    """対局の進行状態を下書きとして保存する。"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ph = "?" if IS_LOCAL else "%s"
    # dict の場合は JSON 文字列に変換
    if isinstance(state_json, dict):
        state_json = json.dumps(state_json, ensure_ascii=False)
    with _db() as conn:
        c = conn.cursor()
        if IS_LOCAL:
            c.execute("""
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute(f"""
                INSERT INTO drafts (id, state_json, updated_at)
                VALUES ({ph}, {ph}, {ph})
                ON CONFLICT(id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
            """, (draft_id, state_json, now_str))
        else:
            c.execute(f"""
                INSERT INTO drafts (id, state_json, updated_at)
                VALUES ({ph}, {ph}::jsonb, now())
                ON CONFLICT(id) DO UPDATE SET
                    state_json = EXCLUDED.state_json,
                    updated_at = now()
            """, (draft_id, state_json))


def get_draft(draft_id="current_game") -> str:
    """保存された下書きの state_json を取得する。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        if IS_LOCAL:
            c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drafts'")
            if not c.fetchone():
                return None
        c.execute(f"SELECT state_json FROM drafts WHERE id = {ph}", (draft_id,))
        row = c.fetchone()
        if row:
            val = row[0]
            return json.dumps(val, ensure_ascii=False) if isinstance(val, dict) else str(val)
        return None


def load_draft(draft_id="current_game"):
    """既存の home.py やテストから呼ばれる (state_dict, updated_at) 返却関数"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        if IS_LOCAL:
            c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drafts'")
            if not c.fetchone():
                return None, None
        c.execute(f"SELECT state_json, updated_at FROM drafts WHERE id = {ph}", (draft_id,))
        row = c.fetchone()
        if not row:
            return None, None
        val, updated_at = row[0], row[1]
        state_dict = json.loads(val) if isinstance(val, str) else val
        return state_dict, updated_at


def delete_draft(draft_id="current_game"):
    """下書きを削除する。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        if IS_LOCAL:
            c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drafts'")
            if not c.fetchone():
                return
        c.execute(f"DELETE FROM drafts WHERE id = {ph}", (draft_id,))


# ==============================================================================
#  スキーマ初期化 & 互換性ブリッジ
# ==============================================================================

def init_local_db():
    """新V2スキーマの全テーブルをローカルSQLiteに構築する（テスト・初期化用）。"""
    if not IS_LOCAL:
        return
    if not SQLITE_PATH:
        return
    parent = os.path.dirname(SQLITE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with _local_db() as conn:
        c = conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            member_id TEXT PRIMARY KEY,
            member_name TEXT NOT NULL,
            is_guest INTEGER NOT NULL DEFAULT 0,
            is_archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            display_id TEXT,
            group_name TEXT NOT NULL,
            default_rule_id TEXT,
            is_archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS group_memberships (
            group_id TEXT NOT NULL,
            member_id TEXT NOT NULL,
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (group_id, member_id)
        );
        CREATE TABLE IF NOT EXISTS rule_templates (
            rule_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            config_json TEXT NOT NULL,
            is_archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            played_at TEXT NOT NULL,
            group_id TEXT,
            rule_name_snapshot TEXT NOT NULL,
            rule_config_snapshot TEXT NOT NULL,
            game_mode TEXT NOT NULL DEFAULT 'detail',
            is_synced INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS game_participants (
            game_id TEXT NOT NULL,
            seat INTEGER NOT NULL,
            member_id TEXT NOT NULL,
            player_name_snapshot TEXT NOT NULL,
            final_score INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            point REAL NOT NULL,
            was_group_member INTEGER NOT NULL,
            PRIMARY KEY (game_id, seat)
        );
        CREATE TABLE IF NOT EXISTS rounds (
            round_id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            round_index INTEGER NOT NULL,
            kyoku_name TEXT NOT NULL,
            honba INTEGER NOT NULL DEFAULT 0,
            riichi_sticks INTEGER NOT NULL DEFAULT 0,
            result_type TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS round_seats (
            round_id TEXT NOT NULL,
            seat INTEGER NOT NULL,
            member_id TEXT NOT NULL,
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
        CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)


def migrate_local_identity_schema(conn=None):
    """旧マイグレーションの no-op 互換関数（新スキーマでは不要）。"""
    pass


def save_game(date_str, scores, players, local=False, rule_id="m_league", group_id="all",
              rule_config=None, player_member_ids=None, player_was_group_member=None):
    """旧呼び出し元向けのブリッジ関数。新 save_game_record を呼び出す。"""
    from calc import calc_point
    sorted_p = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    participants = []
    for rank, (name, score) in enumerate(sorted_p, start=1):
        seat = players.index(name) + 1 if name in players else rank
        mid = (player_member_ids or {}).get(name) or name
        was_mem = (player_was_group_member or {}).get(name, 1)
        pt = calc_point(score, rank, rule_config) if rule_config else 0.0
        participants.append({
            "seat": seat,
            "member_id": mid,
            "player_name_snapshot": name,
            "final_score": score,
            "rank": rank,
            "point": pt,
            "was_group_member": was_mem
        })

    rule_name = (rule_config or {}).get("rule_name", rule_id)
    payload = {
        "played_at": date_str,
        "group_id": group_id,
        "rule_name_snapshot": rule_name,
        "rule_config_snapshot": rule_config or {},
        "game_mode": "detail",
        "participants": participants,
        "rounds": []
    }
    return save_game_record(payload, local=local)



def save_round(game_id, kyoku_name, winner, loser, score, furo=None, riichi=None,
               win_type="", tenpai=None, multi_wins_json=None, local=False):
    """旧 save_round 呼び出し用の互換関数。新 rounds / round_seats テーブルへ保存する。"""
    round_id = generate_uuid7()
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM rounds WHERE game_id = {ph}", (str(game_id),))
        round_index = c.fetchone()[0]

        c.execute(f"""
            INSERT INTO rounds (
                round_id, game_id, round_index, kyoku_name,
                honba, riichi_sticks, result_type
            ) VALUES ({ph}, {ph}, {ph}, {ph}, 0, 0, {ph})
        """, (round_id, str(game_id), round_index, kyoku_name, win_type or "ron"))

        # 参加者のメンバーIDを取得
        c.execute(f"SELECT seat, member_id, player_name_snapshot FROM game_participants WHERE game_id = {ph} ORDER BY seat", (str(game_id),))
        parts = c.fetchall()
        for p in parts:
            seat, mid, pname = p[0], p[1], p[2]
            is_win = 1 if pname == winner else 0
            is_lose = 1 if pname == loser else 0
            is_r = 1 if riichi and (pname in riichi if isinstance(riichi, list) else False) else 0
            is_f = 1 if furo and (pname in furo if isinstance(furo, list) else False) else 0
            is_t = 1 if tenpai and (pname in tenpai if isinstance(tenpai, list) else False) else 0
            delta = score if is_win else (-score if is_lose else 0)

            c.execute(f"""
                INSERT INTO round_seats (
                    round_id, seat, member_id, base_point, score_delta,
                    is_winner, is_loser, is_riichi, is_furo, is_tenpai
                ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """, (round_id, seat, mid, delta, delta, is_win, is_lose, is_r, is_f, is_t))



# ==============================================================================
#  同期・ステータス管理API
# ==============================================================================

def get_pending_count():
    if not IS_LOCAL:
        return 0
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM games WHERE is_synced = 0")
        return c.fetchone()[0]


def get_local_unsynced_games():
    if not IS_LOCAL:
        return pd.DataFrame()
    with _local_db() as conn:
        return _fetch_df(conn, "SELECT * FROM games WHERE is_synced = 0 ORDER BY played_at DESC")


def mark_as_synced(game_id=None):
    if not IS_LOCAL:
        return
    ph = "?"
    with _local_db() as conn:
        c = conn.cursor()
        if game_id:
            c.execute(f"UPDATE games SET is_synced = 1 WHERE game_id = {ph}", (game_id,))
        else:
            c.execute("UPDATE games SET is_synced = 1")
