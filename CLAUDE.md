# CLAUDE.md

このリポジトリで作業する Claude Code への指示は [AGENTS.md](AGENTS.md) を参照（Claude と Codex の両方が読む共通規約）。

要点（詳細は AGENTS.md）:
- 段階的計画（Step 1〜6）を守る。各ステップで「やらないこと」リスト遵守。
- 動作確認できたらコミット → 次ステップ。
- 開発ループは Claude 実装 → Codex レビュー → Claude 修正。スラッシュコマンドは `.claude/commands/` 参照。
- Python 実行は `.venv/bin/python`。
