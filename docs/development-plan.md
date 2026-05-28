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

### Step 10: OSS リリース整備
- **判断**: Streamlit Community Cloud で URL 公開済みなので、コードを
  「外から見て使える」状態にするためのドキュメントとライセンスを整える。
  実装変更は最小限で、リポジトリ直下のメタファイル中心。
- **作るもの**:
  - `LICENSE`（MIT, Copyright holder = hang-up33）
  - `CONTRIBUTING.md`（AGENTS.md の規約から外部コントリビュータ向けに
    必要な部分だけ抽出。Codex レビューフローや段階的計画の趣旨も明記）
  - `CHANGELOG.md`（Keep a Changelog 形式。Step 1〜9 を `0.1.0` として
    まとめ、`pyproject.toml` の version と一致させる）
  - `README.md` に「Demo」セクション（Streamlit Community Cloud の URL +
    GIF プレースホルダ）と LICENSE / CONTRIBUTING / CHANGELOG への
    リンクを追記
- **やらないこと**:
  - GitHub Actions の release ワークフロー / 自動タグ付け
  - PyPI 公開
  - バージョニング自動化（version は手動で `pyproject.toml` を編集）
  - 多言語ドキュメント（README / CONTRIBUTING は日本語のまま）
  - デモ GIF 自体の生成（プレースホルダのみ。ユーザーが画面録画して
    `docs/demo.gif` 等に置く想定）
  - CI / lint / test 基盤の整備（必要になってから）
- **完了条件**:
  - GitHub 上で LICENSE が認識される（MIT バッジが付く）
  - `README.md` から CONTRIBUTING / CHANGELOG / Demo URL に辿れる
  - `CHANGELOG.md` に Step 1〜9 が `0.1.0` として記載されている

### Step 11: 編集可能 3D の最初の一歩 — 高さレイヤー（マルチバンド閾値）
- **判断**: 「編集可能 3D」のビジョン（壁高さ・要素ごとの高さなどを
  パラメータで持つ中間モデル）に向けた最小の一歩として、ピクセル明度を
  複数バンドに分割しバンドごとに独立した高さを JSON で指定可能にする。
  これだけで「外壁 10mm / 内壁 5mm / 開口 0mm」のような階層を 1 枚の
  画像から取り出せ、「JSON を編集して再生成する」体験の最小実例ができる。
- **作るもの**:
  - `to_heights` に `layers: list[dict] | None` を追加。`np.digitize` で
    バンド判定 → バンドの `height_mm` を返す（`invert` は前処理として併用、
    `threshold` / `max_height_mm` は無視）
  - `cli.py` の JSON 設定に `layers` キーを追加。型・昇順を検証し、
    `threshold` との同時指定はエラー
  - `samples/multilayer.json`: `samples/dome.png` を入力にする 4 バンド例
- **使うライブラリ**: 既存（追加なし）
- **やらないこと**:
  - Streamlit UI のフォーム編集（プリセット 1 個に layers を埋め込むのも
    しない。UI 拡張は次 Step で別判断）
  - CLI から `--layers` 等の直接フラグ（JSON 経由のみ）
  - 領域単位（矩形・マスク・要素マップ）の高さ指定
  - 押出方向の変更 / 開口部・穴の明示指定
  - バンド境界の連続補間（階段関数のまま）
  - 複数ページ PDF 対応
- **完了条件**:
  - `python -m meshforge convert --config samples/multilayer.json` で
    階段状の STL（複数の Z 平坦面）が出る
  - 既存サンプル（`layers` キーなし）の出力 STL は Step 10 とバイト一致
  - `layers` と `threshold` の同時指定は `config error` で exit 1

### Step 12: 建築モード (`--mode building`)
- **判断**: Step 11 までは「画像の明度を高さ化する単一押し出し」だったので、
  「平面図 → 建物 3D」をやるには別パイプラインが要る。OpenCV で幾何抽出 →
  Claude API で意味付け → 中間 JSON → trimesh で組み立て、という流れを
  小ステップに割って積み上げる。中間 JSON のスキーマ正本は
  [`docs/building-schema.md`](building-schema.md)。

- **Step 12-1 (完了)**: `--mode building` の骨格と中間 JSON スキーマ仕様。
  - 詳細: コミット `7bdcde9` / `1d0b568` / PR #19
- **Step 12-2 (完了)**: 手書き JSON の `walls[]` から壁 STL を生成。
  - 詳細: コミット `2714097` / PR #20
  - `building/assemble.py` で walls 検証 + trimesh で各壁を箱化 + concat
  - CLI: `convert --config building.json out.stl` の output positional 受付
  - サンプル: `samples/building_minimal.json` (80 mm × 60 mm × 24 mm の箱)
  - **やらないこと**: 角の boolean union (内部の重複面はそのまま) / 開口部 /
    床スラブ / 屋根 / 家具 / 画像→JSON 自動生成 / 複数階 /
    GLB 出力 / building 用 `--save-config` ラウンドトリップ
  - **完了条件**: `python -m meshforge convert --config samples/building_minimal.json out.stl`
    で 4 本の壁が立った STL が出る (各 box が watertight)。既存 dam モードの
    `dome.png` 出力は md5 が変わらない (`e1a9015c...`)。
- **Step 12-3 (完了)**: `rooms[]` を JSON で受けて床スラブを足す。
  - `building/assemble.py` に `rooms` 検証 + shapely Polygon →
    `trimesh.creation.extrude_polygon` で柱状メッシュ生成 + walls とまとめて
    concat
  - 床スラブの z 範囲は 0..floor_thickness_mm。壁基部と重なる内部の重複面は
    walls 同士の角と同じ理由で許容 (FDM スライサが塗り潰す)
  - サンプル: `samples/building_with_floor.json` (80×60 mm を内壁 1 本で
    2 部屋に分け、各室に厚さ 2 mm の床)
  - 新依存: `shapely` + `mapbox_earcut` を `building` extra に分離
    (`pip install -e '.[building]'`)。dam モードには影響しない
  - **やらないこと**: 壁との boolean union (内部の重複面はそのまま) /
    polygon の holes (穴) / 床ポリゴン同士の重なり検出 / 壁高さの自動オフセット
    (床ぶん上げる調整は使う人に任せる) / 床の色・材質メタデータ / `label` を
    メッシュ名に焼く / 自動 watertight 化 / Streamlit UI への露出
  - **完了条件**: `python -m meshforge convert --config samples/building_with_floor.json out.stl`
    で 2 室分の床スラブ + 壁が出る。既存 `samples/building_minimal.json` の
    出力 STL は Step 12-2 とバイト一致 (`92487afcdafbd4ce2afa8290514e15fc`)。
    `dome.png` の dam-mode 出力も md5 が変わらない (`e1a9015cb867a476c59d3fe9018fd96c`)。
- **Step 12-4**: `openings[]` (door/window) を JSON で受けて該当壁を boolean
  でくり抜く。
  - `building/assemble.py` に `openings` 検証 + manifold3d ベースの
    `trimesh.difference` で壁単位にくり抜き、複数開口は `trimesh.boolean.union`
    でまとめてから 1 回の difference をかける
  - サンプル: `samples/building_with_door.json` (80×60 mm の最小建物にドア 1 つ
    と窓 1 つ)
  - 新依存: `manifold3d` を `building` extra に追加 (`pip install -e
    '.[building]'`)。openings 無しの building JSON では import されない
  - **やらないこと**: 開口同士の重なり検出 (boolean union が吸収する) / 開口
    の建具モデル (枠 / ドア板 / ガラス) / `kind` ごとの色・材質メタデータ /
    OpenCV からの開口自動抽出 / Streamlit UI への露出 / 角の boolean union
    (壁の重複面は引き続き許容) / 開口位置から rooms の床に切り欠きを足す
  - **完了条件**: `python -m meshforge convert --config
    samples/building_with_door.json out.stl` で 4 本の壁にドア 1 + 窓 1 が
    開いた watertight STL が出る。既存 `samples/building_minimal.json` /
    `samples/building_with_floor.json` / `samples/dome.png` の md5 は変わら
    ない (`92487afcdafbd4ce2afa8290514e15fc` / `b9743b8784a3e0bd96a524871bad941f`
    / `e1a9015cb867a476c59d3fe9018fd96c`)。

- **Step 12-5**: `roof` (flat) を JSON で受けて壁の上に平らな屋根スラブを乗せる。
  - `building/assemble.py` に `roof` 検証 + shapely Polygon →
    `trimesh.creation.extrude_polygon` でスラブ生成 + `max(walls[].height_mm)`
    ぶん上に持ち上げて concat
  - 屋根 footprint は **明示指定の polygon のみ** (rooms / walls からの自動
    推定はしない)。これで「壁の少し外側に屋根を出したい」「凹形の建物にしたい」
    が同じ仕組みで書ける
  - `kind` は当面 `"flat"` のみ。gable / hip / eaves overhang は Step 12-6+
  - サンプル: `samples/building_with_roof.json` (80×60 mm の最小建物に
    80×60 mm の屋根スラブを厚さ 2 mm で乗せた例)
  - 依存追加なし (`building` extra の shapely を流用)
  - **やらないこと**: gable / hip など勾配屋根・eaves overhang (軒の出) ・
    壁の高さ自動調整 (壁が低い箇所は天井裏に空気層) ・rooms / walls からの
    footprint 自動推定・屋根面と壁との boolean union・複数階の屋根・屋根の
    色 / 材質メタデータ・Streamlit UI 露出
  - **完了条件**: `python -m meshforge convert
    --config samples/building_with_roof.json out.stl` で壁 4 本の上に
    屋根スラブが乗った watertight STL が出る (md5
    `6f5a31afe777fde0b6231389849347a9`)。既存
    `samples/building_minimal.json` / `samples/building_with_floor.json` /
    `samples/building_with_door.json` / `samples/dome.png` の md5 は変わら
    ない (`92487afcdafbd4ce2afa8290514e15fc` /
    `b9743b8784a3e0bd96a524871bad941f` /
    `1f5aec60d29cb9b62665b5e620557c14` /
    `e1a9015cb867a476c59d3fe9018fd96c`)。

- **Step 12-6 以降 (構想)**: 勾配屋根 (gable / hip) と eaves overhang /
  画像→中間 JSON 自動生成 (OpenCV) / Claude API による意味付け / 家具 /
  Streamlit UI への露出。

### Step 13 以降 (構想のみ、ここでは確定しない)
- マルチバンド UI 編集（Streamlit に layers フォームを追加）
- 複数入力対応（複数ページ PDF / 複数 PNG）
- 領域単位（矩形 / マスク）の高さ編集
- デモ GIF の作成と差し込み

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
| Step 10 | GitHub Actions release・PyPI 公開・バージョニング自動化・多言語ドキュメント・GIF 自体の生成・CI/lint/test 基盤 |
| Step 11 | UI フォーム編集・CLI 直接フラグ・領域単位編集・押出方向変更・開口部指定・バンド境界の連続補間・複数ページ PDF |
| Step 12-2 | 角の boolean union・開口部・床スラブ・屋根・家具・画像→JSON 自動生成・複数階・GLB 出力・building 用 `--save-config` |
| Step 12-3 | 壁との boolean union・polygon holes・床ポリゴン同士の重なり検出・壁高さの自動オフセット・床のメタデータ (色/材質)・`label` をメッシュ名に焼く・自動 watertight 化・Streamlit UI 露出 |
| Step 12-4 | 開口同士の重なり検出・建具モデル (枠/ドア板/ガラス)・`kind` 別の色/材質・OpenCV による開口自動抽出・Streamlit UI 露出・角の boolean union・rooms 床への切り欠き反映 |
| Step 12-5 | 勾配屋根 (gable/hip)・eaves overhang・壁の高さ自動調整・rooms/walls からの footprint 自動推定・屋根と壁の boolean union・複数階屋根・屋根の色/材質・Streamlit UI 露出 |

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
