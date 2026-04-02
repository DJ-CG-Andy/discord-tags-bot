"""
刪除所有簽到記錄，重置排行榜
"""

import os
import aiohttp
import asyncio

# D1 配置
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "a511d051b5fb441b2832c4049024998a")
CLOUDFLARE_DATABASE_ID = os.getenv("CLOUDFLARE_DATABASE_ID", "443e3f3f-4903-4367-8dcb-f8df2b2c44ec")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "cfut_1FVHRvaWtrd8W2IINr9QO0nxVfdhucqsvRRUNRhc380bcc6f")

async def delete_all_checkin_records():
    """刪除所有簽到記錄"""
    
    d1_api_url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{CLOUDFLARE_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        # 查詢當前記錄數量
        count_sql = "SELECT COUNT(*) as count FROM checkin_records"
        count_body = {"sql": count_sql, "params": []}
        
        async with session.post(d1_api_url, headers=headers, json=count_body) as response:
            result = await response.json()
            if result.get("success") and result.get("result"):
                count = result["result"][0]["results"][0]["count"]
                print(f"🔍 當前有 {count} 條簽到記錄")
            else:
                print("❌ 查詢失敗")
                return
        
        # 刪除所有記錄
        delete_sql = "DELETE FROM checkin_records"
        delete_body = {"sql": delete_sql, "params": []}
        
        async with session.post(d1_api_url, headers=headers, json=delete_body) as response:
            result = await response.json()
            if result.get("success"):
                print(f"✅ 所有簽到記錄已刪除")
                
                # 驗證
                async with session.post(d1_api_url, headers=headers, json=count_body) as response:
                    result = await response.json()
                    if result.get("success") and result.get("result"):
                        count = result["result"][0]["results"][0]["count"]
                        print(f"🔍 刪除後剩餘記錄: {count}")
            else:
                print(f"❌ 刪除失敗: {result}")

if __name__ == "__main__":
    print("🗑️ 刪除所有簽到記錄...")
    asyncio.run(delete_all_checkin_records())