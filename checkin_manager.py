"""
每日簽到系統管理器
"""

import aiosqlite
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json
from dataclasses import dataclass
import os

@dataclass
class CheckinRecord:
    """簽到記錄"""
    id: int
    user_id: str
    guild_id: str
    checkin_date: str  # YYYY-MM-DD
    streak_days: int  # 連續簽到天數
    created_at: str

@dataclass
class CheckinConfig:
    """簽到配置"""
    id: int
    guild_id: str
    channel_id: str  # 簽到頻道
    checkin_time: str  # 簽到時間 (HH:MM)
    gif_url: str  # 簽到 GIF
    created_at: str
    updated_at: str

class CheckinManager:
    def __init__(self, db_path: str = "discord_tags.db"):
        self.db_path = db_path
    
    async def init_tables(self):
        """初始化簽到相關表"""
        async with aiosqlite.connect(self.db_path) as db:
            # 創建簽到配置表
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
            
            # 創建簽到記錄表
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
            
            # 創建索引
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkin_records_user 
                ON checkin_records(user_id)
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkin_records_date 
                ON checkin_records(checkin_date)
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_checkin_records_guild 
                ON checkin_records(guild_id)
            ''')
            
            await db.commit()
    
    async def set_config(self, guild_id: str, channel_id: str, 
                        checkin_time: str = "00:00", gif_url: str = "") -> bool:
        """設置簽到配置"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO checkin_config (guild_id, channel_id, checkin_time, gif_url)
                    VALUES (?, ?, ?, ?)
                ''', (guild_id, channel_id, checkin_time, gif_url))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                # 配置已存在，更新
                await db.execute('''
                    UPDATE checkin_config 
                    SET channel_id = ?, checkin_time = ?, gif_url = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = ?
                ''', (channel_id, checkin_time, gif_url, guild_id))
                await db.commit()
                return True
    
    async def get_config(self, guild_id: str) -> Optional[CheckinConfig]:
        """獲取簽到配置"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT * FROM checkin_config WHERE guild_id = ?',
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return CheckinConfig(*row)
                return None
    
    async def checkin(self, user_id: str, guild_id: str) -> Tuple[bool, int, int]:
        """
        用戶簽到
        返回: (是否成功, 總簽到次數, 連續簽到天數)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
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
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            async with db.execute(
                'SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?',
                (user_id, guild_id, yesterday)
            ) as cursor:
                yesterday_record = await cursor.fetchone()
                
                # 計算連續簽到天數
                if yesterday_record:
                    # 昨天簽到了，連續天數 +1
                    streak = yesterday_record[4] + 1
                else:
                    # 昨天沒簽到，連續天數 = 1
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
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT streak_days FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?',
                (user_id, guild_id, today)
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result[0]
            
            # 如果今天沒有簽到，檢查最近一次簽到的連續天數
            async with db.execute(
                'SELECT streak_days FROM checkin_records WHERE user_id = ? AND guild_id = ? ORDER BY checkin_date DESC LIMIT 1',
                (user_id, guild_id)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0
    
    async def has_checked_today(self, user_id: str, guild_id: str) -> bool:
        """檢查今天是否已經簽到"""
        today = datetime.now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT * FROM checkin_records WHERE user_id = ? AND guild_id = ? AND checkin_date = ?',
                (user_id, guild_id, today)
            ) as cursor:
                result = await cursor.fetchone()
                return result is not None
    
    async def get_leaderboard(self, guild_id: str, 
                             limit: int = 10, 
                             by_streak: bool = False) -> List[Dict]:
        """
        獲取排行榜
        by_streak: True = 按連續簽到天數排序, False = 按總簽到次數排序
        """
        async with aiosqlite.connect(self.db_path) as db:
            if by_streak:
                # 按連續簽到天數排序
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
                # 按總簽到次數排序
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