"""
清理 D1 數據庫中的損壞數據
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
            print(f"SQL: {sql}")
            print(f"結果: {result}")
            return result

async def main():
    print("🔍 檢查 tags 表中的記錄...")
    result = await execute_d1("SELECT * FROM tags")
    
    if result.get("success") and result.get("result"):
        records = result["result"][0].get("results", [])
        print(f"\n找到 {len(records)} 條記錄:")
        for i, record in enumerate(records, 1):
            print(f"\n記錄 {i}:")
            for key, value in record.items():
                print(f"  {key}: {value}")
        
        # 檢查是否有損壞的記錄
        corrupted = [r for r in records if r.get("name") == "[object Object]"]
        if corrupted:
            print(f"\n❌ 發現 {len(corrupted)} 條損壞的記錄")
            
            # 刪除損壞的記錄
            for record in corrupted:
                record_id = record.get("id")
                print(f"\n🗑️ 刪除記錄 ID: {record_id}")
                delete_result = await execute_d1("DELETE FROM tags WHERE id = ?", [record_id])
                if delete_result.get("success"):
                    print("✅ 刪除成功")
                else:
                    print("❌ 刪除失敗")
        else:
            print("\n✅ 沒有發現損壞的記錄")
    else:
        print("❌ 查詢失敗")

if __name__ == "__main__":
    asyncio.run(main())
