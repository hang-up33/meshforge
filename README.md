# meshforge

> **PDF（仕様書 / 図面）→ 編集可能な 3D モデル → STL**
>
> 紙ベースの設計資料を、その場で形を調整できる 3D に起こし、
> Bambu Lab Studio で印刷できる STL として書き出すツール。

PDF をただ「画像として押し出す」のではなく、**編集可能な中間 3D モデル**
（壁の高さ、開口部、要素の有無などをパラメータとして持つ）を経由するのが
meshforge の特徴。MVP デモは「もしも一級建築士が STL ジオラマを作るとしたら」=
建築平面図 PDF → 壁押出 → 高さ/開口を編集 → STL。

## 想定パイプライン

```
┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   ┌──────────┐
│  PDF / 画像  │ → │  ラスタライズ │ → │  編集可能 3D モデル   │ → │   STL    │
│ (仕様書/図面) │   │ + 領域抽出   │   │ (パラメータ + ジオメトリ)│   │ (印刷用) │
└──────────────┘   └──────────────┘   └──────────────────────┘   └──────────┘
                                              ↑
                                       ここで GUI 編集
                                  （壁高さ・開口・押出方向等）
```

「編集可能 3D」が肝。中間状態を **JSON で保存・再現** でき、後段の UI
（Avalonia 等）から非破壊的に再生成できることを設計目標とする。

最終形は Avalonia UI + C# + Python の3層構成だが、本リポジトリは
**まず Python スクリプト 1 本で「PNG → STL」が動く** ところから段階的に積み上げる方針で進める。

## Demo

ブラウザから触れる公開デモを Streamlit Community Cloud にホストしている。

- **公開 URL**: <https://meshforge.streamlit.app/>（初回アクセス時は sleep
  からの復帰で 20〜40 秒かかる場合あり）
- **Heightmap (dam) タブ**: PNG / PDF をアップロード → プリセット選択 →
  Convert で STL を生成、ブラウザ上で 3D プレビュー → ダウンロード。
- **Building タブ**: 中間 JSON (`walls` / `rooms` / `openings` / `roof` /
  `furniture`) をアップロードして STL を生成、もしくは "Extract from image"
  で PNG / PDF 平面図から `walls[]` を自動抽出 (Step 12-13)。中間 JSON
  単体のダウンロードも可能。

### Editor 画面

![meshforge editor](docs/screenshots/editor.png)

> スクショは Building タブの "Extract from image" を選んだ状態
> (Step 12-13)。Heightmap (dam) タブを開けば従来通り PNG / PDF →
> 直接 STL のフローが使える。

#### Step 12-14/15: Extract 結果の line overlay + rooms 自動抽出

![extract walls + rooms overlay](docs/screenshots/overlay-preview.png)

> `Extract & Build` 押下後、入力画像の上に検出された `walls[]` の中心線が
> 赤で重なって表示される (Step 12-14)。`Auto-extract rooms` を ON にすると
> walls の閉路から `rooms[]` を polygonize で検出し、青の細線で polygon
> outline も重ねる (Step 12-15)。スクショは `samples/floor_plan_simple.png`
> を pixel_mm=0.5 / wall_thickness_mm=4 / wall_height_mm=24 /
> min_length_mm=30 / with_rooms=True で抽出した結果 (外周 4 + 内壁 1 = 5 本
> + 2 部屋) を `_render_extract_overlay` と同じロジックでオフライン再現
> したもの。公開デモではブラウザ上で直接見られる。

> UI を変更した PR では、PR 本文のスクショに加えて
> [`docs/screenshots/editor.png`](docs/screenshots/editor.png) も
> 同じ PR で更新する（README とリポジトリ内画像のズレを防ぐため）。
> 撮り直し手順は [`docs/screenshots/README.md`](docs/screenshots/README.md) 参照。

> **GIF プレースホルダ**: `docs/demo.gif` に画面録画を差し込む予定。
> 公開デモの URL を踏めば実物を触れるので、優先度は低い。

## 方針

- いきなり Avalonia + C# + Python の3層は組まない
- まずは1ファイルの Python スクリプトで「PNG → STL」
- 各ステップで「動く成果物」を1個ずつ手に入れる
- UI (Avalonia) はコアが安定してから載せる
- 各ステップ完了時に動作確認 → コミット → 次へ

詳細は [`docs/development-plan.md`](docs/development-plan.md) を参照（こちらが正）。
タスク単位の歩み・第三者向けサマリは [`docs/progress.md`](docs/progress.md)。

## 技術スタック

- 言語: Python 3.11（Step 1〜5）、後に C# (Avalonia) を載せる可能性あり
- 主要ライブラリ: `numpy`, `pillow`, `trimesh`, `PyMuPDF`（Step 3 以降）
- ホスト OS: macOS 想定（現コンテナは Linux + Python 3.11 のみ）
- スライサ確認用: Bambu Lab Studio

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

## 進捗

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

## フォルダ構成

```
meshforge/
├─ README.md
├─ pyproject.toml              パッケージ定義（Step 5 で追加）
├─ docs/
│   └─ development-plan.md     段階的計画（正）
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

## セットアップ

Step 5 以降、`meshforge` は Python パッケージとして編集可能インストールで
使う。venv の作成後、リポジトリ直下で:

```sh
.venv/bin/pip install -e .                       # PNG のみで使う場合
.venv/bin/pip install -e '.[pdf]'                # PDF 入力 (PyMuPDF) も使う場合
.venv/bin/pip install -e '.[pdf,ui]'             # Step 6 の Streamlit GUI も使う場合
.venv/bin/pip install -e '.[building]'           # Step 12-3 の rooms[] 床スラブ / Step 12-4 の openings くり抜きを使う場合
```

## 使い方

すべて `python -m meshforge convert ...` のサブコマンドで呼ぶ。

### PNG → STL

```sh
# サンプル PNG を作る
.venv/bin/python python/make_sample.py samples/dome.png

# PNG → STL
.venv/bin/python -m meshforge convert samples/dome.png samples/dome.stl
```

### 建築平面図（黒い壁 / 白い床）

`--invert` で明暗を反転し、`--threshold` でアンチエイリアスを切って
垂直な壁にする。

```sh
.venv/bin/python python/make_sample.py samples/floorplan.png floorplan

.venv/bin/python -m meshforge convert samples/floorplan.png samples/floorplan.stl \
    --invert --threshold 128
```

### PDF 入力

入力ファイルの拡張子が `.pdf` の場合は PyMuPDF で 1 ページ目を
ラスタライズしてから処理に流す（要 `[pdf]` extra）。`--dpi` で解像度を
指定できる（既定 150 DPI、PNG 入力では無視）。

```sh
.venv/bin/python python/make_sample.py samples/floorplan.pdf floorplan

.venv/bin/python -m meshforge convert samples/floorplan.pdf samples/floorplan.stl \
    --invert --threshold 128 --dpi 150
```

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

### ブラウザ GUI（Streamlit, Step 6）

`pip install -e '.[ui]'` を入れた後、リポジトリ直下で:

```sh
.venv/bin/streamlit run python/meshforge/ui_streamlit.py
```

ブラウザに UI が開き、PNG / PDF をアップロード → 想定入力に応じた
プリセット（Step 8、Floor plan / Logo / Terrain / Custom）を選ぶか手動で
パラメータを調整 → 「Convert」で STL を生成しダウンロードできる。
Convert 後は `streamlit-stl` による 3D プレビュー（Step 7、three.js ベース）が
表示され、ブラウザ上で回転 / ズームしながら妥当性を確認できる。内部で
呼ぶ変換パイプラインは CLI と同一なので、同じ入力・同じパラメータの STL は
バイト一致する。

Avalonia + C# への移行は将来の Step として保留（CLI を subprocess で
叩く構造に切り替えるだけでコア再利用可能）。

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
の両方を更新する必要がある（詳細は [CONTRIBUTING.md](CONTRIBUTING.md)）。

制約:

- 7 日間アクセスがないと app が sleep する（次回アクセス時に 20〜40 秒で再起動）
- メモリ 1GB / 共有 CPU（meshforge の変換は数秒なので問題なし）
- app は public（誰でも URL で到達可能）— OSS 公開の前提

将来 Avalonia 移行や別ホスト（Hugging Face Spaces, Fly.io 等）に
切り替える場合も、コアは Python パッケージのままなので影響範囲は
UI 層と `requirements.txt` だけ。

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

共通規約: [AGENTS.md](AGENTS.md)（Claude と Codex の両方が読む）。
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

## ライセンス / コントリビュート / 変更履歴

- ライセンス: [MIT License](LICENSE)
- コントリビュート方法: [CONTRIBUTING.md](CONTRIBUTING.md)
- リリースノート / 変更履歴: [CHANGELOG.md](CHANGELOG.md)
