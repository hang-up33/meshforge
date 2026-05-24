# .codex/AGENTS.md

Codex 専用の補足。共通規約は [../AGENTS.md](../AGENTS.md) を参照。

## 出力言語（最優先）

PR レビューコメントの本文、要約、提案、質問への返答 — **すべて日本語で書く**。
- コード内コメントとログ文字列だけ英語で OK。
- 見出しテンプレ（`💡 Codex Review` 等）はコネクタ側固定のため変更不要。
- コードの引用やシンボル名（`heightmap_to_mesh`, `np.arange` 等）は原文のまま。

例:
- ❌ "This introduces a systematic size shrink (e.g., 64 px becomes 31.5 mm)."
- ✅ 「64 px が 31.5 mm になり、印刷スケールが想定と乖離する」

## レビュー観点（reviewer エージェントへのリマインド）

優先度順:
1. 正しさ — numpy index のオフバイワン、三角形の向き、watertight
2. STL/3D プリント妥当性 — 単位（mm）、bounds、ベース厚、法線方向
3. 段階性違反 — 各 Step の「やらないこと」リスト（README.md / docs/development-plan.md）に反する追加機能
4. 抜けのあるテスト — 既に壊れたことのある箇所、非自明な不変条件にのみ要求

避けること:
- スタイルだけの指摘（実害があれば別）
- 現 Step が明示的に先送りしているエラー処理 / 抽象化 / docstring の要求
- 観測された害に紐づかない "ベストプラクティス" の押しつけ
