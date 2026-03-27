# Discord 標籤系統 Bot - 簡化部署腳本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Discord 標籤系統 Bot - 部署到 GitHub" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 檢查 Git 是否已初始化
if (-not (Test-Path ".git")) {
    Write-Host "❌ 錯誤: Git 倉庫未初始化" -ForegroundColor Red
    Write-Host "請先運行: git init" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Git 倉庫已初始化" -ForegroundColor Green
Write-Host ""

# 設置分支名稱為 main
Write-Host "🔄 設置分支名稱為 main..." -ForegroundColor Yellow
git branch -M main
Write-Host "✅ 分支名稱已設置為 main" -ForegroundColor Green
Write-Host ""

# 詢問 GitHub 倉庫 URL
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  創建 GitHub 倉庫" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "請按照以下步驟創建 GitHub 倉庫：" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. 訪問 https://github.com/new" -ForegroundColor White
Write-Host "2. 倉庫名稱: discord-tags-bot" -ForegroundColor White
Write-Host "3. 勾選 Public" -ForegroundColor White
Write-Host "4. **不要** 勾選 'Add a README file'" -ForegroundColor Red
Write-Host "5. 點擊 'Create repository'" -ForegroundColor White
Write-Host ""
Write-Host "6. 從新創建的倉庫頁面復制 HTTPS URL" -ForegroundColor Yellow
Write-Host "   URL 格式: https://github.com/你的用戶名/discord-tags-bot.git" -ForegroundColor White
Write-Host ""

$repoUrl = Read-Host "請粘貼你的 GitHub 倉庫 URL"

# 驗證 URL
if ($repoUrl -notmatch "github\.com") {
    Write-Host "❌ URL 不正確，應該是 GitHub 倉庫 URL" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  推送代碼到 GitHub" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 檢查是否已經有遠程倉庫
$remoteUrl = git remote get-url origin 2>$null
if ($remoteUrl) {
    Write-Host "⚠️  已檢測到遠程倉庫: $remoteUrl" -ForegroundColor Yellow
    $update = Read-Host "是否要更新遠程倉庫 URL? (y/n)"
    if ($update -eq "y" -or $update -eq "Y") {
        git remote set-url origin $repoUrl
        Write-Host "✅ 遠程倉庫 URL 已更新" -ForegroundColor Green
    }
} else {
    # 添加遠程倉庫
    git remote add origin $repoUrl
    Write-Host "✅ 遠程倉庫已添加" -ForegroundColor Green
}

# 推送代碼
Write-Host ""
Write-Host "📤 正在推送代碼到 GitHub..." -ForegroundColor Yellow
Write-Host ""

$pushResult = git push -u origin main
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host ""
    Write-Host "✅ 代碼推送成功！" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "❌ 推送失敗" -ForegroundColor Red
    Write-Host "可能的原因:" -ForegroundColor Yellow
    Write-Host "1. 倉庫 URL 不正確" -ForegroundColor White
    Write-Host "2. 未配置 Git 認證" -ForegroundColor White
    Write-Host "3. 網絡連接問題" -ForegroundColor White
    Write-Host ""
    Write-Host "請檢查錯誤信息並重試" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  下一步：部署到 Render" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 按照以下步驟部署到 Render：" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. 訪問 https://dashboard.render.com/" -ForegroundColor White
Write-Host "2. 使用 GitHub 賬號登錄" -ForegroundColor White
Write-Host "3. 點擊 'New +' -> 'Web Service'" -ForegroundColor White
Write-Host "4. 選擇 'discord-tags-bot' 倉庫" -ForegroundColor White
Write-Host "5. 配置如下：" -ForegroundColor White
Write-Host "   - Name: discord-tags-bot" -ForegroundColor White
Write-Host "   - Runtime: Python 3" -ForegroundColor White
Write-Host "   - Build Command: pip install -r requirements.txt" -ForegroundColor White
Write-Host "   - Start Command: python main.py" -ForegroundColor White
Write-Host ""
Write-Host "6. 添加環境變量：" -ForegroundColor White
Write-Host "   DISCORD_BOT_TOKEN = 你的_Bot_Token" -ForegroundColor White
Write-Host ""
Write-Host "7. 配置持久化存儲：" -ForegroundColor White
Write-Host "   - Mount Path: /opt/render/project/data" -ForegroundColor White
Write-Host "   - Size: 1 GB" -ForegroundColor White
Write-Host ""
Write-Host "8. 點擊 'Create Web Service'" -ForegroundColor White
Write-Host ""
Write-Host "💡 詳細說明請查看 RENDER_GUIDE.md" -ForegroundColor Yellow
Write-Host ""
Write-Host "✅ 準備工作完成！現在可以部署到 Render 了！" -ForegroundColor Green