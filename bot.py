import asyncio
import json
import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    FSInputFile, LabeledPrice, PreCheckoutQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = "8835340993:AAHaD0qLCmtB7ien6R1KPgEfESX0CEqOnRw"
ADMIN_ID = 8146320391

DB_FILE = os.getenv("DB_FILE", "cosdrop.sqlite3")
IMAGE_FILE = "imagemain.png"
BACKUP_DIR = "/data/backups" if os.path.isdir("/data") else "backups"

PACKS = [(100, 20), (400, 30), (1000, 67), (1500, 170)]

MIN_WITHDRAW_SD = 500
DAILY_LIMIT_WITHDRAW = 10000

STARTER_SD = 100
DAILY_BASE = 50
DAILY_STREAK_BONUS = {7: 300, 30: 2000}

REF_BONUS_INVITE = 500
REF_BONUS_DONATE = 2000

CASINO_MIN_BET = 10
CASINO_MAX_BET = 10000
CASINO_MAX_WIN = 50000
CASINO_DAILY_LOSS_LIMIT = 5000

CASE_COOLDOWN = 3
SELL_COMMISSION = 0.10

SUB_PRICE = 200
SUB_DAYS = 30
SUB_BONUS = {"daily_mult": 2, "xp_mult": 1.10, "badge": "💎"}

if not BOT_TOKEN or BOT_TOKEN == "PASTE_NEW_BOT_TOKEN_HERE":
    raise RuntimeError("Вставь токен в BOT_TOKEN")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ============================================================
# DATA
# ============================================================

CASES = [
    ("start", "🎒 Старт-кейс", "Бесплатный стартовый кейс", 0),
    ("basic", "📦 Basic Case", "Обычный коллекционный кейс", 100),
    ("school", "🏫 School Case", "Школьная коллекция", 150),
    ("meme", "😂 Meme Case", "Мемная коллекция", 200),
    ("rare", "💎 Rare Case", "Упор на редкие категории", 300),
    ("epic", "🟣 Epic Case", "Редкие предметы", 500),
    ("night", "🌙 Night Case", "Ночная коллекция", 700),
    ("cos", "👑 COS Case", "Главный коллекционный кейс", 1000),
]

ITEMS = [
    ("basic_star", "⭐ Star", "common", 20),
    ("basic_blue", "🔷 Blue Crystal", "rare", 80),
    ("basic_purple", "🟣 Purple Crystal", "epic", 300),
    ("school_pen", "🖊️ Золотая ручка", "rare", 90),
    ("backpack", "🎒 Космо-рюкзак", "epic", 350),
    ("school_cup", "🏆 Кубок класса", "legendary", 1200),
    ("meme_skull", "💀 Skull", "common", 25),
    ("meme_sigma", "🗿 Sigma", "rare", 100),
    ("meme_fire", "🔥 Fire", "epic", 400),
    ("rare_diamond", "💎 Diamond", "rare", 120),
    ("rare_crown", "👑 Silver Crown", "epic", 500),
    ("rare_gold", "✨ Golden Badge", "legendary", 1500),
    ("epic_galaxy", "🌌 Galaxy", "epic", 600),
    ("epic_comet", "☄️ Comet", "legendary", 1800),
    ("epic_cosmo", "🚀 COSMO", "mythic", 5000),
    ("night_moon", "🌙 Moon", "rare", 130),
    ("night_ghost", "👻 Ghost", "epic", 550),
    ("night_eclipse", "🌑 Eclipse", "legendary", 2000),
    ("cos_crown", "👑 COS Crown", "legendary", 2500),
    ("cos_galaxy", "🌌 COS Galaxy", "mythic", 6000),
    ("cos_core", "💠 COS Core", "mythic", 8000),
]

DROPS = {
    "start": [("basic_star", 50), ("school_pen", 40), ("meme_skull", 10)],
    "basic": [("basic_star", 55), ("basic_blue", 30), ("basic_purple", 12), ("meme_sigma", 3)],
    "school": [("school_pen", 60), ("backpack", 30), ("school_cup", 10)],
    "meme": [("meme_skull", 60), ("meme_sigma", 28), ("meme_fire", 12)],
    "rare": [("rare_diamond", 65), ("rare_crown", 28), ("rare_gold", 7)],
    "epic": [("epic_galaxy", 65), ("epic_comet", 30), ("epic_cosmo", 5)],
    "night": [("night_moon", 60), ("night_ghost", 30), ("night_eclipse", 10)],
    "cos": [("cos_crown", 65), ("cos_galaxy", 30), ("cos_core", 5)],
}

RARITY = {
    "common": "🟢 Common", "rare": "🔵 Rare", "epic": "🟣 Epic",
    "legendary": "🟡 Legendary", "mythic": "🔴 Mythic",
}
RARITY_ORDER = ["common", "rare", "epic", "legendary", "mythic"]

SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣", "⭐"]
SLOT_PAYOUTS = {
    ("🍒", "🍒", "🍒"): 3, ("🍋", "🍋", "🍋"): 4, ("🔔", "🔔", "🔔"): 6,
    ("💎", "💎", "💎"): 12, ("7️⃣", "7️⃣", "7️⃣"): 25, ("⭐", "⭐", "⭐"): 50,
}


# ============================================================
# FSM
# ============================================================

class Apply(StatesGroup):
    name = State(); cls = State(); phone = State(); msg = State()

class GiveSD(StatesGroup):
    uid = State(); amount = State()

class TakeSD(StatesGroup):
    uid = State(); amount = State()

class Broadcast(StatesGroup):
    text = State()

class Promo(StatesGroup):
    code = State()

class PromoCreate(StatesGroup):
    code = State(); reward = State()

class PromoDelete(StatesGroup):
    code = State()

class UserSearch(StatesGroup):
    query = State()

class BlockUser(StatesGroup):
    uid = State()

class UnblockUser(StatesGroup):
    uid = State()

class CasePrice(StatesGroup):
    case_id = State(); price = State()

class WithdrawFSM(StatesGroup):
    amount = State()

class CasinoBet(StatesGroup):
    game = State(); amount = State()

class DuelBet(StatesGroup):
    amount = State()


# ============================================================
# DB
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).date().isoformat()
LIMIT_DEFAULTS = {
    "starter_sd": 100, "daily_base": 50, "daily_streak_7": 300, "daily_streak_30": 2000,
    "case_cooldown": 3, "sell_commission": 0.10, "upgrade_chance": 0.60,
    "casino_min": 10, "casino_max": 10000, "casino_max_win": 50000, "casino_loss_limit": 5000,
    "duel_min": 100, "duel_commission": 0.05,
    "min_withdraw": 500, "max_withdraw": 10000,
    "ref_invite": 500, "ref_donate": 2000,
    "sub_price": 200, "sub_days": 30,
    "pack_100": 20, "pack_400": 30, "pack_1000": 67, "pack_1500": 170,
    "registration_open": 1, "referral_enabled": 1, "casino_enabled": 1,
    "withdraw_enabled": 1, "maintenance_mode": 0,
}


def get_limit(key):
    d = LIMIT_DEFAULTS.get(key, 0)
    try:
        con = db()
        r = con.execute("SELECT value FROM settings WHERE key=?", (f"lim_{key}",)).fetchone()
        con.close()
    except Exception:
        return d
    if not r:
        return d
    v = r["value"]
    try:
        if isinstance(d, float):
            return float(v)
        if isinstance(d, int):
            return int(v)
    except Exception:
        return d
    return v


def set_limit(key, value):
    con = db()
    con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"lim_{key}", str(value)))
    con.commit()
    con.close()



def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)
    con = db()
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE, username TEXT, first_name TEXT,
        sd INTEGER DEFAULT 100, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
        blocked INTEGER DEFAULT 0, created_at TEXT, last_activity TEXT,
        daily_claim TEXT, daily_streak INTEGER DEFAULT 0, last_case_at TEXT,
        referrer_id INTEGER, donated INTEGER DEFAULT 0,
        sub_until TEXT, daily_loss INTEGER DEFAULT 0, daily_loss_date TEXT
    );
    CREATE TABLE IF NOT EXISTS cases(
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, description TEXT, price INTEGER, enabled INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, rarity TEXT, sell_price INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS case_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER,
        item_id INTEGER, chance REAL, UNIQUE(case_id,item_id)
    );
    CREATE TABLE IF NOT EXISTS inventory(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        item_id INTEGER, obtained_at TEXT
    );
    CREATE TABLE IF NOT EXISTS case_opens(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        case_id INTEGER, item_id INTEGER, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS applications(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT,
        name TEXT, class_name TEXT, phone TEXT, message TEXT,
        status TEXT DEFAULT 'pending', admin_id INTEGER,
        created_at TEXT, decided_at TEXT
    );
    CREATE TABLE IF NOT EXISTS promo_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        reward INTEGER, max_uses INTEGER, uses INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS promo_uses(
        id INTEGER PRIMARY KEY AUTOINCREMENT, promo_id INTEGER,
        user_id INTEGER, used_at TEXT, UNIQUE(promo_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS admins(
        user_id INTEGER PRIMARY KEY, role TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS admin_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER,
        action TEXT, target_user_id INTEGER, details TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS achievements(
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, description TEXT, reward INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS user_achievements(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        achievement_id INTEGER, obtained_at TEXT, UNIQUE(user_id, achievement_id)
    );
    CREATE TABLE IF NOT EXISTS withdraws(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
        status TEXT DEFAULT 'pending', admin_id INTEGER, created_at TEXT, decided_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, description TEXT, goal INTEGER, reward INTEGER
    );
    CREATE TABLE IF NOT EXISTS user_tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_id INTEGER,
        date TEXT, progress INTEGER DEFAULT 0, done INTEGER DEFAULT 0,
        UNIQUE(user_id, task_id, date)
    );
    CREATE TABLE IF NOT EXISTS casino_bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, game TEXT,
        bet INTEGER, win INTEGER, profit INTEGER, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS casino_stats(
        user_id INTEGER PRIMARY KEY, total_bets INTEGER DEFAULT 0,
        total_won INTEGER DEFAULT 0, total_lost INTEGER DEFAULT 0,
        biggest_win INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS duels(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challenger_id INTEGER, opponent_id INTEGER, amount INTEGER,
        status TEXT DEFAULT 'pending', winner_id INTEGER,
        created_at TEXT, finished_at TEXT
    );
    """)

    # ===== МИГРАЦИЯ (для старых баз) =====
    def _cols(table):
        try:
            return {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            return set()

    u_cols = _cols("users")
    for col, ddl in [
        ("referrer_id", "INTEGER"), ("donated", "INTEGER DEFAULT 0"),
        ("sub_until", "TEXT"), ("daily_streak", "INTEGER DEFAULT 0"),
        ("daily_loss", "INTEGER DEFAULT 0"), ("daily_loss_date", "TEXT"),
    ]:
        if col not in u_cols:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

    i_cols = _cols("items")
    if "sell_price" not in i_cols:
        cur.execute("ALTER TABLE items ADD COLUMN sell_price INTEGER DEFAULT 0")
    if "enabled" not in i_cols:
        cur.execute("ALTER TABLE items ADD COLUMN enabled INTEGER DEFAULT 1")

    c_cols = _cols("cases")
    if "enabled" not in c_cols:
        cur.execute("ALTER TABLE cases ADD COLUMN enabled INTEGER DEFAULT 1")

    cur.execute("UPDATE items SET sell_price = 50 WHERE sell_price = 0 AND rarity='common'")
    cur.execute("UPDATE items SET sell_price = 150 WHERE sell_price = 0 AND rarity='rare'")
    cur.execute("UPDATE items SET sell_price = 500 WHERE sell_price = 0 AND rarity='epic'")
    cur.execute("UPDATE items SET sell_price = 1500 WHERE sell_price = 0 AND rarity='legendary'")
    cur.execute("UPDATE items SET sell_price = 5000 WHERE sell_price = 0 AND rarity='mythic'")
    con.commit()
    # ===== конец миграции =====

    cur.execute("INSERT OR IGNORE INTO admins(user_id,role,created_at) VALUES(?,?,?)",
                (ADMIN_ID, "owner", now()))

    for code, name, desc, price in CASES:
        cur.execute("INSERT OR IGNORE INTO cases(code,name,description,price) VALUES(?,?,?,?)",
                    (code, name, desc, price))
    for code, name, rarity, price in ITEMS:
        cur.execute("INSERT OR IGNORE INTO items(code,name,rarity,sell_price) VALUES(?,?,?,?)",
                    (code, name, rarity, price))
    for cc, drops in DROPS.items():
        cr = cur.execute("SELECT id FROM cases WHERE code=?", (cc,)).fetchone()
        if not cr:
            continue
        for ic, ch in drops:
            ir = cur.execute("SELECT id FROM items WHERE code=?", (ic,)).fetchone()
            if ir:
                cur.execute("INSERT OR IGNORE INTO case_items(case_id,item_id,chance) VALUES(?,?,?)",
                            (cr["id"], ir["id"], ch))

    ach = [
        ("first_case", "🎁 Первый кейс", "Открыть первый кейс", 50),
        ("ten_cases", "🔥 10 открытий", "Открыть 10 кейсов", 150),
        ("hundred_cases", "💎 100 открытий", "Открыть 100 кейсов", 500),
        ("collector", "🎒 Коллекционер", "Получить 10 предметов", 250),
        ("rich", "💰 Богатый игрок", "Накопить 5000 SD", 500),
        ("casino_king", "🎰 Король казино", "Сделать 100 ставок", 1000),
        ("duelist", "⚔️ Дуэлянт", "Выиграть 5 дуэлей", 400),
        ("referrer", "🤝 Вербовщик", "Пригласить 3 друзей", 750),
    ]
    for c, n, d, r in ach:
        cur.execute("INSERT OR IGNORE INTO achievements(code,name,description,reward) VALUES(?,?,?,?)",
                    (c, n, d, r))

    tasks = [
        ("open5", "🎁 Открой 5 кейсов", "Открыть 5 кейсов", 5, 200),
        ("bet3", "🎰 Сделай 3 ставки", "Сделать 3 ставки в казино", 3, 150),
        ("win1", "🏆 Выиграй 1 раз", "Выиграть в любой игре", 1, 250),
        ("daily", "📅 Зайди в бота", "Просто зайти", 1, 50),
    ]
    for c, n, d, g, r in tasks:
        cur.execute("INSERT OR IGNORE INTO tasks(code,name,description,goal,reward) VALUES(?,?,?,?,?)",
                    (c, n, d, g, r))

    con.commit()
    con.close()


# ============================================================
# HELPERS
# ============================================================

def ensure(user):
    con = db()
    row = con.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()
    if row:
        con.execute("UPDATE users SET username=?, first_name=?, last_activity=? WHERE user_id=?",
                    (user.username, user.first_name or "", now(), user.id))
    else:
        con.execute("""INSERT INTO users(user_id,username,first_name,created_at,last_activity,sd)
                       VALUES(?,?,?,?,?,?)""",
                    (user.id, user.username, user.first_name or "", now(), now(), STARTER_SD))
    con.commit()
    row = con.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()
    con.close()
    return row


def is_admin(uid):
    return uid == ADMIN_ID


def log_admin(action, target=None, details=""):
    con = db()
    con.execute("INSERT INTO admin_logs(admin_id,action,target_user_id,details,created_at) VALUES(?,?,?,?,?)",
                (ADMIN_ID, action, target, details, now()))
    con.commit()
    con.close()


def add_sd(uid, amount):
    con = db()
    con.execute("UPDATE users SET sd=sd+? WHERE user_id=?", (amount, uid))
    con.commit()
    con.close()


def take_sd(uid, amount):
    con = db()
    row = con.execute("SELECT sd FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row or row["sd"] < amount:
        con.close()
        return False
    con.execute("UPDATE users SET sd=sd-? WHERE user_id=?", (amount, uid))
    con.commit()
    con.close()
    return True


def get_user(uid):
    con = db()
    row = con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    con.close()
    return row


def has_sub(user):
    if not user or "sub_until" not in user.keys() or not user["sub_until"]:
        return False
    try:
        until = datetime.fromisoformat(user["sub_until"])
        return until > datetime.now(timezone.utc)
    except Exception:
        return False


def badge(user):
    return SUB_BONUS["badge"] + " " if has_sub(user) else ""


# ============================================================
# KEYBOARDS
# ============================================================

def home_kb(user=None):
    b = InlineKeyboardBuilder()
    btns = [
        ("🎮 Кейсы", "play"),
        ("🎰 Казино", "casino"),
        ("👤 Профиль", "profile"),
        ("💰 Баланс", "balance"),
        ("⭐ Пополнить", "topup"),
        ("🎬 Медиа / Партнёрство", "media"),
        ("🎒 Коллекция", "collection"),
        ("🏆 Рейтинг", "rating"),
        ("🎟 Промокод", "promo"),
        ("🏅 Достижения", "achievements"),
        ("📋 Задания", "tasks"),
        ("⚔️ Дуэли", "duels"),
        ("👥 Рефералы", "ref"),
        ("💎 CosDrop+", "subscribe"),
        ("📝 Заявки", "apps"),
        ("ℹ️ Обо мне", "about"),
    ]
    for t, d in btns:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()


def back(cb="home"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=cb)]
    ])


def admin_kb():
    b = InlineKeyboardBuilder()
    btns = [
        ("📊 Статистика", "adm_stats"), ("👥 Пользователи", "adm_users"),
        ("🔎 Найти", "adm_search"), ("🎁 Выдать SD", "adm_give"),
        ("➖ Забрать SD", "adm_take"), ("🚫 Блокировки", "adm_blocks"),
        ("🎟 Промокоды", "adm_promo"), ("📦 Кейсы", "adm_cases"),
        ("💎 Предметы", "adm_items"), ("📝 Заявки", "adm_apps"),
        ("💸 Выводы", "adm_withdraws"), ("📢 Рассылка", "adm_broadcast"),
        ("📜 Логи", "adm_logs"), ("💾 Бэкап", "adm_backup"),
    ]
    for t, d in btns:
        b.button(text=t, callback_data=d)
    b.adjust(2)
    return b.as_markup()


def casino_menu():
    b = InlineKeyboardBuilder()
    b.button(text="🎰 Слоты", callback_data="cas_slots")
    b.button(text="🎲 Кости", callback_data="cas_dice")
    b.button(text="🪙 Монетка", callback_data="cas_coin")
    b.button(text="🎡 Рулетка", callback_data="cas_roulette")
    b.button(text="💣 Мины", callback_data="cas_mines")
    b.button(text="📊 Статистика", callback_data="cas_stats")
    b.button(text="🏆 Топ выигрышей", callback_data="cas_top")
    b.button(text="◀️ Назад", callback_data="home")
    b.adjust(2, 2, 2, 1, 1)
    return b.as_markup()


def bet_kb(game):
    mn = get_limit("casino_min")
    mx = get_limit("casino_max")
    # 6 удобных точек между min и max
    steps = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000,
             25000, 50000, 100000, 250000, 500000, 1000000,
             2500000, 5000000, 8000000]
    opts = [v for v in steps if mn <= v <= mx]
    if not opts:
        opts = [mn, mx]
    elif opts[-1] != mx:
        opts.append(mx)
    # если точек больше 6 — берём 6 самых показательных
    if len(opts) > 6:
        # берём шаг, чтобы уложиться в 6
        idxs = [0, len(opts)//5, 2*len(opts)//5, 3*len(opts)//5, 4*len(opts)//5, len(opts)-1]
        opts = sorted(set(opts[i] for i in idxs))
    b = InlineKeyboardBuilder()
    for v in opts:
        b.button(text=f"{v}", callback_data=f"bet:{game}:{v}")
    b.button(text="✏️ Своя", callback_data=f"bet:{game}:custom")
    b.button(text="◀️ Назад", callback_data="casino")
    b.adjust(3, 3, 1, 1)
    return b.as_markup()


# ============================================================
# START / HOME
# ============================================================

@dp.message(Command("start"))
async def start(message: Message):
    args = message.text.split(maxsplit=1)
    ref = None
    if len(args) > 1 and args[1].isdigit():
        ref = int(args[1])

    user = ensure(message.from_user)
    if user["blocked"]:
        return await message.answer("🚫 <b>Ваш аккаунт заблокирован.</b>")

    if ref and ref != message.from_user.id and not user["referrer_id"]:
        con = db()
        r = con.execute("SELECT user_id FROM users WHERE user_id=?", (ref,)).fetchone()
        if r:
            con.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (ref, message.from_user.id))
            con.execute("UPDATE users SET sd=sd+? WHERE user_id=?", (REF_BONUS_INVITE, ref))
            con.commit()
            try:
                await bot.send_message(ref, f"🤝 Новый реферал!\n💰 +{REF_BONUS_INVITE} SD")
            except Exception:
                pass
        con.close()

    if os.path.isfile(IMAGE_FILE) and os.path.getsize(IMAGE_FILE) > 0:
        try:
            await message.answer_photo(FSInputFile(IMAGE_FILE),
                                       caption="✨ <b>COS-DROP</b>\n\nДобро пожаловать!")
        except Exception:
            pass

    b = badge(user)
    await message.answer(
        f"🎁 <b>COS-DROP</b>\n\n{b}💰 SD: <b>{user['sd']}</b>\n"
        f"⭐ Уровень: <b>{user['level']}</b>\n✨ XP: <b>{user['xp']}</b>\n\nВыбери раздел:",
        reply_markup=home_kb(user),
    )
    await bump_task(message.from_user.id, "daily", 1)


@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    user = ensure(callback.from_user)
    if user["blocked"]:
        return await callback.answer("Заблокирован.", show_alert=True)
    b = badge(user)
    await callback.message.edit_text(
        f"🎁 <b>COS-DROP</b>\n\n{b}💰 SD: <b>{user['sd']}</b>\n"
        f"⭐ Уровень: <b>{user['level']}</b>\n\nВыбери раздел:",
        reply_markup=home_kb(user),
    )
    await callback.answer()


# ============================================================
# CASES
# ============================================================

@dp.callback_query(F.data == "play")
async def play(callback: CallbackQuery):
    con = db()
    rows = con.execute("SELECT * FROM cases WHERE enabled=1 ORDER BY id").fetchall()
    con.close()
    b = InlineKeyboardBuilder()
    for r in rows:
        b.button(text=f"{r['name']} · {r['price']} SD", callback_data=f"case:{r['id']}")
    b.button(text="◀️ Назад", callback_data="home")
    b.adjust(1)
    await callback.message.edit_text("🎮 <b>КЕЙСЫ</b>\n\nВыбери кейс:", reply_markup=b.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("case:"))
async def case_info(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM cases WHERE id=? AND enabled=1", (cid,)).fetchone()
    con.close()
    if not row:
        return await callback.answer("Кейс недоступен.", show_alert=True)
    b = InlineKeyboardBuilder()
    b.button(text="🎁 Открыть", callback_data=f"open:{cid}")
    b.button(text="🎁 ×5 (скидка 10%)", callback_data=f"open5:{cid}")
    b.button(text="◀️ Назад", callback_data="play")
    b.adjust(1)
    await callback.message.edit_text(
        f"📦 <b>{escape(row['name'])}</b>\n\n{escape(row['description'])}\n\n"
        f"💰 Стоимость: <b>{row['price']} SD</b>",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


async def _do_case_open(uid, cid, count=1):
    con = db()
    case_row = con.execute("SELECT * FROM cases WHERE id=? AND enabled=1", (cid,)).fetchone()
    if not case_row:
        con.close()
        return None, "Кейс недоступен"

    price = case_row["price"]
    if count == 5:
        price = int(price * 5 * 0.9)

    user = con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if not user or user["sd"] < price:
        con.close()
        return None, "Недостаточно SD"

    if count == 1 and user["last_case_at"]:
        try:
            last = datetime.fromisoformat(user["last_case_at"])
            if (datetime.now(timezone.utc) - last).total_seconds() < CASE_COOLDOWN:
                con.close()
                return None, "Подожди пару секунд"
        except Exception:
            pass

    items = con.execute("""
        SELECT i.*, ci.chance FROM case_items ci
        JOIN items i ON i.id=ci.item_id
        WHERE ci.case_id=? AND i.enabled=1
    """, (cid,)).fetchall()
    if not items:
        con.close()
        return None, "В кейсе нет предметов"

    results = []
    for _ in range(count):
        pick = random.choices(items, weights=[float(x["chance"]) for x in items], k=1)[0]
        results.append(pick)
        con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)",
                    (uid, pick["id"], now()))
        con.execute("INSERT INTO case_opens(user_id,case_id,item_id,created_at) VALUES(?,?,?,?)",
                    (uid, cid, pick["id"], now()))

    xp_gain = int(10 * count * (SUB_BONUS["xp_mult"] if has_sub(user) else 1))
    con.execute("UPDATE users SET sd=sd-?, xp=xp+?, last_case_at=?, last_activity=? WHERE user_id=?",
                (price, xp_gain, now(), now(), uid))
    con.commit()
    con.close()
    return results, None


@dp.callback_query(F.data.startswith("open:"))
async def open_case(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    user = ensure(callback.from_user)
    if user["blocked"]:
        return await callback.answer("Заблокирован.", show_alert=True)

    results, err = await _do_case_open(callback.from_user.id, cid, 1)
    if err:
        return await callback.answer(err, show_alert=True)

    sel = results[0]
    await check_achievements(callback.from_user.id)
    await bump_task(callback.from_user.id, "open5", 1)

    await callback.message.edit_text(
        f"✨ <b>ОТКРЫТИЕ</b>\n\n{RARITY.get(sel['rarity'], '⚪')}\n\n"
        f"<b>{escape(sel['name'])}</b>\n\n🎒 Предмет добавлен!\n⭐ +10 XP",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Ещё", callback_data="play")],
            [InlineKeyboardButton(text="🎒 Коллекция", callback_data="collection")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="home")],
        ]),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("open5:"))
async def open_case_5(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    user = ensure(callback.from_user)
    if user["blocked"]:
        return await callback.answer("Заблокирован.", show_alert=True)

    results, err = await _do_case_open(callback.from_user.id, cid, 5)
    if err:
        return await callback.answer(err, show_alert=True)

    text = "✨ <b>×5 ОТКРЫТИЙ</b>\n\n"
    for r in results:
        text += f"{RARITY.get(r['rarity'], '⚪')} <b>{escape(r['name'])}</b>\n"

    await check_achievements(callback.from_user.id)
    await bump_task(callback.from_user.id, "open5", 5)

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Ещё", callback_data="play")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="home")],
    ]))
    await callback.answer()


# ============================================================
# COLLECTION
# ============================================================

@dp.callback_query(F.data == "collection")
async def collection(callback: CallbackQuery):
    con = db()
    rows = con.execute("""
        SELECT i.id, i.name, i.rarity, i.sell_price, COUNT(*) n
        FROM inventory inv JOIN items i ON i.id=inv.item_id
        WHERE inv.user_id=? GROUP BY inv.item_id
        ORDER BY i.rarity, i.name
    """, (callback.from_user.id,)).fetchall()
    con.close()

    if not rows:
        return await callback.message.edit_text("🎒 <b>КОЛЛЕКЦИЯ</b>\n\nПока пусто.",
                                                reply_markup=back())

    b = InlineKeyboardBuilder()
    for r in rows:
        b.button(text=f"{RARITY.get(r['rarity'],'⚪')} {r['name']} ×{r['n']}",
                 callback_data=f"item:{r['id']}")
    b.button(text="◀️ Назад", callback_data="home")
    b.adjust(1)
    await callback.message.edit_text("🎒 <b>КОЛЛЕКЦИЯ</b>\n\nВыбери предмет:",
                                     reply_markup=b.as_markup())
    await callback.answer()


@dp.callback_query(F.data.startswith("item:"))
async def item_menu(callback: CallbackQuery):
    iid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    count = con.execute("SELECT COUNT(*) n FROM inventory WHERE user_id=? AND item_id=?",
                        (callback.from_user.id, iid)).fetchone()["n"]
    con.close()
    if not row:
        return await callback.answer("Предмет не найден.", show_alert=True)

    sell_total = int(row["sell_price"] * count * (1 - SELL_COMMISSION))
    b = InlineKeyboardBuilder()
    b.button(text=f"💰 Продать 1 ({row['sell_price']} SD)", callback_data=f"sell:1:{iid}")
    b.button(text=f"💰 Продать всё ({sell_total} SD)", callback_data=f"sell:all:{iid}")
    b.button(text="⬆️ Апгрейд ×3 → 1 редче", callback_data=f"upgrade:{iid}")
    b.button(text="◀️ Назад", callback_data="collection")
    b.adjust(1)
    await callback.message.edit_text(
        f"{RARITY.get(row['rarity'],'⚪')} <b>{escape(row['name'])}</b>\n\n"
        f"В инвентаре: <b>{count}</b>\n"
        f"Цена продажи за 1: <b>{row['sell_price']} SD</b>\n"
        f"Комиссия: <b>{int(SELL_COMMISSION*100)}%</b>",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("sell:"))
async def sell_item(callback: CallbackQuery):
    parts = callback.data.split(":")
    mode, iid_s = parts[1], parts[2]
    iid = int(iid_s)
    con = db()
    row = con.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    inv = con.execute("SELECT id FROM inventory WHERE user_id=? AND item_id=? LIMIT 100",
                      (callback.from_user.id, iid)).fetchall()
    con.close()
    if not row or not inv:
        return await callback.answer("Нет предмета.", show_alert=True)

    count = len(inv) if mode == "all" else 1
    if count > len(inv):
        count = len(inv)

    total = int(row["sell_price"] * count * (1 - SELL_COMMISSION))
    add_sd(callback.from_user.id, total)

    ids = [x["id"] for x in inv[:count]]
    if ids:
        con = db()
        q = ",".join("?" * len(ids))
        con.execute(f"DELETE FROM inventory WHERE id IN ({q})", ids)
        con.commit()
        con.close()

    await callback.answer(f"✅ Продано ×{count} за {total} SD", show_alert=True)
    await item_menu(callback)


@dp.callback_query(F.data.startswith("upgrade:"))
async def upgrade_item(callback: CallbackQuery):
    iid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not row:
        con.close()
        return await callback.answer("Нет предмета.", show_alert=True)

    r_idx = RARITY_ORDER.index(row["rarity"]) if row["rarity"] in RARITY_ORDER else 0
    if r_idx >= len(RARITY_ORDER) - 1:
        con.close()
        return await callback.answer("Максимальная редкость.", show_alert=True)

    next_rarity = RARITY_ORDER[r_idx + 1]
    candidates = con.execute("SELECT * FROM items WHERE rarity=? AND enabled=1",
                             (next_rarity,)).fetchall()
    if not candidates:
        con.close()
        return await callback.answer("Нет предметов выше.", show_alert=True)

    inv = con.execute("SELECT id FROM inventory WHERE user_id=? AND item_id=? LIMIT 3",
                      (callback.from_user.id, iid)).fetchall()
    if len(inv) < 3:
        con.close()
        return await callback.answer("Нужно 3 шт.", show_alert=True)

    ids = [x["id"] for x in inv]
    if ids:
        q = ",".join("?" * len(ids))
        con.execute(f"DELETE FROM inventory WHERE id IN ({q})", ids)

    success = random.random() < 0.6
    if success:
        new_item = random.choice(candidates)
        con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)",
                    (callback.from_user.id, new_item["id"], now()))
        text = f"✅ УСПЕХ!\n\nПолучен {RARITY.get(new_item['rarity'])} <b>{escape(new_item['name'])}</b>"
    else:
        text = "❌ Апгрейд провалился. Предметы сгорели."

    con.commit()
    con.close()
    await check_achievements(callback.from_user.id)
    await callback.answer(text, show_alert=True)
    await collection(callback)


# ============================================================
# PROFILE / BALANCE / DAILY
# ============================================================

@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    user = ensure(callback.from_user)
    con = db()
    inv = con.execute("SELECT COUNT(*) n FROM inventory WHERE user_id=?", (user["user_id"],)).fetchone()["n"]
    opens = con.execute("SELECT COUNT(*) n FROM case_opens WHERE user_id=?", (user["user_id"],)).fetchone()["n"]
    achs = con.execute("SELECT COUNT(*) n FROM user_achievements WHERE user_id=?", (user["user_id"],)).fetchone()["n"]
    refs = con.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?", (user["user_id"],)).fetchone()["n"]
    con.close()
    sub = "✅ активна" if has_sub(user) else "❌ нет"
    await callback.message.edit_text(
        f"👤 <b>ПРОФИЛЬ</b>\n\nID: <code>{user['user_id']}</code>\n"
        f"Username: @{escape(user['username'] or 'нет')}\n\n"
        f"{badge(user)}💰 SD: <b>{user['sd']}</b>\n⭐ Уровень: <b>{user['level']}</b>\n"
        f"✨ XP: <b>{user['xp']}</b>\n\n"
        f"🎁 Кейсов: <b>{opens}</b>\n🎒 Предметов: <b>{inv}</b>\n"
        f"🏅 Достижений: <b>{achs}</b>\n👥 Рефералов: <b>{refs}</b>\n"
        f"💎 CosDrop+: <b>{sub}</b>",
        reply_markup=back(),
    )
    await callback.answer()


@dp.callback_query(F.data == "balance")
async def balance(callback: CallbackQuery):
    user = ensure(callback.from_user)
    await callback.message.edit_text(
        f"💰 <b>БАЛАНС</b>\n\nТвой баланс: <b>{user['sd']} SD</b>\n\n"
        f"🎁 Ежедневный бонус: <b>+{DAILY_BASE} SD</b>\n\n"
        f"SD — виртуальная валюта Cos-drop.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить бонус", callback_data="daily")],
            [InlineKeyboardButton(text="⭐ Пополнить", callback_data="topup")],
            [InlineKeyboardButton(text="💸 Вывод", callback_data="withdraw")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="home")],
        ]),
    )
    await callback.answer()


@dp.callback_query(F.data == "daily")
async def daily(callback: CallbackQuery):
    con = db()
    row = con.execute("SELECT * FROM users WHERE user_id=?", (callback.from_user.id,)).fetchone()
    t = today()
    if row["daily_claim"] == t:
        con.close()
        return await callback.answer("Бонус уже получен сегодня.", show_alert=True)

    streak = row["daily_streak"] or 0
    if row["daily_claim"]:
        try:
            last = datetime.fromisoformat(row["daily_claim"]).date()
            if (datetime.now(timezone.utc).date() - last).days != 1:
                streak = 0
        except Exception:
            streak = 0
    streak += 1

    reward = DAILY_BASE
    if streak in DAILY_STREAK_BONUS:
        reward += DAILY_STREAK_BONUS[streak]
    if has_sub(row):
        reward *= SUB_BONUS["daily_mult"]

    con.execute("""UPDATE users SET sd=sd+?, daily_claim=?, daily_streak=?,
                   xp=xp+5, last_activity=? WHERE user_id=?""",
                (reward, t, streak, now(), callback.from_user.id))
    con.commit()
    con.close()

    await callback.answer(f"🎁 +{reward} SD\n🔥 Стрик: {streak} дней", show_alert=True)
    await balance(callback)


# ============================================================
# TOPUP
# ============================================================

@dp.callback_query(F.data == "topup")
async def topup(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    for sd, stars in PACKS:
        b.button(text=f"⭐ {sd} SD — {stars} ⭐", callback_data=f"buy:{sd}:{stars}")
    b.button(text="◀️ Назад", callback_data="home")
    b.adjust(1)
    await callback.message.edit_text(
        "⭐ <b>ПОПОЛНЕНИЕ</b>\n\nВыбери пакет:",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def buy_pack(callback: CallbackQuery):
    parts = callback.data.split(":")
    sd, stars = int(parts[1]), int(parts[2])
    await bot.send_invoice(
        chat_id=callback.from_user.id, title=f"{sd} SD",
        description=f"Пополнение на {sd} SD", payload=f"sd_{sd}",
        provider_token="", currency="XTR",
        prices=[LabeledPrice(label=f"{sd} SD", amount=stars)],
    )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def payment_success(message: Message):
    payload = message.successful_payment.invoice_payload
    uid = message.from_user.id

    # CosDrop+ подписка
    if payload.startswith("sub_"):
        try:
            days = int(payload.split("_")[1])
        except (IndexError, ValueError):
            days = SUB_DAYS
        until = datetime.now(timezone.utc) + timedelta(days=days)
        con = db()
        con.execute("UPDATE users SET sub_until=? WHERE user_id=?",
                    (until.isoformat(), uid))
        con.commit()
        con.close()
        await message.answer(
            f"💎 CosDrop+ активирован до {until.date().isoformat()}!",
            reply_markup=home_kb())
        return

    # Пополнение SD
    try:
        amount_sd = int(payload.split("_")[1])
    except (IndexError, ValueError):
        amount_sd = 100
    add_sd(uid, amount_sd)

    user = get_user(uid)
    if user and user["referrer_id"]:
        add_sd(user["referrer_id"], REF_BONUS_DONATE)
        try:
            await bot.send_message(user["referrer_id"],
                                   f"💸 Твой реферал купил Stars!\n💰 +{REF_BONUS_DONATE} SD")
        except Exception:
            pass

    con = db()
    con.execute("UPDATE users SET donated=donated+1 WHERE user_id=?", (uid,))
    con.commit()
    con.close()

    await message.answer(f"✅ Оплата получена!\n💰 +{amount_sd} SD",
                         reply_markup=home_kb())
    await check_achievements(uid)


# ============================================================
# SUBSCRIBE
# ============================================================

@dp.callback_query(F.data == "subscribe")
async def subscribe(callback: CallbackQuery):
    user = ensure(callback.from_user)
    status = "✅ активна до " + user["sub_until"][:10] if has_sub(user) else "❌ нет"
    b = InlineKeyboardBuilder()
    b.button(text=f"💎 Купить CosDrop+ ({SUB_PRICE} ⭐ / {SUB_DAYS} дней)", callback_data="sub_buy")
    b.button(text="◀️ Назад", callback_data="home")
    b.adjust(1)
    await callback.message.edit_text(
        f"💎 <b>CosDrop+</b>\n\nСтатус: <b>{status}</b>\n\n"
        f"Что даёт:\n"
        f"• 💰 ×{SUB_BONUS['daily_mult']} к ежедневному бонусу\n"
        f"• ✨ +{int((SUB_BONUS['xp_mult']-1)*100)}% к XP\n"
        f"• {SUB_BONUS['badge']} значок рядом с ником\n"
        f"• Приоритетная поддержка\n\n"
        f"Цена: <b>{SUB_PRICE} ⭐ / {SUB_DAYS} дней</b>",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@dp.callback_query(F.data == "sub_buy")
async def sub_buy(callback: CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id, title="CosDrop+",
        description=f"Подписка CosDrop+ на {SUB_DAYS} дней",
        payload=f"sub_{SUB_DAYS}", provider_token="", currency="XTR",
        prices=[LabeledPrice(label="CosDrop+", amount=SUB_PRICE)],
    )
    await callback.answer()


# ============================================================
# CASINO
# ============================================================

@dp.callback_query(F.data == "casino")
async def casino_main(callback: CallbackQuery):
    user = ensure(callback.from_user)
    if user["blocked"]:
        return await callback.answer("Заблокирован.", show_alert=True)
    await callback.message.edit_text(
        f"🎰 <b>COS-CASINO</b>\n\n💰 Баланс: <b>{user['sd']} SD</b>\n\nВыбери игру:",
        reply_markup=casino_menu(),
    )
    await callback.answer()


def _log_bet(uid, game, bet, win):
    profit = win - bet
    con = db()
    con.execute("INSERT INTO casino_bets(user_id,game,bet,win,profit,created_at) VALUES(?,?,?,?,?,?)",
                (uid, game, bet, win, profit, now()))
    con.execute("""INSERT INTO casino_stats(user_id,total_bets,total_won,total_lost,biggest_win)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       total_bets = total_bets + 1,
                       total_won = total_won + excluded.total_won,
                       total_lost = total_lost + excluded.total_lost,
                       biggest_win = MAX(biggest_win, excluded.biggest_win)""",
                (uid, 1,
                 win if profit > 0 else 0,
                 bet if profit < 0 else 0,
                 win if profit > 0 else 0))
    con.commit()
    con.close()


def _check_loss_limit(uid, bet):
    con = db()
    row = con.execute("SELECT daily_loss, daily_loss_date FROM users WHERE user_id=?",
                      (uid,)).fetchone()
    con.close()
    if not row:
        return False
    if row["daily_loss_date"] != today():
        return False
    return (row["daily_loss"] or 0) + bet > CASINO_DAILY_LOSS_LIMIT


def _apply_loss(uid, amount):
    con = db()
    row = con.execute("SELECT daily_loss, daily_loss_date FROM users WHERE user_id=?",
                      (uid,)).fetchone()
    if row and row["daily_loss_date"] == today():
        new_loss = (row["daily_loss"] or 0) + amount
    else:
        new_loss = amount
    con.execute("UPDATE users SET daily_loss=?, daily_loss_date=? WHERE user_id=?",
                (new_loss, today(), uid))
    con.commit()
    con.close()


@dp.callback_query(F.data == "cas_slots")
async def cas_slots(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎰 <b>СЛОТЫ</b>\n\nВыбери ставку:\n\n"
        "🍒🍒🍒 ×3\n🍋🍋🍋 ×4\n🔔🔔🔔 ×6\n"
        "💎💎💎 ×12\n7️⃣7️⃣7️⃣ ×25\n⭐⭐⭐ ×50",
        reply_markup=bet_kb("slots"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cas_dice")
async def cas_dice(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎲 <b>КОСТИ</b>\n\nПосле ставки выбери:\n"
        "Меньше 7 — ×2\nБольше 7 — ×2\nРовно 7 — ×5\n\nВыбери ставку:",
        reply_markup=bet_kb("dice"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cas_coin")
async def cas_coin(callback: CallbackQuery):
    await callback.message.edit_text(
        "🪙 <b>МОНЕТКА</b>\n\n×2 при угадывании\n\nВыбери ставку:",
        reply_markup=bet_kb("coin"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cas_roulette")
async def cas_roulette(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎡 <b>РУЛЕТКА</b>\n\nПосле ставки выбери:\n"
        "🔴 Красное ×2\n⚫ Чёрное ×2\n🟢 Зелёное (0) ×14\n\nВыбери ставку:",
        reply_markup=bet_kb("roulette"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cas_mines")
async def cas_mines(callback: CallbackQuery):
    await callback.message.edit_text(
        "💣 <b>МИНЫ</b>\n\nВыбери ставку:",
        reply_markup=bet_kb("mines"),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("bet:"))
async def bet_select(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    game, val = parts[1], parts[2]
    if val == "custom":
        await state.set_state(CasinoBet.amount)
        await state.update_data(game=game)
        await callback.message.edit_text(
            f"✏️ Введи сумму ставки (от {CASINO_MIN_BET} до {CASINO_MAX_BET} SD):",
            reply_markup=back("casino"),
        )
        await callback.answer()
        return

    bet = int(val)
    await _casino_continue(callback, game, bet)


@dp.message(StateFilter(CasinoBet.amount))
async def bet_custom(message: Message, state: FSMContext):
    try:
        bet = int((message.text or "").strip())
    except ValueError:
        return await message.answer("❌ Введи целое число.")
    if bet < CASINO_MIN_BET or bet > CASINO_MAX_BET:
        return await message.answer(f"❌ От {CASINO_MIN_BET} до {CASINO_MAX_BET} SD.")
    data = await state.get_data()
    game = data.get("game")
    await state.clear()

    if game == "slots":
        await _slots_spin(message, message.from_user.id, bet)
        return
    await message.answer(f"Игра: {game} · Ставка: {bet} SD",
                         reply_markup=back("casino"))


async def _casino_continue(callback, game, bet):
    if game == "dice":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Меньше 7 (×2)", callback_data=f"dice:lt:{bet}")],
            [InlineKeyboardButton(text="Больше 7 (×2)", callback_data=f"dice:gt:{bet}")],
            [InlineKeyboardButton(text="Ровно 7 (×5)", callback_data=f"dice:eq:{bet}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="casino")],
        ])
        await callback.message.edit_text(f"🎲 Ставка: <b>{bet} SD</b>\n\nТвой выбор:", reply_markup=kb)
    elif game == "coin":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Орёл", callback_data=f"coin:o:{bet}")],
            [InlineKeyboardButton(text="🪙 Решка", callback_data=f"coin:r:{bet}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="casino")],
        ])
        await callback.message.edit_text(f"🪙 Ставка: <b>{bet} SD</b>\n\nТвой выбор:", reply_markup=kb)
    elif game == "roulette":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Красное ×2", callback_data=f"rl:red:{bet}")],
            [InlineKeyboardButton(text="⚫ Чёрное ×2", callback_data=f"rl:black:{bet}")],
            [InlineKeyboardButton(text="🟢 Зелёное ×14", callback_data=f"rl:green:{bet}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="casino")],
        ])
        await callback.message.edit_text(f"🎡 Ставка: <b>{bet} SD</b>\n\nТвой выбор:", reply_markup=kb)
    elif game == "mines":
        kb = InlineKeyboardBuilder()
        for m in [1, 3, 5, 10, 24]:
            kb.button(text=f"💣 {m} мин", callback_data=f"mines:{bet}:{m}")
        kb.button(text="◀️ Назад", callback_data="casino")
        kb.adjust(3, 2, 1)
        await callback.message.edit_text(f"💣 Ставка: <b>{bet} SD</b>\n\nВыбери число мин:",
                                         reply_markup=kb.as_markup())
    elif game == "slots":
        await _slots_spin(callback.message, callback.from_user.id, bet)
    await callback.answer()


async def _slots_spin(message, uid, bet):
    if not take_sd(uid, bet):
        try:
            await message.edit_text("❌ Недостаточно SD.", reply_markup=back("casino"))
        except Exception:
            await bot.send_message(uid, "❌ Недостаточно SD.")
        return

    frames = [[random.choice(SLOT_SYMBOLS) for _ in range(3)] for _ in range(8)]
    final = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    if random.random() < 0.20:
        sym = random.choice(SLOT_SYMBOLS)
        final = [sym, sym, sym]
    frames.append(final)

    key = tuple(final)
    mult = SLOT_PAYOUTS.get(key, 0)
    win = min(bet * mult, CASINO_MAX_WIN)
    if win > 0:
        add_sd(uid, win)
        _log_bet(uid, "slots", bet, win)
    else:
        _log_bet(uid, "slots", bet, 0)
        _apply_loss(uid, bet)

    for f in frames:
        txt = "🎰 <b>СЛОТЫ</b>\n\n" + " | ".join(f) + f"\n\nСтавка: <b>{bet} SD</b>"
        try:
            await message.edit_text(txt)
        except Exception:
            pass
        await asyncio.sleep(0.35)

    result = "🎰 <b>СЛОТЫ</b>\n\n" + " | ".join(final) + "\n\n"
    if win > 0:
        result += f"🎉 Выигрыш: <b>+{win} SD</b> (×{mult})"
    else:
        result += f"❌ Мимо. Потеряно: <b>{bet} SD</b>"

    try:
        await message.edit_text(result, reply_markup=back("casino"))
    except Exception:
        await bot.send_message(uid, result, reply_markup=back("casino"))

    await check_achievements(uid)
    await bump_task(uid, "bet3", 1)
    if win > bet:
        await bump_task(uid, "win1", 1)


@dp.callback_query(F.data.startswith("dice:"))
async def dice_play(callback: CallbackQuery):
    parts = callback.data.split(":")
    choice, bet = parts[1], int(parts[2])
    if _check_loss_limit(callback.from_user.id, bet):
        return await callback.answer("Дневной лимит проигрыша.", show_alert=True)
    if not take_sd(callback.from_user.id, bet):
        return await callback.answer("Недостаточно SD.", show_alert=True)

    a, b = random.randint(1, 6), random.randint(1, 6)
    total = a + b
    win = 0
    if choice == "lt" and total < 7:
        win = bet * 2
    elif choice == "gt" and total > 7:
        win = bet * 2
    elif choice == "eq" and total == 7:
        win = bet * 5
    win = min(win, CASINO_MAX_WIN)

    if win > 0:
        add_sd(callback.from_user.id, win)
        _log_bet(callback.from_user.id, "dice", bet, win)
    else:
        _log_bet(callback.from_user.id, "dice", bet, 0)
        _apply_loss(callback.from_user.id, bet)

    await check_achievements(callback.from_user.id)
    await bump_task(callback.from_user.id, "bet3", 1)
    if win > bet:
        await bump_task(callback.from_user.id, "win1", 1)

    txt = f"🎲 Кости: <b>{a} + {b} = {total}</b>\n\n"
    txt += f"🎉 Выигрыш: <b>+{win} SD</b>" if win > 0 else f"❌ Потеряно: <b>{bet} SD</b>"
    await callback.message.edit_text(txt, reply_markup=back("casino"))
    await callback.answer()


@dp.callback_query(F.data.startswith("coin:"))
async def coin_play(callback: CallbackQuery):
    parts = callback.data.split(":")
    choice, bet = parts[1], int(parts[2])
    if _check_loss_limit(callback.from_user.id, bet):
        return await callback.answer("Дневной лимит.", show_alert=True)
    if not take_sd(callback.from_user.id, bet):
        return await callback.answer("Недостаточно SD.", show_alert=True)

    result = random.choice(["o", "r"])
    win = bet * 2 if result == choice else 0

    if win > 0:
        add_sd(callback.from_user.id, win)
        _log_bet(callback.from_user.id, "coin", bet, win)
    else:
        _log_bet(callback.from_user.id, "coin", bet, 0)
        _apply_loss(callback.from_user.id, bet)

    await check_achievements(callback.from_user.id)
    await bump_task(callback.from_user.id, "bet3", 1)
    if win > bet:
        await bump_task(callback.from_user.id, "win1", 1)

    emoji = "🪙 Орёл" if result == "o" else "🪙 Решка"
    txt = f"{emoji}\n\n"
    txt += f"🎉 +{win} SD" if win > 0 else f"❌ Потеряно: {bet} SD"
    await callback.message.edit_text(txt, reply_markup=back("casino"))
    await callback.answer()


@dp.callback_query(F.data.startswith("rl:"))
async def roulette_play(callback: CallbackQuery):
    parts = callback.data.split(":")
    choice, bet = parts[1], int(parts[2])
    if _check_loss_limit(callback.from_user.id, bet):
        return await callback.answer("Дневной лимит.", show_alert=True)
    if not take_sd(callback.from_user.id, bet):
        return await callback.answer("Недостаточно SD.", show_alert=True)

    reds = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    num = random.randint(0, 36)
    if num == 0:
        color = "green"
    elif num in reds:
        color = "red"
    else:
        color = "black"

    win = 0
    if choice == color:
        win = bet * (14 if color == "green" else 2)
    win = min(win, CASINO_MAX_WIN)

    if win > 0:
        add_sd(callback.from_user.id, win)
        _log_bet(callback.from_user.id, "roulette", bet, win)
    else:
        _log_bet(callback.from_user.id, "roulette", bet, 0)
        _apply_loss(callback.from_user.id, bet)

    await check_achievements(callback.from_user.id)
    await bump_task(callback.from_user.id, "bet3", 1)
    if win > bet:
        await bump_task(callback.from_user.id, "win1", 1)

    emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[color]
    txt = f"🎡 Выпало: <b>{num}</b> {emoji}\n\n"
    txt += f"🎉 +{win} SD" if win > 0 else f"❌ Потеряно: {bet} SD"
    await callback.message.edit_text(txt, reply_markup=back("casino"))
    await callback.answer()


@dp.callback_query(F.data.startswith("mines:"))
async def mines_start(callback: CallbackQuery):
    parts = callback.data.split(":")
    bet, mines = int(parts[1]), int(parts[2])
    if _check_loss_limit(callback.from_user.id, bet):
        return await callback.answer("Дневной лимит.", show_alert=True)
    if not take_sd(callback.from_user.id, bet):
        return await callback.answer("Недостаточно SD.", show_alert=True)

    safe_cells = 25 - mines
    mult_per_cell = round((25 / max(safe_cells, 1)) * 0.95, 2)

    con = db()
    con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                (f"mines_{callback.from_user.id}",
                 json.dumps({"bet": bet, "mines": mines,
                             "opened": [], "safe": safe_cells,
                             "mult_per": mult_per_cell,
                             "picked": sorted(random.sample(range(25), mines))})))
    con.commit()
    con.close()

    await _mines_render(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


async def _mines_render(message, uid, edit=False):
    con = db()
    row = con.execute("SELECT value FROM settings WHERE key=?", (f"mines_{uid}",)).fetchone()
    con.close()
    if not row:
        return

    st = json.loads(row["value"])
    opened = st["opened"]
    mult = round(st["mult_per"] ** len(opened), 2) if opened else 1.0
    potential = int(st["bet"] * mult)

    b = InlineKeyboardBuilder()
    for i in range(25):
        if i in opened:
            b.button(text="💎", callback_data=f"mine_open:{i}")
        else:
            b.button(text="⬜", callback_data=f"mine_open:{i}")
    b.button(text=f"💰 Забрать {potential} SD", callback_data="mine_take")
    b.adjust(5, 5, 5, 5, 5, 1)

    txt = (f"💣 <b>МИНЫ</b>\n\nМин: <b>{st['mines']}</b>\n"
           f"Открыто: <b>{len(opened)}</b>\nМножитель: <b>×{mult}</b>\n"
           f"Можно забрать: <b>{potential} SD</b>")
    if edit:
        try:
            await message.edit_text(txt, reply_markup=b.as_markup())
        except Exception:
            await bot.send_message(uid, txt, reply_markup=b.as_markup())
    else:
        await bot.send_message(uid, txt, reply_markup=b.as_markup())


@dp.callback_query(F.data.startswith("mine_open:"))
async def mine_open(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1])
    uid = callback.from_user.id

    con = db()
    row = con.execute("SELECT value FROM settings WHERE key=?", (f"mines_{uid}",)).fetchone()
    if not row:
        con.close()
        return await callback.answer("Игра не найдена.", show_alert=True)

    st = json.loads(row["value"])
    if idx in st["opened"]:
        con.close()
        return await callback.answer("Уже открыто.")

    if idx in st["picked"]:
        con.execute("DELETE FROM settings WHERE key=?", (f"mines_{uid}",))
        con.commit()
        con.close()
        _log_bet(uid, "mines", st["bet"], 0)
        _apply_loss(uid, st["bet"])
        await callback.message.edit_text(
            f"💥 <b>МИНА!</b>\n\nПотеряно: <b>{st['bet']} SD</b>",
            reply_markup=back("casino"),
        )
        await callback.answer()
        return

    st["opened"].append(idx)
    con.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(st), f"mines_{uid}"))
    con.commit()
    con.close()

    await _mines_render(callback.message, uid, edit=True)
    await callback.answer()


@dp.callback_query(F.data == "mine_take")
async def mine_take(callback: CallbackQuery):
    uid = callback.from_user.id
    con = db()
    row = con.execute("SELECT value FROM settings WHERE key=?", (f"mines_{uid}",)).fetchone()
    if not row:
        con.close()
        return await callback.answer("Игра не найдена.", show_alert=True)

    st = json.loads(row["value"])
    con.execute("DELETE FROM settings WHERE key=?", (f"mines_{uid}",))
    con.commit()
    con.close()

    if not st["opened"]:
        return await callback.answer("Открой хоть одну клетку.", show_alert=True)

    mult = round(st["mult_per"] ** len(st["opened"]), 2)
    win = int(st["bet"] * mult)
    if win > CASINO_MAX_WIN:
        win = CASINO_MAX_WIN

    add_sd(uid, win)
    _log_bet(uid, "mines", st["bet"], win)
    await check_achievements(uid)
    await bump_task(uid, "bet3", 1)
    if win > st["bet"]:
        await bump_task(uid, "win1", 1)

    await callback.message.edit_text(
        f"💰 <b>Забрано</b>\n\nОткрыто клеток: <b>{len(st['opened'])}</b>\n"
        f"Выигрыш: <b>+{win} SD</b> (×{mult})",
        reply_markup=back("casino"),
    )
    await callback.answer()


@dp.callback_query(F.data == "cas_stats")
async def cas_stats(callback: CallbackQuery):
    con = db()
    row = con.execute("SELECT * FROM casino_stats WHERE user_id=?", (callback.from_user.id,)).fetchone()
    con.close()
    if not row:
        return await callback.message.edit_text("📊 Статистики пока нет.", reply_markup=back("casino"))
    profit = row["total_won"] - row["total_lost"]
    txt = (f"📊 <b>МОЯ СТАТИСТИКА</b>\n\n"
           f"Всего ставок: <b>{row['total_bets']}</b>\n"
           f"Выиграно: <b>{row['total_won']} SD</b>\n"
           f"Проиграно: <b>{row['total_lost']} SD</b>\n"
           f"Профит: <b>{profit:+d} SD</b>\n"
           f"Лучший выигрыш: <b>{row['biggest_win']} SD</b>")
    await callback.message.edit_text(txt, reply_markup=back("casino"))
    await callback.answer()


@dp.callback_query(F.data == "cas_top")
async def cas_top(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT u.username, u.first_name, cs.biggest_win
                          FROM casino_stats cs JOIN users u ON u.user_id=cs.user_id
                          WHERE cs.biggest_win > 0
                          ORDER BY cs.biggest_win DESC LIMIT 10""").fetchall()
    con.close()
    if not rows:
        return await callback.message.edit_text("🏆 Пока нет выигрышей.", reply_markup=back("casino"))
    txt = "🏆 <b>ТОП ВЫИГРЫШЕЙ</b>\n\n" + "\n".join(
        f"{i}. @{escape(r['username'] or r['first_name'] or '-')} — {r['biggest_win']} SD"
        for i, r in enumerate(rows, 1))
    await callback.message.edit_text(txt, reply_markup=back("casino"))
    await callback.answer()


# ============================================================
# TASKS
# ============================================================

def _get_daily_tasks(uid):
    con = db()
    tasks = con.execute("SELECT * FROM tasks").fetchall()
    out = []
    for t in tasks:
        ut = con.execute("SELECT * FROM user_tasks WHERE user_id=? AND task_id=? AND date=?",
                         (uid, t["id"], today())).fetchone()
        out.append((t, ut))
    con.close()
    return out


async def bump_task(uid, code, amount):
    con = db()
    t = con.execute("SELECT * FROM tasks WHERE code=?", (code,)).fetchone()
    if not t:
        con.close()
        return
    ut = con.execute("SELECT * FROM user_tasks WHERE user_id=? AND task_id=? AND date=?",
                     (uid, t["id"], today())).fetchone()
    if not ut:
        con.execute("INSERT INTO user_tasks(user_id,task_id,date,progress) VALUES(?,?,?,?)",
                    (uid, t["id"], today(), amount))
        new_progress = amount
        done = 0
    else:
        if ut["done"]:
            con.close()
            return
        new_progress = ut["progress"] + amount
        done = ut["done"]
        con.execute("UPDATE user_tasks SET progress=? WHERE id=?", (new_progress, ut["id"]))

    if new_progress >= t["goal"] and not done:
        con.execute("UPDATE user_tasks SET done=1 WHERE user_id=? AND task_id=? AND date=?",
                    (uid, t["id"], today()))
        con.execute("UPDATE users SET sd=sd+? WHERE user_id=?", (t["reward"], uid))
        try:
            await bot.send_message(uid, f"✅ Задание выполнено: {t['name']}\n💰 +{t['reward']} SD")
        except Exception:
            pass
    con.commit()
    con.close()


@dp.callback_query(F.data == "tasks")
async def tasks_menu(callback: CallbackQuery):
    rows = _get_daily_tasks(callback.from_user.id)
    if not rows:
        return await callback.message.edit_text("📋 Заданий нет.", reply_markup=back())
    txt = "📋 <b>ЕЖЕДНЕВНЫЕ ЗАДАНИЯ</b>\n\n"
    for t, ut in rows:
        progress = ut["progress"] if ut else 0
        done = "✅" if ut and ut["done"] else ""
        txt += f"{done} <b>{escape(t['name'])}</b>\n"
        txt += f"└ {escape(t['description'])} — {progress}/{t['goal']}\n"
        txt += f"└ 💰 +{t['reward']} SD\n\n"
    await callback.message.edit_text(txt, reply_markup=back())
    await callback.answer()


# ============================================================
# DUELS
# ============================================================

@dp.callback_query(F.data == "duels")
async def duels_menu(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="⚔️ Создать дуэль", callback_data="duel_create")
    b.button(text="📜 Мои дуэли", callback_data="duel_my")
    b.button(text="◀️ Назад", callback_data="home")
    b.adjust(1)
    await callback.message.edit_text(
        "⚔️ <b>ДУЭЛИ</b>\n\nВызов другому игроку. Оба ставят одинаковую сумму, "
        "победитель забирает банк минус 5% комиссии.",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@dp.callback_query(F.data == "duel_create")
async def duel_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DuelBet.amount)
    await callback.message.edit_text(
        "⚔️ Введи сумму дуэли (от 100 SD):",
        reply_markup=back("duels"),
    )
    await callback.answer()


@dp.message(StateFilter(DuelBet.amount))
async def duel_amount(message: Message, state: FSMContext):
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        return await message.answer("❌ Введи целое число.")
    if amount < 100:
        return await message.answer("❌ Минимум 100 SD.")
    if not take_sd(message.from_user.id, amount):
        return await message.answer("❌ Недостаточно SD.")

    con = db()
    cur = con.execute("""INSERT INTO duels(challenger_id,opponent_id,amount,status,created_at)
                         VALUES(?,?,?,?,?)""",
                      (message.from_user.id, 0, amount, "open", now()))
    did = cur.lastrowid
    con.commit()
    con.close()

    await state.clear()
    await message.answer(
        f"⚔️ Дуэль создана!\n\nСсылка для вызова:\n"
        f"<code>/duel {did}</code>\n\nСумма: <b>{amount} SD</b>",
        reply_markup=back("duels"),
    )


@dp.message(Command("duel"))
async def duel_accept(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Использование: /duel ID")
    try:
        did = int(parts[1])
    except ValueError:
        return await message.answer("❌ Неверный ID.")

    con = db()
    row = con.execute("SELECT * FROM duels WHERE id=?", (did,)).fetchone()
    if not row or row["status"] != "open":
        con.close()
        return await message.answer("❌ Дуэль недоступна.")
    if row["challenger_id"] == message.from_user.id:
        con.close()
        return await message.answer("❌ Нельзя сражаться с собой.")

    opponent = ensure(message.from_user)
    if opponent["sd"] < row["amount"]:
        con.close()
        return await message.answer("❌ Недостаточно SD.")

    con.execute("UPDATE users SET sd=sd-? WHERE user_id=?", (row["amount"], message.from_user.id))
    winner = random.choice([row["challenger_id"], message.from_user.id])
    pot = row["amount"] * 2
    commission = int(pot * 0.05)
    prize = pot - commission

    con.execute("UPDATE users SET sd=sd+? WHERE user_id=?", (prize, winner))
    con.execute("""UPDATE duels SET opponent_id=?, status='done', winner_id=?, finished_at=?
                   WHERE id=?""",
                (message.from_user.id, winner, now(), did))
    con.commit()
    con.close()

    await check_achievements(winner)
    await message.answer(
        f"⚔️ <b>ДУЭЛЬ ЗАВЕРШЕНА</b>\n\nПобедитель: <code>{winner}</code>\nПриз: <b>{prize} SD</b>",
    )
    try:
        await bot.send_message(row["challenger_id"],
                               f"⚔️ Дуэль #{did} завершена.\nПобедитель: <code>{winner}</code>")
    except Exception:
        pass


@dp.callback_query(F.data == "duel_my")
async def duel_my(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT * FROM duels WHERE challenger_id=? OR opponent_id=?
                          ORDER BY id DESC LIMIT 20""",
                      (callback.from_user.id, callback.from_user.id)).fetchall()
    con.close()
    if not rows:
        return await callback.message.edit_text("📜 Дуэлей нет.", reply_markup=back("duels"))
    txt = "📜 <b>МОИ ДУЭЛИ</b>\n\n"
    for r in rows:
        who = "я vs ?" if r["opponent_id"] == 0 else f"я vs {r['opponent_id']}"
        txt += f"#{r['id']} · {who} · {r['amount']} SD · {r['status']}\n"
    await callback.message.edit_text(txt, reply_markup=back("duels"))
    await callback.answer()


# ============================================================
# REFERRAL
# ============================================================

@dp.callback_query(F.data == "ref")
async def ref_menu(callback: CallbackQuery):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={callback.from_user.id}"
    con = db()
    refs = con.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?",
                       (callback.from_user.id,)).fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"👥 <b>РЕФЕРАЛЫ</b>\n\n"
        f"Приглашено: <b>{refs}</b>\n\n"
        f"За каждого приглашённого: <b>+{REF_BONUS_INVITE} SD</b>\n"
        f"Если друг купит Stars: <b>+{REF_BONUS_DONATE} SD</b>\n\n"
        f"Твоя ссылка:\n<code>{link}</code>",
        reply_markup=back(),
    )
    await callback.answer()


# ============================================================
# RATING
# ============================================================

@dp.callback_query(F.data == "rating")
async def rating(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT username, first_name, xp,
                          (SELECT COUNT(*) FROM inventory i WHERE i.user_id=u.user_id) items
                          FROM users u WHERE blocked=0
                          ORDER BY xp DESC, items DESC LIMIT 10""").fetchall()
    con.close()
    if rows:
        text = "\n".join(f"{i}. @{escape(r['username'] or r['first_name'] or '-')}"
                         f" — ⭐ {r['xp']} · 🎒 {r['items']}"
                         for i, r in enumerate(rows, 1))
    else:
        text = "Пока нет игроков."
    await callback.message.edit_text(f"🏆 <b>ТОП-10</b>\n\n{text}", reply_markup=back())
    await callback.answer()


# ============================================================
# ACHIEVEMENTS
# ============================================================

async def check_achievements(uid):
    con = db()
    user = con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if not user:
        con.close()
        return

    opens = con.execute("SELECT COUNT(*) n FROM case_opens WHERE user_id=?", (uid,)).fetchone()["n"]
    items = con.execute("SELECT COUNT(*) n FROM inventory WHERE user_id=?", (uid,)).fetchone()["n"]
    bets = con.execute("SELECT COUNT(*) n FROM casino_bets WHERE user_id=?", (uid,)).fetchone()["n"]
    wins = con.execute("SELECT COUNT(*) n FROM duels WHERE winner_id=? AND status='done'", (uid,)).fetchone()["n"]
    refs = con.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?", (uid,)).fetchone()["n"]

    checks = []
    if opens >= 1: checks.append("first_case")
    if opens >= 10: checks.append("ten_cases")
    if opens >= 100: checks.append("hundred_cases")
    if items >= 10: checks.append("collector")
    if user["sd"] >= 5000: checks.append("rich")
    if bets >= 100: checks.append("casino_king")
    if wins >= 5: checks.append("duelist")
    if refs >= 3: checks.append("referrer")

    for code in checks:
        a = con.execute("SELECT * FROM achievements WHERE code=?", (code,)).fetchone()
        if not a:
            continue
        if con.execute("SELECT 1 FROM user_achievements WHERE user_id=? AND achievement_id=?",
                       (uid, a["id"])).fetchone():
            continue
        con.execute("INSERT INTO user_achievements(user_id,achievement_id,obtained_at) VALUES(?,?,?)",
                    (uid, a["id"], now()))
        if a["reward"] > 0:
            con.execute("UPDATE users SET sd=sd+? WHERE user_id=?", (a["reward"], uid))
        try:
            await bot.send_message(uid,
                f"🏅 <b>ДОСТИЖЕНИЕ!</b>\n\n{a['name']}\n{a['description']}\n💰 +{a['reward']} SD")
        except Exception:
            pass

    level = max(1, user["xp"] // 100 + 1)
    con.execute("UPDATE users SET level=? WHERE user_id=?", (level, uid))
    con.commit()
    con.close()


@dp.callback_query(F.data == "achievements")
async def achievements(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT a.*, ua.obtained_at FROM achievements a
                          LEFT JOIN user_achievements ua ON ua.achievement_id=a.id AND ua.user_id=?
                          ORDER BY a.id""", (callback.from_user.id,)).fetchall()
    con.close()
    lines = []
    for r in rows:
        mark = "✅" if r["obtained_at"] else "🔒"
        lines.append(f"{mark} <b>{escape(r['name'])}</b>\n└ {escape(r['description'])}\n└ 💰 +{r['reward']} SD")
    await callback.message.edit_text("🏅 <b>ДОСТИЖЕНИЯ</b>\n\n" + "\n\n".join(lines), reply_markup=back())
    await callback.answer()


# ============================================================
# ABOUT
# ============================================================

@dp.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ <b>О COS-DROP</b>\n\n"
        "Коллекционный Telegram-проект с кейсами, казино, дуэлями, "
        "достижениями и рейтингами.\n\n"
        "💰 SD — виртуальная валюта.\n🎒 Предметы — виртуальные.\n\n"
        "Все игровые ценности не имеют денежной стоимости.",
        reply_markup=back(),
    )
    await callback.answer()


# ============================================================
# MEDIA
# ============================================================

@dp.callback_query(F.data == "media")
async def media(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="📩 Отправить заявку", callback_data="media_apply")
    b.button(text="◀️ Назад", callback_data="home")
    b.adjust(1)
    await callback.message.edit_text(
        "🎬 <b>МЕДИА / ПАРТНЁРСТВО</b>\n\n"
        "Снимай короткие ролики, рекламируй бота, получай бонусы.\n\n"
        "Нажми кнопку ниже, чтобы отправить заявку.",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@dp.callback_query(F.data == "media_apply")
async def media_apply(callback: CallbackQuery):
    load_msg = await callback.message.edit_text("⏳ Загрузка...")
    for i in range(0, 101, 10):
        await asyncio.sleep(0.18)
        filled = i // 10
        bar = "█" * filled + "░" * (10 - filled)
        try:
            await load_msg.edit_text(
                f"⏳ <b>Загрузка информации о партнёрстве...</b>\n\n<code>[{bar}] {i}%</code>")
        except Exception:
            pass
    await load_msg.edit_text(
        "✅ <b>ГОТОВО</b>\n\n🎬 <b>МЕДИА / ПАРТНЁРСТВО</b>\n\n"
        "Чтобы попасть в медиа, напиши создателю:\n\n"
        "👉 <a href=\"https://t.me/d3v_exe\">@d3v_exe</a>\n\n"
        "📌 Что даёт партнёрство:\n"
        "• 🎟 личный промокод\n"
        "• 💰 пополнение баланса за активность\n"
        "• 🚀 продвижение в топе",
        reply_markup=back(),
        disable_web_page_preview=True,
    )
    await callback.answer()


# ============================================================
# WITHDRAW
# ============================================================

@dp.callback_query(F.data == "withdraw")
async def withdraw_start(callback: CallbackQuery, state: FSMContext):
    user = ensure(callback.from_user)
    if user["blocked"]:
        return await callback.answer("Заблокирован.", show_alert=True)
    if user["sd"] < MIN_WITHDRAW_SD:
        return await callback.answer(f"Минимум: {MIN_WITHDRAW_SD} SD", show_alert=True)
    await state.set_state(WithdrawFSM.amount)
    await callback.message.edit_text(
        f"💸 <b>ВЫВОД</b>\n\nБаланс: <b>{user['sd']} SD</b>\n"
        f"Минимум: <b>{MIN_WITHDRAW_SD} SD</b>\n\nВведи сумму:"
    )
    await callback.answer()


@dp.message(StateFilter(WithdrawFSM.amount))
async def withdraw_amount(message: Message, state: FSMContext):
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        return await message.answer("❌ Введи целое число.")
    if amount < MIN_WITHDRAW_SD:
        return await message.answer(f"❌ Минимум {MIN_WITHDRAW_SD} SD.")
    if amount > DAILY_LIMIT_WITHDRAW:
        return await message.answer(f"❌ Максимум в день: {DAILY_LIMIT_WITHDRAW} SD.")

    con = db()
    user = con.execute("SELECT sd FROM users WHERE user_id=?", (message.from_user.id,)).fetchone()
    if not user or user["sd"] < amount:
        con.close()
        await state.clear()
        return await message.answer("❌ Недостаточно SD.")

    con.execute("UPDATE users SET sd=sd-? WHERE user_id=?", (amount, message.from_user.id))
    cur = con.execute("INSERT INTO withdraws(user_id,amount,created_at) VALUES(?,?,?)",
                      (message.from_user.id, amount, now()))
    wid = cur.lastrowid
    con.commit()
    con.close()
    await state.clear()

    await message.answer(f"✅ Заявка #{wid} на {amount} SD создана.")
    try:
        await bot.send_message(ADMIN_ID,
            f"💸 Заявка на вывод #{wid}\n👤 {message.from_user.id}\n💰 {amount} SD",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Ок", callback_data=f"wd_ok:{wid}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"wd_no:{wid}"),
            ]]))
    except Exception:
        pass


@dp.callback_query(F.data.startswith("wd_ok:"))
async def withdraw_ok(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    wid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM withdraws WHERE id=?", (wid,)).fetchone()
    if not row or row["status"] != "pending":
        con.close()
        return await callback.answer("Уже обработана.", show_alert=True)
    con.execute("UPDATE withdraws SET status='paid', admin_id=?, decided_at=? WHERE id=?",
                (ADMIN_ID, now(), wid))
    con.commit()
    con.close()
    log_admin("withdraw_paid", row["user_id"], str(wid))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Выплачено.")
    try:
        await bot.send_message(row["user_id"], f"✅ Заявка #{wid} выплачена.")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("wd_no:"))
async def withdraw_no(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    wid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM withdraws WHERE id=?", (wid,)).fetchone()
    if not row or row["status"] != "pending":
        con.close()
        return await callback.answer("Уже обработана.", show_alert=True)
    con.execute("UPDATE users SET sd=sd+? WHERE user_id=?", (row["amount"], row["user_id"]))
    con.execute("UPDATE withdraws SET status='rejected', admin_id=?, decided_at=? WHERE id=?",
                (ADMIN_ID, now(), wid))
    con.commit()
    con.close()
    log_admin("withdraw_rejected", row["user_id"], str(wid))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отклонено, SD возвращены.")
    try:
        await bot.send_message(row["user_id"], f"❌ Заявка #{wid} отклонена, SD возвращены.")
    except Exception:
        pass


@dp.callback_query(F.data == "adm_withdraws")
async def admin_withdraws(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    rows = con.execute("SELECT * FROM withdraws ORDER BY id DESC LIMIT 30").fetchall()
    con.close()
    txt = "\n".join(f"#{r['id']} · {r['user_id']} · {r['amount']} SD · {r['status']}" for r in rows) or "Пусто."
    await callback.message.edit_text(f"💸 <b>ЗАЯВКИ НА ВЫВОД</b>\n\n{txt}", reply_markup=admin_kb())
    await callback.answer()


# ============================================================
# APPLICATIONS
# ============================================================

@dp.callback_query(F.data == "apps")
async def applications(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT id,kind,status FROM applications
                          WHERE user_id=? ORDER BY id DESC LIMIT 10""",
                      (callback.from_user.id,)).fetchall()
    con.close()
    txt = "\n".join(f"#{r['id']} · {r['kind']} · {r['status']}" for r in rows) or "Заявок нет."
    await callback.message.edit_text(f"📝 <b>МОИ ЗАЯВКИ</b>\n\n{txt}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать заявку", callback_data="newapp")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="home")],
        ]))
    await callback.answer()


@dp.callback_query(F.data == "newapp")
async def new_application(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Apply.name)
    await callback.message.edit_text("📝 <b>ЗАЯВКА</b>\n\nВведите имя:")
    await callback.answer()


@dp.message(StateFilter(Apply.name))
async def app_name(message: Message, state: FSMContext):
    await state.update_data(name=(message.text or "")[:100])
    await state.set_state(Apply.cls)
    await message.answer("🏫 Введите класс:")


@dp.message(StateFilter(Apply.cls))
async def app_cls(message: Message, state: FSMContext):
    await state.update_data(cls=(message.text or "")[:30])
    await state.set_state(Apply.phone)
    await message.answer("📱 Контакт (по желанию):")


@dp.message(StateFilter(Apply.phone))
async def app_phone(message: Message, state: FSMContext):
    await state.update_data(phone=(message.text or "")[:50])
    await state.set_state(Apply.msg)
    await message.answer("💬 Сообщение:")


@dp.message(StateFilter(Apply.msg))
async def app_msg(message: Message, state: FSMContext):
    data = await state.update_data(msg=(message.text or "")[:1000])
    con = db()
    cur = con.execute("""INSERT INTO applications(user_id,kind,name,class_name,phone,message,created_at)
                         VALUES(?,?,?,?,?,?,?)""",
                      (message.from_user.id, "general", data["name"], data["cls"],
                       data["phone"], data["msg"], now()))
    aid = cur.lastrowid
    con.commit()
    con.close()
    await state.clear()
    await message.answer(f"✅ Заявка #{aid} создана.")
    try:
        await bot.send_message(ADMIN_ID,
            f"📝 Заявка #{aid}\n👤 {data['name']}\n🏫 {data['cls']}\n"
            f"📱 {data['phone']}\n💬 {data['msg']}\n🆔 {message.from_user.id}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Принять", callback_data=f"appok:{aid}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"appno:{aid}"),
            ]]))
    except Exception:
        pass


@dp.callback_query(F.data.startswith("appok:"))
async def app_ok(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    aid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
    if not row:
        con.close()
        return await callback.answer("Не найдена.", show_alert=True)
    con.execute("UPDATE applications SET status='approved', admin_id=?, decided_at=? WHERE id=?",
                (ADMIN_ID, now(), aid))
    con.commit()
    con.close()
    log_admin("approve_application", row["user_id"], str(aid))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Принята.")
    try:
        await bot.send_message(row["user_id"], f"✅ Заявка #{aid} принята.")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("appno:"))
async def app_no(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    aid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM applications WHERE id=?", (aid,)).fetchone()
    if not row:
        con.close()
        return await callback.answer("Не найдена.", show_alert=True)
    con.execute("UPDATE applications SET status='rejected', admin_id=?, decided_at=? WHERE id=?",
                (ADMIN_ID, now(), aid))
    con.commit()
    con.close()
    log_admin("reject_application", row["user_id"], str(aid))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отклонена.")
    try:
        await bot.send_message(row["user_id"], f"❌ Заявка #{aid} отклонена.")
    except Exception:
        pass


# ============================================================
# PROMO
# ============================================================

@dp.callback_query(F.data == "promo")
async def promo_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Promo.code)
    await callback.message.edit_text("🎟 <b>ПРОМОКОД</b>\n\nВведите код:")
    await callback.answer()


@dp.message(StateFilter(Promo.code))
async def use_promo(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    con = db()
    promo = con.execute("SELECT * FROM promo_codes WHERE code=? AND enabled=1", (code,)).fetchone()
    if not promo:
        con.close()
        await state.clear()
        return await message.answer("❌ Промокод не найден.")
    if con.execute("SELECT 1 FROM promo_uses WHERE promo_id=? AND user_id=?",
                   (promo["id"], message.from_user.id)).fetchone():
        con.close()
        await state.clear()
        return await message.answer("❌ Уже использован.")
    if promo["uses"] >= promo["max_uses"]:
        con.close()
        await state.clear()
        return await message.answer("❌ Лимит исчерпан.")

    con.execute("INSERT INTO promo_uses(promo_id,user_id,used_at) VALUES(?,?,?)",
                (promo["id"], message.from_user.id, now()))
    con.execute("UPDATE promo_codes SET uses=uses+1 WHERE id=?", (promo["id"],))
    con.execute("UPDATE users SET sd=sd+? WHERE user_id=?", (promo["reward"], message.from_user.id))
    con.commit()
    con.close()
    await state.clear()
    await message.answer(f"🎉 +{promo['reward']} SD")
    await check_achievements(message.from_user.id)


# ============================================================
# ADMIN PANEL
# ============================================================

@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 <b>ADMIN PANEL</b>", reply_markup=admin_kb())


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text("👑 <b>ADMIN PANEL</b>", reply_markup=admin_kb())
    await callback.answer()


@dp.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    u = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    a = con.execute("SELECT COUNT(*) n FROM users WHERE blocked=0").fetchone()["n"]
    b = con.execute("SELECT COUNT(*) n FROM users WHERE blocked=1").fetchone()["n"]
    sd = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    o = con.execute("SELECT COUNT(*) n FROM case_opens").fetchone()["n"]
    i = con.execute("SELECT COUNT(*) n FROM inventory").fetchone()["n"]
    app = con.execute("SELECT COUNT(*) n FROM applications WHERE status='pending'").fetchone()["n"]
    p = con.execute("SELECT COUNT(*) n FROM promo_codes WHERE enabled=1").fetchone()["n"]
    w = con.execute("SELECT COUNT(*) n FROM withdraws WHERE status='pending'").fetchone()["n"]
    cb = con.execute("SELECT COUNT(*) n FROM casino_bets").fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"📊 <b>СТАТИСТИКА</b>\n\n👥 Юзеров: <b>{u}</b>\n🟢 Активных: <b>{a}</b>\n"
        f"🚫 Блок: <b>{b}</b>\n💰 Всего SD: <b>{sd}</b>\n\n"
        f"🎁 Кейсов: <b>{o}</b>\n🎒 Предметов: <b>{i}</b>\n"
        f"🎰 Ставок: <b>{cb}</b>\n\n📝 Заявок: <b>{app}</b>\n"
        f"🎟 Промо: <b>{p}</b>\n💸 Выводов: <b>{w}</b>",
        reply_markup=admin_kb(),
    )
    await callback.answer()


@dp.callback_query(F.data == "adm_users")
async def adm_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    rows = con.execute("""SELECT user_id,username,first_name,sd,level,blocked
                          FROM users ORDER BY id DESC LIMIT 20""").fetchall()
    con.close()
    txt = "\n".join(f"{'🚫' if r['blocked'] else '🟢'} <code>{r['user_id']}</code> "
                    f"@{escape(r['username'] or '-')} · {r['sd']} SD"
                    for r in rows) or "Пусто."
    await callback.message.edit_text(f"👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n{txt}", reply_markup=admin_kb())
    await callback.answer()


@dp.callback_query(F.data == "adm_search")
async def adm_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(UserSearch.query)
    await callback.message.edit_text("🔎 ID или username:")
    await callback.answer()


@dp.message(StateFilter(UserSearch.query))
async def adm_search_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    q = (message.text or "").strip()
    con = db()
    if q.isdigit():
        row = con.execute("SELECT * FROM users WHERE user_id=?", (int(q),)).fetchone()
    else:
        row = con.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)",
                          (q.lstrip("@"),)).fetchone()
    con.close()
    await state.clear()
    if not row:
        return await message.answer("❌ Не найден.")
    await message.answer(
        f"👤 <code>{row['user_id']}</code>\n@{escape(row['username'] or '-')}\n"
        f"💰 {row['sd']} SD · Lv.{row['level']}\n"
        f"🚫 {'Да' if row['blocked'] else 'Нет'}",
        reply_markup=admin_kb(),
    )


@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(GiveSD.uid)
    await callback.message.edit_text("🎁 ID:")
    await callback.answer()


@dp.message(StateFilter(GiveSD.uid))
async def adm_give_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌ ID числом.")
    await state.update_data(uid=uid)
    await state.set_state(GiveSD.amount)
    await message.answer("💰 Сумма:")


@dp.message(StateFilter(GiveSD.amount))
async def adm_give_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌ Число.")
    data = await state.get_data()
    add_sd(data["uid"], amount)
    log_admin("give_sd", data["uid"], str(amount))
    await state.clear()
    await message.answer(f"✅ +{amount} SD → {data['uid']}")


@dp.callback_query(F.data == "adm_take")
async def adm_take(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(TakeSD.uid)
    await callback.message.edit_text("➖ ID:")
    await callback.answer()


@dp.message(StateFilter(TakeSD.uid))
async def adm_take_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌ ID числом.")
    await state.update_data(uid=uid)
    await state.set_state(TakeSD.amount)
    await message.answer("Сумма:")


@dp.message(StateFilter(TakeSD.amount))
async def adm_take_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌ Число.")
    data = await state.get_data()
    con = db()
    row = con.execute("SELECT sd FROM users WHERE user_id=?", (data["uid"],)).fetchone()
    if not row:
        con.close()
        return await message.answer("❌ Не найден.")
    nb = max(0, row["sd"] - amount)
    con.execute("UPDATE users SET sd=? WHERE user_id=?", (nb, data["uid"]))
    con.commit()
    con.close()
    log_admin("take_sd", data["uid"], str(amount))
    await state.clear()
    await message.answer(f"✅ -{amount} SD → {data['uid']}\nНовый: {nb}")


@dp.callback_query(F.data == "adm_blocks")
async def adm_blocks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Блок", callback_data="block_start")],
        [InlineKeyboardButton(text="🔓 Разблок", callback_data="unblock_start")],
        [InlineKeyboardButton(text="📋 Список", callback_data="blocked_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")],
    ])
    await callback.message.edit_text("🚫 <b>БЛОКИРОВКИ</b>", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "block_start")
async def block_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BlockUser.uid)
    await callback.message.edit_text("🚫 ID:")
    await callback.answer()


@dp.message(StateFilter(BlockUser.uid))
async def block_do(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌")
    con = db()
    con.execute("UPDATE users SET blocked=1 WHERE user_id=?", (uid,))
    con.commit()
    con.close()
    log_admin("block_user", uid)
    await state.clear()
    await message.answer(f"🚫 {uid} заблокирован.")


@dp.callback_query(F.data == "unblock_start")
async def unblock_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UnblockUser.uid)
    await callback.message.edit_text("🔓 ID:")
    await callback.answer()


@dp.message(StateFilter(UnblockUser.uid))
async def unblock_do(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌")
    con = db()
    con.execute("UPDATE users SET blocked=0 WHERE user_id=?", (uid,))
    con.commit()
    con.close()
    log_admin("unblock_user", uid)
    await state.clear()
    await message.answer(f"🔓 {uid} разблокирован.")


@dp.callback_query(F.data == "blocked_list")
async def blocked_list(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT user_id,username FROM users WHERE blocked=1
                          ORDER BY id DESC LIMIT 50""").fetchall()
    con.close()
    txt = "\n".join(f"🚫 <code>{r['user_id']}</code> @{escape(r['username'] or '-')}" for r in rows) or "Пусто."
    await callback.message.edit_text(f"🚫 <b>ЗАБЛОКИРОВАННЫЕ</b>\n\n{txt}", reply_markup=back("adm_blocks"))
    await callback.answer()


@dp.callback_query(F.data == "adm_promo")
async def adm_promo(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    rows = con.execute("SELECT code,reward,uses,max_uses FROM promo_codes WHERE enabled=1").fetchall()
    con.close()
    txt = "\n".join(f"🔹 <code>{escape(r['code'])}</code> — +{r['reward']} SD · "
                    f"{r['uses']}/{r['max_uses']}" for r in rows) or "Пусто."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="promo_add"),
         InlineKeyboardButton(text="🗑 Удалить", callback_data="promo_del")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")],
    ])
    await callback.message.edit_text(f"🎟 <b>ПРОМОКОДЫ</b>\n\n{txt}", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "promo_add")
async def promo_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(PromoCreate.code)
    await callback.message.edit_text("➕ Введите код:")
    await callback.answer()


@dp.message(StateFilter(PromoCreate.code))
async def promo_add_code(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{2,32}", code):
        return await message.answer("❌ Только A-Z, 0-9, _, -")
    con = db()
    if con.execute("SELECT 1 FROM promo_codes WHERE code=?", (code,)).fetchone():
        con.close()
        return await message.answer("❌ Уже есть.")
    con.close()
    await state.update_data(code=code)
    await state.set_state(PromoCreate.reward)
    await message.answer("💰 Сколько SD:")


@dp.message(StateFilter(PromoCreate.reward))
async def promo_add_reward(message: Message, state: FSMContext):
    try:
        reward = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌")
    data = await state.get_data()
    con = db()
    con.execute("INSERT INTO promo_codes(code,reward,max_uses,uses,enabled) VALUES(?,?,999999999,0,1)",
                (data["code"], reward))
    con.commit()
    con.close()
    log_admin("create_promo", details=f"{data['code']} +{reward}")
    await state.clear()
    await message.answer(f"✅ {data['code']} +{reward} SD")


@dp.callback_query(F.data == "promo_del")
async def promo_del(callback: CallbackQuery, state: FSMContext):
    con = db()
    rows = con.execute("SELECT code FROM promo_codes WHERE enabled=1").fetchall()
    con.close()
    txt = ", ".join(r["code"] for r in rows) or "Пусто."
    await state.set_state(PromoDelete.code)
    await callback.message.edit_text(f"🗑 Введите код для удаления:\n\n{txt}")
    await callback.answer()


@dp.message(StateFilter(PromoDelete.code))
async def promo_del_do(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    con = db()
    row = con.execute("SELECT * FROM promo_codes WHERE code=?", (code,)).fetchone()
    if not row:
        con.close()
        return await message.answer("❌ Не найден.")
    con.execute("DELETE FROM promo_uses WHERE promo_id=?", (row["id"],))
    con.execute("DELETE FROM promo_codes WHERE id=?", (row["id"],))
    con.commit()
    con.close()
    log_admin("delete_promo", details=code)
    await state.clear()
    await message.answer(f"🗑 {code} удалён.")


@dp.callback_query(F.data == "adm_cases")
async def adm_cases(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    rows = con.execute("SELECT id,code,name,price,enabled FROM cases ORDER BY id").fetchall()
    con.close()
    txt = "\n".join(f"{'🟢' if r['enabled'] else '🔴'} {r['name']} · ID:{r['id']} · {r['price']} SD"
                    for r in rows)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Вкл/выкл", callback_data="case_toggle_start")],
        [InlineKeyboardButton(text="💰 Цена", callback_data="case_price_start")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")],
    ])
    await callback.message.edit_text(f"📦 <b>КЕЙСЫ</b>\n\n{txt}", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "case_toggle_start")
async def case_toggle_start(callback: CallbackQuery):
    con = db()
    rows = con.execute("SELECT id,name,enabled FROM cases ORDER BY id").fetchall()
    con.close()
    kb = []
    for r in rows:
        kb.append([InlineKeyboardButton(text=f"{'🟢' if r['enabled'] else '🔴'} {r['name']}",
                                        callback_data=f"case_toggle:{r['id']}")])
    kb.append([InlineKeyboardButton(text="◀️", callback_data="adm_cases")])
    await callback.message.edit_text("🎮 Выбери:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("case_toggle:"))
async def case_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    cid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT enabled FROM cases WHERE id=?", (cid,)).fetchone()
    if not row:
        con.close()
        return await callback.answer("Нет.", show_alert=True)
    nv = 0 if row["enabled"] else 1
    con.execute("UPDATE cases SET enabled=? WHERE id=?", (nv, cid))
    con.commit()
    con.close()
    log_admin("toggle_case", details=f"{cid}:{nv}")
    await callback.answer("Изменено.", show_alert=True)
    await adm_cases(callback)


@dp.callback_query(F.data == "case_price_start")
async def case_price_start(callback: CallbackQuery, state: FSMContext):
    con = db()
    rows = con.execute("SELECT id,name,price FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"{r['name']} · {r['price']} SD",
                                callback_data=f"price_case:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="adm_cases")])
    await callback.message.edit_text("💰 Выбери:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("price_case:"))
async def price_case(callback: CallbackQuery, state: FSMContext):
    cid = int(callback.data.split(":")[1])
    await state.update_data(case_id=cid)
    await state.set_state(CasePrice.price)
    await callback.message.edit_text("💰 Новая цена:")
    await callback.answer()


@dp.message(StateFilter(CasePrice.price))
async def price_case_do(message: Message, state: FSMContext):
    try:
        price = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌")
    data = await state.get_data()
    con = db()
    con.execute("UPDATE cases SET price=? WHERE id=?", (price, data["case_id"]))
    con.commit()
    con.close()
    log_admin("change_case_price", details=f"{data['case_id']}:{price}")
    await state.clear()
    await message.answer(f"✅ Цена: {price} SD")


@dp.callback_query(F.data == "adm_items")
async def adm_items(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    rows = con.execute("SELECT code,name,rarity,enabled FROM items ORDER BY id").fetchall()
    con.close()
    txt = "\n".join(f"{'🟢' if r['enabled'] else '🔴'} {RARITY.get(r['rarity'], '⚪')} {r['name']}"
                    for r in rows)
    await callback.message.edit_text(f"💎 <b>ПРЕДМЕТЫ</b>\n\n{txt}", reply_markup=back("admin_home"))
    await callback.answer()


@dp.callback_query(F.data == "adm_apps")
async def adm_apps(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    rows = con.execute("""SELECT id,user_id,name,status FROM applications
                          ORDER BY id DESC LIMIT 30""").fetchall()
    con.close()
    txt = "\n".join(f"#{r['id']} · {r['user_id']} · {r['name']} · {r['status']}" for r in rows) or "Пусто."
    await callback.message.edit_text(f"📝 <b>ЗАЯВКИ</b>\n\n{txt}", reply_markup=admin_kb())
    await callback.answer()


@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(Broadcast.text)
    await callback.message.edit_text("📢 Текст рассылки:")
    await callback.answer()


@dp.message(StateFilter(Broadcast.text))
async def broadcast_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    con = db()
    users = con.execute("SELECT user_id FROM users WHERE blocked=0").fetchall()
    con.close()
    s, f = 0, 0
    for r in users:
        try:
            await bot.send_message(r["user_id"], message.text or "")
            s += 1
        except Exception:
            f += 1
        await asyncio.sleep(0.05)
    await state.clear()
    log_admin("broadcast", details=f"s={s},f={f}")
    await message.answer(f"✅ Отправлено: {s}\n❌ Ошибок: {f}")


@dp.callback_query(F.data == "adm_logs")
async def adm_logs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    con = db()
    rows = con.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 30").fetchall()
    con.close()
    txt = "\n".join(f"🕐 {r['created_at'][:19]} · {r['action']} · {r['target_user_id'] or '-'}"
                    for r in rows) or "Пусто."
    await callback.message.edit_text(f"📜 <b>ЛОГИ</b>\n\n{txt}", reply_markup=admin_kb())
    await callback.answer()


@dp.callback_query(F.data == "adm_backup")
async def adm_backup(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BACKUP_DIR, f"cosdrop_{ts}.sqlite3")
        src = sqlite3.connect(DB_FILE)
        dst = sqlite3.connect(path)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        await callback.message.edit_text(f"💾 Бэкап создан:\n<code>{escape(path)}</code>",
                                         reply_markup=admin_kb())
        await callback.answer("Готово.")
    except Exception as e:
        await callback.answer("Ошибка.", show_alert=True)
        await callback.message.answer(f"❌ {escape(str(e))}")
        # ============================================================
# ADMIN PANEL v2 — расширение (130+ функций)
# ============================================================

# -------------------- FSM --------------------

class AdmSetSD(StatesGroup): uid = State(); val = State()
class AdmAddXP(StatesGroup): uid = State(); val = State()
class AdmSetLevel(StatesGroup): uid = State(); val = State()
class AdmGiveItem(StatesGroup): uid = State(); iid = State()
class AdmTakeItem(StatesGroup): uid = State(); iid = State()
class AdmMsgUser(StatesGroup): uid = State(); text = State()
class AdmAddCase(StatesGroup): code = State(); name = State(); desc = State(); price = State()
class AdmAddItem(StatesGroup): code = State(); name = State(); rarity = State(); price = State()
class AdmChangeCaseName(StatesGroup): cid = State(); val = State()
class AdmChangeCaseDesc(StatesGroup): cid = State(); val = State()
class AdmChangeItemName(StatesGroup): iid = State(); val = State()
class AdmChangeItemPrice(StatesGroup): iid = State(); val = State()
class AdmChangeItemRarity(StatesGroup): iid = State(); val = State()
class AdmBulkPromo(StatesGroup): count = State(); reward = State()
class AdmCreateAdmin(StatesGroup): uid = State()
class AdmDelAdmin(StatesGroup): uid = State()
class AdmMaintMsg(StatesGroup): text = State()
class AdmResetUser(StatesGroup): uid = State()
class AdmSearch(StatesGroup): q = State()
class AdmPage(StatesGroup): page = State()
class AdmLogSearch(StatesGroup): q = State()

# -------------------- KEYBOARDS --------------------

def adm_root_kb():
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📊 Статистика", "a2_stats"),
        ("👥 Юзеры", "a2_users"),
        ("📦 Кейсы", "a2_cases"),
        ("💎 Предметы", "a2_items"),
        ("🎟 Промо", "a2_promo"),
        ("💰 Экономика", "a2_econ"),
        ("🎰 Казино", "a2_casino"),
        ("💎 Подписки", "a2_subs"),
        ("📋 Задания", "a2_tasks"),
        ("🏅 Достижения", "a2_ach"),
        ("💸 Выводы", "a2_withdraws"),
        ("📝 Заявки", "a2_apps"),
        ("📜 Логи", "a2_logs"),
        ("🛡 Админы", "a2_admins"),
        ("🛠 Обслуживание", "a2_maint"),
        ("📢 Рассылка", "a2_broadcast_menu"),
        ("🔎 Поиск юзера", "a2_find"),
        ("❌ Закрыть", "a2_close"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
    return b.as_markup()

def a2back(cb="a2_root"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В админку", callback_data=cb)]
    ])

def a2_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="a2_root")]
    ])

# -------------------- GATE --------------------

def a2_guard(uid):
    return is_admin(uid)

@dp.message(Command("admin2"))
async def a2_open(message: Message):
    if not a2_guard(message.from_user.id):
        return
    await message.answer("👑 <b>ADMIN PANEL v2</b>\n\nВыбери раздел:", reply_markup=adm_root_kb())

@dp.callback_query(F.data == "a2_root")
async def a2_root(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id):
        return
    await callback.message.edit_text("👑 <b>ADMIN PANEL v2</b>\n\nВыбери раздел:",
                                     reply_markup=adm_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2_close")
async def a2_close(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id):
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()

# ============================================================
# 📊 СТАТИСТИКА (20 функций)
# ============================================================

def a2_stats_kb():
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📈 Общая", "a2s_full"),
        ("📅 Сегодня", "a2s_today"),
        ("🗓 Неделя", "a2s_week"),
        ("💰 Экономика", "a2s_econ"),
        ("🏆 Топ по SD", "a2s_top_sd"),
        ("⭐ Топ по XP", "a2s_top_xp"),
        ("🎁 Топ по кейсам", "a2s_top_cases"),
        ("🎰 Топ казино", "a2s_top_casino"),
        ("👥 Топ рефералов", "a2s_top_refs"),
        ("🆕 Новые сегодня", "a2s_new"),
        ("🟢 Активные сегодня", "a2s_active"),
        ("😴 Неактивные 7д", "a2s_inactive"),
        ("📉 Отток", "a2s_churn"),
        ("📊 Динамика 7д", "a2s_growth"),
        ("💎 Подписчики", "a2s_subs"),
        ("🎟 Промо-стат", "a2s_promo"),
        ("💸 Выводы", "a2s_withdraws"),
        ("🏅 Достижения", "a2s_achs"),
        ("⚔️ Дуэли", "a2s_duels"),
        ("🔄 Обновить", "a2_stats"),
    ]:
        b.button(text=t, callback_data=d)
    b.button(text="◀️ В админку", callback_data="a2_root")
    b.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
    return b.as_markup()

@dp.callback_query(F.data == "a2_stats")
async def a2_stats(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("📊 <b>СТАТИСТИКА</b>\n\nВыбери отчёт:",
                                     reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_full")
async def a2s_full(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    u = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    b = con.execute("SELECT COUNT(*) n FROM users WHERE blocked=1").fetchone()["n"]
    sd = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    inv = con.execute("SELECT COUNT(*) n FROM inventory").fetchone()["n"]
    op = con.execute("SELECT COUNT(*) n FROM case_opens").fetchone()["n"]
    bets = con.execute("SELECT COUNT(*) n FROM casino_bets").fetchone()["n"]
    wd = con.execute("SELECT COUNT(*) n FROM withdraws").fetchone()["n"]
    subs = con.execute("SELECT COUNT(*) n FROM users WHERE sub_until IS NOT NULL").fetchone()["n"]
    duels = con.execute("SELECT COUNT(*) n FROM duels").fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"📈 <b>ОБЩАЯ СТАТИСТИКА</b>\n\n"
        f"👥 Юзеров: <b>{u}</b>\n🚫 Блок: <b>{b}</b>\n"
        f"💰 SD в системе: <b>{sd}</b>\n🎒 Предметов: <b>{inv}</b>\n"
        f"🎁 Открытий: <b>{op}</b>\n🎰 Ставок: <b>{bets}</b>\n"
        f"💸 Выводов: <b>{wd}</b>\n💎 Подписок: <b>{subs}</b>\n"
        f"⚔️ Дуэлей: <b>{duels}</b>",
        reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_today")
async def a2s_today(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    t = today()
    con = db()
    nu = con.execute("SELECT COUNT(*) n FROM users WHERE created_at LIKE ?", (t+"%",)).fetchone()["n"]
    act = con.execute("SELECT COUNT(*) n FROM users WHERE last_activity LIKE ?", (t+"%",)).fetchone()["n"]
    op = con.execute("SELECT COUNT(*) n FROM case_opens WHERE created_at LIKE ?", (t+"%",)).fetchone()["n"]
    bets = con.execute("SELECT COUNT(*) n FROM casino_bets WHERE created_at LIKE ?", (t+"%",)).fetchone()["n"]
    wd = con.execute("SELECT COUNT(*) n FROM withdraws WHERE created_at LIKE ?", (t+"%",)).fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"📅 <b>СЕГОДНЯ</b>\n\n"
        f"🆕 Новых: <b>{nu}</b>\n🟢 Активных: <b>{act}</b>\n"
        f"🎁 Кейсов: <b>{op}</b>\n🎰 Ставок: <b>{bets}</b>\n"
        f"💸 Выводов: <b>{wd}</b>",
        reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_week")
async def a2s_week(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    con = db()
    nu = con.execute("SELECT COUNT(*) n FROM users WHERE created_at >= ?", (week_ago,)).fetchone()["n"]
    op = con.execute("SELECT COUNT(*) n FROM case_opens WHERE created_at >= ?", (week_ago,)).fetchone()["n"]
    bets = con.execute("SELECT COUNT(*) n FROM casino_bets WHERE created_at >= ?", (week_ago,)).fetchone()["n"]
    sd_sum = con.execute("SELECT COALESCE(SUM(profit),0) n FROM casino_bets WHERE created_at >= ?", (week_ago,)).fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"🗓 <b>ЗА 7 ДНЕЙ</b>\n\n"
        f"🆕 Новых: <b>{nu}</b>\n🎁 Кейсов: <b>{op}</b>\n"
        f"🎰 Ставок: <b>{bets}</b>\n💵 Профит казино: <b>{-sd_sum:+d} SD</b>",
        reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_econ")
async def a2s_econ(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    total_sd = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    avg_sd = con.execute("SELECT COALESCE(AVG(sd),0) n FROM users").fetchone()["n"]
    rich = con.execute("SELECT COUNT(*) n FROM users WHERE sd>=10000").fetchone()["n"]
    poor = con.execute("SELECT COUNT(*) n FROM users WHERE sd<100").fetchone()["n"]
    inv_val = con.execute("""SELECT COALESCE(SUM(i.sell_price),0) n FROM inventory inv
                             JOIN items i ON i.id=inv.item_id""").fetchone()["n"]
    donates = con.execute("SELECT COUNT(*) n FROM users WHERE donated>0").fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"💰 <b>ЭКОНОМИКА</b>\n\n"
        f"💰 Всего SD: <b>{total_sd}</b>\n📊 В среднем: <b>{int(avg_sd)} SD</b>\n"
        f"🐋 Богачей (10k+): <b>{rich}</b>\n🥚 Бедных (<100): <b>{poor}</b>\n"
        f"🎒 Стоимость инвентарей: <b>{inv_val} SD</b>\n"
        f"💎 Донатеров: <b>{donates}</b>",
        reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_top_sd")
async def a2s_top_sd(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,first_name,sd FROM users ORDER BY sd DESC LIMIT 15").fetchall()
    con.close()
    txt = "🏆 <b>ТОП ПО SD</b>\n\n" + "\n".join(
        f"{i}. <code>{r['user_id']}</code> @{escape(r['username'] or r['first_name'] or '-')} — {r['sd']}"
        for i, r in enumerate(rows, 1))
    await callback.message.edit_text(txt, reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_top_xp")
async def a2s_top_xp(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,first_name,xp FROM users ORDER BY xp DESC LIMIT 15").fetchall()
    con.close()
    txt = "⭐ <b>ТОП ПО XP</b>\n\n" + "\n".join(
        f"{i}. <code>{r['user_id']}</code> @{escape(r['username'] or r['first_name'] or '-')} — {r['xp']}"
        for i, r in enumerate(rows, 1))
    await callback.message.edit_text(txt, reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_top_cases")
async def a2s_top_cases(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT user_id, COUNT(*) n FROM case_opens
                          GROUP BY user_id ORDER BY n DESC LIMIT 15""").fetchall()
    con.close()
    txt = "🎁 <b>ТОП ПО КЕЙСАМ</b>\n\n" + "\n".join(
        f"{i}. <code>{r['user_id']}</code> — {r['n']} открытий"
        for i, r in enumerate(rows, 1))
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_top_casino")
async def a2s_top_casino(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT user_id, total_bets, total_won, total_lost, biggest_win
                          FROM casino_stats ORDER BY total_bets DESC LIMIT 15""").fetchall()
    con.close()
    txt = "🎰 <b>ТОП КАЗИНО</b>\n\n" + "\n".join(
        f"{i}. <code>{r['user_id']}</code> — ставок:{r['total_bets']} · win:{r['biggest_win']}"
        for i, r in enumerate(rows, 1))
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_top_refs")
async def a2s_top_refs(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT referrer_id, COUNT(*) n FROM users
                          WHERE referrer_id IS NOT NULL
                          GROUP BY referrer_id ORDER BY n DESC LIMIT 15""").fetchall()
    con.close()
    txt = "👥 <b>ТОП РЕФЕРАЛОВ</b>\n\n" + "\n".join(
        f"{i}. <code>{r['referrer_id']}</code> — {r['n']} приглашённых"
        for i, r in enumerate(rows, 1))
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_new")
async def a2s_new(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    t = today()
    con = db()
    rows = con.execute("SELECT user_id,username,first_name FROM users WHERE created_at LIKE ? ORDER BY id DESC LIMIT 30",
                       (t+"%",)).fetchall()
    con.close()
    txt = "🆕 <b>НОВЫЕ СЕГОДНЯ</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> @{escape(r['username'] or r['first_name'] or '-')}"
        for r in rows) or "Пусто."
    await callback.message.edit_text(txt, reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_active")
async def a2s_active(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    t = today()
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM users WHERE last_activity LIKE ?", (t+"%",)).fetchone()["n"]
    con.close()
    await callback.message.edit_text(f"🟢 <b>АКТИВНЫХ СЕГОДНЯ</b>\n\n{n} юзеров",
                                     reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_inactive")
async def a2s_inactive(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM users WHERE last_activity < ?", (week_ago,)).fetchone()["n"]
    con.close()
    await callback.message.edit_text(f"😴 <b>НЕАКТИВНЫЕ 7д</b>\n\n{n} юзеров",
                                     reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_churn")
async def a2s_churn(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    con = db()
    total = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    lost = con.execute("SELECT COUNT(*) n FROM users WHERE last_activity < ?", (week_ago,)).fetchone()["n"]
    con.close()
    pct = round(lost / max(total, 1) * 100, 1)
    await callback.message.edit_text(f"📉 <b>ОТТОК</b>\n\n{lost}/{total} = <b>{pct}%</b>",
                                     reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_growth")
async def a2s_growth(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    txt = "📊 <b>ДИНАМИКА 7д</b>\n\n"
    for i in range(7):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        n = con.execute("SELECT COUNT(*) n FROM users WHERE created_at LIKE ?", (d+"%",)).fetchone()["n"]
        txt += f"{d}: +{n}\n"
    con.close()
    await callback.message.edit_text(txt, reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_subs")
async def a2s_subs(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM users WHERE sub_until IS NOT NULL").fetchone()["n"]
    rows = con.execute("SELECT user_id,username,sub_until FROM users WHERE sub_until IS NOT NULL ORDER BY sub_until DESC LIMIT 20").fetchall()
    con.close()
    txt = f"💎 <b>ПОДПИСЧИКИ</b>\n\nВсего: <b>{n}</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> @{escape(r['username'] or '-')} до {r['sub_until'][:10]}"
        for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_promo")
async def a2s_promo(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT code, reward, uses, max_uses FROM promo_codes
                          ORDER BY uses DESC LIMIT 20""").fetchall()
    con.close()
    txt = "🎟 <b>ПРОМО-СТАТ</b>\n\n" + "\n".join(
        f"<code>{escape(r['code'])}</code> — +{r['reward']} · {r['uses']}/{r['max_uses']}"
        for r in rows) or "Пусто."
    await callback.message.edit_text(txt, reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_withdraws")
async def a2s_withdraws(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    pend = con.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM withdraws WHERE status='pending'").fetchone()
    paid = con.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM withdraws WHERE status='paid'").fetchone()
    rej = con.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM withdraws WHERE status='rejected'").fetchone()
    con.close()
    await callback.message.edit_text(
        f"💸 <b>ВЫВОДЫ</b>\n\n"
        f"⏳ В ожидании: {pend[0]} · {pend[1]} SD\n"
        f"✅ Выплачено: {paid[0]} · {paid[1]} SD\n"
        f"❌ Отклонено: {rej[0]} · {rej[1]} SD",
        reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_achs")
async def a2s_achs(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT a.name, COUNT(ua.id) n FROM achievements a
                          LEFT JOIN user_achievements ua ON ua.achievement_id=a.id
                          GROUP BY a.id ORDER BY n DESC""").fetchall()
    con.close()
    txt = "🏅 <b>ДОСТИЖЕНИЯ</b>\n\n" + "\n".join(f"{r['name']} — {r['n']} получений" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_stats_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_duels")
async def a2s_duels(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    total = con.execute("SELECT COUNT(*) n FROM duels").fetchone()["n"]
    done = con.execute("SELECT COUNT(*) n FROM duels WHERE status='done'").fetchone()["n"]
    pot = con.execute("SELECT COALESCE(SUM(amount),0) n FROM duels WHERE status='done'").fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"⚔️ <b>ДУЭЛИ</b>\n\nВсего: <b>{total}</b>\nЗавершено: <b>{done}</b>\n"
        f"Оборот: <b>{pot} SD</b>",
        reply_markup=a2_stats_kb())
    await callback.answer()

# ============================================================
# 👥 ЮЗЕРЫ (30+ функций)
# ============================================================

def a2_users_kb():
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📋 Список", "a2u_list"),
        ("🔎 Поиск", "a2u_search"),
        ("📊 Топ активных", "a2u_top_active"),
        ("🆕 Новые", "a2u_new"),
        ("🎁 Выдать SD", "a2u_give_sd"),
        ("➖ Забрать SD", "a2u_take_sd"),
        ("📝 Установить SD", "a2u_set_sd"),
        ("⭐ Выдать XP", "a2u_give_xp"),
        ("📈 Установить уровень", "a2u_set_lvl"),
        ("🎒 Выдать предмет", "a2u_give_item"),
        ("🗑 Забрать предмет", "a2u_take_item"),
        ("💎 Выдать подписку", "a2u_give_sub"),
        ("🚫 Блок", "a2u_block"),
        ("🔓 Разблок", "a2u_unblock"),
        ("🗑 Полный сброс", "a2u_reset"),
        ("✉️ Написать юзеру", "a2u_msg"),
        ("🕵️ Поиск мультиакков", "a2u_alts"),
        ("📄 Экспорт CSV", "a2u_export"),
        ("👻 Удалить заблокированных", "a2u_purge_blocked"),
        ("◀️ В админку", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()

@dp.callback_query(F.data == "a2_users")
async def a2_users(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("👥 <b>УПРАВЛЕНИЕ ЮЗЕРАМИ</b>",
                                     reply_markup=a2_users_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2u_list")
async def a2u_list(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,first_name,sd,level,blocked FROM users ORDER BY id DESC LIMIT 30").fetchall()
    con.close()
    txt = "📋 <b>ПОСЛЕДНИЕ 30</b>\n\n" + "\n".join(
        f"{'🚫' if r['blocked'] else '🟢'} <code>{r['user_id']}</code> @{escape(r['username'] or '-')} · {r['sd']} SD · L{r['level']}"
        for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_users_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2u_search")
async def a2u_search(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmSearch.q)
    await callback.message.edit_text("🔎 Отправь ID или @username:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmSearch.q))
async def a2u_search_do(message: Message, state: FSMContext):
    if not a2_guard(message.from_user.id): return
    q = (message.text or "").strip()
    con = db()
    if q.isdigit():
        row = con.execute("SELECT * FROM users WHERE user_id=?", (int(q),)).fetchone()
    else:
        row = con.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (q.lstrip("@"),)).fetchone()
    con.close()
    await state.clear()
    if not row:
        return await message.answer("❌ Не найден.", reply_markup=a2_users_kb())
    u = row
    txt = (f"👤 <b>КАРТОЧКА</b>\n\n"
           f"🆔 <code>{u['user_id']}</code>\n"
           f"👤 @{escape(u['username'] or '-')}\n"
           f"📛 {escape(u['first_name'] or '-')}\n\n"
           f"💰 SD: <b>{u['sd']}</b> · ⭐ Lv {u['level']} · ✨ XP {u['xp']}\n"
           f"🚫 Блок: {'Да' if u['blocked'] else 'Нет'}\n"
           f"💎 Донат: {u['donated']}\n"
           f"👥 Рефов: ?\n"
           f"📅 Регистрация: {u['created_at'][:10]}\n"
           f"🕐 Последняя: {(u['last_activity'] or '')[:10]}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать", callback_data=f"a2u_msgto:{u['user_id']}")],
        [InlineKeyboardButton(text="🎁 SD", callback_data=f"a2u_gsd:{u['user_id']}"),
         InlineKeyboardButton(text="➖ SD", callback_data=f"a2u_tsd:{u['user_id']}")],
        [InlineKeyboardButton(text="🎒 Дать предмет", callback_data=f"a2u_gi:{u['user_id']}"),
         InlineKeyboardButton(text="🗑 Забрать", callback_data=f"a2u_ti:{u['user_id']}")],
        [InlineKeyboardButton(text="💎 Подписка", callback_data=f"a2u_sub:{u['user_id']}")],
        [InlineKeyboardButton(text="🚫 Блок" if not u['blocked'] else "🔓 Разблок",
                              callback_data=f"a2u_tb:{u['user_id']}")],
        [InlineKeyboardButton(text="🗑 Сброс", callback_data=f"a2u_rst:{u['user_id']}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="a2_users")],
    ])
    await message.answer(txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("a2u_msgto:"))
async def a2u_msgto(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    await state.update_data(uid=uid)
    await state.set_state(AdmMsgUser.text)
    await callback.message.edit_text(f"✉️ Текст для <code>{uid}</code>:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmMsgUser.text))
async def a2u_msg_do(message: Message, state: FSMContext):
    if not a2_guard(message.from_user.id): return
    data = await state.get_data()
    uid = data.get("uid")
    try:
        await bot.send_message(uid, f"📩 <b>Сообщение от админа:</b>\n\n{message.text}")
        await message.answer("✅ Отправлено.", reply_markup=a2_users_kb())
    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=a2_users_kb())
    await state.clear()

@dp.callback_query(F.data.startswith("a2u_gsd:"))
async def a2u_gsd(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    await state.update_data(uid=uid); await state.set_state(AdmSetSD.val)
    await callback.message.edit_text(f"🎁 Сколько SD дать <code>{uid}</code>?", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data.startswith("a2u_tsd:"))
async def a2u_tsd(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    await state.update_data(uid=uid); await state.set_state(AdmSetSD.val); await state.update_data(mode="take")
    await callback.message.edit_text(f"➖ Сколько SD забрать у <code>{uid}</code>?", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data.startswith("a2u_rst:"))
async def a2u_rst(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    con = db()
    con.execute("UPDATE users SET sd=0, xp=0, level=1, daily_claim=NULL, daily_streak=0, sub_until=NULL WHERE user_id=?", (uid,))
    con.execute("DELETE FROM inventory WHERE user_id=?", (uid,))
    con.execute("DELETE FROM casino_stats WHERE user_id=?", (uid,))
    con.commit(); con.close()
    log_admin("full_reset", uid)
    await callback.answer("✅ Сброшено.", show_alert=True)

@dp.callback_query(F.data.startswith("a2u_tb:"))
async def a2u_tb(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT blocked FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row:
        con.close(); return await callback.answer("Нет.", show_alert=True)
    nv = 0 if row["blocked"] else 1
    con.execute("UPDATE users SET blocked=? WHERE user_id=?", (nv, uid))
    con.commit(); con.close()
    log_admin("toggle_block", uid, str(nv))
    await callback.answer("Изменено.", show_alert=True)

@dp.callback_query(F.data.startswith("a2u_sub:"))
async def a2u_sub(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="+7д", callback_data=f"a2u_subg:{uid}:7"),
         InlineKeyboardButton(text="+30д", callback_data=f"a2u_subg:{uid}:30"),
         InlineKeyboardButton(text="+365д", callback_data=f"a2u_subg:{uid}:365")],
        [InlineKeyboardButton(text="❌ Убрать", callback_data=f"a2u_subg:{uid}:0")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="a2_users")],
    ])
    await callback.message.edit_text(f"💎 Подписка для <code>{uid}</code>:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("a2u_subg:"))
async def a2u_subg(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    _, uid_s, days_s = callback.data.split(":")
    uid, days = int(uid_s), int(days_s)
    con = db()
    if days == 0:
        con.execute("UPDATE users SET sub_until=NULL WHERE user_id=?", (uid,))
    else:
        until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        con.execute("UPDATE users SET sub_until=? WHERE user_id=?", (until, uid))
    con.commit(); con.close()
    log_admin("give_sub", uid, str(days))
    await callback.answer(f"✅ Подписка: {days}д", show_alert=True)

@dp.message(StateFilter(AdmSetSD.val))
async def a2u_sd_do(message: Message, state: FSMContext):
    if not a2_guard(message.from_user.id): return
    try:
        val = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌ Число.")
    data = await state.get_data()
    uid = data.get("uid"); mode = data.get("mode", "give")
    if mode == "take":
        con = db()
        row = con.execute("SELECT sd FROM users WHERE user_id=?", (uid,)).fetchone()
        nb = max(0, (row["sd"] if row else 0) - val)
        con.execute("UPDATE users SET sd=? WHERE user_id=?", (nb, uid))
        con.commit(); con.close()
    elif mode == "set":
        con = db()
        con.execute("UPDATE users SET sd=? WHERE user_id=?", (val, uid))
        con.commit(); con.close()
    else:
        add_sd(uid, val)
    log_admin(f"{mode}_sd", uid, str(val))
    await state.clear()
    await message.answer(f"✅ Готово: {mode} {val} SD → {uid}", reply_markup=a2_users_kb())

@dp.callback_query(F.data.startswith("a2u_gi:"))
async def a2u_gi(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    con = db()
    rows = con.execute("SELECT id,code,name FROM items ORDER BY id").fetchall()
    con.close()
    b = InlineKeyboardBuilder()
    for r in rows[:30]:
        b.button(text=r["name"], callback_data=f"a2u_giset:{uid}:{r['id']}")
    b.button(text="◀️ Назад", callback_data="a2_users")
    b.adjust(3)
    await callback.message.edit_text("🎒 Какой предмет выдать?", reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("a2u_giset:"))
async def a2u_giset(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    _, uid_s, iid_s = callback.data.split(":")
    uid, iid = int(uid_s), int(iid_s)
    con = db()
    con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)", (uid, iid, now()))
    con.commit(); con.close()
    log_admin("give_item", uid, str(iid))
    await callback.answer("✅ Предмет выдан.", show_alert=True)

@dp.callback_query(F.data.startswith("a2u_ti:"))
async def a2u_ti(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    con = db()
    n = con.execute("DELETE FROM inventory WHERE user_id=?", (uid,)).rowcount
    con.commit(); con.close()
    log_admin("clear_inventory", uid, str(n))
    await callback.answer(f"🗑 Удалено: {n}", show_alert=True)

@dp.callback_query(F.data == "a2u_top_active")
async def a2u_top_active(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,xp FROM users ORDER BY xp DESC LIMIT 20").fetchall()
    con.close()
    txt = "📊 <b>ТОП АКТИВНЫХ</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> @{escape(r['username'] or '-')} — {r['xp']} XP" for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_users_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2u_new")
async def a2u_new(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    t = today()
    con = db()
    rows = con.execute("SELECT user_id,username FROM users WHERE created_at LIKE ? ORDER BY id DESC LIMIT 30",
                       (t+"%",)).fetchall()
    con.close()
    txt = "🆕 <b>НОВЫЕ СЕГОДНЯ</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> @{escape(r['username'] or '-')}" for r in rows) or "Пусто."
    await callback.message.edit_text(txt, reply_markup=a2_users_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2u_give_sd")
async def a2u_give_sd(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmSetSD.uid); await state.update_data(mode="give")
    await callback.message.edit_text("🎁 ID юзера:", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2u_take_sd")
async def a2u_take_sd(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmSetSD.uid); await state.update_data(mode="take")
    await callback.message.edit_text("➖ ID юзера:", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2u_set_sd")
async def a2u_set_sd(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmSetSD.uid); await state.update_data(mode="set")
    await callback.message.edit_text("📝 ID юзера:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmSetSD.uid))
async def a2u_sd_uid(message: Message, state: FSMContext):
    if not a2_guard(message.from_user.id): return
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return await message.answer("❌ ID.")
    await state.update_data(uid=uid); await state.set_state(AdmSetSD.val)
    await message.answer("Значение:")

@dp.callback_query(F.data == "a2u_give_xp")
async def a2u_give_xp(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmAddXP.uid)
    await callback.message.edit_text("⭐ ID юзера:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmAddXP.uid))
async def a2u_xp_uid(message: Message, state: FSMContext):
    if not a2_guard(message.from_user.id): return
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return
    await state.update_data(uid=uid); await state.set_state(AdmAddXP.val)
    await message.answer("Кол-во XP:")

@dp.message(StateFilter(AdmAddXP.val))
async def a2u_xp_val(message: Message, state: FSMContext):
    if not a2_guard(message.from_user.id): return
    try:
        v = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    con = db()
    con.execute("UPDATE users SET xp=xp+? WHERE user_id=?", (v, data["uid"]))
    con.commit(); con.close()
    log_admin("give_xp", data["uid"], str(v))
    await state.clear()
    await message.answer(f"✅ +{v} XP → {data['uid']}", reply_markup=a2_users_kb())

@dp.callback_query(F.data == "a2u_set_lvl")
async def a2u_set_lvl(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmSetLevel.uid)
    await callback.message.edit_text("📈 ID:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmSetLevel.uid))
async def a2u_lvl_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return
    await state.update_data(uid=uid); await state.set_state(AdmSetLevel.val)
    await message.answer("Уровень:")

@dp.message(StateFilter(AdmSetLevel.val))
async def a2u_lvl_val(message: Message, state: FSMContext):
    try:
        v = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    con = db()
    con.execute("UPDATE users SET level=? WHERE user_id=?", (v, data["uid"]))
    con.commit(); con.close()
    await state.clear()
    await message.answer(f"✅ Уровень: {v}", reply_markup=a2_users_kb())

@dp.callback_query(F.data == "a2u_give_item")
async def a2u_give_item(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmGiveItem.uid)
    await callback.message.edit_text("🎒 ID юзера:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmGiveItem.uid))
async def a2u_gi_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return
    await state.update_data(uid=uid); await state.set_state(AdmGiveItem.iid)
    await message.answer("ID предмета:")

@dp.message(StateFilter(AdmGiveItem.iid))
async def a2u_gi_iid(message: Message, state: FSMContext):
    try:
        iid = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    con = db()
    con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)", (data["uid"], iid, now()))
    con.commit(); con.close()
    log_admin("give_item", data["uid"], str(iid))
    await state.clear()
    await message.answer("✅ Предмет выдан.", reply_markup=a2_users_kb())

@dp.callback_query(F.data == "a2u_take_item")
async def a2u_take_item(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmTakeItem.uid)
    await callback.message.edit_text("🗑 ID юзера:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmTakeItem.uid))
async def a2u_ti_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return
    await state.update_data(uid=uid); await state.set_state(AdmTakeItem.iid)
    await message.answer("ID предмета:")

@dp.message(StateFilter(AdmTakeItem.iid))
async def a2u_ti_iid(message: Message, state: FSMContext):
    try:
        iid = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    con = db()
    con.execute("DELETE FROM inventory WHERE user_id=? AND item_id=? LIMIT 1", (data["uid"], iid))
    con.commit(); con.close()
    log_admin("take_item", data["uid"], str(iid))
    await state.clear()
    await message.answer("✅ Удалено.", reply_markup=a2_users_kb())

@dp.callback_query(F.data == "a2u_block")
async def a2u_block(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(BlockUser.uid)
    await callback.message.edit_text("🚫 ID для блокировки:", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2u_unblock")
async def a2u_unblock(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(UnblockUser.uid)
    await callback.message.edit_text("🔓 ID для разблокировки:", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2u_reset")
async def a2u_reset(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmResetUser.uid)
    await callback.message.edit_text("🗑 ID для сброса:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmResetUser.uid))
async def a2u_reset_do(message: Message, state: FSMContext):
    if not a2_guard(message.from_user.id): return
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return
    con = db()
    con.execute("UPDATE users SET sd=0, xp=0, level=1 WHERE user_id=?", (uid,))
    con.execute("DELETE FROM inventory WHERE user_id=?", (uid,))
    con.commit(); con.close()
    log_admin("reset_user", uid)
    await state.clear()
    await message.answer(f"🗑 {uid} сброшен.", reply_markup=a2_users_kb())

@dp.callback_query(F.data == "a2u_msg")
async def a2u_msg(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmMsgUser.uid)
    await callback.message.edit_text("✉️ ID:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmMsgUser.uid))
async def a2u_msg_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
    except (ValueError, TypeError):
        return
    await state.update_data(uid=uid); await state.set_state(AdmMsgUser.text)
    await message.answer("Текст:")

@dp.callback_query(F.data == "a2u_alts")
async def a2u_alts(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("🕵️ Мультиакки ищутся по совпадению first_name+username префиксу. Тут — только ручная проверка через поиск.",
                                     reply_markup=a2_users_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2u_export")
async def a2u_export(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,sd,xp,level FROM users").fetchall()
    con.close()
    path = "export_users.csv"
    with open(path, "w", encoding="utf-8") as f:
        f.write("user_id,username,sd,xp,level\n")
        for r in rows:
            f.write(f"{r['user_id']},{r['username'] or ''},{r['sd']},{r['xp']},{r['level']}\n")
    await callback.message.answer_document(FSInputFile(path), caption="📄 Экспорт юзеров")
    await callback.answer()

@dp.callback_query(F.data == "a2u_purge_blocked")
async def a2u_purge_blocked(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("DELETE FROM users WHERE blocked=1").rowcount
    con.commit(); con.close()
    log_admin("purge_blocked", details=str(n))
    await callback.answer(f"🗑 Удалено: {n}", show_alert=True)

# ============================================================
# 📦 КЕЙСЫ (15 функций)
# ============================================================

def a2_cases_kb():
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📋 Список", "a2c_list"),
        ("🔄 Вкл/выкл", "a2c_toggle"),
        ("💰 Цена", "a2c_price"),
        ("✏️ Имя", "a2c_name"),
        ("📝 Описание", "a2c_desc"),
        ("➕ Добавить", "a2c_add"),
        ("🗑 Удалить", "a2c_del"),
        ("🎲 Дропы кейса", "a2c_drops"),
        ("📊 Статистика", "a2c_stats"),
        ("🧪 Тест-открытие", "a2c_test"),
        ("🎁 Топ кейс", "a2c_top"),
        ("❌ Закрыть", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2, 2, 2)
    return b.as_markup()

@dp.callback_query(F.data == "a2_cases")
async def a2_cases(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("📦 <b>КЕЙСЫ</b>", reply_markup=a2_cases_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2c_list")
async def a2c_list(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,code,name,price,enabled FROM cases ORDER BY id").fetchall()
    con.close()
    txt = "📋 <b>КЕЙСЫ</b>\n\n" + "\n".join(
        f"{'🟢' if r['enabled'] else '🔴'} <code>{r['id']}</code> {r['name']} · {r['price']} SD"
        for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_cases_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2c_toggle")
async def a2c_toggle(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name,enabled FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"{'🟢' if r['enabled'] else '🔴'} {r['name']}",
                                callback_data=f"a2c_t:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_cases")])
    await callback.message.edit_text("🔄 Кейс:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2c_t:"))
async def a2c_t(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    cid = int(callback.data.split(":")[1])
    con = db()
    r = con.execute("SELECT enabled FROM cases WHERE id=?", (cid,)).fetchone()
    nv = 0 if r["enabled"] else 1
    con.execute("UPDATE cases SET enabled=? WHERE id=?", (nv, cid))
    con.commit(); con.close()
    log_admin("toggle_case", details=f"{cid}:{nv}")
    await callback.answer("✅", show_alert=True)

@dp.callback_query(F.data == "a2c_price")
async def a2c_price(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name,price FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"{r['name']} · {r['price']}",
                                callback_data=f"a2c_p:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_cases")])
    await callback.message.edit_text("💰 Кейс:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2c_p:"))
async def a2c_p(callback: CallbackQuery, state: FSMContext):
    cid = int(callback.data.split(":")[1])
    await state.update_data(cid=cid); await state.set_state(CasePrice.price)
    await callback.message.edit_text("💰 Новая цена:", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2c_name")
async def a2c_name(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=r["name"], callback_data=f"a2c_n:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_cases")])
    await callback.message.edit_text("✏️ Кейс:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2c_n:"))
async def a2c_n(callback: CallbackQuery, state: FSMContext):
    cid = int(callback.data.split(":")[1])
    await state.update_data(cid=cid); await state.set_state(AdmChangeCaseName.val)
    await callback.message.edit_text("✏️ Новое имя:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmChangeCaseName.val))
async def a2c_n_do(message: Message, state: FSMContext):
    data = await state.get_data()
    con = db()
    con.execute("UPDATE cases SET name=? WHERE id=?", (message.text[:64], data["cid"]))
    con.commit(); con.close()
    await state.clear()
    await message.answer("✅ Изменено.", reply_markup=a2_cases_kb())

@dp.callback_query(F.data == "a2c_desc")
async def a2c_desc(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=r["name"], callback_data=f"a2c_d:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_cases")])
    await callback.message.edit_text("📝 Кейс:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2c_d:"))
async def a2c_d(callback: CallbackQuery, state: FSMContext):
    cid = int(callback.data.split(":")[1])
    await state.update_data(cid=cid); await state.set_state(AdmChangeCaseDesc.val)
    await callback.message.edit_text("📝 Новое описание:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmChangeCaseDesc.val))
async def a2c_d_do(message: Message, state: FSMContext):
    data = await state.get_data()
    con = db()
    con.execute("UPDATE cases SET description=? WHERE id=?", (message.text[:200], data["cid"]))
    con.commit(); con.close()
    await state.clear()
    await message.answer("✅ Изменено.", reply_markup=a2_cases_kb())

@dp.callback_query(F.data == "a2c_add")
async def a2c_add(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmAddCase.code)
    await callback.message.edit_text("➕ Код кейса (лат., без пробелов):", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmAddCase.code))
async def a2c_add_code(message: Message, state: FSMContext):
    code = (message.text or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{2,32}", code):
        return await message.answer("❌ Только a-z 0-9 _")
    con = db()
    if con.execute("SELECT 1 FROM cases WHERE code=?", (code,)).fetchone():
        con.close()
        return await message.answer("❌ Уже есть.")
    con.close()
    await state.update_data(code=code); await state.set_state(AdmAddCase.name)
    await message.answer("Название:")

@dp.message(StateFilter(AdmAddCase.name))
async def a2c_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text[:64]); await state.set_state(AdmAddCase.desc)
    await message.answer("Описание:")

@dp.message(StateFilter(AdmAddCase.desc))
async def a2c_add_desc(message: Message, state: FSMContext):
    await state.update_data(desc=message.text[:200]); await state.set_state(AdmAddCase.price)
    await message.answer("Цена (SD):")

@dp.message(StateFilter(AdmAddCase.price))
async def a2c_add_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    con = db()
    con.execute("INSERT INTO cases(code,name,description,price,enabled) VALUES(?,?,?,?,1)",
                (data["code"], data["name"], data["desc"], price))
    con.commit(); con.close()
    log_admin("add_case", details=data["code"])
    await state.clear()
    await message.answer("✅ Кейс создан.", reply_markup=a2_cases_kb())

@dp.callback_query(F.data == "a2c_del")
async def a2c_del(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"🗑 {r['name']}", callback_data=f"a2c_dl:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_cases")])
    await callback.message.edit_text("🗑 Какой удалить?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2c_dl:"))
async def a2c_dl(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    cid = int(callback.data.split(":")[1])
    con = db()
    con.execute("DELETE FROM case_items WHERE case_id=?", (cid,))
    con.execute("DELETE FROM cases WHERE id=?", (cid,))
    con.commit(); con.close()
    log_admin("delete_case", details=str(cid))
    await callback.answer("🗑 Удалён.", show_alert=True)

@dp.callback_query(F.data == "a2c_drops")
async def a2c_drops(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=r["name"], callback_data=f"a2c_dr:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_cases")])
    await callback.message.edit_text("🎲 Кейс:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2c_dr:"))
async def a2c_dr(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    cid = int(callback.data.split(":")[1])
    con = db()
    case = con.execute("SELECT name FROM cases WHERE id=?", (cid,)).fetchone()
    rows = con.execute("""SELECT i.name, i.rarity, ci.chance FROM case_items ci
                          JOIN items i ON i.id=ci.item_id WHERE ci.case_id=?
                          ORDER BY ci.chance DESC""", (cid,)).fetchall()
    con.close()
    txt = f"🎲 <b>{case['name'] if case else '?'}</b>\n\n"
    txt += "\n".join(f"{RARITY.get(r['rarity'])} {r['name']} — {r['chance']}%" for r in rows) or "Пусто."
    await callback.message.edit_text(txt, reply_markup=a2_cases_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2c_stats")
async def a2c_stats(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT c.name, COUNT(co.id) n FROM cases c
                          LEFT JOIN case_opens co ON co.case_id=c.id
                          GROUP BY c.id ORDER BY n DESC""").fetchall()
    con.close()
    txt = "📊 <b>СТАТ КЕЙСОВ</b>\n\n" + "\n".join(f"{r['name']} — {r['n']}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_cases_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2c_test")
async def a2c_test(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name FROM cases ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=r["name"], callback_data=f"a2c_tt:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_cases")])
    await callback.message.edit_text("🧪 Какой?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2c_tt:"))
async def a2c_tt(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    cid = int(callback.data.split(":")[1])
    con = db()
    items = con.execute("""SELECT i.name, i.rarity, ci.chance FROM case_items ci
                           JOIN items i ON i.id=ci.item_id WHERE ci.case_id=?""", (cid,)).fetchall()
    con.close()
    if not items:
        return await callback.answer("Пусто.", show_alert=True)
    pick = random.choices(items, weights=[float(x["chance"]) for x in items], k=1)[0]
    await callback.answer(f"🎁 {RARITY.get(pick['rarity'])} {pick['name']}", show_alert=True)

@dp.callback_query(F.data == "a2c_top")
async def a2c_top(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT c.name, SUM(c.price) revenue, COUNT(co.id) n
                          FROM cases c JOIN case_opens co ON co.case_id=c.id
                          GROUP BY c.id ORDER BY revenue DESC""").fetchall()
    con.close()
    txt = "🏆 <b>ТОП КЕЙСОВ</b>\n\n" + "\n".join(
        f"{r['name']} — {r['n']} открытий · {r['revenue']} SD" for r in rows) or "Пусто."
    await callback.message.edit_text(txt, reply_markup=a2_cases_kb())
    await callback.answer()

# ============================================================
# 💎 ПРЕДМЕТЫ (10 функций)
# ============================================================

def a2_items_kb():
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📋 Список", "a2i_list"),
        ("🔄 Вкл/выкл", "a2i_toggle"),
        ("💰 Цена", "a2i_price"),
        ("✏️ Имя", "a2i_name"),
        ("🎨 Редкость", "a2i_rar"),
        ("➕ Добавить", "a2i_add"),
        ("🗑 Удалить", "a2i_del"),
        ("👥 У кого есть", "a2i_owners"),
        ("🏆 Топ предмет", "a2i_top"),
        ("◀️ Назад", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2, 1, 1)
    return b.as_markup()

@dp.callback_query(F.data == "a2_items")
async def a2_items(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("💎 <b>ПРЕДМЕТЫ</b>", reply_markup=a2_items_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2i_list")
async def a2i_list(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,code,name,rarity,sell_price,enabled FROM items ORDER BY id").fetchall()
    con.close()
    txt = "📋 <b>ПРЕДМЕТЫ</b>\n\n" + "\n".join(
        f"{'🟢' if r['enabled'] else '🔴'} <code>{r['id']}</code> {RARITY.get(r['rarity'],'⚪')} {r['name']} · {r['sell_price']}"
        for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_items_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2i_toggle")
async def a2i_toggle(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name,enabled FROM items ORDER BY id").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"{'🟢' if r['enabled'] else '🔴'} {r['name']}",
                                callback_data=f"a2i_t:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_items")])
    await callback.message.edit_text("🔄 Предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2i_t:"))
async def a2i_t(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    iid = int(callback.data.split(":")[1])
    con = db()
    r = con.execute("SELECT enabled FROM items WHERE id=?", (iid,)).fetchone()
    nv = 0 if r["enabled"] else 1
    con.execute("UPDATE items SET enabled=? WHERE id=?", (nv, iid))
    con.commit(); con.close()
    log_admin("toggle_item", details=f"{iid}:{nv}")
    await callback.answer("✅", show_alert=True)

@dp.callback_query(F.data == "a2i_price")
async def a2i_price(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name,sell_price FROM items ORDER BY id LIMIT 40").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"{r['name']} · {r['sell_price']}",
                                callback_data=f"a2i_p:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_items")])
    await callback.message.edit_text("💰 Предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2i_p:"))
async def a2i_p(callback: CallbackQuery, state: FSMContext):
    iid = int(callback.data.split(":")[1])
    await state.update_data(iid=iid); await state.set_state(AdmChangeItemPrice.val)
    await callback.message.edit_text("💰 Новая цена:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmChangeItemPrice.val))
async def a2i_p_do(message: Message, state: FSMContext):
    try:
        v = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    con = db()
    con.execute("UPDATE items SET sell_price=? WHERE id=?", (v, data["iid"]))
    con.commit(); con.close()
    await state.clear()
    await message.answer("✅ Цена обновлена.", reply_markup=a2_items_kb())

@dp.callback_query(F.data == "a2i_name")
async def a2i_name(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name FROM items ORDER BY id LIMIT 40").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=r["name"], callback_data=f"a2i_n:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_items")])
    await callback.message.edit_text("✏️ Предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2i_n:"))
async def a2i_n(callback: CallbackQuery, state: FSMContext):
    iid = int(callback.data.split(":")[1])
    await state.update_data(iid=iid); await state.set_state(AdmChangeItemName.val)
    await callback.message.edit_text("✏️ Новое имя:", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmChangeItemName.val))
async def a2i_n_do(message: Message, state: FSMContext):
    data = await state.get_data()
    con = db()
    con.execute("UPDATE items SET name=? WHERE id=?", (message.text[:64], data["iid"]))
    con.commit(); con.close()
    await state.clear()
    await message.answer("✅", reply_markup=a2_items_kb())

@dp.callback_query(F.data == "a2i_rar")
async def a2i_rar(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name,rarity FROM items ORDER BY id LIMIT 40").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"{r['name']} · {r['rarity']}", callback_data=f"a2i_r:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_items")])
    await callback.message.edit_text("🎨 Предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2i_r:"))
async def a2i_r(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    iid = int(callback.data.split(":")[1])
    kb = [[InlineKeyboardButton(text=r, callback_data=f"a2i_rs:{iid}:{r}")] for r in RARITY_ORDER]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_items")])
    await callback.message.edit_text("🎨 Новая редкость:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2i_rs:"))
async def a2i_rs(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    _, iid_s, rar = callback.data.split(":")
    con = db()
    con.execute("UPDATE items SET rarity=? WHERE id=?", (rar, int(iid_s)))
    con.commit(); con.close()
    log_admin("change_item_rarity", details=f"{iid_s}:{rar}")
    await callback.answer("✅", show_alert=True)

@dp.callback_query(F.data == "a2i_add")
async def a2i_add(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmAddItem.code)
    await callback.message.edit_text("➕ Код предмета (a-z0-9_):", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmAddItem.code))
async def a2i_add_code(message: Message, state: FSMContext):
    code = (message.text or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{2,32}", code):
        return await message.answer("❌")
    await state.update_data(code=code); await state.set_state(AdmAddItem.name)
    await message.answer("Имя:")

@dp.message(StateFilter(AdmAddItem.name))
async def a2i_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text[:64]); await state.set_state(AdmAddItem.rarity)
    await message.answer(f"Редкость ({', '.join(RARITY_ORDER)}):")

@dp.message(StateFilter(AdmAddItem.rarity))
async def a2i_add_rar(message: Message, state: FSMContext):
    r = (message.text or "").strip().lower()
    if r not in RARITY_ORDER:
        return await message.answer(f"❌ Только: {', '.join(RARITY_ORDER)}")
    await state.update_data(rarity=r); await state.set_state(AdmAddItem.price)
    await message.answer("Цена продажи:")

@dp.message(StateFilter(AdmAddItem.price))
async def a2i_add_price(message: Message, state: FSMContext):
    try:
        p = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    con = db()
    con.execute("INSERT INTO items(code,name,rarity,sell_price,enabled) VALUES(?,?,?,?,1)",
                (data["code"], data["name"], data["rarity"], p))
    con.commit(); con.close()
    log_admin("add_item", details=data["code"])
    await state.clear()
    await message.answer("✅ Предмет создан.", reply_markup=a2_items_kb())

@dp.callback_query(F.data == "a2i_del")
async def a2i_del(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,name FROM items ORDER BY id LIMIT 40").fetchall()
    con.close()
    kb = [[InlineKeyboardButton(text=f"🗑 {r['name']}", callback_data=f"a2i_dl:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️", callback_data="a2_items")])
    await callback.message.edit_text("🗑 Какой удалить?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("a2i_dl:"))
async def a2i_dl(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    iid = int(callback.data.split(":")[1])
    con = db()
    con.execute("DELETE FROM case_items WHERE item_id=?", (iid,))
    con.execute("DELETE FROM inventory WHERE item_id=?", (iid,))
    con.execute("DELETE FROM items WHERE id=?", (iid,))
    con.commit(); con.close()
    log_admin("delete_item", details=str(iid))
    await callback.answer("🗑", show_alert=True)

@dp.callback_query(F.data == "a2i_owners")
async def a2i_owners(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT i.name, COUNT(inv.id) n FROM items i
                          LEFT JOIN inventory inv ON inv.item_id=i.id
                          GROUP BY i.id ORDER BY n DESC LIMIT 20""").fetchall()
    con.close()
    txt = "👥 <b>У КОГО ЕСТЬ</b>\n\n" + "\n".join(f"{r['name']} — {r['n']} шт." for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_items_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2i_top")
async def a2i_top(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT user_id, COUNT(*) n FROM inventory
                          GROUP BY user_id ORDER BY n DESC LIMIT 15""").fetchall()
    con.close()
    txt = "🏆 <b>ТОП КОЛЛЕКЦИОНЕРОВ</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> — {r['n']} предметов" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_items_kb())
    await callback.answer()

# ============================================================
# 🎟 ПРОМО (8 функций)
# ============================================================

def a2_promo_kb():
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📋 Список", "a2p_list"),
        ("➕ Создать", "a2p_add"),
        ("🗑 Удалить", "a2p_del"),
        ("🎁 Массово создать", "a2p_bulk"),
        ("📊 Топ промо", "a2p_top"),
        ("👥 Кто юзал", "a2p_uses"),
        ("🔄 Вкл/выкл", "a2p_toggle"),
        ("◀️ Назад", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2)
    return b.as_markup()

@dp.callback_query(F.data == "a2_promo")
async def a2_promo(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("🎟 <b>ПРОМОКОДЫ</b>", reply_markup=a2_promo_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2p_list")
async def a2p_list(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT code,reward,uses,max_uses,enabled FROM promo_codes ORDER BY id DESC LIMIT 30").fetchall()
    con.close()
    txt = "📋 <b>ПРОМО</b>\n\n" + "\n".join(
        f"{'🟢' if r['enabled'] else '🔴'} <code>{escape(r['code'])}</code> +{r['reward']} ({r['uses']}/{r['max_uses']})"
        for r in rows) or "Пусто."
    await callback.message.edit_text(txt, reply_markup=a2_promo_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2p_add")
async def a2p_add(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(PromoCreate.code)
    await callback.message.edit_text("➕ Код:", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2p_del")
async def a2p_del(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(PromoDelete.code)
    await callback.message.edit_text("🗑 Какой удалить?", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2p_bulk")
async def a2p_bulk(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmBulkPromo.count)
    await callback.message.edit_text("🎁 Сколько промокодов создать? (1-100)", reply_markup=a2_cancel())
    await callback.answer()

@dp.message(StateFilter(AdmBulkPromo.count))
async def a2p_bulk_count(message: Message, state: FSMContext):
    try:
        n = int(message.text)
    except (ValueError, TypeError):
        return
    if n < 1 or n > 100:
        return
    await state.update_data(count=n); await state.set_state(AdmBulkPromo.reward)
    await message.answer("💰 Сколько SD за каждый?")

@dp.message(StateFilter(AdmBulkPromo.reward))
async def a2p_bulk_reward(message: Message, state: FSMContext):
    try:
        reward = int(message.text)
    except (ValueError, TypeError):
        return
    data = await state.get_data()
    codes = []
    import string as _s
    con = db()
    for _ in range(data["count"]):
        code = "COS" + "".join(random.choices(_s.ascii_uppercase + _s.digits, k=8))
        try:
            con.execute("INSERT INTO promo_codes(code,reward,max_uses,uses,enabled) VALUES(?,?,1,0,1)",
                        (code, reward))
            codes.append(code)
        except Exception:
            pass
    con.commit(); con.close()
    log_admin("bulk_promo", details=f"{data['count']}x{reward}")
    await state.clear()
    txt = "🎁 <b>Создано:</b>\n\n" + "\n".join(codes)
    await message.answer(txt, reply_markup=a2_promo_kb())

@dp.callback_query(F.data == "a2p_top")
async def a2p_top(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT code, uses, reward FROM promo_codes ORDER BY uses DESC LIMIT 15").fetchall()
    con.close()
    txt = "📊 <b>ТОП ПРОМО</b>\n\n" + "\n".join(
        f"<code>{escape(r['code'])}</code> — {r['uses']} активаций · +{r['reward']}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_promo_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2p_uses")
async def a2p_uses(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT p.code, u.user_id, u.username, pu.used_at FROM promo_uses pu
                          JOIN promo_codes p ON p.id=pu.promo_id
                          JOIN users u ON u.user_id=pu.user_id
                          ORDER BY pu.id DESC LIMIT 30""").fetchall()
    con.close()
    txt = "👥 <b>ПОСЛЕДНИЕ АКТИВАЦИИ</b>\n\n" + "\n".join(
        f"<code>{escape(r['code'])}</code> → @{escape(r['username'] or r['user_id'])}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_promo_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2p_toggle")
async def a2p_toggle(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    con.execute("UPDATE promo_codes SET enabled = 1 - enabled")
    con.commit(); con.close()
    await callback.answer("✅ Переключено.", show_alert=True)

# ============================================================
# 💰 ЭКОНОМИКА (8 функций)
# ============================================================

@dp.callback_query(F.data == "a2_econ")
async def a2_econ(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for t, d in [
        ("💰 Общая сумма", "a2e_total"),
        ("📊 Средняя", "a2e_avg"),
        ("🐋 Богачи", "a2e_rich"),
        ("🥚 Бедные", "a2e_poor"),
        ("🎁 Оборот кейсов", "a2e_cases"),
        ("🎰 Оборот казино", "a2e_casino"),
        ("💸 Донат-стат", "a2e_donate"),
        ("🔧 Пересчитать", "a2e_recalc"),
        ("◀️ Назад", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2, 1)
    await callback.message.edit_text("💰 <b>ЭКОНОМИКА</b>", reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2e_total")
async def a2e_total(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    con.close()
    await callback.answer(f"💰 Всего: {n} SD", show_alert=True)

@dp.callback_query(F.data == "a2e_avg")
async def a2e_avg(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COALESCE(AVG(sd),0) n FROM users").fetchone()["n"]
    con.close()
    await callback.answer(f"📊 Средняя: {int(n)} SD", show_alert=True)

@dp.callback_query(F.data == "a2e_rich")
async def a2e_rich(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,sd FROM users WHERE sd>=10000 ORDER BY sd DESC LIMIT 20").fetchall()
    con.close()
    txt = "🐋 <b>БОГАЧИ (10k+)</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> @{escape(r['username'] or '-')} — {r['sd']}" for r in rows) or "Пусто."
    await callback.message.edit_text(txt, reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2e_poor")
async def a2e_poor(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM users WHERE sd<100").fetchone()["n"]
    con.close()
    await callback.answer(f"🥚 Бедных: {n}", show_alert=True)

@dp.callback_query(F.data == "a2e_cases")
async def a2e_cases(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("""SELECT COALESCE(SUM(c.price),0) n FROM case_opens co
                       JOIN cases c ON c.id=co.case_id""").fetchone()["n"]
    con.close()
    await callback.answer(f"🎁 Оборот: {n} SD", show_alert=True)

@dp.callback_query(F.data == "a2e_casino")
async def a2e_casino(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COALESCE(SUM(bet),0) n FROM casino_bets").fetchone()["n"]
    p = con.execute("SELECT COALESCE(SUM(profit),0) n FROM casino_bets").fetchone()["n"]
    con.close()
    await callback.answer(f"🎰 Оборот: {n} SD\n💵 Профит: {-p:+d} SD", show_alert=True)

@dp.callback_query(F.data == "a2e_donate")
async def a2e_donate(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COALESCE(SUM(donated),0) n FROM users").fetchone()["n"]
    c = con.execute("SELECT COUNT(*) n FROM users WHERE donated>0").fetchone()["n"]
    con.close()
    await callback.answer(f"💎 Донатов: {n}\n👥 Донатеров: {c}", show_alert=True)

@dp.callback_query(F.data == "a2e_recalc")
async def a2e_recalc(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    con.execute("UPDATE users SET level = MAX(1, xp/100 + 1)")
    con.commit(); con.close()
    await callback.answer("✅ Уровни пересчитаны.", show_alert=True)

def a2_root_kb():
    return adm_root_kb()

# ============================================================
# 🎰 КАЗИНО АДМИН (8 функций)
# ============================================================

@dp.callback_query(F.data == "a2_casino")
async def a2_casino(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📊 Общая стата", "a2g_stat"),
        ("🏆 Топ выигрыш", "a2g_wins"),
        ("💀 Топ проигрыш", "a2g_loss"),
        ("💰 Профит казино", "a2g_profit"),
        ("🎰 Стата по играм", "a2g_games"),
        ("🔧 Сброс юзеру", "a2g_reset"),
        ("💵 Лимиты", "a2g_limits"),
        ("◀️ Назад", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 1)
    await callback.message.edit_text("🎰 <b>КАЗИНО</b>", reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2g_stat")
async def a2g_stat(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM casino_bets").fetchone()["n"]
    b = con.execute("SELECT COALESCE(SUM(bet),0) n FROM casino_bets").fetchone()["n"]
    w = con.execute("SELECT COALESCE(SUM(win),0) n FROM casino_bets").fetchone()["n"]
    con.close()
    await callback.message.edit_text(
        f"📊 <b>СТАТИСТИКА КАЗИНО</b>\n\n"
        f"🎲 Ставок: <b>{n}</b>\n💰 Оборот: <b>{b} SD</b>\n"
        f"🏆 Выплачено: <b>{w} SD</b>\n📈 Профит казино: <b>{b - w} SD</b>",
        reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2g_wins")
async def a2g_wins(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,game,win FROM casino_bets WHERE win>0 ORDER BY win DESC LIMIT 20").fetchall()
    con.close()
    txt = "🏆 <b>ТОП ВЫИГРЫШЕЙ</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> {r['game']} +{r['win']}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2g_loss")
async def a2g_loss(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,game,bet FROM casino_bets WHERE win=0 ORDER BY bet DESC LIMIT 20").fetchall()
    con.close()
    txt = "💀 <b>ТОП ПРОИГРЫШЕЙ</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> {r['game']} -{r['bet']}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2g_profit")
async def a2g_profit(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    b = con.execute("SELECT COALESCE(SUM(bet),0) n FROM casino_bets").fetchone()["n"]
    w = con.execute("SELECT COALESCE(SUM(win),0) n FROM casino_bets").fetchone()["n"]
    con.close()
    await callback.answer(f"💵 Профит казино: {b - w} SD", show_alert=True)

@dp.callback_query(F.data == "a2g_games")
async def a2g_games(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT game, COUNT(*) n, SUM(bet) ob, SUM(win) w
                          FROM casino_bets GROUP BY game""").fetchall()
    con.close()
    txt = "🎰 <b>ПО ИГРАМ</b>\n\n" + "\n".join(
        f"{r['game']}: {r['n']} ставок · оборот {r['ob']} · выигр {r['w'] or 0}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2g_reset")
async def a2g_reset(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmResetUser.uid)
    await callback.message.edit_text("🔧 ID юзера, чью казино-стату сбросить:", reply_markup=a2_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a2g_limits")
async def a2g_limits(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for key, name in [
        ("casino_min","Мин ставка"),
        ("casino_max","Макс ставка"),
        ("casino_max_win","Макс выигрыш"),
        ("casino_loss_limit","Лимит проигрыша"),
        ("duel_min","Мин дуэли"),
        ("duel_commission","Комиссия дуэли"),
    ]:
        b.button(text=f"{name}: {get_limit(key)}", callback_data=f"a3le:{key}")
    b.button(text="◀️ Назад", callback_data="a2_casino")
    b.adjust(1)
    await callback.message.edit_text("💵 <b>ЛИМИТЫ КАЗИНО</b>\n\nНажми на любой, чтобы изменить:",
                                     reply_markup=b.as_markup())
    await callback.answer()

# ============================================================
# 💎 ПОДПИСКИ (5 функций)
# ============================================================

@dp.callback_query(F.data == "a2_subs")
async def a2_subs(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM users WHERE sub_until IS NOT NULL").fetchone()["n"]
    rows = con.execute("SELECT user_id,username,sub_until FROM users WHERE sub_until IS NOT NULL ORDER BY sub_until DESC LIMIT 20").fetchall()
    con.close()
    txt = f"💎 <b>ПОДПИСКИ</b>\n\nВсего: <b>{n}</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> @{escape(r['username'] or '-')} до {r['sub_until'][:10]}" for r in rows)
    b = InlineKeyboardBuilder()
    b.button(text="➕ Выдать", callback_data="a2s_add")
    b.button(text="➖ Забрать", callback_data="a2s_del")
    b.button(text="◀️ Назад", callback_data="a2_root")
    b.adjust(1)
    await callback.message.edit_text(txt, reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2s_add")
async def a2s_add(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("Юзай /admin2 → 👥 Юзеры → 💎 Выдать подписку",
                                     reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2s_del")
async def a2s_del(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("Юзай /admin2 → 👥 Юзеры → 💎 Подписка → ❌ Убрать",
                                     reply_markup=a2_root_kb())
    await callback.answer()

# ============================================================
# 📋 ЗАДАНИЯ (4 функции)
# ============================================================

@dp.callback_query(F.data == "a2_tasks")
async def a2_tasks(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,code,name,goal,reward FROM tasks ORDER BY id").fetchall()
    con.close()
    txt = "📋 <b>ЗАДАНИЯ</b>\n\n" + "\n".join(
        f"<code>{r['id']}</code> {r['name']} · цель {r['goal']} · +{r['reward']}" for r in rows)
    b = InlineKeyboardBuilder()
    b.button(text="💰 Изменить награду", callback_data="a2t_reward")
    b.button(text="📊 Статистика", callback_data="a2t_stats")
    b.button(text="🔄 Обновить", callback_data="a2_tasks")
    b.button(text="◀️ Назад", callback_data="a2_root")
    b.adjust(1)
    await callback.message.edit_text(txt, reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2t_reward")
async def a2t_reward(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("Изменение награды в разработке. Скажи, если срочно — добавлю.",
                                     reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2t_stats")
async def a2t_stats(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    t = today()
    con = db()
    rows = con.execute("""SELECT t.name, COUNT(ut.id) n FROM tasks t
                          LEFT JOIN user_tasks ut ON ut.task_id=t.id AND ut.date=? AND ut.done=1
                          GROUP BY t.id""", (t,)).fetchall()
    con.close()
    txt = "📊 <b>СТАТ ЗАДАНИЙ (сегодня)</b>\n\n" + "\n".join(
        f"{r['name']} — {r['n']} выполнено" for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_root_kb())
    await callback.answer()

# ============================================================
# 🏅 ДОСТИЖЕНИЯ (3 функции)
# ============================================================

@dp.callback_query(F.data == "a2_ach")
async def a2_ach(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT code,name,reward FROM achievements ORDER BY id").fetchall()
    con.close()
    txt = "🏅 <b>ДОСТИЖЕНИЯ</b>\n\n" + "\n".join(
        f"<code>{escape(r['code'])}</code> {r['name']} +{r['reward']}" for r in rows)
    b = InlineKeyboardBuilder()
    b.button(text="🎁 Выдать вручную", callback_data="a2a_grant")
    b.button(text="◀️ Назад", callback_data="a2_root")
    b.adjust(1)
    await callback.message.edit_text(txt, reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2a_grant")
async def a2a_grant(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.message.edit_text("Выдача вручную — в разработке.", reply_markup=a2_root_kb())
    await callback.answer()

# ============================================================
# 💸 ВЫВОДЫ (3 функции)
# ============================================================

@dp.callback_query(F.data == "a2_withdraws")
async def a2_withdraws(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT id,user_id,amount,status,created_at FROM withdraws ORDER BY id DESC LIMIT 30").fetchall()
    con.close()
    if not rows:
        return await callback.message.edit_text("💸 Заявок нет.", reply_markup=a2_root_kb())
    txt = "💸 <b>ЗАЯВКИ НА ВЫВОД</b>\n\n" + "\n".join(
        f"#{r['id']} · <code>{r['user_id']}</code> · {r['amount']} SD · {r['status']}" for r in rows)
    await callback.message.edit_text(txt, reply_markup=a2_root_kb())
    await callback.answer()

# ============================================================
# 📝 ЗАЯВКИ (3 функции)
# ============================================================

@dp.callback_query(F.data == "a2_apps")
async def a2_apps(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT id,user_id,name,status FROM applications
                          ORDER BY id DESC LIMIT 30""").fetchall()
    con.close()
    txt = "📝 <b>ЗАЯВКИ</b>\n\n" + "\n".join(
        f"#{r['id']} {r['user_id']} {escape(r['name'] or '-')} · {r['status']}" for r in rows) or "Пусто."
    b = InlineKeyboardBuilder()
    b.button(text="🧹 Очистить обработанные", callback_data="a2app_clear")
    b.button(text="◀️ Назад", callback_data="a2_root")
    b.adjust(1)
    await callback.message.edit_text(txt, reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2app_clear")
async def a2app_clear(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("DELETE FROM applications WHERE status != 'pending'").rowcount
    con.commit(); con.close()
    await callback.answer(f"🧹 Удалено: {n}", show_alert=True)

# ============================================================
# 📜 ЛОГИ (6 функций)
# ============================================================

@dp.callback_query(F.data == "a2_logs")
async def a2_logs(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for t, d in [
        ("👑 Админ-логи", "a2l_admin"),
        ("🎰 Казино", "a2l_casino"),
        ("🎁 Кейсы", "a2l_cases"),
        ("💸 Выводы", "a2l_withdraws"),
        ("🧹 Очистить", "a2l_clear"),
        ("◀️ Назад", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2)
    await callback.message.edit_text("📜 <b>ЛОГИ</b>", reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2l_admin")
async def a2l_admin(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT created_at,action,target_user_id,details FROM admin_logs ORDER BY id DESC LIMIT 30").fetchall()
    con.close()
    txt = "👑 <b>АДМИН-ЛОГИ</b>\n\n" + "\n".join(
        f"{r['created_at'][:19]} {r['action']} → {r['target_user_id'] or '-'} {r['details'] or ''}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2l_casino")
async def a2l_casino(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT user_id,game,bet,win,created_at FROM casino_bets
                          ORDER BY id DESC LIMIT 30""").fetchall()
    con.close()
    txt = "🎰 <b>ЛОГ КАЗИНО</b>\n\n" + "\n".join(
        f"{r['created_at'][:19]} <code>{r['user_id']}</code> {r['game']} bet {r['bet']} win {r['win']}"
        for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2l_cases")
async def a2l_cases(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT user_id,case_id,item_id,created_at FROM case_opens
                          ORDER BY id DESC LIMIT 30""").fetchall()
    con.close()
    txt = "🎁 <b>ЛОГ КЕЙСОВ</b>\n\n" + "\n".join(
        f"{r['created_at'][:19]} <code>{r['user_id']}</code> case:{r['case_id']} item:{r['item_id']}"
        for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2l_withdraws")
async def a2l_withdraws(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("""SELECT id,user_id,amount,status,created_at,decided_at FROM withdraws
                          ORDER BY id DESC LIMIT 30""").fetchall()
    con.close()
    txt = "💸 <b>ЛОГ ВЫВОДОВ</b>\n\n" + "\n".join(
        f"#{r['id']} <code>{r['user_id']}</code> {r['amount']} {r['status']}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.", reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2l_clear")
async def a2l_clear(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    n = con.execute("DELETE FROM admin_logs").rowcount
    con.commit(); con.close()
    await callback.answer(f"🧹 Удалено: {n}", show_alert=True)

# ============================================================
# 🛡 АДМИНЫ (4 функции)
# ============================================================

@dp.callback_query(F.data == "a2_admins")
async def a2_admins(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,role,created_at FROM admins ORDER BY user_id").fetchall()
    con.close()
    txt = "🛡 <b>АДМИНЫ</b>\n\n" + "\n".join(
        f"<code>{r['user_id']}</code> {r['role']}" for r in rows)
    await callback.message.edit_text(txt + f"\n\nГлавный: <code>{ADMIN_ID}</code>",
                                     reply_markup=a2_root_kb())
    await callback.answer()

# ============================================================
# 🛠 ОБСЛУЖИВАНИЕ (8 функций)
# ============================================================

@dp.callback_query(F.data == "a2_maint")
async def a2_maint(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for t, d in [
        ("💾 Бэкап БД", "a2m_backup"),
        ("📄 Экспорт юзеров CSV", "a2m_csv"),
        ("🧹 Очистить кеш", "a2m_cache"),
        ("🔄 Пересчитать уровни", "a2m_levels"),
        ("🕐 Пинг бота", "a2m_ping"),
        ("📊 Кол-во записей", "a2m_count"),
        ("🚨 Обнулить SD-кэш", "a2m_sdclean"),
        ("◀️ Назад", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2, 2, 2, 2)
    await callback.message.edit_text("🛠 <b>ОБСЛУЖИВАНИЕ</b>", reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2m_backup")
async def a2m_backup(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BACKUP_DIR, f"cosdrop_{ts}.sqlite3")
        src = sqlite3.connect(DB_FILE)
        dst = sqlite3.connect(path)
        with dst:
            src.backup(dst)
        dst.close(); src.close()
        await callback.message.answer_document(FSInputFile(path), caption="💾 Бэкап")
        await callback.answer("Готово.")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@dp.callback_query(F.data == "a2m_csv")
async def a2m_csv(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,sd,xp,level,blocked FROM users").fetchall()
    con.close()
    path = "export_all.csv"
    with open(path, "w", encoding="utf-8") as f:
        f.write("user_id,username,sd,xp,level,blocked\n")
        for r in rows:
            f.write(f"{r['user_id']},{r['username'] or ''},{r['sd']},{r['xp']},{r['level']},{r['blocked']}\n")
    await callback.message.answer_document(FSInputFile(path), caption="📄 CSV")
    await callback.answer()

@dp.callback_query(F.data == "a2m_cache")
async def a2m_cache(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    try:
        import gc; gc.collect()
        await callback.answer("🧹 Очищено.")
    except Exception:
        await callback.answer("✅")

@dp.callback_query(F.data == "a2m_levels")
async def a2m_levels(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    con.execute("UPDATE users SET level = MAX(1, xp/100 + 1)")
    con.commit(); con.close()
    await callback.answer("✅ Пересчитано.", show_alert=True)

@dp.callback_query(F.data == "a2m_ping")
async def a2m_ping(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    t = datetime.now(timezone.utc).isoformat()
    await callback.answer(f"🕐 {t[11:19]}", show_alert=True)

@dp.callback_query(F.data == "a2m_count")
async def a2m_count(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    counts = {t: con.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
              for t in ["users","cases","items","inventory","case_opens","admin_logs","casino_bets","duels","withdraws"]}
    con.close()
    txt = "📊 <b>ЗАПИСЕЙ В БД</b>\n\n" + "\n".join(f"{k}: {v}" for k, v in counts.items())
    await callback.message.edit_text(txt, reply_markup=a2_root_kb())
    await callback.answer()

@dp.callback_query(F.data == "a2m_sdclean")
async def a2m_sdclean(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    con = db()
    con.execute("UPDATE users SET daily_loss=0, daily_loss_date=NULL")
    con.commit(); con.close()
    await callback.answer("✅ Казино-лимиты обнулены.", show_alert=True)

# ============================================================
# 📢 РАССЫЛКА МЕНЮ
# ============================================================

@dp.callback_query(F.data == "a2_broadcast_menu")
async def a2_broadcast_menu(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for t, d in [
        ("📢 Всем", "a2b_all"),
        ("🟢 Активным (7д)", "a2b_active"),
        ("💎 Донатерам", "a2b_donors"),
        ("🐋 Богатым (10k+)", "a2b_rich"),
        ("😴 Спящим", "a2b_sleep"),
        ("◀️ Назад", "a2_root"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(1)
    await callback.message.edit_text("📢 <b>РАССЫЛКА</b>", reply_markup=b.as_markup())
    await callback.answer()

async def _a2_send_broadcast(message: Message, query: str, name: str):
    con = db()
    users = con.execute(query).fetchall()
    con.close()
    s, f = 0, 0
    for r in users:
        try:
            await bot.send_message(r["user_id"], message)
            s += 1
        except Exception:
            f += 1
        await asyncio.sleep(0.05)
    log_admin("broadcast_v2", details=f"{name} s={s} f={f}")
    return s, f

@dp.callback_query(F.data.startswith("a2b_"))
async def a2b_go(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    target = callback.data[4:]
    await state.update_data(b_target=target)
    await state.set_state(Broadcast.text)
    await callback.message.edit_text(f"📢 Введи текст рассылки ({target}):", reply_markup=a2_cancel())
    await callback.answer()

# ============================================================
# 🔎 БЫСТРЫЙ ПОИСК
# ============================================================

@dp.callback_query(F.data == "a2_find")
async def a2_find(callback: CallbackQuery, state: FSMContext):
    if not a2_guard(callback.from_user.id): return
    await state.set_state(AdmSearch.q)
    await callback.message.edit_text("🔎 ID или @username:", reply_markup=a2_cancel())
    await callback.answer()

# ============================================================
# ОБРАБОТКА ВВОДА АДМИН-ПОИСКА (общая)
# ============================================================

# (уже реализовано в a2u_search_do; следим чтобы не конфликтовало)

# ============================================================
# ХЕНДЛЕРЫ НЕКОТОРЫХ ПОВТОРЯЮЩИХСЯ КНОПОК
# ============================================================

@dp.callback_query(F.data.startswith("a2s_"))
async def a2s_unknown(callback: CallbackQuery):
    if not a2_guard(callback.from_user.id): return
    await callback.answer()


# ============================================================
# FALLBACK
# ============================================================

@dp.message(StateFilter(None))
async def fallback(message: Message):
    txt = message.text or ""
    if txt.startswith("/admin3"):
        return await a2_open(message)
    if txt.startswith("/admin2"):
        return await a2_open(message)
    if txt.startswith("/admin"):
        return await admin_cmd(message)
    user = ensure(message.from_user)
    if user["blocked"]:
        return await message.answer("🚫 Заблокирован.")
    await message.answer("Используй /start.")




# ============================================================
# MAIN
# ============================================================
# ============================================================
# ADMIN v3 — ЛИМИТЫ + ФУНКЦИИ
# ============================================================

class A3Limit(StatesGroup):
    key = State()
class A3Mass(StatesGroup):
    mode = State(); amount = State()

def a3_kb():
    b = InlineKeyboardBuilder()
    for t,d in [
        ("⚙️ Лимиты игровые","a3lg:game"),
        ("🎰 Лимиты казино","a3lg:casino"),
        ("💰 Лимиты деньги","a3lg:money"),
        ("⭐ Лимиты пакеты","a3lg:packs"),
        ("🔀 Вкл/выкл","a3lg:toggles"),
        ("📋 Показать все","a3l_showall"),
        ("🔄 Сбросить всё","a3l_resetall"),
        ("💰 Масса SD","a3_econ"),
        ("🎯 Массовые","a3_mass"),
        ("📁 Экспорт","a3_export"),
        ("🛠 Диагностика","a3_diag"),
        ("❌ Закрыть","a3_close"),
    ]:
        b.button(text=t, callback_data=d)
    b.adjust(2,2,2,2,2,1,1)
    return b.as_markup()

def a3_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="a3_root")]])

LIMIT_GROUPS = {
    "game": [("starter_sd","Стартовый SD"),("daily_base","Daily"),
             ("daily_streak_7","Стрик 7д"),("daily_streak_30","Стрик 30д"),
             ("case_cooldown","Кулдаун кейсов"),("sell_commission","Комиссия продажи"),
             ("upgrade_chance","Шанс апгрейда")],
    "casino": [("casino_min","Мин ставка"),("casino_max","Макс ставка"),
               ("casino_max_win","Макс выигрыш"),("casino_loss_limit","Лимит проигрыша"),
               ("duel_min","Мин дуэли"),("duel_commission","Комиссия дуэли")],
    "money": [("min_withdraw","Мин вывод"),("max_withdraw","Макс вывод"),
              ("ref_invite","Бонус за реф"),("ref_donate","Бонус за донат")],
    "packs": [("pack_100","Пакет 100"),("pack_400","Пакет 400"),
              ("pack_1000","Пакет 1000"),("pack_1500","Пакет 1500")],
    "toggles": [("registration_open","Регистрация"),("referral_enabled","Рефералы"),
                ("casino_enabled","Казино"),("withdraw_enabled","Выводы"),
                ("maintenance_mode","Обслуживание")],
}

@dp.message(Command("admin3"))
async def a3_open(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 <b>ADMIN v3</b>", reply_markup=a3_kb())

@dp.callback_query(F.data == "a3_root")
async def a3_root(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text("👑 <b>ADMIN v3</b>", reply_markup=a3_kb())
    await callback.answer()

@dp.callback_query(F.data == "a3_close")
async def a3_close(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    try: await callback.message.delete()
    except Exception: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("a3lg:"))
async def a3_lg(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    grp = callback.data.split(":")[1]
    b = InlineKeyboardBuilder()
    for key, name in LIMIT_GROUPS.get(grp, []):
        b.button(text=f"{name}: {get_limit(key)}", callback_data=f"a3le:{key}")
    b.button(text="◀️ Назад", callback_data="a3_root")
    b.adjust(1)
    await callback.message.edit_text("⚙️ Выбери лимит:", reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("a3le:"))
async def a3_le(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    key = callback.data.split(":")[1]
    await state.update_data(limit_key=key); await state.set_state(A3Limit.key)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сброс к дефолту", callback_data=f"a3ld:{key}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="a2_root")]])
    await callback.message.edit_text(
        f"⚙️ <b>{key}</b>\n\nТекущее: <b>{get_limit(key)}</b>\n"
        f"Дефолт: <b>{LIMIT_DEFAULTS.get(key)}</b>\n\n"
        f"Отправь новое число или /a3d:",
        reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("a3ld:"))
async def a3_ld(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    key = callback.data.split(":")[1]
    con = db(); con.execute("DELETE FROM settings WHERE key=?",(f"lim_{key}",)); con.commit(); con.close()
    await callback.answer(f"✅ {key} → {LIMIT_DEFAULTS.get(key)}", show_alert=True)
@dp.message(StateFilter(A3Limit.key))
async def a3_le_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    key = data.get("limit_key")
    txt = (message.text or "").strip()
    if txt == "/a3d":
        con = db()
        con.execute("DELETE FROM settings WHERE key=?", (f"lim_{key}",))
        con.commit(); con.close()
        await state.clear()
        return await message.answer(f"✅ {key} → default", reply_markup=a3_kb())
    default = LIMIT_DEFAULTS.get(key)
    try:
        if isinstance(default, float): val = float(txt.replace(",", "."))
        elif isinstance(default, int): val = int(txt)
        else: val = txt
    except Exception:
        return await message.answer("❌ Неверный формат.")
    set_limit(key, val)
    log_admin("set_limit", details=f"{key}={val}")
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 К лимитам казино", callback_data="a2g_limits")],
        [InlineKeyboardButton(text="⚙️ Все лимиты", callback_data="a3_root")],
        [InlineKeyboardButton(text="👑 В админку", callback_data="a2_root")]])
    await message.answer(f"✅ {key} = <b>{val}</b>", reply_markup=kb)
@dp.callback_query(F.data == "a3l_showall")
async def a3_showall(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    txt = "📋 <b>ВСЕ ЛИМИТЫ</b>\n\n"
    for grp, items in LIMIT_GROUPS.items():
        txt += f"<b>{grp}</b>\n"
        for k, n in items:
            v = get_limit(k); d = LIMIT_DEFAULTS.get(k)
            mark = "🟢" if v == d else "🟡"
            txt += f"{mark} {n}: <b>{v}</b>\n"
        txt += "\n"
    await callback.message.edit_text(txt, reply_markup=a3_kb())
    await callback.answer()

@dp.callback_query(F.data == "a3l_resetall")
async def a3_resetall(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    n = con.execute("DELETE FROM settings WHERE key LIKE 'lim_%'").rowcount
    con.commit(); con.close()
    log_admin("reset_all_limits", details=str(n))
    await callback.answer(f"✅ Сброшено {n} лимитов.", show_alert=True)

@dp.callback_query(F.data == "a3_econ")
async def a3_econ(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    mass = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    rich = con.execute("SELECT COUNT(*) n FROM users WHERE sd>=10000").fetchone()["n"]
    poor = con.execute("SELECT COUNT(*) n FROM users WHERE sd<100").fetchone()["n"]
    con.close()
    b = InlineKeyboardBuilder()
    b.button(text="💣 Обнулить SD всем", callback_data="a3e_wipe")
    b.button(text="🎁 Начислить всем", callback_data="a3e_add")
    b.button(text="➖ Списать у всех", callback_data="a3e_take")
    b.button(text="◀️ Назад", callback_data="a3_root")
    b.adjust(1)
    await callback.message.edit_text(
        f"💰 <b>ЭКОНОМИКА</b>\n\nМасса SD: <b>{mass}</b>\n"
        f"🐋 Богачей: {rich}\n🥚 Бедных: {poor}",
        reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a3e_wipe")
async def a3e_wipe(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА", callback_data="a3e_wipe_ok")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="a3_root")]])
    await callback.message.edit_text("⚠️ Обнулить SD у всех?", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "a3e_wipe_ok")
async def a3e_wipe_ok(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    con.execute("UPDATE users SET sd=0")
    con.commit(); con.close()
    log_admin("wipe_all_sd")
    await callback.answer("✅ Обнулено.", show_alert=True)

@dp.callback_query(F.data == "a3e_add")
async def a3e_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(mode="add"); await state.set_state(A3Mass.amount)
    await callback.message.edit_text("🎁 Сколько начислить всем?", reply_markup=a3_cancel())
    await callback.answer()

@dp.callback_query(F.data == "a3e_take")
async def a3e_take(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(mode="take"); await state.set_state(A3Mass.amount)
    await callback.message.edit_text("➖ Сколько списать у всех?", reply_markup=a3_cancel())
    await callback.answer()

@dp.message(StateFilter(A3Mass.amount))
async def a3_mass_sd(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: amount = int(message.text)
    except Exception: return await message.answer("❌")
    data = await state.get_data(); mode = data.get("mode")
    con = db()
    if mode == "take":
        con.execute("UPDATE users SET sd=MAX(0, sd-?)", (amount,))
    else:
        con.execute("UPDATE users SET sd=sd+?", (amount,))
    con.commit(); con.close()
    log_admin(f"mass_{mode}_sd", details=str(amount))
    await state.clear()
    await message.answer(f"✅ {mode} {amount} всем.", reply_markup=a3_kb())

@dp.callback_query(F.data == "a3_mass")
async def a3_mass(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    b.button(text="💎 Подписка всем донатерам", callback_data="a3m_sub")
    b.button(text="🎁 Предмет всем активным", callback_data="a3m_item")
    b.button(text="◀️ Назад", callback_data="a3_root")
    b.adjust(1)
    await callback.message.edit_text("🎯 <b>МАССОВЫЕ</b>", reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a3m_sub")
async def a3m_sub(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    con = db()
    n = con.execute("UPDATE users SET sub_until=? WHERE donated>0", (until,)).rowcount
    con.commit(); con.close()
    log_admin("mass_sub", details=str(n))
    await callback.answer(f"✅ {n} юзеров получили подписку.", show_alert=True)

@dp.callback_query(F.data == "a3m_item")
async def a3m_item(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    con = db()
    item = con.execute("SELECT id FROM items WHERE enabled=1 ORDER BY RANDOM() LIMIT 1").fetchone()
    if not item: con.close(); return await callback.answer("Нет предметов.", show_alert=True)
    users = con.execute("SELECT user_id FROM users WHERE last_activity >= ? AND blocked=0",
                        (week_ago,)).fetchall()
    for u in users:
        con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)",
                    (u["user_id"], item["id"], now()))
    con.commit(); con.close()
    log_admin("mass_item", details=f"item={item['id']} n={len(users)}")
    await callback.answer(f"✅ {len(users)} юзеров получили предмет.", show_alert=True)

@dp.callback_query(F.data == "a3_export")
async def a3_export(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    rows = con.execute("SELECT user_id,username,sd,xp,level,blocked FROM users").fetchall()
    con.close()
    path = "export_v3.csv"
    with open(path, "w", encoding="utf-8") as f:
        f.write("user_id,username,sd,xp,level,blocked\n")
        for r in rows:
            f.write(f"{r['user_id']},{r['username'] or ''},{r['sd']},{r['xp']},{r['level']},{r['blocked']}\n")
    await callback.message.answer_document(FSInputFile(path), caption="📄 Экспорт")
    await callback.answer()

@dp.callback_query(F.data == "a3_diag")
async def a3_diag(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    tables = ["users","cases","items","inventory","case_opens","admin_logs",
              "casino_bets","duels","withdraws","promo_codes","settings"]
    txt = "🛠 <b>ДИАГНОСТИКА</b>\n\n"
    for t in tables:
        try:
            n = con.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
            txt += f"{t}: {n}\n"
        except Exception as e:
            txt += f"❌ {t}: {e}\n"
    con.close()
    txt += f"\nDB: <code>{DB_FILE}</code>"
    await callback.message.edit_text(txt, reply_markup=a3_kb())
    await callback.answer()


async def main():
    init_db()
    logging.info("COS-DROP started | DB=%s", DB_FILE)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
