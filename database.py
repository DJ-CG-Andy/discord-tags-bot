import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
import os

@dataclass
class Tag:
    id: int
    name: str
    category: str
    emoji: str
    description: str
    created_at: str
    color: int

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
    def __init__(self, db_path: str = "discord_tags.db"):
        self.db_path = db_path
        # 確保數據庫目錄存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"✅ 已創建數據庫目錄: {db_dir}")
    
    async def init_db(self):
        """初始化數據庫"""
        async with aiosqlite.connect(self.db_path) as db:
            # 創建標籤表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    emoji TEXT DEFAULT '🏷️',
                    description TEXT,
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
    
    async def create_tag(self, name: str, category: str, emoji: str = '🏷️',
                        description: str = "", color: int = 5814783) -> int:
        """創建新標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    'INSERT INTO tags (name, category, emoji, description, color) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (name, category, emoji, description, color)
                )
                await db.commit()
                return cursor.lastrowid
            except aiosqlite.IntegrityError:
                return None
    
    async def get_all_tags(self) -> List[Tag]:
        """獲取所有標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT * FROM tags ORDER BY category, name') as cursor:
                rows = await cursor.fetchall()
                return [Tag(*row) for row in rows]
    
    async def get_tag_by_name(self, name: str) -> Optional[Tag]:
        """根據名稱獲取標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT * FROM tags WHERE name = ?', (name,)) as cursor:
                row = await cursor.fetchone()
                return Tag(*row) if row else None
    
    async def get_tags_by_category(self, category: str) -> List[Tag]:
        """根據分類獲取標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT * FROM tags WHERE category = ? ORDER BY name',
                (category,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [Tag(*row) for row in rows]
    
    async def tag_message(self, message_id: str, channel_id: str, guild_id: str,
                         tag_id: int, tagged_by: str, message_content: str,
                         author_id: str, created_at: str) -> bool:
        """為消息添加標籤"""
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
    
    async def untag_message(self, message_id: str, tag_id: int) -> bool:
        """移除消息標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'DELETE FROM message_tags WHERE message_id = ? AND tag_id = ?',
                (message_id, tag_id)
            )
            await db.commit()
            return cursor.rowcount > 0
    
    async def get_message_tags(self, message_id: str) -> List[MessageTag]:
        """獲取消息的所有標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT mt.*, t.name FROM message_tags mt '
                'JOIN tags t ON mt.tag_id = t.id '
                'WHERE mt.message_id = ?',
                (message_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [MessageTag(*row[:-1]) for row in rows]
    
    async def search_by_tag(self, tag_name: str, guild_id: str = None, 
                           limit: int = 50) -> List[MessageTag]:
        """根據標籤搜索消息"""
        async with aiosqlite.connect(self.db_path) as db:
            if guild_id:
                async with db.execute(
                    'SELECT mt.* FROM message_tags mt '
                    'JOIN tags t ON mt.tag_id = t.id '
                    'WHERE t.name = ? AND mt.guild_id = ? '
                    'ORDER BY mt.tagged_at DESC LIMIT ?',
                    (tag_name, guild_id, limit)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [MessageTag(*row) for row in rows]
            else:
                async with db.execute(
                    'SELECT mt.* FROM message_tags mt '
                    'JOIN tags t ON mt.tag_id = t.id '
                    'WHERE t.name = ? '
                    'ORDER BY mt.tagged_at DESC LIMIT ?',
                    (tag_name, limit)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [MessageTag(*row) for row in rows]
    
    async def search_by_content(self, query: str, guild_id: str = None,
                               limit: int = 50) -> List[MessageTag]:
        """根據內容搜索消息"""
        async with aiosqlite.connect(self.db_path) as db:
            if guild_id:
                async with db.execute(
                    'SELECT mt.* FROM message_tags mt '
                    'WHERE mt.guild_id = ? AND mt.message_content LIKE ? '
                    'ORDER BY mt.tagged_at DESC LIMIT ?',
                    (guild_id, f'%{query}%', limit)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [MessageTag(*row) for row in rows]
            else:
                async with db.execute(
                    'SELECT mt.* FROM message_tags mt '
                    'WHERE mt.message_content LIKE ? '
                    'ORDER BY mt.tagged_at DESC LIMIT ?',
                    (f'%{query}%', limit)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [MessageTag(*row) for row in rows]
    
    async def get_tag_statistics(self, guild_id: str = None) -> List[Dict]:
        """獲取標籤統計信息"""
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
    
    async def get_guild_statistics(self, guild_id: str) -> Dict:
        """獲取服務器統計信息"""
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
            
            # 最活躍用戶
            async with db.execute(
                'SELECT tagged_by, COUNT(*) as count FROM message_tags '
                'WHERE guild_id = ? GROUP BY tagged_by ORDER BY count DESC LIMIT 5',
                (guild_id,)
            ) as cursor:
                top_users = await cursor.fetchall()
            
            # 按分類統計
            async with db.execute(
                'SELECT t.category, COUNT(mt.id) as count FROM tags t '
                'LEFT JOIN message_tags mt ON t.id = mt.tag_id AND mt.guild_id = ? '
                'GROUP BY t.category',
                (guild_id,)
            ) as cursor:
                category_stats = await cursor.fetchall()
            
            return {
                'total_tags': total_tags,
                'total_messages': total_messages,
                'top_users': top_users,
                'category_stats': category_stats
            }
    
    async def delete_tag(self, tag_id: int) -> bool:
        """刪除標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            # 先刪除所有使用該標籤的消息標籤
            await db.execute('DELETE FROM message_tags WHERE tag_id = ?', (tag_id,))
            # 再刪除標籤
            cursor = await db.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
            await db.commit()
            return cursor.rowcount > 0
    
    async def get_active_users_count(self, guild_id: str = None) -> int:
        """獲取活躍用戶數"""
        async with aiosqlite.connect(self.db_path) as db:
            if guild_id:
                async with db.execute(
                    'SELECT COUNT(DISTINCT tagged_by) FROM message_tags WHERE guild_id = ?',
                    (guild_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
            else:
                async with db.execute(
                    'SELECT COUNT(DISTINCT tagged_by) FROM message_tags'
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
    
    async def get_recent_messages(self, guild_id: str, limit: int = 20) -> List[MessageTag]:
        """獲取最近的標籤消息"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT mt.* FROM message_tags mt '
                'WHERE mt.guild_id = ? '
                'ORDER BY mt.tagged_at DESC LIMIT ?',
                (guild_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [MessageTag(*row) for row in rows]
    
    async def delete_all_tags(self):
        """刪除所有標籤"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM message_tags')
            await db.execute('DELETE FROM tags')
            await db.commit()
            return True