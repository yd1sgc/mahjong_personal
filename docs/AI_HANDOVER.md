# Directory Structure Map

- `app.py`: Streamlit アプリケーションのエントリーポイント
- `local_mahjong_v2_new.db`: 現行の本番SQLiteデータベース（正本）
- `src/`: アプリケーションのコアロジック（DB操作、計算、UIビュー）
- `tests/`: 自動テストスイート（テスト実行は `python tests/run_tests.py`）
- `scripts/`: 日常のデータ保守・バックアップ・同期運用スクリプト群
- `migrations/`: 本番・リモート向けDBスキーマ定義SQL
- `docs/`: システム設計・引継・仕様書
- `archive/`: 過去の不要なスクリプトや一時データ、過去DBの退避先（**AI探索・読込不要**）
  - `archive/db/`: 移行中間段階の過去DB
  - `archive/debug/`: 過去の調査ダンプ・一時ファイル
  - `archive/scratch/`: 過去の検証・分析スクリプト
  - `archive/scripts/`: 完了済み単発マイグレーションスクリプト
- `.gemini/`: AIエージェント設定（プロジェクト固有ルールとフック定義）

# AI Agent Testing & Safety Protocol (必読)
1. **コード変更後の全テスト実行義務**:
   - 変更を加えた後は、必ず `.venv\Scripts\python.exe tests/run_tests.py`（または `python tests/run_tests.py`）を実行し、全件 PASS することを確認すること。
2. **対局中断・セッション喪失対策（最重要）**:
   - 対局中の全アクション（和了、流局、リーチ、副露、Undo、履歴修正）は、すべて直ちにドラフト保存（`autosave_draft`）をトリガーすること。
   - ドラフト保存時は、再開時に画面が固まらないよう常に `view="game"`, `input_mode="normal"` で保存すること。
   - `tests/test_interruption_recovery.py` がこれらを自動検証しているため、対局状態や画面遷移を変更した際は本テストを絶対に落とさないこと。

# Current Status
- 新DB構造（第3正規形・UUID v7・完全縦持ち）への移行ブランチ `feature/app-v2-migration` を作成し、全5フェーズの移行が完全完了。
- **Phase 1 完了**: `src/database2.py` の新スキーマ専用リファクタリング・不可分トランザクション化完了（コミット: `0b5831d`）。
- **Phase 2 完了**: 対局進行・保存層のハードコード完全撤廃と不可分トランザクション保存APIへの一本化完了（コミット: `f16d23a`）。
- **Phase 3 完了**: 成績集計層（`src/views/stats.py`, `src/calc.py`）のスパゲッティコード（約250行）全廃、正規化SQL集計（`get_game_stats_summary`, `get_round_stats_summary`, `get_results_data`）およびUUID完全対応完了（コミット: `8437e06`）。
- **Phase 4 完了**: 分散ハイブリッド同期エンジン（マスタ完全同一・対局選択的Push・全件Pull・オンラインバックアップ保護）の実装、対局開始時の同期チェックボックス設置、データ管理UI刷新、全テスト刷新により `python tests/run_tests.py` の **全38件 PASS（0 failed）** を達成（コミット: `631926d`）。
- **Phase 5 完了**: リモートDB（Supabase PostgreSQL）向け追従マイグレーションSQL（`migrations/supabase_migration_v2.sql`）の策定完了。

# TODO (Next Actions)
- [x] ローカルDB（local_mahjong_v2_new.db）への役満記録テーブル（yakuman_records）追加および検証
  - [x] yakuman_records テーブルおよび3種インデックスの作成（第3正規形準拠）
  - [x] src/database2.py の init_local_db() への DDL 追記
  - [x] 過去の実績対局5件（ルイ:緑一色、リョウト:大三元×2、マサキ:四暗刻、オッチャン:大三元）の特定および本番登録
  - [x] 全テスト（tests/run_tests.py）の実行確認（63 passed, 0 failed）
- [ ] 役満記録機能のUIおよび集計ロジック実装（対局詳細表示・個人通算役満スタッツ）
- [ ] リモートDB（Supabase）への yakuman_records マイグレーション適用
- [x] ローカルDBのルールテンプレートをオンラインDB（Supabase）の7件および詳細設定に完全一致化
  - [x] 不要な5件のローカル独自ルールの削除
  - [x] オンライン側7件（詳細設定・レート換算・補足メモ含む）の一括インポート・Upsert
  - [x] 全テスト（tests/run_tests.py）の実行確認（63 passed, 0 failed）
- [x] ローカルDBおよびオンラインDBの同期整合性・二重記録（重複試合）調査
  - [x] ローカルDB（local_mahjong_v2_new.db）内の重複試合（同一日時・参加者・素点）の検出（重複0件確認）
  - [x] ローカルDB内の最新ルール一覧の確認（ローカル11件、リモート7件を検出）
  - [x] オンラインDB（Supabase）とのゲームID体系・未同期状態の照合（ID不一致重複0件、全27件完全一致、全ID UUID v7統一を確認）
- [x] AI段階的開示（Progressive Disclosure）向けドキュメント整備
  - [x] `src/README.md` のタイポ修正とV2モジュール責務の明記
  - [x] `scripts/README.md` の残存運用スクリプト全件網羅
  - [x] `archive/README.md` の新設（AI探索不要宣言と分類マップ）
  - [x] `README.md`（ルート）の拡充（システム概要、起動、テスト、フォルダー構造）
  - [x] `tests/run_tests.py` の実行確認（全件PASS）
- [x] 大規模開発終了に伴うフォルダー整理と最新DBバックアップ
  - [x] 最新本番DB（local_mahjong_v2_new.db）および旧V1バックアップを OneDrive (C:\Users\segu1\OneDrive\mahjong_personal\麻雀バックアップ) へコピー退避
  - [x] 0バイト空DB（local_mahjong.db, mahjong_local.db, src/local_mahjong.db）およびキャッシュの削除
  - [x] 過去中間DB（local_mahjong_v2.db, local_mahjong_v2_fixed.db, local_mahjong_v2_new.db.bak）を archive/db/ へ移動
  - [x] 一時ファイル・調査データ（game_257_data.json, memberships.txt, check_remote.py）を archive/debug/ へ移動
  - [x] scratch/ 配下の検証ファイル群を archive/scratch/ へ移動
  - [x] scripts/ 配下の単発移行スクリプトを archive/scripts/ へ移動
  - [x] tests/run_tests.py の実行確認（全件PASS）

# Changelog (Recent History)
- 2026-09-17: ローカルDB（local_mahjong_v2_new.db）へ第3正規形準拠の新テーブル `yakuman_records` および3種の外部キーインデックスを作成。過去の役満対局5件（2024-01-04 ルイ:緑一色、2025-01-01 リョウト:大三元、2025-01-02 マサキ:四暗刻、2025-01-05 リョウト:大三元、2026-09-05 オッチャン:大三元[東2局3本場]）を特定し、正式にレコード登録を完了。全63件の自動テスト（tests/run_tests.py）が ALL PASS することを確認。
- 2026-09-13: オンラインDB（Supabase）の最新ルール7件（麻雀部v4、親族麻雀v4、連盟公式、Mリーグ等）および詳細設定（本場点・立直棒・ノーテン罰符・ダブロン・途中流局・レート換算・ハウスルール補足メモ等）をローカルDB（local_mahjong_v2_new.db）へ不可分反映。ローカル独自だった未同期5件を安全に削除し、ローカルとオンラインのルールテンプレート構成を完全一致させた。全63件の自動テスト（tests/run_tests.py）が ALL PASS することを確認。
- 2026-09-13: ローカルDB（local_mahjong_v2_new.db）およびオンラインDB（Supabase）の同期状態・二重記録・ルールの調査を実施。(1) ローカルDB内276試合の対局日時・参加者・素点照合により、重複登録（二重記録）は0件であることを確認。(2) ゲームIDはローカル・リモート共に旧整数IDは全廃されており、全件UUID v7に統一済み。(3) オンライン登録済みの27試合はローカルの同期済み27試合とUUID・内容ともに完全一致しており、IDズレによる二重記録は発生していない。(4) ルールテンプレートはローカル11件、リモート7件を検出。未同期のルール5件（一般10-30、ゴットー (5-10)、ノーウマ・オカなし、一般アリアリ（ゴットー）、最高位戦日本プロ麻雀協会）は全体同期実行により安全にUpsert同期可能であることを確認。
- 2026-09-09: データ管理および過去対局の局修正機能を新V2正規化スキーマ（UUID v7・`round_seats` 縦持ち）に完全追従・刷新。全テスト数を全58件から全63件（0 failed）へ拡充。(1) `src/database2.py`: 局修正用不可分置換API（`update_game_record_atomic`）、基本情報不可分更新API（`update_game_basic_info`）、CSV取込時のUUID自動解決およびウマオカpt自動算出（`import_games_from_df`）、局詳細CSV出力（`load_all_rounds` -> `get_rounds_data`）、DB更新直前の自動物理スナップショット退避（`backup_local_db_snapshot`）、およびオンラインへの不可分上書きPush（`push_games_to_remote`）を実装。(2) `src/views/round_edit.py`: UUID対応、ダブロン（複数和了）の入力・復元・連鎖再計算対応、10万点ゼロサム検証および差分プレビュー表示を実装。(3) `src/views/data_manage.py`: 局修正および基本情報編集UIの正式統合、オンライン環境（`IS_LOCAL == False`）における編集操作制限と案内メッセージ設置。(4) `tests/`: 局修正ダブロン再計算、CSV取込UUID解決、局詳細エクスポート、基本情報不可分更新の単体・統合テストを追加し全63件 ALL PASS を確認。
- 2026-09-09: 点数計算・対局進行・統計集計のエッジケースおよび不変量テストを徹底補強し、テスト数を全43件から全58件（0 failed）へ拡充。(1) `tests/test_calc.py` に端数切り上げツモ（40符の700/1300、400/700、1300オール）、七対子25符（400/800、1600、2400）、高符（50符）、および切り上げ満貫境界（4翻30符・3翻60符が原則通り7700点/11600点、4翻40符が満貫8000点/12000点）の検証テストを追加。(2) `tests/test_game_logic.py` に0点ちょうどのトビ境界テスト（0点未満終了ルールでの続行確認、0点以下終了ルールでのトビ確認）、および連続対局進行における点棒の10万点ゼロサム不変量テスト（`test_zero_sum_score_conservation_invariant`）を追加。(3) `tests/test_stats_and_transactions.py` にデータ空・和了0・放銃0時のゼロ除算耐性テスト（`test_zero_division_and_empty_stats_safety`）を追加。tests/run_tests.py 全58件 ALL PASS を確認。
- 2026-09-09: テストスイートの欠落・死蔵を解消し、テスト数を全38件から全43件へ拡充。(1) pytest fixture 依存で死蔵されていた `tests/test_database2.py` をスタンドアロン関数形式へ改修し現行V2スキーマ対応。(2) 新規 `tests/test_stats_and_transactions.py` を新設し、不可分保存トランザクション・ドラフト確実消去、半荘成績SQL集計、局スタッツSQL集計、およびグループ・ゲスト絞り込みフィルターの検証テストを追加。(3) `tests/run_tests.py` に両テストを統合し、全43件 ALL PASS（0 failed）を達成。
- 2026-09-08: AIエージェント段階的開示（Progressive Disclosure）向けドキュメント体系を再整備。(1) `src/README.md` のタイポを修正しV2スキーマ対応各モジュールの責務を明確化。(2) `scripts/README.md` に残存運用スクリプト5件（safety_hook, backup, check, sync等）の仕様・実行方法を網羅。(3) `archive/README.md` を新設し「AI探索不要」の原則と隔離内容を明記。(4) ルートの `README.md` を1行から正式ドキュメント（起動手順・テスト・全体マップ・開発ガイドライン）へ全面拡充。(5) `docs/AI_HANDOVER.md` の Directory Structure Map を最新のフォルダー構成に更新。tests/run_tests.py 全38件 ALL PASS を確認。
- 2026-09-08: 大規模開発（V2移行・同期エンジン・UI/グラフ最適化）完了に伴うフォルダー構造の整理および最新DBバックアップを実施。(1) 最新のローカル本番DB（local_mahjong_v2_new.db: 868KB）および旧V1バックアップを OneDrive (C:\Users\segu1\OneDrive\mahjong_personal\麻雀バックアップ\) へ安全にコピー退避。(2) 0バイト空DB（local_mahjong.db, mahjong_local.db, src/local_mahjong.db）および一時キャッシュの完全破棄。(3) 過去中間DB（archive/db/）、デバッグ用データ・スクリプト（archive/debug/）、検証ファイル群（archive/scratch/）、単発移行スクリプト群（archive/scripts/）を archive/ 配下に系統的に隔離・分類。scripts/ には日常運用スクリプト（safety_hook, backup, sync, check等）のみを保持。全38件のテスト（tests/run_tests.py）が ALL PASS することを確認。
- 2026-09-08: オンラインDB（PostgreSQL）で NUMERIC カラムが Decimal 型として返されることに起因する2つの不具合を修正。(1) 総合ポイント推移グラフで `Decimal is not JSON serializable` による描画破撻を解消するため、`database2.py` の `_fetch_df` および `get_results_data`、`stats.py` のチャート生成処理で `float` キャストを一貫して保証。(2) 相性マトリクスでデータ型不一致により `background_gradient` の着色が完全に無効化されていた問題を解消し、初期表示メンバーを五十音順から対戦数（試合数）上位5名に変更、0pt差を白とする正負対称カラーバー（`vmin=-max_abs, vmax=max_abs`）を適用。tests/run_tests.py 全38件 ALL PASS を確認。
- 2026-09-07: Supabase本番DBへ V2 スキーマ（UUID v7・完全縦持ち）を適用。旧全9テーブル（479レコード）をローカルに完全バックアップ（archive/supabase_v1_backup.json）後、オンラインに存在していた27件のみを選択的Push同期し、ローカルの249件はローカル限定として保護。app.py の参照DBパス修正および成績画面での未同期データ表示クラッシュを修正。tests/run_tests.py 全38件 ALL PASS を確認。
- 2026-09-07: 新DB構造（local_mahjong_v2_new.db）対応ブランチ `feature/app-v2-migration` を作成し、アプリ全面刷新仕様書 `docs/APPLICATION_V2_SPECIFICATION.md` を策定。
- 2026-09-05: 対局進行中にドラフト自動保存が呼ばれずデータ消失する不具合を修正。全アクション（リーチ・副露・和了・流局・チョンボ・Undo・修正）での保存トリガー、およびドラフト復元時の `normal` 画面固定・カスタムルール保持を実装。対局中断復元テスト（`tests/test_interruption_recovery.py`）を新設。
- 2026-08-25: AIエージェント用のプロジェクト固有ルール（`.gemini/rules/user_global.md`）の動作緩和と、重要操作の強制確認フック（`.gemini/hooks.json`, `scripts/safety_hook.py`）を導入。
- 2026-08-25: テスト用のgame_id 15を削除し、本番データ(元16)を15に繰り上げるDBメンテナンス（Supabase側）を実施。
- 2026-08-25: ファイルを src, tests, scripts, archive に分離整理。AI用の誘導仕組みを導入。
- 2026-08-25: UIの親番表示（★マーク）追加、西場サドンデス判定のメッセージ修正、ダブロン（multi_ron）時の距離計算バグを修正。過去データ（ゲームID 2〜15）の適用ルールを最新の親族麻雀ルール（アガリやめなし・飛びなし等）に統一するDB更新を実施。
- 2026-08-25: 対局画面（game.py）のUI操作ラグを解消するため、主要ボタンの処理を st.rerun() から on_click コールバック方式へ全面最適化。また、起動用batに MAHJONG_FORCE_LOCAL 環境変数を追加し、本番データと分離した安全なローカルDB開発環境を確立。