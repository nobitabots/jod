import datetime
from aiogram import F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from mustjoin import check_join
from aiogram import types
import datetime


# ================== FSM ==================
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_deposit_screenshot = State()
    waiting_deposit_amount = State()
    waiting_payment_id = State()


# ================== REGISTER HANDLERS ==================
def register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):
    """Registers all recharge handlers"""

    # ----- Entry helper -----
    async def start_recharge_flow(message: Message, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.button(text="Automatic", callback_data="recharge_auto")
        kb.adjust(2)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n"
            "• Automatic payments have been stopped for security reasons.\n\n"
            "Please choose a method below:"
        )
        msg = await message.answer(text, reply_markup=kb.as_markup())
        await state.update_data(recharge_msg_id=msg.message_id)
        await state.set_state(RechargeState.choose_method)

    # ----- Start -----
    @dp.callback_query(F.data == "recharge")
    async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
        await start_recharge_flow(cq.message, state)
        await cq.answer()

    @dp.message(Command("recharge"))
    async def recharge_start_command(message: Message, state: FSMContext):
        if not await check_join(bot, message):
            return
        await start_recharge_flow(message, state)

    # ----- Manual/Auto choice -----
    @dp.callback_query(F.data == "recharge_auto", StateFilter(RechargeState.choose_method))
    async def recharge_auto(cq: CallbackQuery):
        await cq.answer(
            "⚠️ Automatic payments are temporarily disabled. Please use Manual Payment.",
            show_alert=True
        )

    @dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
    async def recharge_manual(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit Now", callback_data="deposit_now")
        kb.button(text="⬅️ Go Back", callback_data="go_back")
        kb.adjust(2)

        text = (
            f"Hello {cq.from_user.full_name},\n\n"
            "You have chosen the Manual Payment method.\n"
            "After payment, admin will verify and approve your deposit."
        )

        await bot.edit_message_text(
            chat_id=cq.from_user.id,
            message_id=msg_id,
            text=text,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    @dp.callback_query(F.data == "go_back", StateFilter(RechargeState.choose_method))
    async def recharge_go_back(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.button(text="Automatic", callback_data="recharge_auto")
        kb.adjust(2)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n"
            "• Automatic payments have been stopped for security reasons.\n\n"
            "Please choose a method below:"
        )

        await bot.edit_message_text(
            chat_id=cq.from_user.id,
            message_id=msg_id,
            text=text,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ----- Deposit now -----
    @dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.choose_method))
    async def deposit_now(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")
        try:
            await bot.delete_message(chat_id=cq.from_user.id, message_id=msg_id)
        except:
            pass

        qr_image = FSInputFile("IMG_20251008_085640_972.jpg")

        caption = (
            "🔝 Send INR to this QR Code.\n\n"
            "💳 Or Pay To:\n<pre>itsakt5@ptyes</pre>\n\n"
            "✅ After completing payment, click 'Deposit' to continue."
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="📸 Deposit", callback_data="send_deposit")
        kb.adjust(1)

        msg = await cq.message.answer_photo(
            photo=qr_image,
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await state.update_data(recharge_msg_id=msg.message_id)
        await cq.answer()

    # ----- Start deposit -----
    @dp.callback_query(F.data == "send_deposit")
    async def send_deposit(cq: CallbackQuery, state: FSMContext):
        try:
            await cq.message.delete()
        except:
            pass

        await cq.message.answer("📸 Please send a screenshot of your payment.")
        await state.set_state(RechargeState.waiting_deposit_screenshot)
        await cq.answer()

        # ===================== RECHARGE FLOW DEBUG FIX =====================

from aiogram import types
import datetime

# --- Recharge Screenshot ---
@dp.message(StateFilter(RechargeState.waiting_deposit_screenshot))
async def recharge_screenshot_received(message: types.Message, state: FSMContext):
    print("➡️ Handler: waiting_deposit_screenshot")

    if not message.photo:
        await message.answer("❌ Please send a valid screenshot image.")
        return

    await state.update_data(screenshot=message.photo[-1].file_id)
    await message.answer("💰 Enter the amount you sent (numbers only):")
    await state.set_state(RechargeState.waiting_deposit_amount)
    cur = await state.get_state()
    print(f"✅ State changed to: {cur}")

# --- Amount Input ---
@dp.message(StateFilter(RechargeState.waiting_deposit_amount))
async def recharge_amount_received(message: types.Message, state: FSMContext):
    print("➡️ Handler: waiting_deposit_amount triggered")

    amount_text = message.text.strip()
    if not amount_text.isdigit():
        await message.answer("❌ Please enter a valid number (e.g., 100).")
        return

    amount = int(amount_text)
    await state.update_data(amount=amount)
    await message.answer("🆔 Please send your Payment ID / UTR:")
    await state.set_state(RechargeState.waiting_payment_id)
    cur = await state.get_state()
    print(f"✅ State changed to: {cur}")

# --- Payment ID ---
@dp.message(StateFilter(RechargeState.waiting_payment_id))
async def recharge_payment_id_received(message: types.Message, state: FSMContext):
    print("➡️ Handler: waiting_payment_id triggered")

    payment_id = message.text.strip()
    data = await state.get_data()

    screenshot = data.get("screenshot")
    amount = data.get("amount")
    user_id = message.from_user.id

    # Temporary update
    user = users_col.find_one({"_id": user_id})
    if not user:
        users_col.insert_one({"_id": user_id, "balance": amount})
    else:
        users_col.update_one({"_id": user_id}, {"$inc": {"balance": amount}})

    await message.answer(
        f"✅ ₹{amount} added temporarily!\n"
        f"UTR: {payment_id}\n⏳ Awaiting admin verification."
    )

    await state.clear()
    print("✅ Recharge flow finished and FSM cleared.")

# --- Catch-all Debug (see what message is being received) ---
@dp.message()
async def debug_fallback(message: types.Message, state: FSMContext):
    cur = await state.get_state()
    print(f"⚠️ Unhandled message while in state: {cur} | Text: {message.text}")
