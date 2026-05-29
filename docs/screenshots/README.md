# docs/screenshots/

README.md に貼る UI スクショの置き場。

## ファイル

- `editor.png` — Streamlit UI の主要機能画面。Step 12-13 以降は Building タブ
  の "Extract from image" セクション (未アップロード状態) を写している。
  dam タブのフローは README 本文で別途案内する。

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
