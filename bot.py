import asyncio, json, logging, os, random, re, sqlite3, string
from datetime import datetime, timezone, timedelta
from html import escape
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (Message, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, FSInputFile, LabeledPrice, PreCheckoutQuery)
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = 8146320391
DB_FILE = os.getenv("DB_FILE", "/data/cosdrop.sqlite3" if os.path.isdir("/data") else "cosdrop.sqlite3")
IMAGE_FILE = "imagemain.png"
BACKUP_DIR = os.getenv("BACKUP_DIR", "/data/backups" if os.path.isdir("/data") else "backups")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add BOT_TOKEN in Railway Variables.")
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ========== ЛИМИТЫ ==========
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

def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con

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

def now(): return datetime.now(timezone.utc).isoformat()
def today(): return datetime.now(timezone.utc).date().isoformat()

# ========== ДАННЫЕ ==========
CASES = [("start","🎒 Старт","Стартовый",0),("basic","📦 Basic","Обычный",100),
    ("school","🏫 School","Школьная",150),("meme","😂 Meme","Мемы",200),
    ("rare","💎 Rare","Редкие",300),("epic","🟣 Epic","Эпик",500),
    ("night","🌙 Night","Ночь",700),("cos","👑 COS","Главный",1000)]
ITEMS = [("basic_star","⭐ Star","common",20),("basic_blue","🔷 Blue","rare",80),
    ("basic_purple","🟣 Purple","epic",300),("school_pen","🖊️ Ручка","rare",90),
    ("backpack","🎒 Рюкзак","epic",350),("school_cup","🏆 Кубок","legendary",1200),
    ("meme_skull","💀 Skull","common",25),("meme_sigma","🗿 Sigma","rare",100),
    ("meme_fire","🔥 Fire","epic",400),("rare_diamond","💎 Diamond","rare",120),
    ("rare_crown","👑 Crown","epic",500),("rare_gold","✨ Badge","legendary",1500),
    ("epic_galaxy","🌌 Galaxy","epic",600),("epic_comet","☄️ Comet","legendary",1800),
    ("epic_cosmo","🚀 COSMO","mythic",5000),("night_moon","🌙 Moon","rare",130),
    ("night_ghost","👻 Ghost","epic",550),("night_eclipse","🌑 Eclipse","legendary",2000),
    ("cos_crown","👑 COS Crown","legendary",2500),("cos_galaxy","🌌 Galaxy","mythic",6000),
    ("cos_core","💠 Core","mythic",8000)]
DROPS = {"start":[("basic_star",50),("school_pen",40),("meme_skull",10)],
    "basic":[("basic_star",55),("basic_blue",30),("basic_purple",12),("meme_sigma",3)],
    "school":[("school_pen",60),("backpack",30),("school_cup",10)],
    "meme":[("meme_skull",60),("meme_sigma",28),("meme_fire",12)],
    "rare":[("rare_diamond",65),("rare_crown",28),("rare_gold",7)],
    "epic":[("epic_galaxy",65),("epic_comet",30),("epic_cosmo",5)],
    "night":[("night_moon",60),("night_ghost",30),("night_eclipse",10)],
    "cos":[("cos_crown",65),("cos_galaxy",30),("cos_core",5)]}
RARITY = {"common":"🟢 Common","rare":"🔵 Rare","epic":"🟣 Epic","legendary":"🟡 Legendary","mythic":"🔴 Mythic"}
RARITY_ORDER = ["common","rare","epic","legendary","mythic"]
SLOT_SYMBOLS = ["🍒","🍋","🔔","💎","7️⃣","⭐"]
SLOT_PAYOUTS = {("🍒","🍒","🍒"):3,("🍋","🍋","🍋"):4,("🔔","🔔","🔔"):6,
    ("💎","💎","💎"):12,("7️⃣","7️⃣","7️⃣"):25,("⭐","⭐","⭐"):50}
SUB_BONUS = {"daily_mult":2,"xp_mult":1.10,"badge":"💎"}

# ========== FSM ==========
class Apply(StatesGroup): name=State(); cls=State(); phone=State(); msg=State()
class GiveSD(StatesGroup): uid=State(); amount=State()
class TakeSD(StatesGroup): uid=State(); amount=State()
class Broadcast(StatesGroup): text=State()
class Promo(StatesGroup): code=State()
class PromoCreate(StatesGroup): code=State(); reward=State()
class PromoDelete(StatesGroup): code=State()
class UserSearch(StatesGroup): query=State()
class BlockUser(StatesGroup): uid=State()
class UnblockUser(StatesGroup): uid=State()
class CasePrice(StatesGroup): case_id=State(); price=State()
class WithdrawFSM(StatesGroup): amount=State()
class CasinoBet(StatesGroup): game=State(); amount=State()
class DuelBet(StatesGroup): amount=State()
class A2SD(StatesGroup): uid=State(); val=State(); mode=State()
class A2XP(StatesGroup): uid=State(); val=State()
class A2Msg(StatesGroup): uid=State(); text=State()
class A2Search(StatesGroup): q=State()
class A2Reset(StatesGroup): uid=State()
class A2Broadcast(StatesGroup): text=State()
class A3Limit(StatesGroup): key=State()
class A3Mass(StatesGroup): mode=State(); amount=State()
class A3PromoMass(StatesGroup): count=State(); reward=State()

# ========== БД ==========
def init_db():
    con = db(); cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
        username TEXT, first_name TEXT, sd INTEGER DEFAULT 100, xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1, blocked INTEGER DEFAULT 0, created_at TEXT, last_activity TEXT,
        daily_claim TEXT, daily_streak INTEGER DEFAULT 0, last_case_at TEXT,
        referrer_id INTEGER, donated INTEGER DEFAULT 0, sub_until TEXT,
        daily_loss INTEGER DEFAULT 0, daily_loss_date TEXT, tag TEXT);
    CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, description TEXT, price INTEGER, enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, rarity TEXT, sell_price INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS case_items(id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER,
        item_id INTEGER, chance REAL, UNIQUE(case_id,item_id));
    CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        item_id INTEGER, obtained_at TEXT);
    CREATE TABLE IF NOT EXISTS case_opens(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        case_id INTEGER, item_id INTEGER, created_at TEXT);
    CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        kind TEXT, name TEXT, class_name TEXT, phone TEXT, message TEXT,
        status TEXT DEFAULT 'pending', admin_id INTEGER, created_at TEXT, decided_at TEXT);
    CREATE TABLE IF NOT EXISTS promo_codes(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        reward INTEGER, max_uses INTEGER, uses INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS promo_uses(id INTEGER PRIMARY KEY AUTOINCREMENT, promo_id INTEGER,
        user_id INTEGER, used_at TEXT, UNIQUE(promo_id,user_id));
    CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY, role TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS admin_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER,
        action TEXT, target_user_id INTEGER, details TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS achievements(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, description TEXT, reward INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS user_achievements(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        achievement_id INTEGER, obtained_at TEXT, UNIQUE(user_id,achievement_id));
    CREATE TABLE IF NOT EXISTS withdraws(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        amount INTEGER, status TEXT DEFAULT 'pending', admin_id INTEGER, created_at TEXT, decided_at TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
        name TEXT, description TEXT, goal INTEGER, reward INTEGER);
    CREATE TABLE IF NOT EXISTS user_tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        task_id INTEGER, date TEXT, progress INTEGER DEFAULT 0, done INTEGER DEFAULT 0,
        UNIQUE(user_id,task_id,date));
    CREATE TABLE IF NOT EXISTS casino_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        game TEXT, bet INTEGER, win INTEGER, profit INTEGER, created_at TEXT);
    CREATE TABLE IF NOT EXISTS casino_stats(user_id INTEGER PRIMARY KEY, total_bets INTEGER DEFAULT 0,
        total_won INTEGER DEFAULT 0, total_lost INTEGER DEFAULT 0, biggest_win INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS duels(id INTEGER PRIMARY KEY AUTOINCREMENT, challenger_id INTEGER,
        opponent_id INTEGER, amount INTEGER, status TEXT DEFAULT 'pending', winner_id INTEGER,
        created_at TEXT, finished_at TEXT);
    """)
    con.commit()

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
        ("tag", "TEXT"), ("last_case_at", "TEXT"),
    ]:
        if col not in u_cols:
            try: cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            except Exception: pass

    i_cols = _cols("items")
    if "sell_price" not in i_cols:
        try: cur.execute("ALTER TABLE items ADD COLUMN sell_price INTEGER DEFAULT 0")
        except Exception: pass
    if "enabled" not in i_cols:
        try: cur.execute("ALTER TABLE items ADD COLUMN enabled INTEGER DEFAULT 1")
        except Exception: pass

    c_cols = _cols("cases")
    if "enabled" not in c_cols:
        try: cur.execute("ALTER TABLE cases ADD COLUMN enabled INTEGER DEFAULT 1")
        except Exception: pass

    try:
        cur.execute("UPDATE items SET sell_price=50 WHERE (sell_price IS NULL OR sell_price=0) AND rarity='common'")
        cur.execute("UPDATE items SET sell_price=150 WHERE (sell_price IS NULL OR sell_price=0) AND rarity='rare'")
        cur.execute("UPDATE items SET sell_price=500 WHERE (sell_price IS NULL OR sell_price=0) AND rarity='epic'")
        cur.execute("UPDATE items SET sell_price=1500 WHERE (sell_price IS NULL OR sell_price=0) AND rarity='legendary'")
        cur.execute("UPDATE items SET sell_price=5000 WHERE (sell_price IS NULL OR sell_price=0) AND rarity='mythic'")
    except Exception:
        pass
    con.commit()

    cur.execute("INSERT OR IGNORE INTO admins(user_id,role,created_at) VALUES(?,?,?)", (ADMIN_ID,"owner",now()))
    for c,n,d,p in CASES:
        cur.execute("INSERT OR IGNORE INTO cases(code,name,description,price) VALUES(?,?,?,?)", (c,n,d,p))
    for c,n,r,p in ITEMS:
        cur.execute("INSERT OR IGNORE INTO items(code,name,rarity,sell_price) VALUES(?,?,?,?)", (c,n,r,p))
    for cc,drops in DROPS.items():
        cr = cur.execute("SELECT id FROM cases WHERE code=?", (cc,)).fetchone()
        if not cr: continue
        for ic,ch in drops:
            ir = cur.execute("SELECT id FROM items WHERE code=?", (ic,)).fetchone()
            if ir:
                cur.execute("INSERT OR IGNORE INTO case_items(case_id,item_id,chance) VALUES(?,?,?)", (cr["id"],ir["id"],ch))
    for a in [
        ("first_case","🎁 Первый кейс","Открыть кейс",50),
        ("ten_cases","🔥 10 кейсов","10 открытий",150),
        ("hundred_cases","💎 100 кейсов","100 открытий",500),
        ("collector","🎒 Коллекционер","10 предметов",250),
        ("rich","💰 Богатый","5000 SD",500),
        ("casino_king","🎰 Король","100 ставок",1000),
        ("duelist","⚔️ Дуэлянт","5 побед",400),
        ("referrer","🤝 Вербовщик","3 реферала",750),
    ]:
        cur.execute("INSERT OR IGNORE INTO achievements(code,name,description,reward) VALUES(?,?,?,?)", a)
    for t in [
        ("open5","🎁 Открой 5 кейсов","5 кейсов",5,200),
        ("bet3","🎰 3 ставки","3 ставки",3,150),
        ("win1","🏆 Победа","Выиграть",1,250),
        ("daily","📅 Зайти","Заход",1,50),
    ]:
        cur.execute("INSERT OR IGNORE INTO tasks(code,name,description,goal,reward) VALUES(?,?,?,?,?)", t)
    con.commit()
    

    # ========== МИГРАЦИЯ (добавляет недостающие колонки) ==========
    def _cols(table):
        try:
            return {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            return set()

    # users
    u_cols = _cols("users")
    for col, ddl in [
        ("referrer_id", "INTEGER"), ("donated", "INTEGER DEFAULT 0"),
        ("sub_until", "TEXT"), ("daily_streak", "INTEGER DEFAULT 0"),
        ("daily_loss", "INTEGER DEFAULT 0"), ("daily_loss_date", "TEXT"),
        ("tag", "TEXT"), ("last_case_at", "TEXT"),
    ]:
        if col not in u_cols:
            try: cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            except Exception: pass

    # items
    i_cols = _cols("items")
    if "sell_price" not in i_cols:
        try: cur.execute("ALTER TABLE items ADD COLUMN sell_price INTEGER DEFAULT 0")
        except Exception: pass
    if "enabled" not in i_cols:
        try: cur.execute("ALTER TABLE items ADD COLUMN enabled INTEGER DEFAULT 1")
        except Exception: pass

    # cases
    c_cols = _cols("cases")
    if "enabled" not in c_cols:
        try: cur.execute("ALTER TABLE cases ADD COLUMN enabled INTEGER DEFAULT 1")
        except Exception: pass

    # если sell_price пустой — проставим цены
    try:
        cur.execute("UPDATE items SET sell_price = 50 WHERE (sell_price IS NULL OR sell_price = 0) AND rarity='common'")
        cur.execute("UPDATE items SET sell_price = 150 WHERE (sell_price IS NULL OR sell_price = 0) AND rarity='rare'")
        cur.execute("UPDATE items SET sell_price = 500 WHERE (sell_price IS NULL OR sell_price = 0) AND rarity='epic'")
        cur.execute("UPDATE items SET sell_price = 1500 WHERE (sell_price IS NULL OR sell_price = 0) AND rarity='legendary'")
        cur.execute("UPDATE items SET sell_price = 5000 WHERE (sell_price IS NULL OR sell_price = 0) AND rarity='mythic'")
    except Exception:
        pass

    con.commit()
    # ========== КОНЕЦ МИГРАЦИИ ==========

    cur.execute("INSERT OR IGNORE INTO admins(user_id,role,created_at) VALUES(?,?,?)",(ADMIN_ID,"owner",now()))
    for c,n,d,p in CASES: cur.execute("INSERT OR IGNORE INTO cases(code,name,description,price) VALUES(?,?,?,?)",(c,n,d,p))
    for c,n,r,p in ITEMS: cur.execute("INSERT OR IGNORE INTO items(code,name,rarity,sell_price) VALUES(?,?,?,?)",(c,n,r,p))
    for cc,drops in DROPS.items():
        cr = cur.execute("SELECT id FROM cases WHERE code=?",(cc,)).fetchone()
        if not cr: continue
        for ic,ch in drops:
            ir = cur.execute("SELECT id FROM items WHERE code=?",(ic,)).fetchone()
            if ir: cur.execute("INSERT OR IGNORE INTO case_items(case_id,item_id,chance) VALUES(?,?,?)",(cr["id"],ir["id"],ch))
    for a in [("first_case","🎁 Первый кейс","Открыть кейс",50),("ten_cases","🔥 10 кейсов","10 открытий",150),
              ("hundred_cases","💎 100 кейсов","100 открытий",500),("collector","🎒 Коллекционер","10 предметов",250),
              ("rich","💰 Богатый","5000 SD",500),("casino_king","🎰 Король","100 ставок",1000),
              ("duelist","⚔️ Дуэлянт","5 побед",400),("referrer","🤝 Вербовщик","3 реферала",750)]:
        cur.execute("INSERT OR IGNORE INTO achievements(code,name,description,reward) VALUES(?,?,?,?)",a)
    for t in [("open5","🎁 Открой 5 кейсов","5 кейсов",5,200),("bet3","🎰 3 ставки","3 ставки",3,150),
              ("win1","🏆 Победа","Выиграть",1,250),("daily","📅 Зайти","Заход",1,50)]:
        cur.execute("INSERT OR IGNORE INTO tasks(code,name,description,goal,reward) VALUES(?,?,?,?,?)",t)
    con.commit(); con.close()

# ========== ХЕЛПЕРЫ ==========
def ensure(user):
    con = db(); row = con.execute("SELECT * FROM users WHERE user_id=?",(user.id,)).fetchone()
    if row:
        con.execute("UPDATE users SET username=?, first_name=?, last_activity=? WHERE user_id=?",
            (user.username,user.first_name or "",now(),user.id))
    else:
        con.execute("INSERT INTO users(user_id,username,first_name,created_at,last_activity,sd) VALUES(?,?,?,?,?,?)",
            (user.id,user.username,user.first_name or "",now(),now(),get_limit("starter_sd")))
    con.commit()
    row = con.execute("SELECT * FROM users WHERE user_id=?",(user.id,)).fetchone()
    con.close(); return row

def is_admin(uid): return uid == ADMIN_ID
def log_admin(action,target=None,details=""):
    con = db(); con.execute("INSERT INTO admin_logs(admin_id,action,target_user_id,details,created_at) VALUES(?,?,?,?,?)",
        (ADMIN_ID,action,target,details,now())); con.commit(); con.close()
def add_sd(uid,amount):
    con = db(); con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(amount,uid)); con.commit(); con.close()
def take_sd(uid,amount):
    con = db(); r = con.execute("SELECT sd FROM users WHERE user_id=?",(uid,)).fetchone()
    if not r or r["sd"] < amount: con.close(); return False
    con.execute("UPDATE users SET sd=sd-? WHERE user_id=?",(amount,uid)); con.commit(); con.close(); return True
def get_user(uid):
    con = db(); r = con.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone(); con.close(); return r
def has_sub(user):
    if not user: return False
    try: return ("sub_until" in user.keys() and user["sub_until"] and datetime.fromisoformat(user["sub_until"]) > datetime.now(timezone.utc))
    except Exception: return False
def badge(user): return SUB_BONUS["badge"]+" " if has_sub(user) else ""

# ========== КОНЕЦ ЧАСТИ 1/4 ==========
# ========== КЛАВИАТУРЫ ==========
def home_kb(user=None):
    b = InlineKeyboardBuilder()
    for t,d in [("🎮 Кейсы","play"),("🎰 Казино","casino"),("👤 Профиль","profile"),
        ("💰 Баланс","balance"),("⭐ Пополнить","topup"),("🎬 Медиа","media"),
        ("🎒 Коллекция","collection"),("🏆 Рейтинг","rating"),("🎟 Промокод","promo"),
        ("🏅 Достижения","achievements"),("📋 Задания","tasks"),("⚔️ Дуэли","duels"),
        ("👥 Рефералы","ref"),("💎 CosDrop+","subscribe"),("📝 Заявки","apps"),
        ("ℹ️ О боте","about")]:
        b.button(text=t,callback_data=d)
    b.adjust(2,2,2,2,2,2,2,1,1); return b.as_markup()

def back(cb="home"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад",callback_data=cb)]])

def admin_kb():
    b = InlineKeyboardBuilder()
    for t,d in [("📊 Статистика","adm_stats"),("👥 Юзеры","adm_users"),
        ("🔎 Найти","adm_search"),("🎁 +SD","adm_give"),("➖ -SD","adm_take"),
        ("🚫 Блок","adm_blocks"),("🎟 Промо","adm_promo"),("📦 Кейсы","adm_cases"),
        ("💎 Предметы","adm_items"),("📝 Заявки","adm_apps"),("💸 Выводы","adm_withdraws"),
        ("📢 Рассылка","adm_broadcast"),("📜 Логи","adm_logs"),("💾 Бэкап","adm_backup"),
        ("⚙️ Лимиты","a3_root"),("◀️ В админку v2","a2_root")]:
        b.button(text=t,callback_data=d)
    b.adjust(2,2,2,2,2,2,2,2,1); return b.as_markup()

def casino_menu():
    b = InlineKeyboardBuilder()
    for t,d in [("🎰 Слоты","cas_slots"),("🎲 Кости","cas_dice"),("🪙 Монетка","cas_coin"),
        ("🎡 Рулетка","cas_roulette"),("💣 Мины","cas_mines"),("📊 Статистика","cas_stats"),
        ("🏆 Топ","cas_top"),("◀️ Назад","home")]:
        b.button(text=t,callback_data=d)
    b.adjust(2,2,2,1,1); return b.as_markup()

def bet_kb(game):
    mn = get_limit("casino_min"); mx = get_limit("casino_max")
    steps = [10,25,50,100,250,500,1000,2500,5000,10000,25000,50000,100000,250000,
             500000,1000000,2500000,5000000,8000000]
    opts = [v for v in steps if mn <= v <= mx]
    if not opts: opts = [mn, mx]
    elif opts[-1] != mx: opts.append(mx)
    if len(opts) > 6:
        idxs = [0, len(opts)//5, 2*len(opts)//5, 3*len(opts)//5, 4*len(opts)//5, len(opts)-1]
        opts = sorted(set(opts[i] for i in idxs))
    b = InlineKeyboardBuilder()
    for v in opts: b.button(text=f"{v}",callback_data=f"bet:{game}:{v}")
    b.button(text="✏️ Своя",callback_data=f"bet:{game}:custom")
    b.button(text="◀️ Назад",callback_data="casino")
    b.adjust(3,3,1,1); return b.as_markup()

# ========== START / HOME ==========
@dp.message(Command("start"))
async def start(message: Message):
    args = message.text.split(maxsplit=1)
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if not get_limit("registration_open"):
        return await message.answer("🚫 Регистрация временно закрыта.")
    user = ensure(message.from_user)
    if user["blocked"]:
        return await message.answer("🚫 <b>Аккаунт заблокирован.</b>")
    if ref and ref != message.from_user.id and not user["referrer_id"] and get_limit("referral_enabled"):
        con = db()
        if con.execute("SELECT user_id FROM users WHERE user_id=?",(ref,)).fetchone():
            con.execute("UPDATE users SET referrer_id=? WHERE user_id=?",(ref,message.from_user.id))
            con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(get_limit("ref_invite"),ref)); con.commit()
            try: await bot.send_message(ref,f"🤝 Новый реферал! +{get_limit('ref_invite')} SD")
            except Exception: pass
        con.close()
    if os.path.isfile(IMAGE_FILE) and os.path.getsize(IMAGE_FILE) > 0:
        try: await message.answer_photo(FSInputFile(IMAGE_FILE),caption="✨ <b>COS-DROP</b>")
        except Exception: pass
    await message.answer(
        f"🎁 <b>COS-DROP</b>\n\n{badge(user)}💰 SD: <b>{user['sd']}</b>\n"
        f"⭐ Уровень: <b>{user['level']}</b>\n✨ XP: <b>{user['xp']}</b>\n\nВыбери раздел:",
        reply_markup=home_kb(user))
    await bump_task(message.from_user.id,"daily",1)

@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    user = ensure(callback.from_user)
    if user["blocked"]: return await callback.answer("Заблокирован.",show_alert=True)
    await callback.message.edit_text(
        f"🎁 <b>COS-DROP</b>\n\n{badge(user)}💰 SD: <b>{user['sd']}</b>\n"
        f"⭐ Уровень: <b>{user['level']}</b>\n\nВыбери раздел:",reply_markup=home_kb(user))
    await callback.answer()

# ========== CASES ==========
@dp.callback_query(F.data == "play")
async def play(callback: CallbackQuery):
    con = db(); rows = con.execute("SELECT * FROM cases WHERE enabled=1 ORDER BY id").fetchall(); con.close()
    b = InlineKeyboardBuilder()
    for r in rows: b.button(text=f"{r['name']} · {r['price']} SD",callback_data=f"case:{r['id']}")
    b.button(text="◀️ Назад",callback_data="home"); b.adjust(1)
    await callback.message.edit_text("🎮 <b>КЕЙСЫ</b>",reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data.startswith("case:"))
async def case_info(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    con = db(); row = con.execute("SELECT * FROM cases WHERE id=? AND enabled=1",(cid,)).fetchone(); con.close()
    if not row: return await callback.answer("Недоступен.",show_alert=True)
    b = InlineKeyboardBuilder()
    b.button(text="🎁 Открыть",callback_data=f"open:{cid}")
    b.button(text="🎁 ×5 (-10%)",callback_data=f"open5:{cid}")
    b.button(text="◀️ Назад",callback_data="play"); b.adjust(1)
    await callback.message.edit_text(
        f"📦 <b>{escape(row['name'])}</b>\n\n{escape(row['description'])}\n\n💰 <b>{row['price']} SD</b>",
        reply_markup=b.as_markup()); await callback.answer()

async def _open_case(uid,cid,count=1):
    con = db()
    cr = con.execute("SELECT * FROM cases WHERE id=? AND enabled=1",(cid,)).fetchone()
    if not cr: con.close(); return None,"Недоступен"
    price = int(cr["price"]*(5*0.9 if count==5 else 1))
    u = con.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    if not u or u["sd"] < price: con.close(); return None,"Недостаточно SD"
    if count == 1 and u["last_case_at"]:
        try:
            if (datetime.now(timezone.utc)-datetime.fromisoformat(u["last_case_at"])).total_seconds() < get_limit("case_cooldown"):
                con.close(); return None,"Подожди пару секунд"
        except Exception: pass
    items = con.execute("""SELECT i.*, ci.chance FROM case_items ci JOIN items i ON i.id=ci.item_id
        WHERE ci.case_id=? AND i.enabled=1""",(cid,)).fetchall()
    if not items: con.close(); return None,"Пусто"
    res = []
    for _ in range(count):
        p = random.choices(items,weights=[float(x["chance"]) for x in items],k=1)[0]; res.append(p)
        con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)",(uid,p["id"],now()))
        con.execute("INSERT INTO case_opens(user_id,case_id,item_id,created_at) VALUES(?,?,?,?)",(uid,cid,p["id"],now()))
    xp = int(10*count*(SUB_BONUS["xp_mult"] if has_sub(u) else 1))
    con.execute("UPDATE users SET sd=sd-?, xp=xp+?, last_case_at=?, last_activity=? WHERE user_id=?",
        (price,xp,now(),now(),uid))
    con.commit(); con.close(); return res,None

@dp.callback_query(F.data.startswith("open:"))
async def open_case(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    u = ensure(callback.from_user)
    if u["blocked"]: return await callback.answer("Заблокирован.",show_alert=True)
    res,err = await _open_case(callback.from_user.id,cid,1)
    if err: return await callback.answer(err,show_alert=True)
    s = res[0]
    await check_achievements(callback.from_user.id); await bump_task(callback.from_user.id,"open5",1)
    await callback.message.edit_text(
        f"✨ <b>ОТКРЫТИЕ</b>\n\n{RARITY.get(s['rarity'],'⚪')}\n\n<b>{escape(s['name'])}</b>\n\n🎒 +10 XP",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Ещё",callback_data="play")],
            [InlineKeyboardButton(text="🎒 Коллекция",callback_data="collection")],
            [InlineKeyboardButton(text="🏠 Меню",callback_data="home")]]))
    await callback.answer()

@dp.callback_query(F.data.startswith("open5:"))
async def open_case_5(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    u = ensure(callback.from_user)
    if u["blocked"]: return await callback.answer("Заблокирован.",show_alert=True)
    res,err = await _open_case(callback.from_user.id,cid,5)
    if err: return await callback.answer(err,show_alert=True)
    text = "✨ <b>×5</b>\n\n"+"\n".join(f"{RARITY.get(r['rarity'],'⚪')} <b>{escape(r['name'])}</b>" for r in res)
    await check_achievements(callback.from_user.id); await bump_task(callback.from_user.id,"open5",5)
    await callback.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Ещё",callback_data="play")],
        [InlineKeyboardButton(text="🏠 Меню",callback_data="home")]]))
    await callback.answer()

# ========== COLLECTION ==========
@dp.callback_query(F.data == "collection")
async def collection(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT i.id, i.name, i.rarity, i.sell_price, COUNT(*) n
        FROM inventory inv JOIN items i ON i.id=inv.item_id WHERE inv.user_id=?
        GROUP BY inv.item_id ORDER BY i.rarity, i.name""",(callback.from_user.id,)).fetchall()
    con.close()
    if not rows: return await callback.message.edit_text("🎒 <b>КОЛЛЕКЦИЯ</b>\n\nПусто.",reply_markup=back())
    b = InlineKeyboardBuilder()
    for r in rows: b.button(text=f"{RARITY.get(r['rarity'],'⚪')} {r['name']} ×{r['n']}",callback_data=f"item:{r['id']}")
    b.button(text="◀️ Назад",callback_data="home"); b.adjust(1)
    await callback.message.edit_text("🎒 <b>КОЛЛЕКЦИЯ</b>",reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data.startswith("item:"))
async def item_menu(callback: CallbackQuery):
    iid = int(callback.data.split(":")[1])
    con = db()
    row = con.execute("SELECT * FROM items WHERE id=?",(iid,)).fetchone()
    cnt = con.execute("SELECT COUNT(*) n FROM inventory WHERE user_id=? AND item_id=?",(callback.from_user.id,iid)).fetchone()["n"]
    con.close()
    if not row: return await callback.answer("Нет.",show_alert=True)
    comm = get_limit("sell_commission"); st = int(row["sell_price"]*cnt*(1-comm))
    b = InlineKeyboardBuilder()
    b.button(text=f"💰 Продать 1 ({row['sell_price']} SD)",callback_data=f"sell:1:{iid}")
    b.button(text=f"💰 Продать всё ({st} SD)",callback_data=f"sell:all:{iid}")
    b.button(text="⬆️ Апгрейд ×3",callback_data=f"upgrade:{iid}")
    b.button(text="◀️ Назад",callback_data="collection"); b.adjust(1)
    await callback.message.edit_text(
        f"{RARITY.get(row['rarity'],'⚪')} <b>{escape(row['name'])}</b>\n\nВ инвентаре: <b>{cnt}</b>\n"
        f"Цена за 1: <b>{row['sell_price']} SD</b>\nКомиссия: {int(comm*100)}%",
        reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data.startswith("sell:"))
async def sell_item(callback: CallbackQuery):
    _,mode,iid_s = callback.data.split(":"); iid = int(iid_s)
    con = db()
    row = con.execute("SELECT * FROM items WHERE id=?",(iid,)).fetchone()
    inv = con.execute("SELECT id FROM inventory WHERE user_id=? AND item_id=? LIMIT 100",(callback.from_user.id,iid)).fetchall()
    con.close()
    if not row or not inv: return await callback.answer("Нет.",show_alert=True)
    cnt = len(inv) if mode == "all" else 1
    total = int(row["sell_price"]*cnt*(1-get_limit("sell_commission")))
    add_sd(callback.from_user.id,total)
    ids = [x["id"] for x in inv[:cnt]]
    if ids:
        con = db(); q = ",".join("?"*len(ids))
        con.execute(f"DELETE FROM inventory WHERE id IN ({q})",ids); con.commit(); con.close()
    await callback.answer(f"✅ +{total} SD",show_alert=True); await item_menu(callback)

@dp.callback_query(F.data.startswith("upgrade:"))
async def upgrade_item(callback: CallbackQuery):
    iid = int(callback.data.split(":")[1])
    con = db(); row = con.execute("SELECT * FROM items WHERE id=?",(iid,)).fetchone()
    if not row: con.close(); return await callback.answer("Нет.",show_alert=True)
    idx = RARITY_ORDER.index(row["rarity"]) if row["rarity"] in RARITY_ORDER else 0
    if idx >= len(RARITY_ORDER)-1: con.close(); return await callback.answer("Макс.",show_alert=True)
    next_r = RARITY_ORDER[idx+1]
    cands = con.execute("SELECT * FROM items WHERE rarity=? AND enabled=1",(next_r,)).fetchall()
    if not cands: con.close(); return await callback.answer("Нет выше.",show_alert=True)
    inv = con.execute("SELECT id FROM inventory WHERE user_id=? AND item_id=? LIMIT 3",(callback.from_user.id,iid)).fetchall()
    if len(inv) < 3: con.close(); return await callback.answer("Нужно 3 шт.",show_alert=True)
    ids = [x["id"] for x in inv]; q = ",".join("?"*len(ids))
    con.execute(f"DELETE FROM inventory WHERE id IN ({q})",ids)
    if random.random() < get_limit("upgrade_chance"):
        new = random.choice(cands)
        con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)",(callback.from_user.id,new["id"],now()))
        txt = f"✅ {RARITY.get(new['rarity'])} <b>{escape(new['name'])}</b>"
    else: txt = "❌ Провал."
    con.commit(); con.close(); await check_achievements(callback.from_user.id)
    await callback.answer(txt,show_alert=True); await collection(callback)

# ========== PROFILE / BALANCE / DAILY ==========
@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    u = ensure(callback.from_user); con = db()
    inv = con.execute("SELECT COUNT(*) n FROM inventory WHERE user_id=?",(u["user_id"],)).fetchone()["n"]
    ops = con.execute("SELECT COUNT(*) n FROM case_opens WHERE user_id=?",(u["user_id"],)).fetchone()["n"]
    achs = con.execute("SELECT COUNT(*) n FROM user_achievements WHERE user_id=?",(u["user_id"],)).fetchone()["n"]
    refs = con.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?",(u["user_id"],)).fetchone()["n"]
    con.close()
    sub = "✅" if has_sub(u) else "❌"
    await callback.message.edit_text(
        f"👤 <b>ПРОФИЛЬ</b>\n\nID: <code>{u['user_id']}</code>\n@{escape(u['username'] or 'нет')}\n\n"
        f"{badge(u)}💰 SD: <b>{u['sd']}</b>\n⭐ Lv: <b>{u['level']}</b> · ✨ XP: <b>{u['xp']}</b>\n\n"
        f"🎁 Кейсов: <b>{ops}</b>\n🎒 Предметов: <b>{inv}</b>\n🏅 Достижений: <b>{achs}</b>\n"
        f"👥 Рефералов: <b>{refs}</b>\n💎 CosDrop+: <b>{sub}</b>",reply_markup=back())
    await callback.answer()

@dp.callback_query(F.data == "balance")
async def balance(callback: CallbackQuery):
    u = ensure(callback.from_user)
    await callback.message.edit_text(
        f"💰 <b>БАЛАНС</b>\n\nТвой баланс: <b>{u['sd']} SD</b>\n\n🎁 Daily: <b>+{get_limit('daily_base')} SD</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Бонус",callback_data="daily")],
            [InlineKeyboardButton(text="⭐ Пополнить",callback_data="topup")],
            [InlineKeyboardButton(text="💸 Вывод",callback_data="withdraw")],
            [InlineKeyboardButton(text="◀️ Назад",callback_data="home")]]))
    await callback.answer()

@dp.callback_query(F.data == "daily")
async def daily(callback: CallbackQuery):
    con = db(); row = con.execute("SELECT * FROM users WHERE user_id=?",(callback.from_user.id,)).fetchone(); t = today()
    if row["daily_claim"] == t: con.close(); return await callback.answer("Уже получен.",show_alert=True)
    streak = row["daily_streak"] or 0
    if row["daily_claim"]:
        try:
            last = datetime.fromisoformat(row["daily_claim"]).date()
            if (datetime.now(timezone.utc).date()-last).days != 1: streak = 0
        except Exception: streak = 0
    streak += 1
    reward = get_limit("daily_base")
    if streak >= 30: reward += get_limit("daily_streak_30")
    elif streak >= 7: reward += get_limit("daily_streak_7")
    if has_sub(row): reward *= SUB_BONUS["daily_mult"]
    con.execute("UPDATE users SET sd=sd+?, daily_claim=?, daily_streak=?, xp=xp+5, last_activity=? WHERE user_id=?",
        (reward,t,streak,now(),callback.from_user.id)); con.commit(); con.close()
    await callback.answer(f"🎁 +{reward} SD · Стрик: {streak}",show_alert=True); await balance(callback)

# ========== TOPUP / STARS / SUB ==========
@dp.callback_query(F.data == "topup")
async def topup(callback: CallbackQuery):
    packs = [(100,get_limit("pack_100")),(400,get_limit("pack_400")),
             (1000,get_limit("pack_1000")),(1500,get_limit("pack_1500"))]
    b = InlineKeyboardBuilder()
    for sd,stars in packs: b.button(text=f"⭐ {sd} SD — {stars} ⭐",callback_data=f"buy:{sd}:{stars}")
    b.button(text="◀️ Назад",callback_data="home"); b.adjust(1)
    await callback.message.edit_text("⭐ <b>ПОПОЛНЕНИЕ</b>",reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy_pack(callback: CallbackQuery):
    _,sd_s,stars_s = callback.data.split(":"); sd,stars = int(sd_s),int(stars_s)
    await bot.send_invoice(chat_id=callback.from_user.id,title=f"{sd} SD",description=f"+{sd} SD",
        payload=f"sd_{sd}",provider_token="",currency="XTR",
        prices=[LabeledPrice(label=f"{sd} SD",amount=stars)])
    await callback.answer()

@dp.callback_query(F.data == "sub_buy")
async def sub_buy(callback: CallbackQuery):
    price = get_limit("sub_price"); days = get_limit("sub_days")
    await bot.send_invoice(chat_id=callback.from_user.id,title="CosDrop+",
        description=f"Подписка {days} дней",payload=f"sub_{days}",provider_token="",currency="XTR",
        prices=[LabeledPrice(label="CosDrop+",amount=price)])
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.successful_payment)
async def payment_success(message: Message):
    payload = message.successful_payment.invoice_payload; uid = message.from_user.id
    if payload.startswith("sub_"):
        try: days = int(payload.split("_")[1])
        except Exception: days = get_limit("sub_days")
        until = datetime.now(timezone.utc)+timedelta(days=days)
        con = db(); con.execute("UPDATE users SET sub_until=? WHERE user_id=?",(until.isoformat(),uid)); con.commit(); con.close()
        return await message.answer(f"💎 CosDrop+ до {until.date().isoformat()}!",reply_markup=home_kb())
    try: amount_sd = int(payload.split("_")[1])
    except Exception: amount_sd = 100
    add_sd(uid,amount_sd); user = get_user(uid)
    if user and user["referrer_id"]:
        add_sd(user["referrer_id"],get_limit("ref_donate"))
        try: await bot.send_message(user["referrer_id"],f"💸 Реферал купил Stars! +{get_limit('ref_donate')} SD")
        except Exception: pass
    con = db(); con.execute("UPDATE users SET donated=donated+1 WHERE user_id=?",(uid,)); con.commit(); con.close()
    await message.answer(f"✅ +{amount_sd} SD",reply_markup=home_kb()); await check_achievements(uid)

@dp.callback_query(F.data == "subscribe")
async def subscribe(callback: CallbackQuery):
    u = ensure(callback.from_user)
    status = f"✅ до {u['sub_until'][:10]}" if has_sub(u) else "❌ нет"
    price = get_limit("sub_price"); days = get_limit("sub_days")
    b = InlineKeyboardBuilder()
    b.button(text=f"💎 Купить ({price} ⭐ / {days} дн.)",callback_data="sub_buy")
    b.button(text="◀️ Назад",callback_data="home"); b.adjust(1)
    await callback.message.edit_text(
        f"💎 <b>CosDrop+</b>\n\nСтатус: <b>{status}</b>\n\n"
        f"• 💰 ×{SUB_BONUS['daily_mult']} к daily\n• ✨ +{int((SUB_BONUS['xp_mult']-1)*100)}% XP\n"
        f"• {SUB_BONUS['badge']} значок\n\nЦена: <b>{price} ⭐ / {days} дней</b>",reply_markup=b.as_markup())
    await callback.answer()

# ========== КОНЕЦ ЧАСТИ 2/4 ==========
# ========== CASINO ==========
@dp.callback_query(F.data == "casino")
async def casino_main(callback: CallbackQuery):
    u = ensure(callback.from_user)
    if u["blocked"]: return await callback.answer("Заблокирован.",show_alert=True)
    if not get_limit("casino_enabled"): return await callback.answer("Казино выключено.",show_alert=True)
    await callback.message.edit_text(f"🎰 <b>COS-CASINO</b>\n\n💰 Баланс: <b>{u['sd']} SD</b>",reply_markup=casino_menu())
    await callback.answer()

def _log_bet(uid,game,bet,win):
    profit = win-bet; con = db()
    con.execute("INSERT INTO casino_bets(user_id,game,bet,win,profit,created_at) VALUES(?,?,?,?,?,?)",(uid,game,bet,win,profit,now()))
    con.execute("""INSERT INTO casino_stats(user_id,total_bets,total_won,total_lost,biggest_win) VALUES(?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET total_bets=total_bets+1, total_won=total_won+excluded.total_won,
        total_lost=total_lost+excluded.total_lost, biggest_win=MAX(biggest_win,excluded.biggest_win)""",
        (uid,1,win if profit>0 else 0,bet if profit<0 else 0,win if profit>0 else 0))
    con.commit(); con.close()

def _check_loss_limit(uid,bet):
    con = db(); r = con.execute("SELECT daily_loss, daily_loss_date FROM users WHERE user_id=?",(uid,)).fetchone(); con.close()
    if not r or r["daily_loss_date"] != today(): return False
    limit = get_limit("casino_loss_limit")
    if limit <= 0: return False
    return (r["daily_loss"] or 0)+bet > limit

def _apply_loss(uid,amount):
    con = db(); r = con.execute("SELECT daily_loss, daily_loss_date FROM users WHERE user_id=?",(uid,)).fetchone()
    nl = (r["daily_loss"] or 0)+amount if r and r["daily_loss_date"]==today() else amount
    con.execute("UPDATE users SET daily_loss=?, daily_loss_date=? WHERE user_id=?",(nl,today(),uid)); con.commit(); con.close()

@dp.callback_query(F.data == "cas_slots")
async def cas_slots(callback: CallbackQuery):
    await callback.message.edit_text("🎰 <b>СЛОТЫ</b>\n\n🍒×3 · 🍋×4 · 🔔×6\n💎×12 · 7️⃣×25 · ⭐×50",reply_markup=bet_kb("slots")); await callback.answer()

@dp.callback_query(F.data == "cas_dice")
async def cas_dice(callback: CallbackQuery):
    await callback.message.edit_text("🎲 <b>КОСТИ</b>\n\n<7 ×2 · >7 ×2 · =7 ×5",reply_markup=bet_kb("dice")); await callback.answer()

@dp.callback_query(F.data == "cas_coin")
async def cas_coin(callback: CallbackQuery):
    await callback.message.edit_text("🪙 <b>МОНЕТКА</b> ×2",reply_markup=bet_kb("coin")); await callback.answer()

@dp.callback_query(F.data == "cas_roulette")
async def cas_roulette(callback: CallbackQuery):
    await callback.message.edit_text("🎡 <b>РУЛЕТКА</b>\n\n🔴 ×2 · ⚫ ×2 · 🟢 ×14",reply_markup=bet_kb("roulette")); await callback.answer()

@dp.callback_query(F.data == "cas_mines")
async def cas_mines(callback: CallbackQuery):
    await callback.message.edit_text("💣 <b>МИНЫ</b>",reply_markup=bet_kb("mines")); await callback.answer()

@dp.callback_query(F.data.startswith("bet:"))
async def bet_select(callback: CallbackQuery, state: FSMContext):
    _,game,val = callback.data.split(":")
    if val == "custom":
        await state.set_state(CasinoBet.amount); await state.update_data(game=game)
        await callback.message.edit_text(f"✏️ Сумма ({get_limit('casino_min')}-{get_limit('casino_max')}):",reply_markup=back("casino"))
        return await callback.answer()
    await _cas_continue(callback,game,int(val))

@dp.message(StateFilter(CasinoBet.amount))
async def bet_custom(message: Message, state: FSMContext):
    try: bet = int((message.text or "").strip())
    except Exception: return await message.answer("❌ Число.")
    if not (get_limit("casino_min") <= bet <= get_limit("casino_max")):
        return await message.answer(f"❌ {get_limit('casino_min')}-{get_limit('casino_max')}")
    data = await state.get_data(); game = data.get("game"); await state.clear()
    if game == "slots":
        return await _slots_spin(message,message.from_user.id,bet)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️",callback_data="casino")]])
    await message.answer(f"Игра: {game} · {bet} SD",reply_markup=kb)

async def _cas_continue(callback,game,bet):
    if game == "dice":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Меньше 7 ×2",callback_data=f"dice:lt:{bet}")],
            [InlineKeyboardButton(text="Больше 7 ×2",callback_data=f"dice:gt:{bet}")],
            [InlineKeyboardButton(text="Ровно 7 ×5",callback_data=f"dice:eq:{bet}")],
            [InlineKeyboardButton(text="◀️",callback_data="casino")]])
        await callback.message.edit_text(f"🎲 Ставка: {bet} SD",reply_markup=kb)
    elif game == "coin":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Орёл",callback_data=f"coin:o:{bet}")],
            [InlineKeyboardButton(text="🪙 Решка",callback_data=f"coin:r:{bet}")],
            [InlineKeyboardButton(text="◀️",callback_data="casino")]])
        await callback.message.edit_text(f"🪙 Ставка: {bet} SD",reply_markup=kb)
    elif game == "roulette":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔴 ×2",callback_data=f"rl:red:{bet}")],
            [InlineKeyboardButton(text="⚫ ×2",callback_data=f"rl:black:{bet}")],
            [InlineKeyboardButton(text="🟢 ×14",callback_data=f"rl:green:{bet}")],
            [InlineKeyboardButton(text="◀️",callback_data="casino")]])
        await callback.message.edit_text(f"🎡 Ставка: {bet} SD",reply_markup=kb)
    elif game == "mines":
        b = InlineKeyboardBuilder()
        for m in [1,3,5,10,24]: b.button(text=f"💣 {m}",callback_data=f"mines:{bet}:{m}")
        b.button(text="◀️",callback_data="casino"); b.adjust(3,2,1)
        await callback.message.edit_text(f"💣 Ставка: {bet} SD",reply_markup=b.as_markup())
    elif game == "slots":
        await _slots_spin(callback.message,callback.from_user.id,bet)
    await callback.answer()

async def _slots_spin(message,uid,bet):
    if not take_sd(uid,bet):
        try: return await message.edit_text("❌ Недостаточно SD.",reply_markup=back("casino"))
        except Exception: return await bot.send_message(uid,"❌ Недостаточно SD.")
    frames = [[random.choice(SLOT_SYMBOLS) for _ in range(3)] for _ in range(8)]
    final = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    if random.random() < 0.20:
        s = random.choice(SLOT_SYMBOLS); final = [s,s,s]
    frames.append(final)
    mult = SLOT_PAYOUTS.get(tuple(final),0); win = min(bet*mult,get_limit("casino_max_win"))
    if win > 0: add_sd(uid,win); _log_bet(uid,"slots",bet,win)
    else: _log_bet(uid,"slots",bet,0); _apply_loss(uid,bet)
    for f in frames:
        try: await message.edit_text("🎰 <b>СЛОТЫ</b>\n\n"+" | ".join(f)+f"\n\nСтавка: {bet} SD")
        except Exception: pass
        await asyncio.sleep(0.35)
    result = "🎰 <b>СЛОТЫ</b>\n\n"+" | ".join(final)+"\n\n"
    result += f"🎉 +{win} SD (×{mult})" if win > 0 else f"❌ -{bet} SD"
    try: await message.edit_text(result,reply_markup=back("casino"))
    except Exception: await bot.send_message(uid,result,reply_markup=back("casino"))
    await check_achievements(uid); await bump_task(uid,"bet3",1)
    if win > bet: await bump_task(uid,"win1",1)

@dp.callback_query(F.data.startswith("dice:"))
async def dice_play(callback: CallbackQuery):
    _,ch,bet_s = callback.data.split(":"); bet = int(bet_s)
    if _check_loss_limit(callback.from_user.id,bet): return await callback.answer("Дневной лимит проигрыша.",show_alert=True)
    if not take_sd(callback.from_user.id,bet): return await callback.answer("Мало SD.",show_alert=True)
    a,b = random.randint(1,6),random.randint(1,6); total = a+b; win = 0
    if ch == "lt" and total < 7: win = bet*2
    elif ch == "gt" and total > 7: win = bet*2
    elif ch == "eq" and total == 7: win = bet*5
    win = min(win,get_limit("casino_max_win"))
    if win > 0: add_sd(callback.from_user.id,win); _log_bet(callback.from_user.id,"dice",bet,win)
    else: _log_bet(callback.from_user.id,"dice",bet,0); _apply_loss(callback.from_user.id,bet)
    await check_achievements(callback.from_user.id); await bump_task(callback.from_user.id,"bet3",1)
    if win > bet: await bump_task(callback.from_user.id,"win1",1)
    txt = f"🎲 <b>{a}+{b}={total}</b>\n\n"+(f"🎉 +{win} SD" if win > 0 else f"❌ -{bet} SD")
    await callback.message.edit_text(txt,reply_markup=back("casino")); await callback.answer()

@dp.callback_query(F.data.startswith("coin:"))
async def coin_play(callback: CallbackQuery):
    _,ch,bet_s = callback.data.split(":"); bet = int(bet_s)
    if _check_loss_limit(callback.from_user.id,bet): return await callback.answer("Лимит.",show_alert=True)
    if not take_sd(callback.from_user.id,bet): return await callback.answer("Мало SD.",show_alert=True)
    res = random.choice(["o","r"]); win = bet*2 if res == ch else 0
    if win > 0: add_sd(callback.from_user.id,win); _log_bet(callback.from_user.id,"coin",bet,win)
    else: _log_bet(callback.from_user.id,"coin",bet,0); _apply_loss(callback.from_user.id,bet)
    await check_achievements(callback.from_user.id); await bump_task(callback.from_user.id,"bet3",1)
    if win > bet: await bump_task(callback.from_user.id,"win1",1)
    txt = ("🪙 Орёл" if res == "o" else "🪙 Решка")+"\n\n"
    txt += f"🎉 +{win} SD" if win > 0 else f"❌ -{bet} SD"
    await callback.message.edit_text(txt,reply_markup=back("casino")); await callback.answer()

@dp.callback_query(F.data.startswith("rl:"))
async def roulette_play(callback: CallbackQuery):
    _,ch,bet_s = callback.data.split(":"); bet = int(bet_s)
    if _check_loss_limit(callback.from_user.id,bet): return await callback.answer("Лимит.",show_alert=True)
    if not take_sd(callback.from_user.id,bet): return await callback.answer("Мало SD.",show_alert=True)
    reds = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    num = random.randint(0,36)
    color = "green" if num == 0 else ("red" if num in reds else "black")
    win = 0
    if ch == color: win = bet*(14 if color == "green" else 2)
    win = min(win,get_limit("casino_max_win"))
    if win > 0: add_sd(callback.from_user.id,win); _log_bet(callback.from_user.id,"roulette",bet,win)
    else: _log_bet(callback.from_user.id,"roulette",bet,0); _apply_loss(callback.from_user.id,bet)
    await check_achievements(callback.from_user.id); await bump_task(callback.from_user.id,"bet3",1)
    if win > bet: await bump_task(callback.from_user.id,"win1",1)
    em = {"red":"🔴","black":"⚫","green":"🟢"}[color]
    txt = f"🎡 Выпало: <b>{num}</b> {em}\n\n"+(f"🎉 +{win} SD" if win > 0 else f"❌ -{bet} SD")
    await callback.message.edit_text(txt,reply_markup=back("casino")); await callback.answer()

@dp.callback_query(F.data.startswith("mines:"))
async def mines_start(callback: CallbackQuery):
    _,bet_s,m_s = callback.data.split(":"); bet,mines = int(bet_s),int(m_s)
    if _check_loss_limit(callback.from_user.id,bet): return await callback.answer("Лимит.",show_alert=True)
    if not take_sd(callback.from_user.id,bet): return await callback.answer("Мало SD.",show_alert=True)
    safe = 25-mines; mult_per = round((25/max(safe,1))*0.95,2)
    con = db()
    con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
        (f"mines_{callback.from_user.id}",json.dumps({"bet":bet,"mines":mines,"opened":[],"safe":safe,
            "mult_per":mult_per,"picked":sorted(random.sample(range(25),mines))})))
    con.commit(); con.close()
    await _mines_render(callback.message,callback.from_user.id,edit=True); await callback.answer()

async def _mines_render(message,uid,edit=False):
    con = db(); row = con.execute("SELECT value FROM settings WHERE key=?",(f"mines_{uid}",)).fetchone(); con.close()
    if not row: return
    st = json.loads(row["value"]); opened = st["opened"]
    mult = round(st["mult_per"]**len(opened),2) if opened else 1.0
    potential = int(st["bet"]*mult)
    b = InlineKeyboardBuilder()
    for i in range(25): b.button(text="💎" if i in opened else "⬜",callback_data=f"mine_open:{i}")
    b.button(text=f"💰 Забрать {potential} SD",callback_data="mine_take"); b.adjust(5,5,5,5,5,1)
    txt = (f"💣 <b>МИНЫ</b>\n\nМин: {st['mines']}\nОткрыто: {len(opened)}\n×{mult}\nЗабрать: <b>{potential} SD</b>")
    if edit:
        try: await message.edit_text(txt,reply_markup=b.as_markup())
        except Exception: await bot.send_message(uid,txt,reply_markup=b.as_markup())
    else: await bot.send_message(uid,txt,reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("mine_open:"))
async def mine_open(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1]); uid = callback.from_user.id
    con = db(); row = con.execute("SELECT value FROM settings WHERE key=?",(f"mines_{uid}",)).fetchone()
    if not row: con.close(); return await callback.answer("Нет игры.",show_alert=True)
    st = json.loads(row["value"])
    if idx in st["opened"]: con.close(); return await callback.answer("Уже открыто.")
    if idx in st["picked"]:
        con.execute("DELETE FROM settings WHERE key=?",(f"mines_{uid}",)); con.commit(); con.close()
        _log_bet(uid,"mines",st["bet"],0); _apply_loss(uid,st["bet"])
        await callback.message.edit_text(f"💥 МИНА! -{st['bet']} SD",reply_markup=back("casino"))
        return await callback.answer()
    st["opened"].append(idx)
    con.execute("UPDATE settings SET value=? WHERE key=?",(json.dumps(st),f"mines_{uid}")); con.commit(); con.close()
    await _mines_render(callback.message,uid,edit=True); await callback.answer()

@dp.callback_query(F.data == "mine_take")
async def mine_take(callback: CallbackQuery):
    uid = callback.from_user.id
    con = db(); row = con.execute("SELECT value FROM settings WHERE key=?",(f"mines_{uid}",)).fetchone()
    if not row: con.close(); return await callback.answer("Нет игры.",show_alert=True)
    st = json.loads(row["value"]); con.execute("DELETE FROM settings WHERE key=?",(f"mines_{uid}",)); con.commit(); con.close()
    if not st["opened"]: return await callback.answer("Открой клетку.",show_alert=True)
    mult = round(st["mult_per"]**len(st["opened"]),2); win = min(int(st["bet"]*mult),get_limit("casino_max_win"))
    add_sd(uid,win); _log_bet(uid,"mines",st["bet"],win)
    await check_achievements(uid); await bump_task(uid,"bet3",1)
    if win > st["bet"]: await bump_task(uid,"win1",1)
    await callback.message.edit_text(f"💰 +{win} SD (×{mult})",reply_markup=back("casino")); await callback.answer()

@dp.callback_query(F.data == "cas_stats")
async def cas_stats(callback: CallbackQuery):
    con = db(); row = con.execute("SELECT * FROM casino_stats WHERE user_id=?",(callback.from_user.id,)).fetchone(); con.close()
    if not row: return await callback.message.edit_text("📊 Пусто.",reply_markup=back("casino"))
    p = row["total_won"]-row["total_lost"]
    await callback.message.edit_text(
        f"📊 <b>СТАТ</b>\n\nСтавок: {row['total_bets']}\nВыиграно: {row['total_won']}\n"
        f"Проиграно: {row['total_lost']}\nПрофит: {p:+d}\nЛучший: {row['biggest_win']}",reply_markup=back("casino"))
    await callback.answer()

@dp.callback_query(F.data == "cas_top")
async def cas_top(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT u.username,u.first_name,cs.biggest_win FROM casino_stats cs
        JOIN users u ON u.user_id=cs.user_id WHERE cs.biggest_win>0 ORDER BY cs.biggest_win DESC LIMIT 10""").fetchall()
    con.close()
    if not rows: return await callback.message.edit_text("🏆 Пусто.",reply_markup=back("casino"))
    txt = "🏆 <b>ТОП</b>\n\n"+"\n".join(f"{i}. @{escape(r['username'] or r['first_name'] or '-')} — {r['biggest_win']}" for i,r in enumerate(rows,1))
    await callback.message.edit_text(txt,reply_markup=back("casino")); await callback.answer()

# ========== TASKS ==========
async def bump_task(uid,code,amount):
    con = db(); t = con.execute("SELECT * FROM tasks WHERE code=?",(code,)).fetchone()
    if not t: con.close(); return
    ut = con.execute("SELECT * FROM user_tasks WHERE user_id=? AND task_id=? AND date=?",(uid,t["id"],today())).fetchone()
    if not ut:
        con.execute("INSERT INTO user_tasks(user_id,task_id,date,progress) VALUES(?,?,?,?)",(uid,t["id"],today(),amount))
        new = amount; done = 0
    else:
        if ut["done"]: con.close(); return
        new = ut["progress"]+amount; done = ut["done"]
        con.execute("UPDATE user_tasks SET progress=? WHERE id=?",(new,ut["id"]))
    if new >= t["goal"] and not done:
        con.execute("UPDATE user_tasks SET done=1 WHERE user_id=? AND task_id=? AND date=?",(uid,t["id"],today()))
        con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(t["reward"],uid))
        try: await bot.send_message(uid,f"✅ {t['name']}\n+{t['reward']} SD")
        except Exception: pass
    con.commit(); con.close()

@dp.callback_query(F.data == "tasks")
async def tasks_menu(callback: CallbackQuery):
    con = db(); tasks = con.execute("SELECT * FROM tasks").fetchall()
    txt = "📋 <b>ЗАДАНИЯ</b>\n\n"
    for t in tasks:
        ut = con.execute("SELECT * FROM user_tasks WHERE user_id=? AND task_id=? AND date=?",(callback.from_user.id,t["id"],today())).fetchone()
        p = ut["progress"] if ut else 0; d = "✅" if ut and ut["done"] else ""
        txt += f"{d} <b>{escape(t['name'])}</b> — {p}/{t['goal']} · +{t['reward']} SD\n"
    con.close(); await callback.message.edit_text(txt,reply_markup=back()); await callback.answer()

# ========== DUELS ==========
@dp.callback_query(F.data == "duels")
async def duels_menu(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="⚔️ Создать",callback_data="duel_create"); b.button(text="📜 Мои",callback_data="duel_my")
    b.button(text="◀️ Назад",callback_data="home"); b.adjust(1)
    await callback.message.edit_text(
        f"⚔️ <b>ДУЭЛИ</b>\n\nМин: {get_limit('duel_min')} SD. Комиссия: {int(get_limit('duel_commission')*100)}%",
        reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data == "duel_create")
async def duel_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DuelBet.amount)
    await callback.message.edit_text(f"⚔️ Сумма (мин {get_limit('duel_min')}):",reply_markup=back("duels")); await callback.answer()

@dp.message(StateFilter(DuelBet.amount))
async def duel_amount(message: Message, state: FSMContext):
    try: amount = int((message.text or "").strip())
    except Exception: return await message.answer("❌")
    if amount < get_limit("duel_min"): return await message.answer(f"❌ Мин {get_limit('duel_min')}.")
    if not take_sd(message.from_user.id,amount): return await message.answer("❌ Мало SD.")
    con = db()
    cur = con.execute("INSERT INTO duels(challenger_id,opponent_id,amount,status,created_at) VALUES(?,?,?,?,?)",
        (message.from_user.id,0,amount,"open",now()))
    did = cur.lastrowid; con.commit(); con.close(); await state.clear()
    await message.answer(f"⚔️ Дуэль #{did}\n\nВызов: <code>/duel {did}</code>\nСумма: {amount} SD",reply_markup=back("duels"))

@dp.message(Command("duel"))
async def duel_accept(message: Message):
    parts = message.text.split()
    if len(parts) < 2: return await message.answer("Использование: /duel ID")
    try: did = int(parts[1])
    except Exception: return await message.answer("❌")
    con = db(); row = con.execute("SELECT * FROM duels WHERE id=?",(did,)).fetchone()
    if not row or row["status"] != "open": con.close(); return await message.answer("❌ Недоступна.")
    if row["challenger_id"] == message.from_user.id: con.close(); return await message.answer("❌ С собой нельзя.")
    opp = ensure(message.from_user)
    if opp["sd"] < row["amount"]: con.close(); return await message.answer("❌ Мало SD.")
    con.execute("UPDATE users SET sd=sd-? WHERE user_id=?",(row["amount"],message.from_user.id))
    winner = random.choice([row["challenger_id"],message.from_user.id])
    pot = row["amount"]*2; prize = pot-int(pot*get_limit("duel_commission"))
    con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(prize,winner))
    con.execute("UPDATE duels SET opponent_id=?, status='done', winner_id=?, finished_at=? WHERE id=?",
        (message.from_user.id,winner,now(),did)); con.commit(); con.close()
    await check_achievements(winner)
    await message.answer(f"⚔️ Победитель: <code>{winner}</code>\nПриз: {prize} SD")
    try: await bot.send_message(row["challenger_id"],f"⚔️ Дуэль #{did} завершена.")
    except Exception: pass

@dp.callback_query(F.data == "duel_my")
async def duel_my(callback: CallbackQuery):
    con = db()
    rows = con.execute("SELECT * FROM duels WHERE challenger_id=? OR opponent_id=? ORDER BY id DESC LIMIT 20",
        (callback.from_user.id,callback.from_user.id)).fetchall(); con.close()
    if not rows: return await callback.message.edit_text("📜 Пусто.",reply_markup=back("duels"))
    txt = "📜 <b>МОИ ДУЭЛИ</b>\n\n"+"\n".join(f"#{r['id']} · {r['amount']} SD · {r['status']}" for r in rows)
    await callback.message.edit_text(txt,reply_markup=back("duels")); await callback.answer()

# ========== REF / RATING / ACH / ABOUT / MEDIA ==========
@dp.callback_query(F.data == "ref")
async def ref_menu(callback: CallbackQuery):
    me = await bot.get_me(); link = f"https://t.me/{me.username}?start={callback.from_user.id}"
    con = db(); refs = con.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?",(callback.from_user.id,)).fetchone()["n"]; con.close()
    await callback.message.edit_text(
        f"👥 <b>РЕФЕРАЛЫ</b>\n\nПриглашено: <b>{refs}</b>\n"
        f"За друга: +{get_limit('ref_invite')} SD\nЗа донат: +{get_limit('ref_donate')} SD\n\n"
        f"Ссылка:\n<code>{link}</code>",reply_markup=back()); await callback.answer()

@dp.callback_query(F.data == "rating")
async def rating(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT username,first_name,xp,
        (SELECT COUNT(*) FROM inventory i WHERE i.user_id=u.user_id) items
        FROM users u WHERE blocked=0 ORDER BY xp DESC, items DESC LIMIT 10""").fetchall(); con.close()
    txt = "🏆 <b>ТОП-10</b>\n\n"+("\n".join(f"{i}. @{escape(r['username'] or r['first_name'] or '-')} — ⭐ {r['xp']} · 🎒 {r['items']}" for i,r in enumerate(rows,1)) if rows else "Пусто.")
    await callback.message.edit_text(txt,reply_markup=back()); await callback.answer()

async def check_achievements(uid):
    con = db(); user = con.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    if not user: con.close(); return
    ops = con.execute("SELECT COUNT(*) n FROM case_opens WHERE user_id=?",(uid,)).fetchone()["n"]
    its = con.execute("SELECT COUNT(*) n FROM inventory WHERE user_id=?",(uid,)).fetchone()["n"]
    bts = con.execute("SELECT COUNT(*) n FROM casino_bets WHERE user_id=?",(uid,)).fetchone()["n"]
    wns = con.execute("SELECT COUNT(*) n FROM duels WHERE winner_id=? AND status='done'",(uid,)).fetchone()["n"]
    rfs = con.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?",(uid,)).fetchone()["n"]
    checks = []
    if ops >= 1: checks.append("first_case")
    if ops >= 10: checks.append("ten_cases")
    if ops >= 100: checks.append("hundred_cases")
    if its >= 10: checks.append("collector")
    if user["sd"] >= 5000: checks.append("rich")
    if bts >= 100: checks.append("casino_king")
    if wns >= 5: checks.append("duelist")
    if rfs >= 3: checks.append("referrer")
    for code in checks:
        a = con.execute("SELECT * FROM achievements WHERE code=?",(code,)).fetchone()
        if not a: continue
        if con.execute("SELECT 1 FROM user_achievements WHERE user_id=? AND achievement_id=?",(uid,a["id"])).fetchone(): continue
        con.execute("INSERT INTO user_achievements(user_id,achievement_id,obtained_at) VALUES(?,?,?)",(uid,a["id"],now()))
        if a["reward"] > 0: con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(a["reward"],uid))
        try: await bot.send_message(uid,f"🏅 <b>{a['name']}</b>\n+{a['reward']} SD")
        except Exception: pass
    con.execute("UPDATE users SET level=? WHERE user_id=?",(max(1,user["xp"]//100+1),uid))
    con.commit(); con.close()

@dp.callback_query(F.data == "achievements")
async def achievements(callback: CallbackQuery):
    con = db()
    rows = con.execute("""SELECT a.*, ua.obtained_at FROM achievements a
        LEFT JOIN user_achievements ua ON ua.achievement_id=a.id AND ua.user_id=? ORDER BY a.id""",
        (callback.from_user.id,)).fetchall(); con.close()
    txt = "🏅 <b>ДОСТИЖЕНИЯ</b>\n\n"+"\n".join(
        f"{'✅' if r['obtained_at'] else '🔒'} <b>{escape(r['name'])}</b> — +{r['reward']} SD" for r in rows)
    await callback.message.edit_text(txt,reply_markup=back()); await callback.answer()

@dp.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    await callback.message.edit_text("ℹ️ <b>О COS-DROP</b>\n\nКейсы, казино, дуэли, достижения.\n💰 SD — виртуальная валюта.",reply_markup=back()); await callback.answer()

@dp.callback_query(F.data == "media")
async def media(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="📩 Заявка",callback_data="media_apply"); b.button(text="◀️ Назад",callback_data="home"); b.adjust(1)
    await callback.message.edit_text("🎬 <b>МЕДИА / ПАРТНЁРСТВО</b>",reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data == "media_apply")
async def media_apply(callback: CallbackQuery):
    m = await callback.message.edit_text("⏳ Загрузка...")
    for i in range(0,101,10):
        await asyncio.sleep(0.15)
        bar = "█"*(i//10)+"░"*(10-i//10)
        try: await m.edit_text(f"⏳ Загрузка...\n<code>[{bar}] {i}%</code>")
        except Exception: pass
    await m.edit_text("✅ <b>ГОТОВО</b>\n\n🎬 МЕДИА\n\nНапиши: <a href=\"https://t.me/d3v_exe\">@d3v_exe</a>\n\n"
        "• 🎟 промокод\n• 💰 бонус\n• 🚀 продвижение",reply_markup=back(),disable_web_page_preview=True)
    await callback.answer()

# ========== WITHDRAW / APPS / PROMO ==========
@dp.callback_query(F.data == "withdraw")
async def withdraw_start(callback: CallbackQuery, state: FSMContext):
    u = ensure(callback.from_user)
    if u["blocked"]: return await callback.answer("Заблокирован.",show_alert=True)
    if not get_limit("withdraw_enabled"): return await callback.answer("Выводы отключены.",show_alert=True)
    mn = get_limit("min_withdraw")
    if u["sd"] < mn: return await callback.answer(f"Мин: {mn} SD",show_alert=True)
    await state.set_state(WithdrawFSM.amount)
    await callback.message.edit_text(f"💸 <b>ВЫВОД</b>\n\nБаланс: {u['sd']} SD\nМин: {mn} SD\n\nВведи сумму:")
    await callback.answer()

@dp.message(StateFilter(WithdrawFSM.amount))
async def withdraw_amount(message: Message, state: FSMContext):
    try: amount = int((message.text or "").strip())
    except Exception: return await message.answer("❌")
    if amount < get_limit("min_withdraw"): return await message.answer(f"❌ Мин {get_limit('min_withdraw')}.")
    if amount > get_limit("max_withdraw"): return await message.answer(f"❌ Макс {get_limit('max_withdraw')}.")
    con = db(); u = con.execute("SELECT sd FROM users WHERE user_id=?",(message.from_user.id,)).fetchone()
    if not u or u["sd"] < amount: con.close(); await state.clear(); return await message.answer("❌ Мало SD.")
    con.execute("UPDATE users SET sd=sd-? WHERE user_id=?",(amount,message.from_user.id))
    cur = con.execute("INSERT INTO withdraws(user_id,amount,created_at) VALUES(?,?,?)",(message.from_user.id,amount,now()))
    wid = cur.lastrowid; con.commit(); con.close(); await state.clear()
    await message.answer(f"✅ Заявка #{wid} на {amount} SD.")
    try:
        await bot.send_message(ADMIN_ID,f"💸 Вывод #{wid}\n👤 {message.from_user.id}\n💰 {amount}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅",callback_data=f"wd_ok:{wid}"),
                InlineKeyboardButton(text="❌",callback_data=f"wd_no:{wid}")]]))
    except Exception: pass

@dp.callback_query(F.data.startswith("wd_ok:"))
async def wd_ok(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    wid = int(callback.data.split(":")[1]); con = db()
    row = con.execute("SELECT * FROM withdraws WHERE id=?",(wid,)).fetchone()
    if not row or row["status"] != "pending": con.close(); return await callback.answer("Обработана.",show_alert=True)
    con.execute("UPDATE withdraws SET status='paid', admin_id=?, decided_at=? WHERE id=?",(ADMIN_ID,now(),wid)); con.commit(); con.close()
    log_admin("withdraw_paid",row["user_id"],str(wid))
    await callback.message.edit_reply_markup(reply_markup=None); await callback.answer("Выплачено.")
    try: await bot.send_message(row["user_id"],f"✅ Вывод #{wid} выплачен.")
    except Exception: pass

@dp.callback_query(F.data.startswith("wd_no:"))
async def wd_no(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    wid = int(callback.data.split(":")[1]); con = db()
    row = con.execute("SELECT * FROM withdraws WHERE id=?",(wid,)).fetchone()
    if not row or row["status"] != "pending": con.close(); return await callback.answer("Обработана.",show_alert=True)
    con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(row["amount"],row["user_id"]))
    con.execute("UPDATE withdraws SET status='rejected', admin_id=?, decided_at=? WHERE id=?",(ADMIN_ID,now(),wid))
    con.commit(); con.close(); log_admin("withdraw_rejected",row["user_id"],str(wid))
    await callback.message.edit_reply_markup(reply_markup=None); await callback.answer("Отклонено.")
    try: await bot.send_message(row["user_id"],f"❌ Вывод #{wid} отклонён.")
    except Exception: pass

@dp.callback_query(F.data == "apps")
async def applications(callback: CallbackQuery):
    con = db(); rows = con.execute("SELECT id,status FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 10",(callback.from_user.id,)).fetchall(); con.close()
    txt = "\n".join(f"#{r['id']} · {r['status']}" for r in rows) or "Нет."
    await callback.message.edit_text(f"📝 <b>ЗАЯВКИ</b>\n\n{txt}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать",callback_data="newapp")],
            [InlineKeyboardButton(text="◀️ Назад",callback_data="home")]])); await callback.answer()

@dp.callback_query(F.data == "newapp")
async def new_application(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Apply.name); await callback.message.edit_text("📝 Введите имя:"); await callback.answer()

@dp.message(StateFilter(Apply.name))
async def app_name(message: Message, state: FSMContext):
    await state.update_data(name=(message.text or "")[:100]); await state.set_state(Apply.cls); await message.answer("🏫 Класс:")

@dp.message(StateFilter(Apply.cls))
async def app_cls(message: Message, state: FSMContext):
    await state.update_data(cls=(message.text or "")[:30]); await state.set_state(Apply.phone); await message.answer("📱 Контакт:")

@dp.message(StateFilter(Apply.phone))
async def app_phone(message: Message, state: FSMContext):
    await state.update_data(phone=(message.text or "")[:50]); await state.set_state(Apply.msg); await message.answer("💬 Сообщение:")

@dp.message(StateFilter(Apply.msg))
async def app_msg(message: Message, state: FSMContext):
    data = await state.update_data(msg=(message.text or "")[:1000])
    con = db()
    cur = con.execute("""INSERT INTO applications(user_id,kind,name,class_name,phone,message,created_at)
        VALUES(?,?,?,?,?,?,?)""",(message.from_user.id,"general",data["name"],data["cls"],data["phone"],data["msg"],now()))
    aid = cur.lastrowid; con.commit(); con.close(); await state.clear()
    await message.answer(f"✅ Заявка #{aid}.")
    try:
        await bot.send_message(ADMIN_ID,f"📝 #{aid}\n{data['name']}\n{data['cls']}\n{data['phone']}\n{data['msg']}\n{message.from_user.id}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅",callback_data=f"appok:{aid}"),
                InlineKeyboardButton(text="❌",callback_data=f"appno:{aid}")]]))
    except Exception: pass

@dp.callback_query(F.data.startswith("appok:"))
async def app_ok(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    aid = int(callback.data.split(":")[1]); con = db()
    row = con.execute("SELECT * FROM applications WHERE id=?",(aid,)).fetchone()
    if not row: con.close(); return await callback.answer("Нет.",show_alert=True)
    con.execute("UPDATE applications SET status='approved', admin_id=?, decided_at=? WHERE id=?",(ADMIN_ID,now(),aid)); con.commit(); con.close()
    log_admin("approve_app",row["user_id"],str(aid))
    await callback.message.edit_reply_markup(reply_markup=None); await callback.answer("Принята.")
    try: await bot.send_message(row["user_id"],f"✅ Заявка #{aid} принята.")
    except Exception: pass

@dp.callback_query(F.data.startswith("appno:"))
async def app_no(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    aid = int(callback.data.split(":")[1]); con = db()
    row = con.execute("SELECT * FROM applications WHERE id=?",(aid,)).fetchone()
    if not row: con.close(); return await callback.answer("Нет.",show_alert=True)
    con.execute("UPDATE applications SET status='rejected', admin_id=?, decided_at=? WHERE id=?",(ADMIN_ID,now(),aid)); con.commit(); con.close()
    log_admin("reject_app",row["user_id"],str(aid))
    await callback.message.edit_reply_markup(reply_markup=None); await callback.answer("Отклонена.")
    try: await bot.send_message(row["user_id"],f"❌ Заявка #{aid} отклонена.")
    except Exception: pass

@dp.callback_query(F.data == "promo")
async def promo_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Promo.code); await callback.message.edit_text("🎟 Введите код:"); await callback.answer()

@dp.message(StateFilter(Promo.code))
async def use_promo(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper(); con = db()
    promo = con.execute("SELECT * FROM promo_codes WHERE code=? AND enabled=1",(code,)).fetchone()
    if not promo: con.close(); await state.clear(); return await message.answer("❌ Нет.")
    if con.execute("SELECT 1 FROM promo_uses WHERE promo_id=? AND user_id=?",(promo["id"],message.from_user.id)).fetchone():
        con.close(); await state.clear(); return await message.answer("❌ Уже.")
    if promo["uses"] >= promo["max_uses"]: con.close(); await state.clear(); return await message.answer("❌ Лимит.")
    con.execute("INSERT INTO promo_uses(promo_id,user_id,used_at) VALUES(?,?,?)",(promo["id"],message.from_user.id,now()))
    con.execute("UPDATE promo_codes SET uses=uses+1 WHERE id=?",(promo["id"],))
    con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(promo["reward"],message.from_user.id))
    con.commit(); con.close(); await state.clear()
    await message.answer(f"🎉 +{promo['reward']} SD"); await check_achievements(message.from_user.id)

# ========== КОНЕЦ ЧАСТИ 3/4 ==========
# ========== ADMIN v1 ==========
@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("👑 <b>ADMIN</b>",reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.message.edit_text("👑 <b>ADMIN</b>",reply_markup=admin_kb()); await callback.answer()

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    u = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    b = con.execute("SELECT COUNT(*) n FROM users WHERE blocked=1").fetchone()["n"]
    sd = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    op = con.execute("SELECT COUNT(*) n FROM case_opens").fetchone()["n"]; con.close()
    await callback.message.edit_text(f"📊 <b>СТАТИСТИКА</b>\n\n👥 {u}\n🚫 {b}\n💰 {sd} SD\n🎁 {op} кейсов",reply_markup=admin_kb())
    await callback.answer()

@dp.callback_query(F.data == "adm_users")
async def adm_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT user_id,username,sd,blocked FROM users ORDER BY id DESC LIMIT 20").fetchall(); con.close()
    txt = "\n".join(f"{'🚫' if r['blocked'] else '🟢'} <code>{r['user_id']}</code> @{escape(r['username'] or '-')} · {r['sd']}" for r in rows)
    await callback.message.edit_text(f"👥 <b>ЮЗЕРЫ</b>\n\n{txt}",reply_markup=admin_kb()); await callback.answer()

@dp.callback_query(F.data == "adm_search")
async def adm_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(UserSearch.query); await callback.message.edit_text("🔎 ID или @username:"); await callback.answer()

@dp.message(StateFilter(UserSearch.query))
async def adm_search_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    q = (message.text or "").strip(); con = db()
    row = con.execute("SELECT * FROM users WHERE user_id=?",(int(q),)).fetchone() if q.isdigit() else \
        con.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)",(q.lstrip("@"),)).fetchone()
    con.close(); await state.clear()
    if not row: return await message.answer("❌ Нет.",reply_markup=admin_kb())
    await message.answer(f"👤 <code>{row['user_id']}</code>\n@{escape(row['username'] or '-')}\n💰 {row['sd']} · Lv {row['level']}\n🚫 {'Да' if row['blocked'] else 'Нет'}",reply_markup=admin_kb())

@dp.callback_query(F.data == "adm_give")
async def adm_give(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(GiveSD.uid); await callback.message.edit_text("🎁 ID:"); await callback.answer()

@dp.message(StateFilter(GiveSD.uid))
async def adm_give_uid(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except Exception: return await message.answer("❌")
    await state.update_data(uid=uid); await state.set_state(GiveSD.amount); await message.answer("💰 Сколько:")

@dp.message(StateFilter(GiveSD.amount))
async def adm_give_amount(message: Message, state: FSMContext):
    try: amount = int(message.text)
    except Exception: return await message.answer("❌")
    data = await state.get_data(); add_sd(data["uid"],amount); log_admin("give_sd",data["uid"],str(amount))
    await state.clear(); await message.answer(f"✅ +{amount} → {data['uid']}")

@dp.callback_query(F.data == "adm_take")
async def adm_take(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(TakeSD.uid); await callback.message.edit_text("➖ ID:"); await callback.answer()

@dp.message(StateFilter(TakeSD.uid))
async def adm_take_uid(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except Exception: return await message.answer("❌")
    await state.update_data(uid=uid); await state.set_state(TakeSD.amount); await message.answer("Сумма:")

@dp.message(StateFilter(TakeSD.amount))
async def adm_take_amount(message: Message, state: FSMContext):
    try: amount = int(message.text)
    except Exception: return await message.answer("❌")
    data = await state.get_data(); con = db()
    row = con.execute("SELECT sd FROM users WHERE user_id=?",(data["uid"],)).fetchone()
    if not row: con.close(); return await message.answer("❌")
    nb = max(0,row["sd"]-amount); con.execute("UPDATE users SET sd=? WHERE user_id=?",(nb,data["uid"]))
    con.commit(); con.close(); log_admin("take_sd",data["uid"],str(amount))
    await state.clear(); await message.answer(f"✅ -{amount} → {data['uid']}")

@dp.callback_query(F.data == "adm_blocks")
async def adm_blocks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Блок",callback_data="block_start")],
        [InlineKeyboardButton(text="🔓 Разблок",callback_data="unblock_start")],
        [InlineKeyboardButton(text="◀️",callback_data="admin_home")]])
    await callback.message.edit_text("🚫 <b>БЛОКИРОВКИ</b>",reply_markup=kb); await callback.answer()

@dp.callback_query(F.data == "block_start")
async def block_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BlockUser.uid); await callback.message.edit_text("🚫 ID:"); await callback.answer()

@dp.message(StateFilter(BlockUser.uid))
async def block_do(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except Exception: return
    con = db(); con.execute("UPDATE users SET blocked=1 WHERE user_id=?",(uid,)); con.commit(); con.close()
    log_admin("block",uid); await state.clear(); await message.answer(f"🚫 {uid}.")

@dp.callback_query(F.data == "unblock_start")
async def unblock_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UnblockUser.uid); await callback.message.edit_text("🔓 ID:"); await callback.answer()

@dp.message(StateFilter(UnblockUser.uid))
async def unblock_do(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except Exception: return
    con = db(); con.execute("UPDATE users SET blocked=0 WHERE user_id=?",(uid,)); con.commit(); con.close()
    log_admin("unblock",uid); await state.clear(); await message.answer(f"🔓 {uid}.")

@dp.callback_query(F.data == "adm_promo")
async def adm_promo(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT code,reward,uses,max_uses FROM promo_codes WHERE enabled=1").fetchall(); con.close()
    txt = "\n".join(f"<code>{escape(r['code'])}</code> +{r['reward']} ({r['uses']}/{r['max_uses']})" for r in rows) or "Пусто."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕",callback_data="promo_add"),InlineKeyboardButton(text="🗑",callback_data="promo_del")],
        [InlineKeyboardButton(text="🎁 Массово",callback_data="a3_promo_mass")],
        [InlineKeyboardButton(text="◀️",callback_data="admin_home")]])
    await callback.message.edit_text(f"🎟 <b>ПРОМО</b>\n\n{txt}",reply_markup=kb); await callback.answer()

@dp.callback_query(F.data == "promo_add")
async def promo_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoCreate.code); await callback.message.edit_text("➕ Код:"); await callback.answer()

@dp.message(StateFilter(PromoCreate.code))
async def promo_add_code(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{2,32}",code): return await message.answer("❌ A-Z 0-9 _ -")
    con = db()
    if con.execute("SELECT 1 FROM promo_codes WHERE code=?",(code,)).fetchone(): con.close(); return await message.answer("❌ Есть.")
    con.close(); await state.update_data(code=code); await state.set_state(PromoCreate.reward); await message.answer("💰 Сколько SD:")

@dp.message(StateFilter(PromoCreate.reward))
async def promo_add_reward(message: Message, state: FSMContext):
    try: reward = int(message.text)
    except Exception: return
    data = await state.get_data(); con = db()
    con.execute("INSERT INTO promo_codes(code,reward,max_uses,uses,enabled) VALUES(?,?,999999999,0,1)",(data["code"],reward))
    con.commit(); con.close(); log_admin("create_promo",details=f"{data['code']} +{reward}")
    await state.clear(); await message.answer(f"✅ {data['code']} +{reward}")

@dp.callback_query(F.data == "promo_del")
async def promo_del(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoDelete.code); await callback.message.edit_text("🗑 Код:"); await callback.answer()

@dp.message(StateFilter(PromoDelete.code))
async def promo_del_do(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper(); con = db()
    row = con.execute("SELECT * FROM promo_codes WHERE code=?",(code,)).fetchone()
    if not row: con.close(); return await message.answer("❌ Нет.")
    con.execute("DELETE FROM promo_uses WHERE promo_id=?",(row["id"],))
    con.execute("DELETE FROM promo_codes WHERE id=?",(row["id"],)); con.commit(); con.close()
    log_admin("delete_promo",details=code); await state.clear(); await message.answer(f"🗑 {code}.")

@dp.callback_query(F.data == "adm_cases")
async def adm_cases(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT id,name,price,enabled FROM cases ORDER BY id").fetchall(); con.close()
    txt = "\n".join(f"{'🟢' if r['enabled'] else '🔴'} {r['name']} · {r['price']}" for r in rows)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄",callback_data="case_toggle_start")],
        [InlineKeyboardButton(text="💰",callback_data="case_price_start")],
        [InlineKeyboardButton(text="◀️",callback_data="admin_home")]])
    await callback.message.edit_text(f"📦 <b>КЕЙСЫ</b>\n\n{txt}",reply_markup=kb); await callback.answer()

@dp.callback_query(F.data == "case_toggle_start")
async def case_toggle_start(callback: CallbackQuery):
    con = db(); rows = con.execute("SELECT id,name,enabled FROM cases ORDER BY id").fetchall(); con.close()
    kb = [[InlineKeyboardButton(text=f"{'🟢' if r['enabled'] else '🔴'} {r['name']}",callback_data=f"case_toggle:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️",callback_data="adm_cases")])
    await callback.message.edit_text("🎮:",reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)); await callback.answer()

@dp.callback_query(F.data.startswith("case_toggle:"))
async def case_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    cid = int(callback.data.split(":")[1]); con = db()
    r = con.execute("SELECT enabled FROM cases WHERE id=?",(cid,)).fetchone()
    if not r: con.close(); return await callback.answer("Нет.",show_alert=True)
    nv = 0 if r["enabled"] else 1
    con.execute("UPDATE cases SET enabled=? WHERE id=?",(nv,cid)); con.commit(); con.close()
    log_admin("toggle_case",details=f"{cid}:{nv}"); await callback.answer("✅",show_alert=True)

@dp.callback_query(F.data == "case_price_start")
async def case_price_start(callback: CallbackQuery):
    con = db(); rows = con.execute("SELECT id,name,price FROM cases ORDER BY id").fetchall(); con.close()
    kb = [[InlineKeyboardButton(text=f"{r['name']} · {r['price']}",callback_data=f"price_case:{r['id']}")] for r in rows]
    kb.append([InlineKeyboardButton(text="◀️",callback_data="adm_cases")])
    await callback.message.edit_text("💰:",reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)); await callback.answer()

@dp.callback_query(F.data.startswith("price_case:"))
async def price_case(callback: CallbackQuery, state: FSMContext):
    cid = int(callback.data.split(":")[1])
    await state.update_data(case_id=cid); await state.set_state(CasePrice.price)
    await callback.message.edit_text("💰 Новая цена:"); await callback.answer()

@dp.message(StateFilter(CasePrice.price))
async def price_case_do(message: Message, state: FSMContext):
    try: price = int(message.text)
    except Exception: return
    data = await state.get_data(); con = db()
    con.execute("UPDATE cases SET price=? WHERE id=?",(price,data["case_id"])); con.commit(); con.close()
    log_admin("change_case_price",details=f"{data['case_id']}:{price}"); await state.clear(); await message.answer(f"✅ {price}.")

@dp.callback_query(F.data == "adm_items")
async def adm_items(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT name,rarity,sell_price,enabled FROM items ORDER BY id").fetchall(); con.close()
    txt = "\n".join(f"{'🟢' if r['enabled'] else '🔴'} {RARITY.get(r['rarity'],'⚪')} {r['name']} · {r['sell_price']}" for r in rows)
    await callback.message.edit_text(f"💎 <b>ПРЕДМЕТЫ</b>\n\n{txt}",reply_markup=admin_kb()); await callback.answer()

@dp.callback_query(F.data == "adm_apps")
async def adm_apps(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT id,user_id,name,status FROM applications ORDER BY id DESC LIMIT 30").fetchall(); con.close()
    txt = "\n".join(f"#{r['id']} · {r['user_id']} · {r['name']} · {r['status']}" for r in rows) or "Пусто."
    await callback.message.edit_text(f"📝 <b>ЗАЯВКИ</b>\n\n{txt}",reply_markup=admin_kb()); await callback.answer()

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(Broadcast.text); await callback.message.edit_text("📢 Текст:"); await callback.answer()

@dp.message(StateFilter(Broadcast.text))
async def broadcast_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    con = db(); users = con.execute("SELECT user_id FROM users WHERE blocked=0").fetchall(); con.close()
    s,f = 0,0
    for r in users:
        try: await bot.send_message(r["user_id"],message.text or ""); s += 1
        except Exception: f += 1
        await asyncio.sleep(0.05)
    await state.clear(); log_admin("broadcast",details=f"s={s},f={f}")
    await message.answer(f"✅ {s}\n❌ {f}")

@dp.callback_query(F.data == "adm_logs")
async def adm_logs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 30").fetchall(); con.close()
    txt = "\n".join(f"{r['created_at'][:19]} · {r['action']} · {r['target_user_id'] or '-'}" for r in rows) or "Пусто."
    await callback.message.edit_text(f"📜 <b>ЛОГИ</b>\n\n{txt}",reply_markup=admin_kb()); await callback.answer()

@dp.callback_query(F.data == "adm_backup")
async def adm_backup(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    try:
        os.makedirs(BACKUP_DIR,exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BACKUP_DIR,f"cosdrop_{ts}.sqlite3")
        src = sqlite3.connect(DB_FILE); dst = sqlite3.connect(path)
        with dst: src.backup(dst)
        dst.close(); src.close()
        await callback.message.answer_document(FSInputFile(path),caption="💾 Бэкап"); await callback.answer("✅")
    except Exception as e: await callback.answer(f"❌ {e}",show_alert=True)

@dp.callback_query(F.data == "adm_withdraws")
async def admin_withdraws(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT * FROM withdraws ORDER BY id DESC LIMIT 30").fetchall(); con.close()
    txt = "\n".join(f"#{r['id']} · {r['user_id']} · {r['amount']} · {r['status']}" for r in rows) or "Пусто."
    await callback.message.edit_text(f"💸 <b>ВЫВОДЫ</b>\n\n{txt}",reply_markup=admin_kb()); await callback.answer()

# ========== ADMIN v2 ==========
def a2_root_kb():
    b = InlineKeyboardBuilder()
    for t,d in [("📊 Статистика","a2_stats"),("👥 Юзеры","a2_users"),
        ("📦 Кейсы","a2_cases"),("💎 Предметы","a2_items"),("🎟 Промо","a2_promo"),
        ("🎰 Казино","a2_casino"),("📜 Логи","a2_logs"),("🛠 Сервис","a2_maint"),
        ("📢 Рассылка","a2_broadcast"),("⚙️ Лимиты","a3_root"),
        ("💰 Экономика","a3_econ"),("🎯 Массовые","a3_mass"),
        ("📁 Экспорт","a3_export"),("🛠 Диагностика","a3_diag"),
        ("❌ Закрыть","a2_close"),("◀️ Админка v1","admin_home")]:
        b.button(text=t,callback_data=d)
    b.adjust(2,2,2,2,2,2,2,1,1); return b.as_markup()

def a2_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена",callback_data="a2_root")]])

@dp.message(Command("admin2"))
async def a2_open(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("👑 <b>ADMIN v2</b>",reply_markup=a2_root_kb())

@dp.callback_query(F.data == "a2_root")
async def a2_root(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.clear()
    await callback.message.edit_text("👑 <b>ADMIN v2</b>",reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2_close")
async def a2_close(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.clear()
    try: await callback.message.delete()
    except Exception: pass
    await callback.answer()

@dp.callback_query(F.data == "a2_stats")
async def a2_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    u = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    b = con.execute("SELECT COUNT(*) n FROM users WHERE blocked=1").fetchone()["n"]
    sd = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    inv = con.execute("SELECT COUNT(*) n FROM inventory").fetchone()["n"]
    op = con.execute("SELECT COUNT(*) n FROM case_opens").fetchone()["n"]
    bets = con.execute("SELECT COUNT(*) n FROM casino_bets").fetchone()["n"]
    wd = con.execute("SELECT COUNT(*) n FROM withdraws").fetchone()["n"]
    subs = con.execute("SELECT COUNT(*) n FROM users WHERE sub_until IS NOT NULL").fetchone()["n"]
    duels = con.execute("SELECT COUNT(*) n FROM duels").fetchone()["n"]; con.close()
    await callback.message.edit_text(
        f"📈 <b>ОБЩАЯ</b>\n\n👥 {u}\n🚫 {b}\n💰 SD: <b>{sd}</b>\n🎒 Предметов: <b>{inv}</b>\n"
        f"🎁 Открытий: <b>{op}</b>\n🎰 Ставок: <b>{bets}</b>\n💸 Выводов: <b>{wd}</b>\n"
        f"💎 Подписок: <b>{subs}</b>\n⚔️ Дуэлей: <b>{duels}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Топ SD",callback_data="a2s_top_sd")],
            [InlineKeyboardButton(text="⭐ Топ XP",callback_data="a2s_top_xp")],
            [InlineKeyboardButton(text="◀️ Назад",callback_data="a2_root")]]))
    await callback.answer()

@dp.callback_query(F.data == "a2s_top_sd")
async def a2s_top_sd(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT user_id,username,sd FROM users ORDER BY sd DESC LIMIT 15").fetchall(); con.close()
    txt = "🏆 <b>ТОП SD</b>\n\n"+"\n".join(f"{i}. <code>{r['user_id']}</code> @{escape(r['username'] or '-')} — {r['sd']}" for i,r in enumerate(rows,1))
    await callback.message.edit_text(txt,reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2s_top_xp")
async def a2s_top_xp(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT user_id,username,xp FROM users ORDER BY xp DESC LIMIT 15").fetchall(); con.close()
    txt = "⭐ <b>ТОП XP</b>\n\n"+"\n".join(f"{i}. <code>{r['user_id']}</code> @{escape(r['username'] or '-')} — {r['xp']}" for i,r in enumerate(rows,1))
    await callback.message.edit_text(txt,reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2_users")
async def a2_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for t,d in [("📋 Список","a2u_list"),("🔎 Поиск","a2u_search"),
        ("🎁 +SD","a2u_give_sd"),("➖ -SD","a2u_take_sd"),("⭐ +XP","a2u_give_xp"),
        ("🚫 Блок","a2u_block"),("🔓 Разблок","a2u_unblock"),("🗑 Сброс","a2u_reset"),
        ("✉️ Письмо","a2u_msg"),("📄 CSV","a2u_export"),("◀️ Назад","a2_root")]:
        b.button(text=t,callback_data=d)
    b.adjust(2,2,2,2,2,1)
    await callback.message.edit_text("👥 <b>ЮЗЕРЫ</b>",reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data == "a2u_list")
async def a2u_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT user_id,username,sd,blocked FROM users ORDER BY id DESC LIMIT 30").fetchall(); con.close()
    txt = "📋 <b>ПОСЛЕДНИЕ 30</b>\n\n"+"\n".join(
        f"{'🚫' if r['blocked'] else '🟢'} <code>{r['user_id']}</code> @{escape(r['username'] or '-')} · {r['sd']} SD" for r in rows)
    await callback.message.edit_text(txt,reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2u_search")
async def a2u_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(A2Search.q); await callback.message.edit_text("🔎 ID или @username:",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2Search.q))
async def a2u_search_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    q = (message.text or "").strip(); con = db()
    if q.isdigit(): row = con.execute("SELECT * FROM users WHERE user_id=?",(int(q),)).fetchone()
    else: row = con.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)",(q.lstrip("@"),)).fetchone()
    con.close(); await state.clear()
    if not row: return await message.answer("❌ Не найден.",reply_markup=a2_root_kb())
    u = row
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 +SD",callback_data=f"a2u_gsd:{u['user_id']}"),
         InlineKeyboardButton(text="➖ -SD",callback_data=f"a2u_tsd:{u['user_id']}")],
        [InlineKeyboardButton(text="🚫 Блок" if not u['blocked'] else "🔓 Разблок",callback_data=f"a2u_tb:{u['user_id']}")],
        [InlineKeyboardButton(text="🗑 Сброс",callback_data=f"a2u_rst:{u['user_id']}")],
        [InlineKeyboardButton(text="✉️ Письмо",callback_data=f"a2u_msgto:{u['user_id']}")],
        [InlineKeyboardButton(text="◀️ Назад",callback_data="a2_users")]])
    await message.answer(f"👤 <code>{u['user_id']}</code>\n@{escape(u['username'] or '-')}\n💰 {u['sd']} · Lv {u['level']}",reply_markup=kb)

@dp.callback_query(F.data.startswith("a2u_gsd:"))
async def a2u_gsd(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    await state.update_data(uid=uid,mode="give"); await state.set_state(A2SD.val)
    await callback.message.edit_text(f"🎁 Сколько SD для <code>{uid}</code>?",reply_markup=a2_cancel()); await callback.answer()

@dp.callback_query(F.data.startswith("a2u_tsd:"))
async def a2u_tsd(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    await state.update_data(uid=uid,mode="take"); await state.set_state(A2SD.val)
    await callback.message.edit_text(f"➖ Сколько забрать?",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2SD.val))
async def a2u_sd_val(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: val = int(message.text)
    except Exception: return await message.answer("❌")
    data = await state.get_data(); uid = data.get("uid"); mode = data.get("mode")
    if mode == "take":
        con = db(); row = con.execute("SELECT sd FROM users WHERE user_id=?",(uid,)).fetchone()
        nb = max(0,(row["sd"] if row else 0)-val)
        con.execute("UPDATE users SET sd=? WHERE user_id=?",(nb,uid)); con.commit(); con.close()
    else: add_sd(uid,val)
    log_admin(f"{mode}_sd",uid,str(val)); await state.clear()
    await message.answer(f"✅ {mode} {val} → {uid}",reply_markup=a2_root_kb())

@dp.callback_query(F.data == "a2u_give_sd")
async def a2u_give_sd(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(mode="give"); await state.set_state(A2SD.uid)
    await callback.message.edit_text("🎁 ID:",reply_markup=a2_cancel()); await callback.answer()

@dp.callback_query(F.data == "a2u_take_sd")
async def a2u_take_sd(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(mode="take"); await state.set_state(A2SD.uid)
    await callback.message.edit_text("➖ ID:",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2SD.uid))
async def a2u_sd_uid(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: uid = int(message.text)
    except Exception: return await message.answer("❌")
    await state.update_data(uid=uid); await state.set_state(A2SD.val); await message.answer("Значение:")

@dp.callback_query(F.data == "a2u_give_xp")
async def a2u_give_xp(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(A2XP.uid); await callback.message.edit_text("⭐ ID:",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2XP.uid))
async def a2u_xp_uid(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except Exception: return
    await state.update_data(uid=uid); await state.set_state(A2XP.val); await message.answer("XP:")

@dp.message(StateFilter(A2XP.val))
async def a2u_xp_val(message: Message, state: FSMContext):
    try: v = int(message.text)
    except Exception: return
    data = await state.get_data(); con = db()
    con.execute("UPDATE users SET xp=xp+? WHERE user_id=?",(v,data["uid"])); con.commit(); con.close()
    log_admin("give_xp",data["uid"],str(v)); await state.clear()
    await message.answer(f"✅ +{v} XP → {data['uid']}",reply_markup=a2_root_kb())

@dp.callback_query(F.data.startswith("a2u_tb:"))
async def a2u_tb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split(":")[1]); con = db()
    row = con.execute("SELECT blocked FROM users WHERE user_id=?",(uid,)).fetchone()
    if not row: con.close(); return await callback.answer("Нет.",show_alert=True)
    nv = 0 if row["blocked"] else 1
    con.execute("UPDATE users SET blocked=? WHERE user_id=?",(nv,uid)); con.commit(); con.close()
    log_admin("toggle_block",uid,str(nv)); await callback.answer("Изменено.",show_alert=True)

@dp.callback_query(F.data.startswith("a2u_rst:"))
async def a2u_rst(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split(":")[1]); con = db()
    con.execute("UPDATE users SET sd=0, xp=0, level=1 WHERE user_id=?",(uid,))
    con.execute("DELETE FROM inventory WHERE user_id=?",(uid,)); con.commit(); con.close()
    log_admin("reset_user",uid); await callback.answer("✅ Сброшено.",show_alert=True)

@dp.callback_query(F.data.startswith("a2u_msgto:"))
async def a2u_msgto(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split(":")[1])
    await state.update_data(uid=uid); await state.set_state(A2Msg.text)
    await callback.message.edit_text(f"✉️ Текст для <code>{uid}</code>:",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2Msg.text))
async def a2u_msg_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data(); uid = data.get("uid")
    try:
        await bot.send_message(uid,f"📩 <b>От админа:</b>\n\n{message.text}")
        await message.answer("✅ Отправлено.",reply_markup=a2_root_kb())
    except Exception as e: await message.answer(f"❌ {e}",reply_markup=a2_root_kb())
    await state.clear()

@dp.callback_query(F.data == "a2u_msg")
async def a2u_msg(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(A2Msg.uid); await callback.message.edit_text("✉️ ID:",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2Msg.uid))
async def a2u_msg_uid(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except Exception: return
    await state.update_data(uid=uid); await state.set_state(A2Msg.text); await message.answer("Текст:")

@dp.callback_query(F.data == "a2u_block")
async def a2u_block(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(BlockUser.uid); await callback.message.edit_text("🚫 ID:",reply_markup=a2_cancel()); await callback.answer()

@dp.callback_query(F.data == "a2u_unblock")
async def a2u_unblock(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(UnblockUser.uid); await callback.message.edit_text("🔓 ID:",reply_markup=a2_cancel()); await callback.answer()

@dp.callback_query(F.data == "a2u_reset")
async def a2u_reset(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(A2Reset.uid); await callback.message.edit_text("🗑 ID:",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2Reset.uid))
async def a2u_reset_do(message: Message, state: FSMContext):
    try: uid = int(message.text)
    except Exception: return
    con = db()
    con.execute("UPDATE users SET sd=0, xp=0, level=1 WHERE user_id=?",(uid,))
    con.execute("DELETE FROM inventory WHERE user_id=?",(uid,)); con.commit(); con.close()
    log_admin("reset_user",uid); await state.clear()
    await message.answer(f"🗑 {uid}.",reply_markup=a2_root_kb())

@dp.callback_query(F.data == "a2u_export")
async def a2u_export(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT user_id,username,sd,xp,level FROM users").fetchall(); con.close()
    path = "export_users.csv"
    with open(path,"w",encoding="utf-8") as f:
        f.write("user_id,username,sd,xp,level\n")
        for r in rows: f.write(f"{r['user_id']},{r['username'] or ''},{r['sd']},{r['xp']},{r['level']}\n")
    await callback.message.answer_document(FSInputFile(path),caption="📄 CSV"); await callback.answer()

@dp.callback_query(F.data == "a2_cases")
async def a2_cases(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT id,name,price,enabled FROM cases ORDER BY id").fetchall(); con.close()
    txt = "📦 <b>КЕЙСЫ</b>\n\n"+"\n".join(f"{'🟢' if r['enabled'] else '🔴'} {r['name']} · {r['price']}" for r in rows)
    await callback.message.edit_text(txt,reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2_items")
async def a2_items(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT id,name,rarity,sell_price FROM items ORDER BY id").fetchall(); con.close()
    txt = "💎 <b>ПРЕДМЕТЫ</b>\n\n"+"\n".join(f"<code>{r['id']}</code> {RARITY.get(r['rarity'],'⚪')} {r['name']} · {r['sell_price']}" for r in rows)
    await callback.message.edit_text(txt,reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2_promo")
async def a2_promo(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT code,reward,uses,max_uses FROM promo_codes WHERE enabled=1").fetchall(); con.close()
    txt = "🎟 <b>ПРОМО</b>\n\n"+"\n".join(f"<code>{escape(r['code'])}</code> +{r['reward']} ({r['uses']}/{r['max_uses']})" for r in rows) or "Пусто."
    b = InlineKeyboardBuilder()
    b.button(text="➕",callback_data="promo_add"); b.button(text="🗑",callback_data="promo_del")
    b.button(text="🎁 Массово",callback_data="a3_promo_mass")
    b.button(text="◀️ Назад",callback_data="a2_root"); b.adjust(2,1,1)
    await callback.message.edit_text(txt,reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data == "a2_casino")
async def a2_casino(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    n = con.execute("SELECT COUNT(*) n FROM casino_bets").fetchone()["n"]
    b = con.execute("SELECT COALESCE(SUM(bet),0) n FROM casino_bets").fetchone()["n"]
    w = con.execute("SELECT COALESCE(SUM(win),0) n FROM casino_bets").fetchone()["n"]; con.close()
    await callback.message.edit_text(
        f"🎰 <b>КАЗИНО</b>\n\nСтавок: {n}\nОборот: {b} SD\nВыплачено: {w} SD\nПрофит: {b-w} SD",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Топ",callback_data="a2g_wins")],
            [InlineKeyboardButton(text="💵 Лимиты",callback_data="a2g_limits")],
            [InlineKeyboardButton(text="◀️ Назад",callback_data="a2_root")]]))
    await callback.answer()

@dp.callback_query(F.data == "a2g_wins")
async def a2g_wins(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT user_id,game,win FROM casino_bets WHERE win>0 ORDER BY win DESC LIMIT 20").fetchall(); con.close()
    txt = "🏆 <b>ТОП</b>\n\n"+"\n".join(f"<code>{r['user_id']}</code> {r['game']} +{r['win']}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.",reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2g_limits")
async def a2g_limits(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    for key,name in [("casino_min","Мин ставка"),("casino_max","Макс ставка"),
        ("casino_max_win","Макс выигрыш"),("casino_loss_limit","Дневной лимит проигрыша"),
        ("duel_min","Мин дуэли"),("duel_commission","Комиссия дуэли")]:
        b.button(text=f"{name}: {get_limit(key)}",callback_data=f"a3le:{key}")
    b.button(text="◀️ Назад",callback_data="a2_casino"); b.adjust(1)
    await callback.message.edit_text("💵 <b>ЛИМИТЫ КАЗИНО</b>\n\nНажми, чтобы изменить:",reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "a2_logs")
async def a2_logs(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT created_at,action,target_user_id FROM admin_logs ORDER BY id DESC LIMIT 30").fetchall(); con.close()
    txt = "📜 <b>ЛОГИ</b>\n\n"+"\n".join(f"{r['created_at'][:19]} {r['action']} {r['target_user_id'] or '-'}" for r in rows)
    await callback.message.edit_text(txt or "Пусто.",reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2_maint")
async def a2_maint(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Бэкап",callback_data="adm_backup")],
        [InlineKeyboardButton(text="🔄 Пересчёт Lv",callback_data="a2m_lvl")],
        [InlineKeyboardButton(text="📊 Записей",callback_data="a2m_count")],
        [InlineKeyboardButton(text="◀️ Назад",callback_data="a2_root")]])
    await callback.message.edit_text("🛠 <b>СЕРВИС</b>",reply_markup=kb); await callback.answer()

@dp.callback_query(F.data == "a2m_lvl")
async def a2m_lvl(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); con.execute("UPDATE users SET level = MAX(1, xp/100 + 1)"); con.commit(); con.close()
    await callback.answer("✅",show_alert=True)

@dp.callback_query(F.data == "a2m_count")
async def a2m_count(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); tables = ["users","cases","items","inventory","case_opens","admin_logs","casino_bets","duels","withdraws"]
    txt = "📊 <b>ЗАПИСЕЙ</b>\n\n"
    for t in tables:
        try:
            n = con.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]; txt += f"{t}: {n}\n"
        except Exception: pass
    con.close(); await callback.message.edit_text(txt,reply_markup=a2_root_kb()); await callback.answer()

@dp.callback_query(F.data == "a2_broadcast")
async def a2_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(A2Broadcast.text); await callback.message.edit_text("📢 Текст:",reply_markup=a2_cancel()); await callback.answer()

@dp.message(StateFilter(A2Broadcast.text))
async def a2_broadcast_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    con = db(); users = con.execute("SELECT user_id FROM users WHERE blocked=0").fetchall(); con.close()
    s,f = 0,0
    for r in users:
        try: await bot.send_message(r["user_id"],message.text or ""); s += 1
        except Exception: f += 1
        await asyncio.sleep(0.05)
    await state.clear(); log_admin("broadcast",details=f"s={s},f={f}")
    await message.answer(f"✅ {s}\n❌ {f}",reply_markup=a2_root_kb())

# ========== ADMIN v3 (ЛИМИТЫ + ЭКОНОМИКА + МАССОВЫЕ) ==========
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

def a3_kb():
    b = InlineKeyboardBuilder()
    for t,d in [("⚙️ Игровые","a3lg:game"),("🎰 Казино","a3lg:casino"),
        ("💰 Деньги","a3lg:money"),("⭐ Пакеты","a3lg:packs"),
        ("🔀 Вкл/выкл","a3lg:toggles"),("📋 Все лимиты","a3l_showall"),
        ("🔄 Сброс лимитов","a3l_resetall"),("◀️ Назад","a2_root")]:
        b.button(text=t,callback_data=d)
    b.adjust(2,2,2,2,1,1,1); return b.as_markup()

def a3_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена",callback_data="a2_root")]])

@dp.callback_query(F.data == "a3_root")
async def a3_root(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.clear()
    await callback.message.edit_text("⚙️ <b>ЛИМИТЫ</b>",reply_markup=a3_kb()); await callback.answer()

@dp.callback_query(F.data.startswith("a3lg:"))
async def a3_lg(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    grp = callback.data.split(":")[1]
    b = InlineKeyboardBuilder()
    for key,name in LIMIT_GROUPS.get(grp,[]):
        b.button(text=f"{name}: {get_limit(key)}",callback_data=f"a3le:{key}")
    b.button(text="◀️ Назад",callback_data="a3_root"); b.adjust(1)
    await callback.message.edit_text("⚙️ Выбери лимит:",reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data.startswith("a3le:"))
async def a3_le(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    key = callback.data.split(":")[1]
    await state.update_data(limit_key=key); await state.set_state(A3Limit.key)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сброс к дефолту",callback_data=f"a3ld:{key}")],
        [InlineKeyboardButton(text="❌ Отмена",callback_data="a2_root")]])
    await callback.message.edit_text(
        f"⚙️ <b>{key}</b>\n\nТекущее: <b>{get_limit(key)}</b>\nДефолт: <b>{LIMIT_DEFAULTS.get(key)}</b>\n\n"
        f"Отправь новое число или /a3d:",reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("a3ld:"))
async def a3_ld(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    key = callback.data.split(":")[1]
    con = db(); con.execute("DELETE FROM settings WHERE key=?",(f"lim_{key}",)); con.commit(); con.close()
    await callback.answer(f"✅ {key} → {LIMIT_DEFAULTS.get(key)}",show_alert=True)

@dp.message(StateFilter(A3Limit.key))
async def a3_le_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = data.get("limit_key")
    txt = (message.text or "").strip()
    if txt == "/a3d":
        con = db()
        con.execute("DELETE FROM settings WHERE key=?", (f"lim_{key}",))
        con.commit()
        con.close()
        await state.clear()
        return await message.answer(f"✅ {key} → default", reply_markup=a3_kb())
    default = LIMIT_DEFAULTS.get(key)
    try:
        if isinstance(default, float):
            val = float(txt.replace(",", "."))
        elif isinstance(default, int):
            val = int(txt)
        else:
            val = txt
    except Exception:
        return await message.answer("❌ Неверный формат. Отправь число или /a3d.")
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
    for grp,items in LIMIT_GROUPS.items():
        txt += f"<b>{grp}</b>\n"
        for k,n in items:
            v = get_limit(k); d = LIMIT_DEFAULTS.get(k)
            mark = "🟢" if v == d else "🟡"
            txt += f"{mark} {n}: <b>{v}</b>\n"
        txt += "\n"
    await callback.message.edit_text(txt,reply_markup=a3_kb()); await callback.answer()

@dp.callback_query(F.data == "a3l_resetall")
async def a3_resetall(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); n = con.execute("DELETE FROM settings WHERE key LIKE 'lim_%'").rowcount; con.commit(); con.close()
    log_admin("reset_all_limits",details=str(n))
    await callback.answer(f"✅ Сброшено {n}.",show_alert=True)

@dp.callback_query(F.data == "a3_econ")
async def a3_econ(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    mass = con.execute("SELECT COALESCE(SUM(sd),0) n FROM users").fetchone()["n"]
    rich = con.execute("SELECT COUNT(*) n FROM users WHERE sd>=10000").fetchone()["n"]
    poor = con.execute("SELECT COUNT(*) n FROM users WHERE sd<100").fetchone()["n"]; con.close()
    b = InlineKeyboardBuilder()
    b.button(text="💣 Обнулить SD всем",callback_data="a3e_wipe")
    b.button(text="🎁 Начислить всем",callback_data="a3e_add")
    b.button(text="➖ Списать у всех",callback_data="a3e_take")
    b.button(text="◀️ Назад",callback_data="a2_root"); b.adjust(1)
    await callback.message.edit_text(
        f"💰 <b>ЭКОНОМИКА</b>\n\nМасса SD: <b>{mass}</b>\n🐋 Богачей: {rich}\n🥚 Бедных: {poor}",
        reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data == "a3e_wipe")
async def a3e_wipe(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ДА",callback_data="a3e_wipe_ok")],
        [InlineKeyboardButton(text="❌ Отмена",callback_data="a3_econ")]])
    await callback.message.edit_text("⚠️ Обнулить SD у всех?",reply_markup=kb); await callback.answer()

@dp.callback_query(F.data == "a3e_wipe_ok")
async def a3e_wipe_ok(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); con.execute("UPDATE users SET sd=0"); con.commit(); con.close()
    log_admin("wipe_all_sd"); await callback.answer("✅ Обнулено.",show_alert=True)

@dp.callback_query(F.data == "a3e_add")
async def a3e_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(mode="add"); await state.set_state(A3Mass.amount)
    await callback.message.edit_text("🎁 Сколько начислить всем?",reply_markup=a3_cancel()); await callback.answer()

@dp.callback_query(F.data == "a3e_take")
async def a3e_take(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.update_data(mode="take"); await state.set_state(A3Mass.amount)
    await callback.message.edit_text("➖ Сколько списать у всех?",reply_markup=a3_cancel()); await callback.answer()

@dp.message(StateFilter(A3Mass.amount))
async def a3_mass_sd(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try: amount = int(message.text)
    except Exception: return await message.answer("❌")
    data = await state.get_data(); mode = data.get("mode")
    con = db()
    if mode == "take": con.execute("UPDATE users SET sd=MAX(0, sd-?)",(amount,))
    else: con.execute("UPDATE users SET sd=sd+?",(amount,))
    con.commit(); con.close()
    log_admin(f"mass_{mode}_sd",details=str(amount)); await state.clear()
    await message.answer(f"✅ {mode} {amount} всем.",reply_markup=a3_kb())

@dp.callback_query(F.data == "a3_mass")
async def a3_mass(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    b = InlineKeyboardBuilder()
    b.button(text="💎 Подписка донатерам",callback_data="a3m_sub")
    b.button(text="🎁 Предмет активным",callback_data="a3m_item")
    b.button(text="🎟 Промо массово",callback_data="a3_promo_mass")
    b.button(text="◀️ Назад",callback_data="a2_root"); b.adjust(1)
    await callback.message.edit_text("🎯 <b>МАССОВЫЕ</b>",reply_markup=b.as_markup()); await callback.answer()

@dp.callback_query(F.data == "a3_promo_mass")
async def a3_promo_mass(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(A3PromoMass.count)
    await callback.message.edit_text("🎟 Сколько промокодов? (1-100)",reply_markup=a3_cancel()); await callback.answer()

@dp.message(StateFilter(A3PromoMass.count))
async def a3_promo_mass_count(message: Message, state: FSMContext):
    try: n = int(message.text)
    except Exception: return
    if n < 1 or n > 100: return await message.answer("❌ 1-100")
    await state.update_data(count=n); await state.set_state(A3PromoMass.reward)
    await message.answer("💰 Сколько SD за каждый?")

@dp.message(StateFilter(A3PromoMass.reward))
async def a3_promo_mass_reward(message: Message, state: FSMContext):
    try: reward = int(message.text)
    except Exception: return
    data = await state.get_data(); codes = []; con = db()
    for _ in range(data["count"]):
        code = "COS"+"".join(random.choices(string.ascii_uppercase+string.digits,k=8))
        try:
            con.execute("INSERT INTO promo_codes(code,reward,max_uses,uses,enabled) VALUES(?,?,1,0,1)",(code,reward))
            codes.append(code)
        except Exception: pass
    con.commit(); con.close(); log_admin("promo_mass",details=f"{data['count']}x{reward}")
    await state.clear()
    txt = f"🎁 <b>Создано {len(codes)}:</b>\n\n"+"\n".join(codes[:30])
    if len(codes) > 30: txt += f"\n...и ещё {len(codes)-30}"
    await message.answer(txt,reply_markup=a3_kb())

@dp.callback_query(F.data == "a3m_sub")
async def a3m_sub(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    until = (datetime.now(timezone.utc)+timedelta(days=30)).isoformat()
    con = db(); n = con.execute("UPDATE users SET sub_until=? WHERE donated>0",(until,)).rowcount
    con.commit(); con.close(); log_admin("mass_sub",details=str(n))
    await callback.answer(f"✅ {n} получили подписку.",show_alert=True)

@dp.callback_query(F.data == "a3m_item")
async def a3m_item(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    week_ago = (datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    con = db()
    item = con.execute("SELECT id FROM items WHERE enabled=1 ORDER BY RANDOM() LIMIT 1").fetchone()
    if not item: con.close(); return await callback.answer("Нет предметов.",show_alert=True)
    users = con.execute("SELECT user_id FROM users WHERE last_activity >= ? AND blocked=0",(week_ago,)).fetchall()
    for u in users:
        con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)",(u["user_id"],item["id"],now()))
    con.commit(); con.close(); log_admin("mass_item",details=f"item={item['id']} n={len(users)}")
    await callback.answer(f"✅ {len(users)} получили предмет.",show_alert=True)

@dp.callback_query(F.data == "a3_export")
async def a3_export(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db(); rows = con.execute("SELECT user_id,username,sd,xp,level,blocked FROM users").fetchall(); con.close()
    path = "export_v3.csv"
    with open(path,"w",encoding="utf-8") as f:
        f.write("user_id,username,sd,xp,level,blocked\n")
        for r in rows: f.write(f"{r['user_id']},{r['username'] or ''},{r['sd']},{r['xp']},{r['level']},{r['blocked']}\n")
    await callback.message.answer_document(FSInputFile(path),caption="📄 Экспорт"); await callback.answer()

@dp.callback_query(F.data == "a3_diag")
async def a3_diag(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    con = db()
    tables = ["users","cases","items","inventory","case_opens","admin_logs",
              "casino_bets","duels","withdraws","promo_codes","settings"]
    txt = "🛠 <b>ДИАГНОСТИКА</b>\n\n"
    for t in tables:
        try:
            n = con.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]; txt += f"{t}: {n}\n"
        except Exception as e: txt += f"❌ {t}: {e}\n"
    con.close(); txt += f"\nDB: <code>{DB_FILE}</code>"
    await callback.message.edit_text(txt,reply_markup=a3_kb()); await callback.answer()

# ========== FALLBACK ==========
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

# ========== MAIN ==========
async def main():
    init_db()
    logging.info("COS-DROP started | DB=%s",DB_FILE)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
