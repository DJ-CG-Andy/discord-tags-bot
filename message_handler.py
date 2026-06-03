import discord
from discord.ext import commands
from typing import Optional, Union
from datetime import datetime
from database import Database, MessageTag
from tag_manager import TagManager

class MessageHandler:
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

    def _get_author(self, ctx_or_interaction: Union[commands.Context, discord.Interaction]):
        """获取作者的统一方法"""
        if isinstance(ctx_or_interaction, discord.Interaction):
            return ctx_or_interaction.user
        else:
            return ctx_or_interaction.author

    def _get_guild(self, ctx_or_interaction: Union[commands.Context, discord.Interaction]):
        """获取服务器的统一方法"""
        if isinstance(ctx_or_interaction, discord.Interaction):
            return ctx_or_interaction.guild
        else:
            return ctx_or_interaction.guild

    def _get_channel(self, ctx_or_interaction: Union[commands.Context, discord.Interaction]):
        """获取频道的统一方法"""
        if isinstance(ctx_or_interaction, discord.Interaction):
            return ctx_or_interaction.channel
        else:
            return ctx_or_interaction.channel

    async def _defer_if_needed(self, ctx_or_interaction: Union[commands.Context, discord.Interaction]):
        """如果是 Interaction，则调用 defer"""
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.defer()
    
    async def handle_tag_command(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], message_link: str, tag_name: str):
        """處理標籤命令"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            # 解析訊息連結
            message = await self._parse_message_link(ctx_or_interaction, message_link)
            if not message:
                await self._send(ctx_or_interaction, "❌ 無法找到該訊息。請提供正確的訊息連結。")
                return

            # 檢查標籤是否存在
            tag = await self.tag_manager.get_tag_info(tag_name)
            if not tag:
                await self._send(ctx_or_interaction, f"❌ 標籤 `{tag_name}` 不存在。使用 `/tags` 查看可用標籤。")
                return

            # 檢查訊息是否已有該標籤
            existing_tags = await self.db.get_message_tags(message.id)
            if any(mt.tag_id == tag.id for mt in existing_tags):
                await self._send(ctx_or_interaction, f"⚠️ 該訊息已有標籤 `{tag_name}`。")
                return

            # 獲取訊息創建時間
            created_at = message.created_at.strftime("%Y-%m-%d %H:%M:%S")

            # 添加標籤
            success = await self.db.tag_message(
                message_id=str(message.id),
                channel_id=str(message.channel.id),
                guild_id=str(message.guild.id),
                tag_id=tag.id,
                tagged_by=str(self._get_author(ctx_or_interaction).id),
                message_content=message.content,
                author_id=str(message.author.id),
                created_at=created_at
            )

            if success:
                # 發送確認訊息
                embed = discord.Embed(
                    title=f"{tag.emoji} 標籤添加成功",
                    description=f"訊息已添加標籤 `{tag_name}`",
                    color=tag.color,
                    timestamp=datetime.now()
                )
                embed.add_field(name="訊息內容", value=message.content[:100] + "..." if len(message.content) > 100 else message.content, inline=False)
                embed.add_field(name="標籤", value=f"{tag.emoji} {tag.name}", inline=True)
                embed.add_field(name="分類", value=tag.category, inline=True)
                embed.add_field(name="操作者", value=self._get_author(ctx_or_interaction).mention, inline=True)
                embed.set_footer(text=f"訊息ID: {message.id}")

                await self._send(ctx_or_interaction, embed=embed)
            else:
                await self._send(ctx_or_interaction, "❌ 添加標籤失敗。")

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 發生錯誤: {str(e)}")
    
    async def handle_untag_command(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], message_link: str, tag_name: str):
        """處理移除標籤命令"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            # 解析訊息連結
            message = await self._parse_message_link(ctx_or_interaction, message_link)
            if not message:
                await self._send(ctx_or_interaction, "❌ 無法找到該訊息。請提供正確的訊息連結。")
                return

            # 檢查標籤是否存在
            tag = await self.tag_manager.get_tag_info(tag_name)
            if not tag:
                await self._send(ctx_or_interaction, f"❌ 標籤 `{tag_name}` 不存在。")
                return

            # 移除標籤
            success = await self.db.untag_message(str(message.id), tag.id)

            if success:
                embed = discord.Embed(
                    title=f"✅ 標籤移除成功",
                    description=f"訊息已移除標籤 `{tag_name}`",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="訊息ID", value=message.id, inline=True)
                embed.add_field(name="操作者", value=self._get_author(ctx_or_interaction).mention, inline=True)

                await self._send(ctx_or_interaction, embed=embed)
            else:
                await self._send(ctx_or_interaction, "❌ 該訊息沒有這個標籤或移除失敗。")

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 發生錯誤: {str(e)}")
    
    async def handle_search_command(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], tag_name: str, limit: int = 10):
        """處理搜索命令"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            guild = self._get_guild(ctx_or_interaction)
            if not guild:
                await self._send(ctx_or_interaction, "❌ 無法獲取服務器信息。")
                return

            # 搜索訊息
            messages = await self.db.search_by_tag(
                tag_name=tag_name,
                guild_id=str(guild.id),
                limit=limit
            )

            if not messages:
                await self._send(ctx_or_interaction, f"❌ 沒有找到帶有標籤 `{tag_name}` 的訊息。")
                return

            tag = await self.tag_manager.get_tag_info(tag_name)

            embed = discord.Embed(
                title=f"{tag.emoji} 搜索結果: {tag_name}",
                description=f"找到 {len(messages)} 條訊息",
                color=tag.color,
                timestamp=datetime.now()
            )

            for i, msg in enumerate(messages[:10], 1):
                content = msg.message_content[:50] + "..." if len(msg.message_content) > 50 else msg.message_content
                embed.add_field(
                    name=f"#{i} - {msg.tagged_at}",
                    value=f"**頻道**: <#{msg.channel_id}>\n**內容**: {content}\n**連結**: https://discord.com/channels/{msg.guild_id}/{msg.channel_id}/{msg.message_id}",
                    inline=False
                )

            await self._send(ctx_or_interaction, embed=embed)

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 發生錯誤: {str(e)}")
    
    async def handle_content_search_command(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], query: str, limit: int = 10):
        """處理內容搜索命令"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            guild = self._get_guild(ctx_or_interaction)
            if not guild:
                await self._send(ctx_or_interaction, "❌ 無法獲取服務器信息。")
                return

            messages = await self.db.search_by_content(
                query=query,
                guild_id=str(guild.id),
                limit=limit
            )

            if not messages:
                await self._send(ctx_or_interaction, f"❌ 沒有找到包含 '{query}' 的標籤訊息。")
                return

            embed = discord.Embed(
                title="🔍 內容搜索結果",
                description=f"找到 {len(messages)} 條訊息",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )

            for i, msg in enumerate(messages[:10], 1):
                content = msg.message_content[:80] + "..." if len(msg.message_content) > 80 else msg.message_content
                # 高亮匹配的關鍵字
                highlighted = content.replace(query, f"**{query}**")
                embed.add_field(
                    name=f"#{i} - {msg.tagged_at}",
                    value=f"**頻道**: <#{msg.channel_id}>\n**內容**: {highlighted}\n**連結**: https://discord.com/channels/{msg.guild_id}/{msg.channel_id}/{msg.message_id}",
                    inline=False
                )

            await self._send(ctx_or_interaction, embed=embed)

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 發生錯誤: {str(e)}")
    
    async def handle_show_tags_command(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], category: Optional[str] = None):
        """處理顯示標籤命令"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            tags = await self.tag_manager.get_available_tags(category)

            if not tags:
                await self._send(ctx_or_interaction, "❌ 沒有可用的標籤。")
                return

            embed = discord.Embed(
                title="🏷️ 可用標籤",
                description=self.tag_manager.format_tag_list(tags),
                color=discord.Color.gold(),
                timestamp=datetime.now()
            )

            await self._send(ctx_or_interaction, embed=embed)

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 發生錯誤: {str(e)}")
    
    async def handle_stats_command(self, ctx_or_interaction: Union[commands.Context, discord.Interaction]):
        """處理統計命令"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            guild = self._get_guild(ctx_or_interaction)
            if not guild:
                await self._send(ctx_or_interaction, "❌ 無法獲取服務器信息。")
                return

            # 獲取服務器統計
            stats = await self.db.get_guild_statistics(str(guild.id))
            tag_stats = await self.db.get_tag_statistics(str(guild.id))

            embed = discord.Embed(
                title="📊 標籤統計",
                description=f"**{guild.name}** 的標籤使用統計",
                color=discord.Color.purple(),
                timestamp=datetime.now()
            )

            embed.add_field(name="總標籤數", value=stats['total_tags'], inline=True)
            embed.add_field(name="總訊息數", value=stats['total_messages'], inline=True)

            # 分類統計
            if stats['category_stats']:
                category_text = "\n".join([f"{cat}: {count}" for cat, count in stats['category_stats']])
                embed.add_field(name="分類統計", value=category_text, inline=False)

            # 標籤使用排行
            if tag_stats:
                top_tags = tag_stats[:5]
                tag_text = "\n".join([f"{item['tag'].emoji} {item['tag'].name}: {item['usage_count']}次"
                                     for item in top_tags if item['usage_count'] > 0])
                if tag_text:
                    embed.add_field(name="熱門標籤", value=tag_text, inline=False)

            # 活躍用戶
            if stats['top_users']:
                user_text = "\n".join([f"<@{user[0]}>: {user[1]}次" for user in stats['top_users']])
                embed.add_field(name="活躍用戶", value=user_text, inline=False)

            await self._send(ctx_or_interaction, embed=embed)

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 發生錯誤: {str(e)}")
    
    async def handle_recent_command(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], limit: int = 10):
        """處理最近標籤命令"""
        try:
            # 如果是 Interaction，先调用 defer
            await self._defer_if_needed(ctx_or_interaction)

            guild = self._get_guild(ctx_or_interaction)
            if not guild:
                await self._send(ctx_or_interaction, "❌ 無法獲取服務器信息。")
                return

            messages = await self.db.get_recent_messages(str(guild.id), limit)

            if not messages:
                await self._send(ctx_or_interaction, "❌ 沒有最近的標籤訊息。")
                return

            embed = discord.Embed(
                title="🕐 最近的標籤訊息",
                description=f"最近 {len(messages)} 條標籤訊息",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            for i, msg in enumerate(messages[:10], 1):
                tag = await self.tag_manager.get_tag_info(msg.tag_id)
                content = msg.message_content[:50] + "..." if len(msg.message_content) > 50 else msg.message_content
                tag_info = f"{tag.emoji} {tag.name}" if tag else "未知標籤"

                embed.add_field(
                    name=f"#{i} - {tag_info}",
                    value=f"**時間**: {msg.tagged_at}\n**頻道**: <#{msg.channel_id}>\n**內容**: {content}",
                    inline=False
                )

            await self._send(ctx_or_interaction, embed=embed)

        except Exception as e:
            await self._send(ctx_or_interaction, f"❌ 發生錯誤: {str(e)}")
    
    async def _parse_message_link(self, ctx_or_interaction: Union[commands.Context, discord.Interaction], message_link: str) -> Optional[discord.Message]:
        """解析訊息連結並返回訊息對象"""
        try:
            # 嘗試直接獲取訊息ID
            if message_link.isdigit():
                channel = self._get_channel(ctx_or_interaction)
                if not channel:
                    return None
                return await channel.fetch_message(int(message_link))

            # 解析 Discord 訊息連結
            # 格式: https://discord.com/channels/guild_id/channel_id/message_id
            parts = message_link.split('/')
            if len(parts) >= 2:
                message_id = parts[-1]
                if message_id.isdigit():
                    channel_id = parts[-2] if len(parts) >= 3 else str(self._get_channel(ctx_or_interaction).id)
                    guild_id = parts[-3] if len(parts) >= 4 else str(self._get_guild(ctx_or_interaction).id)

                    guild = self.bot.get_guild(int(guild_id))
                    if not guild:
                        guild = await self.bot.fetch_guild(int(guild_id))

                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        channel = await guild.fetch_channel(int(channel_id))

                    return await channel.fetch_message(int(message_id))

            return None

        except Exception as e:
            print(f"解析訊息連結錯誤: {e}")
            return None