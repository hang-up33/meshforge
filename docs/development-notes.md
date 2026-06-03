# 開発メモ / 詳しい使い方 (development notes)

[README.md](../README.md) を初心者向けに簡潔に保つため、そこから外した
**上級者向けの使い方** と **開発者向けの情報**（計画・進捗・工数・開発ループ・
各ステップの方針など）をこのファイルにまとめています。

関連ドキュメント:
- [README.md](../README.md): プロジェクト概要・かんたんな使い方
- [docs/development-plan.md](development-plan.md): 段階的計画の正本
- [docs/progress.md](progress.md): タスク単位の歩み
- [AGENTS.md](../AGENTS.md): 開発エージェント（Claude / Codex）向けの共通規約
- [CONTRIBUTING.md](../CONTRIBUTING.md): 貢献の手引き
- [CHANGELOG.md](../CHANGELOG.md): 変更履歴

---

## 詳しい使い方

すべて `python -m meshforge convert ...` のサブコマンドで呼びます。基本的な
PNG / PDF → STL の手順は README を参照してください。ここではより細かい使い方を
扱います。

### JSON 設定で再現

CLI 引数の代わりに JSON で全パラメータを指定できる。`pixel_mm` /
`max_height_mm` / `base_mm` などジオメトリ定数も JSON で上書き可能なので、
「同じ JSON から同じ STL が再現できる」。

```sh
# 1. CLI で 1 回出力しつつ、その時の設定を JSON に保存
.venv/bin/python -m meshforge convert samples/floorplan.pdf samples/floorplan.stl \
    --invert --threshold 128 --dpi 150 --save-config samples/floorplan.json

# 2. 以降は JSON 1 枚で同じ STL を再生成できる
.venv/bin/python -m meshforge convert --config samples/floorplan.json
```

`--config` と CLI 引数を混ぜた場合は CLI 側が勝つ（`--invert` を JSON で
`true` にしている場合に CLI から無効化するには `--no-invert`）。`--config`
利用時の positional は「両方指定するか両方省略」のどちらか（片方だけだと
`input`/`output` のどちらを上書きしたいか曖昧になるためエラー）。

### 高さレイヤー（マルチバンド閾値, Step 11）

`layers` を JSON で指定すると、明度を複数バンドに分割し、バンドごとに
独立した高さの STL が出る。「外壁 10mm / 内壁 5mm / 開口 0mm」のような
階層構造を 1 枚の画像から取り出せる。`layers` 指定時は `threshold` と
排他（同時指定はエラー）、`max_height_mm` は無視される（`invert` は併用可）。

```sh
.venv/bin/python -m meshforge convert --config samples/multilayer.json
```

`samples/multilayer.json` は dome PNG から階段状の地形を出す 4 バンド例。
バンドは `max` 昇順で並べ、各バンドが `[前バンドの max, 自分の max]`
区間の明度をカバーする（最終バンドは clip により上限超を吸収）。
UI からの編集は次 Step 以降。

### building モードの追加依存

`rooms[]`（床スラブ）や `openings[]`（ドア / 窓のくり抜き）を使う場合は
追加ライブラリが要る。

```sh
.venv/bin/pip install -e '.[building]'   # rooms[] / openings くり抜き
.venv/bin/pip install -e '.[vision]'     # 画像から壁を自動抽出 (extract-walls)
```

中間 JSON のスキーマ仕様は [docs/building-schema.md](building-schema.md) が正本。

### 公開（Streamlit Community Cloud）

GitHub push で自動再デプロイされる、Streamlit 公式の無料ホスティング。
「Vercel 体験 + Streamlit 対応」を満たすので公開先として採用。

セットアップ手順:

1. https://share.streamlit.io にアクセスして GitHub でログイン
2. 「New app」→ 以下を指定:
   - Repository: `hang-up33/meshforge`
   - Branch: `main`
   - Main file path: `python/meshforge/ui_streamlit.py`
3. Deploy

`requirements.txt` はリポジトリ直下に `numpy` / `pillow` / `trimesh` /
`pymupdf` / `streamlit` / `streamlit-stl` を直接列挙している。
`.[pdf,ui]` を読ませる方が DRY だが、Streamlit Cloud が使う uv は
local path entry を reject し、`pyproject.toml` にフォールバックすると
Poetry が `python/meshforge` の src layout を解決できないため、直接
列挙が現実的な妥協。依存追加時は `pyproject.toml` と `requirements.txt`
の両方を更新する必要がある（詳細は [CONTRIBUTING.md](../CONTRIBUTING.md)）。

制約:

- 7 日間アクセスがないと app が sleep する（次回アクセス時に 20〜40 秒で再起動）
- メモリ 1GB / 共有 CPU（meshforge の変換は数秒なので問題なし）
- app は public（誰でも URL で到達可能）— OSS 公開の前提

将来 Avalonia 移行や別ホスト（Hugging Face Spaces, Fly.io 等）に
切り替える場合も、コアは Python パッケージのままなので影響範囲は
UI 層と `requirements.txt` だけ。

---

## 段階的計画（サマリ）

| Step | 成果物 | パイプラインのどこ | 完了条件 |
| --- | --- | --- | --- |
| 1 | `python/heightmap_to_stl.py`（1ファイル） | 画像 → STL（編集なし） | コマンド1発で PNG → STL |
| 2 | Step 1 に `--invert` / `--threshold` を追加 | 画像 → STL（最低限の制御） | 建築ジオラマ STL がスライサで開ける |
| 3 | PDF 入力対応（PyMuPDF でラスタライズ） | **PDF → STL** がつながる | 建築平面図 PDF から STL が出る |
| 4 | `config.json` で全パラメータ指定 | **編集可能 3D の中間表現** が JSON で確立 | JSON 1 ファイルでビルド再現可能 |
| 5 | `python/meshforge/` パッケージ化 + サブコマンド | UI から呼び出せる土台 | `python -m meshforge convert config.json` |
| 6 | UI 層（Avalonia か簡易 GUI かを再判断） | **編集可能 3D を GUI で触る** | Step 5 完了後に改めて計画 |

Step 4 が「編集可能」の核 — ここで作る JSON が中間 3D モデルの仕様になり、
Step 6 の GUI はこの JSON を読み書きする UI として実装される。

Step 11 で「編集可能 3D」の最初の一歩として、明度バンドごとに高さを指定できる
`layers` を JSON 設定に追加（CLI 経由のみ）。UI 拡張・領域単位編集・複数入力・
デモ GIF 差し込みは Step 12 以降の構想。

詳細は [docs/development-plan.md](development-plan.md) を参照（こちらが正）。

## 進捗（詳細）

| # | タスク | 状態 |
| --- | --- | --- |
| 1 | 最小スクリプト「PNG → STL」 | ✅ 完了（Step 5 で `python/meshforge/` パッケージに統合） |
| 2 | `--invert` / `--threshold` 追加 | ✅ 完了（建築ジオラマ用） |
| 3 | PDF 入力対応 | ✅ 完了（PyMuPDF で 1 ページ目をラスタライズ） |
| 4 | 設定の JSON 化 | ✅ 完了（`--config` / `--save-config`、ジオメトリ定数も JSON 化） |
| 5 | Python パッケージ化 | ✅ 完了（`python -m meshforge convert ...`、heightmap/mesh/stl/cli に分離） |
| 6 | GUI（Streamlit 簡易 UI） | ✅ 完了（`streamlit run python/meshforge/ui_streamlit.py`、C# 移行は将来） |
| 7 | 3D プレビュー（streamlit-stl） | ✅ 完了（Convert 後にブラウザで STL を回転 / ズーム可能） |
| 8 | パラメータプリセット UI | ✅ 完了（Floor plan / Logo / Terrain / Custom を selectbox で切替、form 値に反映） |
| 9 | UI のエラー処理強化 | ✅ 完了（PyMuPDF 不在 / 壊れた PDF / 巨大ファイル / DPI 上限を `st.error` で日本語表示） |
| 10 | OSS リリース整備 | ✅ 完了（LICENSE / CONTRIBUTING / CHANGELOG / README に Demo セクション追加） |
| 11 | 高さレイヤー（マルチバンド閾値） | ✅ 完了（`layers` を JSON で指定、明度バンドごとに独立した高さの STL を生成。`samples/multilayer.json` 参照） |
| 12-1 | `--mode building` 骨格 + 中間 JSON スキーマ仕様 | ✅ 完了（`docs/building-schema.md` 正本、`run_building` は NotImplementedError） |
| 12-2 | 手書き JSON `walls[]` → 壁 STL | ✅ 完了（`samples/building_minimal.json` で 80×60×24 mm の壁箱が出る） |
| 12-3 | 手書き JSON `rooms[]` → 床スラブ | ✅ 完了（`samples/building_with_floor.json` で 2 部屋ぶんの床を壁の中に敷ける。`pip install -e '.[building]'` で shapely + mapbox_earcut が要る） |
| 12-4 | 手書き JSON `openings[]` → 壁にドア / 窓のくり抜き | ✅ 完了（`samples/building_with_door.json` で 4 本壁にドア 1 + 窓 1 を boolean で開ける。`pip install -e '.[building]'` で manifold3d が要る） |
| 12-5 | `roof` (flat) 平屋根スラブ | ✅ 完了（`samples/building_with_roof.json`、footprint は明示 polygon のみ） |
| 12-6 | `roof.kind = gable`（切妻） | ✅ 完了（6 頂点 8 面の三角柱を numpy で手組み、axis-aligned 矩形） |
| 12-7 | `roof.kind = hip`（寄棟） | ✅ 完了（gable と検証共有、棟線を内側に引き込む） |
| 12-8 | `roof.kind = pyramidal`（四角錐） | ✅ 完了（W==D 正方形限定、5 頂点 6 面） |
| 12-9 | `furniture[]`（家具） | ✅ 完了（`room_index` で部屋に紐づく直方体、Z 軸回転 + 床上に配置） |
| 12-10 | Streamlit UI に building タブ | ✅ 完了（`st.tabs` で「Heightmap (dam)」「Building」の 2 タブ化） |
| 12-11 | `extract-walls` サブコマンド | ✅ 完了（OpenCV HoughLinesP で PNG/PDF → `walls[]` JSON。`pip install -e '.[vision]'`） |
| 12-12 | `walls[]` 線分マージ（axis-aligned） | ✅ 完了（Canny の両 edge を 1 本に collapse、10 → 5 walls） |
| 12-13 | UI に `extract-walls` 露出 | ✅ 完了（Building タブに "Extract from image" を追加） |
| 12-14 | extract 結果の line overlay | ✅ 完了（検出 `walls[]` の中心線を入力画像に赤で重ね描き） |
| 12-15 | `extract-walls --with-rooms` | ✅ 完了（walls の閉路を shapely polygonize で `rooms[]` に自動生成） |
| 12-16 | 斜め線分のマージ | ✅ 完了（任意角度に一般化、near-collinear な斜め壁も 1 本に統合） |
| 13-1a | Building タブで `walls[]` をテーブル編集 | ✅ 完了（`st.data_editor` で行追加 / 削除 / 値編集 → Build。「編集可能 3D」の UI 第一歩） |

## 工数（開発時間の目安）

git のコミット時刻から推定したタスク別の作業時間。**実測のタイムトラッキング
ではなく、コミット間隔からの推定値**なので、絶対値ではなく相対的な目安として読む。

- 期間: **2026-05-24 〜 2026-05-30（6 日間）** / 推定アクティブ合計: **約 22.6h**
- 日別（アクティブ）: 05-24 ≈ 3.6h / 05-25 ≈ 4.2h / 05-26 ≈ 3.6h /
  05-27 ≈ 2.8h / 05-28 ≈ 3.2h / 05-29 ≈ 4.4h / 05-30 ≈ 0.9h

### フェーズ別

| フェーズ | 内容 | 推定工数 |
| --- | --- | ---: |
| Phase 1 | コアパイプライン（Step 1〜4）+ 計画・環境整備 | 7.0h |
| Phase 2 | パッケージ化 / Streamlit UI / 公開デモ / OSS 整備（Step 5〜10 + deploy） | 4.6h |
| Phase 3 | 編集可能 3D の一歩（Step 11）+ `/codex-loop` 整備 | 1.3h |
| Phase 4 | building モード 16 連続 PR（Step 12-1〜12-16）+ progress.md | 9.8h |
| **合計** | | **約 22.6h** |

### タスク別

| タスク | PR | 推定工数 |
| --- | --- | ---: |
| 環境 / Claude+Codex レビュー基盤 | — | 1.5h |
| 計画書・README 整備 | [#1](https://github.com/hang-up33/meshforge/pull/1)〜[#3](https://github.com/hang-up33/meshforge/pull/3) | 1.9h |
| Step 1: PNG → STL 最小スクリプト | [#4](https://github.com/hang-up33/meshforge/pull/4) | 0.4h |
| Step 2: `--invert` / `--threshold` | [#5](https://github.com/hang-up33/meshforge/pull/5) | 0.5h |
| Step 3: PDF 入力対応 | [#7](https://github.com/hang-up33/meshforge/pull/7) | 0.2h |
| Step 4: 設定の JSON 化 | [#8](https://github.com/hang-up33/meshforge/pull/8) | 2.5h |
| Step 5: パッケージ化 + `convert` | [#9](https://github.com/hang-up33/meshforge/pull/9) | 0.2h |
| Step 6: Streamlit 簡易 GUI | [#10](https://github.com/hang-up33/meshforge/pull/10) | 0.8h |
| Streamlit Cloud デプロイ | [#11](https://github.com/hang-up33/meshforge/pull/11) / [#12](https://github.com/hang-up33/meshforge/pull/12) | 1.1h |
| Step 7: 3D プレビュー | [#13](https://github.com/hang-up33/meshforge/pull/13) | 0.7h |
| Step 8: パラメータプリセット UI | [#14](https://github.com/hang-up33/meshforge/pull/14) | 1.0h |
| Step 9: UI エラー処理強化 | [#15](https://github.com/hang-up33/meshforge/pull/15) | 0.1h |
| Step 10: OSS リリース整備 | [#16](https://github.com/hang-up33/meshforge/pull/16) | 0.8h |
| Step 11: 高さレイヤー（マルチバンド） | [#17](https://github.com/hang-up33/meshforge/pull/17) | 0.6h |
| `/codex-loop` 自走ループ整備 | [#18](https://github.com/hang-up33/meshforge/pull/18) | 0.7h |
| Step 12-1: building 骨格 + JSON スキーマ | [#19](https://github.com/hang-up33/meshforge/pull/19) | 1.1h |
| Step 12-2: `walls[]` → 壁 STL | [#20](https://github.com/hang-up33/meshforge/pull/20) | 0.2h |
| Step 12-3: `rooms[]` → 床スラブ | [#21](https://github.com/hang-up33/meshforge/pull/21) | 1.2h |
| Step 12-4: `openings[]` → くり抜き | [#22](https://github.com/hang-up33/meshforge/pull/22) | 0.2h |
| Step 12-5: `roof` (flat) | [#23](https://github.com/hang-up33/meshforge/pull/23) | 0.5h |
| Step 12-6: `roof` gable（切妻） | [#24](https://github.com/hang-up33/meshforge/pull/24) | 0.1h |
| Step 12-7: `roof` hip（寄棟） | [#25](https://github.com/hang-up33/meshforge/pull/25) | 0.1h |
| Step 12-8: `roof` pyramidal（四角錐） | [#26](https://github.com/hang-up33/meshforge/pull/26) | 0.2h |
| Step 12-9: `furniture[]` | [#27](https://github.com/hang-up33/meshforge/pull/27) | 0.1h |
| Step 12-10: UI に building タブ | [#28](https://github.com/hang-up33/meshforge/pull/28) | 0.3h |
| Step 12-11: `extract-walls` サブコマンド | [#29](https://github.com/hang-up33/meshforge/pull/29) | 0.5h |
| Step 12-12: `walls[]` 線分マージ | [#30](https://github.com/hang-up33/meshforge/pull/30) | 0.4h |
| Step 12-13: UI に `extract-walls` 露出 | [#31](https://github.com/hang-up33/meshforge/pull/31) | 0.4h |
| docs/progress.md 追加 | [#32](https://github.com/hang-up33/meshforge/pull/32) | 1.0h |
| Step 12-14: extract 結果の line overlay | [#33](https://github.com/hang-up33/meshforge/pull/33) | 1.1h |
| Step 12-15: `extract-walls --with-rooms` | [#34](https://github.com/hang-up33/meshforge/pull/34) | 0.6h |
| Step 12-16: 斜め線分のマージ | [#35](https://github.com/hang-up33/meshforge/pull/35) | 1.6h |

> **推定方法**: 全コミットを時系列に並べ、間隔が 2 時間以内なら同一セッションと
> みなして間隔をそのタスクの作業時間に積算する。2 時間超は別セッションとして
> 切り、各セッション先頭のコミットに 30 分のウォームアップを加算。マージコミットは
> 事務的操作として工数から除外（レビュー待ち時間も含まれないため、計画→実装→
> レビュー反映の一気通貫ではなく「手を動かしていた時間」に近い）。AI 支援開発で
> 1 コミットに収束したタスクは「直前コミットからの経過時間」がそのまま値になり、
> 実作業より短めに出ることがある（例: Step 9 / Step 12-6 等）。

## フォルダ構成

```
meshforge/
├─ README.md
├─ pyproject.toml              パッケージ定義（Step 5 で追加）
├─ docs/
│   ├─ development-plan.md     段階的計画（正）
│   ├─ development-notes.md    開発メモ / 詳しい使い方（このファイル）
│   └─ progress.md             タスク単位の歩み
├─ python/
│   ├─ make_sample.py          動作確認用サンプル PNG / PDF 生成
│   └─ meshforge/              Step 5 でパッケージ化済
│       ├─ __init__.py
│       ├─ __main__.py         `python -m meshforge` のエントリ
│       ├─ heightmap.py        PNG/PDF -> 高さ配列
│       ├─ mesh.py             高さ配列 -> trimesh.Trimesh
│       ├─ stl.py              バイナリ STL 出力
│       ├─ cli.py              argparse / --config 解決 / サブコマンド
│       └─ ui_streamlit.py     Streamlit 簡易 GUI（Step 6）
└─ samples/                    入力サンプル（PNG / PDF）
```

## 進め方ルール

- 1 ステップ完了（動作確認できた）→ コミット → 次ステップ
- 動かないうちに次のステップに進まない
- 抽象化・テスト・エラー処理は「必要になってから」入れる
- 計画を膨らませず、必要になったら都度追加
- ユーザー指示「一歩一歩着実に」を最優先

## 開発ループ（Claude 実装 → Codex レビュー → Claude 修正）

```
[Claude が feature branch で実装]
        ↓
[gh pr create で PR を開く]
        ↓
[Codex でレビュー]
        ├─ ローカル: scripts/codex-review.sh → .codex/reviews/*.md
        └─ GitHub: PR コメント
        ↓
[Claude が指摘を反映 → 同じブランチに追加コミット]
        ↓
   レビューが落ち着く ──→ マージ
```

スラッシュコマンド:
- `/codex-review [base]` — 現在ブランチを Codex reviewer エージェントにレビューさせる
- `/apply-pr-feedback [pr <N> | file <path>]` — PR コメント / レビューファイルを読んで修正

共通規約: [AGENTS.md](../AGENTS.md)（Claude と Codex の両方が読む）。
詳細セットアップ: `.codex/config.toml`、`.codex/agents/`、`.claude/commands/`。

## 各ステップの「やらないこと」

| ステップ | やらないこと |
| --- | --- |
| Step 1 | フォルダ階層・テスト・C#・設定ファイル・ロギング・複数入力 |
| Step 2 | PDF・JSON・UI・パッケージ化 |
| Step 3 | JSON・UI・複数ページ・パッケージ化 |
| Step 4 | UI・パッケージ化・複数入力 |
| Step 5 | UI・3D プレビュー・エラー処理凝り |
| Step 6 | Avalonia/C# 移行・3D プレビュー・複数入力・複数ページ PDF・認証 |
| Step 7 | プレビュー上の編集操作・複数ビュー・サーバ側レンダリング |
| Step 8 | プリセット追加 UI・JSON 保存・`pixel_mm`/`dpi` のプリセット化・CLI 展開 |
| Step 9 | CLI 側のエラー整理・多言語化・magic-byte 検証・自動ダウンサンプリング |
| Step 10 | GitHub Actions release・PyPI 公開・バージョニング自動化・多言語ドキュメント・GIF 自体の生成・CI/lint/test 基盤 |
| Step 11 | UI フォーム編集・CLI 直接フラグ・領域単位編集・押出方向変更・開口部指定・バンド境界の連続補間・複数ページ PDF |

## 環境メモ

- 現コンテナ: Python 3.11 のみ（`dotnet` なし）
- Step 1〜5 は Python のみで完結
- Step 6 で C# を入れる判断をした場合は Mac でセットアップ
