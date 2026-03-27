# 安全啟動 Discord Bot（確保只有一個實例）

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Discord Bot 安全啟動腳本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 檢查 Python 進程
Write-Host "【步驟 1】檢查是否已有 bot 在運行" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue

if ($pythonProcesses) {
    Write-Host "⚠️  發現 $($pythonProcesses.Count) 個 Python 進程在運行" -ForegroundColor Yellow
    Write-Host ""
    
    # 檢查是否有進程運行 main.py
    $botRunning = $false
    foreach ($proc in $pythonProcesses) {
        try {
            $commandLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
            if ($commandLine -match "main\.py") {
                $botRunning = $true
                Write-Host "✗ 檢測到 Discord Bot 已在運行！" -ForegroundColor Red
                Write-Host "  進程 ID: $($proc.Id)" -ForegroundColor White
                Write-Host "  啟動時間: $($proc.StartTime)" -ForegroundColor White
                Write-Host "  命令行: $commandLine" -ForegroundColor White
                break
            }
        } catch {
            # 無法獲取命令行，無法確定
        }
    }
    
    if ($botRunning) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "錯誤：Bot 已在運行" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "請先停止現有的 bot 實例：" -ForegroundColor Yellow
        Write-Host "1. 運行 diagnose_multi_instance.ps1 診斷問題" -ForegroundColor White
        Write-Host "2. 運行 check_and_stop_bots.ps1 停止所有 bot" -ForegroundColor White
        Write-Host "3. 或者手動關閉運行 bot 的終端窗口" -ForegroundColor White
        Write-Host ""
        exit 1
    } else {
        Write-Host "✓ 沒有檢測到 Discord Bot 在運行" -ForegroundColor Green
        Write-Host "  （有其他 Python 進程，但不是 bot）" -ForegroundColor Gray
    }
} else {
    Write-Host "✓ 沒有 Python 進程在運行" -ForegroundColor Green
}

Write-Host ""

# 檢查數據庫文件
Write-Host "【步驟 2】檢查數據庫文件" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

if (Test-Path "discord_tags.db") {
    Write-Host "✓ 找到數據庫文件: discord_tags.db" -ForegroundColor Green
    
    # 檢查是否有文件鎖定
    try {
        $stream = [System.IO.File]::Open("discord_tags.db", 'Open', 'Read', 'ReadWrite')
        $stream.Close()
        Write-Host "✓ 數據庫文件未被鎖定" -ForegroundColor Green
    } catch {
        Write-Host "✗ 數據庫文件被鎖定" -ForegroundColor Red
        Write-Host ""
        Write-Host "錯誤：數據庫文件被鎖定，可能有進程正在使用" -ForegroundColor Red
        Write-Host "請運行 diagnose_multi_instance.ps1 診斷問題" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "✓ 數據庫文件不存在，將在首次運行時創建" -ForegroundColor Green
}

Write-Host ""

# 檢查配置文件
Write-Host "【步驟 3】檢查配置文件" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

if (Test-Path ".env") {
    Write-Host "✓ 找到配置文件: .env" -ForegroundColor Green
} else {
    Write-Host "✗ 未找到配置文件: .env" -ForegroundColor Red
    Write-Host "請復制 .env.example 並重命名為 .env" -ForegroundColor Yellow
    exit 1
}

if (Test-Path "config.json") {
    Write-Host "✓ 找到配置文件: config.json" -ForegroundColor Green
} else {
    Write-Host "✗ 未找到配置文件: config.json" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 檢查依賴
Write-Host "【步驟 4】檢查依賴包" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$discordInstalled = pip list | Select-String "discord.py"
if ($discordInstalled) {
    Write-Host "✓ discord.py 已安裝" -ForegroundColor Green
} else {
    Write-Host "✗ discord.py 未安裝" -ForegroundColor Red
    Write-Host "正在安裝依賴包..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

Write-Host ""

# 啟動 Bot
Write-Host "【步驟 5】啟動 Bot" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ 所有檢查通過，正在啟動 Bot..." -ForegroundColor Green
Write-Host ""
Write-Host "提示：" -ForegroundColor Yellow
Write-Host "- 按下 Ctrl+C 可以停止 bot" -ForegroundColor White
Write-Host "- 請確保只運行一個 bot 實例" -ForegroundColor White
Write-Host "- 如果遇到問題，運行 diagnose_multi_instance.ps1" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 啟動 bot
python main.py