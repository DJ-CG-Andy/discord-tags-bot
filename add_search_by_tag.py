    if not self.use_d1:
        async with aiosqlite.connect(self.db_path) as db:
            if guild_id:
                async with db.execute(
                    'SELECT mt.* FROM message_tags mt '