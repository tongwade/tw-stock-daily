---
name: 本機預覽
description: 在本機預覽與驗證網站，不需發佈。當使用者說「本機預覽」「本地看一下」「先在電腦上開來看」「驗證網站有沒有問題」時使用。會跑煙霧測試並啟動本機靜態伺服器供瀏覽。
---

# 本機預覽 / 驗證

在不推上 GitHub 的情況下，於本機檢視 `site/` 並驗證沒有執行錯誤。

## 步驟

1. **煙霧測試**（最快的驗證，無頭跑過每個日期/個股）
   ```bash
   node site/smoke.js site
   ```
   會用 DOM stub 跑 `app.js` 並渲染所有資料以抓出 runtime 錯誤。有錯就回報。

2. **本機瀏覽**，二擇一：
   - **直接開檔**：用瀏覽器開 `site/index.html` 即可。網站用 `.js` 包裝檔（`window.__DATAREG`）載入資料，支援 `file://`，免伺服器。
   - **起靜態伺服器**（需要乾淨網址或測 fetch 行為時）：
     ```bash
     python -m http.server 8765 --directory site
     ```
     然後開 `http://localhost:8765/`。用完記得停掉伺服器。

3. **回報**：說明煙霧測試結果，以及預覽方式 / 網址。

## 注意
- 一律針對 repo 根目錄的 `site/` 操作；不要動 `site/.git`（殘留巢狀 repo）。
- 這個 skill **不**做 commit/push；要發佈請用「更新網站」skill。
