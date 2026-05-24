---
description: PR コメントまたは Codex レビューファイルを読んで修正案を提示し、承認後に同じブランチへ追加コミット
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# /apply-pr-feedback

レビュー指摘（GitHub PR コメント or `.codex/reviews/*.md`）を取り込んで、現在ブランチに修正を入れます。

## 入力ソース（引数で指定 or 自動判定）

- `pr <番号>` → `gh pr view <番号> --comments` と `gh api repos/{owner}/{repo}/pulls/<番号>/comments` で取得
- `file <path>` → そのファイルを Read
- 引数なし → `.codex/reviews/` の最新ファイルを使用

## 実行手順

1. **指摘を取得して列挙**: 1つずつ番号を付け、どこ（ファイル:行）に対する指摘か明示
2. **各指摘の分類**:
   - ✅ 採用: 今の Step で直す
   - ⏸ 保留: 将来 Step の話 → `docs/development-plan.md` に TODO 追記候補
   - ❌ 却下: 段階性違反 / 過剰設計 / 事実誤認 → 理由を添える
3. **採用する指摘の修正計画を提示** してユーザー確認を取る
4. **承認後**: Edit で各箇所を修正 → 動作確認 → 同じブランチに追加コミット
   - コミットメッセージ例: `fix: address codex review (watertight check, off-by-one)`
   - 1 指摘 = 1 コミット を原則とするが、関連する小さな修正はまとめて可
5. **コミット後**: `git push` し、PR コメントに「対応した指摘 / 保留した指摘 / 却下した指摘」のサマリを `gh pr comment` で投稿

## 重要

- レビュアが Codex でも GitHub コメントでも、**Claude は全部鵜呑みにしない**
- 段階性ルール（AGENTS.md）に反する指摘は明示的に却下し、PR コメントで理由を返す
- 同じブランチに追加コミット（force push は使わない）
- 修正後はもう一度 `/codex-review` で確認 → ループ
