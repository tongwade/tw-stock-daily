---
name: 更新網站
description: 重新產生網站資料並發佈到 GitHub Pages（push main 觸發 GitHub Actions 自動部署）。當使用者說「更新網站」「重新上線」「重新部署」「把新資料發佈出去」時使用。會偵測新資料、執行 build.py、跑煙霧測試、commit，並 push 到 main 觸發自動部署、驗證上線。
---

# 更新網站

一鍵把 `data/` 裡的新資料產生並發佈到 GitHub Pages：https://tongwade.github.io/stock-daily/
發佈方式是 **push 到 `main` → GitHub Actions workflow「Deploy site to GitHub Pages」自動部署**（不需手動跑 wrangler）。

## 前置確認
- 一律在 repo **根目錄** `D:\Users\2205\Desktop\main\AI_Project\stock` 執行（不要進到 `site/`，那裡有殘留的巢狀 git repo）。
- 確認 `python`、`node`、`gh`（GitHub CLI，用來查部署狀態）可用。

## 步驟

1. **產生資料**
   ```bash
   python build.py
   ```
   只會處理尚未建好的日期。若使用者明確要求重建全部（例如改過 build.py 邏輯），改用 `python build.py --force`。
   注意：build.py 會「合併」既有 `site/data` 日期——原始 `data/` 缺的日期只要 `site/data/YYYYMMDD/` 資料夾還在就會保留，不會被洗掉。

2. **煙霧測試**（確認沒有渲染錯誤）
   ```bash
   node site/smoke.js site
   ```
   若有錯誤就停下來回報，不要硬推上線。

3. **檢視變更並提交**
   ```bash
   git status
   git add -A
   git commit -m "更新個股資料：<簡述新增的日期/個股>"
   ```
   commit 訊息請反映實際變更（新增了哪些日期/個股）。

4. **Push 到 main 觸發自動部署**（這一步才是真正發佈；對外發佈，動手前先向使用者確認）
   ```bash
   git push origin main
   ```
   push 到 `main` 會自動觸發 GitHub Actions 的「Deploy site to GitHub Pages」workflow，把整個 `site/` 發佈到 GitHub Pages。

5. **驗證部署**
   ```bash
   gh run list --limit 1
   ```
   看到最新一筆「Deploy site to GitHub Pages」為 `success` 即代表已上線（約 20–40 秒完成）。
   要確認新資料內容是否上線：
   ```bash
   curl -s https://tongwade.github.io/stock-daily/data/index.js
   ```
   檢查回傳的 JSON 是否含本次新增的日期。

## 注意
- 原始 `data/` 不會進 git（已 git-ignore），只有處理後的 `site/data/` 會被發佈。
- 正式站是 **GitHub Pages（push `main` 觸發 GitHub Actions 自動部署）**——一定要 push 到 main 才會更新線上內容；**不要再手動跑 `npx wrangler pages deploy`**（舊的 Cloudflare Pages Direct Upload 流程已淘汰）。
- 日期清單 `index.js` 在前端載入時會加 `?t=` 時間戳記避開快取，所以新日期會即時顯示，使用者通常不需手動強制重整（首次拿到含此邏輯的 `app.js` 後生效）。
- 部署/推送屬於對外發佈，動手前先向使用者確認。
