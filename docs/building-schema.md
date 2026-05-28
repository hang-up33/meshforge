# Building mode 中間 JSON スキーマ (draft)

`--mode building` (Step 12+) は「平面図 → 建物っぽい 3D」を実現する新モード。
パイプラインの中核には **中間 JSON** があり、

```
[平面図画像] → OpenCV(幾何抽出) → Claude API(意味付け) → 中間 JSON → trimesh で 3D 組立 → GLB/STL
```

の流れになる。中間 JSON は **人手でも書ける** ことを重視し、Step 12-2 では VLM を
通さず手書き JSON を 3D 化できる状態を先に作る。VLM 統合 (Step 12-7) はこの
スキーマに準拠した JSON を生成させるだけ、という設計。

このファイルはスキーマの **正本** として扱う。Step 12-2〜12-9 でフィールドが
増築されるたびにここを更新する。

## 全体構造

```jsonc
{
  "schema_version": 1,
  "scale_mm_per_px": 1.0,         // 元画像 1px が何 mm に相当するか (省略時 1.0)
  "walls":     [ /* Step 12-2 */ ],
  "rooms":     [ /* Step 12-3 */ ],
  "openings":  [ /* Step 12-4 */ ],
  "roof":     { /* Step 12-5 */ },
  "furniture": [ /* Step 12-9 */ ]
}
```

- `schema_version`: **必須**。後方互換チェック用。Step 12-2 時点では 1 固定。
- `scale_mm_per_px`: JSON 内の 2D 座標 (`walls[].start` / `end` など) を mm に
  換算する倍率。手書き JSON は `1.0` のままで座標を mm として書くのが楽。
  OpenCV パイプライン (Step 12-7) が画像 px から JSON を生成する場合のみ
  非 1.0 を入れる。`thickness_mm` / `height_mm` は名前のとおり常に mm で、
  `scale_mm_per_px` は影響しない。
- 後段フィールド (`openings` / `rooms` / `roof` / `furniture`) は各 Step が
  来るまでは無視される。`walls` だけが必須キー (Step 12-2 以降)。

## フィールド詳細

### `walls` (Step 12-2 で実装)

```jsonc
{
  "start": [x, y],         // 壁の始点 (X-Y 平面、原点は左上、単位は scale_mm_per_px に従う)
  "end":   [x, y],         // 壁の終点 (同上)
  "thickness_mm": 150.0,   // 壁厚 (常に mm)
  "height_mm":    2400.0   // 壁高 (常に mm)
}
```

実装 (`python/meshforge/building/assemble.py`):
- `start` → `end` を中心線とし、`thickness_mm` の厚み × `height_mm` の高さの
  直方体を 1 本の壁として組み立てる。Z=0 が床、Z=`height_mm` が天井。
- 隣接する壁の角はそのまま直方体の重なりとして残す (boolean union しない)。
  スライサは内部の重複面を問題なく塗り潰す。union による厳密な watertight
  化は Step 12-3 で開口部をくり抜くタイミングで manifold3d 導入とまとめて
  検討する。
- 0 長壁・厚さ/高さが正の有限数でないものは `config error` で reject。

実行例:

```bash
.venv/bin/python -m meshforge convert \
  --config samples/building_minimal.json out.stl
```

`samples/building_minimal.json` は 80 mm × 60 mm × 24 mm のミニ建物 (壁厚
4 mm、4 本) で、印刷可能なサイズの最小例として置いている。

### `rooms` (Step 12-3 で実装)

```jsonc
{
  "polygon": [[x,y], [x,y], ...],   // 部屋の床ポリゴン (mm)
  "label":   "LDK",                 // 任意の名称 (省略可)
  "floor_thickness_mm": 100.0
}
```

実装 (`python/meshforge/building/assemble.py`):
- `polygon` を shapely Polygon にして `trimesh.creation.extrude_polygon`
  で z=0..floor_thickness_mm の柱状メッシュにする。壁の z=0..height_mm と
  z 範囲がオーバーラップするので、壁基部の内部に床面が埋まる形になる。
  walls 同士の角と同じく boolean union はしない (スライサが塗り潰す)。
- `label` はメッシュには焼かない。Step 12-9 (家具配置) で room_index 経由の
  目印として参照する想定で残してある。
- 凸でも凹でもよい (L 字・コの字 OK)。穴 (holes) には未対応。
- 自己交差や 0 面積は shapely の `is_valid` が拒否し、
  `explain_validity` の文字列を添えて `ValueError` を返す。
- 任意キー (`rooms` 全体を省略してよい)。walls だけの JSON は Step 12-2 と
  完全に同じ出力 (md5 一致) を返す。

依存:
- shapely + mapbox_earcut が必要 (`pip install -e '.[building]'`)。
  dam モードしか触らないユーザには課さない。

実行例:

```bash
.venv/bin/python -m meshforge convert \
  --config samples/building_with_floor.json out.stl
```

`samples/building_with_floor.json` は 80×60 mm の外周壁を 1 本の内壁で
2 部屋に区切り、各部屋に厚さ 2 mm の床スラブを敷いた最小例。

### `openings` (Step 12-4 で実装)

```jsonc
{
  "wall_index": 0,          // walls[] のインデックス
  "offset_mm":  300.0,      // 壁始点からの距離 (mm)
  "width_mm":   900.0,
  "height_mm":  2000.0,     // ドアは床から、窓は sill_mm 起点
  "sill_mm":    0.0,        // 窓台高さ (省略可、デフォルト 0)
  "kind": "door"            // "door" | "window"
}
```

実装 (`python/meshforge/building/assemble.py`):
- `wall_index` で参照した壁の bounding box から、`offset_mm` 位置に `width_mm`
  × 壁厚 × `height_mm` のくり抜き box を作り、`manifold3d` 経由の trimesh
  boolean difference で差し引く。複数の開口は `trimesh.boolean.union` で
  まとめてから 1 回の difference をかける。
- くり抜き box の y 方向は壁厚 +2 mm にして boolean の coplanar 面を回避
  (manifold3d は coplanar に強いが、座標誤差で薄い残骸が出るのを防ぐ安全側
  マージン)。
- `sill_mm` は optional。`kind=door` の場合は省略するか 0 で書く
  (door + sill_mm > 0 は意味的に衝突するので `config error`)。
- 検証ルール:
  - `wall_index` は walls 範囲内の整数
  - `offset_mm`, `width_mm`, `height_mm` は正の有限数
  - `sill_mm` は 0 以上の有限数 (省略時 0)
  - `kind` は `"door"` | `"window"` のみ
  - `offset_mm + width_mm <= 壁長 (mm)` / `sill_mm + height_mm <= 壁高`
  - 同じ壁内で開口同士が重なるケースは validate しない (boolean union が
    そのまま吸収する)
- `openings` キー全体を省略するか空配列 `[]` で渡せば「開口なし」として
  Step 12-2/12-3 とバイト一致の STL を返す。

依存:
- `manifold3d` が必要 (`pip install -e '.[building]'`)。dam モードや
  openings 無しの building JSON では import されない。

実行例:

```bash
.venv/bin/python -m meshforge convert \
  --config samples/building_with_door.json out.stl
```

`samples/building_with_door.json` は 80×60 mm の最小建物 (壁厚 4 mm、4 本)
にドア (12×16 mm) と窓 (16×8 mm、sill 10 mm) を 1 つずつ開けた例。

### `roof` (Step 12-5 で実装)

```jsonc
{
  "kind": "flat",                     // 現状 "flat" のみ。gable/hip は将来
  "polygon": [[x,y], [x,y], ...],     // 屋根の外形 (mm、scale_mm_per_px 適用)
  "thickness_mm": 2.0
}
```

実装 (`python/meshforge/building/assemble.py`):
- `polygon` を shapely Polygon にして `trimesh.creation.extrude_polygon` で
  柱状メッシュにし、`max(walls[].height_mm)` ぶん上に持ち上げる (壁の最大
  高さの上に乗る平らな屋根)。
- 屋根の z 範囲は `max(walls[].height_mm)..max(walls[].height_mm) + thickness_mm`。
  壁天端とのオーバーラップは 0 で、内部の重複面は基本発生しない (壁ごとに
  高さが違うと低い壁の上に空気層ができるが、それは入力 JSON の責任)。
- 屋根 footprint は **明示指定のみ** (rooms / walls からの自動推定はしない)。
  これで「壁の少し外側に屋根を出したい」「凹形の建物にしたい」が同じ
  仕組みで書ける。eaves overhang を別フィールドで持つのは Step 12-6+。
- 自己交差や 0 面積は shapely の `is_valid` が拒否し、`explain_validity`
  の文字列を添えて `ValueError`。
- 任意キー (`roof` 全体を省略してよい)。roof 無しの JSON は Step 12-4 と
  バイト一致の STL を返す。

依存:
- shapely + mapbox_earcut が必要 (`pip install -e '.[building]'`)。
  rooms と同じ extra に乗っているので追加インストールは不要。

実行例:

```bash
.venv/bin/python -m meshforge convert \
  --config samples/building_with_roof.json out.stl
```

`samples/building_with_roof.json` は 80×60 mm の最小建物 (壁厚 4 mm、4 本)
の上に厚さ 2 mm の屋根スラブを乗せた例。屋根 footprint は壁外周と同じ
80×60 mm にしてある。

### `furniture` (Step 12-9 で実装予定)

```jsonc
{
  "room_index": 0,             // rooms[] のインデックス
  "kind": "bed",               // "bed"|"toilet"|"sink"|"kitchen"|"sofa"|"table"|"bath" 等
  "position_mm": [x, y],
  "size_mm":     [w, d],
  "rotation_deg": 0
}
```

## API キー (Step 12-5 で実装予定)

VLM 呼び出しに使う Anthropic API キーの取得順位 (予定):

1. 環境変数 `ANTHROPIC_API_KEY`
2. `~/.config/meshforge/anthropic_key` (改行のみ含むテキストファイル)
3. Streamlit secrets

どれも見つからない場合は `RuntimeError` で日本語メッセージを返す。

## やらないこと (Step 12 全体スコープ)

- 階層構造 (2 階建て以上)
- 構造材 (柱・梁) のモデリング
- 寸法線・テキストラベルの読み取り
- 開口部の細かい建具 (引き戸 vs 開き戸の作画区別)
- 屋根の L 字形状やドーマー
- 家具モデルのライブラリ取り込み (常に直方体)
