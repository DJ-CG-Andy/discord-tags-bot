"""
使用 Cloudflare API 創建 D1 數據庫
不需要 wrangler CLI

使用方法：
python create_d1_direct.py --account-id YOUR_ACCOUNT_ID --api-token YOUR_API_TOKEN
"""

import requests
import json
import sys
import argparse

def create_d1_database(account_id, api_token, database_name="discord-tags-db"):
    """
    使用 Cloudflare API 創建 D1 數據庫
    """
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "name": database_name
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        result = response.json()
        return result["result"]["uuid"]
    elif response.status_code == 409:
        # 數據庫已存在
        print("數據庫已存在，獲取現有數據庫 ID...")
        # 列出所有數據庫
        list_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database"
        list_response = requests.get(list_url, headers=headers)
        if list_response.status_code == 200:
            databases = list_response.json()["result"]
            for db in databases:
                if db["name"] == database_name:
                    return db["uuid"]
        return None
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None

def execute_d1_query(account_id, database_id, api_token, sql, params=None):
    """
    執行 D1 SQL 查詢
    """
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "sql": sql
    }
    
    if params:
        data["params"] = params
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="創建 Cloudflare D1 數據庫")
    parser.add_argument("--account-id", required=True, help="Cloudflare Account ID")
    parser.add_argument("--api-token", required=True, help="Cloudflare API Token")
    parser.add_argument("--database-name", default="discord-tags-db", help="數據庫名稱")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  Cloudflare D1 數據庫創建工具")
    print("=" * 60)
    print()
    
    # 創建數據庫
    print("正在創建/獲取 D1 數據庫...")
    
    database_id = create_d1_database(args.account_id, args.api_token, args.database_name)
    
    if database_id:
        print(f"✅ 數據庫準備完成！")
        print(f"Database ID: {database_id}")
        print()
        
        # 創建表結構
        print("正在創建表結構...")
        
        # 創建 tags 表
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
        result = execute_d1_query(args.account_id, database_id, args.api_token, sql_tags)
        
        if result and result.get("success"):
            print("✅ tags 表創建成功")
        else:
            print("❌ tags 表創建失敗")
        
        # 創建 message_tags 表
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
        result = execute_d1_query(args.account_id, database_id, args.api_token, sql_message_tags)
        
        if result and result.get("success"):
            print("✅ message_tags 表創建成功")
        else:
            print("❌ message_tags 表創建失敗")
        
        print()
        print("=" * 60)
        print("設置完成！")
        print("=" * 60)
        print()
        print("請在 Render 設置以下環境變量：")
        print()
        print("USE_D1 = true")
        print(f"CLOUDFLARE_ACCOUNT_ID = {args.account_id}")
        print(f"CLOUDFLARE_DATABASE_ID = {database_id}")
        print(f"CLOUDFLARE_API_TOKEN = {args.api_token}")
        print()
        print("注意：請妥善保存 API Token，不要泄露給他人！")
        print("=" * 60)
    else:
        print("❌ 數據庫創建失敗")
        print("請檢查：")
        print("1. Account ID 是否正確")
        print("2. API Token 是否有效")
        print("3. API Token 是否有 D1 權限（Account → D1 → Edit）")
        sys.exit(1)