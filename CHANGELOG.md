# Changelog

このプロジェクトの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、
バージョン番号は [Semantic Versioning](https://semver.org/lang/ja/) に従う。

ステップ表記は [`docs/development-plan.md`](docs/development-plan.md) と対応する。

## [Unreleased]

### Added
- `LICENSE` (MIT)、`CONTRIBUTING.md`、本 `CHANGELOG.md`（Step 10: OSS リリース整備）
- README に Demo セクション（Streamlit Community Cloud の公開 URL 案内）

## [0.1.0] - 2026-05-26

最初の動く成果物。PNG / PDF を入力すると Bambu Lab Studio で開ける
バイナリ STL を吐く。CLI とブラウザ UI の両方から使える。

### Added
- **Step 1**: 最小スクリプト `python/heightmap_to_stl.py` で PNG → STL。
  numpy / pillow / trimesh のみで高さマップ→押出メッシュ→バイナリ STL。
- **Step 2**: `--invert` / `--threshold` を追加。建築平面図（黒壁 / 白床）
  から壁が立ち上がった STL を出せるように。
- **Step 3**: PDF 入力対応。PyMuPDF で 1 ページ目をラスタライズしてから
  既存パイプラインに流す。`--dpi` で解像度指定。
- **Step 4**: `config.json` 化。`--config` で全パラメータを JSON から
  読み込み、`--save-config` で書き出し。`pixel_mm` / `max_height_mm` /
  `base_mm` などジオメトリ定数も JSON で上書き可能。
- **Step 5**: 1 ファイルだったスクリプトを `python/meshforge/` パッケージに
  分割（heightmap / mesh / stl / cli）。`python -m meshforge convert ...`
  で呼べる形に。`pyproject.toml` で editable install。
- **Step 6**: Streamlit ブラウザ UI（`python/meshforge/ui_streamlit.py`）。
  PNG / PDF をアップロードしてフォームでパラメータを調整、STL を
  ダウンロード。CLI とバイト一致する STL を生成。
- **Step 7**: 3D プレビューを Streamlit UI に追加（`streamlit-stl`、
  three.js ベース）。Convert 後にブラウザ上で回転 / ズーム可能。
- **Step 8**: パラメータプリセット UI。Floor plan / Logo / Terrain /
  Custom を `st.selectbox` で切り替え、form widget の値に反映。
- **Step 9**: Streamlit UI のエラー処理強化。PyMuPDF 不在、壊れた /
  パスワード保護 PDF、PDF 0 ページ、8 Mpx 超の巨大入力、DPI 上限 (600)
  を `st.error` で日本語表示。Convert ボタンを文脈に応じて disable。

### Deployed
- Streamlit Community Cloud で `main` ブランチを自動デプロイ。
  `requirements.txt` から `.[pdf,ui]` extra を取り込む形でコア + PDF + UI
  を一括インストール。

<!--
リンクは「タグ作成前でも 404 にならない」ことを優先して、`main` の
コミット履歴と 0.1.0 相当のコミット tree を直接参照している。`v0.1.0`
タグを切ったら下記を `compare/v0.1.0...HEAD` / `releases/tag/v0.1.0` に
書き換える運用。
-->
[Unreleased]: https://github.com/hang-up33/meshforge/commits/main
[0.1.0]: https://github.com/hang-up33/meshforge/tree/231ed020a6bfe24de8e207e53ff1b20e41f32322
