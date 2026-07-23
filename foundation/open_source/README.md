# Lidiya Open Source Growth Node

此目錄讓所有新視窗能搜尋、比較與評估最新開源候選，同時維持「發現不等於核准」的邊界。

## 讀取順序

1. `registry.json`：官方來源白名單與目前採用狀態。
2. `SEARCH_INDEX.json`：依任務與關鍵字找到候選。
3. `EVALUATION_POLICY.md`：五項評分與強制阻擋條件。
4. `RADAR_CHANNEL.json`：最新快照的資料分支與時效規則。
5. 從 `generated/open-source-radar` 分支讀 `LATEST_SNAPSHOT.json` 與 `OPEN_SOURCE_RADAR.md`。

## 擴充新專案

- 使用 GitHub 的 `Open-source candidate` Issue 表單提出。
- 先確認官方來源、授權、固定版本、SHA256、權限需求、沙盒與回退。
- 通過後才加入 `registry.json`；加入清冊也不代表可以安裝。

## 自動化範圍

排程可讀 GitHub 公開 Metadata、Release 與 commit，並更新專用資料分支。它不下載、不安裝、不執行第三方程式，也不修改家的正式核心。
