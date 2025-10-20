import datetime
import asyncio
import requests
from requests.auth import HTTPBasicAuth
from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from aiogram.fsm.storage.memory import MemoryStorage

# === CONFIG ===
BOT_TOKEN = "YOUR_BOT_TOKEN"
RAZORPAY_KEY = "YOUR_RAZORPAY_KEY"
RAZORPAY_SECRET = "YOUR_RAZORPAY_SECRET"
RAZORPAY_QR_ID = "YOUR_RAZORPAY_QR_ID"  # from Razorpay Dashboard

ADMIN_IDS = [123456789]  # Replace with your Telegram ID
USERS_DB = {}  # simple in-memory dict for testing

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# === STATES ===
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_utr = State()

# === COMMAND ===
@dp.message(Command("recharge"))
async def start_recharge(message: Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="Razorpay", callback_data="razorpay_qr")
    kb.adjust(1)
    await message.answer(
        "💰 Add Funds to Your Account\n\nChoose your payment method:",
        reply_markup=kb.as_markup(),
    )
    await state.set_state(RechargeState.choose_method)


# === RAZORPAY QR FLOW ===
@dp.callback_query(F.data == "razorpay_qr", StateFilter(RechargeState.choose_method))
async def razorpay_qr(cq: CallbackQuery, state: FSMContext):
    qr_image = FSInputFile("QrCode.jpeg.png")  # replace with your QR image

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Done", callback_data="razorpay_done")
    kb.adjust(1)

    text = (
        "💳 <b>Razorpay Payment</b>\n\n"
        "📲 Scan this QR and make payment via any UPI app.\n\n"
        "✅ Once payment is done, tap 'Done' and send your UTR (Transaction ID) when asked."
    )

    await cq.message.answer_photo(
        photo=qr_image,
        caption=text,
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await state.set_state(RechargeState.waiting_utr)
    await cq.answer()


# === USER SENDS UTR ===
@dp.callback_query(F.data == "razorpay_done", StateFilter(RechargeState.waiting_utr))
async def razorpay_done(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("💬 Please send your UTR / Transaction ID to verify your payment.")
    await cq.answer()


@dp.message(StateFilter(RechargeState.waiting_utr))
async def verify_razorpay(message: Message, state: FSMContext):
    utr = message.text.strip()
    await message.answer("⏳ Verifying your payment with Razorpay...")

    try:
        url = f"https://api.razorpay.com/v1/payments?qr_id={RAZORPAY_QR_ID}"
        res = requests.get(url, auth=HTTPBasicAuth(RAZORPAY_KEY, RAZORPAY_SECRET))
        data_rz = res.json()
    except Exception as e:
        await message.answer(f"⚠️ API Error: {e}")
        return

    verified = False
    payment_found = None

    for p in data_rz.get("items", []):
        txn_id = p.get("acquirer_data", {}).get("bank_transaction_id")
        if txn_id and utr in txn_id and p["status"] == "captured":
            verified = True
            payment_found = p
            break

    if verified:
        amount = payment_found["amount"] / 100  # Razorpay returns paise
        user_id = message.from_user.id
        USERS_DB[user_id] = USERS_DB.get(user_id, 0) + amount
        await message.answer(f"✅ Payment verified! ₹{amount} credited successfully.")
        await state.clear()
    else:
        await message.answer(
            "❌ Could not verify your payment automatically.\n"
            "Your payment has been sent for manual review."
        )

        txn_doc = {
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "full_name": message.from_user.full_name,
            "utr": utr,
            "status": "pending",
            "created_at": datetime.datetime.utcnow(),
        }

        kb_admin = InlineKeyboardBuilder()
        kb_admin.button(text="✅ Approve", callback_data="approve_txn")
        kb_admin.button(text="❌ Decline", callback_data="decline_txn")
        kb_admin.adjust(2)

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"<b>Manual Razorpay Verification Required</b>\n\n"
                        f"Name: {message.from_user.full_name}\n"
                        f"Username: @{message.from_user.username}\n"
                        f"UTR: {utr}"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb_admin.as_markup(),
                )
            except Exception:
                pass

        await state.clear()


# === START BOT ===
if __name__ == "__main__":
    import asyncio
    from aiogram import executor

    async def main():
        print("🤖 Razorpay Recharge Bot Started")
        await dp.start_polling(bot)

    asyncio.run(main())
