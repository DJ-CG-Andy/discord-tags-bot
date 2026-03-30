# Check checkin_config table
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
    print("Checking checkin_config table...")
    
    result = await execute_d1("SELECT * FROM checkin_config")
    
    if result.get("success") and result.get("result"):
        records = result["result"][0].get("results", [])
        if records:
            print(f"\nFound {len(records)} checkin config(s):")
            for record in records:
                print(f"\nGuild ID: {record.get('guild_id')}")
                print(f"Channel ID: {record.get('channel_id')}")
                print(f"Checkin Time: {record.get('checkin_time')}")
                print(f"GIF URL: {record.get('gif_url') or '(not set)'}")
        else:
            print("No checkin config found")
    else:
        print("Query failed")

if __name__ == "__main__":
    asyncio.run(main())