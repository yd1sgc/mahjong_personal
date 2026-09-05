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
- 対局中のドラフト自動保存脱落バグの修正、復元画面固定、および中断・復帰ライフサイクルテスト（全38件）の配備完了。

# TODO (Next Actions)
- [ ] 今後タスクが発生した場合はここに記述する

# Changelog (Recent History)
- 2026-09-05: 対局進行中にドラフト自動保存が呼ばれずデータ消失する不具合を修正。全アクション（リーチ・副露・和了・流局・チョンボ・Undo・修正）での保存トリガー、およびドラフト復元時の `normal` 画面固定・カスタムルール保持を実装。対局中断復元テスト（`tests/test_interruption_recovery.py`）を新設。
- 2026-08-25: AIエージェント用のプロジェクト固有ルール（`.gemini/rules/user_global.md`）の動作緩和と、重要操作の強制確認フック（`.gemini/hooks.json`, `scripts/safety_hook.py`）を導入。
- 2026-08-25: テスト用のgame_id 15を削除し、本番データ(元16)を15に繰り上げるDBメンテナンス（Supabase側）を実施。
- 2026-08-25: ファイルを src, tests, scripts, archive に分離整理。AI用の誘導仕組みを導入。
- 2026-08-25: UIの親番表示（★マーク）追加、西場サドンデス判定のメッセージ修正、ダブロン（multi_ron）時の距離計算バグを修正。過去データ（ゲームID 2〜15）の適用ルールを最新の親族麻雀ルール（アガリやめなし・飛びなし等）に統一するDB更新を実施。
- 2026-08-25: 対局画面（game.py）のUI操作ラグを解消するため、主要ボタンの処理を st.rerun() から on_click コールバック方式へ全面最適化。また、起動用batに MAHJONG_FORCE_LOCAL 環境変数を追加し、本番データと分離した安全なローカルDB開発環境を確立。