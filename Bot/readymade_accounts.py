import json
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import TelegramClient
from telethon.sessions import StringSession

# Environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "account.json")


def register_readymade_accounts_handlers(dp: Dispatcher, bot: Bot, users_col):
    
    # ------------------- Helper Functions -------------------
    def load_accounts():
        if not os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_accounts(data):
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    async def otp_searcher(strses: str):
        async with TelegramClient(StringSession(strses), API_ID, API_HASH) as client:
            code = ""
            try:
                async for msg in client.iter_messages(777000, limit=1, search="Login code"):
                    match = re.search(r'\b\d{5}\b', msg.message)
                    if match:
                        code += f"YOUR ACCESS CODE IS {match.group()}"
            except:
                pass
            if not code:
                return "❌ OTP NOT FOUND. TRY AGAIN LATER."
            return code

    if not hasattr(dp, "data"):
        dp.data = {}

    # ------------------- Show Countries -------------------
    @dp.callback_query(F.data == "readymade_accounts")
    async def callback_readymade_accounts(cq: CallbackQuery):
        data = load_accounts()
        countries = list(data.keys())
        if not countries:
            await cq.message.answer("❌ No ready-made accounts available yet.")
            await cq.answer()
            return

        kb = InlineKeyboardBuilder()
        for country in countries:
            kb.button(text=country.capitalize(), callback_data=f"rmacct_country:{country}")
        kb.adjust(2)

        # Send new message for country selection
        await cq.message.answer(
            "✨ Select Account Type 👇\n\n🛒 Ready-made accounts available:",
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ------------------- Country Selected -------------------
    @dp.callback_query(F.data.startswith("rmacct_country:"))
    async def callback_rmacct_country(cq: CallbackQuery):
        _, country = cq.data.split(":")
        data = load_accounts()
        country_accounts = [a for a in data.get(country, []) if not a.get("used", False)]
        price = 60
        available = len(country_accounts)

        text = (
            f"⚡ Telegram Account Info\n\n"
            f"🌍 Country :  {country}\n"
            f"💸 Price : ₹{price}\n"
            f"📦 Available : {available}\n"
            "🔍 Reliable | Affordable | Good Quality\n\n"
            "⚠️ Important: Please use Telegram X only to login.\n"
            "🚫 We are not responsible for any freeze/ban if logged in with other apps"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="Buy Now", callback_data=f"rmacct_buy:{country}:{price}")
        kb.button(text="⬅ Back", callback_data="readymade_accounts")
        kb.adjust(2)
        await cq.message.edit_text(text, reply_markup=kb.as_markup())
        await cq.answer()

    # ------------------- Buy Now -------------------
    @dp.callback_query(F.data.startswith("rmacct_buy:"))
    async def callback_rmacct_buy(cq: CallbackQuery):
        _, country, price = cq.data.split(":")
        price = float(price)
        dp.data[cq.from_user.id] = {
            "country": country,
            "price": price,
            "step": "quantity",
            "message_id": cq.message.message_id,
            "chat_id": cq.message.chat.id
        }

        await cq.message.edit_text(
            f"📦 Send how many {country} accounts you want to buy.\n📝 Only numbers (e.g., 5, 10)"
        )
        await cq.answer()

    # ------------------- Handle Quantity -------------------
    @dp.message(F.text)
    async def handle_quantity(msg: Message):
        state = dp.data.get(msg.from_user.id)
        if not state or state.get("step") != "quantity":
            return

        if not msg.text.isdigit():
            await msg.reply("❌ Invalid input. Send only numbers (e.g., 5, 10).")
            return

        quantity = int(msg.text)
        country = state["country"]
        price = state["price"]
        total_cost = price * quantity

        user = users_col.find_one({"_id": msg.from_user.id})
        if not user:
            await msg.reply("❌ User not found in DB.")
            return

        if user["balance"] < total_cost:
            kb = InlineKeyboardBuilder()
            kb.button(text="💳 Add Funds", callback_data="recharge")
            kb.adjust(1)
            await msg.reply(
                f"🚫 Insufficient Balance!\n💰 Your Balance: ₹{user['balance']}\n🧾 Total Required: ₹{total_cost}",
                reply_markup=kb.as_markup()
            )
            return

        # Deduct balance
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -total_cost}})

        # Fetch accounts
        data = load_accounts()
        country_accounts = [a for a in data.get(country, []) if not a.get("used", False)]

        if quantity > len(country_accounts):
            await msg.reply(f"❌ Only {len(country_accounts)} accounts available for {country}.")
            return

        allocated_accounts = country_accounts[:quantity]
        for acc in allocated_accounts:
            acc["used"] = True
        save_accounts(data)

        # Send accounts one by one with short callback codes
        for idx, acc in enumerate(allocated_accounts, start=1):
            cb_code = f"{country[:2]}_{idx}"
            dp.data[cb_code] = acc  # Map code to session

            kb = InlineKeyboardBuilder()
            kb.button(text="Get OTP", callback_data=f"rmacct_otp:{cb_code}")
            kb.button(text="❌ Cancel", callback_data=f"rmacct_cancel:{cb_code}")
            kb.adjust(2)

            await msg.reply(
                f"📦 Account Allocated\n\nNumber: {acc['number']}\n💸 Price: ₹{price}",
                reply_markup=kb.as_markup()
            )

        dp.data.pop(msg.from_user.id, None)

    # ------------------- OTP Fetch -------------------
    @dp.callback_query(F.data.startswith("rmacct_otp:"))
    async def callback_rmacct_otp(cq: CallbackQuery):
        cb_code = cq.data.split(":")[1]
        acc = dp.data.get(cb_code)
        if not acc:
            await cq.message.answer("❌ This account is no longer available.")
            await cq.answer()
            return

        if acc.get("otp_received", False):
            await cq.message.answer("⚠️ OTP already received. Order completed.")
            await cq.answer()
            return

        await cq.message.answer("⏳ Fetching OTP, please wait...")
        otp_code = await otp_searcher(acc["session"])
        if otp_code:
            acc["otp_received"] = True
            # Save back to JSON
            data = load_accounts()
            for country_accs in data.values():
                for c_acc in country_accs:
                    if c_acc["session"] == acc["session"]:
                        c_acc["otp_received"] = True
            save_accounts(data)
            await cq.message.answer(f"📩 OTP Received: {otp_code}")
        else:
            await cq.message.answer("❌ OTP not found. Try again later.")
        await cq.answer()

    # ------------------- Cancel -------------------
    @dp.callback_query(F.data.startswith("rmacct_cancel:"))
    async def callback_rmacct_cancel(cq: CallbackQuery):
        cb_code = cq.data.split(":")[1]
        acc = dp.data.get(cb_code)
        if not acc:
            await cq.message.answer("❌ Account already completed or cancelled.")
            await cq.answer()
            return

        if acc.get("otp_received", False):
            await cq.message.answer("⚠️ Cannot cancel. OTP already received. Order completed.")
            await cq.answer()
            return

        # Refund balance
        price = 60
        users_col.update_one({"_id": cq.from_user.id}, {"$inc": {"balance": price}})

        # Mark as not used
        acc["used"] = False
        data = load_accounts()
        for country_accs in data.values():
            for c_acc in country_accs:
                if c_acc["session"] == acc["session"]:
                    c_acc["used"] = False
        save_accounts(data)

        # Remove inline buttons
        try:
            await cq.message.edit_reply_markup(None)
        except:
            pass

        await cq.message.answer(f"❌ Account cancelled and balance refunded: ₹{price}")
        await cq.answer()

    # ------------------- Admin /addstock -------------------
    @dp.message(F.text.startswith("/addstock"))
    async def cmd_add_stock(msg: Message):
        user_id = msg.from_user.id
        dp.data[user_id] = {"step": "country"}
        await msg.reply("🛠️ Admin Add Stock - Enter country:")

    @dp.message(F.text)
    async def handle_addstock_steps(msg: Message):
        user_id = msg.from_user.id
        if user_id not in dp.data or "step" not in dp.data[user_id]:
            return

        step_data = dp.data[user_id]
        step = step_data["step"]

        if step == "country":
            step_data["country"] = msg.text.lower()
            step_data["step"] = "number"
            await msg.reply("Enter the account number:")
        elif step == "number":
            step_data["number"] = msg.text
            step_data["step"] = "session"
            await msg.reply("Enter the string session for this account:")
        elif step == "session":
            step_data["session"] = msg.text
            data = load_accounts()
            country = step_data["country"]
            if country not in data:
                data[country] = []
            data[country].append({
                "number": step_data["number"],
                "session": step_data["session"],
                "used": False,
                "otp_received": False
            })
            save_accounts(data)
            await msg.reply(f"✅ Stock added for country {country}.")
            dp.data.pop(user_id, None)
