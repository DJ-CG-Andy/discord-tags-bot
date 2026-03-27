# Discord 標籤系統 Bot 啟動腳本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Discord 標籤系統 Bot (新版本)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 檢查 Python 是否安裝
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ 錯誤: 未找到 Python" -ForegroundColor Red
    Write-Host "請先安裝 Python 3.10 或更高版本" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Python 版本:" -ForegroundColor Green
python --version
Write-Host ""

# 檢查依賴
Write-Host "📦 檢查依賴包..." -ForegroundColor Yellow
$discordInstalled = pip list | Select-String "discord.py"
if (-not $discordInstalled) {
    Write-Host "⬇️ 安裝依賴包..." -ForegroundColor Yellow
    pip install -r requirements.txt
    Write-Host "✅ 依賴包安裝完成" -ForegroundColor Green
} else {
    Write-Host "✅ 依賴包已安裝" -ForegroundColor Green
}

# 檢查配置文件
Write-Host "📝 檢查配置文件..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Write-Host "❌ 錯誤: 未找到 .env 文件" -ForegroundColor Red
    Write-Host "請復制 .env.example 並重命名為 .env，然後填入你的 Discord Bot Token" -ForegroundColor Yellow
    exit 1
}

# 檢查數據庫
Write-Host "🗄️ 檢查數據庫..." -ForegroundColor Yellow
if (-not (Test-Path "discord_tags.db")) {
    Write-Host "✅ 數據庫將在首次運行時自動創建" -ForegroundColor Green
} else {
    Write-Host "✅ 數據庫已存在" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "🚀 啟動 Bot..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 啟動 Bot
python main.py