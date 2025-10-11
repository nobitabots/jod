import datetime, random, string, html
from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State


# ================= FSM =================
class RedeemState(StatesGroup):
    waiting_code = State()
    waiting_value = State()
    waiting_limit = State()


# ================= Helper =================
def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ================= Main Register =================
def register_redeem_handlers(dp, bot, db, ADMIN_IDS):
    users_col = db["users"]
    redeem_col = db["redeem_codes"]

    # ================= User Redeem =================
    @dp.message(Command("redeem"))
    async def start_redeem(msg: Message, state: FSMContext):
        await msg.answer("🎟️ Send your redeem code:")
        await state.set_state(RedeemState.waiting_code)

    @dp.message(StateFilter(RedeemState.waiting_code))
    async def handle_redeem_code(msg: Message, state: FSMContext):
        code = msg.text.strip().upper()
        redeem = redeem_col.find_one({"code": code})

        if not redeem:
            await state.clear()
            return await msg.answer("❌ Invalid or expired redeem code.")

        if redeem["claimed_count"] >= redeem["max_claims"]:
            await state.clear()
            return await msg.answer("🚫 This code has reached its claim limit.")

        user = users_col.find_one({"_id": msg.from_user.id})
        if not user:
            await state.clear()
            return await msg.answer("⚠️ Please use /start first.")

        if msg.from_user.id in redeem.get("claimed_users", []):
            await state.clear()
            return await msg.answer("⚠️ You have already claimed this code.")

        # Credit balance
        users_col.update_one({"_id": msg.from_user.id}, {"$inc": {"balance": redeem["amount"]}})
        redeem_col.update_one(
            {"code": code},
            {"$inc": {"claimed_count": 1}, "$push": {"claimed_users": msg.from_user.id}}
        )

        await msg.answer(
            f"✅ Code <b>{html.escape(code)}</b> redeemed successfully!\n"
            f"💰 You received ₹{redeem['amount']:.2f}",
            parse_mode="HTML"
        )
        await state.clear()

    # ================= Admin Create Redeem =================
    @dp.message(Command("createredeem"))
    async def cmd_create_redeem(msg: Message, state: FSMContext):
        if msg.from_user.id not in ADMIN_IDS:
            return await msg.answer("❌ Not authorized.")
        await msg.answer("💰 Enter the amount for this redeem code:")
        await state.set_state(RedeemState.waiting_value)

    @dp.message(StateFilter(RedeemState.waiting_value))
    async def handle_redeem_amount(msg: Message, state: FSMContext):
        try:
            amount = float(msg.text.strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            return await msg.answer("❌ Invalid amount. Send a number like 50 or 100.")

        await state.update_data(amount=amount)
        await msg.answer("👥 Enter max number of users who can claim this code:")
        await state.set_state(RedeemState.waiting_limit)

    @dp.message(StateFilter(RedeemState.waiting_limit))
    async def handle_redeem_limit(msg: Message, state: FSMContext):
        try:
            limit = int(msg.text.strip())
            if limit <= 0:
                raise ValueError
        except ValueError:
            return await msg.answer("❌ Invalid number. Send a positive integer.")

        data = await state.get_data()
        amount = data["amount"]
        code = generate_code()

        redeem_col.insert_one({
            "code": code,
            "amount": amount,
            "max_claims": limit,
            "claimed_count": 0,
            "claimed_users": [],
            "created_at": datetime.datetime.utcnow()
        })

        await msg.answer(
            f"✅ Redeem code created!\n\n"
            f"🎟️ Code: <code>{html.escape(code)}</code>\n"
            f"💰 Amount: ₹{amount:.2f}\n"
            f"👥 Max Claims: {limit}",
            parse_mode="HTML"
        )
        await state.clear()

    # ================= Admin View Redeems =================
    @dp.message(Command("redeemlist"))
    async def cmd_redeem_list(msg: Message):
        if msg.from_user.id not in ADMIN_IDS:
            return await msg.answer("❌ Not authorized.")

        redeems = list(redeem_col.find())
        if not redeems:
            return await msg.answer("📭 No redeem codes found.")

        text = "🎟️ <b>Active Redeem Codes:</b>\n\n"
        for r in redeems:
            text += (
                f"Code: <code>{html.escape(r['code'])}</code>\n"
                f"💰 Amount: ₹{r['amount']}\n"
                f"👥 {r['claimed_count']} / {r['max_claims']} claimed\n\n"
            )
        await msg.answer(text, parse_mode="HTML")
