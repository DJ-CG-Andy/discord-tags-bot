# -*- coding: utf-8 -*-
"""
自動修復腳本：將 search_by_tag 方法插入到 database_d1.py
"""

def insert_search_by_tag_method():
    # 要插入的方法代碼
    method_to_insert = '''    async def search_by_tag(self, tag_name: str, guild_id: str = None, limit: int = 50) -> List[MessageTag]:
        """根據標籤搜索消息"""
        if not self.use_d1:
            async with aiosqlite.connect(self.db_path) as db:
                if guild_id:
                    async with db.execute(
                        "SELECT mt.* FROM message_tags mt "
                        "JOIN tags t ON mt.tag_id = t.id "
                        "WHERE t.name = ? AND mt.guild_id = ? "
                        "ORDER BY mt.tagged_at DESC LIMIT ?",
                        (tag_name, guild_id, limit)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        return [MessageTag(*row) for row in rows]
                else:
                    async with db.execute(
                        "SELECT mt.* FROM message_tags mt "
                        "JOIN tags t ON mt.tag_id = t.id "
                        "WHERE t.name = ? "
                        "ORDER BY mt.tagged_at DESC LIMIT ?",
                        (tag_name, limit)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        return [MessageTag(*row) for row in rows]
        else:
            try:
                if guild_id:
                    sql = """SELECT mt.* FROM message_tags mt 
                             JOIN tags t ON mt.tag_id = t.id 
                             WHERE t.name = ? AND mt.guild_id = ? 
                             ORDER BY mt.tagged_at DESC LIMIT ?"""
                    result = await self._execute_d1(sql, (tag_name, guild_id, limit))
                else:
                    sql = """SELECT mt.* FROM message_tags mt 
                             JOIN tags t ON mt.tag_id = t.id 
                             WHERE t.name = ? 
                             ORDER BY mt.tagged_at DESC LIMIT ?"""
                    result = await self._execute_d1(sql, (tag_name, limit))
                
                message_tags = []
                if result and result.get("success") and result.get("result"):
                    for row_result in result["result"]:
                        if "results" in row_result:
                            for r in row_result["results"]:
                                message_tags.append(MessageTag(
                                    r.get("id"),
                                    r.get("message_id"),
                                    r.get("channel_id"),
                                    r.get("guild_id"),
                                    r.get("tag_id"),
                                    r.get("tagged_by"),
                                    r.get("tagged_at"),
                                    r.get("message_content", ""),
                                    r.get("author_id"),
                                    r.get("created_at")
                                ))
                return message_tags
            except Exception as e:
                print(f"❌ 搜索失敗: {e}")
                return []
'''

    # 讀取目標文件
    print("📖 讀取 database_d1.py...")
    with open('database_d1.py', 'r', encoding='utf-8') as f:
        original_content = f.read()

    # 找到插入點
    insertion_point = original_content.find('    async def get_tags_by_category')
    
    if insertion_point == -1:
        print("❌ 錯誤：無法找到插入點（get_tags_by_category 方法）")
        return False

    print(f"✅ 找到插入點，位置：{insertion_point}")

    # 插入方法
    new_content = original_content[:insertion_point] + method_to_insert + '\n' + original_content[insertion_point:]

    # 寫回文件
    print("💾 寫入 database_d1.py...")
    with open('database_d1.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("✅ 成功！search_by_tag 方法已插入到 database_d1.py")
    return True

if __name__ == '__main__':
    success = insert_search_by_tag_method()
    exit(0 if success else 1)