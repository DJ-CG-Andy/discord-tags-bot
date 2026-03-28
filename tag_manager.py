from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import json
from database import Database, Tag
from emoji_utils import display_emoji

@dataclass
class TagConfig:
    name: str
    category: str
    emoji: str
    description: str
    color: int

class TagManager:
    def __init__(self, db: Database, config_path: str = "config.json"):
        self.db = db
        self.config_path = config_path
        self.config = self._load_config()
        self.default_tags = self._get_default_tags()
    
    def _load_config(self) -> Dict:
        """加載配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "tag_categories": {},
                "tag_colors": {}
            }
    
    def _get_default_tags(self) -> List[TagConfig]:
        """獲取默認標籤配置"""
        default_tags = []
        categories = self.config.get("tag_categories", {})
        colors = self.config.get("tag_colors", {})
        
        for category, info in categories.items():
            emoji = info.get("emoji", "🏷️")
            description = info.get("description", "")
            color = colors.get(category, 5814783)
            
            # 為每個分類創建幾個默認標籤
            if category == "knowledge":
                default_tags.extend([
                    TagConfig("重要", "knowledge", emoji, "重要的知識點", color),
                    TagConfig("教程", "knowledge", emoji, "教程或指南", color),
                    TagConfig("FAQ", "knowledge", emoji, "常見問題", color),
                    TagConfig("資源", "knowledge", emoji, "有用資源", color),
                ])
            elif category == "project":
                default_tags.extend([
                    TagConfig("功能", "project", emoji, "功能相關", color),
                    TagConfig("Bug", "project", emoji, "問題修復", color),
                    TagConfig("優化", "project", emoji, "性能優化", color),
                    TagConfig("設計", "project", emoji, "設計討論", color),
                ])
            elif category == "review":
                default_tags.extend([
                    TagConfig("待審核", "review", emoji, "需要審核", color),
                    TagConfig("違規", "review", emoji, "違規內容", color),
                    TagConfig("關注", "review", emoji, "需要關注", color),
                    TagConfig("警告", "review", emoji, "警告信息", color),
                ])
            elif category == "analytics":
                default_tags.extend([
                    TagConfig("統計", "analytics", emoji, "統計數據", color),
                    TagConfig("報告", "analytics", emoji, "分析報告", color),
                    TagConfig("趨勢", "analytics", emoji, "趨勢分析", color),
                ])
        
        return default_tags
    
    async def initialize_tags(self):
        """不初始化默認標籤 - 用戶自行創建標籤"""
        # 不做任何事情，讓用戶自己創建標籤
        pass
    
    async def create_custom_tag(self, name: str, category: str,
                                   emoji: str = "🏷️", description: str = "", image_url: str = "") -> bool:
            """創建自定義標籤"""
            colors = self.config.get("tag_colors", {})
            color = colors.get(category, 5814783)
            
            tag_id = await self.db.create_tag(name, category, emoji, description, image_url, color)
            return tag_id is not None    
    async def get_available_tags(self, category: str = None) -> List[Tag]:
        """獲取可用標籤"""
        print(f"🔍 get_available_tags 被調用，category={category}")
        if category:
            print(f"🔍 按分類獲取標籤: {category}")
            tags = await self.db.get_tags_by_category(category)
        else:
            print(f"🔍 獲取所有標籤")
            tags = await self.db.get_all_tags()
        print(f"🔍 返回 {len(tags)} 個標籤")
        return tags
    
    async def get_tag_info(self, tag_name: str) -> Optional[Tag]:
        """獲取標籤信息"""
        return await self.db.get_tag_by_name(tag_name)
    
    async def get_tag_suggestions(self, query: str) -> List[str]:
        """獲取標籤建議（用於自動完成）"""
        all_tags = await self.db.get_all_tags()
        query_lower = query.lower()
        
        suggestions = []
        for tag in all_tags:
            if query_lower in tag.name.lower() or query_lower in tag.description.lower():
                suggestions.append(tag.name)
        
        return suggestions[:10]  # 返回前10個建議
    
    def format_tag_list(self, tags: List[Tag]) -> str:
        """格式化標籤列表用於顯示"""
        if not tags:
            return "沒有可用的標籤"
        
        output = []
        current_category = None
        
        for tag in tags:
            if tag.category != current_category:
                if current_category is not None:
                    output.append("")
                output.append(f"**{tag.category.upper()}**")
                current_category = tag.category
            
            # 使用 display_emoji 函數來顯示 emoji
            display_emoji_str = display_emoji(tag.emoji)
            output.append(f"  {display_emoji_str} `{tag.name}` - {tag.description}")
        
        return "\n".join(output)    
    def get_category_emoji(self, category: str) -> str:
        """獲取分類對應的 emoji"""
        categories = self.config.get("tag_categories", {})
        return categories.get(category, {}).get("emoji", "🏷️")
    
    def get_all_categories(self) -> List[str]:
        """獲取所有分類"""
        return list(self.config.get("tag_categories", {}).keys())
    
    async def get_statistics(self, guild_id: str = None) -> Dict:
        """獲取統計信息"""
        try:
            tag_stats = await self.db.get_tag_statistics(guild_id)
            
            # 計算總統計
            total_tags = len(tag_stats)
            total_tagged_messages = sum(stat['usage_count'] for stat in tag_stats)
            
            # 獲取活躍用戶數（不同的 tagged_by）
            active_users = await self.db.get_active_users_count(guild_id)
            
            # 熱門標籤（前5個）
            top_tags = []
            for stat in tag_stats[:5]:
                top_tags.append({
                    'name': stat['tag'].name,
                    'emoji': stat['tag'].emoji,
                    'count': stat['usage_count']
                })
            
            return {
                'total_tags': total_tags,
                'total_tagged_messages': total_tagged_messages,
                'active_users': active_users,
                'top_tags': top_tags
            }
        except Exception as e:
            print(f"獲取統計信息錯誤: {e}")
            return {
                'total_tags': 0,
                'total_tagged_messages': 0,
                'active_users': 0,
                'top_tags': []
            }