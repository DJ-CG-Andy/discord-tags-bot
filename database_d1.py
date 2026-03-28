"""
Database module with Cloudflare D1 support
Supports both local SQLite and Cloudflare D1
"""

import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
import os
import aiohttp

@dataclass
class Tag:
    id: int
    name: str
    category: str
    emoji: str
    description: str
    image_url: str
    created_at: str
    color: int
    
    def __str__(self):
        return f"Tag(name={self.name}, emoji={self.emoji}, category={self.category})"

@dataclass
class MessageTag:
    id: int
    message_id: str
    channel_id: str
    guild_id: str
    tag_id: int
    tagged_by: str
    tagged_at: str
    message_content: str
    author_id: str
    created_at: str

class Database:
    def __init__(self, db_path: str = "discord_tags.db", use_d1: bool = False):
        self.db_path = db_path
        self.use_d1 = use_d1
        
        # 確保數據庫目錄存在（本地模式）
        if not use_d1:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                print(f"✅ 已創建數據庫目錄: {db_dir}")
        
        # Cloudflare D1 API 配置
        if use_d1:
            self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
            self.database_id = os.getenv("CLOUDFLARE_DATABASE_ID")
            self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
            self.d1_api_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}/query"
            
            if not all([self.account_id, self.database_id, self.api_token]):
                print("⚠️  警告: Cloudflare D1 環境變量未設置")
                print("   需要: CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_DATABASE_ID, CLOUDFLARE_API_TOKEN")
    
    async def _execute_d1(self, sql: str, params: tuple = ()) -> List[dict]:
        """執行 Cloudflare D1 查詢"""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        body = {
            "sql": sql,
            "params": []
        }
        
        # 處理參數
        for param in params:
            if isinstance(param, str):
                body["params"].append({"type": "text", "value": param})
            elif isinstance(param, int):
                body["params"].append({"type": "integer", "value": param})
            elif param is None:
                body["params"].append({"type": "null"})
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.d1_api_url, headers=headers, json=body) as response:
                print(f"🔍 D1 API 響應狀態: {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ D1 API 錯誤: {response.status} - {error_text}")
                    raise Exception(f"D1 API 錯誤: {response.status} - {error_text}")
                
                result = await response.json()
                print(f"🔍 D1 返回: {result}")
                
                if not result.get("success", False):
                    errors = result.get('errors', [])
                    print(f"❌ D1 查詢失敗: {errors}")
                    raise Exception(f"D1 查詢失敗: {errors}")
                
                return result.get("result", [])
    
    async def init_db(self):
        """初始化數據庫"""
        if not self.use_d1:
            # 使用本地 SQLite
            async with aiosqlite.connect(self.db_path) as db:
                # 創建標籤表
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        category TEXT NOT NULL,
                        emoji TEXT DEFAULT '🏷️',
                        description TEXT,
                        image_url TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        color INTEGER DEFAULT 5814783
                    )
                ''')

                # 創建消息標籤關聯表
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS message_tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        guild_id TEXT NOT NULL,
                        tag_id INTEGER NOT NULL,
                        tagged_by TEXT NOT NULL,
                        tagged_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        message_content TEXT,
                        author_id TEXT,
                        created_at TEXT,
                        FOREIGN KEY (tag_id) REFERENCES tags(id),
                        UNIQUE(message_id, tag_id)
                    )
                ''')

                # 創建搜索索引
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_message_tags_message 
                    ON message_tags(message_id)
                ''')
                
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_message_tags_tag 
                    ON message_tags(tag_id)
                ''')
                
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_message_tags_guild 
                    ON message_tags(guild_id)
                ''')
                
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_message_tags_content 
                    ON message_tags(message_content)
                ''')
                
                await db.commit()
        else:
            # 使用 Cloudflare D1 - 檢查表是否存在
            print("🌐 使用 Cloudflare D1 數據庫")
    
    async def create_tag(self, name: str, category: str, emoji: str = '🏷️',
                        description: str = "", image_url: str = "", color: int = 5814783) -> int:
        """創建新標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                try:
                    cursor = await db.execute(
                        'INSERT INTO tags (name, category, emoji, description, image_url, color) '
                        'VALUES (?, ?, ?, ?, ?, ?)',
                        (name, category, emoji, description, image_url, color)
                    )
                    await db.commit()
                    return cursor.lastrowid
                except aiosqlite.IntegrityError:
                    return None
        else:
            try:
                print(f"🔍 準備創建標籤: name={name}, category={category}, emoji={emoji}")
                sql = "INSERT INTO tags (name, category, emoji, description, image_url, color) VALUES (?, ?, ?, ?, ?, ?)"
                result = await self._execute_d1(sql, (name, category, emoji, description, image_url, color))
                print(f"🔍 INSERT 返回: {result}")
                
                # D1 插入成功，返回新標籤的 ID
                # 由於 D1 的 INSERT 不返回行信息，我們需要查詢剛創建的標籤
                # 使用多個條件來確保查詢到正確的標籤
                result2 = await self._execute_d1(
                    'SELECT id FROM tags WHERE name = ? AND emoji = ? AND category = ? ORDER BY id DESC LIMIT 1', 
                    (name, emoji, category)
                )
                print(f"🔍 查詢返回: {result2}")
                
                if result2 and len(result2) > 0 and "results" in result2[0]:
                    rows = result2[0]["results"]
                    if rows:
                        tag_id = rows[0].get("id")
                        print(f"✅ 成功創建標籤，ID: {tag_id}")
                        return tag_id
                
                print(f"❌ 查詢失敗或沒有找到結果")
                return None
            except Exception as e:
                print(f"❌ 創建標籤失敗: {e}")
                import traceback
                traceback.print_exc()
                return None
    
    async def get_all_tags(self) -> List[Tag]:
        """獲取所有標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT * FROM tags ORDER BY category, name') as cursor:
                    rows = await cursor.fetchall()
                    return [Tag(*row) for row in rows]
        else:
            try:
                sql = "SELECT * FROM tags ORDER BY category, name"
                result = await self._execute_d1(sql)
                print(f"🔍 get_all_tags D1 返回: {result}")
                tags = []
                
                if result and len(result) > 0:
                    print(f"🔍 result[0]: {result[0]}")
                    if "results" in result[0]:
                        print(f"🔍 results 數量: {len(result[0]['results'])}")
                        for r in result[0]["results"]:
                            print(f"🔍 處理標籤: {r}")
                            # 處理 created_at 欄位
                            created_at = r.get("created_at")
                            if not created_at or created_at == "":
                                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            tag = Tag(
                                r.get("id"),
                                r.get("name"),
                                r.get("category"),
                                r.get("emoji"),
                                r.get("description", ""),
                                r.get("image_url", ""),
                                created_at,
                                r.get("color", 5814783)
                            )
                            tags.append(tag)
                            print(f"🔍 創建的 Tag: {tag}")
                
                print(f"🔍 總共找到 {len(tags)} 個標籤")
                return tags
            except Exception as e:
                print(f"❌ 獲取標籤失敗: {e}")
                import traceback
                traceback.print_exc()
                return []
    
    async def get_tag_by_name(self, name: str) -> Optional[Tag]:
        """根據名稱獲取標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT * FROM tags WHERE name = ?', (name,)) as cursor:
                    row = await cursor.fetchone()
                    return Tag(*row) if row else None
        else:
            try:
                sql = "SELECT * FROM tags WHERE name = ?"
                result = await self._execute_d1(sql, (name,))
                if result and result[0].get("results"):
                    r = result[0]["results"][0]
                    # 處理 created_at 欄位
                    created_at = r.get("created_at")
                    if not created_at or created_at == "":
                        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    return Tag(
                        r["id"], r["name"], r["category"], r["emoji"],
                        r.get("description", ""), r.get("image_url", ""),
                        created_at, r["color"]
                    )
                return None
            except Exception as e:
                print(f"❌ 獲取標籤失敗: {e}")
                return None
    
    async def get_tags_by_category(self, category: str) -> List[Tag]:
        """根據分類獲取標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT * FROM tags WHERE category = ? ORDER BY name',
                    (category,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [Tag(*row) for row in rows]
        else:
            try:
                sql = "SELECT * FROM tags WHERE category = ? ORDER BY name"
                result = await self._execute_d1(sql, (category,))
                tags = []
                for row in result:
                    if "results" in row:
                        for r in row["results"]:
                            # 處理 created_at 欄位
                            created_at = r.get("created_at")
                            if not created_at or created_at == "":
                                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            tags.append(Tag(
                                r["id"], r["name"], r["category"], r["emoji"],
                                r.get("description", ""), r.get("image_url", ""),
                                created_at, r["color"]
                            ))
                return tags
            except Exception as e:
                print(f"❌ 獲取標籤失敗: {e}")
                return []
    
    async def tag_message(self, message_id: str, channel_id: str, guild_id: str,
                         tag_id: int, tagged_by: str, message_content: str,
                         author_id: str, created_at: str) -> bool:
        """為消息添加標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                try:
                    await db.execute(
                        'INSERT INTO message_tags '
                        '(message_id, channel_id, guild_id, tag_id, tagged_by, message_content, author_id, created_at) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (message_id, channel_id, guild_id, tag_id, tagged_by, 
                         message_content, author_id, created_at)
                    )
                    await db.commit()
                    return True
                except aiosqlite.IntegrityError:
                    return False
        else:
            try:
                sql = "INSERT INTO message_tags (message_id, channel_id, guild_id, tag_id, tagged_by, message_content, author_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                await self._execute_d1(sql, (message_id, channel_id, guild_id, tag_id, tagged_by, message_content, author_id, created_at))
                return True
            except Exception as e:
                print(f"❌ 標籤消息失敗: {e}")
                return False
    
    async def get_message_tags(self, message_id: str) -> List[MessageTag]:
        """獲取消息的所有標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT mt.* FROM message_tags mt '
                    'JOIN tags t ON mt.tag_id = t.id '
                    'WHERE mt.message_id = ?',
                    (message_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [MessageTag(*row[:-1]) for row in rows]
        else:
            try:
                sql = 'SELECT mt.* FROM message_tags mt JOIN tags t ON mt.tag_id = t.id WHERE mt.message_id = ?'
                result = await self._execute_d1(sql, (message_id,))
                message_tags = []
                for row in result:
                    if "results" in row:
                        for r in row["results"]:
                            message_tags.append(MessageTag(
                                r["id"], r["message_id"], r["channel_id"], r["guild_id"],
                                r["tag_id"], r["tagged_by"], r["tagged_at"],
                                r.get("message_content", ""), r.get("author_id", ""),
                                r.get("created_at", "")
                            ))
                return message_tags
            except Exception as e:
                print(f"❌ 獲取消息標籤失敗: {e}")
                return []
    
    async def get_tag_statistics(self, guild_id: str = None) -> List[Dict]:
        """獲取標籤統計信息"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                if guild_id:
                    async with db.execute(
                        'SELECT t.*, COUNT(mt.id) as usage_count '
                        'FROM tags t '
                        'LEFT JOIN message_tags mt ON t.id = mt.tag_id AND mt.guild_id = ? '
                        'GROUP BY t.id '
                        'ORDER BY usage_count DESC',
                        (guild_id,)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        return [{'tag': Tag(*row[:-1]), 'usage_count': row[-1]} for row in rows]
                else:
                    async with db.execute(
                        'SELECT t.*, COUNT(mt.id) as usage_count '
                        'FROM tags t '
                        'LEFT JOIN message_tags mt ON t.id = mt.tag_id '
                        'GROUP BY t.id '
                        'ORDER BY usage_count DESC'
                    ) as cursor:
                        rows = await cursor.fetchall()
                        return [{'tag': Tag(*row[:-1]), 'usage_count': row[-1]} for row in rows]
        else:
            # Cloudflare D1 版本
            try:
                if guild_id:
                    sql = '''SELECT t.*, COUNT(mt.id) as usage_count 
                            FROM tags t 
                            LEFT JOIN message_tags mt ON t.id = mt.tag_id AND mt.guild_id = ? 
                            GROUP BY t.id 
                            ORDER BY usage_count DESC'''
                    result = await self._execute_d1(sql, (guild_id,))
                else:
                    sql = '''SELECT t.*, COUNT(mt.id) as usage_count 
                            FROM tags t 
                            LEFT JOIN message_tags mt ON t.id = mt.tag_id 
                            GROUP BY t.id 
                            ORDER BY usage_count DESC'''
                    result = await self._execute_d1(sql)
                
                stats = []
                for row in result:
                    if "results" in row:
                        for r in row["results"]:
                            # 處理 created_at 欄位
                            created_at = r.get("created_at")
                            if not created_at or created_at == "":
                                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            stats.append({
                                'tag': Tag(
                                    r["id"], r["name"], r["category"], r["emoji"],
                                    r.get("description", ""), r.get("image_url", ""),
                                    created_at, r["color"]
                                ),
                                'usage_count': r.get("usage_count", 0)
                            })
                return stats
            except Exception as e:
                print(f"❌ 獲取統計信息失敗: {e}")
                return []
                return []
    
    async def get_guild_statistics(self, guild_id: str) -> Dict:
        """獲取服務器統計信息"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                # 總標籤數
                async with db.execute(
                    'SELECT COUNT(DISTINCT tag_id) FROM message_tags WHERE guild_id = ?',
                    (guild_id,)
                ) as cursor:
                    total_tags = (await cursor.fetchone())[0]
                
                # 總消息數
                async with db.execute(
                    'SELECT COUNT(DISTINCT message_id) FROM message_tags WHERE guild_id = ?',
                    (guild_id,)
                ) as cursor:
                    total_messages = (await cursor.fetchone())[0]
                
                return {
                    'total_tags': total_tags,
                    'total_messages': total_messages,
                    'top_users': [],
                    'category_stats': []
                }
        else:
            try:
                # 總標籤數（從 tags 表統計）
                sql = 'SELECT COUNT(*) as count FROM tags'
                result = await self._execute_d1(sql)
                total_tags = result[0]["results"][0]["count"] if result and result[0].get("results") else 0
                
                # 總消息數
                sql = 'SELECT COUNT(DISTINCT message_id) as count FROM message_tags WHERE guild_id = ?'
                result = await self._execute_d1(sql, (guild_id,))
                total_messages = result[0]["results"][0]["count"] if result and result[0].get("results") else 0
                
                return {
                    'total_tags': total_tags,
                    'total_messages': total_messages,
                    'top_users': [],
                    'category_stats': []
                }
            except Exception as e:
                print(f"❌ 獲取服務器統計失敗: {e}")
                return {'total_tags': 0, 'total_messages': 0, 'top_users': [], 'category_stats': []}
    
    async def delete_tag(self, tag_id: int) -> bool:
        """刪除標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('DELETE FROM message_tags WHERE tag_id = ?', (tag_id,))
                cursor = await db.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
                await db.commit()
                return cursor.rowcount > 0
        else:
            try:
                # 先刪除所有使用該標籤的消息標籤
                await self._execute_d1('DELETE FROM message_tags WHERE tag_id = ?', (tag_id,))
                # 再刪除標籤
                await self._execute_d1('DELETE FROM tags WHERE id = ?', (tag_id,))
                return True
            except Exception as e:
                print(f"❌ 刪除標籤失敗: {e}")
                return False
    
    async def delete_all_tags(self):
        """刪除所有標籤"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('DELETE FROM message_tags')
                await db.execute('DELETE FROM tags')
                await db.commit()
                return True
        else:
            try:
                # 先刪除所有消息標籤
                await self._execute_d1('DELETE FROM message_tags')
                # 再刪除所有標籤
                await self._execute_d1('DELETE FROM tags')
                return True
            except Exception as e:
                print(f"❌ 刪除所有標籤失敗: {e}")
                return False