import os
import json
import uuid
import time
from datetime import datetime
import phonenumbers

# Adjust these paths to your repo layout
BASE_DIR = os.path.dirname(__file__)
SALES_FILE = os.path.join(BASE_DIR, "sales.json")
PRICING_FILE = os.path.join(BASE_DIR, "pricing.json")

# Admin IDs list - replace with your admins
ADMIN_IDS = [111111111]

# Simple in-memory state for demonstration; replace with FSM/store if you have one
user_state = {}

# ---------- file helpers ----------
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_sales():
    return load_json(SALES_FILE, {})

def save_sales(data):
    save_json(SALES_FILE, data)

def load_pricing():
    return load_json(PRICING_FILE, {"default_price": 30.0, "prices": {}})

def save_pricing(data):
    save_json(PRICING_FILE, data)

def make_listing_id():
    return f"L{int(time.time())}_{uuid.uuid4().hex[:6]}"

def make_token():
    return uuid.uuid4().hex[:8]

# ---------- pricing helpers ----------
def get_country_code_from_number(number_e164):
    """
    Returns the ISO country code (e.g., 'IN', 'US') for an E.164 number string.
    Returns None if it can't parse.
    """
    try:
        n = phonenumbers.parse(number_e164, None)
        region = phonenumbers.region_code_for_number(n)
        return region  # e.g., 'IN'
    except Exception:
        return None

def lookup_price_for_number(number_e164):
    pricing = load_pricing()
    country = get_country_code_from_number(number_e164)
    if country:
        price = pricing.get("prices", {}).get(country)
        if price is not None:
            return float(price), country
    # fallback to default
    return float(pricing.get("default_price", 30.0)), country

# ---------- bot handlers (pseudo/aiogram style) ----------
# Note: Replace decorator/handler glue to match your bot framework.

@dp.message_handler(commands=['sell_account'])
async def cmd_sell_account(message):
    """
    Start sell flow — seller must send only the phone number in E.164 format.
    """
    user_state[message.from_user.id] = {"step": "await_sell_number"}
    await message.reply(
        "🛒 Sell account — Send the phone number (only) in international format (E.164).\n"
        "Example: `+919876543210`\n\n"
        "Do NOT include price — price will be assigned automatically based on the account's country."
    )

@dp.message_handler(func=lambda m: user_state.get(m.from_user.id, {}).get("step") == "await_sell_number")
async def handle_sell_number(message):
    txt = message.text.strip()
    uid = message.from_user.id

    # Validate E.164 / parse the number
    try:
        numobj = phonenumbers.parse(txt, None)
        if not phonenumbers.is_possible_number(numobj):
            raise ValueError("not possible")
    except Exception:
        await message.reply("❌ Couldn't parse that phone number. Send in E.164 format like `+919876543210`.")
        return

    number_e164 = phonenumbers.format_number(numobj, phonenumbers.PhoneNumberFormat.E164)
    # Lookup price automatically
    assigned_price, country = lookup_price_for_number(number_e164)
    country_display = country if country else "Unknown"

    # Create listing
    token = make_token()
    lid = make_listing_id()
    sales = load_sales()
    sales[lid] = {
        "listing_id": lid,
        "number": number_e164,
        "price": assigned_price,
        "currency": "INR",               # change if you support multi-currency
        "seller_id": uid,
        "status": "awaiting_confirmation",
        "token": token,
        "country": country_display,
        "created_at": datetime.utcnow().isoformat()
    }
    save_sales(sales)
    user_state.pop(uid, None)

    await message.reply(
        f"✅ Listing created temporarily for {number_e164} (Country: {country_display}).\n"
        f"Assigned price: ₹{assigned_price}\n\n"
        "To prove you own this account, LOG IN to the Telegram account you are selling and send this command to this bot from that account:\n\n"
        f"`/confirm_sell {token}`\n\n"
        "We will notify an admin for review after confirmation."
    )

@dp.message_handler(commands=['confirm_sell'])
async def cmd_confirm_sell(message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply("Usage: /confirm_sell <token>")

    token = parts[1].strip()
    sales = load_sales()

    for lid, listing in sales.items():
        if listing.get("token") == token and listing.get("status") == "awaiting_confirmation":
            # Mark verified_by_account and store which telegram account confirmed
            listing["status"] = "verified_by_account"
            listing["confirmed_from_user_id"] = message.from_user.id
            listing["confirmed_at"] = datetime.utcnow().isoformat()
            save_sales(sales)

            # notify admins
            for admin in ADMIN_IDS:
                try:
                    await bot.send_message(admin,
                        f"📣 Listing {lid} verified by account and awaiting your approval.\n"
                        f"Number: {listing['number']}\n"
                        f"Country: {listing.get('country')}\n"
                        f"Price assigned: ₹{listing['price']}\n"
                        f"Seller Telegram ID: {listing['seller_id']}\n\n"
                        f"Use `/approve_sell {lid}` or `/reject_sell {lid}`"
                    )
                except Exception:
                    pass

            await message.reply("✅ Confirmation received from this account. Admin will review the listing.")
            return

    await message.reply("❌ Token not found or already used.")

# Admin: approve / reject unchanged, but will use the assigned price from the listing
@dp.message_handler(commands=['approve_sell'])
async def cmd_approve_sell(message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("❌ You are not authorized.")

    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply("Usage: /approve_sell <listing_id>")
    lid = parts[1].strip()
    sales = load_sales()
    listing = sales.get(lid)
    if not listing:
        return await message.reply("❌ Listing not found.")
    if listing['status'] not in ('verified_by_account',):
        return await message.reply("❌ Listing is not ready for approval.")

    # Approve: add to accounts inventory (do NOT change owner passwords)
    listing['status'] = 'admin_approved'
    listing['approved_at'] = datetime.utcnow().isoformat()
    save_sales(sales)

    # Add to your existing account inventory function:
    add_listing_to_inventory(listing)   # implement this to append to account.json

    # Notify seller
    try:
        await bot.send_message(listing['seller_id'], f"✅ Your listing {lid} has been approved. It is now live at price ₹{listing['price']}.")
    except Exception:
        pass

    await message.reply(f"✅ Listing {lid} approved and added to inventory at ₹{listing['price']}.")

@dp.message_handler(commands=['reject_sell'])
async def cmd_reject_sell(message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("❌ You are not authorized.")
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply("Usage: /reject_sell <listing_id>")
    lid = parts[1].strip()
    sales = load_sales()
    listing = sales.get(lid)
    if not listing:
        return await message.reply("❌ Listing not found.")
    listing['status'] = 'rejected'
    listing['rejected_at'] = datetime.utcnow().isoformat()
    save_sales(sales)
    try:
        await bot.send_message(listing['seller_id'], f"⚠️ Your listing {lid} was rejected by admin.")
    except:
        pass
    await message.reply(f"✅ Listing {lid} rejected.")

# ---------- admin command to set price ----------
@dp.message_handler(commands=['set_price'])
async def cmd_set_price(message):
    """
    Usage: /set_price <COUNTRY_ISO> <PRICE>
    Example: /set_price IN 30
    """
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply("❌ Not authorized.")
    parts = message.text.strip().split()
    if len(parts) < 3:
        return await message.reply("Usage: /set_price <COUNTRY_ISO> <PRICE>\nExample: /set_price IN 30")
    country = parts[1].upper()
    try:
        price = float(parts[2])
    except:
        return await message.reply("Price must be a number.")
    pricing = load_pricing()
    pricing.setdefault("prices", {})[country] = price
    save_pricing(pricing)
    await message.reply(f"✅ Price for {country} set to ₹{price}.")

@dp.message_handler(commands=['show_pricing'])
async def cmd_show_pricing(message):
    pricing = load_pricing()
    lines = [f"Default: ₹{pricing.get('default_price', 30.0)}"]
    for c, p in pricing.get("prices", {}).items():
        lines.append(f"{c}: ₹{p}")
    await message.reply("Pricing map:\n" + "\n".join(lines))
