# 開発の歩み (progress)

第三者向けに「meshforge をどう進めたか」を 1 ファイルで見せるためのドキュメント。
計画の正本は [`docs/development-plan.md`](development-plan.md)、技術的な
変更履歴は [`CHANGELOG.md`](../CHANGELOG.md)。本ファイルはそのあいだの
**「タスク単位の歩み」** を担当する。

## 全体像 (一目で)

- **方針**: 設計書通りの 3 層 (Avalonia + C# + Python) を最初から組まず、
  Python スクリプト 1 本の「PNG → STL」から始めて 1 ステップずつ動く成果物を
  積み上げる。
- **ループ**: Claude が feature branch に実装 → PR → Codex が review →
  Claude が反映 → マージ。スラッシュコマンド `/codex-review` /
  `/codex-loop` で半自動化。
- **デモ**: <https://meshforge.streamlit.app/> (Step 6 で着地、以降ずっと
  公開デモを伸ばし続けている)。
- **ステップ数**: 2026-05-24 〜 2026-05-29 の 6 日間で Step 1 〜 12-13 まで
  到達 (31 PR / 約 90 コミット)。

## サマリ表

| # | タスク | PR | マージ日 | 一言 |
|---|---|---|---|---|
| 1 | PNG → STL 最小スクリプト | [#4](https://github.com/hang-up33/meshforge/pull/4) | 2026-05-24 | `numpy + pillow + trimesh` の 50 行未満で土台が立つ |
| 2 | `--invert` / `--threshold` | [#5](https://github.com/hang-up33/meshforge/pull/5) | 2026-05-25 | 黒壁/白床の平面図から壁が立つ STL に |
| 3 | PDF 入力対応 | [#7](https://github.com/hang-up33/meshforge/pull/7) | 2026-05-25 | PyMuPDF で 1 ページ目をラスタライズして既存処理に流す |
| 4 | 設定の JSON 化 | [#8](https://github.com/hang-up33/meshforge/pull/8) | 2026-05-25 | `--config` / `--save-config` で「同じ JSON から同じ STL」 |
| 5 | パッケージ化 + `convert` サブコマンド | [#9](https://github.com/hang-up33/meshforge/pull/9) | 2026-05-25 | 1 ファイルを `python/meshforge/` に分割。UI から呼べる土台 |
| 6 | Streamlit 簡易 GUI | [#10](https://github.com/hang-up33/meshforge/pull/10) | 2026-05-25 | Avalonia は保留。ブラウザで動くものを最速で確保 |
| (deploy) | Streamlit Cloud デプロイ | [#11](https://github.com/hang-up33/meshforge/pull/11) / [#12](https://github.com/hang-up33/meshforge/pull/12) | 2026-05-26 | `requirements.txt` を直書きして uv の制約を回避 |
| 7 | 3D プレビュー (streamlit-stl) | [#13](https://github.com/hang-up33/meshforge/pull/13) | 2026-05-26 | Convert 後にその場で回転/ズーム |
| 8 | パラメータプリセット UI | [#14](https://github.com/hang-up33/meshforge/pull/14) | 2026-05-26 | Floor plan / Logo / Terrain / Custom |
| 9 | UI エラー処理強化 | [#15](https://github.com/hang-up33/meshforge/pull/15) | 2026-05-26 | PyMuPDF 不在 / 壊れた PDF / 巨大入力を `st.error` で日本語化 |
| 10 | OSS リリース整備 | [#16](https://github.com/hang-up33/meshforge/pull/16) | 2026-05-26 | LICENSE (MIT) / CONTRIBUTING / CHANGELOG / Demo セクション |
| 11 | 高さレイヤー (マルチバンド閾値) | [#17](https://github.com/hang-up33/meshforge/pull/17) | 2026-05-27 | 1 枚の画像から「外壁 10mm / 内壁 5mm / 開口 0mm」を取り出す |
| (tooling) | `/codex-loop` 自走ループ | [#18](https://github.com/hang-up33/meshforge/pull/18) | 2026-05-27 | PR → @codex review → 反映 → 再依頼 を「指摘 0」まで自走 |
| 12-1 | `--mode building` 骨格 + JSON スキーマ | [#19](https://github.com/hang-up33/meshforge/pull/19) | 2026-05-27 | 別パイプラインの仕様を [`docs/building-schema.md`](building-schema.md) で固定 |
| 12-2 | `walls[]` → 壁 STL | [#20](https://github.com/hang-up33/meshforge/pull/20) | 2026-05-27 | trimesh で箱を並べるだけの最小実装 |
| 12-3 | `rooms[]` → 床スラブ | [#21](https://github.com/hang-up33/meshforge/pull/21) | 2026-05-28 | shapely + extrude_polygon。`building` extra に依存分離 |
| 12-4 | `openings[]` → ドア / 窓くり抜き | [#22](https://github.com/hang-up33/meshforge/pull/22) | 2026-05-28 | manifold3d で boolean difference |
| 12-5 | `roof` (flat) | [#23](https://github.com/hang-up33/meshforge/pull/23) | 2026-05-28 | 屋根 footprint は明示 polygon のみ (自動推定しない) |
| 12-6 | `roof.kind = gable` | [#24](https://github.com/hang-up33/meshforge/pull/24) | 2026-05-28 | 6 頂点 8 面の三角柱を numpy で手組み |
| 12-7 | `roof.kind = hip` (寄棟) | [#25](https://github.com/hang-up33/meshforge/pull/25) | 2026-05-28 | gable と同じ rect + ridge_axis、棟線を内側に引き込む |
| 12-8 | `roof.kind = pyramidal` (四角錐) | [#26](https://github.com/hang-up33/meshforge/pull/26) | 2026-05-28 | 正方形 footprint 限定。5 頂点 6 面 |
| 12-9 | `furniture[]` | [#27](https://github.com/hang-up33/meshforge/pull/27) | 2026-05-28 | room_index で部屋に紐づく直方体家具 |
| 12-10 | Streamlit UI に building モード | [#28](https://github.com/hang-up33/meshforge/pull/28) | 2026-05-28 | `st.tabs` で「Heightmap (dam)」「Building」の 2 タブ |
| 12-11 | `extract-walls` サブコマンド | [#29](https://github.com/hang-up33/meshforge/pull/29) | 2026-05-29 | OpenCV + HoughLinesP で PNG/PDF → `walls[]` JSON |
| 12-12 | `walls[]` の axis-aligned マージ | [#30](https://github.com/hang-up33/meshforge/pull/30) | 2026-05-29 | Canny が出す両 edge を 1 本に collapse。10 → 5 walls |
| 12-13 | UI に `extract-walls` を露出 | [#31](https://github.com/hang-up33/meshforge/pull/31) | 2026-05-29 | Building タブに "Extract from image" radio |

## フェーズで読む (4 つの山)

```
Step 1〜4:   Python 1 ファイルで「画像→STL」を成立
Step 5〜10:  パッケージ化→Streamlit UI→公開デモ→OSS 整備
Step 11:    「編集可能 3D」へ最初の踏み込み (multi-band)
Step 12-*:  別パイプライン「building」を 13 連続 PR で積み上げ
```

### フェーズ1: コアパイプラインを最短経路で (Step 1〜4)

「3 層アーキテクチャを後回しにして、まずは Python 1 ファイルで PNG → STL を
動かす」という方針転換から始まる。Step 4 で JSON 化したところで「同じ JSON から
同じ STL が再現できる」状態になり、これが後の中間 3D モデルの源流になる。

### フェーズ2: パッケージ化と UI 公開 (Step 5〜10)

Step 5 で 1 ファイルを `python/meshforge/` パッケージに分け、Step 6 で
Avalonia ではなく **Streamlit** に切り替える判断。ブラウザで動く成果物を
最速で取って、Step 11 で公開デモを Streamlit Community Cloud に乗せる。
Step 7 (3D プレビュー) → Step 8 (プリセット) → Step 9 (エラー処理) →
Step 10 (LICENSE / CHANGELOG) で「他人が触っても壊れない」状態へ。

### フェーズ3: 編集可能 3D の最初の一歩 (Step 11)

明度を複数バンドに分割して「バンドごとの高さ」を JSON で指定可能に。
これだけで 1 枚の平面図から「外壁 10mm / 内壁 5mm / 開口 0mm」のような
階層を取り出せ、「JSON を編集して再生成する」体験の最小実例になる。
UI 拡張はあえてしない (CLI の JSON 経由のみ)。

### フェーズ4: building モードを 13 連続 PR で組む (Step 12-1〜12-13)

Step 12 から「画像の明度を高さ化する」とは別の **第二パイプライン** に
入る。中間 JSON (`walls` / `rooms` / `openings` / `roof` / `furniture`) を
trimesh で組み立てる流れ。**やらないこと** を毎ステップ明示しながら、

1. 手書き JSON の各セクションを 1 つずつ実装 (12-2 walls → 12-3 rooms →
   12-4 openings → 12-5/6/7/8 roof 4 種 → 12-9 furniture)
2. Streamlit UI に出す (12-10)
3. 画像 → JSON 自動抽出を最小から積む (12-11 線検出 → 12-12 マージ →
   12-13 UI 露出)

の順で進めた。Step 12-13 まで来た時点で「PNG 平面図をアップロードして
そのまま STL がダウンロードできる」というプロジェクト本来の MVP デモが
ブラウザで完結する。

## ステップ詳細

各ステップは「なぜ / 何を作った / やらないこと / 完了条件 / PR」の 5 要素。
完了条件は [`docs/development-plan.md`](development-plan.md) と同じものを
要約している (md5 ハッシュ等の詳細は plan を参照)。

### Step 1: 最小スクリプト「PNG → STL」 [#4](https://github.com/hang-up33/meshforge/pull/4)

- **なぜ**: 設計書通りの 3 層を一度に組むと「動かない」期間が長すぎる。
  最小のパイプラインで動く成果物を確保する。
- **作ったもの**: `python/heightmap_to_stl.py` 1 ファイル。
  `numpy + pillow + trimesh` で PNG → 高さマップ → 押出メッシュ → バイナリ STL。
- **やらないこと**: フォルダ階層 / テスト / C# / 設定ファイル / ロギング / 複数入力。
- **完了条件**: コマンド 1 発で PNG → STL ができる。

### Step 2: `--invert` / `--threshold` 追加 [#5](https://github.com/hang-up33/meshforge/pull/5)

- **なぜ**: 建築平面図 (黒壁 / 白床) を入れたとき、壁が **凹む** ではなく
  **立ち上がる** STL がほしい。
- **作ったもの**: 明暗反転とアンチエイリアス除去で垂直な壁にするオプション。
- **完了条件**: 建築ジオラマ STL がスライサ (Bambu Lab Studio) で開ける。

### Step 3: PDF 入力対応 [#7](https://github.com/hang-up33/meshforge/pull/7)

- **なぜ**: 設計書の MVP デモは「平面図 PDF → STL」。
- **作ったもの**: PyMuPDF で 1 ページ目を PNG ラスタライズ → 既存パイプラインに流す。
  `--dpi` で解像度指定。`[pdf]` extra として分離 (PNG だけ使う人に課さない)。
- **完了条件**: 建築平面図 PDF から STL が出る。

### Step 4: 設定の JSON 化 [#8](https://github.com/hang-up33/meshforge/pull/8)

- **なぜ**: 「編集可能 3D」の核は「中間状態を JSON で保存・再現できる」こと。
  ここで JSON が中間表現の出発点になる。
- **作ったもの**: `--config` / `--save-config`。`pixel_mm` / `max_height_mm` /
  `base_mm` などジオメトリ定数も JSON で上書き可能。
- **完了条件**: JSON 1 枚で同じ STL を再生成できる。

### Step 5: パッケージ化 + `convert` サブコマンド [#9](https://github.com/hang-up33/meshforge/pull/9)

- **なぜ**: UI から再利用するには 1 ファイル構成では辛い。
- **作ったもの**: `python/meshforge/` に heightmap / mesh / stl / cli で分割。
  `python -m meshforge convert ...` で呼ぶ形に。`pyproject.toml` で editable install。
- **完了条件**: リグレッションなくパッケージ経由で同じ STL が出る。

### Step 6: Streamlit 簡易 GUI [#10](https://github.com/hang-up33/meshforge/pull/10)

- **判断**: Avalonia + C# は将来の Step として **保留** し、ブラウザ UI を
  Streamlit で最速で乗せる。コアが Python パッケージになっているので、
  Avalonia 移行時は subprocess で叩く形に切り替えれば良い。
- **作ったもの**: `python/meshforge/ui_streamlit.py`。PNG / PDF アップロード →
  パラメータ調整 → Convert で STL ダウンロード。CLI とバイト一致。
- **デプロイ**: 直後 [#11](https://github.com/hang-up33/meshforge/pull/11) /
  [#12](https://github.com/hang-up33/meshforge/pull/12) で Streamlit
  Community Cloud デプロイ整備 (`requirements.txt` の直書きで uv 制約を回避)。
- **やらないこと**: Avalonia/C# 移行 / 3D プレビュー / 複数ファイル一括 / 認証。
- **完了条件**: ブラウザから STL がダウンロードでき、CLI とバイト一致。

### Step 7: 3D プレビュー [#13](https://github.com/hang-up33/meshforge/pull/13)

- **なぜ**: invert / threshold が想定通り当たっているかをダウンロード前に確認したい。
- **作ったもの**: `streamlit-stl` (three.js ベース) を Convert 結果表示に追加。
  回転 / ズームできる。
- **やらないこと**: プレビュー上の編集操作 / 複数ビュー / サーバ側レンダリング。
- **完了条件**: Convert 後にブラウザで STL を回転 / ズームできる。

### Step 8: パラメータプリセット UI [#14](https://github.com/hang-up33/meshforge/pull/14)

- **なぜ**: Convert ごとに各パラメータをゼロから合わせるのが辛い。
- **作ったもの**: `st.selectbox` で Floor plan / Logo / Terrain / Custom を切替。
  `st.session_state` 経由でフォーム widget の値を上書き。
- **やらないこと**: プリセット追加 UI / JSON 保存 / `pixel_mm` の
  プリセット化 / CLI 展開 (CLI は引き続き `--config` JSON で再現)。
- **完了条件**: プリセット切替で widget 値が連動し、Convert で反映される。

### Step 9: UI エラー処理強化 [#15](https://github.com/hang-up33/meshforge/pull/15)

- **なぜ**: OSS で他人が触っても壊れないように。
- **作ったもの**: PyMuPDF 不在 / 壊れた / パスワード保護 PDF / 0 ページ /
  8 Mpx 超の巨大入力 / DPI 上限 600 を `st.error` で日本語表示。
  Convert ボタンを文脈で disable。
- **やらないこと**: CLI 側のエラー整理 / 多言語化 / magic-byte 検証 /
  自動ダウンサンプリング。
- **完了条件**: 想定エラーで traceback を出さず日本語メッセージが出る。

### Step 10: OSS リリース整備 [#16](https://github.com/hang-up33/meshforge/pull/16)

- **なぜ**: Streamlit Community Cloud で URL 公開済みなので、外から見て
  使える状態にメタファイルを整える。
- **作ったもの**: `LICENSE` (MIT) / `CONTRIBUTING.md` / `CHANGELOG.md`
  (Step 1〜9 を `0.1.0` としてまとめ) / README に Demo セクション。
- **やらないこと**: GitHub Actions release / PyPI 公開 / バージョニング
  自動化 / 多言語ドキュメント / CI/lint/test 基盤。
- **完了条件**: GitHub 上で MIT バッジが付き、README から CONTRIBUTING /
  CHANGELOG / Demo URL に辿れる。

### Step 11: 高さレイヤー (マルチバンド閾値) [#17](https://github.com/hang-up33/meshforge/pull/17)

- **なぜ**: 「編集可能 3D」のビジョン (要素ごとの高さをパラメータで持つ
  中間モデル) に向けた最小の一歩。
- **作ったもの**: `to_heights` に `layers: list[dict] | None` 引数を追加。
  `np.digitize` でバンド判定 → バンドの `height_mm` を返す。
  `samples/multilayer.json` (4 バンド例)。
- **やらないこと**: UI フォーム編集 / CLI 直接フラグ / 領域単位編集 /
  バンド境界の連続補間。
- **完了条件**: 階段状の STL (複数 Z 平坦面) が出る。既存サンプル
  (layers なし) は Step 10 とバイト一致。

### (Tooling) `/codex-loop` 自走ループ [#18](https://github.com/hang-up33/meshforge/pull/18)

- **なぜ**: PR 後の Codex Cloud レビューに 1 回ずつ手動で反応するのが
  面倒。コミット境界の取りこぼし (秒未満) で再 fetch が空になる事故も発生。
- **作ったもの**: `gh pr create` 直後に呼ぶ自走ループ。
  `@codex review` 投稿 → ポーリング → 反映 → 再依頼 を Codex が指摘 0 を
  返すまで繰り返す。SINCE を 1 秒戻して境界取りこぼしを防ぐ。

### Step 12-1: building モード骨格 [#19](https://github.com/hang-up33/meshforge/pull/19)

- **なぜ**: Step 11 までは「画像の明度を高さ化する単一押し出し」で、
  「平面図 → 建物 3D」をやるには別パイプラインが要る。
- **作ったもの**: `--mode building` の CLI 受付と中間 JSON スキーマ仕様
  ([`docs/building-schema.md`](building-schema.md))。`run_building` は
  `NotImplementedError` のスタブ。`docs/screenshots/editor.png` を
  README に追加し UI 変更時のスクショ運用も規約化 (AGENTS.md)。
- **完了条件**: スキーマ仕様が固まり、CLI が `--mode building --config` を
  受け付ける (実体は次 Step から)。

### Step 12-2: 手書き JSON `walls[]` → 壁 STL [#20](https://github.com/hang-up33/meshforge/pull/20)

- **作ったもの**: `building/assemble.py` で walls を検証して trimesh で
  箱化 → concat。CLI は `convert --config building.json out.stl` の
  output positional も受け付け。`samples/building_minimal.json`
  (80×60×24 mm の箱)。
- **やらないこと**: 角の boolean union / 開口部 / 床 / 屋根 / 家具 /
  画像→JSON / 複数階 / GLB 出力 / building 用 `--save-config`。
- **完了条件**: 4 本の壁が立った watertight STL。dam モードの dome.png
  出力は md5 不変。

### Step 12-3: `rooms[]` → 床スラブ [#21](https://github.com/hang-up33/meshforge/pull/21)

- **作ったもの**: shapely Polygon → `trimesh.creation.extrude_polygon` で
  柱状メッシュ。`samples/building_with_floor.json` (2 部屋)。
  `shapely + mapbox_earcut` を `building` extra に分離。
- **やらないこと**: 壁との boolean union / polygon holes / 床ポリゴン
  同士の重なり検出 / 壁高さの自動オフセット / 床のメタデータ /
  自動 watertight 化 / Streamlit UI 露出。

### Step 12-4: `openings[]` → ドア / 窓くり抜き [#22](https://github.com/hang-up33/meshforge/pull/22)

- **作ったもの**: 壁単位に `trimesh.difference` でくり抜き、複数開口は
  `trimesh.boolean.union` でまとめてから 1 回の difference。
  `samples/building_with_door.json` (ドア 1 + 窓 1)。`manifold3d` を
  `building` extra に追加。
- **やらないこと**: 開口同士の重なり検出 / 建具モデル (枠 / ドア板 /
  ガラス) / 色・材質メタデータ / OpenCV 自動抽出 / UI 露出。

### Step 12-5: `roof` (flat) [#23](https://github.com/hang-up33/meshforge/pull/23)

- **設計判断**: 屋根 footprint は **明示 polygon のみ**。
  rooms / walls からの自動推定はしない。これで「壁の少し外側に屋根を
  出したい」「凹形の建物」が同じ仕組みで書ける。
- **作ったもの**: shapely → `extrude_polygon` で屋根スラブ →
  `max(walls.height_mm)` ぶん持ち上げて concat。
  `samples/building_with_roof.json`。
- **やらないこと**: 勾配屋根 / eaves overhang / 自動推定 / boolean
  union / 複数階屋根 / 色・材質。

### Step 12-6: `roof.kind = "gable"` (切妻) [#24](https://github.com/hang-up33/meshforge/pull/24)

- **作ったもの**: `_validate_roof` を kind 別に分岐、`_assemble_gable_roof`
  は shapely を経由せず **6 頂点 8 面の三角柱を numpy で手組み**
  (追加依存なし)。`polygon` は 4 隅の axis-aligned 矩形に限定。
- **やらないこと**: hip / mansard / 任意ポリゴンの gable (L 字・凹形) /
  複数棟線 / 棟軸の自動推定。

### Step 12-7: `roof.kind = "hip"` (寄棟) [#25](https://github.com/hang-up33/meshforge/pull/25)

- **作ったもの**: gable と検証ロジックを共有しつつ「`ridge_axis` が bbox の
  長辺と厳密一致」を追加要求。6 頂点 8 面で手組み、棟線の両端を bbox 内側に
  短辺の半分ぶん引き込む。正方形 footprint は次 Step の pyramidal で別扱い。

### Step 12-8: `roof.kind = "pyramidal"` (四角錐) [#26](https://github.com/hang-up33/meshforge/pull/26)

- **作ったもの**: W==D の正方形 footprint 限定。底 4 + 頂点 1 の 5 頂点・
  底 2 + 側面 4 の 6 面で手組み。`ridge_axis` は無し。
  `samples/building_with_pyramidal_roof.json`。
- **やらないこと**: 不等辺四角錐 (W≠D) / mansard / 鞍型。

### Step 12-9: `furniture[]` [#27](https://github.com/hang-up33/meshforge/pull/27)

- **作ったもの**: `room_index` で rooms に紐づく直方体家具。
  `trimesh.creation.box` → Z 軸回転 → `floor_top + height_mm/2` に配置。
  `kind` は文字列必須 (Step 12-9 ではメッシュに影響しないが、後で kind 別
  形状の余地を残す)。
- **やらないこと**: kind 別形状 (cylindrical toilet 等) / boolean union /
  room polygon 内 bbox 検査 / 家具同士の重なり検出 / 自動配置。

### Step 12-10: Streamlit UI に building タブ [#28](https://github.com/hang-up33/meshforge/pull/28)

- **作ったもの**: `run()` から `build_mesh(spec) -> trimesh.Trimesh` を抽出
  (CLI と UI が同じ関数を呼ぶので md5 完全一致が自動的に成立)。
  `st.tabs(["Heightmap (dam)", "Building"])` で 2 タブ化。Building タブは
  JSON アップロード → `build_mesh` → STL プレビュー / ダウンロード。
- **やらないこと**: building JSON のフォーム編集 / プリセット / テンプレ
  生成 / 画像 → JSON UI (次 Step) / 複数 JSON 同時変換。

### Step 12-11: `extract-walls` サブコマンド [#29](https://github.com/hang-up33/meshforge/pull/29)

- **なぜ**: 画像 → 中間 JSON 自動生成の最小一歩。
- **作ったもの**: `building/extract.py` に `extract_walls()`。
  `cv2.threshold` → `cv2.Canny` → `cv2.HoughLinesP` で線分検出 →
  walls[] に変換。`opencv-python-headless` を `vision` extra に分離。
  `samples/floor_plan_simple.png` を `make_sample.py` に追加。
- **やらないこと**: 線分マージ (次 Step) / 壁厚・壁高の自動検出 /
  rooms / openings / roof / furniture の自動抽出 / Claude API 意味付け /
  Streamlit UI 露出 (Step 12-13)。

### Step 12-12: `walls[]` 線分マージ [#30](https://github.com/hang-up33/meshforge/pull/30)

- **なぜ**: Canny が壁の両 edge を別線として返すため walls 数が約 2 倍に
  なる挙動を吸収。
- **作ったもの**: `_merge_axis_aligned()`。水平 / 垂直 / 斜めに分類し、
  水平は y 中央値・垂直は x 中央値で greedy にクラスタリング。
  cluster 追加判定は「直交方向の近さ + 軸方向の overlap or gap ≦
  `--merge-gap-mm`」(ドア開口や別部屋の壁が誤って繋がるのを防ぐ)。
  内部処理は mm 単位 (`--pixel-mm` 変えても tolerance の意味は変わらない)。
- **やらないこと**: 任意角度 / 斜め線の merge / 複数 cluster をまたぐ merge。
- **完了条件**: `samples/floor_plan_simple.png` で walls 数が 10 → 5 に
  減る。merged JSON を convert に流すと watertight (verts=40 faces=60)。

### Step 12-13: UI に `extract-walls` を露出 [#31](https://github.com/hang-up33/meshforge/pull/31)

- **作ったもの**: Building タブ先頭に `st.radio("Source", ["Upload JSON",
  "Extract from image"])`。"Extract from image" を選ぶと、画像
  アップロード → extract パラメータ form → `Extract & Build` で
  `extract_walls()` 呼び出し → 中間 JSON ダウンロードボタン + そのまま
  `build_mesh` → STL プレビュー / ダウンロード。
- **やらないこと**: フォーム編集 (手動 walls 追加) / Extract パラメータ
  プリセット / Claude API 連携 / 複数ページ PDF / 抽出結果のブラウザ上
  可視化 (line overlay 等)。
- **完了条件**: ブラウザの操作と CLI の `extract-walls` → `convert
  --config` がバイト一致する STL を出す。既存 9 サンプル
  (building_minimal / floor / door / roof / gable / hip / pyramidal /
  furniture / dome.png) の md5 は不変。

### Step 12-14: extract 結果の line overlay [#33](https://github.com/hang-up33/meshforge/pull/33)

- **なぜ**: threshold / min_length / merge パラメータの試行錯誤を画像で
  目視確認できるようにする。
- **作ったもの**: `_render_extract_overlay()`。Extract & Build 後に入力画像 +
  検出 `walls[]` の中心線 (赤、2 px) を `st.image` で重ねて表示。
  README 用に `docs/screenshots/overlay-preview.png` も追加。
- **やらないこと**: 編集 UI (drag) / kind 別色分け / rooms / openings の overlay。
- **完了条件**: `floor_plan_simple.png` で `extracted walls=5` の success 直後に
  5 本の赤線 overlay が出る。CLI とバイト一致 (md5 `5d84a7…`)。9 サンプル不変。

### Step 12-15: `extract-walls --with-rooms` [#34](https://github.com/hang-up33/meshforge/pull/34)

- **なぜ**: 検出した walls の閉路から `rooms[]` を自動生成し、床スラブまで
  一気に出せるようにする。
- **作ったもの**: `_extract_rooms_from_walls()`。shapely `snap` → `unary_union`
  → `polygonize` で閉路を polygon 化し rooms[] に詰める (label は `room_<i>`)。
  CLI `--with-rooms` / `--room-floor-thickness-mm` / `--room-snap-tol-px`、
  UI form + overlay に rooms polygon (青、1 px) を追加。
- **やらないこと**: 部屋の意味分類 / 家具自動配置 / 凹形の特別扱い / snap tol
  自動推定 / 斜め壁 merge。
- **完了条件**: `floor_plan_simple.png --with-rooms` で walls=5 / rooms=2。
  convert で watertight (verts=56 faces=84、md5 `54168e…`)。`--with-rooms`
  無しは 12-14 と完全一致 (md5 `5d84a7…`)。9 サンプル不変。

### Step 12-16: 斜め線分のマージ

- **なぜ**: Step 12-12 は axis-aligned only で斜め壁を素通ししていたため、
  斜め壁が両 edge 2 本のまま残っていた。
- **作ったもの**: `_merge_diagonals()` / `_collapse_diagonal()`。各線分を
  自身の向き θ で perpendicular offset `d` / axial position `t` に分解し、
  「角度差 + |d 差| + 軸方向 gap」で greedy クラスタリング → 平均角の線上に
  collapse。既存 merge flag を流用し新フラグなし。テスト入力
  `samples/floor_plan_diagonal.png` (`floorplan_diagonal` kind) を追加。
- **やらないこと**: 壁厚自動検出 / 複数 cluster をまたぐ merge / openings /
  roof / furniture 自動抽出 / Claude API 意味付け / UI 新 widget。
- **完了条件**: `floor_plan_diagonal.png` で walls=5 (`--no-merge` は 11)。
  convert で watertight (verts=40 faces=60、md5 `fab9da…`)。`floor_plan_simple`
  は斜め線が無いので 12-15 と完全一致 (md5 `5d84a7…` / `54168e…`)。9 サンプル不変。

## 開発スタイルの原則 (第三者向け説明用)

- **1 ステップ = 動く成果物 1 個**: 抽象化やテスト基盤は「必要になってから」。
  各 PR で「やらないこと」を明示し、将来 Step に押し出す。
- **やらないことリスト**: 各 Step の `development-plan.md` 記載は厳守。
  Codex レビューでも「段階性違反 (やらないことを勝手に足していないか)」を
  重要観点に置く。
- **回帰防止は md5 で**: building モードの各 Step では、以前のサンプル
  STL の md5 が変わらないことを完了条件に含める (動作確認の代わりに
  バイト一致で確認)。
- **依存は extra で分離**: `[pdf]` / `[ui]` / `[building]` / `[vision]`
  を分け、使わないユーザーに重い依存 (PyMuPDF / shapely / manifold3d /
  OpenCV) を課さない。
- **レビューは Codex Cloud に自走**: `/codex-loop` で「指摘 0」になるまで
  自動でラウンドを回す。
- **公開デモは Streamlit Community Cloud**: `main` への push で自動再
  デプロイ。`requirements.txt` を直書き (uv / Poetry の制約を回避)。

## 次に何を作るか (構想)

[`docs/development-plan.md`](development-plan.md) の Step 12-17 以降 /
Step 13 構想を参照。主な未踏:

- 壁厚自動検出 / openings / roof の自動抽出 (OpenCV)
- **Claude API による意味付け** (kind 推定: door / window / wall 自動判別)
- kind 別の家具形状 (cylindrical toilet 等)
- Streamlit UI への building JSON フォーム編集
- extract 結果のブラウザ上での可視化 (line overlay)
- マルチバンド UI 編集 / 複数ページ PDF / 領域単位の高さ編集
