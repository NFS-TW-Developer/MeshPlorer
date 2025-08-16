# MeshPlorer

## 簡介

MeshPlorer 是一款 Meshtastic 機器人服務，支援緊急守護、天氣查詢等功能。

## 功能特色

- **緊急守護服務** - 自動監控緊急頻道，提供即時通報
- **天氣查詢服務** - 根據節點位置自動查詢天氣資訊
- **智慧訊息處理** - 支援加密通訊和重複訊息過濾

## 快速開始

```bash
# 啟動服務
docker compose up -d
```

## 機器人指令

在 Meshtastic 網路中可以用以下指令跟機器人互動：

### 基本指令

機器人支援這些前綴：
- `@nfs.tw`
- `@nfstw`
- `@nfs`

**可以用的指令**：
- **@nfs.tw help** - 顯示所有可用指令的詳細說明
- **@nfs.tw weather** - 查詢你所在位置的天氣狀況（定位來源為 MeshSight，每分鐘限用一次）
- **@nfs.tw ab [指令]** - 由機器人幫你呼叫 ARBot 機器人

**使用範例**：
```
@nfs.tw help
@nfs.tw weather
@nfs.tw ab status
```

**靜默機制**：
- 天氣查詢：1 分鐘靜默期，超過限制會回應 🤐 emoji
- 一般指令：無靜默期限制

### 測試功能

發送包含以下關鍵字的訊息會讓機器人回應 👌 emoji：
- **中文**: `測試`
- **英文**: `test`、`testing`（需要是獨立詞彙或短句）

*注意：測試功能有 20 秒靜默期，避免過度回應*

### 緊急守護功能

在緊急守護頻道中發送任何文字訊息會觸發緊急通報：

**觸發條件**：
- 在設定的緊急守護頻道中發送文字訊息
- 機器人會自動忽略 emoji 訊息

**回應內容**：
- 🆘 緊急守護通報
- 發送者節點資訊
- 緊急地址（來源：MeshSight）
- 訊息內容（限制 20 字）
- 安全提醒

**靜默機制**：
- 3 分鐘靜默期，避免重複通報
- 自動過濾重複訊息（10 分鐘內）

## 設定

編輯 `data/meshplorer-gateway/configs/config.json` 來設定機器人參數。

**主要設定項目**：
- 工作頻道和加密金鑰
- 緊急守護頻道設定
- 忽略的節點 ID 清單
- 日誌等級設定

## 參與貢獻

如果您有功能請求或發現錯誤，請在 GitHub 上[開啟 issue](https://github.com/NFS-TW-Developer/MeshPlorer/issues)。

## 法律聲明

This project is not affiliated with or endorsed by the Meshtastic project.

The Meshtastic logo is the trademark of Meshtastic LLC.

## 倉儲狀態
![Alt](https://repobeats.axiom.co/api/embed/8c088057ec39162a448d66f0e68e42274a7c4bfb.svg "Repobeats analytics image")

## 相關專案

- [MeshSight](https://github.com/NFS-TW-Developer/MeshSight)：節點地圖視覺化

## 參考資料

- https://meshtastic.org/docs/software/integrations/mqtt/mqtt-python/
- https://github.com/meshtastic/protobufs
