# TG Monitor

一个功能强大的 Telegram 频道监控系统，支持多频道、分频道关键词配置，并提供 Web 控制台进行实时管理。

## ✨ 核心功能

- **多频道监控**：同时监控多个 Telegram 频道
- **分频道关键词**：每个频道可配置独立的关键词列表
- **实时推送**：关键词匹配后立即通过 Bot 推送通知
- **Web 控制台**：可视化管理界面，实时查看日志和控制 Bot
- **Tag 输入**：现代化的标签式关键词输入体验
- **代理支持**：支持 HTTP/SOCKS5 代理

## 📋 环境要求

- Python 3.8+
- Telegram 账号（用于 UserBot）
- Telegram Bot Token（用于推送通知）

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制配置模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件，填入以下必需配置：

```env
# Telegram UserBot API (https://my.telegram.org 申请)
TG_API_ID=12345678
TG_API_HASH=your_api_hash_here

# Telegram Bot 推送配置 (@BotFather 申请)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=your_chat_id  # 你的 Chat ID (@userinfobot 查询)

# 代理配置 (可选)
TG_PROXY_TYPE=http
TG_PROXY_HOST=127.0.0.1
TG_PROXY_PORT=7897
```

### 3. 配置监控规则

编辑 `config.json` 文件，配置要监控的频道和关键词：

```json
{
  "channels": [
    {
      "id": "nodeseekc",
      "keywords": ["VPS", "特价", "补货"],
      "enabled": true
    },
    {
      "id": "your_channel_username",
      "keywords": ["关键词1", "关键词2"],
      "enabled": true
    }
  ]
}
```

**频道 ID 说明：**
- 公开频道：使用用户名（如 `nodeseekc`）
- 私有频道：使用邀请链接哈希（如 `+ABC123xyz`）或数字 ID

**关键词语法（高级）：**

| 语法 | 说明 | 示例 |
|------|------|------|
| 普通词 | 英文自动全词匹配，中文子串匹配 | `AI` 匹配 "AI" 但不匹配 "air" |
| `-排除词` | 排除包含该词的消息 | `-iPhone` 排除所有含 iPhone 的消息 |
| `/正则/` | 正则表达式匹配 | `/\bVPS\b/i` 大小写不敏感匹配 VPS |

**示例配置：**
```json
{
  "keywords": ["AI", "VPS", "-iPhone", "-苹果", "/\\bGPT-?4\\b/i"]
}
```
此配置会：
- 匹配包含 "AI" 或 "VPS" 的消息（全词匹配）
- 排除包含 "iPhone" 或 "苹果" 的消息
- 用正则匹配 "GPT4" 或 "GPT-4"（不区分大小写）

**正则表达式修饰符：**

| 修饰符 | 含义 | 示例 |
|:---:|:---|:---|
| `i` | 忽略大小写 | `/gpt/i` 匹配 GPT、gpt、Gpt |
| `s` | 点号匹配换行符 | `/开始.*结束/s` 跨行匹配 |
| `m` | 多行模式（`^` `$` 匹配每行） | `/^标题/m` 匹配每行开头 |

可组合使用：`/pattern/ism` 同时启用三个修饰符。

**学习资源：**
- Python 正则文档：https://docs.python.org/zh-cn/3/library/re.html
- 在线测试工具：https://regex101.com/ (选择 Python 语法)

### 4. 首次登录

第一次运行需要登录 Telegram 账号：

```bash
python monitor_tg.py
```

按提示输入手机号和验证码。登录成功后会生成 `anon.session` 文件，以后无需再次登录。

### 5. 启动 Web 控制台

```bash
python web_server.py
```

访问 http://127.0.0.1:8000 即可打开 Web 控制台。

## 🖥️ Web 控制台功能

### 仪表盘
- 实时查看 Bot 运行状态
- 查看最近 50 条运行日志
- 一键启动/停止/重启 Bot

### 配置中心
- 可视化管理监控频道
- Tag 式关键词输入（按 Enter 或逗号添加）
- 动态添加/删除频道配置
- 修改 Bot Token 和 Chat ID

## 📦 生产部署

### 使用 systemd (推荐)

创建服务文件 `/etc/systemd/system/tg-monitor.service`：

```ini
[Unit]
Description=TG Monitor Web Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/clawbot
ExecStart=/usr/bin/python3 web_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable tg-monitor
sudo systemctl start tg-monitor
```

### 使用 PM2

```bash
pm2 start web_server.py --name tg-monitor --interpreter python3
pm2 save
pm2 startup
```

### 使用 nohup

```bash
nohup python web_server.py > web.log 2>&1 &
```

## 🔧 常见问题

**Q: Bot 不转发消息？**
- 确认 UserBot 账号已加入目标频道
- 检查 `config.json` 中的频道 ID 是否正确
- 查看 Web 控制台日志，确认是否有 `[DEBUG]` 输出

**Q: 如何获取私有频道的 ID？**
- 方法 1：使用邀请链接哈希（`t.me/+ABC123` 中的 `+ABC123`）
- 方法 2：在频道内发消息，查看日志中的 `chat_id`

**Q: 关键词不区分大小写吗？**
- 是的，关键词匹配自动忽略大小写

**Q: 如何修改配置？**
- 通过 Web 控制台修改（推荐）
- 或直接编辑 `config.json`，然后重启 Bot

## 📝 文件说明

- `monitor_tg.py` - Bot 核心监控逻辑
- `web_server.py` - Web 控制台服务
- `config.json` - 频道监控配置
- `.env` - 敏感信息配置（不要提交到 Git）
- `templates/` - Web UI 模板文件
- `anon.session` - Telegram 登录会话（不要删除）

## ⚠️ 注意事项

1. **不要泄露 `.env` 文件**，其中包含敏感的 API 密钥
2. **保护好 `anon.session` 文件**，它等同于你的 Telegram 登录凭证
3. **UserBot 有使用限制**，不要用于商业用途或滥用
4. **首次部署建议先在本地测试**，确认配置正确后再部署到服务器

## 📄 License

MIT License
