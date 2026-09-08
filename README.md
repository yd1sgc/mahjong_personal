# 麻雀スコア管理・分析システム（mahjong_personal）

4人麻雀の対局進行・リアルタイム入力、スコア計算、および詳細な個人・グループ成績集計・分析を行うStreamlitアプリケーションです。

---

## 1. アプリケーション起動

ローカル実行時は、プロジェクトルートの起動バッチを使用してください。

```cmd
起動.bat
```
※ `MAHJONG_FORCE_LOCAL=1` 環境変数が自動設定され、ローカルSQLite（`local_mahjong_v2_new.db`）を正本として安全に高速起動します。

---

## 2. 自動テストの実行

すべてのコード変更・リファクタリング後は、テストスイートを実行し全件PASSを確認してください。

```bash
# 仮想環境を使用する場合（推奨）
.venv\Scripts\python.exe tests/run_tests.py

# または
python tests/run_tests.py
```
※全38件の単体テスト、点数計算テスト、IDスキーマ検証、および対局中断・復元テスト（`test_interruption_recovery.py`）が一括実行されます。

---

## 3. ディレクトリ構成

```
mahjong_personal/
  ├── app.py                     # Streamlitアプリケーション・エントリーポイント
  ├── local_mahjong_v2_new.db    # 現行の本番SQLiteデータベース（正本・UUID v7対応）
  ├── DESIGN.md                  # システム詳細設計・次期Next.js移植仕様書
  ├── requirements.txt           # 実行依存パッケージ
  ├── 起動.bat                   # ローカルモード起動用バッチ
  │
  ├── src/                       # アプリケーションコア（database2, game_logic, calc, views/）
  │     └── README.md            # コアモジュールの責務定義
  ├── tests/                     # ユニットテスト・復元テスト群
  │     └── README.md            # テスト実行規約と各テスト解説
  ├── scripts/                   # 運用・保守・バックアップスクリプト
  │     └── README.md            # 運用ツールの使い方
  ├── migrations/                # 本番DBマイグレーションSQL（V1 / V2）
  ├── docs/                      # 開発ドキュメント
  │     ├── AI_HANDOVER.md       # AIエージェント向け引継・プロトコル統括書
  │     ├── APPLICATION_V2_SPECIFICATION.md # V2スキーマ・移行仕様書
  │     └── DATABASE_SPECIFICATION.md       # DBスキーマ定義書
  ├── archive/                   # 過去資産・中間DB退避先（※AI探索・読込不要）
  │     └── README.md            # アーカイブ構成解説
  ├── scratch/                   # 一時作業領域
  ├── .gemini/                   # AIエージェント共通ルール・安全フック設定
  └── .streamlit/                # Streamlit設定・secrets.toml（非公開情報）
```

---

## 4. AIエージェント・開発者向けガイドライン

- **引継書**: 作業前後に必ず [`docs/AI_HANDOVER.md`](docs/AI_HANDOVER.md) を確認・更新してください。
- **安全規約**: データベース直接変更やリモートGit操作は、事前にユーザーの許可を得る必要があります（[`.gemini/rules/user_global.md`](.gemini/rules/user_global.md) および [`scripts/safety_hook.py`](scripts/safety_hook.py) により監視）。