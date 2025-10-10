import datetime
from bson import ObjectId
from aiogram import F
from aiogram.types import CallbackQuery, Message, FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from mustjoin import check_join


# ================= Recharge FSM =================
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_deposit_screenshot = State()
    waiting_deposit_amount = State()


# ================= Recharge Flow =================
def register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):
    """
    Registers recharge handlers with calculator-style amount input.
    """

    # ===== Helper: Start Recharge Menu =====
    async def start_recharge_flow(message: Message, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.adjust(1)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n\n"
            "Please choose a method below:"
        )

        msg = await message.answer(text, reply_markup=kb.as_markup())
        await state.update_data(recharge_msg_id=msg.message_id)
        await state.set_state(RechargeState.choose_method)

    # ===== Entry Points =====
    @dp.callback_query(F.data == "recharge")
    async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
        await start_recharge_flow(cq.message, state)
        await cq.answer()

    @dp.message(Command("recharge"))
    async def recharge_start_command(message: Message, state: FSMContext):
        if not await check_join(bot, message):
            return
        await start_recharge_flow(message, state)

    # ===== Manual Recharge Selected =====
    @dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
    async def recharge_manual(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit Now", callback_data="deposit_now")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = (
            f"Hello {cq.from_user.full_name},\n\n"
            "You have chosen the manual method to add balance to your account.\n\n"
            "Your payment will be processed via admin approval."
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ===== Go Back =====
    @dp.callback_query(F.data == "go_back", StateFilter(RechargeState.choose_method))
    async def recharge_go_back(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.adjust(1)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n\n"
            "Please choose a method below:"
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ===== Deposit Now =====
    @dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.choose_method))
    async def deposit_now(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Send Screenshot", callback_data="send_deposit")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = "📸 Please send a screenshot of your payment first."
        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ===== Screenshot Received =====
    @dp.message(StateFilter(RechargeState.waiting_deposit_screenshot), F.photo)
    async def screenshot_received(message: Message, state: FSMContext):
        await state.update_data(screenshot=message.photo[-1].file_id)

        # Start calculator-style amount input
        await start_amount_input(message, state)

    async def start_amount_input(message: Message, state: FSMContext):
        await state.set_state(RechargeState.waiting_deposit_amount)
        await state.update_data(current_amount="")

        # Send initial amount message with inline buttons
        kb = generate_amount_keyboard("")
        msg = await message.answer("💰 Enter the amount you sent:\n<code>0</code>", parse_mode="HTML", reply_markup=kb.as_markup())
        await state.update_data(amount_msg_id=msg.message_id)

    def generate_amount_keyboard(current_amount: str):
        kb = InlineKeyboardBuilder()

        # Add number buttons
        for row in ["123", "456", "789", "0"]:
            for ch in row:
                kb.button(text=ch, callback_data=f"amount_{ch}")
            kb.adjust(len(row))
        # Add action buttons
        kb.button(text="❌", callback_data="amount_del")
        kb.button(text="✅", callback_data="amount_send")
        kb.adjust(2)

        return kb

    # ===== Handle Calculator Buttons =====
    @dp.callback_query(F.data.startswith("amount_"), StateFilter(RechargeState.waiting_deposit_amount))
    async def amount_button(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        current_amount = data.get("current_amount", "")
        digit = cq.data.split("_")[1]
        current_amount += digit
        await state.update_data(current_amount=current_amount)

        # Edit amount message
        amount_msg_id = data.get("amount_msg_id")
        try:
            await bot.edit_message_text(
                f"💰 Enter the amount you sent:\n<code>{current_amount}</code>",
                chat_id=cq.from_user.id,
                message_id=amount_msg_id,
                parse_mode="HTML",
                reply_markup=generate_amount_keyboard(current_amount).as_markup()
            )
        except:
            pass
        await cq.answer()

    @dp.callback_query(F.data == "amount_del", StateFilter(RechargeState.waiting_deposit_amount))
    async def amount_delete(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        current_amount = data.get("current_amount", "")
        current_amount = current_amount[:-1] if current_amount else ""
        await state.update_data(current_amount=current_amount)

        amount_msg_id = data.get("amount_msg_id")
        try:
            await bot.edit_message_text(
                f"💰 Enter the amount you sent:\n<code>{current_amount or '0'}</code>",
                chat_id=cq.from_user.id,
                message_id=amount_msg_id,
                parse_mode="HTML",
                reply_markup=generate_amount_keyboard(current_amount).as_markup()
            )
        except:
            pass
        await cq.answer()

    @dp.callback_query(F.data == "amount_send", StateFilter(RechargeState.waiting_deposit_amount))
    async def amount_send(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        current_amount = data.get("current_amount", "")
        if not current_amount:
            await cq.answer("❌ Please enter a valid amount.", show_alert=True)
            return

        await state.update_data(amount=float(current_amount))
        await cq.message.answer(f"✅ You entered ₹{current_amount}. Waiting for admin approval...")
        await cq.answer()
        await state.clear()

        # Send to admins
        screenshot = data.get("screenshot")
        user = cq.from_user
        txn_doc = {
            "user_id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "amount": float(current_amount),
            "screenshot": screenshot,
            "status": "pending",
            "created_at": datetime.datetime.utcnow()
        }
        txn_id = txns_col.insert_one(txn_doc).inserted_id

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Approve", callback_data=f"approve_txn:{str(txn_id)}")
        kb.button(text="❌ Decline", callback_data=f"decline_txn:{str(txn_id)}")
        kb.adjust(2)

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=screenshot,
                    caption=(
                        f"<b>Payment Approval Request</b>\n\n"
                        f"Name: {user.full_name}\n"
                        f"Username: @{user.username}\n"
                        f"ID: {user.id}\n"
                        f"Amount: ₹{current_amount}"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            except:
                pass
