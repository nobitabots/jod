import datetime
import asyncio
import requests
from requests.auth import HTTPBasicAuth
from aiogram import F, Bot, Dispatcher
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from aiogram.fsm.storage.memory import MemoryStorage

# ==============================
# Razorpay-Only Recharge System
# ==============================

class RechargeState(StatesGroup):
    choose_method = State()
    waiting_utr = State()


def register_recharge_handlers(dp: Dispatcher, bot: Bot, users_col, txns_col, ADMIN_IDS,
                               RAZORPAY_KEY, RAZORPAY_SECRET, RAZORPAY_QR_ID):
    """
    Registers only Razorpay automatic recharge flow handlers.
    """

    # ========= Start Flow =========
    async def start_recharge_flow(message: Message, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Pay via Razorpay", callback_data="razorpay_qr")
        kb.adjust(1)
        msg = await message.answer(
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via Razorpay UPI.\n\n"
            "Tap below to start:",
            reply_markup=kb.as_markup(),
        )
        await state.update_data(recharge_msg_id=msg.message_id)
        await state.set_state(RechargeState.choose_method)

    # Command entry
    @dp.message(Command("recharge"))
    async def recharge_command(message: Message, state: FSMContext):
        await start_recharge_flow(message, state)

    # ========= Razorpay QR Display =========
    @dp.callback_query(F.data == "razorpay_qr", StateFilter(RechargeState.choose_method))
    async def razorpay_qr(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        try:
            await bot.delete_message(chat_id=cq.from_user.id, message_id=msg_id)
        except:
            pass

        qr_image = FSInputFile("QrCode.jpeg.png")  # Replace with your QR file

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Done", callback_data="razorpay_done")
        kb.adjust(1)

        text = (
            "💳 <b>Razorpay Payment</b>\n\n"
            "📲 Scan this QR and make payment via any UPI app.\n\n"
            "✅ Once payment is done, tap 'Done' and send your UTR (Transaction ID) when asked."
        )

        msg = await cq.message.answer_photo(
            photo=qr_image,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        await state.update_data(recharge_msg_id=msg.message_id)
        await state.set_state(RechargeState.waiting_utr)
        await cq.answer()

    # ========= Razorpay Done Button =========
    @dp.callback_query(F.data == "razorpay_done", StateFilter(RechargeState.waiting_utr))
    async def razorpay_done(cq: CallbackQuery, state: FSMContext):
        await cq.message.answer("💬 Please send your UTR / Transaction ID to verify your payment.")
        await cq.answer()

    # ========= User Sends UTR =========
    @dp.message(StateFilter(RechargeState.waiting_utr))
    async def verify_razorpay(message: Message, state: FSMContext):
        utr = message.text.strip()
        await message.answer("⏳ Verifying your payment with Razorpay...")

        try:
            url = f"https://api.razorpay.com/v1/payments?qr_id={RAZORPAY_QR_ID}"
            res = requests.get(url, auth=HTTPBasicAuth(RAZORPAY_KEY, RAZORPAY_SECRET))
            data_rz = res.json()
        except Exception as e:
            await message.answer(f"⚠️ Razorpay API error: {e}")
            return

        verified = False
        payment_found = None

        for p in data_rz.get("items", []):
            txn_id = p.get("acquirer_data", {}).get("bank_transaction_id")
            if txn_id and utr in txn_id and p["status"] == "captured":
                verified = True
                payment_found = p
                break

        user = message.from_user

        if verified:
            amount = payment_found["amount"] / 100  # Razorpay returns paise
            users_col.update_one({"_id": user.id}, {"$inc": {"balance": amount}}, upsert=True)
            await message.answer(f"✅ Payment verified! ₹{amount} credited successfully.")
            await state.clear()
        else:
            await message.answer(
                "❌ Could not verify your payment automatically.\n"
                "Your payment has been sent for manual review."
            )

            txn_doc = {
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "utr": utr,
                "status": "pending",
                "is_razorpay": True,
                "created_at": datetime.datetime.utcnow(),
            }
            txn_id = txns_col.insert_one(txn_doc).inserted_id

            kb_admin = InlineKeyboardBuilder()
            kb_admin.button(text="✅ Approve", callback_data=f"approve_txn:{txn_id}")
            kb_admin.button(text="❌ Decline", callback_data=f"decline_txn:{txn_id}")
            kb_admin.adjust(2)

            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"<b>Manual Razorpay Verification Required</b>\n\n"
                            f"👤 Name: {user.full_name}\n"
                            f"🆔 User ID: {user.id}\n"
                            f"🌐 Username: @{user.username}\n"
                            f"💸 UTR: {utr}"
                        ),
                        parse_mode="HTML",
                        reply_markup=kb_admin.as_markup(),
                    )
                except Exception:
                    pass

            await state.clear()
