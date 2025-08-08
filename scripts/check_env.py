import os
from config import Config

MASK = "***"

def presence(name: str) -> str:
    val = os.getenv(name, "")
    return "present" if bool(val) else "missing"

if __name__ == "__main__":
    # dotenv is loaded inside Config
    print("Config validation:", "OK" if Config.validate() else "FAIL")
    keys = [
        "TELEGRAM_BOT_TOKEN",
        "MEXC_API_KEY",
        "MEXC_SECRET_KEY",
        "COINGLASS_API_KEY",
        "GEMINI_API_KEY",
    ]
    for k in keys:
        print(f"{k}: {presence(k)}")
