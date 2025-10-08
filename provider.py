import aiohttp
import asyncio
import os
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ==========================
# Config
# ==========================
PROVIDER_API_KEY = os.getenv(
    "PROVIDER_API_KEY",
    "f6ba51d5bfa7ae4861968713433255134984"
)
PROVIDER_BASE_URL = os.getenv(
    "PROVIDER_BASE_URL",
    "https://api.temporasms.com/stubs/handler_api.php"
)

# ==========================
# Logging Setup
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Custom exception for provider errors."""
    pass


class ProviderClient:
    def __init__(self):
        # ==========================
        # Operator definitions
        # ==========================
        self.operators = {
            "USA": {
                "Telegram": {
                    "op1": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=eqg&country=12&operator=11&maxPrice=34",
                        "price": 90
                    },
                    "op7": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=edg&country=12&operator=1",
                        "price": 65
                    },
                    "op8": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=edg&country=12&operator=1&maxPrice=43.22",
                        "price": 72
                    },
                    "op9": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=envg&country=187&operator=6&maxPrice=42.92",
                        "price": 100
                    },
                },
                "WhatsApp": {
                    "op1": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tzs&country=12&operator=15&maxPrice=28",
                        "price": 79
                    },
                    "op2": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tis&country=12&operator=11&maxPrice=24",
                        "price": 49
                    },
                    "op3": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tis&country=12&operator=11&maxPrice=24",
                        "price": 58
                    },
                    "op9": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tbs&country=12&operator=8&maxPrice=53",
                        "price": 139
                    },
                },
            },
            "South Africa": {
                "Telegram": {
                    "op1": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=ehbg&country=31&operator=9&maxPrice=13",
                        "price": 29
                    },
                    "op2": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=epg&country=31&operator=10&maxPrice=21",
                        "price": 45
                    },
                    "op3": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=ehbg&country=31&operator=9&maxPrice=13",
                        "price": 67
                    },
                    "op9": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=ehbg&country=31&operator=9&maxPrice=13",
                        "price": 76
                    },
                },
                "WhatsApp": {
                    "op1": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tpgs&country=31&operator=9&maxPrice=12",
                        "price": 27
                    },
                    "op2": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tpgs&country=31&operator=9&maxPrice=12",
                        "price": 38
                    },
                    "op9": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tpgs&country=31&operator=9&maxPrice=12",
                        "price": 49
                    },
                },
            },
            "Togo": {
                "Telegram": {
                    "op1": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=emg&country=99&operator=17&maxPrice=252",
                        "price": 298
                    },
                    "op2": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=ehbg&country=99&operator=9&maxPrice=42.33",
                        "price": 90
                    },
                },
                "WhatsApp": {
                    "op1": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tss&country=99&operator=12&maxPrice=66",
                        "price" : 98
                    },
                    "op2": {
                        "url": f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getNumber&service=tgs&country=99&operator=12&maxPrice=165",
                        "price": 230
                    },
                },
            },
        }
                    
                
    # ==========================
    # Operator Helpers
    # ==========================
    def get_operator_list(self, country: str, service: str) -> dict:
        return self.operators.get(country, {}).get(service, {})

    def get_operator_url(self, country: str, service: str, op_id: str) -> str:
        op = self.get_operator_list(country, service).get(op_id)
        if not op:
            raise ProviderError(f"Operator not found: {country}/{service}/{op_id}")
        return op["url"]

    def get_operator_price(self, country: str, service: str, op_id: str) -> float:
        op = self.get_operator_list(country, service).get(op_id)
        if not op:
            raise ProviderError(f"Price not found: {country}/{service}/{op_id}")
        return op["price"]

    def build_manual_operators_kb(self, country: str, service: str) -> InlineKeyboardMarkup:
        ops = self.get_operator_list(country, service)
        inline_keyboard = [
            [
                InlineKeyboardButton(
                    text=f"Operator {op_id.upper()} - {self.get_operator_price(country, service, op_id)}💲",
                    callback_data=f"manual_buy:{country}:{service}:{op_id}"
                )
            ]
            for op_id in ops.keys()
        ]
        inline_keyboard.append(
            [InlineKeyboardButton(text="⬅️ Back", callback_data=f"back:services:{country}")]
        )
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    # ==========================
    # API Helpers
    # ==========================
    async def _request(self, url: str) -> str:
        logger.info(f"➡️ Requesting: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                text = await resp.text()
                logger.info(f"⬅️ Response [{resp.status}]: {text.strip()}")
                if resp.status != 200:
                    raise ProviderError(f"Bad status: {resp.status}")
                return text.strip()

    # ==========================
    # Buy Number
    # ==========================
    async def buy_number(self, url: str) -> dict:
        try:
            text = await self._request(url)

            if text.startswith("ACCESS_NUMBER"):
                # Example: ACCESS_NUMBER:68cc230f5539260a954dbdc8:16286821107
                parts = text.split(":")
                if len(parts) >= 3:
                    activation_id = parts[1]
                    number = parts[2]
                else:
                    raise ProviderError(f"Malformed ACCESS_NUMBER response: {text}")

                # ✅ Confirm activation, required by API
                confirm_url = f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=setStatus&id={activation_id}&status=1"
                await self._request(confirm_url)

                return {"status": "success", "id": activation_id, "number": number}

            raise ProviderError(f"Unexpected response: {text[:200]}")
        except Exception as e:
            logger.error(f"❌ Buy number failed: {e}")
            raise ProviderError(f"Sorry, This Operator is currently Out of Stock❗: {e}")

    # ==========================
    # Get SMS
    # ==========================
    async def get_sms(self, order_id: str) -> dict:
        url = f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=getStatus&id={order_id}"
        try:
            text = await self._request(url)

            if text.startswith("STATUS_OK"):
                _, sms = text.split(":", 1)
                return {"status": "sms_received", "sms": sms.strip()}

            elif text.startswith("STATUS_WAIT_CODE"):
                return {"status": "waiting"}

            elif text.startswith("STATUS_CANCEL"):
                return {"status": "cancelled"}

            elif text.startswith("STATUS_FINISH"):
                return {"status": "finished"}

            elif text == "NO_ACTIVATION":
                return {"status": "no_activation"}

            else:
                raise ProviderError(f"Unexpected SMS response: {text}")

        except Exception as e:
            logger.error(f"❌ Get SMS failed: {e}")
            raise ProviderError(f"Get SMS failed: {e}")

    # ==========================
    # Poll SMS until received
    # ==========================
    async def wait_for_sms(self, order_id: str, retries: int = 20, delay: int = 5):
        logger.info(f"📨 Waiting for SMS [id={order_id}]...")
        for attempt in range(retries):
            sms_data = await self.get_sms(order_id)
            if sms_data["status"] == "sms_received":
                logger.info(f"✅ SMS received: {sms_data['sms']}")
                return sms_data["sms"]
            elif sms_data["status"] in ["cancelled", "finished", "no_activation"]:
                logger.warning(f"⚠️ SMS check ended: {sms_data['status']}")
                return None
            logger.info(f"⌛ Attempt {attempt+1}/{retries}: still waiting...")
            await asyncio.sleep(delay)
        logger.warning("⏱️ Timeout: No SMS received.")
        return None
