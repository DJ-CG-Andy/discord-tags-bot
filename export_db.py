import aiosqlite
import asyncio

async def export_db():
    db_path = "discord_tags.db"
    
    async with aiosqlite.connect(db_path) as db:
        # Export tags
        print("Exporting tags...")
        async with db.execute('SELECT * FROM tags') as cursor:
            rows = await cursor.fetchall()
            with open('tags_export.txt', 'w', encoding='utf-8') as f:
                for row in rows:
                    f.write(f"{row}\n")
            print(f"Exported {len(rows)} tags")
        
        # Export message_tags
        print("Exporting message_tags...")
        async with db.execute('SELECT * FROM message_tags') as cursor:
            rows = await cursor.fetchall()
            with open('message_tags_export.txt', 'w', encoding='utf-8') as f:
                for row in rows:
                    f.write(f"{row}\n")
            print(f"Exported {len(rows)} message_tags")
    
    print("Export complete!")

if __name__ == "__main__":
    asyncio.run(export_db())