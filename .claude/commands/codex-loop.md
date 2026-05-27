---
description: PR 作成後に @codex review を投稿し、Codex Cloud のレビューが付くまで待機 → 指摘を反映 → 再依頼を「指摘 0 件」まで自走で繰り返す
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# /codex-loop

`gh pr create` 直後に呼ぶ自走ループコマンド。
**ユーザーから「Codex 指摘を修正して」と再指示を待たず**、Claude 側が以下を「指摘 0 件 / クリーン文言」到達まで繰り返す:

```
@codex review 投稿
   ↓
待機（180〜240 秒）
   ↓
3 つの API から HEAD-SHA の Codex 出力を取得
   ↓
state 優先で判定
   ↓
指摘ありなら 修正 → ビルド確認 → コミット → push → ループ先頭へ
指摘なしなら 完了報告（何ラウンドで収束したか）
```

(運用パターンは [hang-up33/hmi-platform の codex-pr スキル](https://github.com/hang-up33/hmi-platform/blob/main/.claude/skills/codex-pr/SKILL.md) 手順 7 を meshforge 用に移植したもの)

## 引数

- `[PR番号]` — 省略時は `gh pr view --json number -q .number` から自動取得
- `[--once]` — 1 ラウンドだけ実行（修正 push まで。再依頼しない）

## 前提

- Codex Cloud / GitHub App が PR レビューを返す設定済み（meshforge は設定済）
- Codex bot login: `chatgpt-codex-connector[bot]`
- `gh` CLI 認証済み
- 現在ブランチに PR が立っている

## 実行手順

### 1. PR / リポジトリ情報を確定

```sh
PR="${ARG1:-$(gh pr view --json number -q .number)}"
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
[ -z "$PR" ] && echo "PR が無い。先に gh pr create してください" && exit 1
```

### 2. 初回トリガ: `@codex review` を投稿

```sh
gh pr comment "$PR" --body "@codex review"
```

**直後に基準値を確定**（待機後に取ると、待機中に Codex が投稿したクリーン文言を `?since=` で除外してしまい「シグナルなし」と誤判定して 30 分無反応扱いになる）:

```sh
# 実時刻を「1 秒戻して」確定する。GitHub の `?since=` 実装は境界時刻ちょうどの
# イベントを取りこぼすケースがあり、@codex review 投稿と同一秒に Codex の自動
# 応答が記録されると拾えない。1 秒戻し + クライアント側 select(.created_at >= SINCE)
# の二重防御で取りこぼしを防ぐ。macOS / Linux の date コマンド差を吸収。
SINCE=$(date -u -v-1S +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -d '1 second ago' +%Y-%m-%dT%H:%M:%SZ)
HEAD_SHA=$(git rev-parse HEAD)
```

### 3. 待機

```sh
sleep 180   # Codex は通常 1〜5 分でレビューを返す。指摘が多い PR では 240 まで延ばして可
```

長時間 sleep はフォアグラウンドで叩くと harness にブロックされるので、`run_in_background: true` で起動 + `Monitor` で待つ。

### 4. Codex 出力を 3 API から取得

Codex は指摘の有無で投稿先 API が変わる。**全部見る**。`--paginate` を必ず付ける（per_page=30 で先頭ページ以外を取りこぼし「指摘なし」と誤判定するリスク）。

```sh
# (1) reviews: 指摘ありの review summary。state / body を見る。commit_id で HEAD に絞る
gh api --paginate "repos/$REPO/pulls/$PR/reviews" \
  --jq ".[] | select(.user.login == \"chatgpt-codex-connector[bot]\") | select(.commit_id == \"$HEAD_SHA\") | {state, body}"

# (2) review comments: inline コメント本体。commit_id で HEAD に絞る
gh api --paginate "repos/$REPO/pulls/$PR/comments" \
  --jq ".[] | select(.user.login == \"chatgpt-codex-connector[bot]\") | select(.commit_id == \"$HEAD_SHA\") | {path, line, body}"

# (3) issue comments: PR 会話タブのコメント。Codex は指摘なしのとき
#     "Didn't find any major issues" をここに投稿することが多く、
#     reviews API にクリーン文言が載らないラウンドがあるため必ず併せて見る。
#     **commit_id を持たないので必ず時刻で絞る**。過去ラウンドのクリーン文言を
#     拾うと、最新 HEAD のレビュー未完了でもループ誤終了する。
#     `?since=` は GitHub 側で境界取りこぼしがあるため、SINCE は手順 2 で 1 秒
#     戻した値を使い、サーバー側 `?since=` + クライアント側 `select(.created_at >= SINCE)`
#     の二重防御で確実に拾う。
gh api --paginate "repos/$REPO/issues/$PR/comments?since=${SINCE}" \
  --jq ".[] | select(.user.login == \"chatgpt-codex-connector[bot]\") | select(.created_at >= \"$SINCE\") | {created_at, body}"
```

### 5. 判定（state 優先）

「badge / 文言の有無」だけで判断しない。本文に badge が付かない `CHANGES_REQUESTED` を取りこぼしてループが早期終了する事故が起きる。

優先順:

1. reviews `state == "CHANGES_REQUESTED"` → **無条件で** 修正フェーズ (6) へ
2. `state == "COMMENTED"` でも当該 HEAD-SHA の review comments（inline）が 1 件以上 → 修正フェーズ (6) へ
3. inline 0 件で reviews/inline 本文に `P0`〜`P3` / `Major` / `Minor` / `[Major]` / `[Minor]` 等の指摘 badge → 修正フェーズ (6) へ
4. 上のいずれにも該当せず、当該 HEAD 以降に issue comments / reviews のどちらかへ `Didn't find any major issues` 等のクリーン文言 → **ループ脱出して完了報告**
5. どのシグナルも出ていない（reviews / inline / issue comment 全部空） → Codex はまだレビュー中。手順 3 の待機に戻る（ループ脱出しない）

### 6. 修正フェーズ

[apply-pr-feedback](apply-pr-feedback.md) と同じ規約で指摘を分類:

- ✅ 採用: 今の Step で直す
- ⏸ 保留: 将来 Step → `docs/development-plan.md` の TODO 候補
- ❌ 却下: [AGENTS.md](../../AGENTS.md) の段階性ルール違反・過剰設計・事実誤認 → 理由を添える

採用するものについて修正計画を提示してユーザー承認 → Edit で修正 → 動作確認:

```sh
.venv/bin/python -m meshforge convert samples/dome.png /tmp/dome.stl  # 該当機能の動作確認
```

→ 修正ファイルを明示的に `git add` してコミット（1 指摘 = 1 コミット原則。関連小修正はまとめて可）:

```sh
git commit -m "fix: address codex review (<要約>)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### 7. push → サマリ → 再依頼

```sh
git push
gh pr comment "$PR" --body "<対応した指摘 / 保留 / 却下のサマリ>"
gh pr comment "$PR" --body "@codex review"
```

force push は使わない（追加コミットで対応）。

### 8. 基準値を再確定してループ先頭へ

**`SINCE` と `HEAD_SHA` を必ず再取得**してから手順 3 へ。再取得しないと旧ラウンドの値で判定して誤動作する:

```sh
SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
HEAD_SHA=$(git rev-parse HEAD)
```

`--once` フラグが指定されていればここで終了。

### 9. 完了報告

クリーン到達時、**何ラウンドで収束したか** を含めてユーザーに報告:

> Codex 指摘 N 件を M ラウンドで解消、最終レビュー：指摘なし
> PR: https://github.com/$REPO/pull/$PR

マージは従来通りユーザーが行う（Claude はマージしない）。

## 中断してユーザーに相談すべきケース

- 大規模な方針差し戻し（タスク分割要求、Step 計画外のフレームワーク導入提案 等）
- Codex が**同じ指摘を 3 回連続**で返してくる（修正が指摘の意図に合っていない可能性）
- ビルド / `.venv/bin/python -m meshforge convert ...` が通らないまま固着
- **30 分待っても Codex が無反応**（GitHub App 障害等の可能性 → ユーザー報告）

中断時は、現在の状態（直近の指摘 / 反映済みパッチ / 未反映分）をサマリして停止する。

## 重要

- Codex の指摘を **そのまま採用しない**。段階性ルール（[AGENTS.md](../../AGENTS.md)）に反するものは却下し、PR コメントで理由を返す
- ループ中の中間報告は不要（PR の commit 履歴で後から確認できる）
- `gh pr comment ... --body "$(cat <<EOF ... EOF)"` で unquoted HEREDOC を使わない（`$VAR` / `$(...)` / バッククォートが全展開される）。本文に変数を入れる場合は `'EOF'` quoted HEREDOC + `sed` 置換 → `--body-file` で渡す
- 待機 Bash は `run_in_background: true` + `Monitor` 受信。フォアグラウンドで Bash を長時間ブロックしない
