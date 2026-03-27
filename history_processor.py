import discord
from discord.ext import commands
from datetime import datetime, timedelta
from typing import List, Optional, Union
import asyncio
from database import Database
from tag_manager import TagManager
from emoji_utils import compare_emoji, normalize_emoji

class HistoryProcessor:
    def __init__(self, bot: commands.Bot, db: Database, tag_manager: TagManager):
        self.bot = bot
        self.db = db
        self.tag_manager = tag_manager

    # ========== 辅助方法：统一处理 Context 和 Interaction ==========

    async def _send(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], *args, **kwargs):
        """发送消息的统一方法"""
        if isinstance(ctx_or_interaction, discord.Interaction):
            # 对于 Interaction，使用 followup.send
            return await ctx_or_interaction.followup.send(*args, **kwargs)
        else:
            # 对于 Context，使用 send
            return await ctx_or_interaction.send(*args, **kwargs)

    async def _defer_if_needed(self, ctx_or_interaction: Union[commands.Context, discord.Interaction]):
        """如果是 Interaction，则调用 defer"""
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.defer()
    
    async def process_channel_history(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], channel: discord.TextChannel,
                                     tag_name: str, limit: int = 100,
                                     keywords: Optional[List[str]] = None,
                                     after: Optional[datetime] = None):
        """處理頻道歷史訊息並自動添加標籤"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            # 檢查標籤是否存在
            tag = await self.tag_manager.get_tag_info(tag_name)
            if not tag:
                await self._send(ctx_or_interaction, f"❌ 標籤 `{tag_name}` 不存在。")
                return

            await self._send(ctx_or_interaction, f"🔄 開始處理頻道 `{channel.name}` 的歷史訊息...")

            # 設置搜索參數
            kwargs = {"limit": limit}
            if after:
                kwargs["after"] = after

            # 獲取訊息
            messages = []
            async for message in channel.history(**kwargs):
                # 跳過系統訊息和機器人訊息
                if message.author.bot or message.type != discord.MessageType.default:
                    continue

                # 如果有關鍵字，檢查是否包含
                if keywords:
                    content_lower = message.content.lower()
                    if not any(keyword.lower() in content_lower for keyword in keywords):
                        continue

                messages.append(message)

            if not messages:
                await self._send(ctx_or_interaction, f"❌ 沒有找到符合條件的訊息。")
                return

            # 處理訊息
            success_count = 0
            skip_count = 0
            error_count = 0

            # 获取作者 ID
            author_id = ctx_or_interaction.user.id if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author.id

            for message in messages:
                try:
                    # 檢查訊息是否已有該標籤
                    existing_tags = await self.db.get_message_tags(str(message.id))
                    if any(mt.tag_id == tag.id for mt in existing_tags):
                        skip_count += 1
                        continue

                    # 添加標籤
                    created_at = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    success = await self.db.tag_message(
                        message_id=str(message.id),
                        channel_id=str(message.channel.id),
                        guild_id=str(message.guild.id),
                        tag_id=tag.id,
                        tagged_by=str(author_id),
                        message_content=message.content,
                        author_id=str(message.author.id),
                        created_at=created_at
                    )

                    if success:
                        success_count += 1

                    # 避免觸發速率限制
                    await asyncio.sleep(0.5)

                except Exception as e:
                    error_count += 1
                    print(f"處理訊息 {message.id} 時出錯: {e}")

            # 發送結果
            embed = discord.Embed(
                title=f"{tag.emoji} 歷史訊息處理完成",
                description=f"頻道 `{channel.name}` 的處理結果",
                color=tag.color,
                timestamp=datetime.now()
            )

            embed.add_field(name="成功添加", value=success_count, inline=True)
            embed.add_field(name="已跳過", value=skip_count, inline=True)
            embed.add_field(name="錯誤", value=error_count, inline=True)
            embed.add_field(name="總計", value=len(messages), inline=True)

            if keywords:
                embed.add_field(name="關鍵字", value=", ".join(keywords), inline=False)

            if after:
                embed.add_field(name="時間範圍", value=f"{after.strftime('%Y-%m-%d')} 之後", inline=False)

            await self._send(ctx_or_interaction, embed=embed)

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 處理歷史訊息時發生錯誤: {str(e)}")
    
    async def process_multiple_channels(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], channels: List[discord.TextChannel],
                                       tag_name: str, limit: int = 100,
                                       keywords: Optional[List[str]] = None,
                                       after: Optional[datetime] = None):
        """處理多個頻道的歷史訊息"""
        # 如果是 Interaction，先调用 defer
        await self._defer_if_needed(ctx_or_interaction)

        # 获取作者 ID
        author_id = ctx_or_interaction.user.id if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author.id

        total_success = 0
        total_skip = 0
        total_error = 0

        for channel in channels:
            try:
                await self._send(ctx_or_interaction, f"🔄 正在處理頻道 `{channel.name}`...")

                # 檢查標籤是否存在
                tag = await self.tag_manager.get_tag_info(tag_name)
                if not tag:
                    await self._send(ctx_or_interaction, f"❌ 標籤 `{tag_name}` 不存在。")
                    continue

                # 設置搜索參數
                kwargs = {"limit": limit}
                if after:
                    kwargs["after"] = after

                # 獲取訊息
                messages = []
                async for message in channel.history(**kwargs):
                    if message.author.bot or message.type != discord.MessageType.default:
                        continue

                    if keywords:
                        content_lower = message.content.lower()
                        if not any(keyword.lower() in content_lower for keyword in keywords):
                            continue

                    messages.append(message)

                # 處理訊息
                for message in messages:
                    try:
                        existing_tags = await self.db.get_message_tags(str(message.id))
                        if any(mt.tag_id == tag.id for mt in existing_tags):
                            total_skip += 1
                            continue

                        created_at = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                        success = await self.db.tag_message(
                            message_id=str(message.id),
                            channel_id=str(message.channel.id),
                            guild_id=str(message.guild.id),
                            tag_id=tag.id,
                            tagged_by=str(author_id),
                            message_content=message.content,
                            author_id=str(message.author.id),
                            created_at=created_at
                        )

                        if success:
                            total_success += 1

                        await asyncio.sleep(0.5)

                    except Exception as e:
                        total_error += 1
                        print(f"處理訊息 {message.id} 時出錯: {e}")

                await self._send(ctx_or_interaction, f"✅ 頻道 `{channel.name}` 處理完成")
                await asyncio.sleep(1)

            except Exception as e:
                await self._send(ctx_or_interaction, f"❌ 處理頻道 `{channel.name}` 時發生錯誤: {str(e)}")

        # 發送總結果
        embed = discord.Embed(
            title="📊 批量處理完成",
            description=f"所有頻道的處理結果",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        embed.add_field(name="總成功", value=total_success, inline=True)
        embed.add_field(name="總跳過", value=total_skip, inline=True)
        embed.add_field(name="總錯誤", value=total_error, inline=True)
        embed.add_field(name="處理頻道數", value=len(channels), inline=True)

        await self._send(ctx_or_interaction, embed=embed)
    
    async def process_by_date_range(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], channel: discord.TextChannel,
                                   tag_name: str, start_date: datetime, end_date: datetime,
                                   keywords: Optional[List[str]] = None):
        """按日期範圍處理訊息"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            # 获取作者 ID
            author_id = ctx_or_interaction.user.id if isinstance(ctx_or_interaction, discord.Interaction) else ctx_or_interaction.author.id

            await self._send(ctx_or_interaction, f"🔄 正在搜索 `{start_date.date()}` 到 `{end_date.date()}` 之間的訊息...")

            # 檢查標籤是否存在
            tag = await self.tag_manager.get_tag_info(tag_name)
            if not tag:
                await self._send(ctx_or_interaction, f"❌ 標籤 `{tag_name}` 不存在。")
                return

            # 獲取訊息
            messages = []
            async for message in channel.history(limit=None, after=start_date, before=end_date):
                if message.author.bot or message.type != discord.MessageType.default:
                    continue

                if keywords:
                    content_lower = message.content.lower()
                    if not any(keyword.lower() in content_lower for keyword in keywords):
                        continue

                messages.append(message)

            if not messages:
                await self._send(ctx_or_interaction, f"❌ 在指定日期範圍內沒有找到符合條件的訊息。")
                return

            # 處理訊息
            success_count = 0
            skip_count = 0
            error_count = 0

            for message in messages:
                try:
                    existing_tags = await self.db.get_message_tags(str(message.id))
                    if any(mt.tag_id == tag.id for mt in existing_tags):
                        skip_count += 1
                        continue

                    created_at = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    success = await self.db.tag_message(
                        message_id=str(message.id),
                        channel_id=str(message.channel.id),
                        guild_id=str(message.guild.id),
                        tag_id=tag.id,
                        tagged_by=str(author_id),
                        message_content=message.content,
                        author_id=str(message.author.id),
                        created_at=created_at
                    )

                    if success:
                        success_count += 1

                    await asyncio.sleep(0.5)

                except Exception as e:
                    error_count += 1
                    print(f"處理訊息 {message.id} 時出錯: {e}")

            # 發送結果
            embed = discord.Embed(
                title=f"{tag.emoji} 日期範圍處理完成",
                description=f"頻道 `{channel.name}` 的處理結果",
                color=tag.color,
                timestamp=datetime.now()
            )

            embed.add_field(name="成功添加", value=success_count, inline=True)
            embed.add_field(name="已跳過", value=skip_count, inline=True)
            embed.add_field(name="錯誤", value=error_count, inline=True)
            embed.add_field(name="總計", value=len(messages), inline=True)
            embed.add_field(name="日期範圍",
                          value=f"{start_date.date()} 至 {end_date.date()}",
                          inline=False)

            if keywords:
                embed.add_field(name="關鍵字", value=", ".join(keywords), inline=False)

            await self._send(ctx_or_interaction, embed=embed)

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 處理歷史訊息時發生錯誤: {str(e)}")
    
    async def show_import_progress(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], total: int, current: int):
        """顯示導入進度"""
        progress = int((current / total) * 100)
        bar_length = 20
        filled = int(bar_length * current / total)
        bar = "█" * filled + "░" * (bar_length - filled)

        await self._send(ctx_or_interaction, f"📊 進度: [{bar}] {progress}% ({current}/{total})")
    
    async def import_history_by_emoji(self, interaction: discord.Interaction, channel: discord.TextChannel, tag):
        """通過 emoji 導入歷史訊息"""
        try:
            # 获取作者 ID
            author_id = interaction.user.id

            await interaction.followup.send(f"🔄 正在搜索 `{channel.name}` 頻道中包含 {tag.emoji} emoji 的訊息...")

            # 獲取訊息
            messages = []
            async for message in channel.history(limit=None):
                # 跳過系統訊息和機器人訊息
                if message.author.bot or message.type != discord.MessageType.default:
                    continue

                # 檢查訊息是否有這個 emoji 反應
                has_emoji = False
                for reaction in message.reactions:
                    # 使用 compare_emoji 函數進行比較
                    if compare_emoji(tag.emoji, reaction.emoji):
                        has_emoji = True
                        break

                if has_emoji:
                    messages.append(message)

            if not messages:
                await interaction.followup.send(f"❌ 沒有找到包含 {tag.emoji} emoji 的訊息。")
                return

            # 處理訊息
            success_count = 0
            skip_count = 0
            error_count = 0

            for message in messages:
                try:
                    # 檢查訊息是否已有該標籤
                    existing_tags = await self.db.get_message_tags(str(message.id))
                    if any(mt.tag_id == tag.id for mt in existing_tags):
                        skip_count += 1
                        continue

                    # 添加標籤
                    created_at = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    success = await self.db.tag_message(
                        message_id=str(message.id),
                        channel_id=str(message.channel.id),
                        guild_id=str(message.guild.id),
                        tag_id=tag.id,
                        tagged_by=str(author_id),
                        message_content=message.content,
                        author_id=str(message.author.id),
                        created_at=created_at
                    )

                    if success:
                        success_count += 1

                    # 避免觸發速率限制
                    await asyncio.sleep(0.5)

                except Exception as e:
                    error_count += 1
                    print(f"處理訊息 {message.id} 時出錯: {e}")

            # 發送結果
            embed = discord.Embed(
                title=f"{tag.emoji} 歷史訊息導入完成",
                description=f"頻道 `{channel.name}` 的導入結果",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            embed.add_field(name="成功添加", value=success_count, inline=True)
            embed.add_field(name="已跳過", value=skip_count, inline=True)
            embed.add_field(name="錯誤", value=error_count, inline=True)
            embed.add_field(name="總計", value=len(messages), inline=True)
            embed.add_field(name="Emoji", value=tag.emoji, inline=True)
            embed.add_field(name="標籤", value=tag.name, inline=True)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ 導入歷史訊息時發生錯誤: {str(e)}")