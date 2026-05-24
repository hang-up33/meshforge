# meshforge

画像 / PDF を Bambu Lab Studio で読込可能な **STL** に変換するツール。
MVP デモは「もしも一級建築士が STL ジオラマを作るとしたら」=
建築平面図 PDF → 壁押出 STL。

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

| Step | 成果物 | 完了条件 |
| --- | --- | --- |
| 1 | `python/heightmap_to_stl.py`（1ファイル） | コマンド1発で PNG → STL ができる |
| 2 | Step 1 に `--invert` / `--threshold` を追加 | 建築ジオラマ STL がスライサで開ける |
| 3 | PDF 入力対応（PyMuPDF でラスタライズ） | 建築平面図 PDF から STL が出る |
| 4 | `config.json` で全パラメータ指定 | JSON 1 ファイルでビルド再現可能 |
| 5 | `python/meshforge/` パッケージ化 + サブコマンド | `python -m meshforge convert config.json` で動く |
| 6 | UI 層（Avalonia か簡易 GUI かを再判断） | Step 5 完了後に改めて計画 |

Step 7 以降（3D プレビュー / 複数入力 / エラー処理強化 / OSS リリース）は構想のみ。

## 進捗

| # | タスク | 状態 |
| --- | --- | --- |
| 1 | 最小スクリプト「PNG → STL」 | ⬜ 未着手 |
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

### Step 1（予定）

```sh
python python/heightmap_to_stl.py input.png output.stl
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
