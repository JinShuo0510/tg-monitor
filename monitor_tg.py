import asyncio
import logging
import re
import requests
import cloudscraper
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.network.connection import ConnectionTcpFull
import os 

# Load environment variables
load_dotenv()

# Configuration
API_ID = os.getenv('TG_API_ID')
API_HASH = os.getenv('TG_API_HASH')
# Proxy Configuration
PROXY_TYPE = os.getenv('TG_PROXY_TYPE', '').lower()
PROXY_HOST = os.getenv('TG_PROXY_HOST')
PROXY_PORT = os.getenv('TG_PROXY_PORT')

# Bot Notification Configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BOT_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate config
if not API_ID or not API_HASH:
    logger.error("TG_API_ID or TG_API_HASH not found in .env file.")
    exit(1)

def send_bot_message(text):
    """Send message via Telegram Bot API"""
    if not BOT_TOKEN or not BOT_CHAT_ID:
        logger.warning("Bot Token or Chat ID not set. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Build proxy dict for requests
    proxies = None
    if PROXY_HOST and PROXY_PORT:
        proxy_url = f"{PROXY_TYPE}://{PROXY_HOST}:{PROXY_PORT}"
        proxies = {"http": proxy_url, "https": proxy_url}

    try:
        payload = {
            "chat_id": BOT_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            # Enable native Telegram link preview
            "disable_web_page_preview": False
        }
        resp = requests.post(url, json=payload, proxies=proxies, timeout=10)
        resp.raise_for_status()
        logger.info("Notification sent to Telegram Bot.")
    except Exception as e:
        logger.error(f"Failed to send bot notification: {e}")

# Build proxy dict for Telethon (using python-socks style)
proxy = None
if PROXY_HOST and PROXY_PORT:
    try:
        port = int(PROXY_PORT)
        if 'socks5' in PROXY_TYPE:
            proxy = {
                'proxy_type': 'socks5',
                'addr': PROXY_HOST,
                'port': port,
                'rdns': True
            }
        elif 'socks4' in PROXY_TYPE:
            proxy = {
                'proxy_type': 'socks4',
                'addr': PROXY_HOST,
                'port': port
            }
        elif 'http' in PROXY_TYPE:
            proxy = {
                'proxy_type': 'http',
                'addr': PROXY_HOST,
                'port': port
            }
        logger.info(f"Using Proxy: {PROXY_TYPE}://{PROXY_HOST}:{port}")
    except ValueError:
        logger.error("Invalid Proxy Port")
        exit(1)

# Initialize Client
client = TelegramClient(
    'anon',
    int(API_ID),
    API_HASH,
    proxy=proxy
)

def fetch_url_preview(url, max_lines=5):
    """Fetch URL content and return first few lines of text"""
    try:
        # Create cloudscraper session (automatically bypasses Cloudflare)
        scraper = cloudscraper.create_scraper()
        
        # Build proxy dict
        proxies = None
        if PROXY_HOST and PROXY_PORT:
            proxy_url = f"{PROXY_TYPE}://{PROXY_HOST}:{PROXY_PORT}"
            proxies = {"http": proxy_url, "https": proxy_url}
        
        # Fetch content
        response = scraper.get(url, proxies=proxies, timeout=15)
        response.raise_for_status()
        
        # Parse HTML and extract text
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # For NodeSeek: try to find the main post content
        if 'nodeseek.com' in url:
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.decompose()
            
            # Try to find the post content container
            post_content = soup.find('div', class_='post-content') or \
                          soup.find('article') or \
                          soup.find('div', class_='content') or \
                          soup.find('main')
            
            if post_content:
                text = post_content.get_text()
            else:
                text = soup.get_text()
        else:
            # For other sites, use default extraction
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
        
        # Clean and filter lines
        lines = []
        skip_patterns = [
            'NodeSeekbeta', 'DeepFlood', 'search for post', 'search for people',
            'use google search', '所有版块', '日常技术情报测评交易拼车推广',
            '日常 技术 情报 测评 交易 拼车 推广 生活 Dev 贴图 曝光 沙盒'
        ]
        
        # Regex pattern for post metadata (e.g., "username楼主 1s ago in 交易 #0")
        import re as regex_module
        metadata_pattern = regex_module.compile(r'.+楼主\s+\d+[smhd]\s+ago\s+in\s+.+#\d+')
        
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip lines that match unwanted patterns
            if any(pattern in line for pattern in skip_patterns):
                continue
            # Skip post metadata lines
            if metadata_pattern.match(line):
                continue
            lines.append(line)
        
        # Return first N lines
        preview = '\n'.join(lines[:max_lines])
        return preview if preview else None
        
    except Exception as e:
        # Silently fail - return None instead of error message
        return None

import json

# Global to store channel-specific configs (id -> keywords)
CHANNEL_CONFIGS = {}

def load_channel_config():
    """Load channel configuration from json file"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('channels', [])
    except Exception as e:
        logger.error(f"Failed to load config.json: {e}")
        return []

async def main():
    channels_conf = load_channel_config()
    target_chats_ids = []
    
    # Reset global config map
    global CHANNEL_CONFIGS
    CHANNEL_CONFIGS = {}
    
    logger.info(f"Loaded {len(channels_conf)} channel configs from settings.")
    
    await client.start()
    
    # Resolve channel entities and build config map
    valid_chats = []
    
    for conf in channels_conf:
        if not conf.get('enabled', True):
            continue
            
        chat_id_or_name = conf['id']
        keywords = conf.get('keywords', [])
        
        try:
            # Try to resolve the entity
            if chat_id_or_name.lstrip('-').isdigit():
                 entity = await client.get_entity(int(chat_id_or_name))
            else:
                 entity = await client.get_entity(chat_id_or_name)
            
            # Convert to the format used in message events
            # Telethon returns channel IDs with -100 prefix in events
            # For channels/supergroups, entity.id is positive, but event.chat_id is negative with -100 prefix
            event_chat_id = entity.id
            if hasattr(entity, 'megagroup') or hasattr(entity, 'broadcast'):
                # This is a channel or supergroup, convert to event format
                if event_chat_id > 0:
                    event_chat_id = int(f"-100{entity.id}")
            
            # valid_chats used for client.on filter - use original entity.id
            valid_chats.append(entity.id)
            target_chats_ids.append(entity.id)
            
            # Store keywords using the EVENT format ID (with -100 prefix)
            CHANNEL_CONFIGS[event_chat_id] = [k.strip() for k in keywords if k.strip()]
            
            logger.info(f"Monitoring: {getattr(entity, 'title', chat_id_or_name)} (ID: {entity.id}) | Keywords: {CHANNEL_CONFIGS[event_chat_id]}")
            
        except Exception as e:
            logger.error(f"Failed to resolve channel {chat_id_or_name}: {e}")

    if not valid_chats:
        logger.error("No valid channels to monitor. Exiting.")
        return
        
    # We update the event handler filter dynamically or re-register?
    # Telethon's filters are evaluated at runtime, but we need to pass the list to the decorator.
    # Since we can't easily change the decorator args after definition, we might need a workaround.
    # Actually, we can just filter in the handler itself or use a router, but client.on registers immediately.
    # A cleaner way is to define the handler INSIDE main or pass a function that returns the list.
    # However, 'chats' argument in NewMessage accepts a list. If we pass the list object, does it update?
    # No, it copies.
    
    # WORKAROUND: We will listen to ALL incoming messages (or a broad scope if possible, but NewMessage without chats listens to all)
    # AND filter inside the handler function using our valid_chats list.
    # But to be polite to the API, we prefer specifying chats.
    # Since this script runs once, we can just rely on the decorator using a global variable if we could, 
    # but the decorator runs at import time/definition time.
    
    # Better approach: Remove the decorator usage at module level and add_event_handler inside main.
    client.add_event_handler(handler, events.NewMessage(chats=valid_chats))

    logger.info("Connected! Waiting for messages...")
    await client.run_until_disconnected()

# Remove module-level decorator and check manually
async def handler(event):
    message_text = event.message.message
    
    # DEBUG: Log every message received
    logger.info(f"[DEBUG] Received message from chat_id={event.chat_id}: {message_text[:50] if message_text else 'NO TEXT'}...")
    
    if not message_text:
        return

    # Check which channel this came from
    chat_id = event.chat_id
    
    # Get keywords for this channel
    keywords = CHANNEL_CONFIGS.get(chat_id, [])
    
    # If no config found, skip
    if chat_id not in CHANNEL_CONFIGS:
        logger.warning(f"[DEBUG] chat_id {chat_id} not in CHANNEL_CONFIGS. Available: {list(CHANNEL_CONFIGS.keys())}")
        return

    # Extract first line (title) for keyword matching
    # This prevents false positives from content inside code blocks
    first_line = message_text.split('\n')[0] if message_text else ''
    
    # Check for matched keywords using advanced matching (only on title)
    matched_keyword = match_keywords(first_line, keywords)
            
    if matched_keyword:
        logger.info(f"Keyword matched: {matched_keyword}")
        try:
            # Parse message and extract the main link
            parsed = parse_message_format(message_text, event.message.entities)
            
            # Prepare notification
            output_lines = []
            output_lines.append(f"🔔 <b>关键词监控通知</b>")
            output_lines.append(f"#{matched_keyword}")
            
            if parsed['main_url']:
                # Format with clickable title
                if parsed['title']:
                    output_lines.append(f'\n<a href="{parsed["main_url"]}">{html_escape(parsed["title"])}</a>')
                    if parsed['content']:
                        # Add content in a code block style (preformatted)
                        content_preview = parsed['content'][:500] + '...' if len(parsed['content']) > 500 else parsed['content']
                        output_lines.append(f'\n<pre>{html_escape(content_preview)}</pre>')
                else:
                    # Fallback: use full text as link
                    safe_text = html_escape(message_text[:300] + '...' if len(message_text) > 300 else message_text)
                    output_lines.append(f'\n<a href="{parsed["main_url"]}">{safe_text}</a>')
            else:
                # No URL found, just send the text
                output_lines.append(f"\n{html_escape(message_text[:500])}")
            
            # Terminal output
            print(f"\n========== MATCHED MESSAGE ==========")
            print(f"KEYWORD: {matched_keyword}")
            print(f"TITLE: {parsed.get('title', 'N/A')}")
            print(f"MAIN URL: {parsed.get('main_url', 'N/A')}")
            print(f"CONTENT:\n{message_text[:200]}...")
            print(f"=====================================\n", flush=True)
            
            # Send notification via Bot
            full_message = "\n".join(output_lines)
            await asyncio.to_thread(send_bot_message, full_message)
            
        except Exception as e:
            logger.error(f"Failed to process message: {e}")


def html_escape(text):
    """Escape HTML special characters"""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def match_keywords(text, keywords):
    """
    Advanced keyword matching with support for:
    1. Whole word matching for English/alphanumeric (using word boundaries)
    2. Exclusion keywords with '-' prefix (e.g., '-air' excludes messages containing 'air')
    3. Regex patterns with '/pattern/' syntax (e.g., '/\bAI\b/')
    
    For Chinese keywords, uses simple substring matching (no word boundary concept).
    
    Returns the first matched keyword, or None if no match.
    """
    text_lower = text.lower()
    
    # Separate exclusion keywords and positive keywords
    exclusions = []
    positive_keywords = []
    
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if kw.startswith('-'):
            # Exclusion keyword
            exclusions.append(kw[1:].strip())
        else:
            positive_keywords.append(kw)
    
    # First, check exclusions - if ANY exclusion matches, skip this message entirely
    for excl in exclusions:
        if is_keyword_match(text, text_lower, excl):
            return None
    
    # Then check positive keywords
    for kw in positive_keywords:
        if is_keyword_match(text, text_lower, kw):
            return kw
    
    return None


def is_keyword_match(text, text_lower, keyword):
    """
    Check if a single keyword matches the text.
    
    Supports:
    - Regex patterns: /pattern/  or  /pattern/i (case insensitive)
    - Whole word matching for alphanumeric keywords
    - Substring matching for CJK (Chinese/Japanese/Korean) keywords
    """
    keyword = keyword.strip()
    
    # Check if it's a regex pattern
    if keyword.startswith('/') and ('/' in keyword[1:]):
        # Extract regex pattern
        last_slash = keyword.rfind('/')
        if last_slash > 0:
            pattern = keyword[1:last_slash]
            flags_str = keyword[last_slash+1:]
            
            # Parse flags
            flags = 0
            if 'i' in flags_str:
                flags |= re.IGNORECASE
            if 's' in flags_str:
                flags |= re.DOTALL
            if 'm' in flags_str:
                flags |= re.MULTILINE
            
            try:
                if re.search(pattern, text, flags):
                    return True
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            return False
    
    keyword_lower = keyword.lower()
    
    # Check if keyword is primarily CJK (Chinese/Japanese/Korean)
    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')
    is_cjk = bool(cjk_pattern.search(keyword))
    
    if is_cjk:
        # For CJK, use simple substring matching
        return keyword_lower in text_lower
    else:
        # For alphanumeric, use word boundary matching
        # This ensures 'AI' matches 'AI' but not 'air' or 'fair'
        try:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                return True
        except re.error:
            # Fallback to simple matching if regex fails
            return keyword_lower in text_lower
    
    return False


def parse_message_format(text, entities=None):
    """
    Parse message to extract title, main URL, and content.
    
    Handles LINUX DO Channel format:
        Username (@handle) 在 Title (https://linux.do/...) 中发帖
        Content...
    
    And NodeSeek format:
        Title with content and URLs inline
    """
    result = {
        'title': None,
        'main_url': None,
        'content': None,
        'external_urls': []
    }
    
    lines = text.strip().split('\n')
    first_line = lines[0] if lines else ''
    
    # Pattern 1: LINUX DO format - "Username (@handle) 在 Title (URL) 中发帖"
    linux_do_pattern = r'^(.+?)\s+在\s+(.+?)\s*\(?(https?://linux\.do/[^\s\)]+)\)?\s*中发帖'
    match = re.match(linux_do_pattern, first_line)
    
    if match:
        result['title'] = f"{match.group(1)} 在 {match.group(2)} 中发帖"
        result['main_url'] = match.group(3)
        result['content'] = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''
        return result
    
    # Pattern 2: Check entities for hidden links (common in formatted messages)
    if entities:
        for entity in entities:
            if hasattr(entity, 'url') and entity.url:
                # Prefer linux.do or nodeseek.com links as main URL
                if 'linux.do' in entity.url or 'nodeseek.com' in entity.url:
                    result['main_url'] = entity.url
                    result['title'] = first_line
                    result['content'] = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''
                    return result
    
    # Pattern 3: Look for URLs in text, prefer linux.do/nodeseek.com
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    
    # Prioritize certain domains for main URL
    priority_domains = ['linux.do', 'nodeseek.com', 'nodeseek.net']
    main_url = None
    
    for url in urls:
        for domain in priority_domains:
            if domain in url:
                main_url = url
                break
        if main_url:
            break
    
    # If no priority URL found, use the first URL
    if not main_url and urls:
        main_url = urls[0]
    
    result['main_url'] = main_url
    result['title'] = first_line if first_line else None
    result['content'] = '\n'.join(lines[1:]).strip() if len(lines) > 1 else text
    result['external_urls'] = [u for u in urls if u != main_url]
    
    return result


if __name__ == '__main__':
    asyncio.run(main())
