# Discord Bot 多實例問題診斷腳本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Discord Bot 多實例診斷工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 檢查 Python 進程
Write-Host "【步驟 1】檢查 Python 進程" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue

if ($pythonProcesses) {
    Write-Host "✗ 發現 $($pythonProcesses.Count) 個 Python 進程在運行" -ForegroundColor Red
    Write-Host ""
    
    foreach ($proc in $pythonProcesses) {
        Write-Host "  進程 ID: $($proc.Id)" -ForegroundColor White
        Write-Host "  啟動時間: $($proc.StartTime)" -ForegroundColor Gray
        Write-Host "  運行時間: $((Get-Date) - $proc.StartTime | Select-Object -ExpandProperty TotalMinutes):.0f 分鐘" -ForegroundColor Gray
        
        # 嘗試獲取命令行
        try {
            $commandLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
            if ($commandLine) {
                Write-Host "  命令行: $commandLine" -ForegroundColor Gray
                
                if ($commandLine -match "main\.py") {
                    Write-Host "  ⚠️  檢測到 Discord Bot 實例！" -ForegroundColor Red
                }
            }
        } catch {
            Write-Host "  無法獲取命令行（需要管理員權限）" -ForegroundColor Gray
        }
        Write-Host ""
    }
} else {
    Write-Host "✓ 沒有找到 Python 進程" -ForegroundColor Green
}

Write-Host ""

# 2. 檢查 bot 日誌文件
Write-Host "【步驟 2】檢查 bot 日誌文件" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$logFiles = @(
    "bot_startup_log.txt",
    "bot_log.txt"
)

foreach ($logFile in $logFiles) {
    if (Test-Path $logFile) {
        Write-Host "✓ 找到日誌文件: $logFile" -ForegroundColor Green
        
        # 檢查最後修改時間
        $lastModified = (Get-Item $logFile).LastWriteTime
        Write-Host "  最後修改: $lastModified" -ForegroundColor Gray
        
        # 檢查文件大小
        $fileSize = (Get-Item $logFile).Length
        Write-Host "  文件大小: $([math]::Round($fileSize/1KB, 2)) KB" -ForegroundColor Gray
        
        # 讀取最後幾行
        $lastLines = Get-Content $logFile -Tail 5 -ErrorAction SilentlyContinue
        if ($lastLines) {
            Write-Host "  最後幾行內容:" -ForegroundColor Gray
            foreach ($line in $lastLines) {
                Write-Host "    $line" -ForegroundColor Gray
            }
        }
        Write-Host ""
    } else {
        Write-Host "✗ 未找到日誌文件: $logFile" -ForegroundColor Gray
    }
}

Write-Host ""

# 3. 檢查數據庫文件
Write-Host "【步驟 3】檢查數據庫文件" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$dbFiles = @("discord_tags.db", "discord_tags_backup.db")

foreach ($dbFile in $dbFiles) {
    if (Test-Path $dbFile) {
        Write-Host "✓ 找到數據庫文件: $dbFile" -ForegroundColor Green
        
        $lastModified = (Get-Item $dbFile).LastWriteTime
        Write-Host "  最後修改: $lastModified" -ForegroundColor Gray
        
        $fileSize = (Get-Item $dbFile).Length
        Write-Host "  文件大小: $([math]::Round($fileSize/1KB, 2)) KB" -ForegroundColor Gray
        
        # 檢查是否有文件鎖定
        try {
            $stream = [System.IO.File]::Open($dbFile, 'Open', 'Read', 'ReadWrite')
            $stream.Close()
            Write-Host "  ✓ 文件未被鎖定" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ 文件被鎖定（可能有進程正在使用）" -ForegroundColor Red
        }
        Write-Host ""
    } else {
        Write-Host "✗ 未找到數據庫文件: $dbFile" -ForegroundColor Gray
    }
}

Write-Host ""

# 4. 檢查多個 main.py 文件
Write-Host "【步驟 4】檢查多個 main.py 文件" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

$mainFiles = Get-ChildItem -Filter "main*.py" -ErrorAction SilentlyContinue

if ($mainFiles) {
    Write-Host "✗ 發現 $($mainFiles.Count) 個 main*.py 文件" -ForegroundColor Red
    foreach ($file in $mainFiles) {
        Write-Host "  - $($file.Name)" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "⚠️  警告：多個 main 文件可能導致混淆" -ForegroundColor Yellow
} else {
    Write-Host "✓ 沒有找到多個 main*.py 文件" -ForegroundColor Green
}

Write-Host ""

# 5. 提供解決方案
Write-Host "【步驟 5】診斷結果和解決方案" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($pythonProcesses -and $pythonProcesses.Count -gt 1) {
    Write-Host "✗ 診斷結果：檢測到多個 Python 進程" -ForegroundColor Red
    Write-Host ""
    Write-Host "【解決方案 1】停止所有 Python 進程" -ForegroundColor Cyan
    Write-Host "運行以下命令：" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File check_and_stop_bots.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "【解決方案 2】手動停止進程" -ForegroundColor Cyan
    Write-Host "運行：" -ForegroundColor Yellow
    foreach ($proc in $pythonProcesses) {
        Write-Host "  Stop-Process -Id $($proc.Id) -Force" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "【解決方案 3】重啟電腦" -ForegroundColor Cyan
    Write-Host "重啟電腦可以清除所有進程" -ForegroundColor Yellow
    Write-Host ""
} elseif ($pythonProcesses -and $pythonProcesses.Count -eq 1) {
    Write-Host "✓ 診斷結果：只有一個 Python 進程在運行" -ForegroundColor Green
    Write-Host ""
    Write-Host "如果仍然出現重複響應問題：" -ForegroundColor Yellow
    Write-Host "1. 檢查是否有其他終端窗口在運行 bot" -ForegroundColor White
    Write-Host "2. 檢查任務計劃程序是否有 bot 任務" -ForegroundColor White
    Write-Host "3. 嘗試重啟 bot" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "✓ 診斷結果：沒有 Python 進程在運行" -ForegroundColor Green
    Write-Host ""
    Write-Host "現在可以安全地啟動 bot：" -ForegroundColor Yellow
    Write-Host "  python main.py" -ForegroundColor White
    Write-Host "或運行：" -ForegroundColor White
    Write-Host "  .\啟動新Bot.bat" -ForegroundColor White
    Write-Host ""
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "診斷完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "如果問題仍然存在，請提供以下信息：" -ForegroundColor Yellow
Write-Host "1. 此腳本的輸出結果" -ForegroundColor White
Write-Host "2. bot_startup_log.txt 的完整內容" -ForegroundColor White
Write-Host "3. 你如何啟動 bot 的步驟" -ForegroundColor White