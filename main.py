import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime, timedelta, timezone

# 台灣時區 (UTC+8)
TAIWAN_TZ = timezone(timedelta(hours=8))

def get_taiwan_time():
    """獲取台灣時間"""
    return datetime.now(TAIWAN_TZ)

def format_taiwan_time(dt=None):
    """格式化台灣時間"""
    if dt is None:
        dt = get_taiwan_time()
    return dt.strftime("%Y-%m-%d %H:%M:%S")
from dotenv import load_dotenv
import os
import json
from typing import Optional, List
import uuid
import asyncio
import sys
import aiohttp
import tempfile
import os
from urllib.parse import urlparse

# 設置 PYTHONUNBUFFERED 環境變量
os.environ['PYTHONUNBUFFERED'] = '1'

print("🚀 開始加載 main.py", flush=True)

# 根據環境變量選擇數據庫類型
USE_D1 = os.getenv("USE_D1", "false").lower() == "true"

if USE_D1:
    from database_d1 import Database
    print("🌐 使用 Cloudflare D1 數據庫", flush=True)
else:
    from database import Database
    print("💾 使用本地 SQLite 數據庫", flush=True)

from tag_manager import TagManager
from message_handler import MessageHandler
from history_processor import HistoryProcessor
from emoji_utils import compare_emoji, normalize_emoji, is_custom_emoji, display_emoji, set_embed_emoji
from checkin_manager import CheckinManager
from checkin_system import CheckinView, CheckinSettingsView, GifConfirmationView
from reply_manager import ReplyManager

# 加載環境變量
load_dotenv()

# 獲取配置
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# 生成唯一的實例 ID
INSTANCE_ID = str(uuid.uuid4())[:8]

# Bot 配置
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True  # 需要 reaction intent 來偵測 emoji

bot = commands.Bot(
    command_prefix=config.get("prefix", "!"),
    intents=intents,
    help_command=None
)

# 數據庫路徑配置
# Render 上使用固定路徑，避免環境變量問題
DB_PATH = "discord_tags.db"

# 初始化數據庫和管理器
if USE_D1:
    db = Database(use_d1=True)
    checkin_manager = CheckinManager(use_d1=True)
    reply_manager = ReplyManager(use_d1=True)
else:
    db = Database(db_path=DB_PATH)
    checkin_manager = CheckinManager(db_path=DB_PATH)
    reply_manager = ReplyManager(db_path=DB_PATH)
    
tag_manager = TagManager(db)
message_handler = None
history_processor = None

# 命令鎖 - 防止重複執行
_command_locks = {}

async def acquire_command_lock(command_name: str, user_id: str, timeout: float = 5.0):
    """獲取命令鎖"""
    lock_key = f"{command_name}_{user_id}"
    if lock_key not in _command_locks:
        _command_locks[lock_key] = asyncio.Lock()
    
    try:
        await asyncio.wait_for(_command_locks[lock_key].acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False

def release_command_lock(command_name: str, user_id: str):
    """釋放命令鎖"""
    lock_key = f"{command_name}_{user_id}"
    if lock_key in _command_locks:
        if _command_locks[lock_key].locked():
            _command_locks[lock_key].release()

# 初始化標誌
_initialized = False

# 簽到系統標誌
_checkin_initialized = False

# ========== Emoji 偵測邏輯 ==========

@bot.event
async def on_message(message: discord.Message):
    """處理訊息（用於處理簽到 GIF 更換和 GIF 觸發簽到）"""
    # 忽略 bot 的訊息
    if message.author.bot:
        return
    
    print(f"🔍 ===== on_message 被調用 =====", flush=True)
    print(f"🔍 用戶: {message.author.name} (ID: {message.author.id})", flush=True)
    print(f"🔵 頻道: {message.channel.name} (ID: {message.channel.id})", flush=True)
    print(f"📝 訊息內容: {message.content[:100] if message.content else '(無文字)'}", flush=True)
    print(f"📎 附件數量: {len(message.attachments)}", flush=True)
    print(f"🎭 貼圖數量: {len(message.stickers)}", flush=True)
    
    # 獲取基本資訊（初始化以避免 UnboundLocalError）
    guild_id = str(message.guild.id) if message.guild else ""
    channel_id = str(message.channel.id)
    user_id = str(message.author.id)
    
    # ========== 刷版區 @Bot 回覆偵測 ==========
    # 檢查是否是回覆 Bot 的訊息（@bot 或回覆 Bot 的訊息）
    if guild_id and channel_id:
        config = await reply_manager.get_config(guild_id)
        if config and str(config.get('channel_id')) == channel_id and config.get('enabled') and not message.author.bot:
            # 檢查是否提及了 Bot
            bot_mentioned = bot.user.id in [m.id for m in message.mentions]
            # 檢查是否是回覆 Bot 的訊息
            is_reply_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author.id == bot.user.id if message.reference else False
            
            if bot_mentioned or is_reply_to_bot:
                print(f"🔍 檢測到用戶回覆 Bot，準備回覆...", flush=True)
                
                # 獲取用戶傳的訊息內容
                reply_content = message.content
                # 移除 @mention
                if reply_content:
                    for mention in message.mentions:
                        reply_content = reply_content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "").strip()
                
                # 發送回覆
                if message.attachments:
                    for attachment in message.attachments:
                        if attachment.content_type and 'image' in attachment.content_type:
                            try:
                                await message.channel.send(
                                    f"{message.author.mention} {reply_content if reply_content else ''}",
                                    file=discord.File.from_attachment(attachment)
                                )
                            except Exception as e:
                                print(f"❌ 發送附件失敗: {e}", flush=True)
                            break
                elif message.stickers:
                    sticker = message.stickers[0]
                    try:
                        await message.channel.send(
                            f"{message.author.mention} {reply_content if reply_content else ''}",
                            sticker=sticker
                        )
                    except Exception as e:
                        print(f"❌ 發送貼圖失敗: {e}", flush=True)
                elif message.emojis:
                    custom_emoji = message.emojis[0]
                    try:
                        await message.channel.send(
                            f"{message.author.mention} {reply_content if reply_content else ''}",
                            emoji=f"{custom_emoji}"
                        )
                    except Exception as e:
                        print(f"❌ 發送表情失敗: {e}", flush=True)
                else:
                    # 只有文字
                    await message.channel.send(f"{message.author.mention} {reply_content}")
                
                print(f"✅ Bot 回覆已發送", flush=True)
                return
    
    # 處理簽到 GIF 更換
    # 檢查資料庫中是否有 GIF 更換請求
    print(f"🔍 檢查資料庫中的 GIF 更換請求...", flush=True)
    gif_request = await checkin_manager.get_gif_change_request(user_id, channel_id)
    
    if gif_request:
        print(f"✅ 找到 GIF 更換請求: {gif_request}", flush=True)
        
        # 提取 GIF 連結
        gif_url = None
        if message.attachments:
            print(f"🔍 檢查 {len(message.attachments)} 個附件", flush=True)
            for i, attachment in enumerate(message.attachments):
                print(f"🔍 附件 {i}: {attachment.filename}, 類型: {attachment.content_type}", flush=True)
                if attachment.content_type and 'image' in attachment.content_type:
                    gif_url = attachment.url
                    print(f"✅ 從附件獲取到 URL: {gif_url}", flush=True)
                    break
        
        # 檢查貼圖
        if not gif_url and message.stickers:
            print(f"🔍 檢查 {len(message.stickers)} 個貼圖", flush=True)
            sticker = message.stickers[0]
            gif_url = sticker.url
            print(f"✅ 從貼圖獲取到 URL: {gif_url}", flush=True)
        
        if not gif_url:
            # 檢查訊息內容是否包含連結
            print(f"🔍 檢查訊息內容中的連結", flush=True)
            if message.content:
                import re
                urls = re.findall(r'(https?://\S+)', message.content)
                print(f"🔍 找到的連結: {urls}", flush=True)
                if urls:
                    gif_url = urls[0]
                    print(f"✅ 從訊息內容獲取到 URL: {gif_url}", flush=True)
        
        if gif_url:
            print(f"🔍 準備更新 GIF 配置", flush=True)
            # 更新配置
            guild_id = gif_request['guild_id']
            print(f"🔍 Guild ID: {guild_id}", flush=True)
            print(f"🔍 Channel ID: {channel_id}", flush=True)
            print(f"🔍 Checkin Time: {gif_request['checkin_time']}", flush=True)
            
            await checkin_manager.set_config(
                guild_id,
                channel_id,
                gif_request['checkin_time'],
                gif_url
            )
            
            print(f"✅ GIF 配置已更新", flush=True)
            
            embed = discord.Embed(
                title="✅ GIF 已更新",
                description=f"簽到 GIF 已設置",
                color=discord.Color.green()
            )
            embed.set_image(url=gif_url)
            embed.add_field(name="預覽", value="這就是新的簽到 GIF", inline=False)
            
            # 發送訊息並在 3 秒後刪除
            reply_msg = await message.reply(embed=embed)
            import asyncio
            await asyncio.sleep(3)
            await reply_msg.delete()
            await message.delete()
            print(f"✅ 回復已發送", flush=True)
        else:
            print(f"❌ 未檢測到有效的 GIF", flush=True)
            error_msg = await message.reply("❌ 未檢測到有效的 GIF！請重新發送。")
            import asyncio
            await asyncio.sleep(2)
            await error_msg.delete()
            await message.delete()
            print(f"✅ 錯誤回復已發送", flush=True)
    else:
        print(f"🔍 沒有找到 GIF 更換請求", flush=True)
        
        # 處理 GIF 觸發簽到
        if guild_id and channel_id:
            print(f"🔍 檢查是否為簽到頻道...", flush=True)
            config = await checkin_manager.get_config(guild_id)
            
            if config and str(config.get('channel_id')) == channel_id:
                print(f"✅ 這是簽到頻道", flush=True)
                gif_url = config.get('gif_url', '')
                gif_id = config.get('gif_id', '')
                
                if gif_url:
                    print(f"🔍 檢查用戶是否發送了簽到 GIF...", flush=True)
                    print(f"🔍 設定的 GIF URL: {gif_url}", flush=True)
                    print(f"🔍 設定的 GIF ID: {gif_id}", flush=True)
                    
                    # 檢查用戶是否發送了設定的 GIF
                    sent_gif_url = None
                    sent_gif_id = None
                    
                    # 檢查附件
                    if message.attachments:
                        for attachment in message.attachments:
                            if attachment.content_type and 'image' in attachment.content_type:
                                sent_gif_url = attachment.url
                                print(f"🔍 從附件獲取到 URL: {sent_gif_url}", flush=True)
                                # 從 URL 中提取 ID
                                import re
                                id_match = re.search(r'/(\d{16,})', attachment.url)
                                if id_match:
                                    sent_gif_id = id_match.group(1)
                                    print(f"🔍 從附件提取到 GIF ID: {sent_gif_id}", flush=True)
                                break
                    
                    # 檢查貼圖
                    if not sent_gif_url and message.stickers:
                        print(f"🔍 檢查 {len(message.stickers)} 個貼圖", flush=True)
                        sticker = message.stickers[0]
                        sent_gif_url = sticker.url
                        sent_gif_id = str(sticker.id)
                        print(f"🔍 從貼圖獲取到 URL: {sent_gif_url}", flush=True)
                        print(f"🔍 從貼圖提取到 GIF ID: {sent_gif_id}", flush=True)
                    
                    # 檢查訊息內容（即使已經從附件或貼圖獲取了 URL，也要檢查內容中的 ID）
                    if message.content:
                        import re
                        
                        # 檢查是否是純 ID（訊息內容只有數字）
                        content_stripped = message.content.strip()
                        if re.match(r'^\d{16,}$', content_stripped):
                            # 這是一個純 ID
                            if not sent_gif_id:
                                sent_gif_id = content_stripped
                                print(f"🔍 從訊息內容提取到純 GIF ID: {sent_gif_id}", flush=True)
                        else:
                            # 檢查是否有 URL
                            urls = re.findall(r'(https?://\S+)', message.content)
                            if urls:
                                if not sent_gif_url:
                                    sent_gif_url = urls[0]
                                    print(f"🔍 從訊息內容獲取到 URL: {sent_gif_url}", flush=True)
                                # 從 URL 中提取 ID
                                id_match = re.search(r'/(\d{16,})', urls[0])
                                if id_match and not sent_gif_id:
                                    sent_gif_id = id_match.group(1)
                                    print(f"🔍 從訊息內容提取到 GIF ID: {sent_gif_id}", flush=True)
                    
                    print(f"🔍 用戶發送的 GIF URL: {sent_gif_url}", flush=True)
                    print(f"🔍 用戶發送的 GIF ID: {sent_gif_id}", flush=True)
                    
                    # 檢查是否匹配（ID 或 URL）
                    is_match = False
                    match_reason = ""
                    
                    # 檢查 ID
                    if gif_id and sent_gif_id:
                        if sent_gif_id == gif_id:
                            is_match = True
                            match_reason = f"GIF ID 匹配: {gif_id}"
                            print(f"✅ {match_reason}", flush=True)
                        else:
                            print(f"🔍 GIF ID 不匹配: 設定={gif_id}, 發送={sent_gif_id}", flush=True)
                    
                    # 檢查 URL（如果 ID 不匹配或沒有設置 ID）
                    if not is_match and sent_gif_url:
                        from urllib.parse import urlparse
                        sent_parsed = urlparse(sent_gif_url)
                        config_parsed = urlparse(gif_url)
                        
                        print(f"🔍 發送的 URL - Path: {sent_parsed.path}, Netloc: {sent_parsed.netloc}", flush=True)
                        print(f"🔍 設定的 URL - Path: {config_parsed.path}, Netloc: {config_parsed.netloc}", flush=True)
                        
                        url_match = (
                            sent_parsed.path == config_parsed.path and
                            sent_parsed.netloc == config_parsed.netloc
                        )
                        
                        print(f"🔍 URL 匹配結果: {url_match}", flush=True)
                        
                        if url_match:
                            is_match = True
                            match_reason = "GIF URL 匹配"
                            print(f"✅ {match_reason}", flush=True)
                    
                    if is_match:
                        print(f"✅ 用戶發送了簽到 GIF ({match_reason})", flush=True)
                        
                        # 執行簽到
                        success, total, streak = await checkin_manager.checkin(user_id, guild_id)
                        
                        if success:
                            # 簽到成功
                            embed = discord.Embed(
                                title="✨ 簽到成功！",
                                description=f"恭喜 <@{user_id}> 簽到成功！",
                                color=discord.Color.green()
                            )
                            
                            # 顯示 GIF
                            embed.set_image(url=gif_url)
                            
                            embed.add_field(name="總簽到次數", value=f"📊 {total} 次", inline=True)
                            embed.add_field(name="連續簽到", value=f"🔥 {streak} 天", inline=True)
                            embed.add_field(name="簽到時間", value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), inline=False)
                            embed.add_field(name="簽到方式", value="點擊按鈕或發送簽到 GIF/貼圖都可以簽到", inline=False)
                            embed.set_footer(text=f"明天同一時間再來簽到吧！")
                            
                            await message.reply(embed=embed)
                            print(f"✅ 簽到成功回復已發送", flush=True)
                        else:
                            # 今天已經簽到過
                            embed = discord.Embed(
                                title="⚠️ 已簽到",
                                description=f"<@{user_id}> 你今天已經簽到過了！",
                                color=discord.Color.orange()
                            )
                            embed.add_field(name="總簽到次數", value=f"📊 {total} 次", inline=True)
                            embed.add_field(name="連續簽到", value=f"🔥 {streak} 天", inline=True)
                            embed.add_field(name="簽到方式", value="點擊按鈕或發送簽到 GIF/貼圖都可以簽到", inline=False)
                            embed.add_field(name="明天再來", value="明天 00:00 後可以再次簽到", inline=False)
                            embed.set_footer(text=f"明天同一時間再來簽到吧！")
                            
                            await message.reply(embed=embed)
                            print(f"✅ 已簽到回復已發送", flush=True)
                    else:
                        print(f"🔍 用戶發送的 GIF 不匹配簽到 GIF", flush=True)
                else:
                    print(f"🔍 沒有設置簽到 GIF", flush=True)
            else:
                print(f"🔍 不是簽到頻道或沒有簽到配置", flush=True)
    
    # 處理刷版區回覆
    print(f"🔍 檢查刷版區回覆請求...", flush=True)
    
    # 檢查是否有新增回覆請求
    add_request = await reply_manager.get_add_request(user_id, channel_id)
    if add_request:
        print(f"✅ 找到新增回覆請求: {add_request}", flush=True)
        
        # 提取 GIF/貼圖資訊
        trigger_type = None
        trigger_id = None
        trigger_url = None
        
        # 檢查附件
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and 'image' in attachment.content_type:
                    trigger_type = 'gif'
                    trigger_url = attachment.url
                    # 從 URL 中提取 ID
                    import re
                    id_match = re.search(r'/(\d{16,})', attachment.url)
                    if id_match:
                        trigger_id = id_match.group(1)
                    else:
                        trigger_id = str(attachment.id)
                    print(f"✅ 從附件獲取: {trigger_type}, ID: {trigger_id}, URL: {trigger_url}", flush=True)
                    break
        
        # 檢查貼圖
        if not trigger_type and message.stickers:
            sticker = message.stickers[0]
            trigger_type = 'sticker'
            trigger_id = str(sticker.id)
            trigger_url = sticker.url
            print(f"✅ 從貼圖獲取: {trigger_type}, ID: {trigger_id}, URL: {trigger_url}", flush=True)
        
        # 檢查自定義表情符號
        if not trigger_type and message.content:
            # 檢查訊息內容中是否有自定義表情符號
            import re
            emoji_pattern = r'<a?:(\w+):(\d{16,})>'
            emojis = re.findall(emoji_pattern, message.content)
            if emojis:
                emoji_name, emoji_id = emojis[0]
                trigger_type = 'emoji'
                trigger_id = emoji_id
                trigger_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.webp"
                print(f"✅ 從表情符號獲取: {trigger_type}, ID: {trigger_id}, URL: {trigger_url}", flush=True)
        
        if trigger_type and trigger_id:
            # 添加觸發器
            success = await reply_manager.add_trigger(
                guild_id=guild_id,
                user_id=user_id,
                trigger_type=trigger_type,
                trigger_id=trigger_id,
                trigger_url=trigger_url
            )
            
            print(f"🔍 add_trigger 返回結果: {success}", flush=True)
            
            # 驗證觸發器是否真的被添加
            if success:
                triggers = await reply_manager.get_triggers(guild_id)
                print(f"🔍 驗證查詢找到 {len(triggers)} 個觸發器", flush=True)
                for t in triggers:
                    print(f"🔍 觸發器: ID={t['trigger_id'][-8:]}, type={t['trigger_type']}", flush=True)
            
            if success:
                embed = discord.Embed(
                    title="✅ 回覆已新增",
                    description="此 GIF/貼圖/表情符號已被加入回覆列表",
                    color=discord.Color.green()
                )
                if trigger_url:
                    embed.set_image(url=trigger_url)
                embed.add_field(name="類型", value=trigger_type, inline=True)
                embed.add_field(name="ID", value=trigger_id[-8:], inline=True)
                
                # 發送訊息（不刪除）
                await message.reply(embed=embed)
                print(f"✅ 回覆已新增並回復", flush=True)
                # 新增回覆完成後直接返回，避免繼續執行自動回覆邏輯
                return
            else:
                await message.reply("❌ 新增回覆失敗！")
                print(f"❌ 新增回覆失敗", flush=True)
                return
        else:
            await message.reply("❌ 未檢測到有效的 GIF/貼圖/表情符號！請重新發送。")
            print(f"❌ 未檢測到有效的觸發器", flush=True)
            return
    
    # 檢查是否有刪除回覆請求
    delete_request = await reply_manager.get_delete_request(user_id, channel_id)
    if delete_request:
        print(f"✅ 找到刪除回覆請求: {delete_request}", flush=True)
        
        # 提取 GIF/貼圖資訊
        trigger_id = None
        
        # 檢查附件
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and 'image' in attachment.content_type:
                    # 從 URL 中提取 ID
                    import re
                    id_match = re.search(r'/(\d{16,})', attachment.url)
                    if id_match:
                        trigger_id = id_match.group(1)
                    else:
                        trigger_id = str(attachment.id)
                    print(f"✅ 從附件提取 ID: {trigger_id}", flush=True)
                    break
        
        # 檢查貼圖
        if not trigger_id and message.stickers:
            sticker = message.stickers[0]
            trigger_id = str(sticker.id)
            print(f"✅ 從貼圖提取 ID: {trigger_id}", flush=True)
        
        # 檢查自定義表情符號
        if not trigger_id and message.content:
            import re
            emoji_pattern = r'<a?:(\w+):(\d{16,})>'
            emojis = re.findall(emoji_pattern, message.content)
            if emojis:
                emoji_name, emoji_id = emojis[0]
                trigger_id = emoji_id
                print(f"✅ 從表情符號提取 ID: {trigger_id}", flush=True)
        
        if trigger_id:
            # 刪除觸發器
            success = await reply_manager.delete_trigger(
                guild_id=guild_id,
                trigger_id=trigger_id
            )
            
            if success:
                embed = discord.Embed(
                    title="✅ 回覆已刪除",
                    description="此 GIF/貼圖/表情符號已從回覆列表中移除",
                    color=discord.Color.green()
                )
                embed.add_field(name="ID", value=trigger_id[-8:], inline=True)
                
                # 發送訊息（不刪除）
                await message.reply(embed=embed)
                print(f"✅ 回覆已刪除並回復", flush=True)
                # 刪除回覆完成後直接返回，避免繼續執行自動回覆邏輯
                return
            else:
                await message.reply("❌ 刪除回覆失敗！")
                print(f"❌ 刪除回覆失敗", flush=True)
                return
        else:
            await message.reply("❌ 未檢測到有效的 GIF/貼圖/表情符號！請重新發送。")
            print(f"❌ 未檢測到有效的觸發器", flush=True)
            return
    
    # 處理刷版區自動回覆
    if guild_id and channel_id:
        config = await reply_manager.get_config(guild_id)
        
        print(f"🔍 檢查刷版區配置: {config}", flush=True)
        print(f"🔍 頻道 ID: {channel_id}", flush=True)
        print(f"🔍 配置頻道 ID: {config.get('channel_id') if config else None}", flush=True)
        print(f"🔍 是否啟用: {config.get('enabled') if config else None}", flush=True)
        print(f"🔍 是否 Bot: {message.author.bot}", flush=True)
        
        # 跳過 Bot 自己的訊息，避免無限循環
        if config and str(config.get('channel_id')) == channel_id and config.get('enabled') and not message.author.bot:
            print(f"🔍 這是刷版區，檢查觸發器...", flush=True)
            
            # 獲取訊息中的觸發器
            trigger_id = None
            trigger_type = None
            
            # 檢查附件
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.content_type and 'image' in attachment.content_type:
                        import re
                        id_match = re.search(r'/(\d{16,})', attachment.url)
                        if id_match:
                            trigger_id = id_match.group(1)
                        else:
                            trigger_id = str(attachment.id)
                        trigger_type = 'gif'
                        print(f"🔍 從附件提取觸發器: {trigger_type}, ID: {trigger_id}", flush=True)
                        break
            
            # 檢查貼圖
            if not trigger_id and message.stickers:
                sticker = message.stickers[0]
                trigger_id = str(sticker.id)
                trigger_type = 'sticker'
                print(f"🔍 從貼圖提取觸發器: {trigger_type}, ID: {trigger_id}", flush=True)
            
            # 檢查自定義表情符號
            if not trigger_id and message.content:
                import re
                emoji_pattern = r'<a?:(\w+):(\d{16,})>'
                emojis = re.findall(emoji_pattern, message.content)
                if emojis:
                    emoji_name, emoji_id = emojis[0]
                    trigger_id = emoji_id
                    trigger_type = 'emoji'
                    print(f"🔍 從表情符號提取觸發器: {trigger_type}, ID: {trigger_id}", flush=True)
            
            # 檢查是否有匹配的觸發器
            try:
                print(f"🔍 開始檢查觸發器，guild_id: {guild_id}", flush=True)
                triggers = await reply_manager.get_triggers(guild_id)
                print(f"🔍 獲取到 {len(triggers)} 個觸發器", flush=True)
                
                found_match = False
                for trigger in triggers:
                    print(f"🔍 檢查觸發器: ID={trigger['trigger_id'][-8:]} (目標: {trigger_id[-8:]})", flush=True)
                    if trigger['trigger_id'] == trigger_id:
                        print(f"✅ 找到匹配的觸發器，準備回覆...", flush=True)
                        found_match = True
                        
                        # 記錄使用次數
                        await reply_manager.record_usage(guild_id, trigger_id, user_id)
                        
                        # 發送回覆（使用 channel.send 而不是 reply，避免被檢測為觸發器）
                        reply_trigger_type = trigger['trigger_type']
                        reply_trigger_url = trigger['trigger_url']
                        
                        print(f"🔍 準備發送回覆: type={reply_trigger_type}, url={reply_trigger_url}", flush=True)
                        
                        if reply_trigger_type == 'gif' and reply_trigger_url:
                            # 下载 URL 到临时文件再发送
                            async def download_url_to_temp_file(url: str) -> str:
                                from urllib.parse import urlparse
                                async with aiohttp.ClientSession() as session:
                                    async with session.get(url) as response:
                                        content = await response.read()
                                parsed = urlparse(url)
                                ext = os.path.splitext(parsed.path)[1] if '.' in parsed.path else '.gif'
                                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                                temp_file.write(content)
                                temp_file.close()
                                return temp_file.name
                            
                            temp_path = await download_url_to_temp_file(reply_trigger_url)
                            try:
                                await message.channel.send(f"{message.author.mention}", file=discord.File(temp_path))
                            finally:
                                os.unlink(temp_path)
                        elif reply_trigger_type == 'sticker' and reply_trigger_url:
                            # 貼圖需要使用 Discord API 發送
                            try:
                                await message.channel.send(reply_trigger_url)
                            except Exception as e:
                                print(f"❌ 發送貼圖失敗: {e}", flush=True)
                        elif reply_trigger_type == 'emoji' and reply_trigger_url:
                            # 表情符號也使用 send 發送
                            try:
                                await message.channel.send(reply_trigger_url)
                            except Exception as e:
                                print(f"❌ 發送表情符號失敗: {e}", flush=True)
                        
                        print(f"✅ 回覆已發送", flush=True)
                        break
                
                if not found_match:
                    print(f"🔍 沒有找到匹配的觸發器", flush=True)
            except Exception as e:
                print(f"❌ 處理刷版區回覆時發生錯誤: {e}", flush=True)
                import traceback
                traceback.print_exc()
    
    # 確保其他命令繼續正常工作
    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """偵測 emoji 反應並自動添加標籤"""
    # 只處理消息反應，不處理頻道反應
    if payload.channel_id is None or payload.message_id is None:
        return
    
    # 獲取頻道和消息
    try:
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            return
        
        message = await channel.fetch_message(payload.message_id)
        
        # 檢查這個 emoji 是否對應一個標籤
        # 使用 emoji_utils 比較標籤 emoji 和反應 emoji
        # 支援：標準 emoji、自定義 emoji ID、完整格式
        
        # 獲取這個消息的所有標籤
        existing_tags = await db.get_message_tags(message.id)
        existing_tag_ids = [mt.tag_id for mt in existing_tags]
        
        # 查找對應的標籤
        tags = await tag_manager.get_available_tags()
        for tag in tags:
            # 使用 compare_emoji 函數進行比較
            if compare_emoji(tag.emoji, payload.emoji):
                # 檢查是否已經有這個標籤
                if tag.id in existing_tag_ids:
                    return  # 已經有這個標籤，跳過
                
                # 添加標籤
                created_at = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                success = await db.tag_message(
                    message_id=str(message.id),
                    channel_id=str(message.channel.id),
                    guild_id=str(message.guild.id),
                    tag_id=tag.id,
                    tagged_by=str(payload.user_id),
                    message_content=message.content,
                    author_id=str(message.author.id),
                    created_at=created_at
                )
                
                if success:
                    # 使用 display_emoji 來顯示 emoji 或圖片連結
                    emoji_display = display_emoji(tag.emoji)
                    embed = discord.Embed(
                        title=f"{emoji_display} 自動添加標籤",
                        description=f"訊息已自動添加標籤 `{tag.name}`",
                        color=discord.Color.green(),
                        timestamp=get_taiwan_time()
                    )
                    embed.add_field(name="標籤", value=f"{emoji_display} {tag.name}", inline=True)
                    if tag.description:
                        embed.add_field(name="說明", value=tag.description, inline=True)
                    embed.add_field(name="操作者", value=f"<@{payload.user_id}>", inline=True)
                    embed.set_footer(text=f"消息ID: {message.id}")
                    
                    # 發送回應
                    await message.reply(embed=embed)
                
                break  # 找到匹配的標籤後跳出循環
    
    except Exception as e:
        print(f"偵測 emoji 反應時發生錯誤: {e}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """偵測 emoji 反應被移除並自動移除標籤"""
    # 只處理消息反應，不處理頻道反應
    if payload.channel_id is None or payload.message_id is None:
        return
    
    # 獲取頻道和消息
    try:
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            return
        
        message = await channel.fetch_message(payload.message_id)
        
        # 檢查這個 emoji 是否對應一個標籤
        # 使用 emoji_utils 比較標籤 emoji 和反應 emoji
        
        # 獲取這個消息的所有標籤
        existing_tags = await db.get_message_tags(message.id)
        
        # 查找對應的標籤
        tags = await tag_manager.get_available_tags()
        for tag in tags:
            # 使用 compare_emoji 函數進行比較
            if compare_emoji(tag.emoji, payload.emoji):
                # 檢查是否這個消息有這個標籤
                has_tag = any(mt.tag_id == tag.id for mt in existing_tags)
                if not has_tag:
                    continue  # 沒有這個標籤，跳過
                
                # 檢查這條訊息上還有多少人在使用這個 emoji
                # 遍歷所有反應，檢查是否還有相同的 emoji
                has_other_reactions = False
                for reaction in message.reactions:
                    if compare_emoji(tag.emoji, reaction.emoji):
                        if reaction.count > 0:
                            has_other_reactions = True
                            break
                
                # 如果還有其他人在使用這個 emoji，不刪除標籤
                if has_other_reactions:
                    print(f"訊息 {message.id} 上還有其他人在使用 emoji {tag.emoji}，不刪除標籤")
                    return
                
                # 只有當所有人都移除了 emoji，才刪除標籤
                success = await db.untag_message(str(message.id), tag.id)
                
                if success:
                    # 使用 display_emoji 來顯示 emoji 或圖片連結
                    emoji_display = display_emoji(tag.emoji)
                    embed = discord.Embed(
                        title=f"{emoji_display} 自動移除標籤",
                        description=f"訊息已自動移除標籤 `{tag.name}`",
                        color=discord.Color.orange(),
                        timestamp=get_taiwan_time()
                    )
                    embed.add_field(name="標籤", value=f"{emoji_display} {tag.name}", inline=True)
                    if tag.description:
                        embed.add_field(name="說明", value=tag.description, inline=True)
                    embed.add_field(name="操作者", value=f"<@{payload.user_id}>", inline=True)
                    embed.set_footer(text=f"消息ID: {message.id}")
                    
                    # 發送回應
                    await message.reply(embed=embed)
                
                break  # 找到匹配的標籤後跳出循環
    
    except Exception as e:
        print(f"偵測 emoji 移除時發生錯誤: {e}")

# ========== Bot 啟動 ==========

async def checkin_scheduler():
    """簽到系統定時任務"""
    await bot.wait_until_ready()
    
    print(f"🕐 ===== 簽到定時任務已啟動 =====", flush=True)
    
    while not bot.is_closed():
        try:
            now = get_taiwan_time()
            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")
            
            # 每小時打印一次狀態
            if now.minute == 0:
                print(f"🕐 定時任務運行中 - 當前時間: {current_time} ({current_date})", flush=True)
            
            print(f"🔍 ===== 檢查簽到配置 =====", flush=True)
            print(f"🔍 當前時間: {current_time}", flush=True)
            
            # 檢查所有服務器的簽到配置
            for guild in bot.guilds:
                guild_id = str(guild.id)
                config = await checkin_manager.get_config(guild_id)
                
                print(f"🔍 服務器: {guild.name} (ID: {guild_id})", flush=True)
                if config:
                    print(f"🔍 配置存在 - 簽到時間: {config.get('checkin_time')}, 頻道 ID: {config.get('channel_id')}", flush=True)
                else:
                    print(f"🔍 沒有簽到配置", flush=True)
                
                if config and config['checkin_time'] == current_time:
                    print(f"✅ 時間匹配！準備發送簽到訊息", flush=True)
                    
                    # 發送簽到訊息
                    channel = bot.get_channel(int(config['channel_id']))
                    if channel:
                        print(f"✅ 找到頻道: {channel.name}", flush=True)
                        
                        view = CheckinView(checkin_manager, config['gif_url'])
                        embed = discord.Embed(
                            title="✨ 每日簽到",
                            description=f"今天是 {current_date}，點擊下方按鈕進行簽到！",
                            color=discord.Color.gold()
                        )
                        
                        if config['gif_url']:
                            embed.set_image(url=config['gif_url'])
                        
                        message = await channel.send(embed=embed, view=view)
                        print(f"✅ 簽到訊息已發送", flush=True)
                        
                        # 釘選訊息
                        await message.pin()
                        print(f"✅ 訊息已釘選", flush=True)
                        
                        # 發送總簽到次數排行榜
                        leaderboard_total = await checkin_manager.get_leaderboard(guild_id, limit=10, by_streak=False)
                        
                        if leaderboard_total:
                            embed = discord.Embed(
                                title="📊 總簽到次數排行榜",
                                color=discord.Color.gold()
                            )
                            
                            description = ""
                            for idx, entry in enumerate(leaderboard_total, 1):
                                user_id = entry["user_id"]
                                value = entry["value"]
                                medal = ""
                                if idx == 1:
                                    medal = "🥇"
                                elif idx == 2:
                                    medal = "🥈"
                                elif idx == 3:
                                    medal = "🥉"
                                else:
                                    medal = f"{idx}."
                                
                                description += f"{medal} <@{user_id}>: {value} 次\n"
                            
                            embed.description = description
                            embed.set_footer(text=f"更新時間: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            await channel.send(embed=embed)
                            print(f"✅ 總簽到次數排行榜已發送", flush=True)
                        
                        # 發送連續簽到排行榜
                        leaderboard_streak = await checkin_manager.get_leaderboard(guild_id, limit=10, by_streak=True)
                        
                        if leaderboard_streak:
                            embed = discord.Embed(
                                title="🔥 連續簽到排行榜",
                                color=discord.Color.orange()
                            )
                            
                            description = ""
                            for idx, entry in enumerate(leaderboard_streak, 1):
                                user_id = entry["user_id"]
                                value = entry["value"]
                                medal = ""
                                if idx == 1:
                                    medal = "🥇"
                                elif idx == 2:
                                    medal = "🥈"
                                elif idx == 3:
                                    medal = "🥉"
                                else:
                                    medal = f"{idx}."
                                
                                description += f"{medal} <@{user_id}>: {value} 天\n"
                            
                            embed.description = description
                            embed.set_footer(text=f"更新時間: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            await channel.send(embed=embed)
                            print(f"✅ 連續簽到排行榜已發送", flush=True)
                    else:
                        print(f"❌ 找不到頻道 ID: {config['channel_id']}", flush=True)
                else:
                    if config:
                        print(f"⏰ 時間不匹配: 設置時間={config['checkin_time']}, 當前時間={current_time}", flush=True)
            
            # 每分鐘檢查一次
            await asyncio.sleep(60)
            
        except Exception as e:
            print(f"簽到定時任務錯誤: {e}", flush=True)
            import traceback
            traceback.print_exc()
            await asyncio.sleep(60)

# ========== 心跳檢測 ==========

async def heartbeat_monitor():
    """心跳檢測，每 30 秒打印一次"""
    await bot.wait_until_ready()
    counter = 0
    while not bot.is_closed():
        counter += 1
        print(f"💓 Bot 心跳 #{counter} - {format_taiwan_time()}")
        await asyncio.sleep(30)

@bot.event
async def on_ready():
    """Bot 啟動時執行"""
    print(f"✅ [{INSTANCE_ID}] {bot.user.name} 已啟動!")
    print(f"✅ 服務器: {len(bot.guilds)}")
    print(f"✅ 前綴: {config.get('prefix', '!')}")
    
    # 初始化數據庫
    print(f"🔍 資料庫路徑: {DB_PATH}", flush=True)
    print(f"🔍 資料庫文件是否存在: {os.path.exists(DB_PATH)}", flush=True)
    if os.path.exists(DB_PATH):
        print(f"🔍 資料庫文件大小: {os.path.getsize(DB_PATH)} bytes", flush=True)
    
    await db.init_db()
    print("✅ 數據庫初始化完成")
    
    print(f"🔍 資料庫初始化後文件是否存在: {os.path.exists(DB_PATH)}", flush=True)
    if os.path.exists(DB_PATH):
        print(f"🔍 資料庫初始化後文件大小: {os.path.getsize(DB_PATH)} bytes", flush=True)
    
    # 初始化簽到系統表
    print(f"🔍 開始初始化簽到系統表...", flush=True)
    await checkin_manager.init_tables()
    print("✅ 簽到系統初始化完成")
    
    # 初始化回覆系統表
    print(f"🔍 開始初始化回覆系統表...", flush=True)
    await reply_manager.init_tables()
    print("✅ 回覆系統初始化完成")
    
    # 不初始化默認標籤，讓用戶自己創建
    print("✅ 標籤系統就緒（無預設標籤）")
    
    # 初始化處理器
    global message_handler, history_processor, _checkin_initialized
    message_handler = MessageHandler(bot, db, tag_manager)
    history_processor = HistoryProcessor(bot, db, tag_manager)
    _checkin_initialized = True
    
    # 設置狀態
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{config.get('prefix', '!')}menu"
        )
    )
    
    # 設置初始化標誌
    global _initialized
    _initialized = True
    
    # 啟動簽到系統定時任務
    bot.loop.create_task(checkin_scheduler())
    
    # 啟動心跳檢測任務
    bot.loop.create_task(heartbeat_monitor())
    
    # 清除舊的斜線命令
    try:
        print("🔄 清除舊的斜線命令...")
        synced_commands = await bot.tree.sync()
        if synced_commands:
            print(f"✅ 已清除 {len(synced_commands)} 個斜線命令")
        else:
            print("✅ 沒有舊的斜線命令需要清除")
    except Exception as e:
        print(f"⚠️ 清除斜線命令時發生錯誤: {e}")

# ========== 主菜單 ==========

class MainMenuView(View):
    """主選單"""
    
    def __init__(self, guild_id: Optional[str] = None, channel_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    def _should_show_checkin_button(self):
        """檢查是否應該顯示簽到按鈕"""
        if not self.guild_id or not self.channel_id:
            return False
        # 由於是異步方法，我們在初始化時不調用它
        # 而是在 menu_command 中決定是否添加按鈕
        return False
    
    @discord.ui.button(label="🏷️ 新增標籤", style=discord.ButtonStyle.primary, emoji="🏷️", custom_id="add_tag")
    async def add_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示新增標籤模態框"""
        modal = AddTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔍 搜索標籤", style=discord.ButtonStyle.secondary, emoji="🔍", custom_id="search_tag")
    async def search_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示搜索標籤模態框"""
        modal = SearchTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 查看標籤", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="view_tags")
    async def view_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示所有標籤"""
        print("🔍 ===== 開始查看標籤 =====")
        print(f"🔍 交互來自: {interaction.user.name} ({interaction.user.id})")
        try:
            print("🔍 正在獲取標籤...")
            tags = await tag_manager.get_available_tags()
            print(f"🔍 獲取到 {len(tags)} 個標籤")
            
            if not tags:
                print("🔍 沒有標籤，顯示提示訊息")
                embed = discord.Embed(
                    title="📋 標籤列表",
                    description="暫無可用標籤，請先新增標籤！",
                    color=discord.Color.orange()
                )
                embed.add_field(name="💡 提示", value="使用 `!menu` 點擊「🏷️ 新增標籤」來創建新標籤", inline=False)
                await interaction.response.edit_message(embed=embed)
                return
            
            # 分組顯示標籤
            tag_list = []
            for i, tag in enumerate(tags):
                print(f"🔍 標籤 {i}: name={tag.name}, emoji={tag.emoji}, emoji_type={type(tag.emoji)}")
                # 使用 display_emoji 來顯示 emoji 或圖片連結
                emoji_display = display_emoji(tag.emoji)
                print(f"🔍 emoji_display: {emoji_display}, type={type(emoji_display)}")
                tag_list.append(f"{emoji_display} **{tag.name}**")
                if tag.description:
                    tag_list[-1] += f" - {tag.description}"
                print(f"🔍 tag_list[{i}]: {tag_list[-1]}")
            
            print(f"🔍 準備發送 embed，tag_list 長度: {len(tag_list)}")
            embed = discord.Embed(
                title="📋 所有標籤",
                description="\n".join(tag_list),
                color=discord.Color.blue()
            )
            embed.add_field(name="總數", value=f"共有 {len(tags)} 個標籤", inline=True)
            
            # 添加返回按鈕
            view = BackToMenuView(guild_id=self.guild_id, channel_id=self.channel_id)
            print(f"🔍 準備編輯訊息...")
            await interaction.response.edit_message(embed=embed, view=view)
            print("🔍 ===== 查看標籤完成 =====")
            
        except Exception as e:
            print(f"❌ 查看標籤時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 查看標籤時發生錯誤: {str(e)}")
            except:
                print("❌ 無法發送錯誤訊息")
                await interaction.followup.send(f"❌ 查看標籤時發生錯誤: {str(e)}")
            
        except Exception as e:
            print(f"查看標籤錯誤: {e}")
            try:
                await interaction.response.send_message("❌ 查看標籤時發生錯誤")
            except:
                await interaction.followup.send("❌ 查看標籤時發生錯誤")
    
    
    
    @discord.ui.button(label="📥 進階功能", style=discord.ButtonStyle.success, emoji="📥", custom_id="advanced_features")
    async def advanced_features(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示進階功能菜單"""
        view = AdvancedFeaturesView(guild_id=self.guild_id, channel_id=self.channel_id)
        embed = discord.Embed(
            title="📥 進階功能",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="📥 導入歷史", value="導入頻道的歷史訊息並添加標籤", inline=False)
        embed.add_field(name="📊 統計數據", value="查看系統統計和標籤使用情況", inline=False)
        embed.add_field(name="🗑️ 刪除標籤", value="刪除不需要的標籤", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)

class BackToMenuView(View):
    """返回主菜單按鈕"""
    
    def __init__(self, guild_id: Optional[str] = None, channel_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="🔙 返回主菜單", style=discord.ButtonStyle.secondary)
    async def back_to_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回主菜單"""
        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)
        
        print(f"🔍 ===== BackToMenuView.back_to_menu 被調用 =====", flush=True)
        print(f"🔍 Guild ID: {guild_id}", flush=True)
        print(f"🔍 Channel ID: {channel_id}", flush=True)
        
        # 檢查是否在簽到頻道
        checkin_config = await checkin_manager.get_config(guild_id)
        is_checkin_channel = checkin_config and checkin_config['channel_id'] == channel_id
        print(f"🔍 is_checkin_channel: {is_checkin_channel}", flush=True)
        
        # 檢查是否在刷版區頻道
        reply_config = await reply_manager.get_config(guild_id)
        is_reply_channel = reply_config and reply_config.get('channel_id') == channel_id and reply_config.get('enabled')
        print(f"🔍 is_reply_channel: {is_reply_channel}", flush=True)
        
        # 根據情況選擇 View 和 embed
        if is_checkin_channel and is_reply_channel:
            view = MainMenuViewWithCheckinAndReply(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuViewWithCheckinAndReply", flush=True)
        elif is_checkin_channel:
            view = MainMenuViewWithCheckin(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuViewWithCheckin", flush=True)
        elif is_reply_channel:
            view = MainMenuViewWithReply(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuViewWithReply", flush=True)
        else:
            view = MainMenuView(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuView", flush=True)
        
        embed = discord.Embed(
            title="🎮 Discord 標籤系統",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="🏷️ 新增標籤", value="添加新的標籤", inline=False)
        embed.add_field(name="🔍 搜索標籤", value="搜索帶有標籤的消息", inline=False)
        embed.add_field(name="📋 查看標籤", value="查看所有可用標籤", inline=False)
        
        if is_checkin_channel:
            embed.add_field(name="✨ 簽到設定", value="設置每日簽到功能", inline=False)
            print(f"🔍 已添加簽到設定按鈕到 embed", flush=True)
        
        if is_reply_channel:
            embed.add_field(name="🎭 刷版區設定", value="設置刷版區回覆功能", inline=False)
            print(f"🔍 已添加刷版區設定按鈕到 embed", flush=True)
        
        embed.add_field(name="📥 進階功能", value="導入歷史、統計等", inline=False)
        
        print(f"🔍 準備編輯訊息...", flush=True)
        await interaction.response.edit_message(embed=embed, view=view)
        print(f"✅ 訊息已編輯", flush=True)

class MainMenuViewWithCheckin(View):
    """主選單 - 包含簽到設定按鈕"""
    
    def __init__(self, guild_id: Optional[str] = None, channel_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="🏷️ 新增標籤", style=discord.ButtonStyle.primary, emoji="🏷️", custom_id="add_tag_with_checkin")
    async def add_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示新增標籤模態框"""
        modal = AddTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔍 搜索標籤", style=discord.ButtonStyle.secondary, emoji="🔍", custom_id="search_tag_with_checkin")
    async def search_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示搜索標籤模態框"""
        modal = SearchTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 查看標籤", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="view_tags_with_checkin")
    async def view_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示所有標籤"""
        print("🔍 ===== 開始查看標籤（帶簽到） =====")
        print(f"🔍 交互來自: {interaction.user.name} ({interaction.user.id})")
        try:
            print("🔍 正在獲取標籤...")
            tags = await tag_manager.get_available_tags()
            print(f"🔍 獲取到 {len(tags)} 個標籤")
            
            if not tags:
                print("🔍 沒有標籤，顯示提示訊息")
                embed = discord.Embed(
                    title="📋 標籤列表",
                    description="暫無可用標籤，請先新增標籤！",
                    color=discord.Color.orange()
                )
                embed.add_field(name="💡 提示", value="使用 `!menu` 點擊「🏷️ 新增標籤」來創建新標籤", inline=False)
                await interaction.response.edit_message(embed=embed)
                return
            
            # 分組顯示標籤
            tag_list = []
            for i, tag in enumerate(tags):
                print(f"🔍 標籤 {i}: name={tag.name}, emoji={tag.emoji}, emoji_type={type(tag.emoji)}")
                # 使用 display_emoji 來顯示 emoji 或圖片連結
                emoji_display = display_emoji(tag.emoji)
                print(f"🔍 emoji_display: {emoji_display}, type={type(emoji_display)}")
                tag_list.append(f"{emoji_display} **{tag.name}**")
                if tag.description:
                    tag_list[-1] += f" - {tag.description}"
                print(f"🔍 tag_list[{i}]: {tag_list[-1]}")
            
            print(f"🔍 準備發送 embed，tag_list 長度: {len(tag_list)}")
            embed = discord.Embed(
                title="📋 所有標籤",
                description="\n".join(tag_list),
                color=discord.Color.blue()
            )
            embed.add_field(name="總數", value=f"共有 {len(tags)} 個標籤", inline=True)
            
            # 添加返回按鈕
            view = BackToMenuView(guild_id=self.guild_id, channel_id=self.channel_id)
            print(f"🔍 準備編輯訊息...")
            await interaction.response.edit_message(embed=embed, view=view)
            print("🔍 ===== 查看標籤完成 =====")
            
        except Exception as e:
            print(f"❌ 查看標籤時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 查看標籤時發生錯誤: {str(e)}")
            except:
                print("❌ 無法發送錯誤訊息")
                await interaction.followup.send(f"❌ 查看標籤時發生錯誤: {str(e)}")
    
    @discord.ui.button(label="✨ 簽到設定", style=discord.ButtonStyle.success, emoji="✨", custom_id="checkin_settings")
    async def checkin_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示簽到設置菜單"""
        guild_id = str(interaction.guild.id)
        view = CheckinSettingsView(checkin_manager, guild_id)
        embed = discord.Embed(
            title="✨ 簽到設定",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="⏰ 調整時間", value="調整每日簽到的時間界限", inline=False)
        embed.add_field(name="🖼️ 更換 GIF", value="更換簽到成功時顯示的 GIF", inline=False)
        embed.add_field(name="📊 顯示排名", value="查看簽到排行榜", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📥 進階功能", style=discord.ButtonStyle.success, emoji="📥", custom_id="advanced_features_with_checkin")
    async def advanced_features(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示進階功能菜單"""
        view = AdvancedFeaturesView(guild_id=self.guild_id, channel_id=self.channel_id)
        embed = discord.Embed(
            title="📥 進階功能",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="📥 導入歷史", value="導入頻道的歷史訊息並添加標籤", inline=False)
        embed.add_field(name="📊 統計數據", value="查看系統統計和標籤使用情況", inline=False)
        embed.add_field(name="🗑️ 刪除標籤", value="刪除不需要的標籤", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)

class MainMenuViewWithReply(View):
    """主選單 - 包含刷版區設定按鈕"""
    
    def __init__(self, guild_id: Optional[str] = None, channel_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="🏷️ 新增標籤", style=discord.ButtonStyle.primary, emoji="🏷️", custom_id="add_tag_with_reply")
    async def add_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示新增標籤模態框"""
        modal = AddTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔍 搜索標籤", style=discord.ButtonStyle.secondary, emoji="🔍", custom_id="search_tag_with_reply")
    async def search_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示搜索標籤模態框"""
        modal = SearchTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 查看標籤", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="view_tags_with_reply")
    async def view_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示所有標籤"""
        print("🔍 ===== 開始查看標籤（帶刷版區） =====")
        print(f"🔍 交互來自: {interaction.user.name} ({interaction.user.id})")
        try:
            print("🔍 正在獲取標籤...")
            tags = await tag_manager.get_available_tags()
            print(f"🔍 獲取到 {len(tags)} 個標籤")
            
            if not tags:
                print("🔍 沒有標籤，顯示提示訊息")
                embed = discord.Embed(
                    title="📋 標籤列表",
                    description="暫無可用標籤，請先新增標籤！",
                    color=discord.Color.orange()
                )
                embed.add_field(name="💡 提示", value="使用 `!menu` 點擊「🏷️ 新增標籤」來創建新標籤", inline=False)
                await interaction.response.edit_message(embed=embed)
                return
            
            # 分組顯示標籤
            tag_list = []
            for i, tag in enumerate(tags):
                print(f"🔍 標籤 {i}: name={tag.name}, emoji={tag.emoji}, emoji_type={type(tag.emoji)}")
                # 使用 display_emoji 來顯示 emoji 或圖片連結
                emoji_display = display_emoji(tag.emoji)
                print(f"🔍 emoji_display: {emoji_display}, type={type(emoji_display)}")
                tag_list.append(f"{emoji_display} **{tag.name}**")
                if tag.description:
                    tag_list[-1] += f" - {tag.description}"
                print(f"🔍 tag_list[{i}]: {tag_list[-1]}")
            
            print(f"🔍 準備發送 embed，tag_list 長度: {len(tag_list)}")
            embed = discord.Embed(
                title="📋 所有標籤",
                description="\n".join(tag_list),
                color=discord.Color.blue()
            )
            embed.add_field(name="總數", value=f"共有 {len(tags)} 個標籤", inline=True)
            
            # 添加返回按鈕
            view = BackToMenuView(guild_id=self.guild_id, channel_id=self.channel_id)
            print(f"🔍 準備編輯訊息...")
            await interaction.response.edit_message(embed=embed, view=view)
            print("🔍 ===== 查看標籤完成 =====")
            
        except Exception as e:
            print(f"❌ 查看標籤時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 查看標籤時發生錯誤: {str(e)}")
            except:
                print("❌ 無法發送錯誤訊息")
                await interaction.followup.send(f"❌ 查看標籤時發生錯誤: {str(e)}")
    
    @discord.ui.button(label="🎭 刷版區設定", style=discord.ButtonStyle.success, emoji="🎭", custom_id="reply_settings_with_reply")
    async def reply_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示刷版區設置菜單"""
        guild_id = str(interaction.guild.id)
        view = ReplySettingsView(reply_manager, guild_id)
        
        # 檢查是否已設置刷版區頻道
        config = await reply_manager.get_config(guild_id)
        
        if config:
            channel_id = config.get('channel_id')
            try:
                channel = bot.get_channel(int(channel_id))
                channel_name = channel.name if channel else f"未知頻道 ({channel_id})"
                description = f"當前刷版區頻道: **#{channel_name}**\n選擇一個操作："
            except:
                description = f"當前刷版區頻道: {channel_id}\n選擇一個操作："
        else:
            description = "尚未設置刷版區頻道\n選擇一個操作："
        
        embed = discord.Embed(
            title="🎭 刷版區設定",
            description=description,
            color=discord.Color.purple()
        )
        embed.add_field(name="⚙️ 設置頻道", value="設置當前頻道為刷版區", inline=False)
        embed.add_field(name="🖼️ 新增回覆", value="新增想要 bot 回覆的 GIF/貼圖/表情符號", inline=False)
        embed.add_field(name="📊 顯示排名", value="查看觸發回覆排行榜", inline=False)
        embed.add_field(name="🗑️ 刪除回覆", value="刪除想要 bot 回覆的 GIF/貼圖/表情符號", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📥 進階功能", style=discord.ButtonStyle.success, emoji="📥", custom_id="advanced_features_with_reply")
    async def advanced_features(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示進階功能菜單"""
        view = AdvancedFeaturesView(guild_id=self.guild_id, channel_id=self.channel_id)
        embed = discord.Embed(
            title="📥 進階功能",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="📥 導入歷史", value="導入頻道的歷史訊息並添加標籤", inline=False)
        embed.add_field(name="📊 統計數據", value="查看系統統計和標籤使用情況", inline=False)
        embed.add_field(name="🗑️ 刪除標籤", value="刪除不需要的標籤", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)

class MainMenuViewWithCheckinAndReply(View):
    """主選單 - 包含簽到設定和刷版區設定按鈕"""
    
    def __init__(self, guild_id: Optional[str] = None, channel_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="🏷️ 新增標籤", style=discord.ButtonStyle.primary, emoji="🏷️", custom_id="add_tag_with_checkin_reply")
    async def add_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示新增標籤模態框"""
        modal = AddTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔍 搜索標籤", style=discord.ButtonStyle.secondary, emoji="🔍", custom_id="search_tag_with_checkin_reply")
    async def search_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示搜索標籤模態框"""
        modal = SearchTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 查看標籤", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="view_tags_with_checkin_reply")
    async def view_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示所有標籤"""
        print("🔍 ===== 開始查看標籤（帶簽到和刷版區） =====")
        print(f"🔍 交互來自: {interaction.user.name} ({interaction.user.id})")
        try:
            print("🔍 正在獲取標籤...")
            tags = await tag_manager.get_available_tags()
            print(f"🔍 獲取到 {len(tags)} 個標籤")
            
            if not tags:
                print("🔍 沒有標籤，顯示提示訊息")
                embed = discord.Embed(
                    title="📋 標籤列表",
                    description="暫無可用標籤，請先新增標籤！",
                    color=discord.Color.orange()
                )
                embed.add_field(name="💡 提示", value="使用 `!menu` 點擊「🏷️ 新增標籤」來創建新標籤", inline=False)
                await interaction.response.edit_message(embed=embed)
                return
            
            # 分組顯示標籤
            tag_list = []
            for i, tag in enumerate(tags):
                print(f"🔍 標籤 {i}: name={tag.name}, emoji={tag.emoji}, emoji_type={type(tag.emoji)}")
                # 使用 display_emoji 來顯示 emoji 或圖片連結
                emoji_display = display_emoji(tag.emoji)
                print(f"🔍 emoji_display: {emoji_display}, type={type(emoji_display)}")
                tag_list.append(f"{emoji_display} **{tag.name}**")
                if tag.description:
                    tag_list[-1] += f" - {tag.description}"
                print(f"🔍 tag_list[{i}]: {tag_list[-1]}")
            
            print(f"🔍 準備發送 embed，tag_list 長度: {len(tag_list)}")
            embed = discord.Embed(
                title="📋 所有標籤",
                description="\n".join(tag_list),
                color=discord.Color.blue()
            )
            embed.add_field(name="總數", value=f"共有 {len(tags)} 個標籤", inline=True)
            
            # 添加返回按鈕
            view = BackToMenuView(guild_id=self.guild_id, channel_id=self.channel_id)
            print(f"🔍 準備編輯訊息...")
            await interaction.response.edit_message(embed=embed, view=view)
            print("🔍 ===== 查看標籤完成 =====")
            
        except Exception as e:
            print(f"❌ 查看標籤時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 查看標籤時發生錯誤: {str(e)}")
            except:
                print("❌ 無法發送錯誤訊息")
                await interaction.followup.send(f"❌ 查看標籤時發生錯誤: {str(e)}")
    
    @discord.ui.button(label="✨ 簽到設定", style=discord.ButtonStyle.success, emoji="✨", custom_id="checkin_settings_with_reply")
    async def checkin_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示簽到設置菜單"""
        guild_id = str(interaction.guild.id)
        view = CheckinSettingsView(checkin_manager, guild_id)
        embed = discord.Embed(
            title="✨ 簽到設定",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="⏰ 調整時間", value="調整每日簽到的時間界限", inline=False)
        embed.add_field(name="🖼️ 更換 GIF", value="更換簽到成功時顯示的 GIF", inline=False)
        embed.add_field(name="📊 顯示排名", value="查看簽到排行榜", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🎭 刷版區設定", style=discord.ButtonStyle.success, emoji="🎭", custom_id="reply_settings_with_checkin_reply")
    async def reply_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示刷版區設置菜單"""
        guild_id = str(interaction.guild.id)
        view = ReplySettingsView(reply_manager, guild_id)
        
        # 檢查是否已設置刷版區頻道
        config = await reply_manager.get_config(guild_id)
        
        if config:
            channel_id = config.get('channel_id')
            try:
                channel = bot.get_channel(int(channel_id))
                channel_name = channel.name if channel else f"未知頻道 ({channel_id})"
                description = f"當前刷版區頻道: **#{channel_name}**\n選擇一個操作："
            except:
                description = f"當前刷版區頻道: {channel_id}\n選擇一個操作："
        else:
            description = "尚未設置刷版區頻道\n選擇一個操作："
        
        embed = discord.Embed(
            title="🎭 刷版區設定",
            description=description,
            color=discord.Color.purple()
        )
        embed.add_field(name="⚙️ 設置頻道", value="設置當前頻道為刷版區", inline=False)
        embed.add_field(name="🖼️ 新增回覆", value="新增想要 bot 回覆的 GIF/貼圖/表情符號", inline=False)
        embed.add_field(name="📊 顯示排名", value="查看觸發回覆排行榜", inline=False)
        embed.add_field(name="🗑️ 刪除回覆", value="刪除想要 bot 回覆的 GIF/貼圖/表情符號", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📥 進階功能", style=discord.ButtonStyle.success, emoji="📥", custom_id="advanced_features_with_checkin_reply")
    async def advanced_features(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示進階功能菜單"""
        view = AdvancedFeaturesView(guild_id=self.guild_id, channel_id=self.channel_id)
        embed = discord.Embed(
            title="📥 進階功能",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="📥 導入歷史", value="導入頻道的歷史訊息並添加標籤", inline=False)
        embed.add_field(name="📊 統計數據", value="查看系統統計和標籤使用情況", inline=False)
        embed.add_field(name="🗑️ 刪除標籤", value="刪除不需要的標籤", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)

# ========== 新增標籤模態框 ==========

class AddTagModal(Modal, title='新增標籤'):
    """新增標籤的模態框"""
    
    name = TextInput(label='標籤的名字', placeholder='例如：重要', required=True)
    emoji = TextInput(
        label='象徵標籤的emoji', 
        placeholder='請先複製表情符號或表情符號的ID', 
        required=True, 
        max_length=50,
        style=discord.TextStyle.short
    )
    description = TextInput(label='說明/備註', placeholder='例如：重要知識點（可不填寫）', required=False, style=discord.TextStyle.paragraph)
    image_url = TextInput(label='圖片連結', placeholder='可選：輸入圖片連結以顯示自定義emoji', required=False, max_length=200, style=discord.TextStyle.short)
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交新增標籤"""
        print("🔍 ===== AddTagModal on_submit 被調用 =====", flush=True)
        
        try:
            tag_name = self.name.value.strip()
            tag_emoji = self.emoji.value.strip()
            tag_description = self.description.value.strip()
            tag_image_url = self.image_url.value.strip()
            
            print(f"🔍 從 Modal 獲取的原始值:", flush=True)
            print(f"   tag_name: {tag_name} (類型: {type(tag_name).__name__})", flush=True)
            print(f"   tag_emoji: {tag_emoji} (類型: {type(tag_emoji).__name__})", flush=True)
            print(f"   tag_description: {tag_description} (類型: {type(tag_description).__name__})", flush=True)
            print(f"   tag_image_url: {tag_image_url} (類型: {type(tag_image_url).__name__})", flush=True)
            
            # 標準化 emoji（如果是完整格式，提取 ID）
            normalized_emoji = normalize_emoji(tag_emoji)
            print(f"🔍 標準化後的 emoji: {normalized_emoji}", flush=True)
            
            # 驗證 emoji
            if len(normalized_emoji) == 0:
                await interaction.response.send_message("❌ Emoji 不能為空！")
                return
            
            # 檢查 emoji 是否已存在（使用標準化後的 emoji 進行比較）
            tags = await tag_manager.get_available_tags()
            for tag in tags:
                if normalize_emoji(tag.emoji) == normalized_emoji:
                    await interaction.response.send_message(f"❌ Emoji `{tag_emoji}` 已經被使用！")
                    return
            
            # 創建標籤（使用標準化後的 emoji 和圖片連結）
            print(f"🔍 準備調用 create_custom_tag:", flush=True)
            print(f"   name: {tag_name}", flush=True)
            print(f"   category: custom", flush=True)
            print(f"   emoji: {normalized_emoji}", flush=True)
            print(f"   description: {tag_description}", flush=True)
            print(f"   image_url: {tag_image_url}", flush=True)
            
            success = await tag_manager.create_custom_tag(tag_name, "custom", normalized_emoji, tag_description, tag_image_url)
            
            if success:
                # 使用 display_emoji 來顯示 emoji 或圖片連結
                emoji_display = display_emoji(normalized_emoji)
                
                embed = discord.Embed(
                    title="✅ 標籤創建成功",
                    description=f"新標籤 `{tag_name}` 已添加",
                    color=discord.Color.green()
                )
                
                # 如果有圖片連結，設置為縮略圖
                if tag_image_url:
                    embed.set_thumbnail(url=tag_image_url)
                
                embed.add_field(name="名稱", value=tag_name, inline=True)
                embed.add_field(name="Emoji", value=emoji_display, inline=True)
                if tag_description:
                    embed.add_field(name="說明", value=tag_description, inline=False)
                if tag_image_url:
                    embed.add_field(name="圖片", value=f"[查看圖片]({tag_image_url})", inline=False)
                embed.add_field(name="💡 提示", value=f"現在只要有人在訊息上添加 `{emoji_display}` emoji，就會自動加入此標籤！", inline=False)
                
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("❌ 標籤創建失敗，可能已存在")
        except Exception as e:
            print(f"❌ AddTagModal on_submit 發生錯誤: {e}", flush=True)
            import traceback
            traceback.print_exc(flush=True)
            try:
                await interaction.response.send_message(f"❌ 創建標籤時發生錯誤: {str(e)}")
            except:
                print("❌ 無法發送錯誤訊息", flush=True)
                try:
                    await interaction.followup.send(f"❌ 創建標籤時發生錯誤: {str(e)}")
                except:
                    print("❌ 無法使用 followup 發送錯誤訊息", flush=True)

# ========== 搜索標籤模態框 ==========

class SearchTagModal(Modal, title='搜索標籤'):
    """搜索標籤的模態框"""
    
    tag_name = TextInput(label='標籤的名字', placeholder='例如：重要', required=True)
    limit = TextInput(label='搜索數量', placeholder='留空則顯示所有', required=False)
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交搜索"""
        tag_name_input = self.tag_name.value.strip()
        limit_input = self.limit.value.strip()
        
        # 設置限制（Discord 最大顯示數量）
        if limit_input:
            try:
                limit = int(limit_input)
                # Discord 限制：embed 最多 6000 字符，大約 25-30 條訊息
                if limit > 25:
                    limit = 25
                elif limit < 1:
                    limit = 10
            except ValueError:
                limit = 10
        else:
            limit = 10
        
        # 標準化輸入
        normalized_input = normalize_emoji(tag_name_input)
        
        # 搜索標籤（支援標籤名稱、emoji 或 emoji ID）
        tags = await tag_manager.get_available_tags()
        found_tag = None
        for tag in tags:
            # 檢查標籤名稱
            if tag.name.lower() == tag_name_input.lower():
                found_tag = tag
                break
            # 檢查 emoji（標準化後比較）
            if normalize_emoji(tag.emoji) == normalized_input:
                found_tag = tag
                break
        
        if not found_tag:
            await interaction.response.send_message(f"❌ 找不到標籤 `{tag_name_input}`，請使用 `!menu` -> `📋 查看標籤` 查看可用標籤")
            return
        
        # 搜索帶有此標籤的訊息
        message_tags = await db.search_by_tag(found_tag.name, limit=limit)
        
        if not message_tags:
            emoji_display = display_emoji(found_tag.emoji)
            embed = discord.Embed(
                title=f"🔍 搜索結果: {emoji_display} {found_tag.name}",
                description=f"沒有找到帶有此標籤的訊息",
                color=discord.Color.orange()
            )
            embed.add_field(name="💡 提示", value=f"試試在訊息上添加 {emoji_display} emoji 來自動加入標籤！", inline=False)
            await interaction.response.send_message(embed=embed)
            return
        
        # 顯示結果
        emoji_display = display_emoji(found_tag.emoji)
        embed = discord.Embed(
            title=f"🔍 搜索結果: {emoji_display} {found_tag.name}",
            description=f"找到 {len(message_tags)} 條訊息",
            color=discord.Color.blue()
        )
        
        for i, mt in enumerate(message_tags[:limit]):
            content = mt.message_content[:100] + "..." if len(mt.message_content) > 100 else mt.message_content
            message_link = f"https://discord.com/channels/{mt.guild_id}/{mt.channel_id}/{mt.message_id}"
            embed.add_field(
                name=f"{i+1}. 訊息",
                value=f"{content}\n🕐 {mt.created_at}\n🔗 [跳轉到原訊息]({message_link})",
                inline=False
            )
        
        # 添加返回按鈕
        view = BackToMenuView(guild_id=str(interaction.guild.id), channel_id=str(interaction.channel.id))
        await interaction.response.send_message(embed=embed, view=view)

# ========== 進階功能菜單 ==========

class AdvancedFeaturesView(View):
    """進階功能菜單"""
    
    def __init__(self, guild_id: Optional[str] = None, channel_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="📥 導入歷史", style=discord.ButtonStyle.primary, emoji="📥")
    async def import_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示導入歷史視圖"""
        guild_id = str(interaction.guild.id)
        view = ImportHistoryView(guild_id)
        
        # 獲取伺服器的所有文字頻道
        text_channels = [channel for channel in interaction.guild.text_channels]
        if not text_channels:
            await interaction.response.send_message("❌ 這個伺服器沒有文字頻道！")
            return
        
        # 初始化頻道選項
        view.initialize_options(text_channels)
        
        embed = discord.Embed(
            title="📥 導入歷史",
            description="選擇一個頻道來導入歷史訊息",
            color=discord.Color.blue()
        )
        embed.add_field(name="💡 提示", value="請選擇頻道，然後輸入要導入的 emoji", inline=False)
        
        # 如果頻道數量超過 25 個，添加警告
        if len(text_channels) > 25:
            embed.add_field(
                name="⚠️ 注意", 
                value=f"伺服器共有 {len(text_channels)} 個文字頻道，但 Discord 限制最多只能顯示 25 個。如果看不到要選擇的頻道，請聯繫管理員。", 
                inline=False
            )
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📊 統計數據", style=discord.ButtonStyle.secondary, emoji="📊")
    async def show_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示統計數據"""
        try:
            stats = await tag_manager.get_statistics()
            
            embed = discord.Embed(
                title="📊 系統統計",
                color=discord.Color.purple()
            )
            embed.add_field(name="🏷️ 總標籤數", value=stats.get('total_tags', 0), inline=True)
            embed.add_field(name="📝 已標記訊息", value=stats.get('total_tagged_messages', 0), inline=True)
            embed.add_field(name="👥 活躍用戶", value=stats.get('active_users', 0), inline=True)
            
            if stats.get('top_tags'):
                top_tags_str = "\n".join([f"{i+1}. {display_emoji(tag['emoji'])} {tag['name']}: {tag['count']} 次" for i, tag in enumerate(stats['top_tags'][:5])])
                embed.add_field(name="🔥 熱門標籤", value=top_tags_str, inline=False)
            
            # 添加返回按鈕
            view = BackToMenuView(guild_id=self.guild_id, channel_id=self.channel_id)
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            print(f"查看統計錯誤: {e}")
            await interaction.response.send_message("❌ 查看統計時發生錯誤")
    
    @discord.ui.button(label="🗑️ 刪除標籤", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示刪除標籤模態框"""
        modal = DeleteTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔙 返回主菜單", style=discord.ButtonStyle.secondary)
    async def back_to_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回主菜單"""
        view = BackToMenuView(guild_id=self.guild_id, channel_id=self.channel_id)
        embed = discord.Embed(
            title="🎮 Discord 標籤系統",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="🏷️ 新增標籤", value="添加新的標籤", inline=False)
        embed.add_field(name="🔍 搜索標籤", value="搜索帶有標籤的消息", inline=False)
        embed.add_field(name="📋 查看標籤", value="查看所有可用標籤", inline=False)
        embed.add_field(name="📥 進階功能", value="導入歷史、統計等", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)

# ========== 導入歷史模態框 ==========

@discord.ui.button(label="🔙 返回", style=discord.ButtonStyle.secondary)
async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
    """返回主菜單"""
    from advanced_view import AdvancedView
    view = AdvancedView(self.guild_id)
    await interaction.response.edit_message(embed=view.get_embed(), view=view)

class ImportHistoryView(View):
    """導入歷史訊息的視圖"""
    
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self._initialized = False
    
    def initialize_options(self, text_channels):
        """初始化頻道選項"""
        if not self._initialized:
            # 獲取 Select 組件（第一個組件）
            select = self.children[0]
            # Discord Select 組件最多只能有 25 個選項
            channels_to_show = text_channels[:25]
            select.options = [
                discord.SelectOption(
                    label=channel.name,
                    value=str(channel.id),
                    description=f"頻道 ID: {channel.id}"
                )
                for channel in channels_to_show
            ]
            self._initialized = True
    
    @discord.ui.select(
        placeholder="選擇要導入的頻道",
        min_values=1,
        max_values=1,
        custom_id="channel_select"
    )
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.Select):
        """選擇頻道後顯示 emoji 輸入"""
        channel_id = select.values[0]
        
        # 顯示 emoji 輸入模態框
        modal = ImportHistoryModal(self.guild_id, channel_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔙 返回", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回進階功能菜單"""
        view = AdvancedFeaturesView()
        embed = discord.Embed(
            title="📥 進階功能",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="📥 導入歷史", value="導入頻道的歷史訊息並添加標籤", inline=False)
        embed.add_field(name="📊 統計數據", value="查看系統統計和標籤使用情況", inline=False)
        embed.add_field(name="🗑️ 刪除標籤", value="刪除不需要的標籤", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)

class ImportHistoryModal(Modal, title='導入歷史訊息'):
    """導入歷史訊息的模態框"""
    
    def __init__(self, guild_id: str, channel_id: str):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    emoji = TextInput(
        label='導入訊息的emoji', 
        placeholder='請先複製表情符號或表情符號的ID', 
        required=True, 
        max_length=50,
        style=discord.TextStyle.short
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交導入歷史"""
        emoji_input = self.emoji.value.strip()
        
        # 標準化 emoji 輸入
        normalized_emoji = normalize_emoji(emoji_input)
        
        # 驗證 emoji
        if len(normalized_emoji) == 0:
            await interaction.response.send_message("❌ Emoji 不能為空！")
            return
        
        # 查找對應的標籤（使用標準化後的 emoji 進行比較）
        tags = await tag_manager.get_available_tags()
        found_tag = None
        for tag in tags:
            if normalize_emoji(tag.emoji) == normalized_emoji:
                found_tag = tag
                break
        
        if not found_tag:
            await interaction.response.send_message(f"❌ 找不到使用 Emoji `{emoji_input}` 的標籤，請先創建標籤！")
            return
        
        # 獲取頻道
        channel = bot.get_channel(int(self.channel_id))
        if not channel:
            await interaction.response.send_message(f"❌ 找不到頻道！")
            return
        
        # 開始導入歷史
        await interaction.response.send_message(f"📥 正在導入 `{channel.name}` 頻道的歷史訊息...")
        
        # 使用 history_processor 導入歷史
        try:
            await history_processor.import_history_by_emoji(interaction, channel, found_tag)
        except Exception as e:
            print(f"導入歷史錯誤: {e}")
            await interaction.followup.send(f"❌ 導入歷史時發生錯誤: {str(e)}")

# ========== 刪除標籤模態框 ==========

class DeleteTagModal(Modal, title='刪除標籤'):
    """刪除標籤的模態框"""
    
    emoji = TextInput(
        label='要刪除標籤的emoji', 
        placeholder='請先複製表情符號或表情符號的ID', 
        required=True, 
        max_length=50,
        style=discord.TextStyle.short
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交刪除標籤"""
        emoji_input = self.emoji.value.strip()
        
        # 標準化 emoji 輸入
        normalized_emoji = normalize_emoji(emoji_input)
        
        # 查找對應的標籤（使用標準化後的 emoji 進行比較）
        tags = await tag_manager.get_available_tags()
        found_tag = None
        for tag in tags:
            if normalize_emoji(tag.emoji) == normalized_emoji:
                found_tag = tag
                break
        
        if not found_tag:
            await interaction.response.send_message(f"❌ 找不到使用 Emoji `{emoji_input}` 的標籤！")
            return
        
        # 刪除標籤
        success = await db.delete_tag(found_tag.id)
        
        if success:
            embed = discord.Embed(
                title="✅ 標籤刪除成功",
                description=f"標籤 `{found_tag.name}` 已刪除",
                color=discord.Color.green()
            )
            embed.add_field(name="名稱", value=found_tag.name, inline=True)
            embed.add_field(name="Emoji", value=found_tag.emoji, inline=True)
            
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ 標籤刪除失敗")

# ========== 命令 ==========

@bot.command(name="menu")
async def menu_command(ctx: commands.Context):
    """顯示主菜單"""
    # 檢查是否已經在執行中
    user_id = str(ctx.author.id)
    if not await acquire_command_lock("menu", user_id, timeout=1.0):
        print(f"⚠️ menu_command 已在執行中，跳過重複請求", flush=True)
        return
    
    try:
        print(f"🔍 ===== menu_command 被調用 =====", flush=True)
        print(f"🔍 用戶: {ctx.author.name} (ID: {ctx.author.id})", flush=True)
        print(f"🔵 頻道: {ctx.channel.name} (ID: {ctx.channel.id})", flush=True)
        print(f"🏰 時間: {format_taiwan_time()}", flush=True)
        
        guild_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)
        
        # 檢查是否在簽到頻道
        checkin_config = await checkin_manager.get_config(guild_id)
        is_checkin_channel = checkin_config and checkin_config['channel_id'] == channel_id
        print(f"🔍 is_checkin_channel: {is_checkin_channel}", flush=True)
        
        # 檢查是否在刷版區頻道
        reply_config = await reply_manager.get_config(guild_id)
        is_reply_channel = reply_config and reply_config.get('channel_id') == channel_id and reply_config.get('enabled')
        print(f"🔍 is_reply_channel: {is_reply_channel}", flush=True)
        
        # 根據情況選擇 View
        if is_checkin_channel and is_reply_channel:
            view = MainMenuViewWithCheckinAndReply(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuViewWithCheckinAndReply", flush=True)
        elif is_checkin_channel:
            view = MainMenuViewWithCheckin(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuViewWithCheckin", flush=True)
        elif is_reply_channel:
            view = MainMenuViewWithReply(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuViewWithReply", flush=True)
        else:
            view = MainMenuView(guild_id=guild_id, channel_id=channel_id)
            print(f"🔍 使用 MainMenuView", flush=True)
        
        embed = discord.Embed(
            title="🎮 Discord 標籤系統",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="🏷️ 新增標籤", value="添加新的標籤", inline=False)
        embed.add_field(name="🔍 搜索標籤", value="搜索帶有標籤的消息", inline=False)
        embed.add_field(name="📋 查看標籤", value="查看所有可用標籤", inline=False)
        
        if is_checkin_channel:
            embed.add_field(name="✨ 簽到設定", value="設置每日簽到功能", inline=False)
        
        if is_reply_channel:
            embed.add_field(name="🎭 刷版區設定", value="設置刷版區回覆功能", inline=False)
        
        embed.add_field(name="📥 進階功能", value="導入歷史、統計等", inline=False)
        
        print(f"🔍 準備發送 menu 訊息", flush=True)
        await ctx.send(embed=embed, view=view)
        print(f"✅ menu 訊息已發送", flush=True)
    finally:
        # 釋放鎖
        release_command_lock("menu", user_id)

@bot.command(name="status")
async def status_command(ctx: commands.Context):
    """查看 Bot 狀態"""
    stats = await tag_manager.get_statistics()
    
    embed = discord.Embed(
        title="📊 Bot 詳細狀態",
        color=discord.Color.gold()
    )
    embed.add_field(name="🤖 Bot 名稱", value=bot.user.name, inline=True)
    embed.add_field(name="🆔 實例 ID", value=INSTANCE_ID, inline=True)
    embed.add_field(name="⏰ 當前時間", value=format_taiwan_time(), inline=True)
    embed.add_field(name="🌐 服務器數量", value=len(bot.guilds), inline=True)
    embed.add_field(name="🏷️ 總標籤數", value=stats.get('total_tags', 0), inline=True)
    embed.add_field(name="📝 已標記訊息", value=stats.get('total_tagged_messages', 0), inline=True)
    embed.add_field(name="✅ 已初始化", value="是" if _initialized else "否", inline=True)
    embed.add_field(name="📦 延遲", value=f"{int(bot.latency * 1000)}ms", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="set_checkin_channel")
async def set_checkin_channel_command(ctx: commands.Context):
    """設置每日簽到頻道"""
    print(f"🔍 ===== set_checkin_channel 被調用 =====", flush=True)
    print(f"🔍 用戶: {ctx.author.name} (ID: {ctx.author.id})", flush=True)
    print(f"🔵 頻道: {ctx.channel.name} (ID: {ctx.channel.id})", flush=True)
    
    guild_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)
    
    # 設置簽到頻道
    success = await checkin_manager.set_config(guild_id, channel_id)
    
    if success:
        print(f"✅ 簽到頻道設置成功", flush=True)
        embed = discord.Embed(
            title="✅ 簽到頻道設置成功",
            description=f"每日簽到功能已在 **{ctx.channel.name}** 頻道啟用！",
            color=discord.Color.green()
        )
        embed.add_field(name="📌 當前頻道", value=ctx.channel.name, inline=False)
        embed.add_field(name="🆔 頻道 ID", value=channel_id, inline=False)
        embed.add_field(name="💡 提示", value="使用 `!menu` 查看主菜單，現在應該會顯示「✨ 簽到設定」選項", inline=False)
        await ctx.send(embed=embed)
    else:
        print(f"❌ 簽到頻道設置失敗", flush=True)
        await ctx.send("❌ 設置失敗，請稍後再試")

@bot.command(name="check_config")
async def check_config_command(ctx: commands.Context):
    """檢查簽到配置"""
    print(f"🔍 ===== check_config 被調用 =====", flush=True)
    print(f"🔍 用戶: {ctx.author.name} (ID: {ctx.author.id})", flush=True)
    print(f"🔵 頻道: {ctx.channel.name} (ID: {ctx.channel.id})", flush=True)
    
    guild_id = str(ctx.guild.id)
    config = await checkin_manager.get_config(guild_id)
    
    print(f"🔍 查詢結果: {config}", flush=True)
    
    if config:
        embed = discord.Embed(
            title="📋 簽到配置",
            color=discord.Color.green()
        )
        embed.add_field(name="✅ 已配置", value="是", inline=True)
        embed.add_field(name="📌 簽到頻道 ID", value=config.get('channel_id', '未知'), inline=False)
        embed.add_field(name="⏰ 簽到時間", value=config.get('checkin_time', '00:00'), inline=True)
        embed.add_field(name="🖼️ GIF 連結", value=config.get('gif_url', '無')[:50] + '...' if config.get('gif_url') else '無', inline=False)
        embed.add_field(name="📅 創建時間", value=config.get('created_at', '未知'), inline=True)
        embed.add_field(name="🔄 更新時間", value=config.get('updated_at', '未知'), inline=True)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ 簽到配置",
            description="此伺服器還沒有設置簽到系統！",
            color=discord.Color.red()
        )
        embed.add_field(name="💡 提示", value="請使用 `!set_checkin_channel` 在簽到頻道中設置", inline=False)
        await ctx.send(embed=embed)

@bot.command(name="debug_tags")
async def debug_tags_command(ctx: commands.Context):
    """調試標籤 - 直接查看數據庫中的標籤"""
    print("🔍 ===== debug_tags 命令被調用 =====")
    try:
        # 直接查詢 D1 數據庫
        if db.use_d1:
            print("🔍 使用 D1 模式，直接查詢原始數據...")
            sql = "SELECT * FROM tags ORDER BY id"
            result = await db._execute_d1(sql)
            print(f"🔍 D1 原始返回: {result}")
            
            if not result or len(result) == 0:
                await ctx.send("❌ 數據庫中沒有標籤")
                return
            
            # 解析原始數據
            raw_tags = []
            for row in result:
                if "results" in row:
                    for r in row["results"]:
                        raw_tags.append(r)
            
            print(f"🔍 解析到 {len(raw_tags)} 個標籤的原始數據")
            
            # 發送原始數據
            msg = f"📊 數據庫中的原始標籤數據 ({len(raw_tags)} 個):\n\n"
            for i, tag in enumerate(raw_tags):
                msg += f"**{i+1}. 標籤 ID: {tag.get('id')}**\n"
                msg += f"   原始數據: {tag}\n"
                msg += f"   Name: {tag.get('name')} (類型: {type(tag.get('name')).__name__})\n"
                msg += f"   Emoji: {tag.get('emoji')} (類型: {type(tag.get('emoji')).__name__})\n"
                msg += f"   Category: {tag.get('category')} (類型: {type(tag.get('category')).__name__})\n"
                msg += f"   Description: {tag.get('description')} (類型: {type(tag.get('description')).__name__})\n"
                msg += f"   Image URL: {tag.get('image_url')} (類型: {type(tag.get('image_url')).__name__})\n"
                msg += f"   Created At: {tag.get('created_at')}\n"
                msg += f"   Color: {tag.get('color')} (類型: {type(tag.get('color')).__name__})\n\n"
        else:
            print("🔍 使用 SQLite 模式...")
            tags = await db.get_all_tags()
            print(f"🔍 從數據庫獲取到 {len(tags)} 個標籤")
            
            if not tags:
                await ctx.send("❌ 數據庫中沒有標籤")
                return
            
            # 發送詳細的標籤信息
            msg = f"📊 數據庫中的標籤 ({len(tags)} 個):\n\n"
            for i, tag in enumerate(tags):
                msg += f"**{i+1}. {tag.name}**\n"
                msg += f"   ID: {tag.id}\n"
                msg += f"   Emoji: {tag.emoji} (類型: {type(tag.emoji).__name__})\n"
                msg += f"   Category: {tag.category}\n"
                msg += f"   Description: {tag.description or '無'}\n"
                msg += f"   Image URL: {tag.image_url or '無'}\n"
                msg += f"   Created At: {tag.created_at}\n"
                msg += f"   Color: {tag.color}\n\n"
        
        # Discord 限制訊息長度為 2000 字符
        if len(msg) > 2000:
            msg = msg[:1950] + "\n...（訊息太長，已截斷）"
        
        await ctx.send(msg)
    except Exception as e:
        print(f"❌ debug_tags 錯誤: {e}")
        import traceback
        traceback.print_exc()
        await ctx.send(f"❌ 調試失敗: {str(e)}")

@bot.command(name="create_test_tag")
async def create_test_tag_command(ctx: commands.Context, name: str = "測試標籤", emoji: str = "🏷️"):
    """創建測試標籤
    用法: !create_test_tag [名稱] [emoji]
    範例: !create_test_tag 測試 🏷️
    """
    print(f"🔍 ===== create_test_tag 命令被調用 =====")
    print(f"🔍 參數: name={name}, emoji={emoji}")
    try:
        # 標準化 emoji
        normalized_emoji = normalize_emoji(emoji)
        print(f"🔍 標準化後的 emoji: {normalized_emoji}")
        
        # 創建標籤
        success = await tag_manager.create_custom_tag(name, "custom", normalized_emoji, "測試標籤", "")
        
        if success:
            await ctx.send(f"✅ 測試標籤 `{name}` 創建成功！")
            print(f"✅ 測試標籤創建成功")
        else:
            await ctx.send(f"❌ 測試標籤 `{name}` 創建失敗")
            print(f"❌ 測試標籤創建失敗")
    except Exception as e:
        print(f"❌ create_test_tag 錯誤: {e}")
        import traceback
        traceback.print_exc()
        await ctx.send(f"❌ 創建測試標籤時發生錯誤: {str(e)}")

@bot.command(name="test")
async def test_command(ctx: commands.Context):
    """測試命令"""
    print("🔍 ===== test_command 被調用 =====")
    print(f"🔍 用戶: {ctx.author.name} ({ctx.author.id})")
    await ctx.send("✅ 測試成功（新版本 v3.0）")
    print("✅ test_command 完成")

@bot.command(name="rebuild_d1_tables")
async def rebuild_d1_tables_command(ctx: commands.Context):
    """重建 D1 數據庫表結構"""
    if not USE_D1:
        await ctx.send("❌ 當前不使用 D1 數據庫")
        return
    
    await ctx.send("⚠️ 即將刪除並重建 D1 表結構，這會刪除所有數據！")
    await ctx.send("⚠️ 請確認是否繼續？輸入 `!confirm_rebuild` 確認")

@bot.command(name="confirm_rebuild")
async def confirm_rebuild_command(ctx: commands.Context):
    """確認重建 D1 數據庫表結構"""
    if not USE_D1:
        await ctx.send("❌ 當前不使用 D1 數據庫")
        return
    
    try:
        # 刪除現有表
        await db._execute_d1('DROP TABLE IF EXISTS message_tags')
        await db._execute_d1('DROP TABLE IF EXISTS tags')
        
        # 創建 tags 表
        await db._execute_d1('''
            CREATE TABLE tags (
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
        
        # 創建 message_tags 表
        await db._execute_d1('''
            CREATE TABLE message_tags (
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
        
        # 創建索引
        await db._execute_d1('CREATE INDEX IF NOT EXISTS idx_message_tags_message ON message_tags(message_id)')
        await db._execute_d1('CREATE INDEX IF NOT EXISTS idx_message_tags_tag ON message_tags(tag_id)')
        await db._execute_d1('CREATE INDEX IF NOT EXISTS idx_message_tags_guild ON message_tags(guild_id)')
        await db._execute_d1('CREATE INDEX IF NOT EXISTS idx_message_tags_content ON message_tags(message_content)')
        
        await ctx.send("✅ D1 表結構重建成功！")
        await ctx.send("💡 現在可以創建新標籤了")
    except Exception as e:
        await ctx.send(f"❌ 重建失敗: {str(e)}")
        import traceback
        traceback.print_exc(flush=True)

@bot.command(name="ping")
async def ping_command(ctx: commands.Context):
    """Ping 命令 - 測試 bot 是否正常工作"""
    print("🔍 ===== ping_command 被調用 =====")
    print(f"🔍 用戶: {ctx.author.name} ({ctx.author.id})")
    print(f"🔍 Bot 延遲: {int(bot.latency * 1000)}ms")
    await ctx.send(f"🏓 Pong! 延遲: {int(bot.latency * 1000)}ms")
    print("✅ ping_command 完成")

@bot.command(name="check_instances")
async def check_instances_command(ctx: commands.Context):
    """檢查實例數量 - 用於診斷重複訊息問題"""
    print(f"🔍 ===== check_instances_command 被調用 =====", flush=True)
    print(f"🔍 當前實例 ID: {INSTANCE_ID}", flush=True)
    print(f"🔍 Bot 用戶名: {bot.user.name}", flush=True)
    print(f"🔍 服務器數量: {len(bot.guilds)}", flush=True)
    print(f"🔍 連接狀態: {bot.ws.status if hasattr(bot.ws, 'status') else 'unknown'}", flush=True)
    print(f"🔍 延遲: {int(bot.latency * 1000)}ms", flush=True)
    print(f"🔍 當前時間: {format_taiwan_time()}", flush=True)
    
    embed = discord.Embed(
        title="🔍 實例診斷信息",
        description=f"實例 ID: {INSTANCE_ID}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Bot 用戶名", value=bot.user.name, inline=True)
    embed.add_field(name="服務器數量", value=len(bot.guilds), inline=True)
    embed.add_field(name="延遲", value=f"{int(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="連接狀態", value=str(bot.ws.status) if hasattr(bot.ws, 'status') else 'unknown', inline=True)
    embed.add_field(name="當前時間", value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), inline=True)
    embed.add_field(name="💡 提示", value="如果看到多個實例發送訊息，可能有多個 bot 實例在運行", inline=False)
    
    await ctx.send(embed=embed)
    print("✅ check_instances_command 完成", flush=True)

@bot.command(name="force_delete_all_tags")
async def force_delete_all_tags_command(ctx: commands.Context):
    """強制刪除所有標籤"""
    try:
        # 創建確認視圖
        view = ConfirmDeleteAllTagsView()
        embed = discord.Embed(
            title="⚠️ 危險操作",
            description="這將刪除所有標籤和相關的消息標籤！\n\n此操作無法撤銷，請確認！",
            color=discord.Color.red()
        )
        embed.add_field(name="⚠️ 警告", value="所有標籤和關聯的標籤記錄將被永久刪除", inline=False)
        
        await ctx.send(embed=embed, view=view)
    except Exception as e:
        print(f"刪除標籤時發生錯誤: {e}")
        await ctx.send("❌ 刪除標籤時發生錯誤")

class ConfirmDeleteAllTagsView(View):
    """確認刪除所有標籤視圖"""
    
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.button(label="✅ 確認刪除", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """確認刪除"""
        try:
            success = await db.delete_all_tags()
            if success:
                embed = discord.Embed(
                    title="✅ 刪除成功",
                    description="所有標籤和相關的標籤記錄已刪除",
                    color=discord.Color.green()
                )
                embed.add_field(name="📝 統計", value="已清除所有數據", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                embed = discord.Embed(
                    title="❌ 刪除失敗",
                    description="刪除過程中發生錯誤",
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            print(f"刪除標籤時發生錯誤: {e}")
            embed = discord.Embed(
                title="❌ 錯誤",
                description=f"刪除時發生錯誤: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """取消刪除"""
        embed = discord.Embed(
            title="❌ 已取消",
            description="刪除操作已取消",
            color=discord.Color.grey()
        )
        await interaction.response.edit_message(embed=embed, view=None)

# ========== 簽到系統命令 ==========

@bot.command(name="setcheckin")
async def set_checkin_command(ctx: commands.Context, time: str = "00:00", gif_url: str = ""):
    """設置簽到系統
    用法: !setcheckin [時間] [GIF連結]
    時間格式: HH:MM (例如: 00:00)
    """
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ 只有管理員可以設置簽到系統")
        return
    
    # 驗證時間格式
    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        await ctx.send("❌ 時間格式錯誤！請使用 HH:MM 格式（例如: 00:00）")
        return
    
    # 設置配置
    success = await checkin_manager.set_config(
        str(ctx.guild.id),
        str(ctx.channel.id),
        time,
        gif_url
    )
    
    if success:
        embed = discord.Embed(
            title="✅ 簽到系統已設置",
            description=f"簽到系統已在此頻道設置",
            color=discord.Color.green()
        )
        embed.add_field(name="簽到頻道", value=f"<#{ctx.channel.id}>", inline=True)
        embed.add_field(name="簽到時間", value=time, inline=True)
        if gif_url:
            embed.set_image(url=gif_url)
            embed.add_field(name="簽到 GIF", value="已設置", inline=True)
        embed.add_field(name="注意", value="每天會在設定的時間自動發送簽到訊息", inline=False)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ 設置失敗")

@bot.command(name="checkin")
async def checkin_command(ctx: commands.Context):
    """手動發送簽到訊息（測試用）"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ 只有管理員可以手動發送簽到訊息")
        return
    
    config = await checkin_manager.get_config(str(ctx.guild.id))
    if not config:
        await ctx.send("❌ 還沒有設置簽到系統！請使用 `!setcheckin` 設置")
        return
    
    # 發送簽到訊息
    view = CheckinView(checkin_manager, config['gif_url'])
    embed = discord.Embed(
        title="✨ 每日簽到",
        description="點擊下方按鈕進行簽到！",
        color=discord.Color.gold()
    )
    
    if config['gif_url']:
        embed.set_image(url=config['gif_url'])
    
    message = await ctx.send(embed=embed, view=view)
    
    # 釘選訊息
    await message.pin()

@bot.command(name="trigger_checkin")
async def trigger_checkin_command(ctx: commands.Context):
    """手動觸發簽到訊息（測試用，僅管理員）"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ 只有管理員可以使用此命令")
        return
    
    print(f"🔍 ===== trigger_checkin 被調用 =====", flush=True)
    print(f"🔍 用戶: {ctx.author.name} (ID: {ctx.author.id})", flush=True)
    print(f"🔵 頻道: {ctx.channel.name} (ID: {ctx.channel.id})", flush=True)
    
    guild_id = str(ctx.guild.id)
    config = await checkin_manager.get_config(guild_id)
    
    if not config:
        await ctx.send("❌ 還沒有設置簽到系統！請使用 `!set_checkin_channel` 設置")
        return
    
    print(f"🔍 簽到配置: {config}", flush=True)
    
    # 發送簽到訊息
    view = CheckinView(checkin_manager, config['gif_url'])
    embed = discord.Embed(
        title="✨ 每日簽到（測試）",
        description=f"這是手動觸發的簽到訊息！",
        color=discord.Color.gold()
    )
    
    if config['gif_url']:
        embed.set_image(url=config['gif_url'])
    
    message = await ctx.send(embed=embed, view=view)
    print(f"✅ 測試簽到訊息已發送", flush=True)
    
    # 釘選訊息
    await message.pin()
    print(f"✅ 測試訊息已釘選", flush=True)
    
    await ctx.send("✅ 測試簽到訊息已發送！")

@bot.command(name="leaderboard")
async def leaderboard_command(ctx: commands.Context):
    """顯示簽到排行榜"""
    view = LeaderboardView(checkin_manager, str(ctx.guild.id))
    embed = discord.Embed(
        title="📊 簽到排行榜",
        description="請選擇排行榜類型",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed, view=view)

# ========== 運行 Bot ==========

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ 錯誤: 未找到 DISCORD_BOT_TOKEN 環境變量")
        print("請創建 .env 文件並設置 DISCORD_BOT_TOKEN")
        exit(1)
    
    # 啟動 HTTP 服務器（為了滿足 Render 的端口檢查）
    import http.server
    import socketserver
    from threading import Thread
    
    PORT = int(os.getenv("PORT", 8080))
    
    class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Discord Tag System Bot is running!")
        
        def log_message(self, format, *args):
            pass  # 抑制默認的日誌輸出

# ========== 刷版區回覆系統 View ==========

class ReplySettingsView(View):
    """刷版區設置視圖"""
    def __init__(self, reply_manager: ReplyManager, guild_id: str):
        super().__init__(timeout=None)
        self.reply_manager = reply_manager
        self.guild_id = guild_id
    
    @discord.ui.button(label="⚙️ 設置頻道", style=discord.ButtonStyle.primary)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """設置刷版區頻道"""
        print(f"🔍 ===== set_channel 被調用 =====", flush=True)
        print(f"🔍 用戶: {interaction.user.name} (ID: {interaction.user.id})", flush=True)
        print(f"🔵 頻道: {interaction.channel.name} (ID: {interaction.channel.id})", flush=True)
        
        # 獲取當前頻道作為刷版區頻道
        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)
        
        print(f"🔍 準備設置配置: guild_id={guild_id}, channel_id={channel_id}", flush=True)
        
        success = await self.reply_manager.set_config(guild_id, channel_id, enabled=True)
        
        print(f"🔍 set_config 返回: {success}", flush=True)
        
        if success:
            embed = discord.Embed(
                title="✅ 刷版區頻道已設置",
                description=f"此頻道 (`#{interaction.channel.name}`) 已設置為刷版區",
                color=discord.Color.green()
            )
            embed.add_field(name="功能說明", value="在此頻道中發送設定的 GIF/貼圖/表情符號時，bot 會隨機回覆", inline=False)
            embed.add_field(name="新增回覆", value="使用「🖼️ 新增回覆」來添加觸發器", inline=False)
            
            # 不使用 ephemeral，讓用戶能看到訊息
            await interaction.response.send_message(embed=embed)
            print(f"✅ 設置成功訊息已發送", flush=True)
        else:
            await interaction.response.send_message("❌ 設置刷版區頻道失敗！")
            print(f"❌ 設置失敗訊息已發送", flush=True)
    
    @discord.ui.button(label="🖼️ 新增回覆", style=discord.ButtonStyle.secondary)
    async def add_reply(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 顯示確認對話框
        embed = discord.Embed(
            title="📤 發送新的回覆",
            description="你確定要新增回覆嗎？",
            color=discord.Color.blue()
        )
        view = AddReplyConfirmationView(self.reply_manager, self.guild_id, str(interaction.channel.id))
        await interaction.response.send_message(embed=embed, view=view)
    
    @discord.ui.button(label="📊 回覆排名", style=discord.ButtonStyle.secondary)
    async def show_reply_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 顯示回覆排名（GIF/貼圖/表情符號使用次數）
        stats = await self.reply_manager.get_usage_stats(self.guild_id)
        
        if not stats:
            embed = discord.Embed(
                title="📊 回覆觸發排行榜",
                description="暫無回覆數據",
                color=discord.Color.orange()
            )
            embed.add_field(name="💡 提示", value="先使用「🖼️ 新增回覆」來添加一些回覆！", inline=False)
        else:
            embed = discord.Embed(
                title="📊 回覆觸發排行榜",
                description=f"共有 {len(stats)} 個回覆",
                color=discord.Color.purple()
            )
            
            for i, stat in enumerate(stats[:10]):
                trigger_type = stat['trigger_type']
                trigger_id = stat['trigger_id']
                trigger_url = stat.get('trigger_url', '')
                usage_count = stat['usage_count']
                
                if trigger_type == 'gif' and trigger_url:
                    trigger_display = f"[GIF]({trigger_url})"
                elif trigger_type == 'sticker' and trigger_url:
                    trigger_display = f"[貼圖]({trigger_url})"
                else:
                    trigger_display = f"{trigger_type}:{trigger_id[-8:]}"
                
                embed.add_field(
                    name=f"#{i+1} {trigger_display}",
                    value=f"觸發次數: {usage_count}",
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.ui.button(label="👤 用戶排名", style=discord.ButtonStyle.secondary)
    async def show_user_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 顯示用戶排名（用戶觸發bot回覆次數）
        stats = await self.reply_manager.get_user_trigger_stats(self.guild_id)
        
        if not stats:
            embed = discord.Embed(
                title="👤 用戶觸發排行榜",
                description="暫無用戶數據",
                color=discord.Color.orange()
            )
            embed.add_field(name="💡 提示", value="用戶還沒有觸發過回覆！", inline=False)
        else:
            embed = discord.Embed(
                title="👤 用戶觸發排行榜",
                description=f"共有 {len(stats)} 位用戶",
                color=discord.Color.purple()
            )
            
            description = ""
            for i, stat in enumerate(stats[:10]):
                user_id = stat['user_id']
                trigger_count = stat['trigger_count']
                medal = ""
                if i == 0:
                    medal = "🥇"
                elif i == 1:
                    medal = "🥈"
                elif i == 2:
                    medal = "🥉"
                else:
                    medal = f"{i+1}."
                
                description += f"{medal} <@{user_id}>: {trigger_count} 次\n"
            
            embed.description = description
        
        await interaction.response.send_message(embed=embed)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.ui.button(label="🗑️ 刪除回覆", style=discord.ButtonStyle.secondary)
    async def delete_reply(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 顯示確認對話框
        embed = discord.Embed(
            title="🗑️ 刪除回覆",
            description="你確定要刪除回覆嗎？",
            color=discord.Color.red()
        )
        view = DeleteReplyConfirmationView(self.reply_manager, self.guild_id, str(interaction.channel.id))
        await interaction.response.send_message(embed=embed, view=view)
    
    @discord.ui.button(label="🔙 返回", style=discord.ButtonStyle.secondary)
    async def back_to_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        from main import BackToMenuView
        view = BackToMenuView(guild_id=self.guild_id, channel_id=str(interaction.channel.id))
        embed = discord.Embed(
            title="🎮 Discord 標籤系統",
            description="選擇一個操作：",
            color=discord.Color.gold()
        )
        embed.add_field(name="🏷️ 新增標籤", value="添加新的標籤", inline=False)
        embed.add_field(name="🔍 搜索標籤", value="搜索帶有標籤的消息", inline=False)
        embed.add_field(name="📋 查看標籤", value="查看所有可用標籤", inline=False)
        embed.add_field(name="📥 進階功能", value="導入歷史、統計等", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)

class AddReplyConfirmationView(View):
    """新增回覆確認視圖"""
    def __init__(self, reply_manager: ReplyManager, guild_id: str, channel_id: str):
        super().__init__(timeout=60)
        self.reply_manager = reply_manager
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="✅ 確定", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"🔍 ===== AddReplyConfirmationView.confirm 被調用 =====", flush=True)
        print(f"🔍 用戶 ID: {interaction.user.id}", flush=True)
        print(f"🔍 頻道 ID: {interaction.channel.id}", flush=True)
        print(f"🔍 Guild ID: {self.guild_id}", flush=True)
        
        # 使用資料庫存儲新增回覆請求
        try:
            success = await self.reply_manager.set_add_request(
                user_id=str(interaction.user.id),
                channel_id=str(interaction.channel.id),
                guild_id=self.guild_id,
                timeout_seconds=120  # 2分鐘過期
            )
            
            if success:
                print(f"✅ 新增回覆請求已保存到資料庫", flush=True)
            else:
                print(f"❌ 保存新增回覆請求失敗", flush=True)
        except Exception as e:
            print(f"❌ 保存新增回覆請求時發生錯誤: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        # 讓用戶發送 GIF/貼圖
        embed = discord.Embed(
            title="📤 發送新的回覆",
            description="請在此訊息下方發送新的 GIF/貼圖/表情符號",
            color=discord.Color.blue()
        )
        embed.add_field(name="發送方式", value="你可以使用以下任一方式：", inline=False)
        embed.add_field(name="1. GIF 連結", value="直接發送 GIF 連結", inline=False)
        embed.add_field(name="2. GIF ID", value="只發送 GIF ID", inline=False)
        embed.add_field(name="3. 上傳 GIF", value="直接上傳 GIF 圖片", inline=False)
        embed.add_field(name="4. Discord 貼圖", value="直接發送 Discord 貼圖", inline=False)
        embed.add_field(name="5. 表情符號", value="直接發送自定義表情符號", inline=False)
        embed.add_field(name="⏰ 有效時間", value="2 分鐘", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=None)
        print(f"✅ 用戶已被告知發送 GIF/貼圖", flush=True)
    
    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="已取消新增回覆", embed=None, view=None)

class DeleteReplyConfirmationView(View):
    """刪除回覆確認視圖"""
    def __init__(self, reply_manager: ReplyManager, guild_id: str, channel_id: str):
        super().__init__(timeout=60)
        self.reply_manager = reply_manager
        self.guild_id = guild_id
        self.channel_id = channel_id
    
    @discord.ui.button(label="✅ 確定", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"🔍 ===== DeleteReplyConfirmationView.confirm 被調用 =====", flush=True)
        print(f"🔍 用戶 ID: {interaction.user.id}", flush=True)
        print(f"🔍 頻道 ID: {interaction.channel.id}", flush=True)
        print(f"🔍 Guild ID: {self.guild_id}", flush=True)
        
        # 使用資料庫存儲刪除回覆請求
        try:
            success = await self.reply_manager.set_delete_request(
                user_id=str(interaction.user.id),
                channel_id=str(interaction.channel.id),
                guild_id=self.guild_id,
                timeout_seconds=120  # 2分鐘過期
            )
            
            if success:
                print(f"✅ 刪除回覆請求已保存到資料庫", flush=True)
            else:
                print(f"❌ 保存刪除回覆請求失敗", flush=True)
        except Exception as e:
            print(f"❌ 保存刪除回覆請求時發生錯誤: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        # 讓用戶發送要刪除的 GIF/貼圖
        embed = discord.Embed(
            title="🗑️ 刪除回覆",
            description="請在此訊息下方發送要刪除的 GIF/貼圖/表情符號",
            color=discord.Color.red()
        )
        embed.add_field(name="發送方式", value="你可以使用以下任一方式：", inline=False)
        embed.add_field(name="1. GIF 連結", value="直接發送要刪除的 GIF 連結", inline=False)
        embed.add_field(name="2. GIF ID", value="只發送要刪除的 GIF ID", inline=False)
        embed.add_field(name="3. Discord 貼圖", value="直接發送要刪除的 Discord 貼圖", inline=False)
        embed.add_field(name="4. 表情符號", value="直接發送要刪除的自定義表情符號", inline=False)
        embed.add_field(name="⏰ 有效時間", value="2 分鐘", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=None)
        print(f"✅ 用戶已被告知發送要刪除的 GIF/貼圖", flush=True)
    
    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="已取消刪除回覆", embed=None, view=None)

# ========== HTTP 健康檢查服務器 ==========

if __name__ == "__main__":
    # 在單獨的線程中運行 HTTP 服務器
    def start_http_server():
        with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
            print(f"🌐 HTTP 服務器已啟動，監聽端口 {PORT}")
            httpd.serve_forever()
    
    http_thread = Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # 等待 HTTP 服務器完全啟動
    import time
    time.sleep(2)
    
    # 啟動 Bot
    print("🚀 正在啟動 Discord 標籤系統 Bot...")
    print("🤖 啟動 Discord Bot...")
    bot.run(token)
