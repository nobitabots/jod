from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import random
import string
import datetime
import traceback

# -------------------------------
# Helpers
# -------------------------------
def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def now_utc():
    return datetime.datetime.utcnow()

# -------------------------------
# Register function
# -------------------------------
def register_redeem_handlers(dp, bot, db, ADMIN_IDS):
    users_col = db["users"]
    redeem_col = db["redeem_codes"]

    # safe callback answer helper
    async def safe_cq_answer(cq: CallbackQuery, text: str = "", show_alert: bool = False):
        try:
            await cq.answer(text, show_alert=show_alert)
        except Exception:
            # ignore if query is too old / invalid
            pass

    # -------------------------------
    # User presses Redeem button (callback query)
    # -------------------------------
    @dp.callback_query(F.data == "redeem")
    async def callback_redeem(cq: CallbackQuery, state: FSMContext):
        try:
            await safe_cq_answer(cq, "✅ Send your redeem code now!", show_alert=False)
            user_id = cq.from_user.id
            now = now_utc()
            # ensure user record exists and set pending_redeem flag
            users_col.update_one(
                {"_id": user_id},
                {
                    "$setOnInsert": {"username": cq.from_user.username or None, "balance": 0.0},
                    "$set": {"pending_redeem": True, "pending_redeem_at": now}
                },
                upsert=True
            )
            await cq.message.answer("🎟️ Send your redeem code below (you have 5 minutes):")
        except Exception as e:
            print("REDEEM-DEBUG callback_redeem error:", e)
            traceback.print_exc()

    # -------------------------------
    # Catch text messages for redeem if the user has a pending_redeem flag and no active FSM
    # -------------------------------
    @dp.message(F.text & ~F.text.startswith("/"))
    async def handle_text_for_redeem(msg: Message, state: FSMContext):
        try:
            user_id = msg.from_user.id

            # if user is currently in another FSM state, ignore (other handlers will handle)
            current_state = await state.get_state()
            if current_state:
                return

            user_doc = users_col.find_one({"_id": user_id})
            if not user_doc:
                return  # no user record, nothing to do

            if not user_doc.get("pending_redeem"):
                return  # user didn't press Redeem — ignore

            # check expiry (5 minutes)
            pending_at = user_doc.get("pending_redeem_at")
            if not pending_at:
                # cleanup just in case
                users_col.update_one({"_id": user_id}, {"$unset": {"pending_redeem": "", "pending_redeem_at": ""}})
                return

            elapsed = (now_utc() - pending_at).total_seconds()
            if elapsed > 300:
                users_col.update_one({"_id": user_id}, {"$unset": {"pending_redeem": "", "pending_redeem_at": ""}})
                await msg.answer("⏳ Your redeem session expired. Please press the Redeem button again.")
                return

            code = msg.text.strip().upper()

            # find redeem doc
            redeem = redeem_col.find_one({"code": code})
            if not redeem:
                # invalid code — clear pending to avoid spam, require user to press Redeem again
                users_col.update_one({"_id": user_id}, {"$unset": {"pending_redeem": "", "pending_redeem_at": ""}})
                await msg.answer("❌ Invalid or expired redeem code.")
                return

            # atomic update: only increase if not already claimed by this user and not exceeded max_claims
            update_filter = {
                "code": code,
                "claimed_count": {"$lt": redeem["max_claims"]},
                "claimed_users": {"$ne": user_id}
            }
            update_op = {"$inc": {"claimed_count": 1}, "$push": {"claimed_users": user_id}}
            res = redeem_col.update_one(update_filter, update_op)

            if res.modified_count == 0:
                # either already claimed by this user or limit reached
                # check which
                if user_id in redeem.get("claimed_users", []):
                    await msg.answer("⚠️ You have already claimed this code.")
                else:
                    await msg.answer("🚫 This code has reached its claim limit.")
                users_col.update_one({"_id": user_id}, {"$unset": {"pending_redeem": "", "pending_redeem_at": ""}})
                return

            # credit the user's balance
            users_col.update_one({"_id": user_id}, {"$inc": {"balance": redeem["amount"]}, "$unset": {"pending_redeem": "", "pending_redeem_at": ""}})

            # fetch new balance (best-effort)
            user_after = users_col.find_one({"_id": user_id}) or {}
            new_balance = user_after.get("balance", 0.0)

            await msg.answer(
                f"✅ Code <b>{code}</b> redeemed successfully!\n💰 You received ₹{redeem['amount']:.2f}\n💰 New Balance: ₹{new_balance:.2f}",
                parse_mode="HTML"
            )
            print(f"REDEEM-DEBUG: user {user_id} redeemed {code} for ₹{redeem['amount']}")
        except Exception as e:
            print("REDEEM-DEBUG handle_text_for_redeem error:", e)
            traceback.print_exc()
            # try to cleanup pending flag to avoid stuck sessions
            try:
                users_col.update_one({"_id": msg.from_user.id}, {"$unset": {"pending_redeem": "", "pending_redeem_at": ""}})
            except Exception:
                pass

    # -------------------------------
    # Admin: Create redeem via single command with args:
    # Usage: /createredeem 50,10   <-- amount, max_claims
    # -------------------------------
    @dp.message(Command("createredeem"))
    async def cmd_create_redeem(msg: Message):
        try:
            if msg.from_user.id not in ADMIN_IDS:
                return await msg.answer("❌ Not authorized.")

            # parse inline args
            text = (msg.text or "").strip()
            parts = text.split(None, 1)
            if len(parts) < 2:
                return await msg.answer("Usage: /createredeem <amount>,<max_claims>\nExample: /createredeem 50,10")

            args = parts[1].strip()
            if "," not in args:
                return await msg.answer("Invalid format. Example: /createredeem 50,10")

            amount_str, limit_str = map(str.strip, args.split(",", 1))
            try:
                amount = float(amount_str)
                limit = int(limit_str)
                if amount <= 0 or limit <= 0:
                    raise ValueError
            except ValueError:
                return await msg.answer("Invalid numbers. Example: /createredeem 50,10")

            # generate unique code (avoid rare collision)
            for _ in range(10):
                code = generate_code(6)
                if not redeem_col.find_one({"code": code}):
                    break
            else:
                return await msg.answer("❌ Failed to generate unique code. Try again.")

            redeem_doc = {
                "code": code,
                "amount": amount,
                "max_claims": limit,
                "claimed_count": 0,
                "claimed_users": [],
                "created_at": now_utc()
            }
            redeem_col.insert_one(redeem_doc)

            await msg.answer(
                f"✅ Redeem code created!\n\n🎟️ Code: <code>{code}</code>\n💰 Amount: ₹{amount:.2f}\n👥 Max Claims: {limit}",
                parse_mode="HTML"
            )
            print(f"REDEEM-DEBUG: admin {msg.from_user.id} created code {code} amount={amount} max={limit}")
        except Exception as e:
            print("REDEEM-DEBUG cmd_create_redeem error:", e)
            traceback.print_exc()
            await msg.answer("❌ Error creating redeem code.")

    # -------------------------------
    # Admin: list redeem codes
    # -------------------------------
    @dp.message(Command("redeemlist"))
    async def cmd_redeem_list(msg: Message):
        try:
            if msg.from_user.id not in ADMIN_IDS:
                return await msg.answer("❌ Not authorized.")

            redeems = list(redeem_col.find().sort("created_at", -1))
            if not redeems:
                return await msg.answer("📭 No redeem codes found.")

            text = "🎟️ <b>Redeem Codes:</b>\n\n"
            for r in redeems:
                text += (
                    f"Code: <code>{r['code']}</code>\n"
                    f"💰 Amount: ₹{r['amount']}\n"
                    f"👥 {r.get('claimed_count',0)} / {r.get('max_claims',0)} claimed\n\n"
                )
            await msg.answer(text, parse_mode="HTML")
        except Exception as e:
            print("REDEEM-DEBUG cmd_redeem_list error:", e)
            traceback.print_exc()
            await msg.answer("❌ Error fetching list.")
