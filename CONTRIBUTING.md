# Contributing to meshforge

meshforge への貢献を検討してくれてありがとう。このドキュメントは、
外部から PR / Issue を出すときに最低限知っておくと噛み合わせやすい
内容をまとめたもの。

開発エージェント（Claude Code / Codex）向けの詳細規約は
[AGENTS.md](AGENTS.md) を見てほしい。

## このプロジェクトの進め方

- **段階的計画**: 一度に大改修せず、[`docs/development-plan.md`](docs/development-plan.md)
  のステップ単位で「動く成果物」を 1 つずつ積む方針。
- **各ステップの「やらないこと」**: 同じファイルにステップごとの
  「やらないこと」が明記されている。レビューでは「そのステップで足すべき
  でない機能」が混ざっていないかを優先的に見る。
- **抽象化・テスト・エラー処理は必要になってから**。

新機能を提案するときは、それが既存ステップの追補なのか、新ステップとして
扱うのが妥当なのかを Issue / PR 説明に書いてもらえると判断が早い。

## セットアップ

```sh
python -m venv .venv
.venv/bin/pip install -e '.[pdf,ui]'
```

- `pdf` extra: PDF 入力（PyMuPDF）
- `ui` extra: Streamlit ブラウザ UI と 3D プレビュー

ローカル開発の依存は [`pyproject.toml`](pyproject.toml) が正本。
`requirements.txt` は Streamlit Community Cloud のデプロイ専用で、
`numpy` / `pillow` / `trimesh` / `pymupdf` / `streamlit` / `streamlit-stl`
を直接列挙している（uv が local path entry を reject し、`pyproject.toml`
へフォールバックすると Poetry が `python/meshforge` の src layout を
解決できないため）。

**依存を追加するときは両方を更新する必要がある**:

1. `pyproject.toml` の `dependencies` / `optional-dependencies` を編集
2. `requirements.txt` にも同じパッケージ名を追記

片方だけ更新すると、ローカルで動いても Streamlit Cloud 側で ImportError、
あるいはその逆になる。

## 動作確認

最小限の動作確認は次の 2 つ:

```sh
# サンプル PNG → STL
.venv/bin/python python/make_sample.py samples/dome.png
.venv/bin/python -m meshforge convert samples/dome.png samples/dome.stl

# Streamlit UI
.venv/bin/streamlit run python/meshforge/ui_streamlit.py
```

3D プレビューが出て STL がダウンロードできれば一旦 OK。

## PR の出し方

1. main から feature branch を切る（命名は `stepN-xxx` か `fix-xxx` 程度で OK）
2. 変更を作って commit
3. `gh pr create`（または GitHub Web）で main 宛に PR を開く
4. レビューが付いたら同じブランチに追加コミットで反映
5. レビューが落ち着いたらマージ

このリポジトリでは AI レビュアー（Codex）が PR にコメントすることがある。
スタイルだけの指摘は無視して OK。実害のあるバグ・退行・段階性違反は
取り込んでほしい。

### コミット / PR メッセージ

- **日本語で書く**（[AGENTS.md](AGENTS.md) の規約に合わせる）
- prefix は Conventional Commits 風（`feat(step10): ...` / `fix(step9): ...` / `docs: ...`）
- 本文では「なぜ」を 1〜2 行で。コード差分から読める「何を」は短くて良い

### コード規約（要点）

- Python 3.11 以上
- 型ヒントは「読みやすくなる時だけ」入れる
- コメントは「なぜ」を書く。「何をしているか」は識別子で表現する
- ファイル末尾は改行で終わる
- 公開関数のドキストリングは 1 行で十分

## バグ報告 / 機能要望

GitHub の [Issues](https://github.com/hang-up33/meshforge/issues) に立ててほしい。
できれば以下を含めてもらえると助かる:

- meshforge のバージョン（`pyproject.toml` の `version` か git commit hash）
- 再現手順（入力ファイル / コマンド / Streamlit UI の操作）
- 期待した挙動と実際の挙動
- 環境（OS / Python バージョン）

入力 PDF / PNG はバイナリのまま添付しづらいことが多いので、最小化した
合成ケース（`python/make_sample.py` で作れるもの等）に差し替えられると
受け側で再現しやすい。

## ライセンス

このリポジトリへの貢献は [MIT License](LICENSE) で配布されることに
同意したものとみなす。
