# Update GIF URL in checkin_config
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
    gif_url = "https://media.discordapp.net/stickers/1484898455502454886.gif?size=240"
    guild_id = "1484784310316957828"
    
    print(f"Updating GIF URL for guild {guild_id}...")
    print(f"New GIF URL: {gif_url}")
    
    # Update the checkin config
    result = await execute_d1(
        "UPDATE checkin_config SET gif_url = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
        [gif_url, guild_id]
    )
    
    if result.get("success"):
        print("✅ GIF URL updated successfully")
        
        # Verify the update
        result = await execute_d1("SELECT * FROM checkin_config WHERE guild_id = ?", [guild_id])
        if result.get("success") and result.get("result"):
            records = result["result"][0].get("results", [])
            if records:
                record = records[0]
                print(f"\nUpdated config:")
                print(f"Guild ID: {record.get('guild_id')}")
                print(f"Channel ID: {record.get('channel_id')}")
                print(f"Checkin Time: {record.get('checkin_time')}")
                print(f"GIF URL: {record.get('gif_url')}")
    else:
        print(f"❌ Failed to update GIF URL: {result.get('errors')}")

if __name__ == "__main__":
    asyncio.run(main())