from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

def register_admin_command_handlers(dp, bot, users_col, ADMIN_IDS):
    """
    Register admin commands: /credit, /debit, /broadcast
    """

    def _is_admin(user_id: int) -> bool:
        return user_id in ADMIN_IDS

    @dp.message(Command("credit"))
    async def cmd_credit(m: Message, command: CommandObject):
        if not _is_admin(m.from_user.id):
            return
        try:
            uid, amt = command.args.split()
            uid = int(uid)
            amt = float(amt)
        except Exception:
            return await m.reply("Usage: /credit <user_id> <amount>")

        users_col.update_one({"_id": uid}, {"$inc": {"balance": amt}}, upsert=True)
        new_balance = users_col.find_one({"_id": uid})["balance"]
        await m.reply(f"Credited {amt} to {uid}. New balance: {new_balance:.2f}")

    @dp.message(Command("debit"))
    async def cmd_debit(m: Message, command: CommandObject):
        if not _is_admin(m.from_user.id):
            return
        try:
            uid, amt = command.args.split()
            uid = int(uid)
            amt = float(amt)
        except Exception:
            return await m.reply("Usage: /debit <user_id> <amount>")

        user = users_col.find_one({"_id": uid})
        if not user:
            return await m.reply("User not found.")

        new_balance = max(0.0, user.get("balance", 0.0) - amt)
        users_col.update_one({"_id": uid}, {"$set": {"balance": new_balance}})
        await m.reply(f"Debited {amt} from {uid}. New balance: {new_balance:.2f}")

    @dp.message(Command("broadcast"))
    async def cmd_broadcast(m: Message, command: CommandObject):
        if not _is_admin(m.from_user.id):
            return
        text = (command.args or "").strip()
        if not text:
            return await m.reply("Usage: /broadcast <message>")
        sent = 0
        for user in users_col.find({}):
            try:
                await bot.send_message(user["_id"], text)
                sent += 1
            except Exception:
                pass
        await m.reply(f"Broadcast sent to {sent} users.")
