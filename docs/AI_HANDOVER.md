# Directory Structure Map

- src/: アプリケーションのコアロジック（DB操作、計算、UIビュー）
- 	ests/: テストコード
- scripts/: DBマイグレーションなどの運用スクリプト
- archive/: 過去の不要なスクリプトや一時データ（探索・読込不要）
- .gemini/: AIエージェント設定（プロジェクト固有ルールとフック定義）

# Current Status
- プロジェクトのディレクトリ構造再編（AI段階的開示対応）を実施完了。

# TODO (Next Actions)
- [ ] 今後タスクが発生した場合はここに記述する

# Changelog (Recent History)
- 2026-08-25: AIエージェント用のプロジェクト固有ルール（`.gemini/rules/user_global.md`）の動作緩和と、重要操作の強制確認フック（`.gemini/hooks.json`, `scripts/safety_hook.py`）を導入。
- 2026-08-25: テスト用のgame_id 15を削除し、本番データ(元16)を15に繰り上げるDBメンテナンス（Supabase側）を実施。
- 2026-08-25: ファイルを src, tests, scripts, archive に分離整理。AI用の誘導仕組みを導入。

- 2026-08-25: UIの親番表示（★マーク）追加、西場サドンデス判定のメッセージ修正、ダブロン（multi_ron）時の距離計算バグを修正。過去データ（ゲームID 2〜15）の適用ルールを最新の親族麻雀ルール（アガリやめなし・飛びなし等）に統一するDB更新を実施。
- 2026-08-25: 対局画面（game.py）のUI操作ラグを解消するため、主要ボタンの処理を st.rerun() から on_click コールバック方式へ全面最適化。また、起動用batに MAHJONG_FORCE_LOCAL 環境変数を追加し、本番データと分離した安全なローカルDB開発環境を確立。