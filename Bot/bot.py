import os
import asyncio
import datetime
import html
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession

from recharge_flow import register_recharge_handlers
from readymade_accounts import register_readymade_accounts_handlers
from mustjoin import check_join
from otp_fetcher import fetch_otp_for_number  # Your module
from config import BOT_TOKEN, ADMIN_IDS, API_ID, API_HASH

# ===== MongoDB Setup =====
MONGO_URI = os.getenv("MONGO_URI") or "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority&appName=Sony0"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]
numbers_col = db["numbers"]
txns_col = db["transactions"]

# ===== Bot Setup =====
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ===== FSM for Admin Adding Number =====
class AddNumberStates(StatesGroup):
    waiting_country = State()
    waiting_number = State()
    waiting_password = State()

# ===== Helpers =====
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_or_create_user(user_id: int, username: str | None):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username, "balance": 0.0}
        users_col.insert_one(user)
    return user

# ===== START =====
@dp.message(Command("start"))
async def cmd_start(m: Message):
    if not await check_join(bot, m):
        return

    get_or_create_user(m.from_user.id, m.from_user.username)

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton("💵 Balance", callback_data="balance"),
        InlineKeyboardButton("🛒 Buy Account", callback_data="buy")
    )
    kb.row(
        InlineKeyboardButton("💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton("🛠️ Support", url="https://t.me/iamvalrik")
    )
    kb.row(
        InlineKeyboardButton("📦 Your Info", callback_data="stats"),
        InlineKeyboardButton("🆘 How to Use?", callback_data="howto")
    )
    text = (
        "<b>Welcome to Bot – ⚡ Fastest Telegram OTP Bot!</b>\n"
        "<i>📖 How to use Bot:</i>\n"
        "1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Buy Account and 📩 Receive OTP\n"
        "🚀 Enjoy Fast OTP Services!"
    )
    await m.answer(text, reply_markup=kb.as_markup())

# ===== Balance =====
@dp.callback_query(F.data == "balance")
async def callback_balance(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    await cq.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹", show_alert=True)

# ===== Buy Flow =====
async def send_country_menu(message, previous=""):
    countries = list(countries_col.find({}))
    if not countries:
        return await message.edit_text("❌ No countries available. Admin must add stock first.")
    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=html.escape(c["name"]), callback_data=f"country:{c['name']}")
    kb.adjust(2)
    if previous:
        kb.row(InlineKeyboardButton("🔙 Back", callback_data=previous))
    await message.edit_text("🌍 Select a country:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy")
async def callback_buy(cq: CallbackQuery):
    await cq.answer()
    await send_country_menu(cq.message, previous="start_menu")

@dp.callback_query(F.data.startswith("country:"))
async def callback_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    country = countries_col.find_one({"name": country_name})
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)

    text = (
        f"⚡ Telegram Account Info\n\n"
        f"🌍 Country : {html.escape(country['name'])}\n"
        f"💸 Price : ₹{country['price']}\n"
        f"📦 Available : {country['stock']}\n"
        f"🔍 Reliable | Affordable | Good Quality\n\n"
        f"⚠️ Use Telegram X only to login.\n"
        f"🚫 Not responsible for freeze/ban."
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton("💳 Buy Now", callback_data=f"buy_now:{country_name}"),
        InlineKeyboardButton("🔙 Back", callback_data="buy")
    )
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_now:"))
async def callback_buy_now(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    country = countries_col.find_one({"name": country_name})
    if not country or country["stock"] <= 0:
        return await cq.answer("❌ Out of stock or country not found", show_alert=True)

    user = get_or_create_user(cq.from_user.id, cq.from_user.username)
    if user["balance"] < country["price"]:
        return await cq.answer("⚠️ Insufficient balance", show_alert=True)

    number_doc = numbers_col.find_one({"country": country_name, "used": False})
    if not number_doc:
        return await cq.answer("❌ No available numbers for this country.", show_alert=True)

    # Deduct and mark used
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -country["price"]}})
    numbers_col.update_one({"_id": number_doc["_id"]}, {"$set": {"used": True}})
    countries_col.update_one({"name": country_name}, {"$inc": {"stock": -1}})

    orders_col.insert_one({
        "user_id": user["_id"],
        "country": country_name,
        "number": number_doc["number"],
        "price": country["price"],
        "status": "purchased",
        "created_at": datetime.datetime.utcnow()
    })

    text = (
        f"✅ Purchase Successful!\n\n"
        f"🌍 Country: {html.escape(country_name)}\n"
        f"📱 Number: {html.escape(number_doc['number'])}\n"
        f"💸 Deducted: {country['price']}\n"
        f"💰 Balance Left: {user['balance'] - country['price']:.2f}\n\n"
        "👉 Copy the number and open Telegram X, paste the number, request login."
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_number:{number_doc['number']}"),
        InlineKeyboardButton("🔑 Get OTP", callback_data=f"get_otp:{number_doc['_id']}")
    )
    kb.row(InlineKeyboardButton("🔙 Back", callback_data=f"country:{country_name}"))
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

# ===== Get OTP =====
@dp.callback_query(F.data.startswith("get_otp:"))
async def callback_get_otp(cq: CallbackQuery):
    await cq.answer()
    _, number_id = cq.data.split(":", 1)
    number_doc = numbers_col.find_one({"_id": number_id})
    if not number_doc:
        return await cq.answer("❌ Number not found", show_alert=True)

    otp = await fetch_otp_for_number(number_doc)
    if not otp:
        return await cq.answer("❌ Failed to fetch OTP. Try again.", show_alert=True)

    text = (
        f"🚚 OTP Delivered Successfully!\n\n"
        f"📱 {html.escape(number_doc['number'])}\n"
        f"🔑 OTP: {otp}\n"
        f"PASS: {html.escape(number_doc['password'])}\n\n"
        "⚠️ This message will be deleted after 3 minutes.\n"
        "👉 Enter this OTP in Telegram X. Max 2 attempts."
    )
    msg = await cq.message.answer(text)
    numbers_col.delete_one({"_id": number_doc["_id"]})
    await asyncio.sleep(180)
    await msg.delete()

# ===== Admin Add Number =====
@dp.message(Command("addnumber"))
async def cmd_add_number(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    await msg.answer("Enter country for the new number:")
    await state.set_state(AddNumberStates.waiting_country)

@dp.message(AddNumberStates.waiting_country)
async def add_number_country(msg: Message, state: FSMContext):
    await state.update_data(country=msg.text.strip())
    await msg.answer("Enter Telegram number (with country code, e.g., +911234567890):")
    await state.set_state(AddNumberStates.waiting_number)

@dp.message(AddNumberStates.waiting_number)
async def add_number_number(msg: Message, state: FSMContext):
    await state.update_data(number=msg.text.strip())
    await msg.answer("Enter password for this number:")
    await state.set_state(AddNumberStates.waiting_password)

@dp.message(AddNumberStates.waiting_password)
async def add_number_password(msg: Message, state: FSMContext):
    data = await state.get_data()
    country, number, password = data["country"], data["number"], msg.text.strip()

    # Generate empty string session placeholder
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    session_str = StringSession().save()
    await client.disconnect()

    numbers_col.insert_one({
        "country": country,
        "number": number,
        "password": password,
        "string_session": session_str,
        "used": False
    })
    countries_col.update_one({"name": country}, {"$setOnInsert": {"stock": 0, "price": 0}}, upsert=True)
    await msg.answer(f"✅ Number {number} added for {country} with string session.")
    await state.clear()

# ===== Register external handlers =====
register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS)
register_readymade_accounts_handlers(dp, bot, users_col)

# ===== Main Runner =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
