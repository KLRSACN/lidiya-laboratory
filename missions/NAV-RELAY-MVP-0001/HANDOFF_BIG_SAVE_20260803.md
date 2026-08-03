# NAV-RELAY-MVP-0001 — 大儲存／新視窗交接

保存時間：2026-08-03 09:27（Asia/Taipei）
權威專案：`KLRSACN/lidiya-laboratory`
分支：`nav-relay-mvp-0001`
本機家根目錄：`D:\lidiya`
本機 Repo：`D:\lidiya\lidiya-laboratory`
任務目錄：`D:\lidiya\lidiya-laboratory\missions\NAV-RELAY-MVP-0001`

## 1. 核心任務狀態

- MISSION_ID：`NAV-RELAY-MVP-0001`
- 目標：讓 Coordinator 與 Builder 兩個 ChatGPT 視窗，透過 Chrome CDP、Playwright、SQLite Relay 自動派送與回傳任務。
- WINDOW-00：Coordinator，CDP port `9222`，標記 `[LIDIYA:WINDOW-00]`
- WINDOW-01：Builder，CDP port `9223`，標記 `[LIDIYA:WINDOW-01]`
- Scheduler：`relay_mvp.py ... scheduler --interval 5`
- Navigator：`navigator_adapter.py ... WINDOW-00 WINDOW-01`
- SQLite：`nav_relay_mvp.sqlite3`
- 第一輪往返：`WINDOW-00 → WINDOW-01 → WINDOW-00` 成功。
- 測試：12/12 通過。

### 已驗證的往返內容

Builder ACK：

```text
STATE=NAVIGATOR_ROUNDTRIP_BUILDER_ACK
SOURCE=WINDOW-01
TARGET=WINDOW-00
READY_FOR_NEXT_TASK=true
```

Coordinator 確認：

```text
STATE=WINDOW-00_ROUNDTRIP_CONFIRMED
SOURCE=WINDOW-00
BUILDER=WINDOW-01
MISSION_ID=NAV-RELAY-MVP-0001
READY_FOR_NEXT_TASK=true
```

## 2. 本機環境與軟硬體

### 作業環境

- Windows 10
- PowerShell 為主要操作介面
- Git：`C:\Program Files\Git\cmd\git.exe`
- Git 版本：`2.47.1.windows.1`
- Python Launcher：`C:\Windows\py.exe`
- Python：`3.14.6`
- 虛擬環境：任務目錄下 `.venv`
- Playwright：`1.62.0`
- Playwright Chromium：已安裝
- Chrome CDP profiles：
  - `D:\lidiya\chrome-window-00`
  - `D:\lidiya\chrome-window-01`

### 已知硬體

- 筆電 GPU：NVIDIA RTX 4050 Laptop，6 GB VRAM
- RAM：16 GB
- 3D：Bambu P1S + AMS
- Blender：4.5
- 掃描設備：POP3 / Mini2 / MetroX

### 現有 AI／開發工具

- Gemini CLI
- Ollama
- qwen3.6（約 23 GB）
- hermes3:8b（約 4.7 GB）
- SillyTavern
- OpenClaw
- Blender Python
- Git / GitHub
- Playwright
- SQLite
- PowerShell
- Python
- NotebookLM 工作流
- React + Python API 工作流
- SRT / TTS / 影片組合作業

## 3. 與使用者的 PowerShell/CMD 合作規則

1. 一次只執行一個步驟。
2. 每一步等待使用者貼回完整輸出後再繼續。
3. 不預設路徑、版本、程序是否存在；先查證。
4. 發生錯誤立即停止，不連續追加指令。
5. PowerShell 執行外部 EXE 時，含空格路徑必須使用 call operator `&`：

```powershell
& "C:\Program Files\Git\cmd\git.exe" --version
```

6. PowerShell 切換目錄使用：

```powershell
Set-Location "D:\lidiya\lidiya-laboratory\missions\NAV-RELAY-MVP-0001"
```

7. 不使用 CMD 專屬的 `cd /d` 當作 PowerShell 指令。
8. 長駐程序啟動後畫面停住且沒有回到 `PS>`，通常代表正在運行，不代表卡死。
9. `KeyboardInterrupt` 通常是使用者按下 Ctrl+C，不是程式本身故障。
10. 使用者要求「慢一點」時，嚴格維持單步確認模式。

## 4. 已完成的正確指令

### Git PATH（目前 PowerShell 暫時設定）

```powershell
$env:Path += ";C:\Program Files\Git\cmd"
```

### 任務路徑

```powershell
Set-Location "D:\lidiya\lidiya-laboratory\missions\NAV-RELAY-MVP-0001"
```

### 建立環境（只需第一次）

```powershell
py -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m playwright install chromium
```

### 測試

```powershell
& ".\.venv\Scripts\python.exe" -m unittest -v test_mvp.py test_navigator_adapter.py
```

結果：12 tests / OK。

### 登記視窗

```powershell
& ".\.venv\Scripts\python.exe" ".\relay_mvp.py" --db ".\nav_relay_mvp.sqlite3" register WINDOW-00 COORDINATOR 9222 "[LIDIYA:WINDOW-00]"
& ".\.venv\Scripts\python.exe" ".\relay_mvp.py" --db ".\nav_relay_mvp.sqlite3" register WINDOW-01 BUILDER 9223 "[LIDIYA:WINDOW-01]"
```

### Scheduler（獨立 PowerShell 常駐）

```powershell
& ".\.venv\Scripts\python.exe" ".\relay_mvp.py" --db ".\nav_relay_mvp.sqlite3" scheduler --interval 5
```

### Navigator（另一個獨立 PowerShell 常駐）

```powershell
& ".\.venv\Scripts\python.exe" ".\navigator_adapter.py" --db ".\nav_relay_mvp.sqlite3" --mission-id NAV-RELAY-MVP-0001 --interval 5 WINDOW-00 WINDOW-01
```

### 第一輪注入

```powershell
& ".\.venv\Scripts\python.exe" ".\inject_roundtrip.py"
```

## 5. 本輪除錯紀錄

### Git 無法直接呼叫

症狀：`git` not recognized。
原因：Git 已安裝，但 PowerShell PATH 未含 Git。
驗證：

```powershell
& "C:\Program Files\Git\cmd\git.exe" --version
```

### Python 命令

此機使用 `py --version`，已確認 Python 3.14.6。

### SQLite 測試 WinError 32

症狀：TemporaryDirectory 無法刪除 `relay.sqlite3`。
原因：測試結束前 SQLite connection 未關閉。
本機目前已在 `test_mvp.py` 兩個 RelayTests 加入：

```python
store.connection.close()
```

注意：此為本機工作樹修改，必須在後續 Git status 檢查後提交；目前 GitHub 此交接檔不代表該程式修改已由本機 push。

### Scheduler 重複程序

曾誤啟動兩個 Scheduler。已停止重複程序。之後一鍵啟動器必須先檢查既有程序，避免重複啟動。

## 6. 家的規則

- 本機權威根目錄：`D:\lidiya`
- GitHub 是跨視窗權威交接位置。
- `/mnt/data` 僅可作暫存，不能當跨視窗權威儲存。
- 新視窗先讀取：
  1. `D:\lidiya\LIDIYA_CORE.md`
  2. `D:\lidiya\CURRENT_STATE.json`
  3. `D:\lidiya\LOCAL_HANDOFF.md`
  4. 本文件：`missions/NAV-RELAY-MVP-0001/HANDOFF_BIG_SAVE_20260803.md`
- 若本機資料與 GitHub 衝突，先停止並核對 commit、branch、時間戳，不可自行覆蓋。

## 7. 新視窗標準啟動認知

新視窗必須知道：

```text
HOME_ROOT=D:\lidiya
REPO_ROOT=D:\lidiya\lidiya-laboratory
MISSION_ROOT=D:\lidiya\lidiya-laboratory\missions\NAV-RELAY-MVP-0001
REPO=KLRSACN/lidiya-laboratory
BRANCH=nav-relay-mvp-0001
MISSION_ID=NAV-RELAY-MVP-0001
```

交接時不得假設：

- 不得假設 Git 在 PATH。
- 不得假設 `python` 命令可用；優先 `py` 或 `.venv\Scripts\python.exe`。
- 不得假設 Scheduler/Navigator 未執行；先查程序。
- 不得一次給多個未驗證步驟。

## 8. 目前目標達成率

以「可用的兩視窗半自主 Relay MVP」為範圍：

- Repo / branch / 任務檔案：100%
- Python / Playwright 環境：100%
- Protocol / SQLite Relay：100%
- 單元測試：100%
- WINDOW-00 ↔ WINDOW-01 真實往返：100%
- 重開機後自動恢復：0%
- 一鍵啟動與防重複程序：0%
- 長時間穩定性測試：20%
- 三視窗 Reviewer 擴充：0%
- 完整錯誤日誌與健康檢查 UI：0%

**目前 MVP 達成率：約 70%。**

核心通信已打通；剩餘工作主要是產品化、恢復能力、長時間穩定與一鍵啟動。

## 9. 下一輪順序

1. 停止前先記錄 Scheduler / Navigator PID 與資料庫狀態。
2. `git status` 檢查本機修改與未追蹤檔案。
3. 將 `test_mvp.py` SQLite close 修正正式提交。
4. 建立 `START_NAV_RELAY.bat` 或 PowerShell launcher。
5. Launcher 加入：路徑驗證、CDP port 檢查、程序去重、錯誤日誌、成功提示。
6. 執行第二輪往返測試。
7. 測試關閉後重啟與重開機恢復。
8. 再建立 WINDOW-02 Reviewer。

## 10. 當前保護要求

- Scheduler 與 Navigator 正在常駐時，不要在其視窗輸入其他命令。
- 不要直接刪除 `nav_relay_mvp.sqlite3`。
- 不要關閉 9222 / 9223 Chrome profile 前，先確認是否需要保存對話。
- 任何新視窗接手後，先回報讀取到的 branch、mission、home path、最近成功 checkpoint，再繼續操作。
