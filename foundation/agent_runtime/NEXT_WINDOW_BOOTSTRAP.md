# Agent Runtime 下一視窗啟動清單

下一個璃蒂雅視窗處理 Home Bridge／Hermes／本地模型時，先做以下順序，不得從頭探索：

1. 讀取雲端之家：`00 → 25 → 26 → 27 → HERMES_LOCAL_CORE_GROWTH_HANDOFF_20260719 → Runtime/HOME_BRIDGE_V2_FORMAL_HANDOFF.md → Runtime/HOME_BRIDGE_STATUS.json → Runtime/ROUND_PROGRESS.json`。
2. 讀取本機 `D:\lidiya\0.dev_tools\home_bridge_v2\current.json`。
3. 讀 active release 的 `release.json`。
4. 讀 `HOME_BRIDGE_AGENT_RUNTIME_HANDOFF_20260729.md`。
5. 讀 `HOME_BRIDGE_AGENT_RUNTIME_STATUS_20260729.json`。
6. 查看 GitHub Draft PR #2 最新 head，不要重新建立 Agent Runtime。

已知固定資訊：

- Home Bridge：`D:\lidiya\0.dev_tools\home_bridge_v2`
- active candidate：`2.0.0-alpha.5-agent-runtime-candidate`
- rollback：`2.0.0-alpha.4`
- Git：`C:\Program Files\Git\cmd\git.exe`
- Python Launcher：`C:\Windows\py.exe`
- `D:\lidiya` 不是 Git repository。

下一個工程工作只有一個：實作 Hermes supervisor adapter，讓 `ESCALATE` Session 經 Ollama 呼叫 `hermes3:8b`，輸出受控 JSON 修正計畫；不得給任意 Shell 權限。
