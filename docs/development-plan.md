# meshforge: 画像/PDF → STL 変換ツール 段階的計画

## Context

リポジトリ `meshforge` は README.md のみの状態。設計書「STL出力ツール 設計書」を参照しつつ、**いきなり全アーキテクチャを組まず、一歩ずつ動くものを積み上げる方針** に切り替える。

**最終ゴール (再掲、変えない)**: 画像/PDFを Bambu Lab Studio で読込可能な STL に変換する Avalonia UI ツール。MVP のデモは「もしも一級建築士が STL ジオラマを作るとしたら」= 建築平面図 PDF → 壁押出 STL。

**今回の方針変更**:
- いきなり Avalonia + C# + Python の3層を組まない
- **まずは1ファイルの Python スクリプト** で「PNG → STL」が動くところから
- 各ステップで「動く成果物」を1個ずつ手に入れる
- UI (Avalonia) は **コアが安定してから** 載せる
- 各ステップ完了時に動作確認 → コミット → 次へ

## ステップ計画 (小さい順)

各ステップは **「これ単体で動く成果物」** を返す。前ステップが動かないと次に進まない。

### Step 1: 最小スクリプト「PNG → STL」(1ファイル)
- **作るもの**: `python/heightmap_to_stl.py` 1ファイルのみ
- **やること**: 引数で渡された PNG をグレースケール→高さマップ→単純な押出メッシュ→バイナリ STL 出力
- **使うライブラリ**: numpy, pillow, trimesh
- **検証**: 適当な PNG (黒い円が描かれた画像など) を入力して STL が出力され、Bambu Lab Studio (またはオンラインSTLビューワ) で開ける
- **作らないもの**: フォルダ階層、C#、テスト、設定ファイル、CLI 引数の凝った設計
- **完了条件**: コマンド1発で PNG → STL ができる

### Step 2: 建築ジオラマ用に「閾値+反転」を足す
- **作るもの**: Step 1 のスクリプトに `--invert` と `--threshold` オプションを追加
- **やること**: 建築平面図 (黒い壁線/白い床) を入れて壁が立ち上がる STL を出す
- **検証**: フリー素材の建築平面図 PNG (この時点では PDF はまだやらない) を入力 → 壁が立ち上がった建築ジオラマ STL → Bambu Lab Studio で開いて確認
- **成果**: 一級建築士ジオラマ デモが PNG ベースで完成
- **完了条件**: 建築ジオラマ STL がスライサで開ける

### Step 3: PDF 入力対応
- **作るもの**: Step 2 のスクリプトに PDF 対応を追加 (PyMuPDF で 1ページ目を PNG ラスタライズしてから既存処理に流す)
- **やること**: PDF → PNG → STL の流れを1コマンドで
- **検証**: 建築平面図 PDF を直接入力 → 同じジオラマが出る
- **成果**: 設計書の MVP デモ (PDF→押出ジオラマ) がスクリプト1本で実現
- **完了条件**: 建築平面図 PDF から STL が出る

### Step 4: 設定の JSON 化
- **作るもの**: コマンドライン引数の代わりに `config.json` で全パラメータを指定可能にする
- **やること**: 設計書の Project Format (簡易版) を JSON で読み込み、保存も可能に
- **検証**: `config.json` を作って同じ STL が再現できる
- **成果**: 「変換設定の保存/再利用」ができる
- **完了条件**: JSON 1ファイルでビルド再現可能

### Step 5: Python パッケージ化 + サブコマンド
- **作るもの**: 1ファイルだったスクリプトを `python/meshforge/` パッケージに整理し `python -m meshforge convert ...` で呼べる形に
- **やること**: 機能ごとにモジュール分割 (heightmap, mesh, stl, cli)
- **検証**: 同じ STL が `python -m meshforge convert config.json` で出る
- **成果**: UI から呼びやすい構造になる (後で Avalonia から呼べる土台)
- **完了条件**: 既存機能がリグレッションなくパッケージ経由で動く

### Step 6: 簡易 GUI を Streamlit で載せる
- **判断 (Step 5 完了後の再計画結果)**: まず Streamlit でブラウザ UI を載せる。
  Avalonia + C# は将来のリプレース候補として残し、Step 6 では着手しない。
  - 理由: コアは Step 5 で `python -m meshforge convert` の Python パッケージに
    なっているため、UI 層だけ Streamlit で被せれば「動く成果物」が最速で得られる。
    C# 移行時はコアをそのまま subprocess 経由で叩く形に切り替えれば良い。
- **作るもの**: `python/meshforge/ui_streamlit.py` 1 ファイル
- **やること**:
  - PNG / PDF をブラウザからアップロード
  - `--invert` / `--threshold` / `--dpi` / `--pixel-mm` / `--max-height-mm` /
    `--base-mm` をフォームで調整
  - 「変換」ボタンで STL を生成し、ブラウザからダウンロード可能にする
  - 同じ入力・同じパラメータで CLI と バイト一致する STL を返す
- **使うライブラリ**: `streamlit` (新規依存、`pyproject.toml` の `ui` extra)
- **起動**: `.venv/bin/streamlit run python/meshforge/ui_streamlit.py`
- **やらないこと**:
  - Avalonia / C# 移行（将来 Step として保留）
  - STL の 3D プレビュー（Step 7 構想に回す）
  - 複数ファイル一括変換 / 複数ページ PDF
  - 認証 / マルチユーザー（ローカル単体起動前提）
- **完了条件**: ブラウザから PNG/PDF を入れて STL をダウンロードでき、CLI と
  同じ入力・同じパラメータでバイト一致する

### Step 7: STL の 3D プレビューを Streamlit UI に組み込む
- **判断**: Step 6 の Streamlit UI に「Convert したらその場で 3D で確認できる」
  プレビューを足す。ダウンロード前に妥当性を目視確認できると、特に
  「invert / threshold が想定通りに当たっているか」を試行錯誤しやすい。
- **作るもの**: `python/meshforge/ui_streamlit.py` の Convert 結果表示に
  `streamlit-stl` の `stl_from_text` を 1 ブロック追加するだけ。
- **使うライブラリ**: `streamlit-stl`（three.js ベース、軽量。`ui` extra に追加）
- **やること**:
  - Convert 成功後に `st.subheader("3D preview")` の下に `stl_from_text(stl_bytes, ...)`
    を呼ぶ。color / material / opacity / height だけ控えめに設定
  - ダウンロードボタンはそのまま残す（プレビュー → 良ければダウンロード の流れ）
- **やらないこと**:
  - プレビュー上でのマウス編集（頂点を動かす等）— 編集は別 Step
  - 複数ビュー / カメラプリセット
  - サーバ側レンダリング（あくまでブラウザの three.js）
- **完了条件**: Convert 後にブラウザに STL が 3D 表示され、回転 / ズームできる

### Step 8: パラメータプリセットを UI に追加
- **判断**: Convert ごとに invert / threshold / max_height_mm / base_mm を
  ゼロから合わせ込む UX が辛いため、想定入力ごとのプリセットを用意して
  「選ぶ→微調整」できるようにする。
- **作るもの**: `ui_streamlit.py` の Convert フォーム上に `st.selectbox`
  のプリセット選択を 1 つ追加。`st.session_state` 経由で form 内 widget の
  値を上書きする。
- **プリセット**:
  - Custom (manual): 何もしない（現在のフォーム値を維持）
  - Floor plan (dark walls on light background): `invert=True`,
    `use_threshold=True`, `threshold=128`, `max_height_mm=10.0`, `base_mm=1.0`
  - Logo / Text (light on dark): `invert=False`, `use_threshold=True`,
    `threshold=128`, `max_height_mm=5.0`, `base_mm=2.0`
  - Terrain / Depth map (grayscale gradient): `invert=False`,
    `use_threshold=False`, `max_height_mm=15.0`, `base_mm=1.0`
- **やらないこと**:
  - プリセット追加 UI（プリセットはコード固定、保存先 JSON 等は持たない）
  - `pixel_mm` / `dpi` のプリセット化（入力タイプによる差が小さいため固定）
  - CLI 側へのプリセット展開（CLI は引き続き `--config` JSON で再現する）
- **完了条件**: プリセットを切り替えると form の widget 値が連動して変わり、
  Convert ボタンで反映後の値が使われる

### Step 9: Streamlit UI のエラー処理強化
- **判断**: OSS 限定公開で「他人が触っても壊れない」状態にするため、UI で
  起こりうる失敗ケースを明示的に拾って、ユーザーフレンドリーなメッセージに
  置き換える。CLI のエラー整理は別 Step（必要になってから）。
- **対象ケース**:
  - PDF 入力だが PyMuPDF 未インストール → form 描画前に検知して error 表示 +
    Convert ボタン disable
  - 壊れた / パスワード保護 / 形式不一致なファイル → 種別付きメッセージで
    `st.error`
  - PDF 0 ページ（既存の `ValueError`）→ UI 上で error 表示
  - 巨大ファイル（8 Mpx 超）→ heightmap → mesh の前に止めて error 表示。
    Streamlit Cloud の 1 GB RAM 制限で OOM するのを予防
  - DPI に上限 600 を設けて PyMuPDF の暴走を防ぐ
- **やらないこと**:
  - CLI 側のエラーメッセージ整理（CLI は既に CLI らしく例外を吐けば良い）
  - 多言語化
  - アップロード前の magic-byte 検証（拡張子チェックで十分）
  - 巨大ファイル時の自動ダウンサンプリング（明示エラーで止めて DPI 調整を
    促す方が誤動作リスクが低い）
- **完了条件**: 想定エラーケースで UI が traceback を出さず、`st.error` で
  日本語メッセージを表示する。サンプル PNG / PDF の正常系には影響しない

### Step 10 以降 (構想のみ、ここでは確定しない)
- 複数入力対応（複数ページ PDF / 複数 PNG）
- OSS リリース整備（LICENSE / CONTRIBUTING / CHANGELOG / デモ GIF）
- 編集可能 3D の最初の一歩

## 各ステップの「やらないこと」リスト (重要)

複雑化を防ぐため、各ステップで **やらないこと** を明示する。

| ステップ | やらないこと |
|---|---|
| Step 1 | フォルダ階層・テスト・C#・設定ファイル・ロギング・複数入力 |
| Step 2 | PDF・JSON・UI・パッケージ化 |
| Step 3 | JSON・UI・複数ページ・パッケージ化 |
| Step 4 | UI・パッケージ化・複数入力 |
| Step 5 | UI・3Dプレビュー・エラー処理凝り |
| Step 6 | Avalonia/C# 移行・3D プレビュー・複数入力・複数ページ PDF・認証 |
| Step 7 | プレビュー上の編集操作・複数ビュー・サーバ側レンダリング |
| Step 8 | プリセット追加 UI・JSON 保存・`pixel_mm`/`dpi` のプリセット化・CLI 展開 |
| Step 9 | CLI 側のエラー整理・多言語化・magic-byte 検証・自動ダウンサンプリング |

## 着手判断

- Step 1 のスクリプトは **20〜50行で書ける規模** を目標にする
- 各ステップ完了時にユーザーが動作を確認 → 次ステップへ
- 計画を膨らませず、必要になったら都度追加

## 設計書との関係

- 設計書の「フォルダ構成」「Project Format」「タスク分解」は **最終形のリファレンス** として残す
- 直近では設計書を達成するための **最小経路** を Step 1〜6 として進める
- Avalonia + C# 採用は前提だが、コアが Python で動いてから載せても遅くない

## 進め方ルール

- 1ステップ完了 (動作確認できた) → コミット → 次ステップ
- 動かないうちに次のステップに進まない
- 抽象化・テスト・エラー処理は「必要になってから」入れる
- ユーザー指示「一歩一歩着実に」を最優先

## 環境メモ

- 現在のコンテナには Python 3.11 のみインストール済 (`dotnet` は無し)
- ユーザー指示により環境構築は今回行わない
- Step 1〜5 は Python のみで完結 (このコンテナでも実行可能)
- Step 6 で C# を入れる判断をした場合は Mac でセットアップ
