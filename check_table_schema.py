import aiohttp
import asyncio
import os
from dotenv import load_dotenv

# 加載環境變量
load_dotenv()

ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
DATABASE_ID = os.getenv("CLOUDFLARE_DATABASE_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

async def execute_d1(sql, params=None):
    """執行 D1 查詢"""
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "sql": sql,
        "params": params or []
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            result = await response.json()
            return result

async def main():
    print("🔍 檢查 tags 表的結構...")
    
    # D1 使用 SQLite，可以查詢 sqlite_master
    result = await execute_d1("SELECT sql FROM sqlite_master WHERE type='table' AND name='tags'")
    
    if result.get("success") and result.get("result"):
        tables = result["result"][0].get("results", [])
        if tables:
            print(f"\n✅ tags 表的結構:")
            print(tables[0].get("sql"))
        else:
            print("❌ 沒有找到 tags 表")
    else:
        print("❌ 查詢失敗")

if __name__ == "__main__":
    asyncio.run(main())