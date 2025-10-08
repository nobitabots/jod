from bson import ObjectId
from aiogram import F
from aiogram.types import CallbackQuery

def register_admin_approval_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):
    """
    Registers approve/decline handlers for admin to approve recharge transactions.
    """

    @dp.callback_query(F.data.startswith("approve_txn"))
    async def approve_txn(cq: CallbackQuery):
        if cq.from_user.id not in ADMIN_IDS:
            return await cq.answer("You are not authorized.", show_alert=True)

        txn_id = cq.data.split(":")[1]
        try:
            txn = txns_col.find_one({"_id": ObjectId(txn_id)})
        except Exception:
            txn = None

        if not txn or txn.get("status") != "pending":
            return await cq.answer("Transaction already processed or not found.", show_alert=True)

        users_col.update_one({"_id": txn["user_id"]}, {"$inc": {"balance": txn["amount"]}})
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "approved", "approved_by": cq.from_user.id}})

        # Edit admin photo caption (if exists)
        try:
            if cq.message and cq.message.caption is not None:
                await cq.message.edit_caption(cq.message.caption + "\n\n✅ Approved")
        except Exception:
            pass

        try:
            await bot.send_message(txn["user_id"], f"✅ Your payment request of {txn['amount']} ₹ has been approved!")
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("decline_txn"))
    async def decline_txn(cq: CallbackQuery):
        if cq.from_user.id not in ADMIN_IDS:
            return await cq.answer("You are not authorized.", show_alert=True)

        txn_id = cq.data.split(":")[1]
        try:
            txn = txns_col.find_one({"_id": ObjectId(txn_id)})
        except Exception:
            txn = None

        if not txn or txn.get("status") != "pending":
            return await cq.answer("Transaction already processed or not found.", show_alert=True)

        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "declined", "declined_by": cq.from_user.id}})
        try:
            if cq.message and cq.message.caption is not None:
                await cq.message.edit_caption(cq.message.caption + "\n\n❌ Declined")
        except Exception:
            pass

        try:
            await bot.send_message(
                txn["user_id"],
                "❌ Your payment request was declined. Please contact support at @hehe_stalker or write your query there."
            )
        except Exception:
            pass
