import os
import asyncio
import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pymongo import MongoClient

# External modules
from readymade_accounts import register_readymade_accounts_handlers
from mustjoin import check_join
from config import BOT_TOKEN, ADMIN_IDS, DEFAULT_CURRENCY, MIN_BALANCE_REQUIRED

# ===== MongoDB Setup =====
MONGO_URI = "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority&appName=Sony0"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]  # New collection to store Telegram country stock & price

# ===== Bot Setup =====
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ===== Helpers =====
def get_or_create_user(user_id: int, username: str | None):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username or None, "balance": 0.0}
        users_col.insert_one(user)
    return user

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ===== START Command =====
@dp.message(Command("start"))
async def cmd_start(m: Message):
    if not await check_join(bot, m):
        return

    get_or_create_user(m.from_user.id, m.from_user.username)

    await m.answer("🧑‍💻")
    text = (
        "<b>Welcome to Bot – ⚡ Most Trusted and Fastest OTP Bot!</b>\n"
        "<i><blockquote>📖 How to use Bot:</blockquote></i>\n"
        "<blockquote expandable>1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Click on Purchase and 📩 Receive OTP</blockquote>\n"
        "🚀 Enjoy Fast OTP Services<a href=\"https://files.catbox.moe/c1pxci.mp4\">!</a>"
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
        InlineKeyboardButton(text="FAKE BUTTON", url="tg://setting"),
        InlineKeyboardButton(text="📦 Your Info", callback_data="stats")
    )
    kb.row(InlineKeyboardButton(text="🆘 How to Use?", callback_data="howto"))
    await m.answer(text, reply_markup=kb.as_markup())

# ===== Balance =====
@dp.callback_query(F.data == "balance")
async def show_balance(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    bal = user["balance"] if user else 0.0
    await cq.answer(f"💰 Your balance: {bal:.2f} ₹", show_alert=True)

@dp.message(Command("balance"))
async def cmd_balance(msg: Message):
    user = users_col.find_one({"_id": msg.from_user.id})
    bal = user["balance"] if user else 0.0
    await msg.answer(f"💰 Your balance: {bal:.2f} ₹")

# ===== Telegram Purchase Flow =====
@dp.callback_query(F.data == "buy")
async def callback_buy(cq: CallbackQuery):
    await cq.answer()
    kb = InlineKeyboardBuilder()
    countries = list(countries_col.find({}))
    if not countries:
        return await cq.message.answer("❌ No countries available. Admin must add stock first.")
    for country in countries:
        kb.button(text=country["name"], callback_data=f"country:{country['name']}")
    kb.adjust(2)
    await cq.message.edit_text("🌍 Select a country:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("country:"))
async def callback_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":")
    country = countries_col.find_one({"name": country_name})
    if not country:
        return await cq.answer("❌ Country not found.", show_alert=True)

    text = (
        f"⚡ Telegram Account Info\n\n"
        f"🌍 Country : {country['name']}\n"
        f"💸 Price : ₹{country['price']}\n"
        f"📦 Available : {country['stock']}\n"
        f"🔍 Reliable | Affordable | Good Quality\n\n"
        f"⚠️ Important: Please use Telegram X only to login.\n"
        f"🚫 We are not responsible for freeze/ban if logged in with other apps."
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💳 Buy Now", callback_data=f"buy_now:{country_name}"),
        InlineKeyboardButton(text="🔙 Back", callback_data="buy")
    )
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_now:"))
async def callback_buy_now(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":")
    country = countries_col.find_one({"name": country_name})
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)

    user = get_or_create_user(cq.from_user.id, cq.from_user.username)

    if user["balance"] < country["price"]:
        return await cq.answer("⚠️ Insufficient balance.", show_alert=True)
    if country["stock"] <= 0:
        return await cq.answer("❌ Out of stock.", show_alert=True)

    users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -country["price"]}})
    countries_col.update_one({"name": country_name}, {"$inc": {"stock": -1}})

    order_doc = {
        "user_id": user["_id"],
        "country": country_name,
        "price": country["price"],
        "status": "completed",
        "created_at": datetime.datetime.utcnow()
    }
    orders_col.insert_one(order_doc)

    await cq.answer("✅ Purchase successful!", show_alert=True)
    await cq.message.edit_text(
        f"✅ Telegram account purchased!\n\n"
        f"🌍 Country: {country_name}\n"
        f"💰 Price: ₹{country['price']}"
    )

# ===== Admin: Add Stock =====
@dp.message(Command("add_stock"))
async def cmd_add_stock(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ You are not authorized to use this command.")
    try:
        _, country_name, price, stock = msg.text.split()
        price = float(price)
        stock = int(stock)
    except Exception:
        return await msg.answer("Usage: /add_stock <Country> <Price> <Stock>")

    countries_col.update_one(
        {"name": country_name},
        {"$set": {"price": price}, "$inc": {"stock": stock}},
        upsert=True
    )
    await msg.answer(f"✅ {stock} accounts added for {country_name} at ₹{price} each.")

# ===== Other Callbacks =====
@dp.callback_query(F.data == "howto")
async def callback_howto(cq: CallbackQuery):
    if not await check_join(bot, cq.message): return
    await cq.message.answer(
        "<b>📖 How to use QuickCodes Bot</b>\n1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Click Purchase and 📩 Receive OTP\n\n"
        "✅ Done!\n🚀 Enjoy Fast OTP Services!\nNeed help? DM @Hehe_stalker"
    )
    await cq.answer()

# ===== Stats =====
@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not await check_join(bot, msg): return
    user = users_col.find_one({"_id": msg.from_user.id})
    if not user: return await msg.answer("❌ No data found for your account.")
    text = (
        f"📊 <b>Your Statistics</b>\n\n👤 Name: {msg.from_user.full_name}\n"
        f"🔹 Username: @{msg.from_user.username or '—'}\n🆔 User ID: <code>{msg.from_user.id}</code>\n"
        f"💰 Balance: ₹{user.get('balance', 0):.2f}\n"
    )
    await msg.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "stats")
async def callback_stats(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    if not user: return await cq.answer("❌ No data found for your account.", show_alert=True)
    text = (
        f"📊 <b>Your Statistics</b>\n\n👤 Name: {cq.from_user.full_name}\n"
        f"🔹 Username: @{cq.from_user.username or '—'}\n🆔 User ID: <code>{cq.from_user.id}</code>\n"
        f"💰 Balance: ₹{user.get('balance', 0):.2f}\n"
    )
    await cq.message.answer(text, parse_mode="HTML")
    await cq.answer()

# ===== Support =====
@dp.message(Command("support"))
async def cmd_support(msg: Message):
    if not await check_join(bot, msg): return
    text = f"👋 Hey {msg.from_user.full_name},\n\nIf you have any queries, feel free to contact our support."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Contact Support", url="https://t.me/hehe_stalker")],
        [InlineKeyboardButton(text="📖 Terms of Use", url="https://telegra.ph/Terms-of-Use--Quick-Codes-Bot-08-31")]
    ])
    await msg.answer(text, reply_markup=kb)

# ===== Register external handlers =====
register_readymade_accounts_handlers(dp=dp, bot=bot, users_col=users_col)

# ===== Runner =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
