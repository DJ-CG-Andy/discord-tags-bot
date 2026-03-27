# Discord 標籤系統 Bot - Render 部署指南

## 快速部署到 Render

### 第一步：準備 GitHub 倉庫

1. **初始化 Git 倉庫**
   ```bash
   cd discord_tags
   git init
   ```

2. **添加所有文件**
   ```bash
   git add .
   ```

3. **提交更改**
   ```bash
   git commit -m "Initial commit"
   ```

4. **創建 GitHub 倉庫**
   - 訪問 https://github.com/new
   - 倉庫名稱：`discord-tags-bot`
   - 勾選 "Public"
   - **不要** 勾選 "Add a README file"

5. **推送代碼**
   ```bash
   git remote add origin https://github.com/你的用戶名/discord-tags-bot.git
   git branch -M main
   git push -u origin main
   ```

### 第二步：在 Render 上部署

1. **登錄 Render**
   - 訪問 https://dashboard.render.com/
   - 使用 GitHub 賬號登錄

2. **創建新服務**
   - 點擊 "New +"
   - 選擇 "Web Service"

3. **連接 GitHub 倉庫**
   - 選擇 "discord-tags-bot" 倉庫
   - 點擊 "Connect"

4. **配置服務**
   - **Name**: discord-tags-bot
   - **Region**: 選擇離你最近的區域
   - **Branch**: main

5. **配置構建和運行**
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`

6. **配置環境變量**
   - 在 "Environment" 部分點擊 "Add Environment Variable"
   - 添加：
     ```
     Key: DISCORD_BOT_TOKEN
     Value: 你的_Bot_Token
     ```

7. **配置持久化存儲**
   - 滾動到 "Advanced" 部分
   - 找到 "Disk" 設置
   - 點擊 "Create New Disk"
   - 填寫：
     - **Name**: data
     - **Mount Path**: `/opt/render/project/data`
     - **Size**: 1 GB
   - 點擊 "Save"

8. **部署**
   - 點擊 "Create Web Service"
   - 等待 2-5 分鐘
   - 看到 "Live" 狀態就成功了！

### 第三步：驗證部署

1. 在 Render 控制台點擊 "Logs"
2. 應該看到：
   ```
   ✅ Discord標籤系統Bot 已啟動!
   ✅ 服務器: 1
   ✅ 數據庫初始化完成
   ```

3. 在 Discord 中測試：
   ```
   !help
   !tags
   ```

## 常見問題

### Q: 部署失敗怎麼辦？
A:
1. 檢查 Render Logs 查看錯誤信息
2. 確認環境變量設置正確
3. 檢查 Bot Token 是否有效

### Q: 如何更新代碼？
A:
```bash
git add .
git commit -m "Update code"
git push
```
Render 會自動重新部署！

### Q: 如何查看 Bot 日誌？
A:
1. 打開 Render 控制台
2. 選擇你的服務
3. 點擊 "Logs" 標籤

### Q: 免費層夠用嗎？
A: 完全夠用！免費層每月 750 小時，足夠運行一個 Discord Bot。

### Q: 數據會丟失嗎？
A: 不會！我們配置了持久化存儲，數據保存在磁盤上。

## 環境變量說明

| 變量名 | 必需 | 說明 |
|--------|------|------|
| DISCORD_BOT_TOKEN | ✅ | Discord Bot Token |
| DATABASE_PATH | ❌ | 數據庫路徑（默認：discord_tags.db） |

## 注意事項

1. **不要提交 .env 文件到 Git**
2. **確保 Bot Token 有效**
3. **定期備份數據庫**
4. **監控 Bot 運行狀態**

## 支持和幫助

如有問題，請檢查：
- Render Logs
- Discord Developer Portal
- GitHub Issues

---

**預計部署時間**: 5-10 分鐘
**難度**: ⭐☆☆☆☆（非常簡單）
**成本**: 免费 🆓