import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import json
from typing import Optional

from database import Database
from tag_manager import TagManager
from message_handler import MessageHandler
from history_processor import HistoryProcessor

# 加載環境變量
load_dotenv()

# 獲取配置
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# Bot 配置
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

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

@bot.event
async def on_ready():
    """Bot 啟動時執行"""
    print(f"✅ {bot.user.name} 已啟動!")
    print(f"✅ 服務器: {len(bot.guilds)}")
    
    # 初始化數據庫
    await db.init_db()
    print("✅ 數據庫初始化完成")
    
    # 初始化默認標籤
    await tag_manager.initialize_tags()
    print("✅ 默認標籤初始化完成")
    
    # 初始化處理器
    global message_handler, history_processor
    message_handler = MessageHandler(bot, db, tag_manager)
    history_processor = HistoryProcessor(bot, db, tag_manager)
    
    # 同步slash命令
    try:
        # 等待Bot完全连接
        import asyncio
        await asyncio.sleep(3)
        
        # 检查命令是否已注册
        commands = bot.tree.get_commands()
        print(f"📊 已注册的命令数量: {len(commands)}")
        for cmd in commands:
            print(f"   - {cmd.name}: {cmd.description}")
        
        server_id = os.getenv("DISCORD_SERVER_ID")
        if server_id:
            print(f"🔄 尝试服务器级别同步到 {server_id}...")
            
            # 检查服务器是否存在
            guild = bot.get_guild(int(server_id))
            if guild:
                print(f"✅ 找到服务器: {guild.name}")
            else:
                print(f"⚠️  警告: 找不到服务器 ID {server_id}")
                print(f"📋 Bot所在的服务器列表:")
                for g in bot.guilds:
                    print(f"   - {g.name} (ID: {g.id})")
            
            # 先尝试服务器级别同步
            try:
                synced = await bot.tree.sync(guild=discord.Object(id=int(server_id)))
                print(f"✅ 服务器级别同步: 已同步 {len(synced)} 個slash命令")
                
                # 如果同步返回0个命令，说明有问题，尝试全局同步
                if len(synced) == 0:
                    print(f"⚠️  服务器级别同步返回0个命令，尝试全局同步...")
                    synced = await bot.tree.sync()
                    print(f"✅ 全局同步: 已同步 {len(synced)} 個slash命令")
            except Exception as e:
                print(f"❌ 服务器级别同步失败: {e}")
                print("🔄 尝试全局同步...")
                synced = await bot.tree.sync()
                print(f"✅ 全局同步: 已同步 {len(synced)} 個slash命令")
        else:
            print("🔄 正在同步全局slash命令...")
            synced = await bot.tree.sync()
            print(f"✅ 已同步 {len(synced)} 個全局slash命令")
    except Exception as e:
        print(f"❌ 同步slash命令失敗: {e}")
        import traceback
        traceback.print_exc()
    
    # 設置狀態
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="使用 /menu 查看菜單"
        )
    )

@bot.event
async def on_guild_join(guild):
    """Bot 加入新服務器時執行"""
    print(f"🎉 加入新服務器: {guild.name}")
    
    # 發送歡迎消息
    if guild.system_channel:
        embed = discord.Embed(
            title="🎉 歡迎使用 Discord 標籤系統!",
            description=f"我是 {bot.user.name}，可以幫助你管理和搜索服務器消息標籤。",
            color=discord.Color.green()
        )
        embed.add_field(name="開始使用", value="使用 `/menu` 查看交互式菜單", inline=False)

        try:
            await guild.system_channel.send(embed=embed)
        except:
            pass

# ========== 標籤管理命令 ==========

# 標籤名稱自動補全
async def tag_name_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    """為 tag_name 參數提供自動補全"""
    try:
        tags = await tag_manager.get_available_tags()
        
        # 過濾符合當前輸入的標籤
        filtered_tags = [
            app_commands.Choice(name=f"{tag.emoji} {tag.name}", value=tag.name)
            for tag in tags
            if current.lower() in tag.name.lower() or current == ""
        ]
        
        # 最多返回25個選項（Discord限制）
        return filtered_tags[:25]
    except Exception as e:
        print(f"標籤自動補全錯誤: {e}")
        return []

@bot.tree.command(name="tag", description="為消息添加標籤")
@app_commands.describe(
    message_link="要添加標籤的消息鏈接",
    tag_name="標籤名稱（從下拉菜單選擇或輸入）"
)
@app_commands.autocomplete(tag_name=tag_name_autocomplete)
async def tag(interaction: discord.Interaction, message_link: str, tag_name: str):
    """為消息添加標籤"""
    await message_handler.handle_tag_command(interaction, message_link, tag_name)

@bot.tree.command(name="tags", description="列出所有可用標籤")
@app_commands.describe(
    category="標籤分類（可選）"
)
@app_commands.choices(category=[
    app_commands.Choice(name="全部", value="all"),
    app_commands.Choice(name="知識庫", value="knowledge"),
    app_commands.Choice(name="項目", value="project"),
    app_commands.Choice(name="審核", value="moderation"),
    app_commands.Choice(name="分析", value="analytics")
])
async def tags(interaction: discord.Interaction, category: Optional[str] = None):
    """列出所有可用標籤"""
    if category == "all":
        category = None
    await message_handler.handle_show_tags_command(interaction, category)

@bot.tree.command(name="search", description="搜索帶有標籤的消息")
@app_commands.describe(
    tag_name="要搜索的標籤名稱（從下拉菜單選擇或輸入）",
    limit="顯示結果數量（默認10，最多50）"
)
@app_commands.autocomplete(tag_name=tag_name_autocomplete)
async def search(interaction: discord.Interaction, tag_name: str, limit: int = 10):
    """搜索帶有標籤的消息"""
    if limit > 50:
        limit = 50
    await message_handler.handle_search_command(interaction, tag_name, limit)

@bot.tree.command(name="untag", description="移除消息標籤")
@app_commands.describe(
    message_link="要移除標籤的消息鏈接",
    tag_name="標籤名稱（從下拉菜單選擇或輸入）"
)
@app_commands.autocomplete(tag_name=tag_name_autocomplete)
async def untag(interaction: discord.Interaction, message_link: str, tag_name: str):
    """移除消息標籤"""
    await message_handler.handle_untag_command(interaction, message_link, tag_name)

@bot.tree.command(name="stats", description="查看標籤統計信息")
async def stats(interaction: discord.Interaction):
    """查看標籤統計信息"""
    await message_handler.handle_stats_command(interaction)

# ========== 管理員命令 ==========

@bot.tree.command(name="addtag", description="創建新標籤（管理員）")
@app_commands.describe(
    name="標籤名稱",
    category="標籤分類",
    emoji="標籤Emoji（默認🏷️）",
    description="標籤描述（可選）"
)
@app_commands.choices(category=[
    app_commands.Choice(name="知識庫", value="knowledge"),
    app_commands.Choice(name="項目", value="project"),
    app_commands.Choice(name="審核", value="moderation"),
    app_commands.Choice(name="分析", value="analytics")
])
async def addtag(interaction: discord.Interaction, name: str, category: str, emoji: str = "🏷️", description: str = ""):
    """創建新標籤（管理員）"""
    # 检查管理员权限
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 你沒有權限使用此命令（需要管理員權限）", ephemeral=True)
        return
    
    success = await tag_manager.create_custom_tag(name, category, emoji, description)
    
    if success:
        embed = discord.Embed(
            title="✅ 標籤創建成功",
            description=f"新標籤 `{name}` 已添加",
            color=discord.Color.green()
        )
        embed.add_field(name="名稱", value=name, inline=True)
        embed.add_field(name="分類", value=category, inline=True)
        embed.add_field(name="Emoji", value=emoji, inline=True)
        if description:
            embed.add_field(name="描述", value=description, inline=False)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ 標籤創建失敗，可能已存在", ephemeral=True)

@bot.tree.command(name="deltag", description="刪除標籤（管理員）")
@app_commands.describe(
    tag_name="要刪除的標籤名稱（從下拉菜單選擇或輸入）"
)
@app_commands.autocomplete(tag_name=tag_name_autocomplete)
async def deltag(interaction: discord.Interaction, tag_name: str):
    """刪除標籤（管理員）"""
    # 检查管理员权限
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 你沒有權限使用此命令（需要管理員權限）", ephemeral=True)
        return
    
    # 检查标签是否存在
    tag = await tag_manager.get_tag_info(tag_name)
    if not tag:
        await interaction.response.send_message(f"❌ 標籤 `{tag_name}` 不存在", ephemeral=True)
        return
    
    # 删除标签
    success = await db.delete_tag(tag.id)
    
    if success:
        embed = discord.Embed(
            title="✅ 標籤刪除成功",
            description=f"標籤 `{tag_name}` 已刪除",
            color=discord.Color.green()
        )
        embed.add_field(name="名稱", value=tag.name, inline=True)
        embed.add_field(name="分類", value=tag.category, inline=True)
        embed.add_field(name="Emoji", value=tag.emoji, inline=True)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ 標籤刪除失敗", ephemeral=True)

# ========== 歷史消息處理命令 ==========

@bot.tree.command(name="import", description="導入頻道歷史消息並添加標籤")
@app_commands.describe(
    channel="要導入的頻道",
    tag_name="標籤名稱（從下拉菜單選擇或輸入）",
    limit="導入數量（默認100，最多1000）",
    keywords="關鍵字過濾（可選，多個關鍵字用空格分隔）"
)
@app_commands.autocomplete(tag_name=tag_name_autocomplete)
async def import_history(interaction: discord.Interaction, channel: discord.TextChannel, tag_name: str, limit: int = 100, keywords: str = ""):
    """導入頻道歷史消息並添加標籤"""
    if limit > 1000:
        await interaction.response.send_message("❌ 限制最多 1000 條消息", ephemeral=True)
        return
    
    keyword_list = keywords.split() if keywords else None
    await history_processor.process_channel_history(interaction, channel, tag_name, limit, keyword_list)

# ========== 輔助命令 ==========

@bot.tree.command(name="menu", description="打開交互式菜單")
async def menu(interaction: discord.Interaction):
    """顯示交互式菜單"""
    # 创建一个带按钮的视图
    class MainMenuView(discord.ui.View):
        def __init__(self):
            super().__init__()

        @discord.ui.button(label="🏷️ 添加標籤", style=discord.ButtonStyle.primary)
        async def add_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("使用 `/tag` 命令為消息添加標籤\n格式: `/tag [消息鏈接] [標籤名稱]`", ephemeral=True)

        @discord.ui.button(label="🔍 搜索標籤", style=discord.ButtonStyle.secondary)
        async def search_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("使用 `/search` 命令搜索帶有標籤的消息\n格式: `/search [標籤名稱]`", ephemeral=True)

        @discord.ui.button(label="📋 查看所有標籤", style=discord.ButtonStyle.secondary)
        async def list_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("使用 `/tags` 命令查看所有可用標籤", ephemeral=True)

        @discord.ui.button(label="📥 進階功能", style=discord.ButtonStyle.success)
        async def advanced(self, interaction: discord.Interaction, button: discord.ui.Button):
            """顯示進階功能說明"""
            embed = discord.Embed(
                title="📥 進階功能",
                description="以下是可用的進階命令：",
                color=discord.Color.gold()
            )
            
            embed.add_field(
                name="🏷️ 標籤管理",
                value="""
                `/untag [消息鏈接] [標籤名稱]` - 移除消息標籤
                `/addtag [名稱] [分類] [Emoji] [描述]` - 創建新標籤（管理員）
                `/deltag [標籤名稱]` - 刪除標籤（管理員）
                """,
                inline=False
            )
            
            embed.add_field(
                name="📊 統計與分析",
                value="""
                `/stats` - 查看標籤統計信息
                """,
                inline=False
            )
            
            embed.add_field(
                name="📥 歷史消息導入",
                value="""
                `/import [頻道] [標籤] [數量] [關鍵字]` - 導入頻道歷史消息
                """,
                inline=False
            )
            
            embed.add_field(
                name="💡 使用提示",
                value="""
                • 所有命令都支持自動補全
                • 右鍵點擊消息可以複製消息鏈接
                • 管理員功能需要管理員權限
                """,
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

    embed = discord.Embed(
        title="🎮 Discord 標籤系統",
        description="選擇一個操作：",
        color=discord.Color.gold()
    )
    embed.add_field(name="🏷️ 添加標籤", value="為消息添加標籤", inline=False)
    embed.add_field(name="🔍 搜索標籤", value="搜索帶有標籤的消息", inline=False)
    embed.add_field(name="📋 查看標籤", value="查看所有可用標籤", inline=False)
    embed.add_field(name="📥 進階功能", value="導入歷史、統計等", inline=False)

    view = MainMenuView()
    await interaction.response.send_message(embed=embed, view=view)



# 錯誤處理
@bot.event
async def on_command_error(ctx: commands.Context, error):
    """處理prefix命令錯誤（保留兼容性）"""
    command_name = ctx.command.name if ctx.command else "Unknown"
    
    # 嘗試獲取原始錯誤
    original_error = error
    if hasattr(error, 'original'):
        original_error = error.original
    
    # 檢查是否是數據庫錯誤
    if "no such table" in str(original_error).lower():
        await ctx.send("❌ 數據庫錯誤：請使用 `/update_tags` 更新數據庫")
        return
    
    # 如果是權限錯誤
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ 你沒有權限使用此命令")
        return
    
    # 如果是缺少參數
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ 缺少必需參數: {error.param.name}")
        return
    
    # 如果是參數格式錯誤
    if isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ 參數格式錯誤: {str(error)}")
        return
    
    # 顯示一般錯誤
    error_type = type(original_error).__name__
    error_msg = str(original_error)
    
    if len(error_msg) > 100:
        error_msg = error_msg[:100] + "..."
    
    await ctx.send(f"❌ 執行命令時發生錯誤\n錯誤類型: {error_type}\n詳細訊息: {error_msg}")

@bot.event
async def on_message(message):
    """處理消息（保留prefix命令兼容性）"""
    await bot.process_commands(message)

if __name__ == "__main__":
    # 檢查是否有 Bot Token
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ 錯誤: 未找到 DISCORD_BOT_TOKEN 環境變量")
        print("請創建 .env 文件並設置 DISCORD_BOT_TOKEN")
        exit(1)
    
    # 啟動 Bot
    print("🚀 正在啟動 Discord 標籤系統 Bot...")
    print("🤖 啟動 Discord Bot...")
    
    # Render 需要服务监听端口
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class QuietHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is running!')
        def log_message(self, format, *args):
            pass
    
    def run_server():
        port = int(os.getenv('PORT', 10000))
        server = HTTPServer(('', port), QuietHandler)
        print(f'🌐 HTTP server running on port {port}')
        server.serve_forever()
    
    # 启动 HTTP 服务器在后台
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    bot.run(token)