"""Emoji 工具函數"""

def compare_emoji(tag_emoji: str, reaction_emoji) -> bool:
    """
    比較標籤的 emoji 和反應的 emoji
    
    支援：
    - 標準 emoji（👍、🏷️ 等）
    - 自定義 emoji（通過 ID 或完整格式比較）
    - ID（1486700764377124994）
    """
    reaction_str = str(reaction_emoji)
    
    # 1. 如果 tag_emoji 是標準 emoji，直接比較
    if len(tag_emoji) <= 4:  # 標準 emoji 通常很短
        return tag_emoji == reaction_str
    
    # 2. 如果 tag_emoji 是 ID（純數字）
    if tag_emoji.isdigit():
        # 檢查反應是否是自定義 emoji，並比較 ID
        if hasattr(reaction_emoji, 'id') and reaction_emoji.id:
            return tag_emoji == str(reaction_emoji.id)
        
        # 檢查反應字串中是否包含 ID
        if f":{tag_emoji}>" in reaction_str:
            return True
    
    # 3. 如果 tag_emoji 是完整格式（<:name:id>）
    if tag_emoji.startswith("<:") and tag_emoji.endswith(">"):
        # 提取 ID
        tag_emoji_id = tag_emoji.split(":")[-1].rstrip(">")
        
        # 檢查反應是否是自定義 emoji，並比較 ID
        if hasattr(reaction_emoji, 'id') and reaction_emoji.id:
            return tag_emoji_id == str(reaction_emoji.id)
        
        # 比較完整格式
        return tag_emoji == reaction_str
    
    # 4. 其他情況，直接比較
    return tag_emoji == reaction_str


def normalize_emoji(emoji_input: str) -> str:
    """
    標準化 emoji 輸入
    
    - 如果是標準 emoji，直接返回
    - 如果是 ID，直接返回
    - 如果是完整格式，提取 ID 並返回
    """
    # 如果是標準 emoji
    if len(emoji_input) <= 4:
        return emoji_input
    
    # 如果是 ID（純數字）
    if emoji_input.isdigit():
        return emoji_input
    
    # 如果是完整格式，提取 ID
    if emoji_input.startswith("<:") and emoji_input.endswith(">"):
        emoji_id = emoji_input.split(":")[-1].rstrip(">")
        return emoji_id
    
    # 其他情況，直接返回
    return emoji_input


def is_custom_emoji(emoji_input: str) -> bool:
    """
    判斷是否為自定義 emoji
    
    - 標準 emoji：False
    - ID：True
    - 完整格式：True
    """
    # 如果是標準 emoji
    if len(emoji_input) <= 4:
        return False
    
    # 如果是 ID（純數字）
    if emoji_input.isdigit():
        return True
    
    # 如果是完整格式
    if emoji_input.startswith("<:") and emoji_input.endswith(">"):
        return True
    
    # 其他情況，假設是標準 emoji
    return False


def emoji_to_image_url(emoji_input: str, size: int = 40) -> str:
    """
    將 emoji 或 ID 轉換為圖片連結
    
    - 標準 emoji：返回 emoji 本身
    - ID：返回圖片連結
    - 完整格式：返回圖片連結
    """
    # 如果是標準 emoji，直接返回
    if len(emoji_input) <= 4:
        return emoji_input
    
    # 如果是 ID（純數字）
    if emoji_input.isdigit():
        return f"https://cdn.discordapp.com/emojis/{emoji_input}.webp?size={size}"
    
    # 如果是完整格式，提取 ID 並返回圖片連結
    if emoji_input.startswith("<:") and emoji_input.endswith(">"):
        emoji_id = emoji_input.split(":")[-1].rstrip(">")
        return f"https://cdn.discordapp.com/emojis/{emoji_id}.webp?size={size}"
    
    # 其他情況，直接返回
    return emoji_input


def display_emoji(emoji_input: str) -> str:
    """
    用於顯示 emoji（如果是 ID，使用圖片連結）
    
    - 標準 emoji：返回 emoji 本身
    - ID：返回圖片連結（使用 Discord 圖片 URL）
    - 完整格式：返回圖片連結
    """
    # 如果是標準 emoji，直接返回
    if len(emoji_input) <= 4:
        return emoji_input
    
    # 如果是 ID 或完整格式，返回圖片連結
    image_url = emoji_to_image_url(emoji_input)
    
    # 如果是 ID 或完整格式，返回圖片連結
    if emoji_input.isdigit() or (emoji_input.startswith("<:") and emoji_input.endswith(">")):
        return image_url
    
    # 其他情況，直接返回
    return emoji_input