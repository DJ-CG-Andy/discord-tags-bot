## 修复内容
- 添加 `aiohttp`, `tempfile`, `urllib.parse` 导入
- 添加 `download_url_to_temp_file` 函数，将 GIF URL 下载到临时文件后再发送
- 修复 `FileNotFoundError` 错误（之前 `discord.File` 直接使用 URL 而不是本地文件路径）

## 问题原因
`discord.File()` 只能接受本地文件路径，不能直接接受 URL。之前代码传入了 Discord CDN URL 导致 `FileNotFoundError`。

## 修复方法
在发送 GIF 前先下载 URL 内容到临时文件，然后使用 `discord.File(临时文件路径)` 发送，完成后删除临时文件。