"""
測試簡單的 D1 插入
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
    
    # 直接傳遞參數數組，不使用 type 字段
    data = {
        "sql": sql
    }
    
    if params:
        data["params"] = params
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            result = await response.json()
            return result

async def main():
    print("🧪 測試 1: 使用簡單的參數格式")
    
    # 先刪除所有測試數據
    print("\n1️⃣ 刪除所有標籤...")
    result = await execute_d1("DELETE FROM tags")
    print(f"結果: {result}")
    
    # 插入測試數據
    print("\n2️⃣ 插入測試數據...")
    result = await execute_d1(
        "INSERT INTO tags (name, category, emoji, description, image_url, color) VALUES (?, ?, ?, ?, ?, ?)",
        ["測試標籤", "測試分類", "🏷️", "這是測試", "https://example.com/image.png", 123456]
    )
    print(f"結果: {result}")
    
    # 查詢數據
    print("\n3️⃣ 查詢數據...")
    result = await execute_d1("SELECT * FROM tags")
    print(f"結果: {result}")
    
    if result.get("success") and result.get("result"):
        records = result["result"][0].get("results", [])
        print(f"\n找到 {len(records)} 條記錄:")
        for i, record in enumerate(records, 1):
            print(f"\n記錄 {i}:")
            for key, value in record.items():
                print(f"  {key}: {value}")

if __name__ == "__main__":
    asyncio.run(main())