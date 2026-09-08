# scripts（運用・保守スクリプト）

データベースのバックアップ、オンライン同期、データ復旧、およびAIエージェントの安全監視を行う日常運用スクリプト群です。
※一時的な移行・修復スクリプトはすべて `archive/scripts/` へ隔離済みです。

## 運用スクリプト一覧

| スクリプト名 | 機能と用途 | 実行方法 |
| :--- | :--- | :--- |
| **`safety_hook.py`** | **AIエージェント用安全ガード（PreToolUseフック）**<br>`.gemini/hooks.json` から自動呼出。危険なGit操作（push等）、DB直接変更、重要設定編集を検知して強制確認を要求し、`docs/AI_HANDOVER.md` の未更新をブロック。 | 自動実行（ツール呼出時） |
| **`backup_supabase.py`** | **リモートDB（Supabase）バックアップ**<br>オンライン上の全テーブルデータをJSON形式でローカルに取得・保存。 | `python scripts/backup_supabase.py` |
| **`check_online.py`** | **オンラインDB疎通・整合性チェック**<br>Supabaseへの接続可否、テーブル存在確認、ローカルとの基本接続状況を診断。 | `python scripts/check_online.py` |
| **`find_unsynced_games.py`** | **未同期対局検出ツール**<br>ローカルとオンラインでID体系が異なる場合でも、対局日時・参加者・素点の完全一致を利用してオンライン未登録のゲームを特定。 | `python scripts/find_unsynced_games.py` |
| **`upload_specific_games.py`** | **特定ゲームの安全直接アップロード（Upsert）**<br>指定した `game_id` の対局データ（および依存するグループ・ルール・参加者・局データ）を完全不可分にSupabaseへ反映。 | `python scripts/upload_specific_games.py` |

