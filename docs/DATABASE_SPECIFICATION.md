# 麻雀スコア管理システム データ構造・移行 仕様書

## 1. 概要と基本原則

### 1.1 目的
本仕様書は、麻雀スコアアプリにおけるデータモデルを第3正規形に適合させ、データの冗長化・更新時異変・集計困難な非アトミック値（カンマ区切り文字列や過剰なJSON）を排除し、過去対局の不変性と将来的なルール拡張性を担保するデータ構造を定義する。

### 1.2 設計原則
1. **完全な正規化と縦持ち構造**:
   局ごとの記録は「局ヘッダ(`rounds`)」と「4座席ごとの状態レコード(`round_seats`)」に完全に分離する。文字列検索を要するカンマ区切り文字列やJSONを排除し、全てフラグ(0/1)と細分化された点数内訳で表現する。
2. **UUID v7 による一意性と順序性の担保**:
   複数端末でのオフライン記録時におけるID衝突を防ぎつつ、書き込みパフォーマンスを維持するため、主キーには UUID v7（時間順UUID）を採用する。
3. **過去対局の完全な不変性（Immutability）**:
   対局完了後にメンバー名変更、グループ脱退、ルール編集が行われても、過去の対局結果・成績・順位は一切変動しない。当時のルールはJSONスナップショットとして対局単位で凍結保存する。
4. **ゲストの扱い**:
   外部参加者（ゲスト）であっても専用のメンバーID（`is_guest = 1`）を発行して管理し、成績の集計可能性を保証する。

---

## 2. データベース物理スキーマ仕様

SQLite（ローカル）および PostgreSQL / Supabase（リモート）の双方で同一の論理構造を維持する。
主キー(UUID)は `VARCHAR(36)` として保存する。

### 2.1 マスターエンティティ

#### `members`（メンバーマスター）
個人を一意に識別する。ゲストも一時メンバーとして登録する。

| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `member_id` | VARCHAR(36) | PK | メンバー固有ID (UUID v7) |
| `member_name` | TEXT / VARCHAR(255) | NOT NULL | 現在の表示名 |
| `is_guest` | INTEGER / SMALLINT | NOT NULL DEFAULT 0 | ゲストフラグ（0: 正規, 1: ゲスト） |
| `is_archived` | INTEGER / SMALLINT | NOT NULL DEFAULT 0 | 削除フラグ（0: 有効, 1: アーカイブ） |
| `created_at` | TEXT / TIMESTAMPTZ | NOT NULL DEFAULT CURRENT_TIMESTAMP | 登録日時 |

#### `groups`（グループマスター）

| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `group_id` | VARCHAR(36) | PK | グループ識別子 (UUID v7) |
| `display_id` | TEXT / VARCHAR(32) | NULL | 表示用ID（例: 'G01'） |
| `group_name` | TEXT / VARCHAR(255) | NOT NULL | グループ表示名 |
| `default_rule_id`| VARCHAR(36) | NULL, FK -> rule_templates | 既定のルールテンプレートID |
| `is_archived` | INTEGER / SMALLINT | NOT NULL DEFAULT 0 | 削除フラグ |

#### `group_memberships`（グループ所属中間テーブル）

| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `group_id` | VARCHAR(36) | PK, FK -> groups | グループID |
| `member_id` | VARCHAR(36) | PK, FK -> members | メンバーID |
| `joined_at` | TEXT / TIMESTAMPTZ | NOT NULL DEFAULT CURRENT_TIMESTAMP | 所属開始日時 |

#### `rule_templates`（ルールテンプレート）

| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `rule_id` | VARCHAR(36) | PK | ルール識別子 (UUID v7) |
| `name` | TEXT / VARCHAR(255) | NOT NULL | 表示名（例: 'Mリーグルール'） |
| `kind` | TEXT / VARCHAR(32) | NOT NULL | 種別（'official' / 'custom'） |
| `version` | INTEGER | NOT NULL DEFAULT 1 | スキーマバージョン |
| `config_json` | TEXT / JSONB | NOT NULL | 設定パラメータ一式 |
| `is_archived` | INTEGER / SMALLINT | NOT NULL DEFAULT 0 | 削除フラグ |

---

### 2.2 対局トランザクションエンティティ

#### `games`（対局ヘッダ）
| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `game_id` | VARCHAR(36) | PK | 対局ID (UUID v7) |
| `played_at` | TEXT / TIMESTAMPTZ | NOT NULL | 対局完了日時 |
| `group_id` | VARCHAR(36) | NULL, FK -> groups | 選択されたグループID |
| `rule_name_snapshot` | TEXT / VARCHAR(255) | NOT NULL | 対局時点のルール名 |
| `rule_config_snapshot`| TEXT / JSONB | NOT NULL | 当時のルール設定スナップショット |
| `game_mode` | TEXT / VARCHAR(32) | NOT NULL DEFAULT 'detail'| 入力モード ('detail' / 'simple') |
| `is_synced` | INTEGER / SMALLINT | NOT NULL DEFAULT 0 | 同期フラグ |

#### `game_participants`（対局参加者・最終成績）
各対局における参加者と確定成績（4人麻雀時は4行）。

| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `game_id` | VARCHAR(36) | PK, FK -> games | 対局ID |
| `seat` | INTEGER / SMALLINT | PK, CHECK (seat 1-4)| 座席（1:東, 2:南, 3:西, 4:北） |
| `member_id` | VARCHAR(36) | NOT NULL, FK -> members | メンバーID（ゲストも必ず指定） |
| `player_name_snapshot`| TEXT / VARCHAR(255) | NOT NULL | 対局時点の表示名 |
| `final_score` | INTEGER | NOT NULL | 最終持ち点 |
| `rank` | INTEGER / SMALLINT | NOT NULL, CHECK(1-4)| 確定着順 |
| `point` | REAL / NUMERIC(6,1) | NOT NULL | ウマオカ適用後の最終pt |
| `was_group_member` | INTEGER / SMALLINT | NOT NULL | 0:対局当時ゲスト, 1:当時正規メンバー |

#### `rounds`（局ヘッダ）
1局ごとの進行メタ情報（名前や個別点数は持たない）。

| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `round_id` | VARCHAR(36) | PK | 局のID (UUID v7) |
| `game_id` | VARCHAR(36) | NOT NULL, FK -> games | 対局ID |
| `round_index` | INTEGER | NOT NULL | 局通番（0: 東1局...） |
| `kyoku_name` | TEXT / VARCHAR(64) | NOT NULL | 局表示名（例: '東1局'） |
| `honba` | INTEGER | NOT NULL DEFAULT 0 | 本場数 |
| `riichi_sticks` | INTEGER | NOT NULL DEFAULT 0 | 局開始時の供託リーチ棒本数 |
| `result_type` | TEXT / VARCHAR(32) | NOT NULL | 結果（'ron', 'tsumo', 'ryukyoku', 'chombo'） |

#### `round_seats`（座席別局結果・スタッツ）
各局の座席別点数とフラグ（1局4行）。カンマ区切りやJSONを完全に排除。

| カラム名 | 型 (SQLite / PG) | 制約 | 説明 |
| :--- | :--- | :--- | :--- |
| `round_id` | VARCHAR(36) | PK, FK -> rounds | 局ID |
| `seat` | INTEGER / SMALLINT | PK, CHECK(1-4) | 座席 |
| `member_id` | VARCHAR(36) | NOT NULL, FK -> members | メンバーID |
| `base_point` | INTEGER | NOT NULL DEFAULT 0 | 和了/放銃/ツモられの基本点増減 |
| `honba_point` | INTEGER | NOT NULL DEFAULT 0 | 本場による加減点 |
| `kyotaku_point` | INTEGER | NOT NULL DEFAULT 0 | リーチ棒の獲得・支出（宣言時 -1000） |
| `penalty_point` | INTEGER | NOT NULL DEFAULT 0 | 流局罰符・チョンボの増減 |
| `score_delta` | INTEGER | NOT NULL DEFAULT 0 | 上記すべての合算（最終的な点数変動） |
| `chip_delta` | INTEGER | NOT NULL DEFAULT 0 | チップ増減 |
| `han` | INTEGER | NULL | 翻数（和了時のみ） |
| `fu` | INTEGER | NULL | 符数（和了時のみ） |
| `is_winner` | INTEGER / SMALLINT| NOT NULL DEFAULT 0 | 和了フラグ（ダブロン時は複数席が1） |
| `is_loser` | INTEGER / SMALLINT| NOT NULL DEFAULT 0 | 放銃フラグ |
| `is_riichi` | INTEGER / SMALLINT| NOT NULL DEFAULT 0 | 立直フラグ |
| `is_furo` | INTEGER / SMALLINT| NOT NULL DEFAULT 0 | 副露フラグ |
| `is_tenpai` | INTEGER / SMALLINT| NOT NULL DEFAULT 0 | テンパイフラグ |

---

## 3. 旧データ移行（マイグレーション）方式

既存の旧データ（カンマ区切り等を含む古い `games` や `rounds`）からの移行は、アプリ起動時の動的マイグレーション**ではなく**、事前実行型の「一括移行バッチスクリプト」により行います。

1. **専用スクリプトの実行**: 旧 `local_mahjong.db` を読み込み、本仕様に基づく新しいスキーマのDB（例: `local_mahjong_v2.db`）を生成するスクリプトを用意する。
2. **データのクレンジング**: 文字列の分解、不足データの補完、ゲストの仮メンバー登録などをスクリプト内で一括処理する。
3. **アプリの完全刷新**: アプリ（`database2.py` 等）のコードは、新仕様のデータアクセスのみを前提として書き直し、後方互換性維持のためのレガシーコードをアプリ内に残さない。

---

## 4. 成績集計クエリ仕様

完全正規化されたスキーマにより、すべての通算成績・スタッツは文字列パースなしに SQL のみで高速算出可能です。

### 4.1 平均純和了点（本場・供託を除く）の集計例
```sql
SELECT 
    m.member_name,
    COUNT(rs.round_id) AS win_count,
    -- 和了した局の純粋な基本点（base_point）の平均
    AVG(rs.base_point) AS avg_base_win_point
FROM round_seats rs
JOIN members m ON rs.member_id = m.member_id
WHERE rs.is_winner = 1
GROUP BY rs.member_id, m.member_name;
```
