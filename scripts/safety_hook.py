import sys
import json
import re

def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        # 入力エラー時はブロックしない
        print(json.dumps({"decision": "allow"}))
        return

    tool_name = input_data.get("toolCall", {}).get("name", "")
    args = input_data.get("toolCall", {}).get("args", {})
    decision, reason = "allow", ""

    if tool_name == "run_command":
        cmd = args.get("CommandLine", "").lower()
        # リモートGit操作の検知
        if re.search(r"git\s+(push|pull|merge|fetch|rebase)", cmd):
            decision, reason = "force_ask", "リモートリポジトリに影響を与えるGit操作はユーザーの許可が必要です。"
        # DB関連・Supabase操作の検知
        elif "supabase" in cmd or "psql" in cmd:
            decision, reason = "force_ask", "データベースへの直接操作はユーザーの許可が必要です。"

    elif tool_name in ["replace_file_content", "write_to_file"]:
        filepath = args.get("TargetFile", "").replace("\\", "/").lower()
        # 重要な設定・マイグレーションの検知
        if any(x in filepath for x in ["/migrations/", "/.env", "/secrets.toml"]):
            decision, reason = "force_ask", "DBマイグレーションや機密設定ファイルの編集はユーザーの許可が必要です。"
        # アプリケーションソースコードの直接編集前のドキュメント更新チェック
        elif ".gemini" not in filepath and "docs/ai_handover.md" not in filepath:
            import os
            import time
            handover_path = "docs/AI_HANDOVER.md"
            if not os.path.exists(handover_path):
                decision, reason = "deny", "エラー: docs/AI_HANDOVER.md が見つかりません。コードを変更する前に、必ずこのファイルを作成/更新して作業計画を記述してください。"
            else:
                mtime = os.path.getmtime(handover_path)
                current_time = time.time()
                # 60分以内に更新されていなければブロック
                if current_time - mtime > 3600:
                    decision, reason = "deny", "エラー: docs/AI_HANDOVER.md が古いです。コードを変更する前に、必ずファイルを読んで最新の計画と状況を追記し、ユーザーの許可を得てください。"
                else:
                    decision, reason = "allow", ""

    print(json.dumps({"decision": decision, "reason": reason}))

if __name__ == "__main__":
    main()
