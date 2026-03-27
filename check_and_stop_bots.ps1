# 檢查並停止所有運行中的 Discord bot 實例

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  檢查 Discord Bot 實例" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 查找所有運行中的 Python 進程
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue

if ($pythonProcesses) {
    Write-Host "找到 $($pythonProcesses.Count) 個 Python 進程：" -ForegroundColor Yellow
    Write-Host ""
    
    $count = 0
    foreach ($proc in $pythonProcesses) {
        $count++
        Write-Host "[$count] 進程 ID: $($proc.Id)" -ForegroundColor White
        Write-Host "    啟動時間: $($proc.StartTime)" -ForegroundColor Gray
        Write-Host "    路徑: $($proc.Path)" -ForegroundColor Gray
        
        # 檢查這個進程是否運行 main.py
        try {
            $commandLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
            if ($commandLine -match "main\.py") {
                Write-Host "    ⚠️  檢測到運行 main.py" -ForegroundColor Red
            }
        } catch {
            Write-Host "    無法獲取命令行參數" -ForegroundColor Gray
        }
        Write-Host ""
    }
    
    Write-Host "========================================" -ForegroundColor Cyan
    $response = Read-Host "是否要停止所有 Python 進程？(y/n)"
    
    if ($response -eq 'y' -or $response -eq 'Y') {
        Write-Host ""
        Write-Host "正在停止所有 Python 進程..." -ForegroundColor Yellow
        
        Stop-Process -Name python -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        
        # 再次檢查
        $remaining = Get-Process python -ErrorAction SilentlyContinue
        if ($remaining) {
            Write-Host "⚠️  仍有 $($remaining.Count) 個 Python 進程在運行" -ForegroundColor Yellow
        } else {
            Write-Host "✅ 所有 Python 進程已停止" -ForegroundColor Green
        }
    }
} else {
    Write-Host "✅ 沒有找到運行中的 Python 進程" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "檢查完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "提示：" -ForegroundColor Yellow
Write-Host "1. 請確保只運行一個 bot 實例" -ForegroundColor White
Write-Host "2. 如果問題仍然存在，請重啟電腦" -ForegroundColor White
Write-Host "3. 然後只運行一次啟動腳本" -ForegroundColor White