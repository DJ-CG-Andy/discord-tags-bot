# Cloudflare D1 快速設置腳本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Cloudflare D1 設置助手" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 檢查 Node.js 和 npm
Write-Host "【步驟 1】檢查環境" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$nodeInstalled = Get-Command node -ErrorAction SilentlyContinue
$npmInstalled = Get-Command npm -ErrorAction SilentlyContinue

if (-not $nodeInstalled) {
    Write-Host "❌ Node.js 未安裝" -ForegroundColor Red
    Write-Host "請訪問 https://nodejs.org/ 安裝 Node.js" -ForegroundColor Yellow
    exit 1
}

if (-not $npmInstalled) {
    Write-Host "❌ npm 未安裝" -ForegroundColor Red
    Write-Host "請訪問 https://nodejs.org/ 安裝 Node.js" -ForegroundColor Yellow
    exit 1
}

$nodeVersion = node --version
$npmVersion = npm --version

Write-Host "✅ Node.js 版本: $nodeVersion" -ForegroundColor Green
Write-Host "✅ npm 版本: $npmVersion" -ForegroundColor Green
Write-Host ""

# 檢查 wrangler
Write-Host "【步驟 2】檢查 Wrangler" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$wranglerInstalled = Get-Command wrangler -ErrorAction SilentlyContinue

if (-not $wranglerInstalled) {
    Write-Host "⬇️ 安裝 Wrangler CLI..." -ForegroundColor Yellow
    npm install -g wrangler
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Wrangler 安裝失敗" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Wrangler 安裝成功" -ForegroundColor Green
} else {
    $wranglerVersion = wrangler --version
    Write-Host "✅ Wrangler 已安裝: $wranglerVersion" -ForegroundColor Green
}

Write-Host ""

# 登錄 Wrangler
Write-Host "【步驟 3】登錄 Cloudflare" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

Write-Host "將在瀏覽器中打登錄頁面..." -ForegroundColor Cyan
Write-Host ""

wrangler login

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 登錄失敗" -ForegroundColor Red
    exit 1
}

Write-Host "✅ 登錄成功" -ForegroundColor Green
Write-Host ""

# 創建 D1 數據庫
Write-Host "【步驟 4】創建 D1 數據庫" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

Write-Host "正在創建 D1 數據庫..." -ForegroundColor Cyan

$d1Result = wrangler d1 create discord-tags-db 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 數據庫創建失敗" -ForegroundColor Red
    Write-Host $d1Result -ForegroundColor Gray
    exit 1
}

# 提取數據庫 ID
$d1Id = ($d1Result | Select-String "database_id").ToString().Trim()
$d1Id = $d1Id.Split("=")[1].Trim()

Write-Host "✅ 數據庫創建成功" -ForegroundColor Green
Write-Host "數據庫 ID: $d1Id" -ForegroundColor Cyan
Write-Host ""

# 更新 wrangler.toml
Write-Host "【步驟 5】更新 wrangler.toml" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$wranglerToml = @"
name = "discord-tags-bot"
main = "main.py"
compatibility_date = "2024-01-01"

[[d1_databases]]
binding = "DB"
database_name = "discord-tags-db"
database_id = "$d1Id"
"@

$wranglerToml | Out-File -FilePath "wrangler.toml" -Encoding utf8

Write-Host "✅ wrangler.toml 已更新" -ForegroundColor Green
Write-Host ""

# 導出數據
Write-Host "【步驟 6】導出現有數據" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

Write-Host "正在導出數據庫..." -ForegroundColor Cyan

python migrate_to_d1.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  數據導出失敗或沒有數據" -ForegroundColor Yellow
} else {
    Write-Host "✅ 數據導出成功" -ForegroundColor Green
}

Write-Host ""

# 創建表結構
Write-Host "【步驟 7】初始化 D1 數據庫" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

Write-Host "正在創建表結構..." -ForegroundColor Cyan

wrangler d1 execute discord-tags-db --command="CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, category TEXT NOT NULL, emoji TEXT DEFAULT '🏷️', description TEXT, image_url TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, color INTEGER DEFAULT 5814783)"

wrangler d1 execute discord-tags-db --command="CREATE TABLE IF NOT EXISTS message_tags (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT NOT NULL, channel_id TEXT NOT NULL, guild_id TEXT NOT NULL, tag_id INTEGER NOT NULL, tagged_by TEXT NOT NULL, tagged_at TEXT DEFAULT CURRENT_TIMESTAMP, message_content TEXT, author_id TEXT, created_at TEXT, FOREIGN KEY (tag_id) REFERENCES tags(id), UNIQUE(message_id, tag_id))"

Write-Host "✅ 表結構創建成功" -ForegroundColor Green
Write-Host ""

# 導入數據
Write-Host "【步驟 8】導入數據" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

if (Test-Path "migration.sql") {
    Write-Host "正在導入數據..." -ForegroundColor Cyan
    
    wrangler d1 execute discord-tags-db --file=migration.sql
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 數據導入成功" -ForegroundColor Green
    } else {
        Write-Host "⚠️  數據導入失敗" -ForegroundColor Yellow
        Write-Host "可能原因: 數據已存在或格式錯誤" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠️  未找到 migration.sql 文件" -ForegroundColor Yellow
}

Write-Host ""

# 顯示下一步
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "設置完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步：" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. 在 Cloudflare Dashboard 獲取以下信息：" -ForegroundColor White
Write-Host "   - Account ID (在右側邊欄)" -ForegroundColor Gray
Write-Host "   - API Token (My Profile → API Token → Create Token)" -ForegroundColor Gray
Write-Host ""
Write-Host "2. 在 Render 設置環境變量：" -ForegroundColor White
Write-Host "   USE_D1 = true" -ForegroundColor Cyan
Write-Host "   CLOUDFLARE_ACCOUNT_ID = 你的 Account ID" -ForegroundColor Cyan
Write-Host "   CLOUDFLARE_DATABASE_ID = $d1Id" -ForegroundColor Cyan
Write-Host "   CLOUDFLARE_API_TOKEN = 你的 API Token" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. 提交並推送到 GitHub：" -ForegroundColor White
Write-Host "   git add ." -ForegroundColor Gray
Write-Host "   git commit -m 'feat: 遷移到 Cloudflare D1'" -ForegroundColor Gray
Write-Host "   git push" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Render 會自動重新部署" -ForegroundColor Gray
Write-Host ""
Write-Host "詳細說明請查看: CLOUDFLARE_D1_SETUP.md" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan