# Update GIF ID in checkin_config
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
    guild_id = "1484784310316957828"
    gif_id = "1484898455502454886"
    
    print(f"Updating GIF ID for guild {guild_id}...")
    print(f"New GIF ID: {gif_id}")
    
    # Update GIF ID
    result = await execute_d1(
        "UPDATE checkin_config SET gif_id = ? WHERE guild_id = ?",
        [gif_id, guild_id]
    )
    
    if result.get("success"):
        print("✅ GIF ID updated successfully")
    else:
        print(f"❌ Failed to update GIF ID: {result}")
    
    # Verify the change
    print("\nVerifying config...")
    result = await execute_d1(
        "SELECT * FROM checkin_config WHERE guild_id = ?",
        [guild_id]
    )
    
    if result.get("success") and result.get("result"):
        rows = result["result"][0].get("results", [])
        if rows:
            row = rows[0]
            print("\nUpdated config:")
            print(f"Guild ID: {row.get('guild_id')}")
            print(f"Channel ID: {row.get('channel_id')}")
            print(f"Checkin Time: {row.get('checkin_time')}")
            print(f"GIF URL: {row.get('gif_url')}")
            print(f"GIF ID: {row.get('gif_id')}")

if __name__ == "__main__":
    asyncio.run(main())