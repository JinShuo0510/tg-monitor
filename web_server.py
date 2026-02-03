import os
import subprocess
import signal
import sys
import threading
import time
import json
from typing import List
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import dotenv_values, set_key
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "your-secret-key-change-in-production"))

# Setup templates
templates = Jinja2Templates(directory="templates")

# Global variable to store the bot process
bot_process = None
BOT_SCRIPT = "monitor_tg.py"
LOG_FILE = "bot.log"
ENV_FILE = ".env"

class ChannelConfig(BaseModel):
    id: str
    keywords: str # Comma separated string for UI
    enabled: bool

class ConfigUpdate(BaseModel):
    # .env settings
    telegram_bot_token: str
    telegram_chat_id: str
    # config.json settings
    channels: List[ChannelConfig]

def get_bot_status():
    global bot_process
    if bot_process is None:
        return "stopped"
    if bot_process.poll() is None:
        return "running"
    return "stopped"

def start_bot():
    global bot_process
    if get_bot_status() == "running":
        return False
    
    # Run the bot and redirect output to log file
    # Open with utf-8 encoding to ensure Chinese characters are written correctly
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        # Force Python subprocess to use UTF-8 for IO
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        # Use sys.executable to ensure we use the same python interpreter
        bot_process = subprocess.Popen(
            [sys.executable, BOT_SCRIPT],
            cwd=os.getcwd(),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
    return True

def stop_bot():
    global bot_process
    if get_bot_status() == "stopped":
        return False
    
    # Terminate the process
    bot_process.terminate()
    try:
        bot_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        bot_process.kill()
    
    bot_process = None
    return True

# ========== Authentication ==========

def check_auth(request: Request) -> bool:
    """Check if user is authenticated"""
    return request.session.get("authenticated", False)

def require_auth(request: Request):
    """Raise exception if not authenticated"""
    if not check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

class LoginRequest(BaseModel):
    password: str

@app.get("/login")
async def login_page(request: Request):
    """Show login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/api/login")
async def api_login(request: Request, login: LoginRequest):
    """Handle login"""
    env_config = dotenv_values(ENV_FILE)
    correct_password = env_config.get("WEB_PASSWORD", "admin")
    
    if login.password == correct_password:
        request.session["authenticated"] = True
        return {"success": True}
    else:
        raise HTTPException(status_code=401, detail="Invalid password")

@app.post("/api/logout")
async def api_logout(request: Request):
    """Handle logout"""
    request.session.clear()
    return {"success": True}

# ========== Routes ==========

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/settings")
async def read_settings(request: Request):
    # Require authentication for settings
    if not check_auth(request):
        return RedirectResponse(url="/login?redirect=/settings")
    return templates.TemplateResponse("settings.html", {"request": request})


@app.get("/api/status")
async def api_status():
    return {"status": get_bot_status()}

@app.post("/api/start")
async def api_start(request: Request):
    require_auth(request)
    if start_bot():
        return {"message": "Bot started"}
    return JSONResponse(status_code=400, content={"message": "Bot is already running"})

@app.post("/api/stop")
async def api_stop(request: Request):
    require_auth(request)
    if stop_bot():
        return {"message": "Bot stopped"}
    return JSONResponse(status_code=400, content={"message": "Bot is not running"})

@app.post("/api/restart")
async def api_restart(request: Request):
    require_auth(request)
    stop_bot()
    time.sleep(1)
    if start_bot():
        return {"message": "Bot restarted"}
    return JSONResponse(status_code=500, content={"message": "Failed to restart bot"})

@app.get("/api/logs")
async def api_logs():
    if not os.path.exists(LOG_FILE):
        return {"logs": ""}
    
    # Read last 50 lines
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            return {"logs": "".join(lines[-50:])}
    except Exception as e:
        return {"logs": f"Error reading logs: {e}"}

@app.get("/api/config")
async def api_get_config(request: Request):
    require_auth(request)
    # Load .env config
    env_config = dotenv_values(ENV_FILE)
    
    # Load json config
    channels = []
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                channels_data = data.get('channels', [])
                # Convert list to UI format
                for c in channels_data:
                    channels.append({
                        "id": c.get('id', ''),
                        "keywords": ",".join(c.get('keywords', [])),
                        "enabled": c.get('enabled', True)
                    })
        except Exception as e:
            print(f"Error reading config.json: {e}")

    return {
        "channels": channels,
        "telegram_bot_token": env_config.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": env_config.get("TELEGRAM_CHAT_ID", "")
    }

@app.post("/api/config")
async def api_update_config(request: Request, config: ConfigUpdate):
    require_auth(request)
    # 1. Update .env
    set_key(ENV_FILE, "TELEGRAM_BOT_TOKEN", config.telegram_bot_token)
    set_key(ENV_FILE, "TELEGRAM_CHAT_ID", config.telegram_chat_id)
    
    # 2. Update config.json
    channels_data = []
    for c in config.channels:
        # Split keywords string back to list
        kw_list = [k.strip() for k in c.keywords.split(',') if k.strip()]
        channels_data.append({
            "id": c.id,
            "keywords": kw_list,
            "enabled": c.enabled
        })
    
    try:
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump({"channels": channels_data}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config.json: {e}")

    return {"message": "Config updated"}

# ... (previous code)

def kill_existing_bot():
    """Kill any existing monitor_tg.py processes to unlock the session file"""
    if sys.platform == "win32":
        os.system("taskkill /f /im monitor_tg.py 2>nul")
        os.system(f"wmic process where \"CommandLine like '%{BOT_SCRIPT}%'\" call terminate 2>nul")
    else:
        os.system(f"pkill -f {BOT_SCRIPT}")

@app.on_event("startup")
async def startup_event():
    # Cleanup any zombie processes from previous runs
    kill_existing_bot()
    # Start the bot
    start_bot()

@app.on_event("shutdown")
async def shutdown_event():
    stop_bot()

if __name__ == "__main__":
    import uvicorn
    print(f"Web UI running at http://0.0.0.0:8132")
    uvicorn.run(app, host="0.0.0.0", port=8132)
