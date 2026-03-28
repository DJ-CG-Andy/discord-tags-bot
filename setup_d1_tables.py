"""
創建 D1 表結構
"""
import requests

ACCOUNT_ID = "a511d051b5fb441b2832c4049024998a"
DATABASE_ID = "443e3f3f-4903-4367-8dcb-f8df2b2c44ec"
API_TOKEN = "cfut_1FVHRvaWtrd8W2IINr9QO0nxVfdhucqsvRRUNRhc380bcc6f"

def execute_query(sql, params=None):
    """執行 D1 查詢"""
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {"sql": sql}
    if params:
        data["params"] = params
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()

print("=" * 60)
print("創建 D1 表結構")
print("=" * 60)

# 創建 tags 表
print("正在創建 tags 表...")
sql_tags = """
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    emoji TEXT DEFAULT '🏷️',
    description TEXT,
    image_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    color INTEGER DEFAULT 5814783
)
"""
result = execute_query(sql_tags)
if result.get("success"):
    print("✅ tags 表創建成功")
else:
    print("❌ tags 表創建失敗")
    print(result)

# 創建 message_tags 表
print("\n正在創建 message_tags 表...")
sql_message_tags = """
CREATE TABLE IF NOT EXISTS message_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    tagged_by TEXT NOT NULL,
    tagged_at TEXT DEFAULT CURRENT_TIMESTAMP,
    message_content TEXT,
    author_id TEXT,
    created_at TEXT,
    FOREIGN KEY (tag_id) REFERENCES tags(id),
    UNIQUE(message_id, tag_id)
)
"""
result = execute_query(sql_message_tags)
if result.get("success"):
    print("✅ message_tags 表創建成功")
else:
    print("❌ message_tags 表創建失敗")
    print(result)

# 創建 checkin_config 表
print("\n正在創建 checkin_config 表...")
sql_checkin_config = """
CREATE TABLE IF NOT EXISTS checkin_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    checkin_time TEXT DEFAULT "00:00",
    gif_url TEXT DEFAULT "",
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""
result = execute_query(sql_checkin_config)
if result.get("success"):
    print("✅ checkin_config 表創建成功")
else:
    print("❌ checkin_config 表創建失敗")
    print(result)

# 創建 checkin_records 表
print("\n正在創建 checkin_records 表...")
sql_checkin_records = """
CREATE TABLE IF NOT EXISTS checkin_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    checkin_date TEXT NOT NULL,
    streak_days INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, guild_id, checkin_date)
)
"""
result = execute_query(sql_checkin_records)
if result.get("success"):
    print("✅ checkin_records 表創建成功")
else:
    print("❌ checkin_records 表創建失敗")
    print(result)

# 創建 gif_change_requests 表
print("\n正在創建 gif_change_requests 表...")
sql_gif_requests = """
CREATE TABLE IF NOT EXISTS gif_change_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""
result = execute_query(sql_gif_requests)
if result.get("success"):
    print("✅ gif_change_requests 表創建成功")
else:
    print("❌ gif_change_requests 表創建失敗")
    print(result)

print("\n" + "=" * 60)
print("✅ D1 表創建完成！")
print("=" * 60)
print(f"Database ID: {DATABASE_ID}")
print()
print("接下來需要：")
print("1. 更新 Render 環境變量")
print("2. 更新本地 .env 文件")
print("3. 重新部署")