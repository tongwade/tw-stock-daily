---
name: 產生 QR Code
description: 為指定網址產生 QR Code 圖檔（PNG）。當使用者說「產生 QR Code」「做一個 QR」「給我網站的 QR 條碼」時使用。預設網址為線上網站 https://tongwade.github.io/stock-daily/。
---

# 產生 QR Code

為網址產生 QR Code PNG。預設對象是線上網站 `https://tongwade.github.io/stock-daily/`（GitHub Pages），使用者也可指定其他網址。

## 步驟

1. **確認網址**：未指定就用線上網站網址。

2. **產生 PNG**：用 Python 的 `qrcode` 套件。

   先確認套件（缺就安裝）：
   ```bash
   python -c "import qrcode" 2>nul || pip install "qrcode[pil]"
   ```

   產生檔案（輸出到 repo 根目錄）：
   ```bash
   python -c "import qrcode; qrcode.make('https://tongwade.github.io/stock-daily/').save('stock-daily-qrcode.png')"
   ```
   若是其他網址，請替換成使用者指定的網址，並用易懂的檔名。

3. **回報**：告知輸出檔路徑。若使用者想，可一併 commit/push（push 前先確認）。

## 注意
- README.md 內以 `stock-daily-qrcode.png` 顯示網站 QR Code；若重新產生線上網站的 QR，沿用此檔名即可自動更新 README 顯示。
