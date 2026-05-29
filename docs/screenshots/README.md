# docs/screenshots/

README.md に貼る UI スクショの置き場。

## ファイル

- `editor.png` — Streamlit UI の主要機能画面。Step 12-13 以降は Building タブ
  の "Extract from image" セクション (未アップロード状態) を写している。
  dam タブのフローは README 本文で別途案内する。
- `overlay-preview.png` — Step 12-14 で追加した extract overlay の見た目を
  オフラインで再現したもの。`_render_extract_overlay` と同じ
  `load_grayscale` + `ImageDraw.line` のロジックで生成。
  Streamlit の file_uploader を CDP で操作するのが React 由来の制約で
  難しいため、UI 上の overlay 表示そのものではなく抽出結果の画像だけを
  載せる運用に分けている (再生成手順は下記 7 を参照)。

## 撮り直し手順（macOS）

UI を変更した PR では、PR 本文のスクショに加えてここの画像も同じ PR で
更新する。ズレないように手順を固定しておく。

1. 別ターミナルで Streamlit を起動

   ```sh
   .venv/bin/streamlit run python/meshforge/ui_streamlit.py
   ```

   起動完了（`Local URL: http://localhost:8501` が出る）まで待つ。

2. ヘッドレス Chrome を CDP 待受で起動

   ```sh
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --headless=new --disable-gpu --hide-scrollbars \
     --window-size=1280,2000 \
     --remote-debugging-port=9222 \
     --user-data-dir=/tmp/chrome-screenshot-profile \
     about:blank &
   sleep 2
   ```

3. CDP 経由でスクショを取得（Streamlit は WebSocket でレンダリングを完了
   させるので、`--virtual-time-budget` だけだとスケルトンを撮ってしまう。
   DOM が出るまでポーリングする必要がある）

   ```python
   # save as /tmp/shot.py
   import asyncio, base64, json, urllib.request
   import websockets

   async def main():
       req = urllib.request.Request(
           "http://localhost:9222/json/new?http://localhost:8501/?embed=true",
           method="PUT",
       )
       ws_url = json.loads(urllib.request.urlopen(req).read())["webSocketDebuggerUrl"]
       async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
           mid = 0
           async def send(method, params=None):
               nonlocal mid
               mid += 1
               await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
               while True:
                   data = json.loads(await ws.recv())
                   if data.get("id") == mid:
                       return data
           await send("Page.enable")
           await send("Emulation.setDeviceMetricsOverride", {
               "width": 1280, "height": 2000, "deviceScaleFactor": 2, "mobile": False,
           })
           for _ in range(60):
               r = await send("Runtime.evaluate", {
                   "expression": (
                       "document.querySelector('[data-testid=\"stFileUploader\"]') !== null "
                       "&& document.querySelector('[data-testid=\"stForm\"]') !== null"
                   ),
                   "returnByValue": True,
               })
               if r.get("result", {}).get("result", {}).get("value") is True:
                   break
               await asyncio.sleep(0.5)
           await asyncio.sleep(1.5)
           shot = await send("Page.captureScreenshot", {"format": "png"})
           open("docs/screenshots/editor.png", "wb").write(
               base64.b64decode(shot["result"]["data"])
           )

   asyncio.run(main())
   ```

   ```sh
   .venv/bin/python /tmp/shot.py
   ```

4. 余白をクロップ（フォーム下の黒い空白を切る）

   ```sh
   .venv/bin/python - <<'PY'
   from PIL import Image
   p = "docs/screenshots/editor.png"
   img = Image.open(p)
   img.crop((0, 0, img.width, 1550)).save(p, optimize=True)
   PY
   ```

5. 後片付け

   ```sh
   pkill -f "Google Chrome.*remote-debugging-port=9222"
   rm -rf /tmp/chrome-screenshot-profile /tmp/shot.py
   ```

6. `git diff docs/screenshots/editor.png` で差分が出ていることを確認 →
   UI 変更の PR に同梱してコミットする。

## `overlay-preview.png` の再生成（Step 12-14 以降）

Streamlit の file_uploader は React 由来の事情で headless CDP からは
プログラム的にファイルを流し込めない (`DOM.setFileInputFiles` でファイル
は input に乗るが、React の onChange 経路を通らないため Streamlit
バックエンドに POST されない)。なので「実 UI 上に overlay が乗った
状態」を CDP で自動撮影する代わりに、`_render_extract_overlay` と
同じ PIL ロジックを直接呼び出して overlay 画像を生成し、それを
`overlay-preview.png` として置く運用にしている。

Step 12-15 で `with_rooms=True` の場合に rooms 輪郭 (青) も追加。

7. リポジトリ直下で:

   ```sh
   .venv/bin/python - <<'PY'
   import sys; sys.path.insert(0, "python")
   from PIL import Image, ImageDraw, ImageFont
   from meshforge.building.extract import extract_walls
   from meshforge.heightmap import load_grayscale

   spec = extract_walls(
       "samples/floor_plan_simple.png",
       pixel_mm=0.5, wall_thickness_mm=4.0,
       wall_height_mm=24.0, min_length_mm=30.0,
       with_rooms=True,
   )
   gray = load_grayscale("samples/floor_plan_simple.png", 150.0)
   rgb = gray.convert("RGB")
   draw = ImageDraw.Draw(rgb)
   for room in spec.get("rooms", []):
       coords = [(float(x), float(y)) for x, y in room["polygon"]]
       if len(coords) >= 2:
           coords.append(coords[0])
           draw.line(coords, fill=(60, 140, 220), width=1)
   for w in spec["walls"]:
       x1, y1 = w["start"]; x2, y2 = w["end"]
       draw.line([(float(x1), float(y1)), (float(x2), float(y2))],
                 fill=(220, 50, 50), width=2)
   scaled = rgb.resize((rgb.width * 4, rgb.height * 4), Image.NEAREST)
   pad, caption_h = 24, 56
   canvas = Image.new("RGB",
       (scaled.width + pad*2, scaled.height + pad*2 + caption_h),
       (245, 245, 245))
   canvas.paste(scaled, (pad, pad))
   draw2 = ImageDraw.Draw(canvas)
   try:
       font = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 18)
   except Exception:
       font = ImageFont.load_default()
   draw2.text((pad, scaled.height + pad + 16),
       "Step 12-14/15: walls (5, red) + rooms (2, blue) detected on "
       "floor_plan_simple.png",
       fill=(50, 50, 50), font=font)
   canvas.save("docs/screenshots/overlay-preview.png", optimize=True)
   PY
   ```

   キャプション文言は Step が進む / extract パラメータが変わる時に
   合わせて更新する。サンプル画像 / パラメータが同じなら walls=5 / rooms=2 のまま。
