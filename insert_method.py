with open('database_d1.py', 'r', encoding='utf-8') as f:
    content = f.read()
with open('search_by_tag_method.py', 'r', encoding='utf-8') as f:
    method = f.read()
insert_pos = content.find('    async def get_tags_by_category')
new_content = content[:insert_pos] + method + '\n' + content[insert_pos:]
open('database_d1.py', 'w', encoding='utf-8').write(new_content)
print('✅ search_by_tag 方法已添加')
