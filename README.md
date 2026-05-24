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

## 方針

- いきなり Avalonia + C# + Python の3層は組まない
- まずは1ファイルの Python スクリプトで「PNG → STL」
- 各ステップで「動く成果物」を1個ずつ手に入れる
- UI (Avalonia) はコアが安定してから載せる
- 各ステップ完了時に動作確認 → コミット → 次へ

詳細は [`docs/development-plan.md`](docs/development-plan.md) を参照（こちらが正）。

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

Step 7 以降（3D プレビュー / 複数入力 / エラー処理強化 / OSS リリース）は構想のみ。

## 進捗

| # | タスク | 状態 |
| --- | --- | --- |
| 1 | 最小スクリプト「PNG → STL」 | ✅ 完了（`python/heightmap_to_stl.py`） |
| 2 | `--invert` / `--threshold` 追加 | ⬜ 未着手 |
| 3 | PDF 入力対応 | ⬜ 未着手 |
| 4 | 設定の JSON 化 | ⬜ 未着手 |
| 5 | Python パッケージ化 | ⬜ 未着手 |
| 6 | GUI（再計画） | ⬜ 未着手 |

## 想定フォルダ構成（段階的に育てる）

```
meshforge/
├─ README.md
├─ docs/
│   └─ development-plan.md     段階的計画（正）
├─ python/
│   ├─ heightmap_to_stl.py     Step 1〜4 はこの 1 ファイル
│   └─ meshforge/              Step 5 でパッケージ化
│       ├─ __init__.py
│       ├─ heightmap.py
│       ├─ mesh.py
│       ├─ stl.py
│       └─ cli.py
└─ samples/                    入力サンプル（PNG / PDF）
```

現時点ではこの構成は **まだ存在しない**（README と `docs/` のみ）。Step 進行に合わせて育てる。

## 使い方（Step 進行ごとに更新）

### Step 1（実装済み）

```sh
# サンプル PNG を作る
.venv/bin/python python/make_sample.py samples/dome.png

# PNG → STL
.venv/bin/python python/heightmap_to_stl.py samples/dome.png samples/dome.stl
```

### Step 2（予定）

```sh
python python/heightmap_to_stl.py input.png output.stl --invert --threshold 128
```

### Step 5（予定）

```sh
python -m meshforge convert config.json
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
| Step 6 | （要再計画） |

## 環境メモ

- 現コンテナ: Python 3.11 のみ（`dotnet` なし）
- Step 1〜5 は Python のみで完結
- Step 6 で C# を入れる判断をした場合は Mac でセットアップ
