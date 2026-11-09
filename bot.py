import os
import random
import sqlite3
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "hypergram.db")
logging.basicConfig(level=logging.INFO)

if not TOKEN:
    raise RuntimeError("Set BOT_TOKEN in Render environment variables")

bot = Bot(TOKEN)
dp = Dispatcher()

# These are clearly fictional sandbox numbers, not real phone numbers.
TEST_NUMBERS = {
    "ru": ["+7 000 000 0101", "+7 000 000 0102", "+7 000 000 0103",
           "+7 000 000 0104", "+7 000 000 0105"],
    "us": ["+1 202 555 0101", "+1 202 555 0102", "+1 202 555 0103",
           "+1 202 555 0104", "+1 202 555 0105"],
}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        country TEXT NOT NULL,
        phone TEXT NOT NULL UNIQUE,
        test_code TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_seen TEXT NOT NULL
    )""")
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
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO users(user_id, username, first_seen) VALUES(?,?,?)",
        (message.from_user.id, message.from_user.username or "",
         datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()
    await message.answer(
        "🚀 Добро пожаловать в HyperGram!\n\n"
        "Здесь можно получить демонстрационный номер и проверить "
        "сценарий регистрации.\n\n"
        "Важно: номера и коды в этой версии тестовые. Они не принимают "
        "реальные SMS и не подходят для регистрации в Telegram или других сервисах.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text("🚀 Главное меню HyperGram", reply_markup=main_keyboard())
    await call.answer()

@dp.callback_query(F.data == "get")
async def choose_country(call: CallbackQuery):
    await call.message.edit_text("Выберите страну тестового номера:", reply_markup=country_keyboard())
    await call.answer()

@dp.callback_query(F.data.startswith("country:"))
async def issue_number(call: CallbackQuery):
    country = call.data.split(":", 1)[1]
    if country not in TEST_NUMBERS:
        await call.answer("Неизвестная страна", show_alert=True)
        return

    conn = db()
    used = {row[0] for row in conn.execute("SELECT phone FROM numbers").fetchall()}
    available = [n for n in TEST_NUMBERS[country] if n not in used]
    if not available:
        conn.close()
        await call.answer("Тестовые номера закончились. Администратору нужно добавить пул.", show_alert=True)
        return

    phone = random.choice(available)
    code = f"{random.randint(0, 999999):06d}"
    conn.execute(
        "INSERT INTO numbers(user_id, country, phone, test_code, created_at) VALUES(?,?,?,?,?)",
        (call.from_user.id, country, phone, code, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

    kb = InlineKeyboardBuilder()
    kb.button(text="📩 Показать тестовый код", callback_data=f"code:{phone}")
    kb.button(text="📂 Мои номера", callback_data="mine")
    kb.button(text="🏠 Главное меню", callback_data="home")
    kb.adjust(1)

    await call.message.edit_text(
        f"✅ Тестовый номер выдан!\n\n"
        f"Страна: {'Россия' if country == 'ru' else 'США'}\n"
        f"Номер: `{phone}`\n\n"
        "Это демонстрационный номер. Реальные SMS на него не поступают.",
        parse_mode="Markdown",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@dp.callback_query(F.data.startswith("code:"))
async def show_test_code(call: CallbackQuery):
    phone = call.data.split(":", 1)[1]
    conn = db()
    row = conn.execute(
        "SELECT test_code FROM numbers WHERE user_id=? AND phone=?",
        (call.from_user.id, phone)
    ).fetchone()
    conn.close()
    if not row:
        await call.answer("Номер не найден в вашем профиле.", show_alert=True)
        return
    await call.message.answer(
        f"📩 Демонстрационный код для {phone}: `{row[0]}`\n\n"
        "Код создан локально для тестирования интерфейса; это не входящее SMS.",
        parse_mode="Markdown"
    )
    await call.answer()

@dp.callback_query(F.data == "mine")
async def my_numbers(call: CallbackQuery):
    conn = db()
    rows = conn.execute(
        "SELECT country, phone, created_at FROM numbers WHERE user_id=? ORDER BY id DESC",
        (call.from_user.id,)
    ).fetchall()
    conn.close()
    if not rows:
        text = "📂 У вас пока нет тестовых номеров."
    else:
        items = []
        for country, phone, created in rows:
            label = "🇷🇺 Россия" if country == "ru" else "🇺🇸 США"
            items.append(f"{label}\n`{phone}`\nПолучен: {created[:10]}")
        text = "📂 Ваши тестовые номера:\n\n" + "\n\n".join(items)
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Получить номер", callback_data="get")
    kb.button(text="🏠 Главное меню", callback_data="home")
    kb.adjust(1)
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.as_markup())
    await call.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
