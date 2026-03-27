from local SQLite database migration to Cloudflare D1

import aiosqlite
import json
from datetime import datetime

async def export_to_sql(db_path: str = "discord_tags.db", output_file: str = "migration.sql"):
    """Export database to SQL file"""
    
    sql_statements = []
    
    async with aiosqlite.connect(db_path) as db:
        # 1. Export tags table
        print("📦 Exporting tags table...")
        async with db.execute('SELECT * FROM tags') as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                id, name, category, emoji, description, image_url, created_at, color = row
                sql = f"INSERT INTO tags (id, name, category, emoji, description, image_url, created_at, color) VALUES ({id}, '{name}', '{category}', '{emoji}', '{description or ''}', '{image_url or ''}', '{created_at}', {color});"
                sql_statements.append(sql)
            print(f"   ✅ Exported {len(rows)} tags")
        
        # 2. Export message_tags table
        print("📦 Exporting message_tags table...")
        async with db.execute('SELECT * FROM message_tags') as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                id, message_id, channel_id, guild_id, tag_id, tagged_by, tagged_at, message_content, author_id, created_at = row
                # Escape single quotes
                message_content = (message_content or '').replace("'", "''")
                sql = f"INSERT INTO message_tags (id, message_id, channel_id, guild_id, tag_id, tagged_by, tagged_at, message_content, author_id, created_at) VALUES ({id}, '{message_id}', '{channel_id}', '{guild_id}', {tag_id}, '{tagged_by}', '{tagged_at}', '{message_content}', '{author_id}', '{created_at}');"
                sql_statements.append(sql)
            print(f"   ✅ Exported {len(rows)} message tags")
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("-- Migration SQL File\n")
        f.write(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("-- Tags\n")
        f.write("\n".join([s for s in sql_statements if "tags VALUES" in s]))
        f.write("\n\n-- Message Tags\n")
        f.write("\n".join([s for s in sql_statements if "message_tags VALUES" in s]))
    
    print(f"\n✅ Export complete! Saved to: {output_file}")
    print(f"📊 Total {len(sql_statements)} SQL statements")

async def export_to_json(db_path: str = "discord_tags.db", output_file: str = "migration.json"):
    """Export database to JSON file (backup)"""
    
    data = {
        "tags": [],
        "message_tags": []
    }
    
    async with aiosqlite.connect(db_path) as db:
        # 1. Export tags table
        print("📦 Exporting tags table to JSON...")
        async with db.execute('SELECT * FROM tags') as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                data["tags"].append({
                    "id": row[0],
                    "name": row[1],
                    "category": row[2],
                    "emoji": row[3],
                    "description": row[4],
                    "image_url": row[5],
                    "created_at": row[6],
                    "color": row[7]
                })
            print(f"   ✅ Exported {len(data['tags'])} tags")
        
        # 2. Export message_tags table
        print("📦 Exporting message_tags table to JSON...")
        async with db.execute('SELECT * FROM message_tags') as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                data["message_tags"].append({
                    "id": row[0],
                    "message_id": row[1],
                    "channel_id": row[2],
                    "guild_id": row[3],
                    "tag_id": row[4],
                    "tagged_by": row[5],
                    "tagged_at": row[6],
                    "message_content": row[7],
                    "author_id": row[8],
                    "created_at": row[9]
                })
            print(f"   ✅ Exported {len(data['message_tags'])} message tags")
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Export complete! Saved to: {output_file}")

if __name__ == "__main__":
    import asyncio
    
    print("=" * 60)
    print("  Migration to Cloudflare D1 - Data Export Tool")
    print("=" * 60)
    print()
    
    # Export as SQL
    asyncio.run(export_to_sql())
    
    print()
    
    # Export as JSON (backup)
    asyncio.run(export_to_json())
    
    print()
    print("=" * 60)
    print("Next steps:")
    print("1. Install wrangler: npm install -g wrangler")
    print("2. Login to Cloudflare: wrangler login")
    print("3. Create D1 database: wrangler d1 create discord-tags-db")
    print("4. Update database_id in wrangler.toml")
    print("5. Execute migration: wrangler d1 execute discord-tags-db --file=migration.sql")
    print("=" * 60)