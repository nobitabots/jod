import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from pymongo import MongoClient
from datetime import datetime, timedelta
from config import API_ID, API_HASH, BOT_TOKEN
from aiogram import Bot

# ===== MongoDB Setup =====
MONGO_URI = "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority&appName=Sony0"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
numbers_col = db["numbers"]

# ===== Aiogram Bot =====
bot = Bot(token=BOT_TOKEN)

# ===== OTP Fetcher =====
async def fetch_otp_for_number(number: str, chat_id: int):
    # Get the number record
    record = numbers_col.find_one({"number": number, "used": False})
    if not record:
        await bot.send_message(chat_id, "❌ Number not found or already used.")
        return

    string_sess = record["string_session"]
    password = record["password"]

    try:
        client = TelegramClient(StringSession(string_sess), API_ID, API_HASH)

        # Connect and fetch code
        await client.start(phone=number, password=password)
        # Telethon automatically receives pending login code
        # We'll get the latest message from Telegram
        dialogs = await client.get_dialogs()
        otp = None
        for dialog in dialogs:
            messages = await client.get_messages(dialog.id, limit=5)
            for msg in messages:
                if msg.message and any(s in msg.message.lower() for s in ["code", "otp"]):
                    otp = msg.message
                    break
            if otp:
                break

        if not otp:
            otp = "❌ OTP not received. Try again."

        # Mark number as used
        numbers_col.update_one({"_id": record["_id"]}, {"$set": {"used": True, "used_at": datetime.utcnow()}})

        text = (
            f"🚚 OTP Delivered Successfully!\n\n"
            f"📱 {number}\n"
            f"🔑 OTP: {otp}\n"
            f"PASS: {password}\n\n"
            f"⚠️ This message will be deleted after 3 minutes.\n\n"
            f"👉 Please enter this OTP in Telegram X to log in.\n"
            f"If you face issues, request OTP again (max 2 times)."
        )

        msg_obj = await bot.send_message(chat_id, text)

        # Delete after 3 minutes
        await asyncio.sleep(180)
        await bot.delete_message(chat_id, msg_obj.message_id)

        await client.disconnect()
        return otp

    except Exception as e:
        await bot.send_message(chat_id, f"❌ Failed to fetch OTP: {e}")
        return None
