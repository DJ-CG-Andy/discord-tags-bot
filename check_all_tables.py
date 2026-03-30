"""
檢查所有 D1 表中的數據
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

async def check_table(table_name):
    """檢查表中的記錄"""
    print(f"\n{'='*60}")
    print(f"🔍 檢查表: {table_name}")
    print(f"{'='*60}")
    
    result = await execute_d1(f"SELECT * FROM {table_name}")
    
    if result.get("success") and result.get("result"):
        records = result["result"][0].get("results", [])
        print(f"找到 {len(records)} 條記錄")
        
        if records:
            for i, record in enumerate(records[:5], 1):  # 只顯示前 5 條
                print(f"\n記錄 {i}:")
                for key, value in record.items():
                    # 檢查是否有損壞的數據
                    if isinstance(value, str) and "[object Object]" in value:
                        print(f"  ❌ {key}: {value} (損壞)")
                    else:
                        value_str = str(value)
                        if len(value_str) > 50:
                            value_str = value_str[:50] + "..."
                        print(f"  {key}: {value_str}")
            
            if len(records) > 5:
                print(f"\n... 還有 {len(records) - 5} 條記錄未顯示")
        else:
            print("✅ 表為空")
    else:
        print(f"❌ 查詢失敗: {result}")

async def main():
    tables = ["tags", "message_tags", "checkin_config", "checkin_records", "gif_change_requests"]
    
    for table in tables:
        await check_table(table)
    
    print(f"\n{'='*60}")
    print("✅ 檢查完成")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())