import asyncio
import logging
import os
import random
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = "8835340993:AAFZE730NKzcObK3GzGwfVbPPuXTdu-NM0g"
ADMIN_ID = 8146320391

DB_FILE = os.getenv("DB_FILE", "cosdrop.sqlite3")
IMAGE_FILE = "imagemain.png"

BACKUP_DIR = "/data/backups" if os.path.isdir("/data") else "backups"

if not BOT_TOKEN or BOT_TOKEN == "PASTE_NEW_BOT_TOKEN_HERE":
    raise RuntimeError("Вставь новый токен бота в BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

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
    ("basic_star", "⭐ Star", "common"),
    ("basic_blue", "🔷 Blue Crystal", "rare"),
    ("basic_purple", "🟣 Purple Crystal", "epic"),

    ("school_pen", "🖊️ Золотая ручка", "rare"),
    ("backpack", "🎒 Космо-рюкзак", "epic"),
    ("school_cup", "🏆 Кубок класса", "legendary"),

    ("meme_skull", "💀 Skull", "common"),
    ("meme_sigma", "🗿 Sigma", "rare"),
    ("meme_fire", "🔥 Fire", "epic"),

    ("rare_diamond", "💎 Diamond", "rare"),
    ("rare_crown", "👑 Silver Crown", "epic"),
    ("rare_gold", "✨ Golden Badge", "legendary"),

    ("epic_galaxy", "🌌 Galaxy", "epic"),
    ("epic_comet", "☄️ Comet", "legendary"),
    ("epic_cosmo", "🚀 COSMO", "mythic"),

    ("night_moon", "🌙 Moon", "rare"),
    ("night_ghost", "👻 Ghost", "epic"),
    ("night_eclipse", "🌑 Eclipse", "legendary"),

    ("cos_crown", "👑 COS Crown", "legendary"),
    ("cos_galaxy", "🌌 COS Galaxy", "mythic"),
    ("cos_core", "💠 COS Core", "mythic"),
]

DROPS = {
    "start": [
        ("basic_star", 50),
        ("school_pen", 40),
        ("meme_skull", 10),
    ],
    "basic": [
        ("basic_star", 55),
        ("basic_blue", 30),
        ("basic_purple", 12),
        ("meme_sigma", 3),
    ],
    "school": [
        ("school_pen", 60),
        ("backpack", 30),
        ("school_cup", 10),
    ],
    "meme": [
        ("meme_skull", 60),
        ("meme_sigma", 28),
        ("meme_fire", 12),
    ],
    "rare": [
        ("rare_diamond", 65),
        ("rare_crown", 28),
        ("rare_gold", 7),
    ],
    "epic": [
        ("epic_galaxy", 65),
        ("epic_comet", 30),
        ("epic_cosmo", 5),
    ],
    "night": [
        ("night_moon", 60),
        ("night_ghost", 30),
        ("night_eclipse", 10),
    ],
    "cos": [
        ("cos_crown", 65),
        ("cos_galaxy", 30),
        ("cos_core", 5),
    ],
}

RARITY = {
    "common": "🟢 Common",
    "rare": "🔵 Rare",
    "epic": "🟣 Epic",
    "legendary": "🟡 Legendary",
    "mythic": "🔴 Mythic",
}


# ============================================================
# FSM
# ============================================================

class Apply(StatesGroup):
    name = State()
    cls = State()
    phone = State()
    msg = State()


class GiveSD(StatesGroup):
    uid = State()
    amount = State()


class TakeSD(StatesGroup):
    uid = State()
    amount = State()


class Broadcast(StatesGroup):
    text = State()


class Promo(StatesGroup):
    code = State()


class PromoCreate(StatesGroup):
    code = State()
    reward = State()


class PromoDelete(StatesGroup):
    code = State()


class UserSearch(StatesGroup):
    query = State()


class BlockUser(StatesGroup):
    uid = State()


class UnblockUser(StatesGroup):
    uid = State()


class CasePrice(StatesGroup):
    case_id = State()
    price = State()


class ItemToggle(StatesGroup):
    code = State()


# ============================================================
# DB
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)

    con = db()
    cur = con.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            sd INTEGER DEFAULT 500,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            blocked INTEGER DEFAULT 0,
            created_at TEXT,
            last_activity TEXT,
            daily_claim TEXT
        );

        CREATE TABLE IF NOT EXISTS cases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            description TEXT,
            price INTEGER,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            rarity TEXT,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS case_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            item_id INTEGER,
            chance REAL,
            UNIQUE(case_id,item_id)
        );

        CREATE TABLE IF NOT EXISTS inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_id INTEGER,
            obtained_at TEXT
        );

        CREATE TABLE IF NOT EXISTS case_opens(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            case_id INTEGER,
            item_id INTEGER,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            kind TEXT,
            name TEXT,
            class_name TEXT,
            phone TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            admin_id INTEGER,
            created_at TEXT,
            decided_at TEXT
        );

        CREATE TABLE IF NOT EXISTS promo_codes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            reward INTEGER,
            max_uses INTEGER,
            uses INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS promo_uses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER,
            user_id INTEGER,
            used_at TEXT,
            UNIQUE(promo_id,user_id)
        );

        CREATE TABLE IF NOT EXISTS admins(
            user_id INTEGER PRIMARY KEY,
            role TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS admin_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_user_id INTEGER,
            details TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS achievements(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            description TEXT,
            reward INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS user_achievements(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            achievement_id INTEGER,
            obtained_at TEXT,
            UNIQUE(user_id, achievement_id)
        );
        """
    )

    cur.execute(
        "INSERT OR IGNORE INTO admins(user_id,role,created_at) VALUES(?,?,?)",
        (ADMIN_ID, "owner", now()),
    )

    for code, name, description, price in CASES:
        cur.execute(
            """
            INSERT OR IGNORE INTO cases
            (code,name,description,price)
            VALUES(?,?,?,?)
            """,
            (code, name, description, price),
        )

    for code, name, rarity in ITEMS:
        cur.execute(
            """
            INSERT OR IGNORE INTO items
            (code,name,rarity)
            VALUES(?,?,?)
            """,
            (code, name, rarity),
        )

    for case_code, drops in DROPS.items():
        case_row = cur.execute(
            "SELECT id FROM cases WHERE code=?",
            (case_code,),
        ).fetchone()

        if not case_row:
            continue

        for item_code, chance in drops:
            item_row = cur.execute(
                "SELECT id FROM items WHERE code=?",
                (item_code,),
            ).fetchone()

            if not item_row:
                continue

            cur.execute(
                """
                INSERT OR IGNORE INTO case_items
                (case_id,item_id,chance)
                VALUES(?,?,?)
                """,
                (case_row["id"], item_row["id"], chance),
            )

    achievements = [
        (
            "first_case",
            "🎁 Первый кейс",
            "Открыть первый кейс",
            50,
        ),
        (
            "ten_cases",
            "🔥 10 открытий",
            "Открыть 10 кейсов",
            150,
        ),
        (
            "hundred_cases",
            "💎 100 открытий",
            "Открыть 100 кейсов",
            500,
        ),
        (
            "collector",
            "🎒 Коллекционер",
            "Получить 10 предметов",
            250,
        ),
        (
            "rich",
            "💰 Богатый игрок",
            "Накопить 5000 SD",
            500,
        ),
    ]

    for code, name, description, reward in achievements:
        cur.execute(
            """
            INSERT OR IGNORE INTO achievements
            (code,name,description,reward)
            VALUES(?,?,?,?)
            """,
            (code, name, description, reward),
        )

    con.commit()
    con.close()


# ============================================================
# HELPERS
# ============================================================

def ensure(user):
    con = db()

    row = con.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user.id,),
    ).fetchone()

    if row:
        con.execute(
            """
            UPDATE users
            SET username=?,
                first_name=?,
                last_activity=?
            WHERE user_id=?
            """,
            (
                user.username,
                user.first_name or "",
                now(),
                user.id,
            ),
        )
    else:
        con.execute(
            """
            INSERT INTO users
            (user_id,username,first_name,created_at,last_activity)
            VALUES(?,?,?,?,?)
            """,
            (
                user.id,
                user.username,
                user.first_name or "",
                now(),
                now(),
            ),
        )

    con.commit()

    row = con.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user.id,),
    ).fetchone()

    con.close()

    return row


def is_admin(user_id):
    return user_id == ADMIN_ID


def log_admin(action, target=None, details=""):
    con = db()
    con.execute(
        """
        INSERT INTO admin_logs
        (admin_id,action,target_user_id,details,created_at)
        VALUES(?,?,?,?,?)
        """,
        (
            ADMIN_ID,
            action,
            target,
            details,
            now(),
        ),
    )
    con.commit()
    con.close()


def home_kb():
    b = InlineKeyboardBuilder()

    buttons = [
        ("🎮 Играть", "play"),
        ("👤 Профиль", "profile"),
        ("💰 Баланс", "balance"),
        ("🎒 Коллекция", "collection"),
        ("🏆 Рейтинг", "rating"),
        ("🎟 Промокод", "promo"),
        ("🏅 Достижения", "achievements"),
        ("📝 Заявки", "apps"),
        ("ℹ️ Обо мне", "about"),
    ]

    for text, data in buttons:
        b.button(text=text, callback_data=data)

    b.adjust(1, 2, 2, 2, 2)

    return b.as_markup()


def back(callback="home"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=callback,
                )
            ]
        ]
    )


def admin_kb():
    b = InlineKeyboardBuilder()

    buttons = [
        ("📊 Статистика", "adm_stats"),
        ("👥 Пользователи", "adm_users"),
        ("🔎 Найти пользователя", "adm_search"),
        ("🎁 Выдать SD", "adm_give"),
        ("➖ Забрать SD", "adm_take"),
        ("🚫 Блокировки", "adm_blocks"),
        ("🎟 Промокоды", "adm_promo"),
        ("📦 Кейсы", "adm_cases"),
        ("💎 Предметы", "adm_items"),
        ("📝 Заявки", "adm_apps"),
        ("📢 Рассылка", "adm_broadcast"),
        ("📜 Логи", "adm_logs"),
        ("💾 Бэкап БД", "adm_backup"),
    ]

    for text, data in buttons:
        b.button(text=text, callback_data=data)

    b.adjust(2)

    return b.as_markup()


# ============================================================
# USER START
# ============================================================

@dp.message(Command("start"))
async def start(message: Message):
    user = ensure(message.from_user)

    if user["blocked"]:
        return await message.answer(
            "🚫 <b>Ваш аккаунт заблокирован.</b>"
        )

    if os.path.isfile(IMAGE_FILE):
        if os.path.getsize(IMAGE_FILE) > 0:
            try:
                await message.answer_photo(
                    FSInputFile(IMAGE_FILE),
                    caption="✨ <b>COS-DROP</b>\n\nДобро пожаловать!",
                )
            except Exception:
                logging.exception("Ошибка отправки изображения")

    await message.answer(
        f"""
🎁 <b>COS-DROP</b>

💰 SD: <b>{user['sd']}</b>
⭐ Уровень: <b>{user['level']}</b>
✨ XP: <b>{user['xp']}</b>

Выбери раздел:
""",
        reply_markup=home_kb(),
    )


@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    user = ensure(callback.from_user)

    if user["blocked"]:
        return await callback.answer(
            "Ваш аккаунт заблокирован.",
            show_alert=True,
        )

    await callback.message.edit_text(
        f"""
🎁 <b>COS-DROP</b>

💰 SD: <b>{user['sd']}</b>
⭐ Уровень: <b>{user['level']}</b>

Выбери раздел:
""",
        reply_markup=home_kb(),
    )

    await callback.answer()


# ============================================================
# CASES
# ============================================================

@dp.callback_query(F.data == "play")
async def play(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT *
        FROM cases
        WHERE enabled=1
        ORDER BY id
        """
    ).fetchall()

    con.close()

    b = InlineKeyboardBuilder()

    for row in rows:
        b.button(
            text=f"{row['name']} · {row['price']} SD",
            callback_data=f"case:{row['id']}",
        )

    b.button(
        text="◀️ Назад",
        callback_data="home",
    )

    b.adjust(1)

    await callback.message.edit_text(
        "🎮 <b>КЕЙСЫ</b>\n\nВыбери кейс:",
        reply_markup=b.as_markup(),
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("case:"))
async def case_info(callback: CallbackQuery):
    try:
        case_id = int(callback.data.split(":")[1])
    except ValueError:
        return await callback.answer("Ошибка", show_alert=True)

    con = db()

    row = con.execute(
        """
        SELECT *
        FROM cases
        WHERE id=? AND enabled=1
        """,
        (case_id,),
    ).fetchone()

    con.close()

    if not row:
        return await callback.answer(
            "Кейс недоступен",
            show_alert=True,
        )

    b = InlineKeyboardBuilder()

    b.button(
        text="🎁 Открыть",
        callback_data=f"open:{case_id}",
    )

    b.button(
        text="◀️ Назад",
        callback_data="play",
    )

    b.adjust(1)

    await callback.message.edit_text(
        f"""
📦 <b>{escape(row['name'])}</b>

{escape(row['description'])}

💰 Стоимость: <b>{row['price']} SD</b>
""",
        reply_markup=b.as_markup(),
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("open:"))
async def open_case(callback: CallbackQuery):
    user = ensure(callback.from_user)

    if user["blocked"]:
        return await callback.answer(
            "Аккаунт заблокирован.",
            show_alert=True,
        )

    case_id = int(callback.data.split(":")[1])

    con = db()

    case_row = con.execute(
        """
        SELECT *
        FROM cases
        WHERE id=? AND enabled=1
        """,
        (case_id,),
    ).fetchone()

    if not case_row:
        con.close()
        return await callback.answer(
            "Кейс недоступен",
            show_alert=True,
        )

    if user["sd"] < case_row["price"]:
        con.close()
        return await callback.answer(
            "Недостаточно SD",
            show_alert=True,
        )

    items = con.execute(
        """
        SELECT i.*, ci.chance
        FROM case_items ci
        JOIN items i ON i.id=ci.item_id
        WHERE ci.case_id=?
          AND i.enabled=1
        """,
        (case_id,),
    ).fetchall()

    if not items:
        con.close()
        return await callback.answer(
            "В кейсе нет предметов.",
            show_alert=True,
        )

    selected = random.choices(
        items,
        weights=[float(x["chance"]) for x in items],
        k=1,
    )[0]

    con.execute(
        """
        UPDATE users
        SET sd=sd-?,
            xp=xp+10,
            last_activity=?
        WHERE user_id=?
        """,
        (
            case_row["price"],
            now(),
            callback.from_user.id,
        ),
    )

    con.execute(
        """
        INSERT INTO inventory
        (user_id,item_id,obtained_at)
        VALUES(?,?,?)
        """,
        (
            callback.from_user.id,
            selected["id"],
            now(),
        ),
    )

    con.execute(
        """
        INSERT INTO case_opens
        (user_id,case_id,item_id,created_at)
        VALUES(?,?,?,?)
        """,
        (
            callback.from_user.id,
            case_id,
            selected["id"],
            now(),
        ),
    )

    con.commit()
    con.close()

    await check_achievements(callback.from_user.id)

    await callback.message.edit_text(
        f"""
✨ <b>ОТКРЫТИЕ</b>

{RARITY.get(selected["rarity"], "⚪")}

<b>{escape(selected["name"])}</b>

🎒 Предмет добавлен в коллекцию!
⭐ +10 XP
""",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎮 Ещё",
                        callback_data="play",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎒 Коллекция",
                        callback_data="collection",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 Меню",
                        callback_data="home",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


# ============================================================
# PROFILE
# ============================================================

@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    user = ensure(callback.from_user)

    con = db()

    inventory_count = con.execute(
        """
        SELECT COUNT(*) n
        FROM inventory
        WHERE user_id=?
        """,
        (user["user_id"],),
    ).fetchone()["n"]

    opens = con.execute(
        """
        SELECT COUNT(*) n
        FROM case_opens
        WHERE user_id=?
        """,
        (user["user_id"],),
    ).fetchone()["n"]

    achievements = con.execute(
        """
        SELECT COUNT(*) n
        FROM user_achievements
        WHERE user_id=?
        """,
        (user["user_id"],),
    ).fetchone()["n"]

    con.close()

    await callback.message.edit_text(
        f"""
👤 <b>ПРОФИЛЬ</b>

ID: <code>{user['user_id']}</code>
Username: @{escape(user['username'] or 'нет')}

💰 SD: <b>{user['sd']}</b>
⭐ Уровень: <b>{user['level']}</b>
✨ XP: <b>{user['xp']}</b>

🎁 Открыто кейсов: <b>{opens}</b>
🎒 Предметов: <b>{inventory_count}</b>
🏅 Достижений: <b>{achievements}</b>
""",
        reply_markup=back(),
    )

    await callback.answer()


# ============================================================
# BALANCE
# ============================================================

@dp.callback_query(F.data == "balance")
async def balance(callback: CallbackQuery):
    user = ensure(callback.from_user)

    await callback.message.edit_text(
        f"""
💰 <b>БАЛАНС</b>

Твой баланс:

<b>{user['sd']} SD</b>

🎁 Ежедневный бонус: <b>+100 SD</b>

SD — виртуальная валюта Cos-drop.
Она не выводится и не обменивается на реальные деньги.
""",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎁 Получить бонус",
                        callback_data="daily",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎟 Промокод",
                        callback_data="promo",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="home",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


@dp.callback_query(F.data == "daily")
async def daily(callback: CallbackQuery):
    con = db()

    row = con.execute(
        """
        SELECT daily_claim
        FROM users
        WHERE user_id=?
        """,
        (callback.from_user.id,),
    ).fetchone()

    today = datetime.now(timezone.utc).date().isoformat()

    if row and row["daily_claim"] == today:
        con.close()
        return await callback.answer(
            "Бонус уже получен сегодня.",
            show_alert=True,
        )

    con.execute(
        """
        UPDATE users
        SET sd=sd+100,
            daily_claim=?,
            xp=xp+5,
            last_activity=?
        WHERE user_id=?
        """,
        (
            today,
            now(),
            callback.from_user.id,
        ),
    )

    con.commit()
    con.close()

    await callback.answer(
        "🎁 +100 SD и +5 XP!",
        show_alert=True,
    )

    await balance(callback)


# ============================================================
# COLLECTION
# ============================================================

@dp.callback_query(F.data == "collection")
async def collection(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT
            i.name,
            i.rarity,
            COUNT(*) n
        FROM inventory inv
        JOIN items i ON i.id=inv.item_id
        WHERE inv.user_id=?
        GROUP BY inv.item_id
        ORDER BY i.rarity, i.name
        """,
        (callback.from_user.id,),
    ).fetchall()

    con.close()

    if rows:
        text = "\n".join(
            f"{RARITY.get(row['rarity'], '⚪')} "
            f"{escape(row['name'])} ×{row['n']}"
            for row in rows
        )
    else:
        text = "Пока пусто."

    await callback.message.edit_text(
        f"🎒 <b>КОЛЛЕКЦИЯ</b>\n\n{text}",
        reply_markup=back(),
    )

    await callback.answer()


# ============================================================
# RATING
# ============================================================

@dp.callback_query(F.data == "rating")
async def rating(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT
            username,
            first_name,
            xp,
            level,
            (
                SELECT COUNT(*)
                FROM inventory i
                WHERE i.user_id=u.user_id
            ) items
        FROM users u
        WHERE blocked=0
        ORDER BY xp DESC, items DESC
        LIMIT 10
        """
    ).fetchall()

    con.close()

    if rows:
        text = "\n".join(
            f"{i}. @{escape(row['username'] or row['first_name'] or '-')}"
            f" — ⭐ {row['xp']} · 🎒 {row['items']}"
            for i, row in enumerate(rows, 1)
        )
    else:
        text = "Пока нет игроков."

    await callback.message.edit_text(
        f"🏆 <b>ТОП-10</b>\n\n{text}",
        reply_markup=back(),
    )

    await callback.answer()


# ============================================================
# ACHIEVEMENTS
# ============================================================

async def check_achievements(user_id):
    con = db()

    user = con.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,),
    ).fetchone()

    if not user:
        con.close()
        return

    opens = con.execute(
        """
        SELECT COUNT(*) n
        FROM case_opens
        WHERE user_id=?
        """,
        (user_id,),
    ).fetchone()["n"]

    items = con.execute(
        """
        SELECT COUNT(*) n
        FROM inventory
        WHERE user_id=?
        """,
        (user_id,),
    ).fetchone()["n"]

    checks = []

    if opens >= 1:
        checks.append("first_case")

    if opens >= 10:
        checks.append("ten_cases")

    if opens >= 100:
        checks.append("hundred_cases")

    if items >= 10:
        checks.append("collector")

    if user["sd"] >= 5000:
        checks.append("rich")

    for code in checks:
        achievement = con.execute(
            """
            SELECT *
            FROM achievements
            WHERE code=?
            """,
            (code,),
        ).fetchone()

        if not achievement:
            continue

        exists = con.execute(
            """
            SELECT 1
            FROM user_achievements
            WHERE user_id=? AND achievement_id=?
            """,
            (
                user_id,
                achievement["id"],
            ),
        ).fetchone()

        if exists:
            continue

        con.execute(
            """
            INSERT INTO user_achievements
            (user_id,achievement_id,obtained_at)
            VALUES(?,?,?)
            """,
            (
                user_id,
                achievement["id"],
                now(),
            ),
        )

        if achievement["reward"] > 0:
            con.execute(
                """
                UPDATE users
                SET sd=sd+?
                WHERE user_id=?
                """,
                (
                    achievement["reward"],
                    user_id,
                ),
            )

        try:
            await bot.send_message(
                user_id,
                f"""
🏅 <b>НОВОЕ ДОСТИЖЕНИЕ!</b>

{achievement['name']}

{escape(achievement['description'])}

💰 Награда: <b>+{achievement['reward']} SD</b>
""",
            )
        except Exception:
            pass

    # Level calculation
    level = max(1, user["xp"] // 100 + 1)

    con.execute(
        """
        UPDATE users
        SET level=?
        WHERE user_id=?
        """,
        (level, user_id),
    )

    con.commit()
    con.close()


@dp.callback_query(F.data == "achievements")
async def achievements(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT
            a.*,
            ua.obtained_at
        FROM achievements a
        LEFT JOIN user_achievements ua
            ON ua.achievement_id=a.id
            AND ua.user_id=?
        ORDER BY a.id
        """,
        (callback.from_user.id,),
    ).fetchall()

    con.close()

    lines = []

    for row in rows:
        if row["obtained_at"]:
            mark = "✅"
        else:
            mark = "🔒"

        lines.append(
            f"{mark} <b>{escape(row['name'])}</b>\n"
            f"└ {escape(row['description'])}\n"
            f"└ 💰 +{row['reward']} SD"
        )

    await callback.message.edit_text(
        "🏅 <b>ДОСТИЖЕНИЯ</b>\n\n" + "\n\n".join(lines),
        reply_markup=back(),
    )

    await callback.answer()


# ============================================================
# ABOUT
# ============================================================

@dp.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    await callback.message.edit_text(
        """
ℹ️ <b>О COS-DROP</b>

Коллекционный Telegram-проект
с кейсами, предметами, профилями,
достижениями и рейтингами.

💰 SD — виртуальная игровая валюта.
🎒 Предметы — виртуальные коллекционные предметы.

Все игровые ценности не имеют денежной стоимости.
""",
        reply_markup=back(),
    )

    await callback.answer()


# ============================================================
# APPLICATIONS
# ============================================================

@dp.callback_query(F.data == "apps")
async def applications(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT id,kind,status
        FROM applications
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (callback.from_user.id,),
    ).fetchall()

    con.close()

    if rows:
        text = "\n".join(
            f"#{row['id']} · {escape(row['kind'])} · {row['status']}"
            for row in rows
        )
    else:
        text = "Заявок пока нет."

    await callback.message.edit_text(
        f"📝 <b>МОИ ЗАЯВКИ</b>\n\n{text}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📝 Создать заявку",
                        callback_data="newapp",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="home",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


@dp.callback_query(F.data == "newapp")
async def new_application(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(Apply.name)

    await callback.message.edit_text(
        """
📝 <b>ЗАЯВКА</b>

Введите имя:
"""
    )

    await callback.answer()


@dp.message(StateFilter(Apply.name))
async def application_name(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        name=(message.text or "")[:100]
    )

    await state.set_state(Apply.cls)

    await message.answer("🏫 Введите класс:")


@dp.message(StateFilter(Apply.cls))
async def application_class(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        cls=(message.text or "")[:30]
    )

    await state.set_state(Apply.phone)

    await message.answer(
        "📱 Контакт для связи (по желанию):"
    )


@dp.message(StateFilter(Apply.phone))
async def application_phone(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        phone=(message.text or "")[:50]
    )

    await state.set_state(Apply.msg)

    await message.answer(
        "💬 Напишите сообщение:"
    )


@dp.message(StateFilter(Apply.msg))
async def application_message(
    message: Message,
    state: FSMContext,
):
    data = await state.update_data(
        msg=(message.text or "")[:1000]
    )

    con = db()

    cur = con.execute(
        """
        INSERT INTO applications
        (user_id,kind,name,class_name,phone,message,created_at)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            message.from_user.id,
            "general",
            data["name"],
            data["cls"],
            data["phone"],
            data["msg"],
            now(),
        ),
    )

    application_id = cur.lastrowid

    con.commit()
    con.close()

    await state.clear()

    await message.answer(
        f"✅ Заявка <b>#{application_id}</b> создана."
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            f"""
📝 <b>ЗАЯВКА #{application_id}</b>

👤 {escape(data['name'])}
🏫 {escape(data['cls'])}
📱 {escape(data['phone'])}
💬 {escape(data['msg'])}

🆔 <code>{message.from_user.id}</code>
""",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Принять",
                            callback_data=f"appok:{application_id}",
                        ),
                        InlineKeyboardButton(
                            text="❌ Отклонить",
                            callback_data=f"appno:{application_id}",
                        ),
                    ]
                ]
            ),
        )
    except Exception:
        logging.exception("Не удалось отправить заявку админу")


@dp.callback_query(F.data.startswith("appok:"))
async def approve_application(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    application_id = int(
        callback.data.split(":")[1]
    )

    con = db()

    row = con.execute(
        "SELECT * FROM applications WHERE id=?",
        (application_id,),
    ).fetchone()

    if not row:
        con.close()
        return await callback.answer(
            "Заявка не найдена.",
            show_alert=True,
        )

    con.execute(
        """
        UPDATE applications
        SET status='approved',
            admin_id=?,
            decided_at=?
        WHERE id=?
        """,
        (
            ADMIN_ID,
            now(),
            application_id,
        ),
    )

    con.commit()
    con.close()

    log_admin(
        "approve_application",
        row["user_id"],
        str(application_id),
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.answer(
        "Заявка принята."
    )

    try:
        await bot.send_message(
            row["user_id"],
            f"✅ Ваша заявка <b>#{application_id}</b> принята.",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("appno:"))
async def reject_application(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    application_id = int(
        callback.data.split(":")[1]
    )

    con = db()

    row = con.execute(
        "SELECT * FROM applications WHERE id=?",
        (application_id,),
    ).fetchone()

    if not row:
        con.close()
        return await callback.answer(
            "Заявка не найдена.",
            show_alert=True,
        )

    con.execute(
        """
        UPDATE applications
        SET status='rejected',
            admin_id=?,
            decided_at=?
        WHERE id=?
        """,
        (
            ADMIN_ID,
            now(),
            application_id,
        ),
    )

    con.commit()
    con.close()

    log_admin(
        "reject_application",
        row["user_id"],
        str(application_id),
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.answer(
        "Заявка отклонена."
    )

    try:
        await bot.send_message(
            row["user_id"],
            f"❌ Ваша заявка <b>#{application_id}</b> отклонена.",
        )
    except Exception:
        pass


# ============================================================
# PROMO USER
# ============================================================

@dp.callback_query(F.data == "promo")
async def promo_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(Promo.code)

    await callback.message.edit_text(
        """
🎟 <b>ПРОМОКОД</b>

Введите код:
"""
    )

    await callback.answer()


@dp.message(StateFilter(Promo.code))
async def use_promo(
    message: Message,
    state: FSMContext,
):
    code = (message.text or "").strip().upper()

    con = db()

    promo = con.execute(
        """
        SELECT *
        FROM promo_codes
        WHERE code=? AND enabled=1
        """,
        (code,),
    ).fetchone()

    if not promo:
        con.close()
        await state.clear()
        return await message.answer(
            "❌ Промокод не найден."
        )

    used = con.execute(
        """
        SELECT 1
        FROM promo_uses
        WHERE promo_id=? AND user_id=?
        """,
        (
            promo["id"],
            message.from_user.id,
        ),
    ).fetchone()

    if used:
        con.close()
        await state.clear()
        return await message.answer(
            "❌ Ты уже использовал этот промокод."
        )

    if promo["uses"] >= promo["max_uses"]:
        con.close()
        await state.clear()
        return await message.answer(
            "❌ Лимит использований закончился."
        )

    con.execute(
        """
        INSERT INTO promo_uses
        (promo_id,user_id,used_at)
        VALUES(?,?,?)
        """,
        (
            promo["id"],
            message.from_user.id,
            now(),
        ),
    )

    con.execute(
        """
        UPDATE promo_codes
        SET uses=uses+1
        WHERE id=?
        """,
        (promo["id"],),
    )

    con.execute(
        """
        UPDATE users
        SET sd=sd+?
        WHERE user_id=?
        """,
        (
            promo["reward"],
            message.from_user.id,
        ),
    )

    con.commit()
    con.close()

    await state.clear()

    await message.answer(
        f"""
🎉 <b>ПРОМОКОД АКТИВИРОВАН!</b>

🎟 <code>{escape(code)}</code>
💰 Награда: <b>+{promo['reward']} SD</b>
"""
    )

    await check_achievements(
        message.from_user.id
    )


# ============================================================
# ADMIN COMMAND
# ============================================================

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        """
👑 <b>COS-DROP ADMIN PANEL</b>

Управление ботом:
""",
        reply_markup=admin_kb(),
    )


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        """
👑 <b>COS-DROP ADMIN PANEL</b>

Выбери раздел:
""",
        reply_markup=admin_kb(),
    )

    await callback.answer()


# ============================================================
# ADMIN STATISTICS
# ============================================================

@dp.callback_query(F.data == "adm_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    users = con.execute(
        "SELECT COUNT(*) n FROM users"
    ).fetchone()["n"]

    active = con.execute(
        """
        SELECT COUNT(*) n
        FROM users
        WHERE blocked=0
        """
    ).fetchone()["n"]

    blocked = con.execute(
        """
        SELECT COUNT(*) n
        FROM users
        WHERE blocked=1
        """
    ).fetchone()["n"]

    sd = con.execute(
        """
        SELECT COALESCE(SUM(sd),0) n
        FROM users
        """
    ).fetchone()["n"]

    opens = con.execute(
        """
        SELECT COUNT(*) n
        FROM case_opens
        """
    ).fetchone()["n"]

    inventory = con.execute(
        """
        SELECT COUNT(*) n
        FROM inventory
        """
    ).fetchone()["n"]

    applications = con.execute(
        """
        SELECT COUNT(*) n
        FROM applications
        WHERE status='pending'
        """
    ).fetchone()["n"]

    promos = con.execute(
        """
        SELECT COUNT(*) n
        FROM promo_codes
        WHERE enabled=1
        """
    ).fetchone()["n"]

    con.close()

    await callback.message.edit_text(
        f"""
📊 <b>СТАТИСТИКА COS-DROP</b>

👥 Пользователей: <b>{users}</b>
🟢 Активных: <b>{active}</b>
🚫 Заблокировано: <b>{blocked}</b>

💰 Всего SD: <b>{sd}</b>

🎁 Открытий кейсов: <b>{opens}</b>
🎒 Предметов: <b>{inventory}</b>

📝 Заявок ожидает: <b>{applications}</b>
🎟 Активных промокодов: <b>{promos}</b>
""",
        reply_markup=admin_kb(),
    )

    await callback.answer()


# ============================================================
# ADMIN USERS
# ============================================================

@dp.callback_query(F.data == "adm_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT user_id,username,first_name,sd,level,blocked
        FROM users
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    con.close()

    lines = []

    for row in rows:
        status = "🚫" if row["blocked"] else "🟢"

        lines.append(
            f"{status} <code>{row['user_id']}</code> "
            f"@{escape(row['username'] or '-')}"
            f" · {row['sd']} SD · Lv.{row['level']}"
        )

    text = (
        "👥 <b>ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ</b>\n\n"
        + ("\n".join(lines) if lines else "Пользователей нет.")
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_kb(),
    )

    await callback.answer()


# ============================================================
# ADMIN SEARCH
# ============================================================

@dp.callback_query(F.data == "adm_search")
async def admin_search_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(UserSearch.query)

    await callback.message.edit_text(
        """
🔎 <b>ПОИСК ПОЛЬЗОВАТЕЛЯ</b>

Отправь Telegram ID или username.
"""
    )

    await callback.answer()


@dp.message(StateFilter(UserSearch.query))
async def admin_search_result(
    message: Message,
    state: FSMContext,
):
    if not is_admin(message.from_user.id):
        return

    query = (message.text or "").strip()

    con = db()

    if query.isdigit():
        row = con.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (int(query),),
        ).fetchone()
    else:
        query = query.lstrip("@")

        row = con.execute(
            """
            SELECT *
            FROM users
            WHERE LOWER(username)=LOWER(?)
            """,
            (query,),
        ).fetchone()

    if not row:
        con.close()
        return await message.answer(
            "❌ Пользователь не найден."
        )

    inventory = con.execute(
        """
        SELECT COUNT(*) n
        FROM inventory
        WHERE user_id=?
        """,
        (row["user_id"],),
    ).fetchone()["n"]

    opens = con.execute(
        """
        SELECT COUNT(*) n
        FROM case_opens
        WHERE user_id=?
        """,
        (row["user_id"],),
    ).fetchone()["n"]

    con.close()

    await state.clear()

    await message.answer(
        f"""
👤 <b>ПОЛЬЗОВАТЕЛЬ</b>

🆔 <code>{row['user_id']}</code>
👤 @{escape(row['username'] or 'нет')}
📛 {escape(row['first_name'] or '-')}

💰 SD: <b>{row['sd']}</b>
⭐ Level: <b>{row['level']}</b>
✨ XP: <b>{row['xp']}</b>

🎁 Кейсов: <b>{opens}</b>
🎒 Предметов: <b>{inventory}</b>

🚫 Заблокирован: <b>{'Да' if row['blocked'] else 'Нет'}</b>
""",
        reply_markup=admin_kb(),
    )


# ============================================================
# GIVE SD
# ============================================================

@dp.callback_query(F.data == "adm_give")
async def admin_give_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(GiveSD.uid)

    await callback.message.edit_text(
        "🎁 <b>ВЫДАТЬ SD</b>\n\nВведите Telegram ID:"
    )

    await callback.answer()


@dp.message(StateFilter(GiveSD.uid))
async def admin_give_uid(
    message: Message,
    state: FSMContext,
):
    try:
        uid = int((message.text or "").strip())
    except ValueError:
        return await message.answer(
            "❌ ID должен быть числом."
        )

    await state.update_data(uid=uid)
    await state.set_state(GiveSD.amount)

    await message.answer(
        "💰 Введите количество SD:"
    )


@dp.message(StateFilter(GiveSD.amount))
async def admin_give_amount(
    message: Message,
    state: FSMContext,
):
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        return await message.answer(
            "❌ Введите целое число."
        )

    if amount <= 0:
        return await message.answer(
            "❌ Сумма должна быть больше нуля."
        )

    data = await state.get_data()

    con = db()

    row = con.execute(
        """
        SELECT user_id
        FROM users
        WHERE user_id=?
        """,
        (data["uid"],),
    ).fetchone()

    if not row:
        con.close()
        return await message.answer(
            "❌ Пользователь не найден."
        )

    con.execute(
        """
        UPDATE users
        SET sd=sd+?
        WHERE user_id=?
        """,
        (
            amount,
            data["uid"],
        ),
    )

    con.commit()
    con.close()

    log_admin(
        "give_sd",
        data["uid"],
        str(amount),
    )

    await state.clear()

    await message.answer(
        f"✅ Пользователю <code>{data['uid']}</code> выдано "
        f"<b>+{amount} SD</b>."
    )


# ============================================================
# TAKE SD
# ============================================================

@dp.callback_query(F.data == "adm_take")
async def admin_take_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(TakeSD.uid)

    await callback.message.edit_text(
        "➖ <b>ЗАБРАТЬ SD</b>\n\nВведите Telegram ID:"
    )

    await callback.answer()


@dp.message(StateFilter(TakeSD.uid))
async def admin_take_uid(
    message: Message,
    state: FSMContext,
):
    try:
        uid = int((message.text or "").strip())
    except ValueError:
        return await message.answer(
            "❌ Неверный ID."
        )

    await state.update_data(uid=uid)
    await state.set_state(TakeSD.amount)

    await message.answer(
        "Введите количество SD:"
    )


@dp.message(StateFilter(TakeSD.amount))
async def admin_take_amount(
    message: Message,
    state: FSMContext,
):
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        return await message.answer(
            "❌ Введите число."
        )

    if amount <= 0:
        return await message.answer(
            "❌ Сумма должна быть больше нуля."
        )

    data = await state.get_data()

    con = db()

    row = con.execute(
        """
        SELECT sd
        FROM users
        WHERE user_id=?
        """,
        (data["uid"],),
    ).fetchone()

    if not row:
        con.close()
        return await message.answer(
            "❌ Пользователь не найден."
        )

    new_balance = max(
        0,
        row["sd"] - amount,
    )

    con.execute(
        """
        UPDATE users
        SET sd=?
        WHERE user_id=?
        """,
        (
            new_balance,
            data["uid"],
        ),
    )

    con.commit()
    con.close()

    log_admin(
        "take_sd",
        data["uid"],
        str(amount),
    )

    await state.clear()

    await message.answer(
        f"✅ Снято <b>{amount} SD</b>.\n"
        f"💰 Новый баланс: <b>{new_balance} SD</b>"
    )


# ============================================================
# BLOCKS
# ============================================================

@dp.callback_query(F.data == "adm_blocks")
async def admin_blocks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data="block_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔓 Разблокировать",
                    callback_data="unblock_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Заблокированные",
                    callback_data="blocked_list",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Админ-панель",
                    callback_data="admin_home",
                )
            ],
        ]
    )

    await callback.message.edit_text(
        "🚫 <b>БЛОКИРОВКИ</b>",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(F.data == "block_start")
async def block_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(BlockUser.uid)

    await callback.message.edit_text(
        "🚫 Введите Telegram ID пользователя:"
    )

    await callback.answer()


@dp.message(StateFilter(BlockUser.uid))
async def block_user(
    message: Message,
    state: FSMContext,
):
    try:
        uid = int(message.text)
    except ValueError:
        return await message.answer(
            "❌ Неверный ID."
        )

    con = db()

    con.execute(
        """
        UPDATE users
        SET blocked=1
        WHERE user_id=?
        """,
        (uid,),
    )

    con.commit()
    con.close()

    log_admin(
        "block_user",
        uid,
    )

    await state.clear()

    await message.answer(
        f"🚫 Пользователь <code>{uid}</code> заблокирован."
    )


@dp.callback_query(F.data == "unblock_start")
async def unblock_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(UnblockUser.uid)

    await callback.message.edit_text(
        "🔓 Введите Telegram ID:"
    )

    await callback.answer()


@dp.message(StateFilter(UnblockUser.uid))
async def unblock_user(
    message: Message,
    state: FSMContext,
):
    try:
        uid = int(message.text)
    except ValueError:
        return await message.answer(
            "❌ Неверный ID."
        )

    con = db()

    con.execute(
        """
        UPDATE users
        SET blocked=0
        WHERE user_id=?
        """,
        (uid,),
    )

    con.commit()
    con.close()

    log_admin(
        "unblock_user",
        uid,
    )

    await state.clear()

    await message.answer(
        f"🔓 Пользователь <code>{uid}</code> разблокирован."
    )


@dp.callback_query(F.data == "blocked_list")
async def blocked_list(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT user_id,username,first_name
        FROM users
        WHERE blocked=1
        ORDER BY id DESC
        LIMIT 50
        """
    ).fetchall()

    con.close()

    text = "\n".join(
        f"🚫 <code>{row['user_id']}</code> "
        f"@{escape(row['username'] or row['first_name'] or '-')}"
        for row in rows
    )

    if not text:
        text = "Заблокированных нет."

    await callback.message.edit_text(
        f"🚫 <b>ЗАБЛОКИРОВАННЫЕ</b>\n\n{text}",
        reply_markup=back("adm_blocks"),
    )

    await callback.answer()


# ============================================================
# ADMIN PROMOS
# ============================================================

@dp.callback_query(F.data == "adm_promo")
async def admin_promos(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT code,reward,uses,max_uses
        FROM promo_codes
        WHERE enabled=1
        ORDER BY id DESC
        """
    ).fetchall()

    con.close()

    if rows:
        text = "\n".join(
            f"🔹 <code>{escape(row['code'])}</code> "
            f"— +{row['reward']} SD "
            f"· {row['uses']}/{row['max_uses']}"
            for row in rows
        )
    else:
        text = "Промокодов пока нет."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить",
                    callback_data="promo_add",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data="promo_del",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data="adm_promo",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Админ-панель",
                    callback_data="admin_home",
                )
            ],
        ]
    )

    await callback.message.edit_text(
        f"🎟 <b>ПРОМОКОДЫ</b>\n\n{text}",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(F.data == "promo_add")
async def promo_add(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(PromoCreate.code)

    await callback.message.edit_text(
        """
➕ <b>СОЗДАНИЕ ПРОМОКОДА</b>

Введите код.

Например:

<code>COS500</code>
"""
    )

    await callback.answer()


@dp.message(StateFilter(PromoCreate.code))
async def promo_add_code(
    message: Message,
    state: FSMContext,
):
    code = (message.text or "").strip().upper()

    if not re.fullmatch(
        r"[A-Z0-9_-]{2,32}",
        code,
    ):
        return await message.answer(
            "❌ Используй латинские буквы, цифры, _ или -."
        )

    con = db()

    exists = con.execute(
        """
        SELECT 1
        FROM promo_codes
        WHERE code=?
        """,
        (code,),
    ).fetchone()

    con.close()

    if exists:
        return await message.answer(
            "❌ Такой промокод уже существует."
        )

    await state.update_data(code=code)
    await state.set_state(PromoCreate.reward)

    await message.answer(
        f"""
🎟 Код: <code>{escape(code)}</code>

💰 Сколько SD выдавать?
"""
    )


@dp.message(StateFilter(PromoCreate.reward))
async def promo_add_reward(
    message: Message,
    state: FSMContext,
):
    try:
        reward = int(
            (message.text or "").strip()
        )
    except ValueError:
        return await message.answer(
            "❌ Введите число."
        )

    if reward <= 0:
        return await message.answer(
            "❌ Награда должна быть больше 0."
        )

    data = await state.get_data()

    con = db()

    try:
        con.execute(
            """
            INSERT INTO promo_codes
            (code,reward,max_uses,uses,enabled)
            VALUES(?,?,999999999,0,1)
            """,
            (
                data["code"],
                reward,
            ),
        )

        con.commit()

    except sqlite3.IntegrityError:
        con.close()
        await state.clear()
        return await message.answer(
            "❌ Такой код уже существует."
        )

    con.close()

    log_admin(
        "create_promo",
        details=f"{data['code']} +{reward} SD",
    )

    await state.clear()

    await message.answer(
        f"""
✅ <b>ПРОМОКОД СОЗДАН</b>

🎟 <code>{escape(data['code'])}</code>
💰 Награда: <b>+{reward} SD</b>
♾ Каждый пользователь может активировать его один раз.
"""
    )


@dp.callback_query(F.data == "promo_del")
async def promo_delete_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    con = db()

    rows = con.execute(
        """
        SELECT code,reward,uses
        FROM promo_codes
        WHERE enabled=1
        ORDER BY id DESC
        """
    ).fetchall()

    con.close()

    if not rows:
        return await callback.answer(
            "Промокодов нет.",
            show_alert=True,
        )

    text = "\n".join(
        f"• <code>{escape(row['code'])}</code> "
        f"— +{row['reward']} SD · {row['uses']} использований"
        for row in rows
    )

    await state.set_state(PromoDelete.code)

    await callback.message.edit_text(
        f"""
🗑 <b>УДАЛЕНИЕ ПРОМОКОДА</b>

{text}

Введите код, который удалить:
"""
    )

    await callback.answer()


@dp.message(StateFilter(PromoDelete.code))
async def promo_delete_code(
    message: Message,
    state: FSMContext,
):
    code = (message.text or "").strip().upper()

    con = db()

    promo = con.execute(
        """
        SELECT *
        FROM promo_codes
        WHERE code=?
        """,
        (code,),
    ).fetchone()

    if not promo:
        con.close()
        return await message.answer(
            "❌ Такой промокод не найден."
        )

    con.execute(
        """
        DELETE FROM promo_uses
        WHERE promo_id=?
        """,
        (promo["id"],),
    )

    con.execute(
        """
        DELETE FROM promo_codes
        WHERE id=?
        """,
        (promo["id"],),
    )

    con.commit()
    con.close()

    log_admin(
        "delete_promo",
        details=code,
    )

    await state.clear()

    await message.answer(
        f"🗑 Промокод <code>{escape(code)}</code> удалён."
    )


# ============================================================
# ADMIN CASES
# ============================================================

@dp.callback_query(F.data == "adm_cases")
async def admin_cases(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT id,code,name,price,enabled
        FROM cases
        ORDER BY id
        """
    ).fetchall()

    con.close()

    lines = []

    for row in rows:
        status = "🟢" if row["enabled"] else "🔴"

        lines.append(
            f"{status} <b>{escape(row['name'])}</b>\n"
            f"└ ID: <code>{row['id']}</code> · "
            f"{row['price']} SD · "
            f"<code>{escape(row['code'])}</code>"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Вкл/выкл кейс",
                    callback_data="case_toggle_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Изменить цену",
                    callback_data="case_price_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Админ-панель",
                    callback_data="admin_home",
                )
            ],
        ]
    )

    await callback.message.edit_text(
        "📦 <b>УПРАВЛЕНИЕ КЕЙСАМИ</b>\n\n"
        + "\n\n".join(lines),
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(F.data == "case_toggle_start")
async def case_toggle_start(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT id,name,enabled
        FROM cases
        ORDER BY id
        """
    ).fetchall()

    con.close()

    keyboard = []

    for row in rows:
        status = "🟢" if row["enabled"] else "🔴"

        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {row['name']}",
                    callback_data=f"case_toggle:{row['id']}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="adm_cases",
            )
        ]
    )

    await callback.message.edit_text(
        "🎮 Выбери кейс:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        ),
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("case_toggle:"))
async def case_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    case_id = int(
        callback.data.split(":")[1]
    )

    con = db()

    row = con.execute(
        """
        SELECT enabled,name
        FROM cases
        WHERE id=?
        """,
        (case_id,),
    ).fetchone()

    if not row:
        con.close()
        return await callback.answer(
            "Кейс не найден.",
            show_alert=True,
        )

    new_value = 0 if row["enabled"] else 1

    con.execute(
        """
        UPDATE cases
        SET enabled=?
        WHERE id=?
        """,
        (
            new_value,
            case_id,
        ),
    )

    con.commit()
    con.close()

    log_admin(
        "toggle_case",
        details=f"{case_id}:{new_value}",
    )

    await callback.answer(
        "Кейс включён." if new_value else "Кейс выключен.",
        show_alert=True,
    )

    await admin_cases(callback)


# ============================================================
# ADMIN ITEMS
# ============================================================

@dp.callback_query(F.data == "adm_items")
async def admin_items(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT code,name,rarity,enabled
        FROM items
        ORDER BY id
        """
    ).fetchall()

    con.close()

    lines = []

    for row in rows:
        status = "🟢" if row["enabled"] else "🔴"

        lines.append(
            f"{status} {RARITY.get(row['rarity'], '⚪')} "
            f"<b>{escape(row['name'])}</b>\n"
            f"└ <code>{escape(row['code'])}</code>"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Вкл/выкл предмет",
                    callback_data="item_toggle_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Админ-панель",
                    callback_data="admin_home",
                )
            ],
        ]
    )

    await callback.message.edit_text(
        "💎 <b>ПРЕДМЕТЫ</b>\n\n"
        + "\n\n".join(lines),
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(F.data == "item_toggle_start")
async def item_toggle_start(callback: CallbackQuery):
    con = db()

    rows = con.execute(
        """
        SELECT id,name,enabled
        FROM items
        ORDER BY id
        """
    ).fetchall()

    con.close()

    keyboard = []

    for row in rows:
        status = "🟢" if row["enabled"] else "🔴"

        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {row['name']}",
                    callback_data=f"item_toggle:{row['id']}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="adm_items",
            )
        ]
    )

    await callback.message.edit_text(
        "💎 Выбери предмет:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        ),
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("item_toggle:"))
async def item_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    item_id = int(
        callback.data.split(":")[1]
    )

    con = db()

    row = con.execute(
        """
        SELECT enabled,name
        FROM items
        WHERE id=?
        """,
        (item_id,),
    ).fetchone()

    if not row:
        con.close()
        return await callback.answer(
            "Предмет не найден.",
            show_alert=True,
        )

    new_value = 0 if row["enabled"] else 1

    con.execute(
        """
        UPDATE items
        SET enabled=?
        WHERE id=?
        """,
        (
            new_value,
            item_id,
        ),
    )

    con.commit()
    con.close()

    log_admin(
        "toggle_item",
        details=f"{item_id}:{new_value}",
    )

    await callback.answer(
        "Предмет включён." if new_value else "Предмет выключен.",
        show_alert=True,
    )

    await admin_items(callback)


# ============================================================
# ADMIN APPLICATIONS
# ============================================================

@dp.callback_query(F.data == "adm_apps")
async def admin_applications(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT id,user_id,name,class_name,status
        FROM applications
        ORDER BY id DESC
        LIMIT 30
        """
    ).fetchall()

    con.close()

    if rows:
        text = "\n".join(
            f"#{row['id']} · "
            f"<code>{row['user_id']}</code> · "
            f"{escape(row['name'] or '-')}"
            f" · {row['status']}"
            for row in rows
        )
    else:
        text = "Заявок пока нет."

    await callback.message.edit_text(
        f"📝 <b>ЗАЯВКИ</b>\n\n{text}",
        reply_markup=admin_kb(),
    )

    await callback.answer()


# ============================================================
# ADMIN BROADCAST
# ============================================================

@dp.callback_query(F.data == "adm_broadcast")
async def admin_broadcast(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(Broadcast.text)

    await callback.message.edit_text(
        """
📢 <b>РАССЫЛКА</b>

Отправь сообщение, которое нужно отправить пользователям.

Поддерживается HTML.
"""
    )

    await callback.answer()


@dp.message(StateFilter(Broadcast.text))
async def broadcast_send(
    message: Message,
    state: FSMContext,
):
    if not is_admin(message.from_user.id):
        return

    con = db()

    users = con.execute(
        """
        SELECT user_id
        FROM users
        WHERE blocked=0
        """
    ).fetchall()

    con.close()

    success = 0
    failed = 0

    for row in users:
        try:
            await bot.send_message(
                row["user_id"],
                message.text or "",
            )
            success += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.05)

    await state.clear()

    log_admin(
        "broadcast",
        details=f"success={success},failed={failed}",
    )

    await message.answer(
        f"""
📢 <b>РАССЫЛКА ЗАВЕРШЕНА</b>

✅ Отправлено: <b>{success}</b>
❌ Ошибок: <b>{failed}</b>
"""
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@dp.callback_query(F.data == "adm_logs")
async def admin_logs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT *
        FROM admin_logs
        ORDER BY id DESC
        LIMIT 30
        """
    ).fetchall()

    con.close()

    if rows:
        text = "\n".join(
            f"🕐 {escape(row['created_at'][:19])}\n"
            f"├ {escape(row['action'])}\n"
            f"└ ID: {row['target_user_id'] or '-'}"
            for row in rows
        )
    else:
        text = "Логов пока нет."

    await callback.message.edit_text(
        f"📜 <b>ЛОГИ АДМИНИСТРАТОРА</b>\n\n{text}",
        reply_markup=admin_kb(),
    )

    await callback.answer()


# ============================================================
# DATABASE BACKUP
# ============================================================

@dp.callback_query(F.data == "adm_backup")
async def admin_backup(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    try:
        os.makedirs(
            BACKUP_DIR,
            exist_ok=True,
        )

        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%d_%H%M%S")

        backup_path = os.path.join(
            BACKUP_DIR,
            f"cosdrop_{timestamp}.sqlite3",
        )

        source = sqlite3.connect(DB_FILE)
        destination = sqlite3.connect(backup_path)

        with destination:
            source.backup(destination)

        destination.close()
        source.close()

        size = os.path.getsize(
            backup_path
        )

        log_admin(
            "database_backup",
            details=backup_path,
        )

        await callback.message.edit_text(
            f"""
💾 <b>БЭКАП БД СОЗДАН</b>

📁 Файл:
<code>{escape(backup_path)}</code>

📦 Размер:
<b>{size:,} bytes</b>

✅ Основная база не изменена.
""",
            reply_markup=admin_kb(),
        )

        await callback.answer(
            "Бэкап создан."
        )

    except Exception as exc:
        logging.exception("Backup error")

        await callback.answer(
            "Ошибка создания бэкапа.",
            show_alert=True,
        )

        await callback.message.answer(
            f"❌ <code>{escape(str(exc))}</code>"
        )


# ============================================================
# ADMIN CASE PRICE
# ============================================================

@dp.callback_query(F.data == "case_price_start")
async def case_price_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    con = db()

    rows = con.execute(
        """
        SELECT id,name,price
        FROM cases
        ORDER BY id
        """
    ).fetchall()

    con.close()

    keyboard = []

    for row in rows:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{row['name']} · {row['price']} SD",
                    callback_data=f"price_case:{row['id']}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="adm_cases",
            )
        ]
    )

    await callback.message.edit_text(
        "💰 Выбери кейс:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        ),
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("price_case:"))
async def price_case(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(callback.from_user.id):
        return

    case_id = int(
        callback.data.split(":")[1]
    )

    await state.update_data(
        case_id=case_id
    )

    await state.set_state(
        CasePrice.price
    )

    await callback.message.edit_text(
        "💰 Введи новую цену кейса в SD:"
    )

    await callback.answer()


@dp.message(StateFilter(CasePrice.price))
async def save_case_price(
    message: Message,
    state: FSMContext,
):
    try:
        price = int(
            (message.text or "").strip()
        )
    except ValueError:
        return await message.answer(
            "❌ Введи целое число."
        )

    if price < 0:
        return await message.answer(
            "❌ Цена не может быть отрицательной."
        )

    data = await state.get_data()

    con = db()

    con.execute(
        """
        UPDATE cases
        SET price=?
        WHERE id=?
        """,
        (
            price,
            data["case_id"],
        ),
    )

    con.commit()
    con.close()

    log_admin(
        "change_case_price",
        details=f"case={data['case_id']},price={price}",
    )

    await state.clear()

    await message.answer(
        f"✅ Цена кейса изменена на <b>{price} SD</b>."
    )


# ============================================================
# FALLBACK
# ============================================================

@dp.message()
async def fallback(message: Message):
    user = ensure(message.from_user)

    if user["blocked"]:
        return await message.answer(
            "🚫 Ваш аккаунт заблокирован."
        )

    await message.answer(
        "Используй /start, чтобы открыть меню."
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    init_db()

    logging.info(
        "COS-DROP started | DB=%s",
        DB_FILE,
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
