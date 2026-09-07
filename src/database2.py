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
    """ミリ秒タイムスタンプベースの UUID v7 (36文字文字列: 8-4-4-4-12) を生成する。"""
    ts = int(time.time() * 1000)
    ts_hex = f"{ts:012x}"
    rand_hex = os.urandom(10).hex()
    return f"{ts_hex[:8]}-{ts_hex[8:12]}-7{rand_hex[:3]}-8{rand_hex[3:6]}-{rand_hex[6:18]}"



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

def save_game_record(game_data: dict, participants: list = None, rounds: list = None, local=None) -> str:
    """対局ヘッダ、参加者4名、局データ、局座席データを不可分に一括保存する。"""
    if participants is not None:
        game_data = dict(game_data)
        game_data["participants"] = participants
        if rounds is not None:
            game_data["rounds"] = rounds

    game_id = game_data.get("game_id") or generate_uuid7()
    played_at = game_data.get("played_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_id = game_data.get("group_id")
    rule_name_snap = game_data.get("rule_name_snapshot") or "標準ルール"
    rule_cfg = game_data.get("rule_config_snapshot", {})
    rule_cfg_str = json.dumps(rule_cfg, ensure_ascii=False) if isinstance(rule_cfg, dict) else str(rule_cfg)
    game_mode = game_data.get("game_mode", "detail")
    parts = game_data.get("participants", [])
    rounds_list = game_data.get("rounds", [])

    if len(parts) != 4:
        raise ValueError(f"対局参加者は4名必須です (現在: {len(parts)}名)")


    use_local = IS_LOCAL if local is None else local
    ph = "?" if use_local else "%s"

    with _db(local=local) as conn:

        c = conn.cursor()

        sync_target = int(game_data.get("sync_target", 1))

        # 1. games テーブルへの INSERT
        c.execute(f"""
            INSERT INTO games (
                game_id, played_at, group_id, rule_name_snapshot,
                rule_config_snapshot, game_mode, sync_target, is_synced
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (game_id, played_at, group_id, rule_name_snap, rule_cfg_str, game_mode, sync_target, 0 if IS_LOCAL else 1))


        # 2. game_participants テーブルへの INSERT (4行)
        for idx, p in enumerate(parts):
            seat_num = int(p.get("seat", idx + 1))
            mid = str(p.get("member_id", ""))
            pname = p.get("player_name_snapshot") or p.get("name") or mid or f"P{seat_num}"
            fscore = int(p.get("final_score", p.get("score", 25000)))
            rnk = int(p.get("rank", idx + 1))
            pt_val = float(p.get("point", p.get("pt", 0.0)))
            was_mem = int(p.get("was_group_member", 1))

            c.execute(f"""
                INSERT INTO game_participants (
                    game_id, seat, member_id, player_name_snapshot,
                    final_score, rank, point, was_group_member
                ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """, (
                game_id, seat_num, mid, pname,
                fscore, rnk, pt_val, was_mem
            ))


        # 3. rounds / round_seats テーブルへの INSERT (詳細対局時)
        if game_mode == "detail" and rounds_list:
            for r_idx, r in enumerate(rounds_list):

                round_id = r.get("round_id") or generate_uuid7()
                r_num = int(r.get("round_index", r.get("round_number", r_idx + 1)))
                k_name = r.get("kyoku_name") or f"第{r_idx + 1}局"
                res_type = r.get("result_type", "ron")

                c.execute(f"""
                    INSERT INTO rounds (
                        round_id, game_id, round_index, kyoku_name,
                        honba, riichi_sticks, result_type
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """, (
                    round_id, game_id, r_num, k_name,
                    int(r.get("honba", 0)), int(r.get("riichi_sticks", 0)), res_type
                ))

                for s_idx, s in enumerate(r.get("seats", [])):
                    seat_val = int(s.get("seat", s_idx + 1))
                    c.execute(f"""
                        INSERT INTO round_seats (
                            round_id, seat, member_id, base_point, honba_point,
                            kyotaku_point, penalty_point, score_delta, chip_delta,
                            han, fu, is_winner, is_loser, is_riichi, is_furo, is_tenpai
                        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """, (
                        round_id, seat_val, s["member_id"],
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


def load_all_rounds():
    """全局レコードを取得する（CSVエクスポート用）。"""
    with _db() as conn:
        return _fetch_df(conn, "SELECT * FROM rounds ORDER BY round_index")


def load_rounds_by_game(game_id: str):
    """指定対局の局データを取得する。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        return _fetch_df(conn, f"SELECT * FROM rounds WHERE game_id = {ph} ORDER BY round_index", (str(game_id),))


def update_round(round_id: str, fields: dict):
    """指定局レコードの特定フィールドを更新する。"""
    if not fields:
        return
    ph = "?" if IS_LOCAL else "%s"
    set_clause = ", ".join(f"{k} = {ph}" for k in fields)
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE rounds SET {set_clause} WHERE round_id = {ph}", list(fields.values()) + [str(round_id)])


def update_game_scores(game_id: str, scores_dict: dict):
    """対局の最終持ち点および順位・ptを更新する。"""
    from calc import calc_point
    sorted_p = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
    name_to_rank = {name: rank for rank, (name, _) in enumerate(sorted_p, 1)}
    
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"SELECT rule_config_snapshot FROM games WHERE game_id = {ph}", (str(game_id),))
        row = c.fetchone()
        rule_cfg = {}
        if row and row[0]:
            rule_cfg = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            
        for name, score in scores_dict.items():
            rank = name_to_rank[name]
            pt = calc_point(score, rank, rule_cfg) if rule_cfg else 0.0
            c.execute(f"""
                UPDATE game_participants 
                SET final_score = {ph}, rank = {ph}, point = {ph}
                WHERE game_id = {ph} AND player_name_snapshot = {ph}
            """, (score, rank, pt, str(game_id), name))


def import_games_from_df(df):
    """CSVから対局データを一括取り込みする。"""
    count = 0
    for _, row in df.iterrows():
        players = [
            {"seat": 1, "member_id": str(row['p1_name']), "player_name_snapshot": str(row['p1_name']), "final_score": int(row['p1_score']), "rank": 1, "point": 0.0, "was_group_member": 1},
            {"seat": 2, "member_id": str(row['p2_name']), "player_name_snapshot": str(row['p2_name']), "final_score": int(row['p2_score']), "rank": 2, "point": 0.0, "was_group_member": 1},
            {"seat": 3, "member_id": str(row['p3_name']), "player_name_snapshot": str(row['p3_name']), "final_score": int(row['p3_score']), "rank": 3, "point": 0.0, "was_group_member": 1},
            {"seat": 4, "member_id": str(row['p4_name']), "player_name_snapshot": str(row['p4_name']), "final_score": int(row['p4_score']), "rank": 4, "point": 0.0, "was_group_member": 1},
        ]
        sorted_p = sorted(players, key=lambda x: x["final_score"], reverse=True)
        for rank, p in enumerate(sorted_p, 1):
            p["rank"] = rank
        game_payload = {
            "game_id": str(row.get('game_id')) if pd.notna(row.get('game_id')) else generate_uuid7(),
            "played_at": str(row.get('date', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))),
            "rule_name_snapshot": "標準ルール",
            "rule_config_snapshot": {},
            "game_mode": "detail",
            "participants": players,
            "rounds": []
        }
        save_game_record(game_payload)
        count += 1
    return count


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


def get_groups() -> list:
    """登録済みグループの一覧を取得する (メンバーIDリスト付き、G01/G02等の表示用ID対応)。"""
    try:
        ph = "?" if IS_LOCAL else "%s"
        with _db() as conn:
            c = conn.cursor()
            c.execute("SELECT group_id, group_name, default_rule_id, display_id FROM groups WHERE is_archived = 0 ORDER BY display_id ASC, group_name ASC")
            group_rows = c.fetchall()
            groups = []
            for idx, r in enumerate(group_rows):
                g_id, g_name, r_id, d_id = r[0], r[1], r[2], r[3]
                c.execute(f"SELECT member_id FROM group_memberships WHERE group_id = {ph}", (g_id,))
                members = [m[0] for m in c.fetchall()]
                groups.append({
                    "display_id": d_id if d_id else f"G{idx + 1:02d}",
                    "group_id": g_id,
                    "group_name": g_name,
                    "default_rule_id": r_id,
                    "members": members
                })
            return groups
    except Exception:
        return []


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


def add_group(group_name: str, default_rule_id: str = "m_league", member_ids: list = None) -> str:
    """グループを新規作成するショートハンド関数。"""
    return save_group(
        group_id=None,
        group_name=group_name,
        default_rule_id=default_rule_id,
        member_ids=member_ids or []
    )


def archive_group(group_id: str):
    """グループをアーカイブする。"""
    ph = "?" if IS_LOCAL else "%s"
    with _db() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE groups SET is_archived = 1 WHERE group_id = {ph}", (group_id,))


def delete_group(group_id: str):
    """グループを削除（アーカイブ）する下位互換関数。"""
    archive_group(group_id)


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

def check_connectivity() -> bool:
    """リモートDB（Supabase）への通信可否を確認し、接続可能なら True、不可なら False を返す。"""
    if psycopg2 is None or not REMOTE_DB_KWARGS:
        return False
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False


def init_db():
    """オンライン初期化の互換関数（Supabase側はマイグレーション済みのため no-op）。"""
    pass


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
            sync_target INTEGER NOT NULL DEFAULT 1,
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
        # 既存 games テーブルへの sync_target カラム追加確認
        c.execute("PRAGMA table_info(games)")
        cols = [r[1] for r in c.fetchall()]
        if "sync_target" not in cols:
            c.execute("ALTER TABLE games ADD COLUMN sync_target INTEGER NOT NULL DEFAULT 1")



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
#  分散ハイブリッド同期API（選択的Push & 全件Pull & マスタ双方向同期）
# ==============================================================================

def get_sync_status_summary():
    """同期状況のサマリー（未送信対象数、ローカル限定数、同期済み数）を取得する。"""
    if not IS_LOCAL:
        return {"pending_push": 0, "local_only": 0, "synced": 0}
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM games WHERE sync_target = 1 AND is_synced = 0")
        pending_push = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM games WHERE sync_target = 0")
        local_only = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM games WHERE is_synced = 1")
        synced = c.fetchone()[0]
        return {
            "pending_push": pending_push,
            "local_only": local_only,
            "synced": synced
        }


def set_game_sync_target(game_id: str, sync_target: int):
    """対局のオンライン同期対象フラグ（1: 同期する, 0: ローカル限定）を更新する。"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE games SET sync_target = ? WHERE game_id = ?", (int(sync_target), game_id))


def get_pending_count():
    """未同期の対象対局数を取得する。"""
    if not IS_LOCAL:
        return 0
    with _local_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM games WHERE sync_target = 1 AND is_synced = 0")
        return c.fetchone()[0]


def get_local_unsynced_games():
    """未同期かつ同期対象のローカル対局一覧（4座席確定成績を含む）を取得する。"""
    if not IS_LOCAL:
        return pd.DataFrame()
    query = """
    SELECT 
        g.game_id,
        g.played_at AS date,
        g.group_id,
        g.rule_name_snapshot,
        g.rule_config_snapshot,
        g.game_mode,
        g.sync_target,
        g.is_synced,
        MAX(CASE WHEN gp.seat = 1 THEN gp.player_name_snapshot END) AS p1_name,
        MAX(CASE WHEN gp.seat = 1 THEN gp.final_score END) AS p1_score,
        MAX(CASE WHEN gp.seat = 1 THEN gp.rank END) AS p1_rank,
        MAX(CASE WHEN gp.seat = 1 THEN gp.point END) AS p1_point,
        MAX(CASE WHEN gp.seat = 2 THEN gp.player_name_snapshot END) AS p2_name,
        MAX(CASE WHEN gp.seat = 2 THEN gp.final_score END) AS p2_score,
        MAX(CASE WHEN gp.seat = 2 THEN gp.rank END) AS p2_rank,
        MAX(CASE WHEN gp.seat = 2 THEN gp.point END) AS p2_point,
        MAX(CASE WHEN gp.seat = 3 THEN gp.player_name_snapshot END) AS p3_name,
        MAX(CASE WHEN gp.seat = 3 THEN gp.final_score END) AS p3_score,
        MAX(CASE WHEN gp.seat = 3 THEN gp.rank END) AS p3_rank,
        MAX(CASE WHEN gp.seat = 3 THEN gp.point END) AS p3_point,
        MAX(CASE WHEN gp.seat = 4 THEN gp.player_name_snapshot END) AS p4_name,
        MAX(CASE WHEN gp.seat = 4 THEN gp.final_score END) AS p4_score,
        MAX(CASE WHEN gp.seat = 4 THEN gp.rank END) AS p4_rank,
        MAX(CASE WHEN gp.seat = 4 THEN gp.point END) AS p4_point
    FROM games g
    LEFT JOIN game_participants gp ON g.game_id = gp.game_id
    WHERE g.sync_target = 1 AND g.is_synced = 0
    GROUP BY g.game_id
    ORDER BY g.played_at DESC
    """
    with _local_db() as conn:
        return _fetch_df(conn, query)


def mark_as_synced(game_id=None):
    """ローカル対局を同期済みに更新する。"""
    if not IS_LOCAL:
        return
    with _local_db() as conn:
        c = conn.cursor()
        if game_id:
            c.execute("UPDATE games SET is_synced = 1 WHERE game_id = ?", (game_id,))
        else:
            c.execute("UPDATE games SET is_synced = 1 WHERE sync_target = 1")


def sync_masters():
    """マスタデータ（members, groups, memberships, rule_templates）の双方向マージを行う。"""
    if not IS_LOCAL:
        return {"members": 0, "groups": 0, "rules": 0}

    with _local_db() as l_conn, _remote_db() as r_conn:
        lc = l_conn.cursor()
        rc = r_conn.cursor()

        # 1. members マージ
        lc.execute("SELECT member_id, member_name, is_guest, is_archived, created_at FROM members")
        l_mems = lc.fetchall()
        for m in l_mems:
            rc.execute("""
                INSERT INTO members (member_id, member_name, is_guest, is_archived, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (member_id) DO UPDATE SET
                    member_name = EXCLUDED.member_name,
                    is_archived = EXCLUDED.is_archived
            """, m)

        rc.execute("SELECT member_id, member_name, is_guest, is_archived, created_at FROM members")
        for m in rc.fetchall():
            lc.execute("""
                INSERT INTO members (member_id, member_name, is_guest, is_archived, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (member_id) DO UPDATE SET
                    member_name = excluded.member_name,
                    is_archived = excluded.is_archived
            """, m)

        # 2. groups マージ
        lc.execute("SELECT group_id, display_id, group_name, default_rule_id, is_archived FROM groups")
        for g in lc.fetchall():
            rc.execute("""
                INSERT INTO groups (group_id, display_id, group_name, default_rule_id, is_archived)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (group_id) DO UPDATE SET
                    group_name = EXCLUDED.group_name,
                    default_rule_id = EXCLUDED.default_rule_id,
                    is_archived = EXCLUDED.is_archived
            """, g)

        rc.execute("SELECT group_id, display_id, group_name, default_rule_id, is_archived FROM groups")
        for g in rc.fetchall():
            lc.execute("""
                INSERT INTO groups (group_id, display_id, group_name, default_rule_id, is_archived)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (group_id) DO UPDATE SET
                    group_name = excluded.group_name,
                    default_rule_id = excluded.default_rule_id,
                    is_archived = excluded.is_archived
            """, g)

        # 3. group_memberships マージ
        lc.execute("SELECT group_id, member_id, joined_at FROM group_memberships")
        for gm in lc.fetchall():
            rc.execute("""
                INSERT INTO group_memberships (group_id, member_id, joined_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (group_id, member_id) DO NOTHING
            """, gm)

        rc.execute("SELECT group_id, member_id, joined_at FROM group_memberships")
        for gm in rc.fetchall():
            lc.execute("""
                INSERT INTO group_memberships (group_id, member_id, joined_at)
                VALUES (?, ?, ?)
                ON CONFLICT (group_id, member_id) DO NOTHING
            """, gm)

        # 4. rule_templates マージ
        lc.execute("SELECT rule_id, name, kind, version, config_json, is_archived FROM rule_templates")
        for r in lc.fetchall():
            cfg_val = r[4] if isinstance(r[4], str) else json.dumps(r[4], ensure_ascii=False)
            rc.execute("""
                INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (rule_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    config_json = EXCLUDED.config_json,
                    is_archived = EXCLUDED.is_archived
            """, (r[0], r[1], r[2], r[3], cfg_val, r[5]))

        rc.execute("SELECT rule_id, name, kind, version, config_json, is_archived FROM rule_templates")
        for r in rc.fetchall():
            cfg_val = json.dumps(r[4], ensure_ascii=False) if isinstance(r[4], dict) else str(r[4])
            lc.execute("""
                INSERT INTO rule_templates (rule_id, name, kind, version, config_json, is_archived)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (rule_id) DO UPDATE SET
                    name = excluded.name,
                    config_json = excluded.config_json,
                    is_archived = excluded.is_archived
            """, (r[0], r[1], r[2], r[3], cfg_val, r[5]))

        r_conn.commit()


def pull_games_from_remote():
    """リモートにあってローカルに存在しない対局を全件取得してローカルへ保存する（バックアップ復元）。"""
    if not IS_LOCAL:
        return 0

    pulled_count = 0
    with _local_db() as l_conn, _remote_db() as r_conn:
        lc = l_conn.cursor()
        rc = r_conn.cursor()

        # ローカルに存在する全対局ID
        lc.execute("SELECT game_id FROM games")
        local_ids = set(r[0] for r in lc.fetchall())

        # リモートの対局一覧
        rc.execute("SELECT game_id, played_at, group_id, rule_name_snapshot, rule_config_snapshot, game_mode FROM games")
        remote_games = rc.fetchall()

        for g in remote_games:
            gid = str(g[0])
            if gid in local_ids:
                continue

            played_at = str(g[1])
            grp_id = g[2]
            r_snap = g[3]
            r_cfg = json.dumps(g[4], ensure_ascii=False) if isinstance(g[4], dict) else str(g[4])
            mode = g[5]

            # participants 取得
            rc.execute("""
                SELECT seat, member_id, player_name_snapshot, final_score, rank, point, was_group_member
                FROM game_participants WHERE game_id = %s ORDER BY seat
            """, (gid,))
            parts = rc.fetchall()

            # rounds 取得
            rc.execute("""
                SELECT round_id, round_index, kyoku_name, honba, riichi_sticks, result_type
                FROM rounds WHERE game_id = %s ORDER BY round_index
            """, (gid,))
            rounds = rc.fetchall()

            # ローカルへ不可分保存 (sync_target=1, is_synced=1)
            lc.execute("""
                INSERT INTO games (
                    game_id, played_at, group_id, rule_name_snapshot,
                    rule_config_snapshot, game_mode, sync_target, is_synced
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 1)
            """, (gid, played_at, grp_id, r_snap, r_cfg, mode))

            for p in parts:
                lc.execute("""
                    INSERT INTO game_participants (
                        game_id, seat, member_id, player_name_snapshot,
                        final_score, rank, point, was_group_member
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (gid, p[0], str(p[1]), p[2], p[3], p[4], p[5], p[6]))

            for r in rounds:
                rid = str(r[0])
                lc.execute("""
                    INSERT INTO rounds (
                        round_id, game_id, round_index, kyoku_name,
                        honba, riichi_sticks, result_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (rid, gid, r[1], r[2], r[3], r[4], r[5]))

                # round_seats 取得・保存
                rc.execute("""
                    SELECT seat, member_id, base_point, honba_point, kyotaku_point,
                           penalty_point, score_delta, chip_delta, han, fu,
                           is_winner, is_loser, is_riichi, is_furo, is_tenpai
                    FROM round_seats WHERE round_id = %s ORDER BY seat
                """, (rid,))
                for s in rc.fetchall():
                    lc.execute("""
                        INSERT INTO round_seats (
                            round_id, seat, member_id, base_point, honba_point,
                            kyotaku_point, penalty_point, score_delta, chip_delta,
                            han, fu, is_winner, is_loser, is_riichi, is_furo, is_tenpai
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (rid, s[0], str(s[1]), s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11], s[12], s[13], s[14]))

            pulled_count += 1

    return pulled_count


def push_games_to_remote(game_ids=None):
    """ローカルの sync_target = 1 かつ未同期の対局（または指定ID）のみをリモートへ送信する（選択的Push）。"""
    if not IS_LOCAL:
        return 0

    pushed_count = 0
    with _local_db() as l_conn, _remote_db() as r_conn:
        lc = l_conn.cursor()
        rc = r_conn.cursor()

        if game_ids:
            ph_list = ",".join("?" for _ in game_ids)
            lc.execute(f"SELECT game_id FROM games WHERE game_id IN ({ph_list}) AND sync_target = 1 AND is_synced = 0", tuple(game_ids))
        else:
            lc.execute("SELECT game_id FROM games WHERE sync_target = 1 AND is_synced = 0")

        target_gids = [r[0] for r in lc.fetchall()]
        if not target_gids:
            return 0

        for gid in target_gids:
            # 1. games レコード取得
            lc.execute("SELECT game_id, played_at, group_id, rule_name_snapshot, rule_config_snapshot, game_mode FROM games WHERE game_id = ?", (gid,))
            g = lc.fetchone()
            cfg_val = g[4] if isinstance(g[4], str) else json.dumps(g[4], ensure_ascii=False)

            rc.execute("""
                INSERT INTO games (
                    game_id, played_at, group_id, rule_name_snapshot,
                    rule_config_snapshot, game_mode, is_synced
                ) VALUES (%s, %s, %s, %s, %s, %s, 1)
                ON CONFLICT (game_id) DO NOTHING
            """, (g[0], g[1], g[2], g[3], cfg_val, g[5]))

            # 2. participants 取得・送信
            lc.execute("""
                SELECT seat, member_id, player_name_snapshot, final_score, rank, point, was_group_member
                FROM game_participants WHERE game_id = ? ORDER BY seat
            """, (gid,))
            for p in lc.fetchall():
                rc.execute("""
                    INSERT INTO game_participants (
                        game_id, seat, member_id, player_name_snapshot,
                        final_score, rank, point, was_group_member
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (game_id, seat) DO NOTHING
                """, (gid, p[0], p[1], p[2], p[3], p[4], p[5], p[6]))

            # 3. rounds 取得・送信
            lc.execute("""
                SELECT round_id, round_index, kyoku_name, honba, riichi_sticks, result_type
                FROM rounds WHERE game_id = ? ORDER BY round_index
            """, (gid,))
            for r in lc.fetchall():
                rid = r[0]
                rc.execute("""
                    INSERT INTO rounds (
                        round_id, game_id, round_index, kyoku_name,
                        honba, riichi_sticks, result_type
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (round_id) DO NOTHING
                """, (rid, gid, r[1], r[2], r[3], r[4], r[5]))

                # 4. round_seats 取得・送信
                lc.execute("""
                    SELECT seat, member_id, base_point, honba_point, kyotaku_point,
                           penalty_point, score_delta, chip_delta, han, fu,
                           is_winner, is_loser, is_riichi, is_furo, is_tenpai
                    FROM round_seats WHERE round_id = ? ORDER BY seat
                """, (rid,))
                for s in lc.fetchall():
                    rc.execute("""
                        INSERT INTO round_seats (
                            round_id, seat, member_id, base_point, honba_point,
                            kyotaku_point, penalty_point, score_delta, chip_delta,
                            han, fu, is_winner, is_loser, is_riichi, is_furo, is_tenpai
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (round_id, seat) DO NOTHING
                    """, (rid, s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11], s[12], s[13], s[14]))

            # ローカル側を同期済みに更新
            lc.execute("UPDATE games SET is_synced = 1 WHERE game_id = ?", (gid,))
            pushed_count += 1

        r_conn.commit()

    return pushed_count


def sync_all():
    """マスタ同期 → 全件Pull → 選択的Push を順次実行する統合同期関数。"""
    sync_masters()
    pulled = pull_games_from_remote()
    pushed = push_games_to_remote()
    return {"pulled": pulled, "pushed": pushed}


def sync_to_supabase():
    """下位互換用同期関数。"""
    res = sync_all()
    return res.get("pushed", 0)



# ==============================================================================
#  正規化SQL成績集計API
# ==============================================================================

def get_game_stats_summary(group_id=None, rule_id=None, year=None, include_guests=True):
    """game_participants と games から試合成績集計 DataFrame を取得する。"""
    ph = "?" if IS_LOCAL else "%s"
    where_clauses = []
    params = []

    if group_id and group_id != "all":
        where_clauses.append(f"g.group_id = {ph}")
        params.append(group_id)

    if not include_guests:
        where_clauses.append("m.is_guest = 0")

    if rule_id and rule_id != "all":
        where_clauses.append(f"(g.rule_id = {ph} OR g.rule_name_snapshot = {ph})")
        params.extend([rule_id, rule_id])

    if year and year != "全期間":
        where_clauses.append(f"strftime('%Y', g.played_at) = {ph}" if IS_LOCAL else f"EXTRACT(YEAR FROM g.played_at) = {ph}")
        params.append(str(year))

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    col_1 = "`1着率`" if IS_LOCAL else '"1着率"'
    col_2 = "`2着率`" if IS_LOCAL else '"2着率"'
    col_3 = "`3着率`" if IS_LOCAL else '"3着率"'
    col_4 = "`4着率`" if IS_LOCAL else '"4着率"'

    query = f"""
    SELECT 
        m.member_name AS 名前,
        COUNT(gp.game_id) AS 試合数,
        ROUND(SUM(gp.point), 1) AS 総合pt,
        ROUND(SUM(
            (gp.final_score - 25000) / 1000.0 + 
            CASE gp.rank 
                WHEN 1 THEN 30.0 
                WHEN 2 THEN 10.0 
                WHEN 3 THEN -10.0 
                WHEN 4 THEN -30.0 
                ELSE 0.0 
            END
        ), 1) AS オカなし総合pt,
        ROUND(AVG(gp.rank), 2) AS 平均順位,
        ROUND(SUM(CASE WHEN gp.rank <= 2 THEN 1.0 ELSE 0.0 END) / COUNT(gp.game_id) * 100, 1) AS 連対率,
        ROUND(SUM(CASE WHEN gp.rank <= 3 THEN 1.0 ELSE 0.0 END) / COUNT(gp.game_id) * 100, 1) AS ラス回避率,
        ROUND(SUM(CASE WHEN gp.rank = 1 THEN 1.0 ELSE 0.0 END) / COUNT(gp.game_id) * 100, 1) AS {col_1},
        ROUND(SUM(CASE WHEN gp.rank = 2 THEN 1.0 ELSE 0.0 END) / COUNT(gp.game_id) * 100, 1) AS {col_2},
        ROUND(SUM(CASE WHEN gp.rank = 3 THEN 1.0 ELSE 0.0 END) / COUNT(gp.game_id) * 100, 1) AS {col_3},
        ROUND(SUM(CASE WHEN gp.rank = 4 THEN 1.0 ELSE 0.0 END) / COUNT(gp.game_id) * 100, 1) AS {col_4}
    FROM game_participants gp
    JOIN games g ON gp.game_id = g.game_id
    JOIN members m ON gp.member_id = m.member_id
    {where_str}
    GROUP BY gp.member_id, m.member_name
    ORDER BY 総合pt DESC
    """
    with _db() as conn:
        return _fetch_df(conn, query, tuple(params))


def get_results_data(group_id=None, rule_id=None, year=None, include_guests=True):
    """グラフ・レコード・相性・履歴用の全プレイヤーリザルト DataFrame を取得する。"""
    ph = "?" if IS_LOCAL else "%s"
    where_clauses = []
    params = []

    if group_id and group_id != "all":
        where_clauses.append(f"g.group_id = {ph}")
        params.append(group_id)

    if not include_guests:
        where_clauses.append("m.is_guest = 0")

    if rule_id and rule_id != "all":
        where_clauses.append(f"(g.rule_id = {ph} OR g.rule_name_snapshot = {ph})")
        params.extend([rule_id, rule_id])

    if year and year != "全期間":
        where_clauses.append(f"strftime('%Y', g.played_at) = {ph}" if IS_LOCAL else f"EXTRACT(YEAR FROM g.played_at) = {ph}")
        params.append(str(year))

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    query = f"""
    SELECT 
        gp.game_id,
        g.played_at AS date,
        m.member_name AS name,
        gp.final_score AS score,
        gp.rank,
        gp.point AS pt
    FROM game_participants gp
    JOIN games g ON gp.game_id = g.game_id
    JOIN members m ON gp.member_id = m.member_id
    {where_str}
    ORDER BY g.played_at ASC, gp.game_id ASC, gp.rank ASC
    """
    with _db() as conn:
        df = _fetch_df(conn, query, tuple(params))
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df


def get_round_stats_summary(group_id=None, rule_id=None, year=None, include_guests=True):
    """round_seats と rounds, games から局詳細集計 DataFrame を取得する。"""
    ph = "?" if IS_LOCAL else "%s"
    where_clauses = []
    params = []

    if group_id and group_id != "all":
        where_clauses.append(f"g.group_id = {ph}")
        params.append(group_id)

    if not include_guests:
        where_clauses.append("m.is_guest = 0")

    if rule_id and rule_id != "all":
        where_clauses.append(f"(g.rule_id = {ph} OR g.rule_name_snapshot = {ph})")
        params.extend([rule_id, rule_id])

    if year and year != "全期間":
        where_clauses.append(f"strftime('%Y', g.played_at) = {ph}" if IS_LOCAL else f"EXTRACT(YEAR FROM g.played_at) = {ph}")
        params.append(str(year))

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # 放銃時の相手立直・副露判定のため、各 round_id における立直者・副露者の存在を集計してサブクエリ結合
    query = f"""
    WITH round_context AS (
        SELECT 
            round_id,
            MAX(is_riichi) AS has_riichi_player,
            MAX(is_furo) AS has_furo_player
        FROM round_seats
        GROUP BY round_id
    )
    SELECT 
        m.member_name AS 名前,
        COUNT(rs.round_id) AS 局数,
        SUM(rs.is_winner) AS 和了,
        SUM(CASE WHEN rs.is_winner = 1 AND r.result_type = 'tsumo' THEN 1 ELSE 0 END) AS ツモ,
        SUM(rs.is_loser) AS 放銃,
        SUM(rs.is_riichi) AS リーチ,
        SUM(rs.is_furo) AS 副露,
        SUM(CASE WHEN r.result_type = 'ryukyoku' THEN 1 ELSE 0 END) AS 流局,
        SUM(rs.is_tenpai) AS テンパイ,
        SUM(CASE WHEN rs.is_winner = 1 AND rs.is_riichi = 1 THEN 1 ELSE 0 END) AS リーチ後和了,
        SUM(CASE WHEN rs.is_loser = 1 AND rs.is_riichi = 1 THEN 1 ELSE 0 END) AS リーチ後放銃,
        SUM(CASE WHEN rs.is_winner = 1 AND rs.is_furo = 1 THEN 1 ELSE 0 END) AS 副露和了,
        SUM(CASE WHEN rs.is_loser = 1 AND rs.is_furo = 1 THEN 1 ELSE 0 END) AS 副露放銃,
        SUM(CASE WHEN rs.is_winner = 1 AND rs.is_riichi = 0 AND rs.is_furo = 0 THEN 1 ELSE 0 END) AS ダマ和了,
        SUM(CASE WHEN rs.is_winner = 1 THEN rs.base_point ELSE 0 END) AS 和了点合計,
        SUM(CASE WHEN rs.is_loser = 1 THEN ABS(rs.base_point) ELSE 0 END) AS 放銃点合計,
        SUM(CASE WHEN rs.is_winner = 1 AND rs.is_riichi = 1 THEN rs.base_point ELSE 0 END) AS 立直和了点合計,
        SUM(CASE WHEN rs.is_winner = 1 AND rs.is_furo = 1 THEN rs.base_point ELSE 0 END) AS 副露和了点合計,
        SUM(CASE WHEN rs.is_winner = 1 AND rs.is_riichi = 0 AND rs.is_furo = 0 THEN rs.base_point ELSE 0 END) AS ダマ和了点合計,
        SUM(CASE WHEN rs.is_loser = 1 AND rc.has_riichi_player = 1 THEN 1 ELSE 0 END) AS 被リーチ放銃,
        SUM(CASE WHEN rs.is_loser = 1 AND rc.has_riichi_player = 0 AND rc.has_furo_player = 1 THEN 1 ELSE 0 END) AS 被副露放銃,
        SUM(CASE WHEN rs.is_loser = 1 AND rc.has_riichi_player = 0 AND rc.has_furo_player = 0 THEN 1 ELSE 0 END) AS 被ダマ放銃,
        SUM(rs.kyotaku_point) AS 供託収支,
        SUM(rs.penalty_point) AS ノーテン罰符収支,
        SUM(CASE WHEN r.result_type = 'chombo' AND rs.is_loser = 1 THEN 1 ELSE 0 END) AS チョンボ数
    FROM round_seats rs
    JOIN rounds r ON rs.round_id = r.round_id
    JOIN games g ON r.game_id = g.game_id
    JOIN members m ON rs.member_id = m.member_id
    JOIN round_context rc ON rs.round_id = rc.round_id
    {where_str}
    GROUP BY rs.member_id, m.member_name
    """
    with _db() as conn:
        df_raw = _fetch_df(conn, query, tuple(params))
        if df_raw.empty:
            return pd.DataFrame(), 0

        # 比率・平均値計算
        rows = []
        for _, d in df_raw.iterrows():
            k = int(d["局数"])
            if k == 0:
                continue
            w_c = int(d["和了"])
            h_c = int(d["放銃"])
            r_c = int(d["リーチ"])
            f_c = int(d["副露"])
            l_c = int(d["流局"])
            tsumo_c = int(d["ツモ"])
            r_w_c = int(d["リーチ後和了"])
            f_w_c = int(d["副露和了"])
            d_w_c = int(d["ダマ和了"])

            avg_win = round(d["和了点合計"] / w_c) if w_c else 0
            avg_lose = round(d["放銃点合計"] / h_c) if h_c else 0

            row = {
                "名前": d["名前"],
                "局数": k,
                "和了率": round(w_c / k * 100, 1),
                "ツモ率": round(tsumo_c / w_c * 100, 1) if w_c else 0.0,
                "放銃率": round(h_c / k * 100, 1),
                "和銃差": round((w_c - h_c) / k * 100, 1),
                "流局時聴牌率": round(int(d["テンパイ"]) / l_c * 100, 1) if l_c > 0 else 0.0,
                "ノーテン罰符収支": int(d["ノーテン罰符収支"]),
                "供託収支": int(d["供託収支"]),
                "副露率": round(f_c / k * 100, 1),
                "リーチ率": round(r_c / k * 100, 1),
                "立直和了率": round(r_w_c / r_c * 100, 1) if r_c else 0.0,
                "立直放銃率": round(int(d["リーチ後放銃"]) / r_c * 100, 1) if r_c else 0.0,
                "副露和了率": round(f_w_c / f_c * 100, 1) if f_c else 0.0,
                "副露放銃率": round(int(d["副露放銃"]) / f_c * 100, 1) if f_c else 0.0,
                "ダマ和了率": round(d_w_c / w_c * 100, 1) if w_c else 0.0,
                "被リーチ放銃率": round(int(d["被リーチ放銃"]) / h_c * 100, 1) if h_c else 0.0,
                "被副露放銃率": round(int(d["被副露放銃"]) / h_c * 100, 1) if h_c else 0.0,
                "被ダマ放銃率": round(int(d["被ダマ放銃"]) / h_c * 100, 1) if h_c else 0.0,
                "平均和了": avg_win,
                "平均放銃": avg_lose,
                "立直平均打点": round(d["立直和了点合計"] / r_w_c) if r_w_c else 0,
                "副露平均打点": round(d["副露和了点合計"] / f_w_c) if f_w_c else 0,
                "ダマ平均打点": round(d["ダマ和了点合計"] / d_w_c) if d_w_c else 0,
                "打点効率": round(avg_win / avg_lose, 2) if (avg_win and avg_lose) else 0.0,
            }
            if int(d["チョンボ数"]) > 0:
                row["チョンボ数"] = int(d["チョンボ数"])
            rows.append(row)

        # 対象となった試合数を取得
        gid_query = f"""
        SELECT COUNT(DISTINCT r.game_id)
        FROM rounds r
        JOIN games g ON r.game_id = g.game_id
        {where_str}
        """
        c = conn.cursor()
        c.execute(gid_query, tuple(params))
        n_round_games = c.fetchone()[0] or 0

        return pd.DataFrame(rows), n_round_games
