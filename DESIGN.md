# 麻雀スコアアプリ 設計書・現状ステータス

## 1. 概要と達成状況

本システムは、四麻の対局進行管理・スコア入力・成績集計（グループ別・個人別・ルール別）・ルール管理・メンバー管理を行う麻雀スコア管理システムである。

過去の旧スキーマ（対局テーブルに4名分の名前・点数が直接保持されていた形式）から、正規化された新スキーマ（メンバー不変ID、対局参加者分離、局詳細分離、ルール完全スナップショット）へのデータ移行および検証は**完了済み**である。

- **現在の正本ローカルDB:** `local_mahjong_v2_new.db`
- **現在の稼働アプリ:** Streamlit（`app.py`、`src/database2.py`）
- **次期フェーズ:** Next.js + Supabase + Cloudflare Pages による複数端末・リアルタイムWebアプリへの移行

---

## 2. 確定した利用ルール・仕様

### 2.1 グループ管理と所属
- **親族麻雀グループ:**
  - 既存メンバーを所属させた基本グループ。
  - 通常の親族麻雀成績では、対局時点で4人全員が所属メンバーだった対局のみを集計・表示。
  - 「外部参加者を含む」をオンにすることで、外部参加者が同卓した対局および外部参加者の成績を表示可能。
- **追加グループ（麻雀部等）:**
  - メンバーの複数グループ所属に対応。
- **全体成績:**
  - グループに関係なく、記録されたすべての対局を集計・表示。

### 2.2 ルールテンプレートと対局スナップショット
- **公式テンプレート（`kind = 'official'`）:** 固定・編集不可。
- **カスタムテンプレート（`kind = 'custom'`）:** 公式テンプレートを複製して作成・編集。
- **アーカイブ機能:** カスタムテンプレートおよびグループは物理削除せず、`is_archived = 1` で論理削除。アーカイブ後も過去対局の表示・検証に利用可能。
- **不変性の保証:**
  - 対局開始時点のルール名およびルール設定（JSON）を `games` テーブルにスナップショットとして完全保持。
  - 後からルールテンプレートを変更・アーカイブしても、過去の対局結果・成績集計は一切変化しない。

### 2.3 対応範囲
- 四麻専用（`player_count = 4`）。
- 点数計算（符・翻）、ウマ・オカ、連荘・輪荘、ノーテン罰符、飛び終了、西入条件、チョンボペナルティに対応。

---

## 3. データモデル（実装実態：`src/database2.py` 準拠）

データベースは正規化されており、以下のテーブルで構成される。

### 3.1 `members`（メンバーマスタ）
個人を不変IDで管理する。表示名の重複や変更を許容する。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `member_id` | TEXT (UUID v7) | 主キー。不変ID |
| `member_name` | TEXT | メンバー名（表示名） |
| `is_guest` | INTEGER | ゲスト・外部参加者フラグ（0: 正則, 1: ゲスト） |
| `is_archived` | INTEGER | アーカイブフラグ（0: 有効, 1: アーカイブ） |

### 3.2 `groups`（グループマスタ）
対局のまとまり（親族麻雀、麻雀部など）を管理する。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `group_id` | TEXT (UUID v7) | 主キー。不変ID |
| `display_id` | TEXT | 表示用ID（G01, G02等） |
| `group_name` | TEXT | グループ名 |
| `default_rule_id` | TEXT | 既定ルールテンプレートID |
| `is_archived` | INTEGER | アーカイブフラグ（0: 有効, 1: アーカイブ） |

### 3.3 `group_memberships`（グループ所属関係）
メンバーとグループの多対多の所属関係を管理する。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `group_id` | TEXT (UUID) | 外部キー（groups） |
| `member_id` | TEXT (UUID) | 外部キー（members） |
| 複合主キー | - | `(group_id, member_id)` |

### 3.4 `rule_templates`（ルールテンプレート）
公式ルールおよびカスタムルールの設定マスタ。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `rule_id` | TEXT | 主キー（'m_league', 'rule_xxxx' 等） |
| `name` | TEXT | ルール名 |
| `kind` | TEXT | 区分（'official' または 'custom'） |
| `version` | INTEGER | 設定スキーマバージョン |
| `config_json` | TEXT (JSON) | 詳細設定（返し点、ウマ、オカ、飛び、連荘、流局等） |
| `is_archived` | INTEGER | アーカイブフラグ（0: 有効, 1: アーカイブ） |

### 3.5 `games`（対局ヘッダ）
対局ごとの基本情報と、対局時点の不変スナップショットを保持する。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `game_id` | TEXT (UUID v7) | 主キー。対局ID |
| `played_at` | TEXT (DATETIME) | 対局日時 |
| `group_id` | TEXT (UUID) | 選択されたグループID |
| `rule_name_snapshot` | TEXT | 対局時点のルール名 |
| `rule_config_snapshot` | TEXT (JSON) | 対局時点のルール設定完全JSON |
| `game_mode` | TEXT | 'detail'（詳細局入力）または 'simple'（結果のみ入力） |
| `sync_target` | INTEGER | オンライン同期対象フラグ |
| `is_synced` | INTEGER | 同期済みフラグ |

### 3.6 `game_participants`（対局参加者・確定成績）
対局参加者4名の成績と、対局時点の所属状態を保持する。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `game_id` | TEXT (UUID) | 外部キー（games） |
| `seat` | INTEGER | 起親からの座席順（1: 東, 2: 南, 3: 西, 4: 北） |
| `member_id` | TEXT (UUID) | 外部キー（members） |
| `player_name_snapshot` | TEXT | 対局時点のプレイヤー表示名 |
| `final_score` | INTEGER | 最終持ち点 |
| `rank` | INTEGER | 確定順位（1〜4） |
| `point` | REAL | ウマ・オカ計算後の確定ポイント |
| `was_group_member` | INTEGER | 対局時点で選択グループに所属していたか（1: 所属, 0: 外部） |
| 複合主キー | - | `(game_id, seat)` |

### 3.7 `rounds`（局データ）
詳細対局モードにおける局ごとの進行・結果ヘッダ。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `round_id` | TEXT (UUID v7) | 主キー。局ID |
| `game_id` | TEXT (UUID) | 外部キー（games） |
| `round_index` | INTEGER | 進行順インデックス（1〜） |
| `kyoku_name` | TEXT | 局名（'東1局', '南2局' 等） |
| `honba` | INTEGER | 本場数 |
| `riichi_sticks` | INTEGER | 供託立直棒数 |
| `result_type` | TEXT | 結果種別（'ron', 'tsumo', 'ryukyoku', 'chombo'） |

### 3.8 `round_seats`（局座席データ）
1局における各座席（各プレイヤー）の収支・アクション詳細。

| カラム名 | 型 | 説明 |
| :--- | :--- | :--- |
| `round_id` | TEXT (UUID) | 外部キー（rounds） |
| `seat` | INTEGER | 座席順（1〜4） |
| `member_id` | TEXT (UUID) | 外部キー（members） |
| `base_point` | INTEGER | 和了打点・放銃打点 |
| `honba_point` | INTEGER | 積み棒収支 |
| `kyotaku_point` | INTEGER | 供託立直棒収支 |
| `penalty_point` | INTEGER | ノーテン罰符・チョンボ罰符収支 |
| `score_delta` | INTEGER | 局収支（総点数変動） |
| `chip_delta` | INTEGER | チップ収支 |
| `han` / `fu` | INTEGER | 翻数 / 符数 |
| 各種フラグ | INTEGER | `is_winner`, `is_loser`, `is_riichi`, `is_furo`, `is_tenpai` |
| 複合主キー | - | `(round_id, seat)` |

---

## 4. 実装・移行の完了実績

以下の工程はすべて完了し、検証済みである。

1. **新スキーマの構築と移行スクリプト作成:** 完了（`scripts/migrate_v2_final.py`, `scripts/rebuild_v2_perfect.py`）。
2. **旧対局データ（games）の完全移行:** 完了。全過去対局を `games`, `game_participants`, `rounds`, `round_seats` へ正規化。
3. **点数整合性検証:** 完了（`scripts/verify_scores.py`, `scripts/verify_production_migration.py`）。過去全試合の点数整合性が保証されている。
4. **メンバー・グループのID化:** 完了。親族麻雀グループ、麻雀部グループ、公式ルール（Mリーグルール等）が整備済み。
5. **正本ローカルDBの統合:** `local_mahjong_v2_new.db` を正本として `app.py` が正常稼働。

---

## 5. 次期フェーズ計画：Webアプリ移行（Next.js + Supabase）

### 5.1 移行の目的
- PC、スマートフォンなど複数端末からの安全な同時利用。
- 1台の入力（記録係）を他の全端末でリアルタイム自動更新（閲覧）。
- クラウド（Supabase無料枠 + Cloudflare Pages）での完全無料・永続運用。

### 5.2 アーキテクチャ
- **フロントエンド:** Next.js (TypeScript) on Cloudflare Pages
- **データベース・認証・リアルタイム:** Supabase (PostgreSQL, Supabase Auth, Supabase Realtime)
- **スリープ防止:** GitHub Actions による定期ヘルスチェック実行

### 5.3 実装移行ステップ
1. **Supabase環境構築:** `local_mahjong_v2_new.db` のスキーマおよびデータをそのままSupabase PostgreSQLへ展開。
2. **ロジック移植:** `src/calc.py` および `src/game_logic.py` をTypeScriptの純粋関数として移植。
3. **フロントエンド実装:**
   - 記録係のみに入力ボタンを表示・活性化する排他制御（RLS＋UI制御）。
   - Supabase Realtimeによる閲覧端末へのスコア自動反映。
   - 個人成績、グループ別成績、ルール管理画面の構築。
