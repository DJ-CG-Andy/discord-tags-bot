import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime
from dotenv import load_dotenv
import os
import json
from typing import Optional, List
import uuid
import asyncio

# 根據環境變量選擇數據庫類型
USE_D1 = os.getenv("USE_D1", "false").lower() == "true"

if USE_D1:
    from database_d1 import Database
    print("🌐 使用 Cloudflare D1 數據庫")
else:
    from database import Database
    print("💾 使用本地 SQLite 數據庫")

from tag_manager import TagManager
from message_handler import MessageHandler
from history_processor import HistoryProcessor
from emoji_utils import compare_emoji, normalize_emoji, is_custom_emoji, display_emoji, set_embed_emoji
from checkin_manager import CheckinManager
from checkin_system import CheckinView, CheckinSettingsView, GifConfirmationView

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

# 初始化簽到 GIF 等待狀態
bot._waiting_for_gif = None

# 初始化數據庫和管理器
db = Database(os.getenv("DATABASE_PATH", "discord_tags.db"), use_d1=USE_D1)
tag_manager = TagManager(db)
message_handler = None
history_processor = None
checkin_manager = CheckinManager(os.getenv("DATABASE_PATH", "discord_tags.db"), use_d1=USE_D1)

# 命令鎖 - 防止重複執行
_command_locks = {}

# 初始化標誌
_initialized = False

# 簽到系統標誌
_checkin_initialized = False

# ========== Emoji 偵測邏輯 ==========

@bot.event
async def on_message(message: discord.Message):
    """處理訊息（用於處理簽到 GIF 更換）"""
    # 忽略 bot 的訊息
    if message.author.bot:
        return
    
    # 處理簽到 GIF 更換
    # 檢查是否正在等待用戶發送 GIF
    if hasattr(bot, '_waiting_for_gif') and bot._waiting_for_gif:
        user_id = str(message.author.id)
        channel_id = str(message.channel.id)
        
        if bot._waiting_for_gif.get('user_id') == user_id and bot._waiting_for_gif.get('channel_id') == channel_id:
            # 提取 GIF 連結
            gif_url = None
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.content_type and 'image' in attachment.content_type:
                        gif_url = attachment.url
                        break
            
            if not gif_url:
                # 檢查訊息內容是否包含連結
                if message.content:
                    import re
                    urls = re.findall(r'(https?://\S+)', message.content)
                    if urls:
                        gif_url = urls[0]
            
            if gif_url:
                # 更新配置
                guild_id = bot._waiting_for_gif.get('guild_id')
                await checkin_manager.set_config(
                    guild_id,
                    channel_id,
                    bot._waiting_for_gif.get('checkin_time'),
                    gif_url
                )
                
                embed = discord.Embed(
                    title="✅ GIF 已更新",
                    description=f"簽到 GIF 已設置",
                    color=discord.Color.green()
                )
                embed.set_image(url=gif_url)
                embed.add_field(name="預覽", value="這就是新的簽到 GIF", inline=False)
                
                await message.reply(embed=embed)
            else:
                await message.reply("❌ 未檢測到有效的 GIF！請重新發送。")
            
            # 清除等待狀態
            bot._waiting_for_gif = None
            return
    
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
                        timestamp=datetime.now()
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
                        timestamp=datetime.now()
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
    
    while not bot.is_closed():
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_date = now.strftime("%Y-%m-%d")
            
            # 檢查所有服務器的簽到配置
            for guild in bot.guilds:
                guild_id = str(guild.id)
                config = await checkin_manager.get_config(guild_id)
                
                if config and config['checkin_time'] == current_time:
                    # 發送簽到訊息
                    channel = bot.get_channel(int(config['channel_id']))
                    if channel:
                        view = CheckinView(checkin_manager, config['gif_url'])
                        embed = discord.Embed(
                            title="✨ 每日簽到",
                            description=f"今天是 {current_date}，點擊下方按鈕進行簽到！",
                            color=discord.Color.gold()
                        )
                        
                        if config['gif_url']:
                            embed.set_image(url=config['gif_url'])
                        
                        message = await channel.send(embed=embed, view=view)
                        
                        # 釘選訊息
                        await message.pin()
                        
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
            
            # 每分鐘檢查一次
            await asyncio.sleep(60)
            
        except Exception as e:
            print(f"簽到定時任務錯誤: {e}")
            await asyncio.sleep(60)

@bot.event
async def on_ready():
    """Bot 啟動時執行"""
    print(f"✅ [{INSTANCE_ID}] {bot.user.name} 已啟動!")
    print(f"✅ 服務器: {len(bot.guilds)}")
    print(f"✅ 前綴: {config.get('prefix', '!')}")
    
    # 初始化數據庫
    await db.init_db()
    print("✅ 數據庫初始化完成")
    
    # 初始化簽到系統表
    await checkin_manager.init_tables()
    print("✅ 簽到系統初始化完成")
    
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
            view = BackToMenuView()
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

class BackToMenuView(View):
    """返回主菜單按鈕"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🔙 返回主菜單", style=discord.ButtonStyle.secondary)
    async def back_to_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """返回主菜單"""
        view = MainMenuView()
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
            view = BackToMenuView()
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
        tag_name = self.name.value.strip()
        tag_emoji = self.emoji.value.strip()
        tag_description = self.description.value.strip()
        tag_image_url = self.image_url.value.strip()
        
        # 標準化 emoji（如果是完整格式，提取 ID）
        normalized_emoji = normalize_emoji(tag_emoji)
        
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
            embed.add_field(
                name=f"{i+1}. 訊息 (ID: {mt.message_id[-8:]})",
                value=f"{content}\n🕐 {mt.created_at}",
                inline=False
            )
        
        # 添加返回按鈕
        view = BackToMenuView()
        await interaction.response.send_message(embed=embed, view=view)

# ========== 進階功能菜單 ==========

class AdvancedFeaturesView(View):
    """進階功能菜單"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
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
            view = BackToMenuView()
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
        view = MainMenuView()
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
            # 獲取 Select 組件
            select = self.children[0]
            select.options = [
                discord.SelectOption(
                    label=channel.name,
                    value=str(channel.id),
                    description=f"頻道 ID: {channel.id}"
                )
                for channel in text_channels
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
    guild_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)
    
    # 檢查是否在簽到頻道
    config = await checkin_manager.get_config(guild_id)
    is_checkin_channel = config and config['channel_id'] == channel_id
    
    # 根據情況選擇 View
    if is_checkin_channel:
        view = MainMenuViewWithCheckin(guild_id=guild_id, channel_id=channel_id)
    else:
        view = MainMenuView(guild_id=guild_id, channel_id=channel_id)
    
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
    
    embed.add_field(name="📥 進階功能", value="導入歷史、統計等", inline=False)
    
    await ctx.send(embed=embed, view=view)

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
    embed.add_field(name="⏰ 當前時間", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    embed.add_field(name="🌐 服務器數量", value=len(bot.guilds), inline=True)
    embed.add_field(name="🏷️ 總標籤數", value=stats.get('total_tags', 0), inline=True)
    embed.add_field(name="📝 已標記訊息", value=stats.get('total_tagged_messages', 0), inline=True)
    embed.add_field(name="✅ 已初始化", value="是" if _initialized else "否", inline=True)
    embed.add_field(name="📦 延遲", value=f"{int(bot.latency * 1000)}ms", inline=True)
    
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
    await ctx.send("✅ 測試成功（新版本 v3.0）")

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
            # 禁用 HTTP 服務器的日誌輸出
            pass
    
    # 在單獨的線程中運行 HTTP 服務器
    def start_http_server():
        with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
            print(f"🌐 HTTP 服務器已啟動，監聽端口 {PORT}")
            httpd.serve_forever()
    
    http_thread = Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # 啟動 Bot
    print("🚀 正在啟動 Discord 標籤系統 Bot...")
    print("🤖 啟動 Discord Bot...")
    bot.run(token)
