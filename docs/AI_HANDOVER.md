# Directory Structure Map

- src/: アプリケーションのコアロジック（DB操作、計算、UIビュー）
- tests/: テストコード（テスト実行は `python tests/run_tests.py`）
- scripts/: DBマイグレーションなどの運用スクリプト
- archive/: 過去の不要なスクリプトや一時データ（探索・読込不要）
- .gemini/: AIエージェント設定（プロジェクト固有ルールとフック定義）

# AI Agent Testing & Safety Protocol (必読)
1. **コード変更後の全テスト実行義務**:
   - 変更を加えた後は、必ず `.venv\Scripts\python.exe tests/run_tests.py`（または `python tests/run_tests.py`）を実行し、全件 PASS することを確認すること。
2. **対局中断・セッション喪失対策（最重要）**:
   - 対局中の全アクション（和了、流局、リーチ、副露、Undo、履歴修正）は、すべて直ちにドラフト保存（`autosave_draft`）をトリガーすること。
   - ドラフト保存時は、再開時に画面が固まらないよう常に `view="game"`, `input_mode="normal"` で保存すること。
   - `tests/test_interruption_recovery.py` がこれらを自動検証しているため、対局状態や画面遷移を変更した際は本テストを絶対に落とさないこと。

# Current Status
- 新DB構造（第3正規形・UUID v7・完全縦持ち）への移行ブランチ `feature/app-v2-migration` を作成。
- アプリケーション移行仕様書（`docs/APPLICATION_V2_SPECIFICATION.md`）策定完了。
- **Phase 1 完了**: `src/database2.py` の新スキーマ専用リファクタリング・不可分トランザクション化完了（コミット: `0b5831d`）。
- **Phase 2 完了**: 対局進行・保存層のハードコード完全撤廃と不可分トランザクション保存APIへの一本化完了（コミット: `f16d23a`）。
- **Phase 3 完了**: 成績集計層（`src/views/stats.py`, `src/calc.py`）のスパゲッティコード（約250行）全廃、正規化SQL集計（`get_game_stats_summary`, `get_round_stats_summary`, `get_results_data`）およびUUID完全対応完了。276対局実データに対する回帰テストPASS。

# TODO (Next Actions)
- [x] Phase 1: `src/database2.py` を新DB構造（UUID v7、`games`・`game_participants`・`rounds`・`round_seats`）専用に刷新
- [x] Phase 2: `src/game_logic.py` および対局画面（`src/views/game.py`, `src/views/setup.py`）のハードコード撤廃、`round_seats` 生成・新保存API連携
- [x] Phase 3: `src/views/stats.py` の集計ロジックを正規化SQLクエリへ全面置換
- [ ] Phase 4: `tests/test_identity_schema.py` などの古いマイグレーションテストを新V2スキーマテストへ刷新し、`tests/run_tests.py` 全件を 0 failed にする
- [ ] Phase 5: リモートDB（Supabase）向けの追従マイグレーション実施



# Changelog (Recent History)
- 2026-09-07: 新DB構造（local_mahjong_v2_new.db）対応ブランチ `feature/app-v2-migration` を作成し、アプリ全面刷新仕様書 `docs/APPLICATION_V2_SPECIFICATION.md` を策定。
- 2026-09-05: 対局進行中にドラフト自動保存が呼ばれずデータ消失する不具合を修正。全アクション（リーチ・副露・和了・流局・チョンボ・Undo・修正）での保存トリガー、およびドラフト復元時の `normal` 画面固定・カスタムルール保持を実装。対局中断復元テスト（`tests/test_interruption_recovery.py`）を新設。
- 2026-08-25: AIエージェント用のプロジェクト固有ルール（`.gemini/rules/user_global.md`）の動作緩和と、重要操作の強制確認フック（`.gemini/hooks.json`, `scripts/safety_hook.py`）を導入。
- 2026-08-25: テスト用のgame_id 15を削除し、本番データ(元16)を15に繰り上げるDBメンテナンス（Supabase側）を実施。
- 2026-08-25: ファイルを src, tests, scripts, archive に分離整理。AI用の誘導仕組みを導入。
- 2026-08-25: UIの親番表示（★マーク）追加、西場サドンデス判定のメッセージ修正、ダブロン（multi_ron）時の距離計算バグを修正。過去データ（ゲームID 2〜15）の適用ルールを最新の親族麻雀ルール（アガリやめなし・飛びなし等）に統一するDB更新を実施。
- 2026-08-25: 対局画面（game.py）のUI操作ラグを解消するため、主要ボタンの処理を st.rerun() から on_click コールバック方式へ全面最適化。また、起動用batに MAHJONG_FORCE_LOCAL 環境変数を追加し、本番データと分離した安全なローカルDB開発環境を確立。