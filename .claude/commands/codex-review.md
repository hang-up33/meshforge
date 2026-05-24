---
description: 現在ブランチの差分を Codex reviewer エージェントに渡してレビューを取得
allowed-tools:
  - Bash
  - Read
---

# /codex-review

現在ブランチを `main`（または引数で指定したブランチ）と比較し、Codex の reviewer エージェントにレビューさせ、結果を `.codex/reviews/` に保存します。

## 実行手順

1. **base ブランチを決定**: 引数が無ければ `main`
2. **スクリプトを実行**: `scripts/codex-review.sh <base>`
   - codex CLI が無い場合はインストール案内が出る → ユーザーに知らせて停止
   - 差分が無い場合は何もせず終了
3. **出力ファイルを読む**: 標準出力に出たパスを Read する
4. **要約をユーザーに提示**:
   - Blocking issues（必ず直すべきもの）
   - Suggestions（任意）
   - Out of scope（今の Step では扱わない指摘）
   - そのままマージして良いか、修正が必要か、の判断
5. **次のアクションを提案**:
   - Blocking があれば `/apply-pr-feedback` でパッチを当てる
   - 無ければ PR を進めて良い

## 重要

- Codex の指摘を **そのまま採用しない**。各指摘について「今の Step で対応すべきか」を AGENTS.md の段階性ルールと照らして判断する
- Out of scope は将来 Step の TODO として `docs/development-plan.md` に追記候補とする
- 修正を入れる場合はレビューファイルの該当箇所を引用して、何をどう直すかをユーザーに見せてから着手
