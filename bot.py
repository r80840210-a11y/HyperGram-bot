import os, json, sqlite3, asyncio, logging, secrets, hmac
from datetime import datetime, timezone
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN=os.environ["BOT_TOKEN"]
PORT=int(os.getenv("PORT","10000"))
DB=os.getenv("DB_PATH","xypergram.db")
SECRET=os.getenv("WEBHOOK_SECRET","")
logging.basicConfig(level=logging.INFO)
bot=Bot(TOKEN); dp=Dispatcher()

def pool(key):
    try: return json.loads(os.getenv(key,"[]"))
    except Exception as e: raise RuntimeError(f"{key} must be a JSON array") from e
POOLS={"ru":pool("PHONE_POOL_RU"),"us":pool("PHONE_POOL_US")}

def now(): return datetime.now(timezone.utc).isoformat()
def conn():
    c=sqlite3.connect(DB,timeout=20)
    c.execute("PRAGMA busy_timeout=20000")
    c.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, username TEXT, created TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS numbers(
      id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, country TEXT, phone TEXT UNIQUE,
      status TEXT DEFAULT 'active', created TEXT, released TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS inbox(id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, body TEXT, created TEXT)")
    return c

def menu():
    k=InlineKeyboardBuilder()
    k.button(text="📱 Получить номер",callback_data="get")
    k.button(text="📂 Мои номера",callback_data="mine")
    k.adjust(1); return k.as_markup()
def countries():
    k=InlineKeyboardBuilder()
    k.button(text="🇷🇺 Россия (+7)",callback_data="c:ru")
    k.button(text="🇺🇸 США (+1)",callback_data="c:us")
    k.button(text="⬅️ Назад",callback_data="home")
    k.adjust(1); return k.as_markup()
def active(uid):
    c=conn(); r=c.execute("SELECT country,phone,created FROM numbers WHERE uid=? AND status='active' ORDER BY id DESC LIMIT 1",(uid,)).fetchone(); c.close(); return r

@dp.message(CommandStart())
async def start(m:Message):
    c=conn(); c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?)",(m.from_user.id,m.from_user.username or "",now())); c.commit(); c.close()
    await m.answer("🚀 Добро пожаловать в XyperGram!\n\nЗдесь вы можете получить номер для регистрации в XyperGram и получать сообщения подтверждения.\n\nУ каждого пользователя может быть только один активный номер.",reply_markup=menu())

@dp.callback_query(F.data=="home")
async def home(q:CallbackQuery):
    await q.message.edit_text("🚀 Главное меню XyperGram",reply_markup=menu()); await q.answer()

@dp.callback_query(F.data=="get")
async def get(q:CallbackQuery):
    if active(q.from_user.id):
        await q.answer("У вас уже есть активный номер. Завершите текущую регистрацию.",show_alert=True); return
    await q.message.edit_text("Выберите страну:",reply_markup=countries()); await q.answer()

@dp.callback_query(F.data.startswith("c:"))
async def choose(q:CallbackQuery):
    country=q.data.split(":")[1]
    if country not in POOLS:
        await q.answer("Страна не поддерживается",show_alert=True); return
    c=conn(); c.execute("BEGIN IMMEDIATE")
    if c.execute("SELECT 1 FROM numbers WHERE uid=? AND status='active'",(q.from_user.id,)).fetchone():
        c.rollback(); c.close(); await q.answer("У вас уже есть активный номер",show_alert=True); return
    used={x[0] for x in c.execute("SELECT phone FROM numbers WHERE status='active'")}
    available=[p for p in POOLS[country] if p not in used]
    if not available:
        c.rollback(); c.close(); await q.answer("Нет свободных номеров. Проверьте пул провайдера.",show_alert=True); return
    phone=secrets.choice(available)
    c.execute("INSERT INTO numbers(uid,country,phone,status,created) VALUES(?,?,?,'active',?)",(q.from_user.id,country,phone,now()))
    c.commit(); c.close()
    k=InlineKeyboardBuilder(); k.button(text="📩 Сообщения",callback_data="inbox"); k.button(text="✅ Завершить регистрацию",callback_data="release"); k.button(text="🏠 Главное меню",callback_data="home"); k.adjust(1)
    await q.message.edit_text(f"✅ Ваш номер:\n`{phone}`\n\nОн закреплён за вами. Сообщения для XyperGram появятся в разделе «Сообщения».",parse_mode="Markdown",reply_markup=k.as_markup()); await q.answer()

@dp.callback_query(F.data=="mine")
async def mine(q:CallbackQuery):
    r=active(q.from_user.id)
    text=f"📂 Ваш активный номер:\n`{r[1]}`" if r else "У вас пока нет активного номера."
    k=InlineKeyboardBuilder()
    if r: k.button(text="📩 Сообщения",callback_data="inbox"); k.button(text="✅ Завершить регистрацию",callback_data="release")
    else: k.button(text="📱 Получить номер",callback_data="get")
    k.button(text="🏠 Главное меню",callback_data="home"); k.adjust(1)
    await q.message.edit_text(text,parse_mode="Markdown",reply_markup=k.as_markup()); await q.answer()

@dp.callback_query(F.data=="inbox")
async def inbox(q:CallbackQuery):
    r=active(q.from_user.id)
    if not r: await q.answer("Сначала получите номер",show_alert=True); return
    c=conn(); rows=c.execute("SELECT body,created FROM inbox WHERE phone=? ORDER BY id DESC LIMIT 10",(r[1],)).fetchall(); c.close()
    text="📩 Пока нет новых сообщений." if not rows else "📩 Сообщения XyperGram:\n\n"+"\n\n".join(x[0] for x in rows)
    k=InlineKeyboardBuilder(); k.button(text="🔄 Обновить",callback_data="inbox"); k.button(text="⬅️ Мои номера",callback_data="mine"); k.adjust(1)
    await q.message.edit_text(text,reply_markup=k.as_markup()); await q.answer()

@dp.callback_query(F.data=="release")
async def release(q:CallbackQuery):
    c=conn(); c.execute("UPDATE numbers SET status='released',released=? WHERE uid=? AND status='active'",(now(),q.from_user.id)); c.commit(); c.close()
    await q.message.edit_text("✅ Регистрация завершена. Номер освобождён.",reply_markup=menu()); await q.answer()

async def health(req): return web.json_response({"status":"ok","service":"XyperGram"})
async def webhook(req):
    raw=await req.read()
    if SECRET and not hmac.compare_digest(req.headers.get("X-Webhook-Secret",""),SECRET):
        return web.json_response({"error":"unauthorized"},status=401)
    try: data=json.loads(raw)
    except Exception: return web.json_response({"error":"invalid_json"},status=400)
    # Accept only verification messages explicitly tagged for your own XyperGram service.
    if data.get("service")!="xypergram": return web.json_response({"error":"unsupported_service"},status=400)
    phone=str(data.get("phone","")).strip(); body=str(data.get("message","")).strip()
    if not phone or not body: return web.json_response({"error":"phone_and_message_required"},status=400)
    c=conn(); row=c.execute("SELECT uid FROM numbers WHERE phone=? AND status='active'",(phone,)).fetchone()
    if not row: c.close(); return web.json_response({"status":"ignored"})
    c.execute("INSERT INTO inbox(phone,body,created) VALUES(?,?,?)",(phone,body[:1500],now())); c.commit(); c.close()
    try: await bot.send_message(row[0],"📩 Новое сообщение для XyperGram:\n\n"+body[:1500])
    except Exception: logging.exception("User notification failed")
    return web.json_response({"status":"accepted"})

async def serve():
    app=web.Application(client_max_size=65536)
    app.router.add_get("/",health); app.router.add_get("/health",health); app.router.add_post("/provider-webhook",webhook)
    runner=web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner,"0.0.0.0",PORT).start()
    logging.info("Listening on 0.0.0.0:%s",PORT)
    return runner

async def main():
    runner=await serve()
    try: await dp.start_polling(bot)
    finally: await runner.cleanup(); await bot.session.close()

if __name__=="__main__": asyncio.run(main())
