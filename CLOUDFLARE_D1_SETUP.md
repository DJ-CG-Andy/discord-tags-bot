# Cloudflare D1 數據庫遷移指南

## 📋 概述

本指南將幫助你將本地 SQLite 數據庫遷移到 Cloudflare D1 雲端數據庫，確保數據不會丟失。

---

## 🚀 遷移步驟

### 第一步：準備工作

#### 1. 安裝 Node.js 和 npm
如果你還沒有安裝 Node.js：
- 訪問 https://nodejs.org/
- 下載並安裝 LTS 版本

#### 2. 安裝 Wrangler CLI
```bash
npm install -g wrangler
```

驗證安裝：
```bash
wrangler --version
```

---

### 第二步：設置 Cloudflare 帳號

#### 1. 創建 Cloudflare 帳號
- 訪問 https://dash.cloudflare.com/sign-up
- 註冊免費帳號

#### 2. 獲取 API Token
1. 登錄 Cloudflare Dashboard
2. 點擊右上角用戶頭像 → 「我的個人資料」
3. 選擇「API Token」標籤
4. 點擊「Create Token」
5. 使用「Edit Cloudflare Workers」模板
6. 確保權限包括：
   - Account → D1 → Edit
7. 創建並複製 token（妥善保存）

#### 3. 獲取 Account ID
1. 在 Cloudflare Dashboard 右側邊欄
2. 找到「Account ID」並複制

---

### 第三步：創建 D1 數據庫

#### 1. 登錄 Wrangler
```bash
wrangler login
```
這會打開瀏覽器進行授權。

#### 2. 創建數據庫
```bash
cd c:\Users\user\Desktop\新增資料夾\discord_tags
wrangler d1 create discord-tags-db
```

記住輸出的數據庫 ID（格式類似：`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`）

---

### 第四步：配置本地環境

#### 1. 更新 wrangler.toml
打開 `wrangler.toml`，將 `your-database-id-here` 替換為實際的數據庫 ID：

```toml
[[d1_databases]]
binding = "DB"
database_name = "discord-tags-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # 替換為你的 ID
```

#### 2. 導出現有數據
```bash
cd c:\Users\user\Desktop\新增資料夾\discord_tags
python migrate_to_d1.py
```

這會生成兩個文件：
- `migration.sql` - SQL 格式的遷移文件
- `migration.json` - JSON 格式的備份文件

---

### 第五步：初始化 D1 數據庫

#### 1. 創建表結構
```bash
wrangler d1 execute discord-tags-db --command="CREATE TABLE tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, category TEXT NOT NULL, emoji TEXT DEFAULT '🏷️', description TEXT, image_url TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, color INTEGER DEFAULT 5814783)"

wrangler d1 execute discord-tags-db --command="CREATE TABLE message_tags (id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT NOT NULL, channel_id TEXT NOT NULL, guild_id TEXT NOT NULL, tag_id INTEGER NOT NULL, tagged_by TEXT NOT NULL, tagged_at TEXT DEFAULT CURRENT_TIMESTAMP, message_content TEXT, author_id TEXT, created_at TEXT, FOREIGN KEY (tag_id) REFERENCES tags(id), UNIQUE(message_id, tag_id))"
```

#### 2. 導入數據
```bash
wrangler d1 execute discord-tags-db --file=migration.sql
```

---

### 第六步：配置 Render

#### 1. 在 Render 設置環境變量
訪問你的 Render 服務 → Environment → Add Environment Variable

添加以下變量：

| 變量名 | 值 | 說明 |
|--------|------|------|
| `DISCORD_BOT_TOKEN` | 你的 Bot Token | Discord Bot Token |
| `DATABASE_PATH` | 留空或設為 `local` | 不再使用本地數據庫 |
| `USE_D1` | `true` | 啟用 D1 模式 |
| `CLOUDFLARE_ACCOUNT_ID` | 你的 Account ID | Cloudflare Account ID |
| `CLOUDFLARE_DATABASE_ID` | 數據庫 ID | D1 數據庫 ID |
| `CLOUDFLARE_API_TOKEN` | API Token | Cloudflare API Token |

#### 2. 更新 main.py
在 `main.py` 中修改數據庫初始化：

```python
# 原來的代碼
db = Database(os.getenv("DATABASE_PATH", "discord_tags.db"))

# 修改為
use_d1 = os.getenv("USE_D1", "false").lower() == "true"
db = Database(os.getenv("DATABASE_PATH", "discord_tags.db"), use_d1=use_d1)
```

如果使用新的 `database_d1.py`：

```python
# 在導入部分修改
# from database import Database
from database_d1 import Database
```

---

### 第七步：測試

#### 1. 重新部署到 Render
```bash
git add .
git commit -m "feat: 遷移到 Cloudflare D1"
git push origin main
```

Render 會自動重新部署。

#### 2. 檢查部署日誌
在 Render 控制台查看日誌，確認：
- 沒有錯誤
- Bot 成功連接到 D1

#### 3. 測試功能
在 Discord 中測試：
- 創建標籤
- 為消息添加標籤
- 查看標籤列表

---

## 🔧 故障排除

### 問題 1：D1 API 錯誤
**錯誤訊息：** `D1 API 錯誤: 403 - Forbidden`

**解決方法：**
- 檢查 API Token 權限是否正確
- 確認 Account ID 是否正確
- 確認 Database ID 是否正確

### 問題 2：遷移失敗
**錯誤訊息：** `遷移失敗`

**解決方法：**
- 檢查 `migration.sql` 文件格式
- 手動執行 SQL 語句
- 使用 JSON 備份手動導入

### 問題 3：數據不顯示
**症狀：** Bot 運行正常但看不到標籤

**解決方法：**
- 檢查環境變量 `USE_D1` 是否設置為 `true`
- 查看日誌確認是否連接到 D1
- 驗證數據是否成功導入到 D1

---

## 📊 管理數據庫

### 查看 D1 數據庫
```bash
wrangler d1 execute discord-tags-db --command="SELECT * FROM tags"
```

### 添加索引
```bash
wrangler d1 execute discord-tags-db --command="CREATE INDEX IF NOT EXISTS idx_message_tags_message ON message_tags(message_id)"
```

### 清空數據
```bash
wrangler d1 execute discord-tags-db --command="DELETE FROM message_tags"
wrangler d1 execute discord-tags-db --command="DELETE FROM tags"
```

---

## 💰 成本

Cloudflare D1 免費計劃：
- ✅ 每天免費 5,000,000 次讀取
- ✅ 每天免費 100,000 次寫入
- ✅ 免費 5 GB 存儲

對於 Discord Bot 來說，免費計劃完全夠用！

---

## 🎯 下一步

遷移完成後：
1. 刪除本地 `discord_tags.db` 文件（不再需要）
2. 刪除 `migration.sql` 和 `migration.json`（已遷移完成）
3. 定期備份 D1 數據（使用 wrangler d1 export）

---

## 📞 需要幫助？

如有問題：
1. 查看 Cloudflare D1 文檔：https://developers.cloudflare.com/d1/
2. 查看日誌找出錯誤
3. 使用 `wrangler d1 execute` 測試 SQL

---

**預計時間：** 20-30 分鐘
**難度：** ⭐⭐⭐☆☆
**成本：** 免费 🆓