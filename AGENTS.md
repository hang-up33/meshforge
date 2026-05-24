# AGENTS.md

このファイルは Claude Code と Codex（CLI / GitHub Cloud connector）の両方が読む、プロジェクト共通の規約。

## 出力言語

**すべての PR コメント、レビューコメント、コミットメッセージ、ユーザーへの返答は日本語で書くこと。** コード内コメントとログメッセージは英語のままで OK。
これはレビュアー（Codex）にも実装者（Claude）にも適用される。Codex Cloud のテンプレ部分（`💡 Codex Review` 見出し等）はコネクタ側でハードコードされているため翻訳できないが、本文（指摘内容、要約、提案）は日本語で出力すること。

## プロジェクト概要

meshforge は「PDF（仕様書 / 図面）→ 編集可能な 3D モデル → STL」を実現するツール。
最終形は Avalonia + C# + Python の3層構成だが、本リポジトリは **まず Python スクリプト 1 本で「PNG → STL」が動く** ところから段階的に積み上げる。

詳細:
- [README.md](README.md): プロジェクト概要・段階的計画サマリ・進捗
- [docs/development-plan.md](docs/development-plan.md): ステップ計画の正本

## 進め方ルール（最優先）

- **1 ステップ完了（動作確認できた）→ コミット → 次ステップ**
- 動かないうちに次のステップに進まない
- 抽象化・テスト・エラー処理は「必要になってから」入れる
- 計画を膨らませず、必要になったら都度追加
- ユーザー指示「一歩一歩着実に」を最優先

各ステップで **やらないこと** は README / development-plan.md に明記。

## 開発ループ（Claude 実装 → Codex レビュー → Claude 修正）

1. **Claude が実装**: ステップ単位で feature branch に変更を作る
2. **PR を作る**: `gh pr create` で main にマージ予定の PR を開く
3. **Codex がレビュー**:
   - ローカル: `scripts/codex-review.sh` → `.codex/reviews/review-*.md` に出力
   - もしくは GitHub 側で Codex が PR にコメント
4. **Claude が指摘を反映**:
   - ローカルレビューファイルか、`gh pr view <N> --comments` で取得
   - パッチを作って同じブランチに追加コミット
5. レビューが落ち着くまで 3〜4 を繰り返し → 承認 → マージ

スラッシュコマンド:
- `/codex-review` — 現在ブランチを Codex にレビューさせる
- `/apply-pr-feedback` — PR コメント / レビューファイルを読んで修正案を出す

## 環境

- Python 3.14 + venv (`.venv/`)
- 依存: `numpy`, `pillow`, `trimesh`（必要に応じて `PyMuPDF` を Step 3 で追加）
- 実行例: `.venv/bin/python python/heightmap_to_stl.py samples/dome.png samples/dome.stl`
- macOS / Homebrew Python では `pyexpat` の symbol 不一致があり、`brew install expat` 済みなら pip 用に `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib` を渡す。**スクリプト実行には不要**。

## コーディング規約

- 1 ファイルで完結する Step では分割しない（Step 5 でパッケージ化）
- 型ヒントは「読みやすくなる時だけ」入れる
- コメントは「なぜ」を書く。何をしているかは識別子で表現する
- ファイル末尾は改行で終わる
- 公開関数のドキュストリングは 1 行で十分（Step 5 まで）

## レビュー観点（Codex への期待）

- **正しさ**: 端の処理、numpy index 系のオフバイワン、watertight 性
- **STL の妥当性**: 三角形の向き、座標系、印刷時の単位
- **段階性違反**: そのステップで「やらないこと」に書かれた機能を勝手に足していないか
- **過剰設計**: クラス分割・例外設計・設定ファイル化など「まだ要らないもの」

スタイルだけの指摘は避ける。実害のあるバグ・退行・抜けのあるテストを優先。

## ファイル / ディレクトリ

```
meshforge/
├─ AGENTS.md                共通規約（このファイル）
├─ CLAUDE.md                Claude Code 向け薄いポインタ
├─ README.md                プロジェクト概要・進捗
├─ docs/development-plan.md ステップ計画（正本）
├─ python/                  実装コード
│   ├─ heightmap_to_stl.py  Step 1〜4 はこの 1 ファイル
│   └─ make_sample.py       動作確認用のサンプル PNG 生成
├─ samples/                 入力サンプル（PNG / PDF）。STL 出力は gitignore
├─ .codex/                  Codex CLI 設定（reviewer / explorer エージェント）
├─ .claude/commands/        Claude スラッシュコマンド
└─ scripts/                 開発ループ用シェルスクリプト
```
