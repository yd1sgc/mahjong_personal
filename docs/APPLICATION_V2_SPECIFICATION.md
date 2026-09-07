# 麻雀スコア管理システム アプリケーション V2 移行仕様書
（新DB構造・第3正規形・UUID v7 完全対応版）

## 1. 概要と基本方針

### 1.1 背景と目的
現在、本プロジェクトには旧レガシースキーマ（INTEGER連番ID、`games` テーブル内の横持ちカラム `p1_name`〜`p4_name`、局データ `rounds` のカンマ区切り文字列）を前提としたコードと、互換用コードが混在している。
また、計算処理や終了判定においてモジュール固定定数（ハードコード）や複雑な手続き型ループが残り、スパゲッティ化およびルール拡張の阻害要因となっている。
本仕様書は、第3正規形・UUID v7・完全縦持ち構造を採用した新DB（`local_mahjong_v2_new.db` および `docs/DATABASE_SPECIFICATION.md`）を唯一の正本として、アプリケーションコード（`src/` 配下）を全面的に対応・刷新し、ハードコードを撤廃して保守性の高いアーキテクチャを確立するための仕様を定める。

### 1.2 設計基本原則
1. **旧互換レイヤーの完全排除**:
   アプリ内に旧データ形式（横持ちカラムやカンマ区切り文字列）をパース・変換するフォールバックロジックを残さない。DBアクセスは新スキーマのみを前提としてシンプルに記述する。
2. **ハードコードの完全撤廃とルールの完全注入**:
   初期点、返し点、ウマ配列、本場加算点、供託リーチ棒、東風/半荘終了基準、飛び判定閾値等の対局パラメータは、すべて対局開始時に固定された `rule_config` から動的に取得する。モジュール先頭の固定定数による暗黙的フォールバックを禁止する。
3. **単一責任の原則に基づくスパゲッティコードの防止**:
   * **データアクセス層（`database2.py`）**: 純粋なSQL実行とトランザクション管理のみに責務を限定。
   * **進行・計算層（`game_logic.py`）**: 局イベントから4席分の `round_seats` レコードを算出する純粋な計算ロジックと、対局進行状態コンテナを分離。
   * **集計層（`stats.py`）**: Python側でのループ展開や辞書突き合わせを全廃し、正規化SQL集計ビューへ全面移行。
4. **ID体系の UUID v7 統一**:
   対局（`game_id`）、局（`round_id`）、メンバー（`member_id`）、グループ（`group_id`）、ルール（`rule_id`）の識別子をすべて 36文字の文字列（UUID v7）に一本化する。
5. **ローカル先行・オンラインDB（Supabase）同一スキーマ保証**:
   ローカル（SQLite）とリモート（PostgreSQL / Supabase）で同一のテーブル構造・列名・制約を維持する。ローカル環境での完全動作・テスト検証完了後に、Supabase側への同一マイグレーションを適用する。

---

## 2. データベース物理スキーマ定義（ローカル & リモート共通）

### 2.1 マスターエンティティ

#### `members`（メンバーマスター）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `member_id` | TEXT | VARCHAR(36) | PRIMARY KEY | UUID v7 |
| `member_name` | TEXT | VARCHAR(255) | NOT NULL | メンバー表示名 |
| `is_guest` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | ゲストフラグ (0:正規, 1:ゲスト) |
| `is_archived` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | アーカイブフラグ (0:有効, 1:無効) |
| `created_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT CURRENT_TIMESTAMP | 登録日時 |

#### `groups`（グループマスター）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `group_id` | TEXT | VARCHAR(36) | PRIMARY KEY | UUID v7 |
| `display_id` | TEXT | VARCHAR(32) | NULL | 表示用識別子（例: 'G01'） |
| `group_name` | TEXT | VARCHAR(255) | NOT NULL | グループ表示名 |
| `default_rule_id`| TEXT | VARCHAR(36) | NULL | 既定ルールID |
| `is_archived` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | アーカイブフラグ |

#### `group_memberships`（グループ所属中間テーブル）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `group_id` | TEXT | VARCHAR(36) | NOT NULL | FK -> groups(group_id) |
| `member_id` | TEXT | VARCHAR(36) | NOT NULL | FK -> members(member_id) |
| `joined_at` | TEXT | TIMESTAMPTZ | NOT NULL DEFAULT CURRENT_TIMESTAMP | 所属開始日時 |
| **PRIMARY KEY** | - | - | (group_id, member_id) | 複合主キー |

#### `rule_templates`（ルールテンプレート）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `rule_id` | TEXT | VARCHAR(36) | PRIMARY KEY | ルール識別子 |
| `name` | TEXT | VARCHAR(255) | NOT NULL | ルール名 |
| `kind` | TEXT | VARCHAR(32) | NOT NULL | 種別 ('official' / 'custom') |
| `version` | INTEGER | INTEGER | NOT NULL DEFAULT 1 | スキーマバージョン |
| `config_json` | TEXT | JSONB | NOT NULL | 設定パラメータJSON |
| `is_archived` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | アーカイブフラグ |

---

### 2.2 対局トランザクションエンティティ

#### `games`（対局ヘッダ）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `game_id` | TEXT | VARCHAR(36) | PRIMARY KEY | UUID v7 |
| `played_at` | TEXT | TIMESTAMPTZ | NOT NULL | 対局終了日時 |
| `group_id` | TEXT | VARCHAR(36) | NULL | 選択グループID (FK -> groups) |
| `rule_name_snapshot` | TEXT | VARCHAR(255) | NOT NULL | 対局時点のルール表示名 |
| `rule_config_snapshot`| TEXT | JSONB | NOT NULL | 当時のルール設定JSONスナップショット |
| `game_mode` | TEXT | VARCHAR(32) | NOT NULL DEFAULT 'detail' | 入力モード ('detail' / 'simple') |
| `is_synced` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | リモート同期フラグ |

#### `game_participants`（対局参加者・確定成績）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `game_id` | TEXT | VARCHAR(36) | NOT NULL | FK -> games(game_id) |
| `seat` | INTEGER | SMALLINT | NOT NULL CHECK(seat BETWEEN 1 AND 4) | 座席 (1:東, 2:南, 3:西, 4:北) |
| `member_id` | TEXT | VARCHAR(36) | NOT NULL | 参加者ID (FK -> members) |
| `player_name_snapshot`| TEXT | VARCHAR(255) | NOT NULL | 対局時点の表示名 |
| `final_score` | INTEGER | INTEGER | NOT NULL | 確定持ち点 (例: 25000) |
| `rank` | INTEGER | SMALLINT | NOT NULL CHECK(rank BETWEEN 1 AND 4) | 最終着順 (1〜4) |
| `point` | REAL | NUMERIC(6,1) | NOT NULL | ウマオカ適用後の確定ポイント (例: +45.0) |
| `was_group_member` | INTEGER | SMALLINT | NOT NULL | 対局当時のグループ所属フラグ (0/1) |
| **PRIMARY KEY** | - | - | (game_id, seat) | 複合主キー |

#### `rounds`（局ヘッダ）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `round_id` | TEXT | VARCHAR(36) | PRIMARY KEY | UUID v7 |
| `game_id` | TEXT | VARCHAR(36) | NOT NULL | FK -> games(game_id) |
| `round_index` | INTEGER | INTEGER | NOT NULL | 局通番 (0始まり) |
| `kyoku_name` | TEXT | VARCHAR(64) | NOT NULL | 局表示名 (例: '東1局') |
| `honba` | INTEGER | INTEGER | NOT NULL DEFAULT 0 | 本場数 |
| `riichi_sticks` | INTEGER | INTEGER | NOT NULL DEFAULT 0 | 局開始時の供託リーチ棒本数 |
| `result_type` | TEXT | VARCHAR(32) | NOT NULL | 局結果種別 ('ron', 'tsumo', 'ryukyoku', 'chombo') |

#### `round_seats`（局・座席別成績・行動スタッツ）
| カラム名 | SQLite 型 | PostgreSQL 型 | 制約 | 説明 |
| :--- | :--- | :--- | :--- | :--- |
| `round_id` | TEXT | VARCHAR(36) | NOT NULL | FK -> rounds(round_id) |
| `seat` | INTEGER | SMALLINT | NOT NULL CHECK(seat BETWEEN 1 AND 4) | 座席 (1〜4) |
| `member_id` | TEXT | VARCHAR(36) | NOT NULL | 席のプレイヤーID (FK -> members) |
| `base_point` | INTEGER | INTEGER | NOT NULL DEFAULT 0 | 純粋な和了・放銃・ツモ支払いの基本点増減 |
| `honba_point` | INTEGER | INTEGER | NOT NULL DEFAULT 0 | 本場による点数増減 |
| `kyotaku_point`| INTEGER | INTEGER | NOT NULL DEFAULT 0 | 供託リーチ棒の収受（立直宣言時は -1000） |
| `penalty_point`| INTEGER | INTEGER | NOT NULL DEFAULT 0 | ノーテン罰符・チョンボの支払/受取 |
| `score_delta` | INTEGER | INTEGER | NOT NULL DEFAULT 0 | 局での総点数増減（上記4項目の合計） |
| `chip_delta` | INTEGER | INTEGER | NOT NULL DEFAULT 0 | チップ増減枚数 |
| `han` | INTEGER | SMALLINT | NULL | 翻数（和了時のみ） |
| `fu` | INTEGER | SMALLINT | NULL | 符数（和了時のみ） |
| `is_winner` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | 和了フラグ (0/1, ダブロン時は複数席が1) |
| `is_loser` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | 放銃フラグ (0/1) |
| `is_riichi` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | 立直フラグ (0/1) |
| `is_furo` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | 副露フラグ (0/1) |
| `is_tenpai` | INTEGER | SMALLINT | NOT NULL DEFAULT 0 | 流局時テンパイフラグ (0/1) |
| **PRIMARY KEY** | - | - | (round_id, seat) | 複合主キー |

---

## 3. アプリケーション層（`src/`）刷新仕様

### 3.1 データアクセス層（`src/database2.py`）
1. **レガシーカラム・旧互換コードの完全除去**:
   * `games` テーブルに対する `p1_name`, `p1_score`, `p1_rank`, ..., `p4_rank` への SELECT / INSERT / UPDATE をすべて廃止。
   * `rounds` テーブルに対するカンマ区切り列（`winner`, `loser`, `furo_names`, `riichi_names`, `tenpai_names`）の読み書きを全廃。
   * 1,360行に肥大化したコードから旧スキーマ移行関数や分岐を削ぎ落とし、スリムなCRUDモジュールとして再構築。
2. **対局保存APIの再定義**:
   * `save_game_record(game_data: dict) -> str`:
     1つのトランザクション内で以下を不可分に実行する。
     1. `games` への INSERT（1行）
     2. `game_participants` への INSERT（4行）
     3. 詳細入力時（`game_mode == 'detail'`）:
        - `rounds` への INSERT（局数分）
        - `round_seats` への INSERT（局数 × 4行）
3. **下書き（ドラフト）保存・復元の新スキーマ連動**:
   * `drafts` テーブル（またはローカル一時保存）の構造を新スキーマのエンティティ構造に合わせ、中断時の局進行データが `round_seats` 形式でシリアライズされるようにする。

### 3.2 対局進行・状態管理層（`src/game_logic.py`, `src/views/game.py`）
1. **ハードコード撤廃とルール完全注入**:
   * 本場加算点：`rule_config["detail"].get("honba_pt", 300)`（ロン時）、`honba_pt // 3`（ツモ時）を参照し、直書き数値を排除。
   * リーチ棒供託点：`rule_config["detail"].get("riichi_pt", 1000)` を参照。
   * 局終了・サドンデス判定：`rule_config["basic"].get("game_length", "hanchan")` により、東風戦（東4局終了基準）と半荘戦（南4局終了基準）を動的に切り替え。
   * 飛び判定：`rule_config["detail"].get("tobi_end")`（`under_zero` / `zero_or_less` / `none`）に従い厳密に分岐。
2. **各局精算データの生成ロジック（純粋関数化）**:
   局結果確定時、座席ごとの変動内訳を明確に算出して辞書化する。
   * 和了者: `base_point`（符翻の基本点）, `honba_point`（本場加算分）, `kyotaku_point`（供託棒獲得分 - 宣言支出分）
   * 放銃者: `base_point`（マイナス）, `honba_point`（マイナス）, `kyotaku_point`（立直宣言時は -1000）
   * ツモられ（親/子）: 各自の支払い分を `base_point` と `honba_point` に分離
   * 流局時: `penalty_point`（ノーテン罰符の増減）
   * チョンボ時: `penalty_point`（満貫払い等の減点）
3. **ダブロン（multi_ron）対応**:
   同一局内で複数の `is_winner = 1` 行を許可する。供託棒はルールスナップショット（上家取り／頭ハネか頭割りか）に基づき勝者の `kyotaku_point` に加算。

### 3.3 成績集計・分析層（`src/views/stats.py`, `src/calc.py`）
1. **SQLによる集計への完全置換**:
   従来の「全対局をメモリにロードしてPython側でカンマ区切りをsplitしてループ集計する処理」を全廃し、`round_seats` と `game_participants` をJOINする高速SQLクエリへ置換する。
2. **ウマオカ計算の純粋関数化 ([src/calc.py](file:///c:/Users/segu1/MyFiles/開発/repos/mahjong_personal/src/calc.py))**:
   モジュールトップレベルの定数 `RETURN_POINT` や `UMA_SETTINGS` を完全撤廃。`calc_point(score, rank, rule_config)` は `rule_config` が与えられない場合はエラーとし、暗黙のデフォルト値計算によるバグを防止する。
3. **主要指標の算出式（SQL）**:
   * **和了率**: `SUM(is_winner) * 1.0 / COUNT(round_id)`
   * **放銃率**: `SUM(is_loser) * 1.0 / COUNT(round_id)`
   * **立直率**: `SUM(is_riichi) * 1.0 / COUNT(round_id)`
   * **副露率**: `SUM(is_furo) * 1.0 / COUNT(round_id)`
   * **流局時聴牌率**: `SUM(is_tenpai) * 1.0 / COUNT(流局局数)`
   * **平均純和了打点**: `AVG(base_point) WHERE is_winner = 1`
   * **平均純放銃打点**: `AVG(ABS(base_point)) WHERE is_loser = 1`
4. **グループ・ゲストフィルター**:
   * 特定グループ選択時:
     * 「外部参加者を含まない」: その対局の全4名が `was_group_member = 1` である対局のみを対象とする。
     * 「外部参加者を含む」: `selected_group_id` が対象グループの全対局を対象とする。
   * 全体成績: グループに関係なくすべての対局を集計。

---

## 4. オンライン版（Supabase / PostgreSQL）追従・移行仕様

### 4.1 論理・物理スキーマ整合性
* テーブル構造、カラム名、制約条件は SQLite（ローカル）と PostgreSQL（Supabase）で100%同一とする。
* UUID 生成は、Pythonアプリケーション側で生成する UUID v7（36文字文字列）を主キーとして INSERT するため、DB側の拡張（`pg_uuidv7` 等）への依存を排除する。

### 4.2 移行手順ロードマップ
1. **Step 1: ローカル環境でのアプリ完全刷新**
   * ローカルDB（`local_mahjong_v2_new.db`）を対象としてアプリケーションコードを改修。
   * 単体テスト・結合テスト（全件PASS）を確認。
2. **Step 2: リモート向け新マイグレーションSQLの策定**
   * `migrations/supabase_migration_v2.sql` を作成（第3正規形テーブル群の作成）。
3. **Step 3: リモート本番データ移行スクリプトの実行**
   * `scripts/migrate_v2_remote.py` により、現在の Supabase 内の旧 `games` / `rounds` データを、UUID v7 を採番した新テーブル群へデータ欠損なくバッチ移行する。
4. **Step 4: 接続切替と動作確認**
   * Streamlit secrets を通じたオンライン接続モードでの動作を検証。

---

## 5. テスト計画と安全性検証要件（網羅的検証仕様）

新構造への移行において、以下の5つのテストを網羅的に実施し、品質を客観的に保証する。

### 5.1 【テスト1】ルール動的変更・計算エンジンの単体テスト
* **目的**: ハードコードが排除され、任意のルール設定に対して正しくスコア・ポイントが算出されることを検証する。
* **テストケース**:
  1. **ウマ設定の動的変更**:
     * Mリーグ `[30, 10, -10, -30]`
     * 親族麻雀 `[50, 10, -10, -30]`
     * ゴットー `[10, 5, -5, -10]`
     * ウマなし `[0, 0, 0, 0]`
  2. **オカの有無・返し点の変更**:
     * 25000点持ち30000点返し（オカ20.0ptがトップに加算されるか）
     * 30000点持ち30000点返し（オカなし、ゼロサム確認）
  3. **ゲーム長（東風／半荘）の判定**:
     * 東風戦で東4局終了時に正しくゲーム終了と判定されるか。
     * 半荘戦で南4局終了時まで続行されるか。
  4. **飛び判定（トビ終了）の変更**:
     * `under_zero`（0点未満で終了、ちょうど0点は続行）
     * `zero_or_less`（0点以下で終了）
     * `none`（マイナスになっても箱下続行）
  5. **ゼロサム整合性（全ケース共通）**:
     * 4名の最終 pt の合計値が、計算ルール（ウマ・オカ・端数丸め）で定義された規定の総和（オカなしなら `0.0`）と数学的に一致することを確認。

### 5.2 【テスト2】不可分トランザクション保存テスト
* **目的**: 対局データ保存時のアトミック性（全保存または全ロールバック）を保証する。
* **テストケース**:
  1. **完全保存検証**:
     `save_game_record` を実行した際、`games`（1行）、`game_participants`（4行）、`rounds`（N行）、`round_seats`（N×4行）が過不足なくコミットされ、外部キー整合性が保たれているか。
  2. **異常系ロールバック検証**:
     `rounds` または `round_seats` の INSERT 途中で意図的に例外（不正な型やキー違反）を発生させた際、同一トランザクション内の先行 INSERT（`games` や `game_participants`）が完全にロールバックされ、孤児レコードが一切残らないか。

### 5.3 【テスト3】対局中断・セッション復元ライフサイクルテスト（最重要）
* **目的**: ブラウザのリロードやセッション切断時における対局データ喪失および画面ロックの再発を防止する。
* **対象テスト**: [tests/test_interruption_recovery.py](file:///c:/Users/segu1/MyFiles/開発/repos/mahjong_personal/tests/test_interruption_recovery.py)
* **テストケース**:
  以下の全アクションの直後にセッション状態（`st.session_state`）を強制破棄し、下書き（ドラフト）から復元を試行：
  1. リーチ宣言直後
  2. 副露宣言直後
  3. 和了（ロン／ツモ／ダブロン）直後
  4. 流局（通常流局／途中流局）直後
  5. チョンボ入力直後
  6. Undo（一手戻す）直後
  7. 局履歴修正（round_edit）直後
* **合格判定基準**:
  * 復元後の画面が必ず `view="game"`, `input_mode="normal"` で開くこと（画面が固まらないこと）。
  * 復元後の点数、局数、本場、供託リーチ棒本数が中断前の状態と1点・1本も狂わず一致すること。
  * `python tests/run_tests.py` において 0 failed で合格すること。

### 5.4 【テスト4】成績集計SQLの正確性検証（回帰テスト）
* **目的**: Pythonループから正規化SQLへ置換した集計パイプラインが、従来の計算結果と完全に一致することを保証する。
* **テストケース**:
  * 実データ（`local_mahjong_v2_new.db`）を用いて、特定の主要プレイヤー（全17名）の以下の指標を新旧両方式で算出し、差分ゼロを検証：
    * 対局数、通算得点、平均着順、トップ率、ラス率
    * 和了率、放銃率、立直率、副露率
    * 平均純和了打点、平均純放銃打点

### 5.5 【テスト5】実データ276対局の整合性監査
* **目的**: `local_mahjong_v2_new.db` 内に格納されている既存データの健全性を自動監査する。
* **テストケース**:
  1. **持ち点合計監査**: 全276対局について、4名の `final_score` の合計が各試合 `100,000点`（初期持ち点25,000点×4）と一致すること。
  2. **順位重複監査**: 各対局の `rank` が 1, 2, 3, 4 の4名で構成され、重複がないこと（同着処理ルールに適合していること）。
  3. **局座席整合監査**: `rounds`（300行）の各行に対し、`round_seats` が必ず 4行（seat 1〜4）存在し、`score_delta` の局内合計が供託棒の出入りと数学的に整合していること。

---

## 6. 分散ハイブリッド同期仕様（選択的Push & 全件Pull）

### 6.1 同期アーキテクチャの基本設計
UUID v7 の採用により、オフライン環境とオンライン環境で生成されたIDが全世界で衝突しない特性を最大限に活かし、以下の非対称ハイブリッド同期を実現する。

```mermaid
flowchart TD
    subgraph OnlineServer["オンラインサーバー (Supabase PostgreSQL)"]
        OM["マスタデータ\n(members, groups, rules)"]
        OG["共有対局データ\n(games, rounds, round_seats)"]
    end

    subgraph LocalClient["ローカル環境 (SQLite)"]
        LM["マスタデータ\n(members, groups, rules)"]
        LG_All["全対局データ (ローカル保存)"]
        LG_Sync["オンライン同期対象対局\n(sync_target = 1)"]
        LG_Priv["ローカル限定対局\n(sync_target = 0)"]
    end

    OM <-->|完全双方向同期 (常に同一)| LM
    OG -->|全件Pull (すべて取り込み)| LG_All
    LG_Sync -->|選択的Push (特定対局のみ)| OG
    LG_Priv -.->|送信しない (ローカル維持)| LG_Priv
```

### 6.2 マスタデータの同期ルール（完全同一）
* **対象テーブル**: `members`, `groups`, `group_memberships`, `rule_templates`
* **動作原則**:
  * オンライン・オフラインのどちらで追加・変更されたマスタデータも、同期実行時に双方向で統合（マージ）される。
  * `ON CONFLICT (id) DO UPDATE` により、双方に未登録のレコードを相互に挿入し、常に両環境で同じメンバー一覧・グループ・ルールが利用可能となる。

### 6.3 対局データの同期ルール（非対称・選択的同期）
* **対象テーブル**: `games`, `game_participants`, `rounds`, `round_seats`
* **データモデルの拡張**:
  * `games.sync_target INTEGER NOT NULL DEFAULT 1`: オンライン同期の対象とするか（1: 同期する, 0: ローカル限定）。
  * `games.is_synced INTEGER NOT NULL DEFAULT 0`: オンラインへ同期送信済みか（1: 同期済み, 0: 未同期）。
* **オンライン → ローカル（全件Pull）**:
  * オンラインに存在し、ローカルに未登録の `game_id`（UUID）をすべてローカルDBへ取り込む。
  * これにより、ローカル環境には常にすべての対局履歴が集約される。
* **ローカル → オンライン（選択的Push）**:
  * ローカルの対局データのうち、`sync_target = 1` かつ `is_synced = 0` の対局レコード（および関連する参加者・局・局座席）のみをオンラインへ送信する。
  * 送信完了後、ローカル側の `is_synced` を 1 に更新する。
  * `sync_target = 0`（ローカル限定）の対局は、オンラインへ一切送信されず、ローカル端末内にのみ保存される。

### 6.4 ユーザー操作フロー（対局開始時 & データ管理画面）
1. **対局開始時（`views/setup.py`）**:
   * 対局設定画面に、以下のチェックボックスを配置する：
     * `[✓] この対局をオンラインにも同期する`（デフォルト: チェックON）
   * ローカル限定でプレイしたい対局（テストや非公開対局等）の場合は、チェックを外すことで `sync_target = 0` として記録される。
2. **データ管理画面（`views/data_manage.py`）**:
   * 「データ同期」タブを設置し、以下の情報を可視化・操作可能とする：
     * 「オンラインへ未送信の対象対局: X件」
     * 「ローカル限定対局: Y件」
     * 「オンラインから未取得の対局: Z件」
   * **「同期を実行」ボタン**: ワンクリックで「マスタ同期」→「対局Pull（全件）」→「対局Push（選択分）」を一括アトミックに実行する。
   * また、対局一覧から後から個別に `sync_target`（同期対象／ローカル限定）を切り替えることも可能とする。

### 6.5 コンフリクトフリーとバックアップ保護仕様
* **対局データはイミュータブル（追記保存）**:
  * 本アプリでは確定保存された過去の対局内容を編集する仕様は存在しないため、同一対局の同時編集によるデータ競合は構造的に発生しない。
* **削除時のオンライン保護（バックアップ原則）**:
  * **ローカルでの削除はオンラインに波及させない**: 端末の初期化、データ破損、誤操作によるローカル対局削除が発生しても、オンライン上の対局データは絶対に消去せずバックアップとして保護する。
  * **バックアップからの安全復元（リストア）**: ローカルで消失・削除された対局は、次回同期時の「オンラインからのPull」によってオンラインから安全にローカルへ再取得・復元できる。
  * **完全抹消（例外操作）**: 誤登録などでオンラインからも完全に削除したい場合は、データ管理画面等で明示的に「オンラインのバックアップも完全消去する」と二重確認された場合のみ実行する。


