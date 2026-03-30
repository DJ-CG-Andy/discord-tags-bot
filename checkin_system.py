"""
每日簽到系統 UI 和邏輯
"""

import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select
from datetime import datetime, timedelta
from typing import Optional
from checkin_manager import CheckinManager

class CheckinButton(discord.ui.Button):
    """簽到按鈕"""
    def __init__(self, checkin_manager: CheckinManager, gif_url: str):
        super().__init__(style=discord.ButtonStyle.primary, label="✨ 簽到", emoji="✨")
        self.checkin_manager = checkin_manager
        self.gif_url = gif_url
    
    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        
        print(f"🔍 簽到按鈕被點擊 - 用戶: {user_id}", flush=True)
        
        # 執行簽到
        success, total, streak = await self.checkin_manager.checkin(user_id, guild_id)
        
        if success:
            # 簽到成功
            embed = discord.Embed(
                title="✨ 簽到成功！",
                description=f"恭喜 <@{user_id}> 簽到成功！",
                color=discord.Color.green()
            )
            
            # 顯示 GIF（如果有設置）
            if self.gif_url:
                embed.set_image(url=self.gif_url)
            
            embed.add_field(name="總簽到次數", value=f"📊 {total} 次", inline=True)
            embed.add_field(name="連續簽到", value=f"🔥 {streak} 天", inline=True)
            embed.set_footer(text=f"簽到時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            await interaction.response.send_message(embed=embed)
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
            embed.add_field(name="明天再來", value="明天 00:00 後可以再次簽到", inline=False)
            
            await interaction.response.send_message(embed=embed)
            print(f"✅ 已簽到回復已發送", flush=True)

class CheckinView(View):
    """簽到視圖"""
    def __init__(self, checkin_manager: CheckinManager, gif_url: str = ""):
        super().__init__(timeout=None)
        self.checkin_manager = checkin_manager
        self.gif_url = gif_url
        self.add_item(CheckinButton(checkin_manager, gif_url))

class CheckinConfigModal(Modal, title="調整簽到時間"):
    """調整簽到時間模態框"""
    time_input = TextInput(label="簽到時間 (HH:MM)", placeholder="例如: 00:00", required=True, max_length=5)
    
    def __init__(self, checkin_manager: CheckinManager, guild_id: str):
        super().__init__()
        self.checkin_manager = checkin_manager
        self.guild_id = guild_id
    
    async def on_submit(self, interaction: discord.Interaction):
        time_str = self.time_input.value.strip()
        
        # 驗證時間格式
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await interaction.response.send_message("❌ 時間格式錯誤！請使用 HH:MM 格式（例如: 00:00）")
            return
        
        # 獲取當前配置
        config = await self.checkin_manager.get_config(self.guild_id)
        if not config:
            await interaction.response.send_message("❌ 還沒有設置簽到配置！請先設置頻道和 GIF。")
            return
        
        # 更新配置
        await self.checkin_manager.set_config(
            self.guild_id, 
            config['channel_id'], 
            time_str, 
            config['gif_url']
        )
        
        embed = discord.Embed(
            title="✅ 簽到時間已更新",
            description=f"每日簽到時間已設為 `{time_str}`",
            color=discord.Color.green()
        )
        embed.add_field(name="生效時間", value="明天開始生效", inline=False)
        
        await interaction.response.send_message(embed=embed)

class SetGifModal(Modal, title="設置簽到 GIF"):
    """設置簽到 GIF 模態框"""
    gif_url = TextInput(label="GIF 連結", placeholder="輸入 GIF 連結", required=True, style=discord.TextStyle.paragraph)
    
    def __init__(self, checkin_manager: CheckinManager, guild_id: str):
        super().__init__()
        self.checkin_manager = checkin_manager
        self.guild_id = guild_id
    
    async def on_submit(self, interaction: discord.Interaction):
        gif_url = self.gif_url.value.strip()
        
        # 獲取當前配置
        config = await self.checkin_manager.get_config(self.guild_id)
        if not config:
            await interaction.response.send_message("❌ 還沒有設置簽到配置！請先設置頻道。")
            return
        
        # 更新配置
        await self.checkin_manager.set_config(
            self.guild_id, 
            config['channel_id'], 
            config['checkin_time'], 
            gif_url
        )
        
        embed = discord.Embed(
            title="✅ GIF 已更新",
            description=f"簽到 GIF 已設置",
            color=discord.Color.green()
        )
        embed.set_image(url=gif_url)
        embed.add_field(name="預覽", value="這就是新的簽到 GIF", inline=False)
        
        await interaction.response.send_message(embed=embed)

class LeaderboardSelect(Select):
    """排行榜選擇器"""
    def __init__(self, checkin_manager: CheckinManager, guild_id: str):
        options = [
            discord.SelectOption(
                label="總簽到次數排行榜",
                value="total",
                description="查看總簽到次數最多的用戶",
                emoji="📊"
            ),
            discord.SelectOption(
                label="連續簽到排行榜",
                value="streak",
                description="查看連續簽到天數最長的用戶",
                emoji="🔥"
            )
        ]
        super().__init__(placeholder="選擇排行榜類型", options=options, min_values=1, max_values=1)
        self.checkin_manager = checkin_manager
        self.guild_id = guild_id
    
    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        by_streak = (choice == "streak")
        
        leaderboard = await self.checkin_manager.get_leaderboard(self.guild_id, limit=10, by_streak=by_streak)
        
        if not leaderboard:
            embed = discord.Embed(
                title="📊 簽到排行榜",
                description="暫無簽到記錄",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 構建排行榜消息
        title = "🔥 連續簽到排行榜" if by_streak else "📊 總簽到次數排行榜"
        embed = discord.Embed(
            title=title,
            color=discord.Color.gold()
        )
        
        description = ""
        current_rank = 1
        last_value = None
        
        for idx, entry in enumerate(leaderboard, 1):
            user_id = entry["user_id"]
            value = entry["value"]
            
            # 計算排名（同次數同排名）
            if idx == 1:
                current_rank = 1
            elif value != last_value:
                current_rank = idx
            
            last_value = value
            
            medal = ""
            if current_rank == 1:
                medal = "🥇"
            elif current_rank == 2:
                medal = "🥈"
            elif current_rank == 3:
                medal = "🥉"
            else:
                medal = f"{current_rank}."
            
            description += f"{medal} <@{user_id}>: {value}\n"
        
        embed.description = description
        embed.set_footer(text=f"更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await interaction.response.send_message(embed=embed)

class LeaderboardView(View):
    """排行榜視圖"""
    def __init__(self, checkin_manager: CheckinManager, guild_id: str):
        super().__init__(timeout=None)
        self.add_item(LeaderboardSelect(checkin_manager, guild_id))

class CheckinSettingsView(View):
    """簽到設置視圖"""
    def __init__(self, checkin_manager: CheckinManager, guild_id: str):
        super().__init__(timeout=None)
        self.checkin_manager = checkin_manager
        self.guild_id = guild_id
    
    @discord.ui.button(label="⏰ 調整時間", style=discord.ButtonStyle.secondary)
    async def adjust_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CheckinConfigModal(self.checkin_manager, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🖼️ 更換 GIF", style=discord.ButtonStyle.secondary)
    async def change_gif(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 顯示確認對話框
        embed = discord.Embed(
            title="⚠️ 確認更換 GIF",
            description="你確定要更換簽到 GIF 嗎？",
            color=discord.Color.orange()
        )
        
        # 獲取當前配置
        config = await self.checkin_manager.get_config(self.guild_id)
        if config:
            view = GifConfirmationView(self.checkin_manager, self.guild_id, str(interaction.channel.id), config['checkin_time'])
        else:
            view = GifConfirmationView(self.checkin_manager, self.guild_id, str(interaction.channel.id), "00:00")
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @discord.ui.button(label="📊 顯示排名", style=discord.ButtonStyle.secondary)
    async def show_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LeaderboardView(self.checkin_manager, self.guild_id)
        embed = discord.Embed(
            title="📊 簽到排行榜",
            description="請選擇排行榜類型",
            color=discord.Color.gold()
        )
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

class GifConfirmationView(View):
    """GIF 確認視圖"""
    def __init__(self, checkin_manager: CheckinManager, guild_id: str, channel_id: str, checkin_time: str):
        super().__init__(timeout=60)
        self.checkin_manager = checkin_manager
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.checkin_time = checkin_time
    
    @discord.ui.button(label="✅ 確定", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"🔍 ===== GifConfirmationView.confirm 被調用 =====", flush=True)
        print(f"🔍 用戶 ID: {interaction.user.id}", flush=True)
        print(f"🔍 頻道 ID: {interaction.channel.id}", flush=True)
        print(f"🔍 Guild ID: {self.guild_id}", flush=True)
        print(f"🔍 Checkin Time: {self.checkin_time}", flush=True)
        
        # 使用資料庫存儲 GIF 更換請求（避免多實例問題）
        try:
            success = await self.checkin_manager.set_gif_change_request(
                user_id=str(interaction.user.id),
                channel_id=str(interaction.channel.id),
                guild_id=self.guild_id,
                checkin_time=self.checkin_time,
                timeout_seconds=120  # 2分鐘過期
            )
            
            if success:
                print(f"✅ GIF 更換請求已保存到資料庫", flush=True)
            else:
                print(f"❌ 保存 GIF 更換請求失敗", flush=True)
        except Exception as e:
            print(f"❌ 保存 GIF 更換請求時發生錯誤: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        # 讓用戶發送 GIF
        embed = discord.Embed(
            title="📤 發送新的 GIF",
            description="請在此訊息下方發送新的 GIF 連結或圖片",
            color=discord.Color.blue()
        )
        embed.add_field(name="提示", value="你可以直接發送 GIF 連結，或者上傳圖片", inline=False)
        embed.add_field(name="⏰ 有效時間", value="2 分鐘", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=None)
        print(f"✅ 用戶已被告知發送 GIF", flush=True)
    
    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="已取消更換 GIF", embed=None, view=None)
