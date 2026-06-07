@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   每日個股資訊網站 - 一鍵上傳 GitHub
echo ============================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [錯誤] 找不到 git，請先安裝 Git for Windows：
  echo        https://git-scm.com/download/win
  echo 安裝後重新執行本檔。
  pause
  exit /b
)

if not exist ".git" (
  echo 第一次執行，初始化 git...
  git init
)
git branch -M main

echo 加入變更並建立提交...
git add -A
git commit -m "update site" 2>nul
if errorlevel 1 echo （沒有新的變更，略過提交）

git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo.
  echo 尚未設定 GitHub repo 網址。
  echo 請先到 github.com 建立一個空的 repository（Public、不要加 README），
  echo 然後把它的網址貼到這裡，例如：https://github.com/你的帳號/stock-daily.git
  echo.
  set /p REPOURL=請貼上 repo 網址:
)
if defined REPOURL git remote add origin %REPOURL%

echo.
echo 推送到 GitHub...（第一次會跳出登入視窗，請用你的 GitHub 帳號登入）
git push -u origin main

echo.
echo ============================================
echo 完成。接著到 GitHub 該 repo 的 Settings - Pages，
echo Source 選 main / root，儲存後約 1-2 分鐘即可取得網址：
echo   https://你的帳號.github.io/repo名稱/
echo ============================================
pause
