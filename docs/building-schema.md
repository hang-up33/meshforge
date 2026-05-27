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
  "openings":  [ /* Step 12-3 */ ],
  "rooms":     [ /* Step 12-4 */ ],
  "roof":     { /* Step 12-8 */ },
  "furniture": [ /* Step 12-9 */ ]
}
```

- `schema_version`: **必須**。後方互換チェック用。Step 12-1 時点では 1 固定。
- 後段フィールド (`openings` / `rooms` / `roof` / `furniture`) は各 Step が
  来るまでは無視される。`walls` だけが必須キー (Step 12-2 以降)。

## フィールド詳細

### `walls` (Step 12-2 で実装予定)

```jsonc
{
  "start": [x_mm, y_mm],   // 壁の始点 (X-Y 平面、原点は左上)
  "end":   [x_mm, y_mm],   // 壁の終点
  "thickness_mm": 150.0,   // 壁厚
  "height_mm":    2400.0   // 壁高
}
```

### `openings` (Step 12-3 で実装予定)

```jsonc
{
  "wall_index": 0,          // walls[] のインデックス
  "offset_mm":  300.0,      // 壁始点からの距離
  "width_mm":   900.0,
  "height_mm":  2000.0,     // ドアは床から、窓は sill_mm 起点
  "sill_mm":    0.0,        // 窓台高さ (ドアは 0)
  "kind": "door"            // "door" | "window"
}
```

### `rooms` (Step 12-4 で実装予定)

```jsonc
{
  "polygon": [[x,y], [x,y], ...],   // 部屋の床ポリゴン (mm)
  "label":   "LDK",                 // 任意の名称
  "floor_thickness_mm": 100.0
}
```

### `roof` (Step 12-8 で実装予定)

```jsonc
{
  "kind": "gable",            // "gable" | "hip" | "flat"
  "ridge_height_mm": 3500.0,
  "eaves_overhang_mm": 300.0
}
```

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
