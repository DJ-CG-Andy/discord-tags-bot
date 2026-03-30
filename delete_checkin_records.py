"""
刪除所有簽到記錄
"""
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
    print("🗑️ 檢查當前簽到記錄...")
    result = await execute_d1("SELECT * FROM checkin_records")
    
    if result.get("success") and result.get("result"):
        records = result["result"][0].get("results", [])
        print(f"找到 {len(records)} 條簽到記錄:")
        for record in records:
            print(f"  - 用戶 {record.get('user_id')}: {record.get('checkin_date')}")
        
        if records:
            print("\n🗑️ 刪除所有簽到記錄...")
            result = await execute_d1("DELETE FROM checkin_records")
            if result.get("success"):
                print("✅ 所有簽到記錄已刪除")
            else:
                print("❌ 刪除失敗")
        else:
            print("✅ 沒有需要刪除的記錄")
    else:
        print("❌ 查詢失敗")

if __name__ == "__main__":
    asyncio.run(main())
