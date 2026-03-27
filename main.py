import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime
from dotenv import load_dotenv
import os
import json
from typing import Optional, List
import uuid

from database import Database
from tag_manager import TagManager
from message_handler import MessageHandler
from history_processor import HistoryProcessor
from emoji_utils import compare_emoji, normalize_emoji, is_custom_emoji, display_emoji, set_embed_emoji

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

# 初始化數據庫和管理器
db = Database(os.getenv("DATABASE_PATH", "discord_tags.db"))
tag_manager = TagManager(db)
message_handler = None
history_processor = None

# 命令鎖 - 防止重複執行
_command_locks = {}

# 初始化標誌
_initialized = False

# ========== Emoji 偵測邏輯 ==========

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
                
                # 移除標籤
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

@bot.event
async def on_ready():
    """Bot 啟動時執行"""
    print(f"✅ [{INSTANCE_ID}] {bot.user.name} 已啟動!")
    print(f"✅ 服務器: {len(bot.guilds)}")
    print(f"✅ 前綴: {config.get('prefix', '!')}")
    
    # 初始化數據庫
    await db.init_db()
    print("✅ 數據庫初始化完成")
    
    # 不初始化默認標籤，讓用戶自己創建
    print("✅ 標籤系統就緒（無預設標籤）")
    
    # 初始化處理器
    global message_handler, history_processor
    message_handler = MessageHandler(bot, db, tag_manager)
    history_processor = HistoryProcessor(bot, db, tag_manager)
    
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
    """主選單 - 四個主要按鈕"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🏷️ 新增標籤", style=discord.ButtonStyle.primary, emoji="🏷️")
    async def add_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示新增標籤模態框"""
        modal = AddTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔍 搜索標籤", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def search_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示搜索標籤模態框"""
        modal = SearchTagModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 查看標籤", style=discord.ButtonStyle.secondary, emoji="📋")
    async def view_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        """顯示所有標籤"""
        try:
            tags = await tag_manager.get_available_tags()
            
            if not tags:
                embed = discord.Embed(
                    title="📋 標籤列表",
                    description="暫無可用標籤，請先新增標籤！",
                    color=discord.Color.orange()
                )
                embed.add_field(name="💡 提示", value="使用 `!menu` 點擊「🏷️ 新增標籤」來創建新標籤", inline=False)
                await interaction.response.send_message(embed=embed)
                return
            
            # 分組顯示標籤
            tag_list = []
            for i, tag in enumerate(tags):
                # 使用 display_emoji 來顯示 emoji 或圖片連結
                emoji_display = display_emoji(tag.emoji)
                tag_list.append(f"{emoji_display} **{tag.name}**")
                if tag.description:
                    tag_list[-1] += f" - {tag.description}"
            
            embed = discord.Embed(
                title="📋 所有標籤",
                description="\n".join(tag_list),
                color=discord.Color.blue()
            )
            embed.add_field(name="總數", value=f"共有 {len(tags)} 個標籤", inline=True)
            
            # 添加返回按鈕
            view = BackToMenuView()
            await interaction.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            print(f"查看標籤錯誤: {e}")
            await interaction.response.send_message("❌ 查看標籤時發生錯誤")
    
    @discord.ui.button(label="📥 進階功能", style=discord.ButtonStyle.success, emoji="📥")
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
                embed.set_thumbnail(tag_image_url)
            
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
        """顯示導入歷史模態框"""
        modal = ImportHistoryModal()
        await interaction.response.send_modal(modal)
    
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

class ImportHistoryModal(Modal, title='導入歷史訊息'):
    """導入歷史訊息的模態框"""
    
    emoji = TextInput(
        label='導入訊息的emoji', 
        placeholder='請先複製表情符號或表情符號的ID', 
        required=True, 
        max_length=50,
        style=discord.TextStyle.short
    )
    channel_name = TextInput(label='頻道名稱', placeholder='例如：general', required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        """提交導入歷史"""
        emoji_input = self.emoji.value.strip()
        channel_name_input = self.channel_name.value.strip()
        
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
        
        # 查找頻道
        channel = discord.utils.get(interaction.guild.text_channels, name=channel_name_input)
        if not channel:
            await interaction.response.send_message(f"❌ 找不到頻道 `{channel_name_input}`！")
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

@bot.command(name="test")
async def test_command(ctx: commands.Context):
    """測試命令"""
    await ctx.send("✅ 測試成功（新版本 v3.0）")

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
