# Home Bridge Agent Runtime 正式交接｜2026-07-29

## 1. 目前狀態

- 本機正式基準：`2.0.0-alpha.4`
- 目前啟用候選：`2.0.0-alpha.5-agent-runtime-candidate`
- 本機入口：`D:\lidiya\0.dev_tools\home_bridge_v2`
- 候選 Release：`D:\lidiya\0.dev_tools\home_bridge_v2\releases\2.0.0-alpha.5-agent-runtime-candidate`
- 回退基準：`D:\lidiya\0.dev_tools\home_bridge_v2\releases\2.0.0-alpha.4`
- GitHub 分支：`home-bridge/agent-runtime-v0.1`
- Draft PR：`#2`

## 2. 已完成能力

- Agent Loop：Skill 步驟依序執行、結果回寫、失敗轉 `ESCALATE`。
- Skills：JSON Skill 格式，已完成 `safe_file_copy`。
- Session：SQLite 保存 sessions、attempts、cron_jobs。
- Cron：最小 tick runner，可處理 `@hourly`、`@daily`。
- 工具調度：白名單 `fs.list`、`fs.mkdir`、`fs.copy`、`fs.move`、`fs.sha256`、`fs.write_text`。
- 安全邊界：所有檔案路徑限制於 autonomous zone；無任意 Shell、永久刪除、憑證存取或外部發布。
- Windows 修正：SQLite 連線改為明確 commit／rollback／close，避免 `runtime.db` 被鎖住。

## 3. 已完成驗證

- Python compile：PASS。
- 單元測試：2/2 PASS。
- 路徑逃逸阻擋：PASS。
- 實際 Skill 閉環：PASS。
- 檔案複製後 SHA256：PASS。
- 候選專用 self-test：`AGENT_RUNTIME_SELFTEST_PASS`。
- 切換後驗收：PASS，ExitCode 0。
- Release Manifest：13 檔案，建立時全數 SHA256 相符。

## 4. 已知本機候選檔案

候選 Release 內含原 Home Bridge Release 檔案，加上：

- `agent_runtime/agent_runtime.py`
- `agent_runtime/cron_runner.py`
- `agent_runtime/runtime_config.json`
- `agent_runtime/README.md`
- `agent_runtime/test_agent_runtime.py`
- `agent_runtime/skills/safe_file_copy.json`
- `selftest_agent_runtime.ps1`
- `install_agent_runtime.ps1`

注意：本機 `selftest_agent_runtime.ps1`、`install_agent_runtime.ps1` 是候選整合檔；GitHub foundation 目前保存核心 runtime，後續應再正式同步 Release 安裝腳本，不能假設已存在於 GitHub。

## 5. 新視窗禁止重跑的探索

後續璃蒂雅不要再次從根目錄猜路徑，也不要重複尋找 Git、Python 或 Home Bridge：

- Git：`C:\Program Files\Git\cmd\git.exe`
- Git 版本：`2.47.1.windows.1`
- Python Launcher：`C:\Windows\py.exe`
- Python 實際版本路徑曾顯示：`C:\Python314`
- `D:\lidiya` 不是 Git repository。
- Home Bridge 固定入口：`D:\lidiya\0.dev_tools\home_bridge_v2`
- 正式 Release 目錄：`...\releases\2.0.0-alpha.4`
- 候選 Release 目錄：`...\releases\2.0.0-alpha.5-agent-runtime-candidate`

## 6. 每次接續時優先讀取的位置

### 雲端之家

依序讀：

1. `00 Lidiya Memory Index`
2. `25 Lidiya 家同步最高順位、成功指令模式與線上核心協作協定 20260719`
3. `26 Lidiya 路徑先詢問、證據永久化、結案清理與線上本地共成長協定 20260719`
4. `27 Lidiya 原檔唯讀、複製開發、Claude 協作與版本開發鏈協定 20260719`
5. `HERMES_LOCAL_CORE_GROWTH_HANDOFF_20260719`
6. `Runtime/HOME_BRIDGE_V2_FORMAL_HANDOFF.md`
7. `Runtime/HOME_BRIDGE_STATUS.json`
8. `Runtime/ROUND_PROGRESS.json`

### 本機

優先讀：

1. `D:\lidiya\0.dev_tools\home_bridge_v2\current.json`
2. active release 的 `release.json`
3. `D:\lidiya\CURRENT_STATE.json`
4. `D:\lidiya\LOCAL_HANDOFF.md`
5. `D:\lidiya\LOCAL_INCIDENT_LOG.jsonl`
6. `D:\lidiya\SUCCESS_LEDGER.json`
7. `D:\lidiya\LOCAL_GROWTH_JOURNAL.jsonl`

### GitHub

優先讀：

1. Repository：`KLRSACN/lidiya-laboratory`
2. Branch：`home-bridge/agent-runtime-v0.1`
3. Draft PR：`#2`
4. `foundation/agent_runtime/README.md`
5. 本交接文件
6. `foundation/agent_runtime/runtime_config.json`
7. `foundation/agent_runtime/agent_runtime.py`

## 7. 下一個最小工作

不是重新建立 Agent Runtime，而是：

1. 新增 Hermes supervisor adapter。
2. 當 Session 進入 `ESCALATE` 時，呼叫本機 Ollama `hermes3:8b`。
3. Hermes 只能輸出結構化修正計畫，不直接取得任意 Shell。
4. 計畫必須經 Tool Allowlist 與路徑治理再執行。
5. 限制重試次數，保留每次 supervisor decision 與結果。
6. 再新增 Gemma fallback／frontline adapter。

## 8. 禁止事項

- 不直接修改 `2.0.0-alpha.4`。
- 不刪除舊 Release 或 staging 備份。
- 不把 runtime.db、workspace、`__pycache__` 寫入 Release Manifest。
- 不直接讓模型執行任意 PowerShell／CMD。
- 不在沒有本機驗證證據時宣布正式封版。
- 不因新視窗缺少上下文而從頭重跑 Git、Python、路徑與 Release 探索。
