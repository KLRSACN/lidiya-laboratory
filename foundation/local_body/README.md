# Lidiya Local Body Bridge

此橋接器只允許線上璃蒂雅讀取已核准的本機 JSON 證據，不提供任意 Shell、檔案寫入、程式安裝、服務重啟或公開網路入站。

## 安全邊界

- 綁定 `127.0.0.1`／`localhost`／`::1`，其他位址直接拒絕啟動。
- 除 `/health` 外均需本機環境變數中的 Bearer Token。
- Token 至少 32 字元，不得提交 GitHub、Google Drive、日誌或聊天。
- 只讀 `approved_reports.json` 內具名的 JSON 報告。
- 每個報告必須位於 `approved_roots` 之下。
- 支援預期 SHA256；不一致時停止回傳。
- POST、PUT、PATCH、DELETE 全部拒絕。

## 本機啟用前置

1. 將 `approved_reports.example.json` 複製為本機專用 `approved_reports.json`。
2. 填入已核准的完整 D 槽候選工作區路徑。
3. 驗證路徑後，將 `authorized` 改為 `true`。
4. 在 Windows 本機祕密管理方式中設定 `LIDIYA_BRIDGE_TOKEN`，不要貼入聊天。
5. 啟動前先執行 Phase 2B 唯讀探針，確認報告已存在。

## 啟動

```powershell
$env:LIDIYA_BRIDGE_HOST = "127.0.0.1"
$env:LIDIYA_BRIDGE_PORT = "8765"
$env:LIDIYA_BRIDGE_CONFIG = "D:\\<候選工作區>\\approved_reports.json"
python foundation\\local_body\\bridge_server.py
```

## 可用端點

- `GET /health`：最小健康狀態，不回傳私人資料。
- `GET /capabilities`：需授權，回傳只讀能力表。
- `GET /report/<approved-name>`：需授權，回傳具名 JSON 報告、大小及 SHA256。

本橋接器在本機真實執行與 Phase 2B 證據回傳完成前，狀態保持 `LOCAL_EXECUTION_PENDING`。
