# hmi-platform

Yocto 上で動作する i.MX8M Plus 向け Qt/QML HMI ランタイムを対象に、HMI 作画・シミュレーション・タグ管理・実機デプロイを統合した開発環境。

## 成果物

| モジュール | 役割 |
| --- | --- |
| Editor | HMI 作画ツール（Qt6 + QML） |
| Simulator | PC 上での HMI 試験環境（Qt6 + QML） |
| Runtime | i.MX8MP / Yocto 実機向けランタイム（MVP 後着手） |
| Shared/Schema | プロジェクト JSON スキーマ / C++ データモデル（唯一の真実） |
| Shared/Widgets | 共通 QML Widget（Button / Label 等） |

## 技術スタック

- 言語 / フレームワーク: Qt 6 (Qt Quick / QML), C++17
- ビルド: CMake (≥ 3.21)
- ホスト OS（開発）: macOS（現在動作確認済み）
- ターゲット OS（最終）: Yocto on i.MX8MP

## フォルダ構成

```
hmi-platform/
├─ Editor/              HMI Editor アプリ
│   ├─ CMakeLists.txt
│   ├─ src/
│   └─ qml/
├─ Simulator/           HMI Simulator アプリ
│   ├─ CMakeLists.txt
│   ├─ src/
│   └─ qml/
├─ Runtime/             i.MX8MP / Yocto 実機向け（MVP 後）
├─ Shared/
│   ├─ Schema/          JSON スキーマ・C++ データモデル
│   │   ├─ CMakeLists.txt
│   │   ├─ include/
│   │   └─ src/
│   └─ Widgets/         共通 QML Widget モジュール
│       ├─ CMakeLists.txt
│       └─ qml/
├─ Docs/
└─ CMakeLists.txt       ルート CMake
```

## 前提

- Qt 6.8 以上（macOS 14+ では Qt 6.7 以前は AGL.framework 不在によりリンクエラーになるため）
- CMake 3.21 以上
- C++17 対応コンパイラ

macOS で Homebrew Qt を使う場合:

```sh
brew install qt
```

## ビルド

```sh
cmake -S . -B build -DCMAKE_PREFIX_PATH=/opt/homebrew/opt/qt
cmake --build build
```

`CMAKE_PREFIX_PATH` は環境に合わせて変更してください（例: `~/Qt/6.8.0/macos`）。

## 起動

```sh
# Editor
./build/Editor/hmi_editor.app/Contents/MacOS/hmi_editor

# Simulator
./build/Simulator/hmi_simulator.app/Contents/MacOS/hmi_simulator
```

## MVP タスク進捗

| # | タスク | 状態 |
| --- | --- | --- |
| 1 | Qt6 プロジェクト作成 | ✅ 完了 |
| 2 | キャンバス表示 | ✅ 完了 |
| 3 | Widget データ構造定義 | ⬜ 未着手 |
| 4 | Button 配置 | ⬜ 未着手 |
| 5 | ドラッグ | ⬜ 未着手 |
| 6 | JSON 保存 | ⬜ 未着手 |
| 7 | JSON 読込 | ⬜ 未着手 |
| 8 | Simulator 表示 | ⬜ 未着手 |

## 共通データ仕様（Project Format）

`Shared/Schema` を唯一の真実とし、以下の JSON 形状で project / screen / widget を表現する。

```json
{
  "project": "Sample",
  "screens": [
    {
      "name": "Main",
      "widgets": [
        {
          "id": "btn001",
          "type": "Button",
          "x": 100,
          "y": 50,
          "width": 120,
          "height": 40,
          "text": "Start",
          "tag": "PLC.START"
        }
      ]
    }
  ]
}
```

## 開発ルール

- 1 タスクごとに実装し、ビルド成功を完了基準とする
- `Shared/Schema` を唯一の真実とする
- フォルダ構成の変更禁止
- 既存コードの削除禁止
- Qt6 + CMake 前提
