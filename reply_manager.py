"""
刷版區回覆系統管理器
支持本地 SQLite 和 Cloudflare D1
"""

import aiosqlite
from typing import List, Dict, Optional
import os
import aiohttp

class ReplyManager:
    def __init__(self, db_path: str = "discord_tags.db", use_d1: bool = False):
        self.db_path = db_path
        self.use_d1 = use_d1
        
        # Cloudflare D1 配置
        if use_d1:
            self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
            self.database_id = os.getenv("CLOUDFLARE_DATABASE_ID")
            self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
            
            if not all([self.account_id, self.database_id, self.api_token]):
                raise ValueError("使用 D1 模式時必須設置 CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_DATABASE_ID 和 CLOUDFLARE_API_TOKEN")
    
    async def _execute_d1(self, sql: str, params: list = None):
        """執行 D1 查詢，返回完整結果對象"""
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
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
    
    async def init_tables(self):
        """初始化回覆相關表"""
        if self.use_d1:
            # D1 模式：執行 SQL 創建表
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS reply_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL UNIQUE,
                    channel_id TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS reply_triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_id TEXT NOT NULL,
                    trigger_url TEXT DEFAULT "",
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, user_id, trigger_type, trigger_id)
                )
            ''')
            
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS reply_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    trigger_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    used_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS reply_add_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            ''')
            
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS reply_delete_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            ''')
        else:
            # SQLite 模式
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS reply_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL UNIQUE,
                        channel_id TEXT NOT NULL,
                        enabled INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS reply_triggers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        trigger_type TEXT NOT NULL,
                        trigger_id TEXT NOT NULL,
                        trigger_url TEXT DEFAULT "",
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(guild_id, user_id, trigger_type, trigger_id)
                    )
                ''')
                
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS reply_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL,
                        trigger_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        used_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS reply_add_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        guild_id TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                ''')
                
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS reply_delete_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        guild_id TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                ''')
                
                await db.commit()
    
    async def set_config(self, guild_id: str, channel_id: str, enabled: bool = True) -> bool:
        """設置回覆配置"""
        try:
            if self.use_d1:
                # 檢查是否已存在配置
                result = await self._execute_d1(
                    'SELECT * FROM reply_config WHERE guild_id = ?',
                    [guild_id]
                )
                
                if result and result.get("success") and result.get("result") and len(result["result"]) > 0:
                    # 更新配置
                    await self._execute_d1(
                        'UPDATE reply_config SET channel_id = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?',
                        [channel_id, 1 if enabled else 0, guild_id]
                    )
                else:
                    # 插入新配置
                    await self._execute_d1(
                        'INSERT INTO reply_config (guild_id, channel_id, enabled) VALUES (?, ?, ?)',
                        [guild_id, channel_id, 1 if enabled else 0]
                    )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        'SELECT * FROM reply_config WHERE guild_id = ?',
                        (guild_id,)
                    )
                    config = await cursor.fetchone()
                    
                    if config:
                        await db.execute(
                            'UPDATE reply_config SET channel_id = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?',
                            (channel_id, 1 if enabled else 0, guild_id)
                        )
                    else:
                        await db.execute(
                            'INSERT INTO reply_config (guild_id, channel_id, enabled) VALUES (?, ?, ?)',
                            (guild_id, channel_id, 1 if enabled else 0)
                        )
                    
                    await db.commit()
            
            return True
        except Exception as e:
            print(f"❌ 設置回覆配置失敗: {e}")
            return False
    
    async def get_config(self, guild_id: str) -> Optional[Dict]:
        """獲取回覆配置"""
        try:
            if self.use_d1:
                result = await self._execute_d1(
                    'SELECT * FROM reply_config WHERE guild_id = ?',
                    [guild_id]
                )
                
                if result and result.get("success") and result.get("result") and len(result["result"]) > 0:
                    row_result = result["result"][0]
                    if "results" in row_result and len(row_result["results"]) > 0:
                        row = row_result["results"][0]
                        return {
                            'id': row.get("id"),
                            'guild_id': row.get("guild_id"),
                            'channel_id': row.get("channel_id"),
                            'enabled': row.get("enabled") == 1,
                            'created_at': row.get("created_at"),
                            'updated_at': row.get("updated_at")
                        }
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute(
                        'SELECT * FROM reply_config WHERE guild_id = ?',
                        (guild_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            return {
                                'id': row[0],
                                'guild_id': row[1],
                                'channel_id': row[2],
                                'enabled': row[3] == 1,
                                'created_at': row[4],
                                'updated_at': row[5]
                            }
            return None
        except Exception as e:
            print(f"❌ 獲取回覆配置失敗: {e}")
            return None
    
    async def add_trigger(self, guild_id: str, user_id: str, trigger_type: str, trigger_id: str, trigger_url: str = "") -> bool:
        """添加回覆觸發器"""
        try:
            if self.use_d1:
                await self._execute_d1(
                    'INSERT OR REPLACE INTO reply_triggers (guild_id, user_id, trigger_type, trigger_id, trigger_url) VALUES (?, ?, ?, ?, ?)',
                    [guild_id, user_id, trigger_type, trigger_id, trigger_url]
                )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        'INSERT OR REPLACE INTO reply_triggers (guild_id, user_id, trigger_type, trigger_id, trigger_url) VALUES (?, ?, ?, ?, ?)',
                        (guild_id, user_id, trigger_type, trigger_id, trigger_url)
                    )
                    await db.commit()
            return True
        except Exception as e:
            print(f"❌ 添加回覆觸發器失敗: {e}")
            return False
    
    async def get_triggers(self, guild_id: str) -> List[Dict]:
        """獲取所有回覆觸發器"""
        try:
            triggers = []
            if self.use_d1:
                result = await self._execute_d1(
                    'SELECT * FROM reply_triggers WHERE guild_id = ?',
                    [guild_id]
                )
                
                if result and result.get("success") and result.get("result"):
                    for row_result in result["result"]:
                        if "results" in row_result:
                            for row in row_result["results"]:
                                triggers.append({
                                    'id': row.get("id"),
                                    'guild_id': row.get("guild_id"),
                                    'user_id': row.get("user_id"),
                                    'trigger_type': row.get("trigger_type"),
                                    'trigger_id': row.get("trigger_id"),
                                    'trigger_url': row.get("trigger_url"),
                                    'created_at': row.get("created_at")
                                })
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute(
                        'SELECT * FROM reply_triggers WHERE guild_id = ?',
                        (guild_id,)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        for row in rows:
                            triggers.append({
                                'id': row[0],
                                'guild_id': row[1],
                                'user_id': row[2],
                                'trigger_type': row[3],
                                'trigger_id': row[4],
                                'trigger_url': row[5],
                                'created_at': row[6]
                            })
            return triggers
        except Exception as e:
            print(f"❌ 獲取回覆觸發器失敗: {e}")
            return []
    
    async def delete_trigger(self, guild_id: str, trigger_id: str) -> bool:
        """刪除回覆觸發器"""
        try:
            if self.use_d1:
                await self._execute_d1(
                    'DELETE FROM reply_triggers WHERE guild_id = ? AND trigger_id = ?',
                    [guild_id, trigger_id]
                )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        'DELETE FROM reply_triggers WHERE guild_id = ? AND trigger_id = ?',
                        (guild_id, trigger_id)
                    )
                    await db.commit()
            return True
        except Exception as e:
            print(f"❌ 刪除回覆觸發器失敗: {e}")
            return False
    
    async def record_usage(self, guild_id: str, trigger_id: str, user_id: str) -> bool:
        """記錄回覆使用次數"""
        try:
            if self.use_d1:
                await self._execute_d1(
                    'INSERT INTO reply_usage (guild_id, trigger_id, user_id) VALUES (?, ?, ?)',
                    [guild_id, trigger_id, user_id]
                )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        'INSERT INTO reply_usage (guild_id, trigger_id, user_id) VALUES (?, ?, ?)',
                        (guild_id, trigger_id, user_id)
                    )
                    await db.commit()
            return True
        except Exception as e:
            print(f"❌ 記錄回覆使用失敗: {e}")
            return False
    
    async def get_usage_stats(self, guild_id: str) -> List[Dict]:
        """獲取回覆使用統計"""
        try:
            stats = []
            if self.use_d1:
                result = await self._execute_d1(
                    '''SELECT rt.trigger_id, rt.trigger_type, rt.trigger_url, COUNT(ru.id) as usage_count
                       FROM reply_triggers rt
                       LEFT JOIN reply_usage ru ON rt.trigger_id = ru.trigger_id
                       WHERE rt.guild_id = ?
                       GROUP BY rt.trigger_id
                       ORDER BY usage_count DESC''',
                    [guild_id]
                )
                
                if result and result.get("success") and result.get("result"):
                    for row_result in result["result"]:
                        if "results" in row_result:
                            for row in row_result["results"]:
                                stats.append({
                                    'trigger_id': row.get("trigger_id"),
                                    'trigger_type': row.get("trigger_type"),
                                    'trigger_url': row.get("trigger_url"),
                                    'usage_count': row.get("usage_count", 0)
                                })
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute(
                        '''SELECT rt.trigger_id, rt.trigger_type, rt.trigger_url, COUNT(ru.id) as usage_count
                           FROM reply_triggers rt
                           LEFT JOIN reply_usage ru ON rt.trigger_id = ru.trigger_id
                           WHERE rt.guild_id = ?
                           GROUP BY rt.trigger_id
                           ORDER BY usage_count DESC''',
                        (guild_id,)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        for row in rows:
                            stats.append({
                                'trigger_id': row[0],
                                'trigger_type': row[1],
                                'trigger_url': row[2],
                                'usage_count': row[3]
                            })
            return stats
        except Exception as e:
            print(f"❌ 獲取回覆使用統計失敗: {e}")
            return []
    
    async def set_add_request(self, user_id: str, channel_id: str, guild_id: str, timeout_seconds: int = 120) -> bool:
        """設置新增回覆請求"""
        try:
            from datetime import datetime, timedelta, timezone
            UTC8 = timezone(timedelta(hours=8))
            expires_at = (datetime.now(UTC8) + timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%d %H:%M:%S")
            
            if self.use_d1:
                # 先刪除舊請求
                await self._execute_d1(
                    'DELETE FROM reply_add_requests WHERE user_id = ? AND channel_id = ?',
                    [user_id, channel_id]
                )
                # 插入新請求
                await self._execute_d1(
                    'INSERT INTO reply_add_requests (user_id, channel_id, guild_id, expires_at) VALUES (?, ?, ?, ?)',
                    [user_id, channel_id, guild_id, expires_at]
                )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        'DELETE FROM reply_add_requests WHERE user_id = ? AND channel_id = ?',
                        (user_id, channel_id)
                    )
                    await db.execute(
                        'INSERT INTO reply_add_requests (user_id, channel_id, guild_id, expires_at) VALUES (?, ?, ?, ?)',
                        (user_id, channel_id, guild_id, expires_at)
                    )
                    await db.commit()
            return True
        except Exception as e:
            print(f"❌ 設置新增回覆請求失敗: {e}")
            return False
    
    async def get_add_request(self, user_id: str, channel_id: str) -> Optional[Dict]:
        """獲取並刪除新增回覆請求"""
        try:
            if self.use_d1:
                result = await self._execute_d1(
                    'SELECT * FROM reply_add_requests WHERE user_id = ? AND channel_id = ?',
                    [user_id, channel_id]
                )
                
                if result and result.get("success") and result.get("result") and len(result["result"]) > 0:
                    row_result = result["result"][0]
                    if "results" in row_result and len(row_result["results"]) > 0:
                        row = row_result["results"][0]
                        request_data = {
                            'id': row.get("id"),
                            'user_id': row.get("user_id"),
                            'channel_id': row.get("channel_id"),
                            'guild_id': row.get("guild_id"),
                            'expires_at': row.get("expires_at")
                        }
                        # 刪除請求
                        await self._execute_d1(
                            'DELETE FROM reply_add_requests WHERE id = ?',
                            [request_data['id']]
                        )
                        return request_data
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute(
                        'SELECT * FROM reply_add_requests WHERE user_id = ? AND channel_id = ?',
                        (user_id, channel_id)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            request_data = {
                                'id': row[0],
                                'user_id': row[1],
                                'channel_id': row[2],
                                'guild_id': row[3],
                                'expires_at': row[4]
                            }
                            # 刪除請求
                            await db.execute(
                                'DELETE FROM reply_add_requests WHERE id = ?',
                                (request_data['id'],)
                            )
                            await db.commit()
                            return request_data
            return None
        except Exception as e:
            print(f"❌ 獲取新增回覆請求失敗: {e}")
            return None
    
    async def set_delete_request(self, user_id: str, channel_id: str, guild_id: str, timeout_seconds: int = 120) -> bool:
        """設置刪除回覆請求"""
        try:
            from datetime import datetime, timedelta, timezone
            UTC8 = timezone(timedelta(hours=8))
            expires_at = (datetime.now(UTC8) + timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%d %H:%M:%S")
            
            if self.use_d1:
                # 先刪除舊請求
                await self._execute_d1(
                    'DELETE FROM reply_delete_requests WHERE user_id = ? AND channel_id = ?',
                    [user_id, channel_id]
                )
                # 插入新請求
                await self._execute_d1(
                    'INSERT INTO reply_delete_requests (user_id, channel_id, guild_id, expires_at) VALUES (?, ?, ?, ?)',
                    [user_id, channel_id, guild_id, expires_at]
                )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        'DELETE FROM reply_delete_requests WHERE user_id = ? AND channel_id = ?',
                        (user_id, channel_id)
                    )
                    await db.execute(
                        'INSERT INTO reply_delete_requests (user_id, channel_id, guild_id, expires_at) VALUES (?, ?, ?, ?)',
                        (user_id, channel_id, guild_id, expires_at)
                    )
                    await db.commit()
            return True
        except Exception as e:
            print(f"❌ 設置刪除回覆請求失敗: {e}")
            return False
    
    async def get_delete_request(self, user_id: str, channel_id: str) -> Optional[Dict]:
        """獲取並刪除刪除回覆請求"""
        try:
            if self.use_d1:
                result = await self._execute_d1(
                    'SELECT * FROM reply_delete_requests WHERE user_id = ? AND channel_id = ?',
                    [user_id, channel_id]
                )
                
                if result and result.get("success") and result.get("result") and len(result["result"]) > 0:
                    row_result = result["result"][0]
                    if "results" in row_result and len(row_result["results"]) > 0:
                        row = row_result["results"][0]
                        request_data = {
                            'id': row.get("id"),
                            'user_id': row.get("user_id"),
                            'channel_id': row.get("channel_id"),
                            'guild_id': row.get("guild_id"),
                            'expires_at': row.get("expires_at")
                        }
                        # 刪除請求
                        await self._execute_d1(
                            'DELETE FROM reply_delete_requests WHERE id = ?',
                            [request_data['id']]
                        )
                        return request_data
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute(
                        'SELECT * FROM reply_delete_requests WHERE user_id = ? AND channel_id = ?',
                        (user_id, channel_id)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            request_data = {
                                'id': row[0],
                                'user_id': row[1],
                                'channel_id': row[2],
                                'guild_id': row[3],
                                'expires_at': row[4]
                            }
                            # 刪除請求
                            await db.execute(
                                'DELETE FROM reply_delete_requests WHERE id = ?',
                                (request_data['id'],)
                            )
                            await db.commit()
                            return request_data
            return None
        except Exception as e:
            print(f"❌ 獲取刪除回覆請求失敗: {e}")
            return None
    
    async def clean_expired_requests(self):
        """清理過期的請求"""
        try:
            if self.use_d1:
                from datetime import datetime, timedelta, timezone
                UTC8 = timezone(timedelta(hours=8))
                current_time = datetime.now(UTC8).strftime("%Y-%m-%d %H:%M:%S")
                
                await self._execute_d1(
                    'DELETE FROM reply_add_requests WHERE expires_at < ?',
                    [current_time]
                )
                await self._execute_d1(
                    'DELETE FROM reply_delete_requests WHERE expires_at < ?',
                    [current_time]
                )
            else:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        'DELETE FROM reply_add_requests WHERE expires_at < CURRENT_TIMESTAMP'
                    )
                    await db.execute(
                        'DELETE FROM reply_delete_requests WHERE expires_at < CURRENT_TIMESTAMP'
                    )
                    await db.commit()
        except Exception as e:
            print(f"❌ 清理過期請求失敗: {e}")