# Check gif_change_requests table structure
import aiohttp
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
DATABASE_ID = os.getenv("CLOUDFLARE_DATABASE_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

async def execute_d1(sql, params=None):
    """Execute D1 query"""
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
    print("Checking gif_change_requests table structure...")
    
    # D1 uses SQLite, can query sqlite_master
    result = await execute_d1("SELECT sql FROM sqlite_master WHERE type='table' AND name='gif_change_requests'")
    
    if result.get("success") and result.get("result"):
        tables = result["result"][0].get("results", [])
        if tables:
            print(f"\ngif_change_requests table structure:")
            print(tables[0].get("sql"))
        else:
            print("gif_change_requests table not found")
    else:
        print("Query failed")

if __name__ == "__main__":
    asyncio.run(main())
