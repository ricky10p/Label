from dotenv import load_dotenv
import os
from bot.bot_handlers import start_bot

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Telegram bot token tidak ditemukan di file .env")
    
    print("Memulai bot...")
    start_bot(TOKEN)
