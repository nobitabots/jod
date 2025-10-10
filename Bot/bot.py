import os
import asyncio
import datetime
import html
from bson import ObjectId
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
from telethon.errors import SessionPasswordNeededError

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN_HERE"
ADMIN_IDS = [123456789]  # Replace with your Telegram ID(s)
API_ID = int(os.getenv("API_ID") or "123456")  # Telegram API ID
API_HASH = os.getenv("API_HASH") or "YOUR_API_HASH"

# ===== MongoDB Setup =====
MONGO_URI = os.getenv("MONGO_URI") or "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]
numbers_col = db["numbers"]

# ===== Bot Setup =====
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ===== FSM =====
class AddSession(StatesGroup):
    waiting_country = State()
    waiting_number = State()
    waiting_otp = State()
    waiting_password = State()

class AdminAdjustBalanceState(StatesGroup):
    waiting_input = State()

# ===== Helpers =====
def get_or_create_user(user_id: int, username: str | None):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username or None, "balance": 0.0}
        users_col.insert_one(user)
    return user

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ===== START =====
@dp.message(Command("start"))
async def cmd_start(m: Message):
    get_or_create_user(m.from_user.id, m.from_user.username)

    text = (
        "<b>Welcome to Bot – ⚡ Fastest Telegram OTP Bot!</b>\n"
        "<i>📖 How to use Bot:</i>\n"
        "1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Buy Account and 📩 Receive OTP\n"
        "🚀 Enjoy Fast OTP Services!"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💵 Balance", callback_data="balance"),
        InlineKeyboardButton(text="🛒 Buy Account", callback_data="buy")
    )
    kb.row(
        InlineKeyboardButton(text="💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton(text="🛠️ Support", url="https://t.me/iamvalrik")
    )
    kb.row(
        InlineKeyboardButton(text="📦 Your Info", callback_data="stats"),
        InlineKeyboardButton(text="🆘 How to Use?", callback_data="howto")
    )

    menu_msg = await m.answer("Loading menu...", reply_markup=None)
    await menu_msg.edit_text(text, reply_markup=kb.as_markup())

# ===== BALANCE =====
@dp.callback_query(F.data=="balance")
async def show_balance(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    await cq.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹", show_alert=True)

@dp.message(Command("balance"))
async def cmd_balance(msg: Message):
    user = users_col.find_one({"_id": msg.from_user.id})
    await msg.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹")

# ===== COUNTRY MENU =====
async def send_country_menu(message, previous=""):
    countries = list(countries_col.find({}))
    if not countries:
        return await message.edit_text("❌ No countries available.")
    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=html.escape(c["name"]), callback_data=f"country:{c['name']}")
    kb.adjust(2)
    if previous:
        kb.row(InlineKeyboardButton(text="🔙 Back", callback_data=previous))
    await message.edit_text("🌍 Select a country:", reply_markup=kb.as_markup())

@dp.callback_query(F.data=="buy")
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
        f"⚠️ Use Telegram X only to login.\n"
        f"🚫 Not responsible for freeze/ban."
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💳 Buy Now", callback_data=f"buy_now:{country_name}"),
        InlineKeyboardButton(text="🔙 Back", callback_data="buy")
    )
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

# ===== BUY NOW =====
@dp.callback_query(F.data.startswith("buy_now:"))
async def callback_buy_now(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    country = countries_col.find_one({"name": country_name})
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)
    user = get_or_create_user(cq.from_user.id, cq.from_user.username)
    if user["balance"] < country["price"]:
        return await cq.answer("⚠️ Insufficient balance", show_alert=True)
    number_doc = numbers_col.find_one({"country": country_name, "used": False})
    if not number_doc:
        return await cq.answer("❌ No available numbers for this country.", show_alert=True)
    # Deduct balance and mark used
    new_balance = user["balance"] - country["price"]
    users_col.update_one({"_id": user["_id"]}, {"$set": {"balance": new_balance}})
    numbers_col.update_one({"_id": ObjectId(number_doc["_id"])}, {"$set": {"used": True}})
    countries_col.update_one({"name": country_name}, {"$inc": {"stock": -1}})
    orders_col.insert_one({
        "user_id": user["_id"],
        "country": country_name,
        "number": number_doc["number"],
        "price": country["price"],
        "status": "purchased",
        "created_at": datetime.datetime.utcnow()
    })
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🔑 Get OTP", callback_data=f"grab_otp:{number_doc['_id']}")
    )
    text = (
        f"✅ Purchase Successful!\n\n"
        f"🌍 Country: {html.escape(country_name)}\n"
        f"📱 Your Number: {html.escape(number_doc['number'])}\n"
        f"💸 Deducted: {country['price']}\n"
        f"💰 Balance Left: {new_balance:.2f}\n\n"
        "👉 Click below to get OTP when ready."
    )
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

# ===== GRAB OTP =====
@dp.callback_query(F.data.startswith("grab_otp:"))
async def callback_grab_otp(cq: CallbackQuery):
    await cq.answer()
    _, number_id = cq.data.split(":", 1)
    number_doc = numbers_col.find_one({"_id": ObjectId(number_id)})
    if not number_doc:
        return await cq.answer("❌ Number not found", show_alert=True)
    string_session = number_doc.get("string_session")
    if not string_session:
        return await cq.answer("❌ No string session.", show_alert=True)
    client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
    await client.connect()
    try:
        code = ""
        async for msg in client.iter_messages("777000", limit=5):
            if msg.message and msg.message.isdigit():
                code = msg.message
                break
        if not code:
            await cq.answer("⚠️ No OTP received yet.", show_alert=True)
        else:
            await cq.message.answer(f"🔑 OTP for {number_doc['number']}:\n<code>{code}</code>", parse_mode="HTML")
    except SessionPasswordNeededError:
        await cq.message.answer("🔐 2FA enabled. Use password manually.")
    except Exception as e:
        await cq.message.answer(f"❌ Failed to grab OTP: {e}")
    finally:
        await client.disconnect()

# ===== ADMIN COMMANDS =====
# ADD COUNTRY
@dp.message(Command("addcountry"))
async def cmd_add_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("Send country name and price (e.g., India,50):")

@dp.message()
async def handle_add_country(msg: Message):
    if not is_admin(msg.from_user.id) or "," not in msg.text:
        return
    name, price = msg.text.split(",", 1)
    try:
        price = float(price.strip())
    except:
        return await msg.answer("❌ Invalid price.")
    countries_col.update_one({"name": name.strip()}, {"$set": {"price": price, "stock": 0}}, upsert=True)
    await msg.answer(f"✅ Country {name.strip()} added/updated with price {price}.")

# REMOVE COUNTRY
@dp.message(Command("removecountry"))
async def cmd_remove_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("Send the country name to remove:")

@dp.message()
async def handle_remove_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    countries_col.delete_one({"name": msg.text.strip()})
    await msg.answer(f"✅ Country {msg.text.strip()} removed.")

# VIEW DB
@dp.message(Command("db"))
async def cmd_db(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    numbers = numbers_col.find({})
    text = "<b>All numbers in DB:</b>\n\n"
    for n in numbers:
        text += f"📱 {n['number']} | Country: {n['country']} | Used: {n['used']}\n"
    await msg.answer(text)

# CREDIT / DEBIT
@dp.message(Command("credit"), StateFilter(None))
async def cmd_credit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("Send user_id and amount (e.g., 123456,50):")
    await state.set_state(AdminAdjustBalanceState.waiting_input)
    await state.update_data(action="credit")

@dp.message(Command("debit"), StateFilter(None))
async def cmd_debit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("Send user_id and amount (e.g., 123456,50):")
    await state.set_state(AdminAdjustBalanceState.waiting_input)
    await state.update_data(action="debit")

@dp.message(AdminAdjustBalanceState.waiting_input)
async def handle_adjust_balance(msg: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    if "," not in msg.text:
        return await msg.answer("❌ Invalid format.")
    user_id_str, amount_str = msg.text.split(",", 1)
    try:
        user_id = int(user_id_str.strip())
        amount = float(amount_str.strip())
    except:
        return await msg.answer("❌ Invalid user_id or amount.")
    user = users_col.find_one({"_id": user_id})
    if not user:
        return await msg.answer("❌ User not found.")
    if action == "credit":
        new_balance = user["balance"] + amount
        users_col.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
        await msg.answer(f"✅ Credited ₹{amount:.2f}. New balance: ₹{new_balance:.2f}")
    else:
        new_balance = max(user["balance"] - amount, 0)
        users_col.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
        await msg.answer(f"✅ Debited ₹{amount:.2f}. New balance: ₹{new_balance:.2f}")
    await state.clear()

# ===== RUNNER =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
