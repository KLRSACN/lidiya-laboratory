# NAV-RELAY-MVP-0001

最小半自主協作閉環：Coordinator + SQLite Relay + Navigator 端口登記 + 固定關鍵字協議。

## 目前包含

- `relay_protocol.py`：解析 `[TARGET]`、`[ACTION]`、`[WAKE_AFTER]` 與 Relay 輸出區塊。
- `relay_mvp.py`：SQLite Mailbox、排程喚醒、視窗登記與 CLI。
- `coordinator_mvp.py`：依 Worker `STATE` 決定下一個目標視窗。
- `windows.example.json`：WINDOW-00/01/02 的 CDP debug port 範例。
- `test_mvp.py`：協議、Queue、排程與 Coordinator 路由測試。

這一版不控制瀏覽器 DOM；它先提供 Navigator 可接入的本地中繼核心。

## Windows 啟動

在此目錄開啟 CMD：

```bat
python -m unittest -v test_mvp.py
python relay_mvp.py --db nav_relay_mvp.sqlite3 register WINDOW-00 COORDINATOR 9222 "[LIDIYA:WINDOW-00]"
python relay_mvp.py --db nav_relay_mvp.sqlite3 register WINDOW-01 BUILDER 9223 "[LIDIYA:WINDOW-01]"
python relay_mvp.py --db nav_relay_mvp.sqlite3 register WINDOW-02 REVIEWER 9224 "[LIDIYA:WINDOW-02]"
python relay_mvp.py --db nav_relay_mvp.sqlite3 scheduler --interval 5
```

## Chrome/CDP 範例

每個瀏覽器實例必須使用不同的資料目錄與端口：

```bat
chrome.exe --remote-debugging-port=9222 --user-data-dir="D:\lidiya\chrome-window-00"
chrome.exe --remote-debugging-port=9223 --user-data-dir="D:\lidiya\chrome-window-01"
chrome.exe --remote-debugging-port=9224 --user-data-dir="D:\lidiya\chrome-window-02"
```

如果只先測兩個工作視窗，可只啟動 9223 與 9224；Coordinator 也可以先由本地模型或人工輸入取代。

## Relay 回覆格式

```text
[RELAY_READY]
[TARGET:WINDOW-02]
[ACTION:SEND]
[WAKE_AFTER:5]

[RELAY_OUTPUT_BEGIN]
MISSION_ID=NAV-RELAY-MVP-0001
STATE=BUILDER_TASK_COMPLETED
SUMMARY=已完成指定工作
[RELAY_OUTPUT_END]
```

導航程式只擷取 `RELAY_OUTPUT_BEGIN/END` 之間的內容，並依 `TARGET` 尋找登記端口。

## 手動注入測試

把上述格式保存為 `sample_output.txt`：

```bat
python relay_mvp.py --db nav_relay_mvp.sqlite3 ingest NAV-RELAY-MVP-0001 WINDOW-01 sample_output.txt
python relay_mvp.py --db nav_relay_mvp.sqlite3 pull WINDOW-02
```

看到 JSON 訊息即表示 Relay 的第一段往返成立。

## 下一個實作項目

Navigator Adapter 需要連接 Chrome DevTools Protocol，完成：

1. 依 debug port 找到正確 ChatGPT 分頁。
2. 驗證頁面上的 `[LIDIYA:WINDOW-NN]` 標記。
3. 將 Relay 訊息貼入輸入框並送出。
4. 以 DOM 穩定時間判斷回答完成。
5. 擷取最後一則 Assistant 回覆並呼叫 `ingest`。

## 安全限制

- 不執行任意 Shell 字串。
- 不修改 HOME 或 Wake Core。
- 不使用 force-push。
- 預設最多 20 輪，Navigator 實作時必須加入停止開關。
- 第一版僅做文字搬運與固定狀態路由。
