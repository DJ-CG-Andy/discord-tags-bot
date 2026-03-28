"""
每日簽到系統管理器
支持本地 SQLite 和 Cloudflare D1
"""

import aiosqlite
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import os
import aiohttp

class CheckinManager:
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
    
    async def _execute_d1(self, sql: str, params: list = None) -> list:
        """執行 D1 查詢"""
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
                
                if result.get("success"):
                    return result.get("result", [])
                else:
                    raise Exception(f"D1 查詢失敗: {result}")
    
    async def init_tables(self):
        """初始化簽到相關表"""
        if self.use_d1:
            # D1 模式：執行 SQL 創建表
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS checkin_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL UNIQUE,
                    channel_id TEXT NOT NULL,
                    checkin_time TEXT DEFAULT "00:00",
                    gif_url TEXT DEFAULT "",
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS checkin_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    checkin_date TEXT NOT NULL,
                    streak_days INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, guild_id, checkin_date)
                )
            ''')
            
            await self._execute_d1('''
                CREATE TABLE IF NOT EXISTS gif_change_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    checkin_time TEXT DEFAULT "00:00",
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT NOT NULL
                )
            ''')
        else:
            # SQLite 模式
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS checkin_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id TEXT NOT NULL UNIQUE,
                        channel_id TEXT NOT NULL,
                        checkin_time TEXT DEFAULT "00:00",
                        gif_url TEXT DEFAULT "",
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS checkin_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        guild_id TEXT NOT NULL,
                        checkin_date TEXT NOT NULL,
                        streak_days INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, guild_id, checkin_date)
                    )
                ''')
                
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS gif_change_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        guild_id TEXT NOT NULL,
                        checkin_time TEXT DEFAULT "00:00",
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        expires_at TEXT NOT NULL
                    )
                ''')
                
                await db.commit()
    
    async def set_gif_change_request(self, user_id: str, channel_id: str, guild_id: str, checkin_time: str = "00:00", timeout_seconds: int = 120) -> bool:
        """設置 GIF 更換請求（使用資料庫存儲，避免多實例問題）"""
        from datetime import datetime, timedelta
        
        # 計算過期時間
        expires_at = (datetime.now() + timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        
        if self.use_d1:
            # 先刪除舊的請求
            await self._execute_d1('''
                DELETE FROM gif_change_requests WHERE user_id = ? AND channel_id = ?
            ''', [user_id, channel_id])
            
            # 插入新請求
            await self._execute_d1('''
                INSERT INTO gif_change_requests (user_id, channel_id, guild_id, checkin_time, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', [user_id, channel_id, guild_id, checkin_time, expires_at])
        else:
            async with aiosqlite.connect(self.db_path) as db:
                # 先刪除舊的請求
                await db.execute('''
                    DELETE FROM gif_change_requests WHERE user_id = ? AND channel_id = ?
                ''', (user_id, channel_id))
                
                # 插入新請求
                await db.execute('''
                    INSERT INTO gif_change_requests (user_id, channel_id, guild_id, checkin_time, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, channel_id, guild_id, checkin_time, expires_at))
                
                await db.commit()
        
        return True
    
    async def get_gif_change_request(self, user_id: str, channel_id: str) -> Optional[Dict]:
        """獲取並刪除 GIF 更換請求"""
        from datetime import datetime
        
        if self.use_d1:
            # 查詢請求
            result = await self._execute_d1('''
                SELECT * FROM gif_change_requests 
                WHERE user_id = ? AND channel_id = ? AND expires_at > CURRENT_TIMESTAMP
                ORDER BY id DESC LIMIT 1
            ''', [user_id, channel_id])
            
            if result and result[0].get("results"):
                row = result[0]["results"][0]
                request_data = {
                    "user_id": row.get("user_id"),
                    "channel_id": row.get("channel_id"),
                    "guild_id": row.get("guild_id"),
                    "checkin_time": row.get("checkin_time")
                }
                
                # 刪除請求
                await self._execute_d1('''
                    DELETE FROM gif_change_requests WHERE id = ?
                ''', [row.get("id")])
                
                return request_data
            return None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                # 查詢請求
                async with db.execute('''
                    SELECT * FROM gif_change_requests 
                    WHERE user_id = ? AND channel_id = ? AND expires_at > datetime('now')
                    ORDER BY id DESC LIMIT 1
                ''', (user_id, channel_id)) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        request_data = {
                            "user_id": row[1],
                            "channel_id": row[2],
                            "guild_id": row[3],
                            "checkin_time": row[4]
                        }
                        
                        # 刪除請求
                        await db.execute('''
                            DELETE FROM gif_change_requests WHERE id = ?
                        ''', (row[0],))
                        await db.commit()
                        
                        return request_data
                    return None
    
    async def cleanup_expired_requests(self):
        """清理過期的 GIF 更換請求"""
        if self.use_d1:
            await self._execute_d1('''
                DELETE FROM gif_change_requests WHERE expires_at < CURRENT_TIMESTAMP
            ''')
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    DELETE FROM gif_change_requests WHERE expires_at < datetime('now')
                ''')
                await db.commit()
    
    async def set_config(self, guild_id: str, channel_id: str, 
                        checkin_time: str = "00:00", gif_url: str = "") -> bool:
        """設置簽到配置"""
        if self.use_d1:
            # 先嘗試插入
            result = await self._execute_d1('''
                INSERT INTO checkin_config (guild_id, channel_id, checkin_time, gif_url)
                VALUES (?, ?, ?, ?)
            ''', [guild_id, channel_id, checkin_time, gif_url])
            
            # 如果失敗（因為已存在），則更新
            if not result:
                await self._execute_d1('''
                    UPDATE checkin_config 
                    SET channel_id = ?, checkin_time = ?, gif_url = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = ?
                ''', [channel_id, checkin_time, gif_url, guild_id])
        else:
            async with aiosqlite.connect(self.db_path) as db:
                try:
                    await db.execute('''
                        INSERT INTO checkin_config (guild_id, channel_id, checkin_time, gif_url)
                        VALUES (?, ?, ?, ?)
                    ''', (guild_id, channel_id, checkin_time, gif_url))
                    await db.commit()
                except aiosqlite.IntegrityError:
                    await db.execute('''
                        UPDATE checkin_config 
                        SET channel_id = ?, checkin_time = ?, gif_url = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE guild_id = ?
                    ''', (channel_id, checkin_time, gif_url, guild_id))
                    await db.commit()
        
        return True
    
    async def get_config(self, guild_id: str) -> Optional[Dict]:
        """獲取簽到配置"""
        if self.use_d1:
            result = await self._execute_d1('''
                SELECT * FROM checkin_config WHERE guild_id = ?
            ''', [guild_id])
            
            if result and len(result) > 0 and result[0].get("results"):
                row = result[0]["results"][0]
                # 確保返回的字典有所有必需的字段
                return {
                    "id": row.get("id"),
                    "guild_id": row.get("guild_id") or guild_id,
                    "channel_id": row.get("channel_id"),
                    "checkin_time": row.get("checkin_time") or "00:00",
                    "gif_url": row.get("gif_url") or "",
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at")
                }
            return None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT * FROM checkin_config WHERE guild_id = ?',
                    (guild_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "id": row[0],
                            "guild_id": row[1],
                            "channel_id": row[2],
                            "checkin_time": row[3],
                            "gif_url": row[4],
                            "created_at": row[5],
                            "updated_at": row[6]
                        }
                    return None
    
    async def checkin(self, user_id: str, guild_id: str) -> Tuple[bool, int, int]:
        """
        用戶簽到
        返回: (是否成功, 總簽到次數, 連續簽到天數)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        if self.use_d1:
            # 檢查今天是否已經簽到
            result = await self._execute_d1('''
                SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?
            ''', [user_id, guild_id, today])
            
            if result and result[0].get("results"):
                # 今天已經簽到過
                total_count = await self.get_total_checkins(user_id, guild_id)
                streak = await self.get_streak(user_id, guild_id)
                return (False, total_count, streak)
            
            # 檢查昨天是否簽到
            result = await self._execute_d1('''
                SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?
            ''', [user_id, guild_id, yesterday])
            
            if result and result[0].get("results"):
                # 昨天簽到了，連續天數 +1
                yesterday_record = result[0]["results"][0]
                streak = yesterday_record.get("streak_days", 0) + 1
            else:
                # 昨天沒簽到，連續天數 = 1
                streak = 1
            
            # 創建簽到記錄
            await self._execute_d1('''
                INSERT INTO checkin_records (user_id, guild_id, checkin_date, streak_days)
                VALUES (?, ?, ?, ?)
            ''', [user_id, guild_id, today, streak])
            
            # 獲取總簽到次數
            total_count = await self.get_total_checkins(user_id, guild_id)
            
            return (True, total_count, streak)
        else:
            async with aiosqlite.connect(self.db_path) as db:
                # 檢查今天是否已經簽到
                async with db.execute(
                    'SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?',
                    (user_id, guild_id, today)
                ) as cursor:
                    existing = await cursor.fetchone()
                    if existing:
                        # 今天已經簽到過
                        total_count = await self.get_total_checkins(user_id, guild_id)
                        streak = await self.get_streak(user_id, guild_id)
                        return (False, total_count, streak)
                
                # 檢查昨天是否簽到
                async with db.execute(
                    'SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?',
                    (user_id, guild_id, yesterday)
                ) as cursor:
                    yesterday_record = await cursor.fetchone()
                    
                    # 計算連續簽到天數
                    if yesterday_record:
                        streak = yesterday_record[4] + 1
                    else:
                        streak = 1
                
                # 創建簽到記錄
                await db.execute('''
                    INSERT INTO checkin_records (user_id, guild_id, checkin_date, streak_days)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, guild_id, today, streak))
                await db.commit()
                
                # 獲取總簽到次數
                total_count = await self.get_total_checkins(user_id, guild_id)
                
                return (True, total_count, streak)
    
    async def get_total_checkins(self, user_id: str, guild_id: str) -> int:
        """獲取總簽到次數"""
        if self.use_d1:
            result = await self._execute_d1('''
                SELECT COUNT(*) as count FROM checkin_records WHERE user_id = ? AND guild_id = ?
            ''', [user_id, guild_id])
            
            if result and result[0].get("results"):
                row = result[0]["results"][0]
                return row.get("count", 0)
            return 0
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT COUNT(*) FROM checkin_records WHERE user_id = ? AND guild_id = ?',
                    (user_id, guild_id)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
    
    async def get_streak(self, user_id: str, guild_id: str) -> int:
        """獲取連續簽到天數"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if self.use_d1:
            # 檢查今天是否簽到
            result = await self._execute_d1('''
                SELECT streak_days FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?
            ''', [user_id, guild_id, today])
            
            if result and result[0].get("results"):
                row = result[0]["results"][0]
                return row.get("streak_days", 0)
            
            # 如果今天沒有簽到，檢查最近一次簽到的連續天數
            result = await self._execute_d1('''
                SELECT streak_days FROM checkin_records WHERE user_id = ? AND guild_id = ? ORDER BY checkin_date DESC LIMIT 1
            ''', [user_id, guild_id])
            
            if result and result[0].get("results"):
                row = result[0]["results"][0]
                return row.get("streak_days", 0)
            return 0
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT streak_days FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?',
                    (user_id, guild_id, today)
                ) as cursor:
                    result = await cursor.fetchone()
                    if result:
                        return result[0]
                
                async with db.execute(
                    'SELECT streak_days FROM checkin_records WHERE user_id = ? AND guild_id = ? ORDER BY checkin_date DESC LIMIT 1',
                    (user_id, guild_id)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
    
    async def has_checked_today(self, user_id: str, guild_id: str) -> bool:
        """檢查今天是否已經簽到"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if self.use_d1:
            result = await self._execute_d1('''
                SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?
            ''', [user_id, guild_id, today])
            
            return result and result[0].get("results") is not None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?',
                    (user_id, guild_id, today)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result is not None
    
    async def get_leaderboard(self, guild_id: str, limit: int = 10, by_streak: bool = False) -> List[Dict]:
        """獲取排行榜"""
        if self.use_d1:
            if by_streak:
                result = await self._execute_d1('''
                    SELECT user_id, MAX(streak_days) as max_streak
                    FROM checkin_records
                    WHERE guild_id = ?
                    GROUP BY user_id
                    ORDER BY max_streak DESC, user_id
                    LIMIT ?
                ''', [guild_id, limit])
                
                if result and result[0].get("results"):
                    return [
                        {
                            "user_id": row.get("user_id"),
                            "value": row.get("max_streak", 0),
                            "label": "連續簽到天數"
                        }
                        for row in result[0]["results"]
                    ]
            else:
                result = await self._execute_d1('''
                    SELECT user_id, COUNT(*) as total_checkins
                    FROM checkin_records
                    WHERE guild_id = ?
                    GROUP BY user_id
                    ORDER BY total_checkins DESC, user_id
                    LIMIT ?
                ''', [guild_id, limit])
                
                if result and result[0].get("results"):
                    return [
                        {
                            "user_id": row.get("user_id"),
                            "value": row.get("total_checkins", 0),
                            "label": "總簽到次數"
                        }
                        for row in result[0]["results"]
                    ]
            return []
        else:
            async with aiosqlite.connect(self.db_path) as db:
                if by_streak:
                    async with db.execute('''
                        SELECT user_id, MAX(streak_days) as max_streak
                        FROM checkin_records
                        WHERE guild_id = ?
                        GROUP BY user_id
                        ORDER BY max_streak DESC, user_id
                        LIMIT ?
                    ''', (guild_id, limit)) as cursor:
                        rows = await cursor.fetchall()
                        return [
                            {
                                "user_id": row[0],
                                "value": row[1],
                                "label": "連續簽到天數"
                            }
                            for row in rows
                        ]
                else:
                    async with db.execute('''
                        SELECT user_id, COUNT(*) as total_checkins
                        FROM checkin_records
                        WHERE guild_id = ?
                        GROUP BY user_id
                        ORDER BY total_checkins DESC, user_id
                        LIMIT ?
                    ''', (guild_id, limit)) as cursor:
                        rows = await cursor.fetchall()
                        return [
                            {
                                "user_id": row[0],
                                "value": row[1],
                                "label": "總簽到次數"
                            }
                            for row in rows
                        ]
    
    async def get_user_stats(self, user_id: str, guild_id: str) -> Dict:
        """獲取用戶簽到統計"""
        total = await self.get_total_checkins(user_id, guild_id)
        streak = await self.get_streak(user_id, guild_id)
        checked_today = await self.has_checked_today(user_id, guild_id)
        
        return {
            "total_checkins": total,
            "streak_days": streak,
            "checked_today": checked_today
        }