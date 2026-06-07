# 每日個股資訊網站

每日更新的台股個股資訊靜態網站。資料在**本機自動產生**（大盤放量訊號引擎 + 個股分點爬蟲）→ 轉成 Excel/CSV → `build.py` 產生精簡的靜態網站資料 → push 到 `main` 後由 GitHub Actions 自動發佈到 GitHub Pages。

**發佈出去的網站沒有後端、沒有資料庫、沒有前端框架** —— 前端是手寫的 HTML + 原生 JavaScript，直接讀取事先產生好的資料檔。（*資料產生*階段在本機有用到一個 SQLite 資料庫 `tw_volume.db`，但它不會上傳、也不會進到網站。）

🔗 **線上網站**：https://tongwade.github.io/stock-daily/

<p align="left">
  <img src="stock-daily-qrcode.png" width="160" alt="網站 QR Code">
</p>

> 📘 **完整的每日操作手冊在 [`每日更新流程.md`](每日更新流程.md)** —— 要實際更新網站請看那份逐步說明。

---

## 網站內容

| 分頁 | 說明 |
| --- | --- |
| **大盤放量訊號** | 當日放量訊號（可搜尋、排序、星等強度） |
| **量能延續追蹤** | 前一交易日訊號在今日是否量能延續 |
| **出關股追蹤** | 處置期結束後第一個交易日的表現 |
| **處置股清單** | 當日處置股名單 |
| **勝率回測** | 放量訊號的歷史勝率（D+5／D+10／D+15）圖表與表格 |
| **個股分析** | 各檔個股的技術圖表、券商買賣超前 20、各價位量、券商分點明細 |
| **週報分析** | 以「週」為單位的券商買賣超與大量均價分析 |
| **使用說明** | 各指標說明 |

上方可用日期下拉選單切換不同交易日；週報分頁有自己的「週期」下拉。

---

## 本機環境（這台電腦）

> ⚠️ 不要用系統預設的 `python`（Miniconda 3.9，裝不了爬蟲套件）。一律用下面的 Python 3.13 完整路徑。

| 工具 | 路徑 |
| --- | --- |
| Python 3.13 | `C:\Users\tongw\AppData\Local\Programs\Python\Python313\python.exe` |
| Node.js | `C:\Program Files\nodejs\node.exe`（沒進 PATH，用完整路徑）|
| Chrome（tpex 抓取用）| `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe` |

Python 套件（裝在上面那個 3.13）：`openpyxl requests ddddocr patchright pandas numpy`。煙霧測試需要 Node.js。

---

## 每日更新流程（摘要）

> 交易日**收盤後**做一次，順著跑、別跳天。完整版見 [`每日更新流程.md`](每日更新流程.md)。

1. `volume_system.py --update` → 產生 `out/台股放量訊號_<日期>.xlsx`（大盤放量/延續/出關/處置/勝率）。
2. `bsr_fetch.py 2344 3037 6257 --date <日期>`（上市）＋ `tpex_fetch.py 3105 6261 --date <日期>`（上櫃）→ 個股分點 CSV 存進 `data/<日期>/`。
3. 把 `out/台股放量訊號_<日期>.xlsx` 複製進 `data/<日期>/`。
4. `build.py` 產生網站資料。
5. `node site/smoke.js site` 確認沒有渲染錯誤。
6. `git push` → GitHub Actions 約 1 分鐘內自動重新發佈。

> 💡 `volume_system.py` 是**逐日累積**的系統：每個交易日都要跑，跳天會讓「量能延續」鏈斷掉、勝率回測出現缺口。

---

## 指令

`$PY` = 上面的 Python 3.13 完整路徑；`$NODE` = Node 完整路徑。

```bash
# --- 資料產生（build.py 的上游）---
$PY volume_system.py --update              # 每日：抓最新交易日全市場、偵測訊號、匯出 Excel
$PY volume_system.py --init                # 僅第一次：回溯約 7 個月到 tw_volume.db

$PY bsr_fetch.py 2344 3037 6257 --date YYYYMMDD     # 上市個股分點（ddddocr 解驗證碼）
$PY tpex_fetch.py 3105 6261 --date YYYYMMDD           # 上櫃個股分點（patchright 過 Turnstile，會跳 Chrome）

# --- 建置與發佈 ---
$PY build.py                  # 從 data/ 重新產生網站資料（已產生的日期會跳過）
$PY build.py --force          # 強制重建所有日期（改過 build.py 邏輯後用）
$NODE site/smoke.js site      # 無頭煙霧測試：渲染每個日期/個股/週報以抓出執行錯誤
git add -A && git commit -m "..." && git push    # 發佈：push 到 main → GitHub Actions 自動部署

# 本機預覽：直接用瀏覽器開 site/index.html（支援 file://，免架伺服器）
```

---

## 架構

三段式管線：**(爬蟲) → Excel/CSV → (build.py) → site/data/\*.js → (靜態前端) → GitHub Pages**

### 資料產生（build.py 的上游）
- **`volume_system.py`** —— 大盤放量訊號引擎。抓全市場 TWSE/TPEx 每日量價存進 SQLite `tw_volume.db`，偵測放量/出關/量能延續/處置/勝率回測，匯出 `out/台股放量訊號_YYYYMMDD.xlsx`。
  - `--init`（首次）回溯約 7 個月；`--update`（每日）抓最新交易日並匯出。
  - ⚠️ **`tw_volume.db` 是不可重生的累積狀態檔**（約 92MB，git 忽略）：重新 `--init` 補不回歷史訊號與勝率追蹤。**請定期備份、別刪。**
- **`bsr_fetch.py`** —— 上市（TWSE）個股分點，用 `ddddocr` 自動解驗證碼。輸出 `data/YYYYMMDD/{代號}_bsr.csv`。
- **`tpex_fetch.py`** —— 上櫃（TPEX）個股分點，用 `patchright` + 系統 Chrome 自動過 Cloudflare Turnstile。**需要桌面環境 + 住宅 IP**（機房/雲端 IP 過不了）。輸出同樣的 `_bsr.csv` 格式。
- 輔助：`backfill_twse.py`（補抓 TWSE 歷史）、`verify_data.py`／`fetch_verify.py`（校驗）。

### build.py（Excel/CSV → 資料檔）
- 掃描 `data/YYYYMMDD/`，依檔名在 `classify()` 分類：
  - `台股放量訊號*.xlsx` → 大盤訊號檔（多個工作表）→ `market.json`
  - `{代號}_bsr.csv` → **主要**個股來源：直接從完整分點資料算出買賣超前20、各價位量、券商明細
  - `{代號}*日報*.xlsx`／`{代號}*分析結果*.xlsx` → 舊版個股後備來源（無 BSR CSV 時才用）
  - `{代號}*charts*.xlsx` → **不再使用**；技術圖改由前端 Chart.js 即時繪製
- **週報**：一週 = **週一~週五**。優先用 `build_weekly_from_daily.py <wkey>` 把既有的每日分點彙總成該週（券商買賣超 + 大量與均價），例 `python build_weekly_from_daily.py 20260601-0605`（`--check` 可比對驗證）；舊路徑為夥伴的 `*週報*.xlsx` 經 `process_weekly`/`process_volume_avg`。索引多一份 `weekly_dates`。
- 產生 `site/data/index.json`（日期清單 + 每日個股），前端據此建立所有選單。
- **新增個股／日期不需改程式碼**，自動偵測；顯示名稱可在 `stock_names.json` 覆寫。

### .js 包裝檔的小技巧（重要）
`build.py` 為每個 `.json` 另存一份呼叫 `window.__DATAREG(key, data)` 的 `.js`。前端用注入 `<script>` 載入（而非 fetch），所以**直接 `file://` 開也能用、免伺服器**。線上實際使用的是 `.js`；`.json` 為中間產物、已被 git 忽略。

### 前端（site/）
- `index.html` —— 8 個分頁 + 日期下拉（週報分頁另有週期下拉）。
- `app.js` —— 原生 JS，透過 `__DATAREG` 載入器供應資料；Grid.js 畫表格、Chart.js 畫圖表。改 `app.js` 後要更新 `index.html` 裡 `<script>` 的 `?v=` 版本號。
- `site/smoke.js` —— 煙霧測試（**被 git 忽略，不在版控**）：用 DOM/Grid.js/Chart stub 跑 `app.js`，渲染每個日期×分頁×個股×週報抓執行錯誤。
- 第三方函式庫（Grid.js、Chart.js）由 CDN 載入。

### 部署
- `.github/workflows/pages.yml`（GitHub Actions）：push 到 `main` 時把 `./site` 部署到 GitHub Pages。
- 舊版 Cloudflare Pages + `wrangler`、`site/deploy.bat` 均**已停用**。

---

## 注意事項

- **原始資料不會上傳**：`data/`、`out/`、`tw_volume.db*`、`*.log` 都已被 git 忽略，只有處理後的 `site/data/` 會發佈。請在本機保留 `data/` 與資料庫以便重建。
- **資料產生無法放雲端 CI / Claude routines**：兩個阻礙 —— (1) `tw_volume.db` 是有狀態的大檔，雲端用完即丟的 runner 留不住；(2) `tpex_fetch.py` 的 Turnstile 在機房 IP 過不了，需要真桌面 Chrome + 住宅 IP。要自動化請用**本機 Windows 工作排程器**，部署那段才是雲端 CI。
- **巢狀 git repo**：`site/.git` 是舊 `deploy.bat` 留下的殘留，與真正部署用的根目錄 repo 不同。請一律在 repo **根目錄** 執行 git 指令。
- Excel 解析靠 `find_header` 尋找含關鍵欄位（代號／分類／股價）的標題列；若來源檔版面改變，解析會靜默回傳空資料而非報錯。
