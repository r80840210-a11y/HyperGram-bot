import os
import asyncio
import logging
import random
import sqlite3
from datetime import datetime, timezone

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Render Web Service settings
BOT_TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "hypergram.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("hypergram")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Fictional sandbox numbers for interface testing only.
# They do not receive real SMS or third-party verification messages.
TEST_NUMBERS = {
    "ru": [
        "+7 000 000 0101",
        "+7 000 000 0102",
        "+7 000 000 0103",
        "+7 000 000 0104",
        "+7 000 000 0105",
    ],
    "us": [
        "+1 202 555 0101",
        "+1 202 555 0102",
        "+1 202 555 0103",
        "+1 202 555 0104",
        "+1 202 555 0105",
    ],
}


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_seen TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            country TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            test_code TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    return conn


def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📱 Получить тестовый номер", callback_data="get")
    kb.button(text="📂 Мои номера", callback_data="mine")
    kb.adjust(1)
    return kb.as_markup()


def country_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Россия (+7)", callback_data="country:ru")
    kb.button(text="🇺🇸 США (+1)", callback_data="country:us")
    kb.button(text="⬅️ Назад", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


@dp.message(CommandStart())
async def start(message: Message):
    conn = connect_db()
    conn.execute(
        "INSERT OR IGNORE INTO users(user_id, username, first_seen) VALUES (?, ?, ?)",
        (
            message.from_user.id,
            message.from_user.username or "",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    await message.answer(
        "🚀 Добро пожаловать в HyperGram!\n\n"
        "В этой демонстрационной версии можно получить тестовый номер "
        "и посмотреть тестовый код.\n\n"
        "Важно: номера и коды вымышленные. Они не принимают реальные SMS "
        "и не предназначены для подтверждения аккаунтов в Telegram "
        "или других сторонних сервисах.",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text(
        "🚀 Главное меню HyperGram",
        reply_markup=main_keyboard(),
    )
    await call.answer()


@dp.callback_query(F.data == "get")
async def choose_country(call: CallbackQuery):
    await call.message.edit_text(
        "Выберите страну тестового номера:",
        reply_markup=country_keyboard(),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("country:"))
async def issue_number(call: CallbackQuery):
    country = call.data.split(":", 1)[1]
    if country not in TEST_NUMBERS:
        await call.answer("Неизвестная страна", show_alert=True)
        return

    conn = connect_db()
    used = {
        row[0]
        for row in conn.execute("SELECT phone FROM numbers").fetchall()
    }
    available = [phone for phone in TEST_NUMBERS[country] if phone not in used]

    if not available:
        conn.close()
        await call.answer(
            "Тестовые номера закончились.",
            show_alert=True,
        )
        return

    phone = random.choice(available)
    test_code = f"{random.randint(0, 999999):06d}"

    conn.execute(
        """
        INSERT INTO numbers(user_id, country, phone, test_code, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            call.from_user.id,
            country,
            phone,
            test_code,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    kb = InlineKeyboardBuilder()
    kb.button(
        text="📩 Показать тестовый код",
        callback_data=f"code:{phone}",
    )
    kb.button(text="📂 Мои номера", callback_data="mine")
    kb.button(text="🏠 Главное меню", callback_data="home")
    kb.adjust(1)

    country_name = "Россия" if country == "ru" else "США"
    await call.message.edit_text(
        f"✅ Тестовый номер выдан!\n\n"
        f"Страна: {country_name}\n"
        f"Номер: `{phone}`\n\n"
        "Это демонстрационный номер: реальные SMS на него не поступают.",
        parse_mode="Markdown",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("code:"))
async def show_test_code(call: CallbackQuery):
    phone = call.data.split(":", 1)[1]
    conn = connect_db()
    row = conn.execute(
        "SELECT test_code FROM numbers WHERE user_id = ? AND phone = ?",
        (call.from_user.id, phone),
    ).fetchone()
    conn.close()

    if row is None:
        await call.answer("Номер не найден в вашем профиле.", show_alert=True)
        return

    await call.message.answer(
        f"📩 Демонстрационный код для {phone}: `{row[0]}`\n\n"
        "Это локальный тестовый код, а не входящее SMS.",
        parse_mode="Markdown",
    )
    await call.answer()


@dp.callback_query(F.data == "mine")
async def my_numbers(call: CallbackQuery):
    conn = connect_db()
    rows = conn.execute(
        """
        SELECT country, phone, created_at
        FROM numbers
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (call.from_user.id,),
    ).fetchall()
    conn.close()

    if not rows:
        text = "📂 У вас пока нет тестовых номеров."
    else:
        entries = []
        for country, phone, created_at in rows:
            flag = "🇷🇺 Россия" if country == "ru" else "🇺🇸 США"
            entries.append(
                f"{flag}\n`{phone}`\nПолучен: {created_at[:10]}"
            )
        text = "📂 Ваши тестовые номера:\n\n" + "\n\n".join(entries)

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Получить номер", callback_data="get")
    kb.button(text="🏠 Главное меню", callback_data="home")
    kb.adjust(1)

    await call.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


async def health(request):
    return web.json_response({
        "status": "ok",
        "service": "HyperGram Registration Bot",
    })


async def start_http_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=PORT,
    )
    await site.start()
    log.info("HTTP health server listening on 0.0.0.0:%s", PORT)
    return runner


async def main():
    # Render detects this HTTP listener as the Web Service port.
    runner = await start_http_server()

    try:
        # Long polling requires exactly one active process per bot token.
        log.info("Starting HyperGram bot polling")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
