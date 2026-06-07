@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  TPEx 上櫃分點抓取 (3105 久元-非, 6261)
echo  會開出 Chromium 視窗自動查詢；
echo  若出現「我不是機器人」請點一下。
echo ============================================
"C:\Python313\python.exe" tpex_fetch.py 3105 6261
echo.
echo ============================================
echo  跑完了。若上面顯示 OK，接著可執行：
echo     "C:\Python313\python.exe" build.py
echo     node site\smoke.js site
echo ============================================
pause
