import asyncio, logging, os, random, sqlite3
from datetime import datetime, timezone
from html import escape
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8835340993:AAF4EkJ4R5en0kIgKgMPKKexynFFbMaXqqM"
ADMIN_ID = 8146320391
DB_FILE=os.getenv("DB_FILE","cosdrop.sqlite3")
IMAGE_FILE = "imagemain.png"
if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is not set")
logging.basicConfig(level=logging.INFO)
bot=Bot(BOT_TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML)); dp=Dispatcher()

CASES=[("start","🎒 Старт-кейс","Бесплатный стартовый кейс",0),("basic","📦 Basic Case","Обычный коллекционный кейс",100),("school","🏫 School Case","Школьная коллекция",150),("meme","😂 Meme Case","Мемная коллекция",200),("rare","💎 Rare Case","Упор на редкие категории",300),("epic","🟣 Epic Case","Редкие предметы",500),("night","🌙 Night Case","Ночная коллекция",700),("cos","👑 COS Case","Главный коллекционный кейс",1000)]
ITEMS=[("basic_star","⭐ Star","common"),("basic_blue","🔷 Blue Crystal","rare"),("basic_purple","🟣 Purple Crystal","epic"),("school_pen","🖊️ Золотая ручка","rare"),("backpack","🎒 Космо-рюкзак","epic"),("school_cup","🏆 Кубок класса","legendary"),("meme_skull","💀 Skull","common"),("meme_sigma","🗿 Sigma","rare"),("meme_fire","🔥 Fire","epic"),("rare_diamond","💎 Diamond","rare"),("rare_crown","👑 Silver Crown","epic"),("rare_gold","✨ Golden Badge","legendary"),("epic_galaxy","🌌 Galaxy","epic"),("epic_comet","☄️ Comet","legendary"),("epic_cosmo","🚀 COSMO","mythic"),("night_moon","🌙 Moon","rare"),("night_ghost","👻 Ghost","epic"),("night_eclipse","🌑 Eclipse","legendary"),("cos_crown","👑 COS Crown","legendary"),("cos_galaxy","🌌 COS Galaxy","mythic"),("cos_core","💠 COS Core","mythic")]
DROPS={"start":[("basic_star",50),("school_pen",40),("meme_skull",10)],"basic":[("basic_star",55),("basic_blue",30),("basic_purple",12),("meme_sigma",3)],"school":[("school_pen",60),("backpack",30),("school_cup",10)],"meme":[("meme_skull",60),("meme_sigma",28),("meme_fire",12)],"rare":[("rare_diamond",65),("rare_crown",28),("rare_gold",7)],"epic":[("epic_galaxy",65),("epic_comet",30),("epic_cosmo",5)],"night":[("night_moon",60),("night_ghost",30),("night_eclipse",10)],"cos":[("cos_crown",65),("cos_galaxy",30),("cos_core",5)]}
RARITY={"common":"🟢 Common","rare":"🔵 Rare","epic":"🟣 Epic","legendary":"🟡 Legendary","mythic":"🔴 Mythic"}
class Apply(StatesGroup): name=State(); cls=State(); phone=State(); msg=State()
class Give(StatesGroup): uid=State(); amount=State()
class Broadcast(StatesGroup): text=State()
class Promo(StatesGroup): code=State()
class PromoCreate(StatesGroup): code=State(); reward=State()
class PromoDelete(StatesGroup): code=State()
def now(): return datetime.now(timezone.utc).isoformat()
def db(): c=sqlite3.connect(DB_FILE); c.row_factory=sqlite3.Row; return c

def init_db():
 c=db(); x=c.cursor(); x.executescript('''
 CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE,username TEXT,first_name TEXT,sd INTEGER DEFAULT 500,xp INTEGER DEFAULT 0,level INTEGER DEFAULT 1,blocked INTEGER DEFAULT 0,created_at TEXT,last_activity TEXT,daily_claim TEXT);
 CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,name TEXT,description TEXT,price INTEGER,enabled INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,name TEXT,rarity TEXT,enabled INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS case_items(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id INTEGER,item_id INTEGER,chance REAL,UNIQUE(case_id,item_id));
 CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,item_id INTEGER,obtained_at TEXT);
 CREATE TABLE IF NOT EXISTS case_opens(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,case_id INTEGER,item_id INTEGER,created_at TEXT);
 CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,kind TEXT,name TEXT,class_name TEXT,phone TEXT,message TEXT,status TEXT DEFAULT 'pending',admin_id INTEGER,created_at TEXT,decided_at TEXT);
 CREATE TABLE IF NOT EXISTS promo_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE,reward INTEGER,max_uses INTEGER,uses INTEGER DEFAULT 0,enabled INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS promo_uses(id INTEGER PRIMARY KEY AUTOINCREMENT,promo_id INTEGER,user_id INTEGER,used_at TEXT,UNIQUE(promo_id,user_id));
 CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY,role TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS admin_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,admin_id INTEGER,action TEXT,target_user_id INTEGER,details TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);''')
 x.execute("INSERT OR IGNORE INTO admins VALUES(?,?,?)",(ADMIN_ID,"owner",now()))
 for a,b,d,p in CASES:x.execute("INSERT OR IGNORE INTO cases(code,name,description,price) VALUES(?,?,?,?)",(a,b,d,p))
 for a,b,r in ITEMS:x.execute("INSERT OR IGNORE INTO items(code,name,rarity) VALUES(?,?,?)",(a,b,r))
 for cc,ds in DROPS.items():
  cr=x.execute("SELECT id FROM cases WHERE code=?",(cc,)).fetchone()
  for ic,ch in ds:
   ir=x.execute("SELECT id FROM items WHERE code=?",(ic,)).fetchone()
   x.execute("INSERT OR IGNORE INTO case_items(case_id,item_id,chance) VALUES(?,?,?)",(cr[0],ir[0],ch))
 c.commit(); c.close()
def ensure(u):
 c=db(); r=c.execute("SELECT * FROM users WHERE user_id=?",(u.id,)).fetchone()
 if r:c.execute("UPDATE users SET username=?,first_name=?,last_activity=? WHERE user_id=?",(u.username,u.first_name or '',now(),u.id))
 else:c.execute("INSERT INTO users(user_id,username,first_name,created_at,last_activity) VALUES(?,?,?,?,?)",(u.id,u.username,u.first_name or '',now(),now()))
 c.commit(); r=c.execute("SELECT * FROM users WHERE user_id=?",(u.id,)).fetchone(); c.close(); return r
def home_kb():
 b=InlineKeyboardBuilder()
 for t,d in [("🎮 Играть","play"),("👤 Профиль","profile"),("💰 Баланс","balance"),("🎒 Коллекция","collection"),("🏆 Рейтинг","rating"),("🎟 Промокод","promo"),("📝 Заявки","apps"),("ℹ️ Обо мне","about")]:b.button(text=t,callback_data=d)
 b.adjust(1,2,2,2,1); return b.as_markup()
def back():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад",callback_data="home")]])
@dp.message(Command("start"))
async def start(m):
 u=ensure(m.from_user)
 if u['blocked']:return await m.answer("🚫 Ваш аккаунт заблокирован.")
 if os.path.isfile(IMAGE_FILE) and os.path.getsize(IMAGE_FILE)>0:
  try:await m.answer_photo(FSInputFile(IMAGE_FILE),caption="✨ <b>COS-DROP</b>\n\nДобро пожаловать!")
  except Exception:logging.exception("image")
 await m.answer(f"🎁 <b>COS-DROP</b>\n\n💰 SD: <b>{u['sd']}</b>\n⭐ Уровень: <b>{u['level']}</b>\n\nВыбери раздел:",reply_markup=home_kb())
@dp.callback_query(F.data=='home')
async def home(c):
 u=ensure(c.from_user); await c.message.edit_text(f"🎁 <b>COS-DROP</b>\n\n💰 SD: <b>{u['sd']}</b>\n⭐ Уровень: <b>{u['level']}</b>",reply_markup=home_kb()); await c.answer()
@dp.callback_query(F.data=='play')
async def play(c):
 con=db(); rs=con.execute("SELECT * FROM cases WHERE enabled=1 ORDER BY id").fetchall();con.close();b=InlineKeyboardBuilder()
 for r in rs:b.button(text=f"{r['name']} · {r['price']} SD",callback_data=f"case:{r['id']}")
 b.button(text="◀️ Назад",callback_data="home");b.adjust(1);await c.message.edit_text("🎮 <b>КЕЙСЫ</b>\n\nВыбери кейс:",reply_markup=b.as_markup());await c.answer()
@dp.callback_query(F.data.startswith('case:'))
async def case(c):
 con=db();r=con.execute("SELECT * FROM cases WHERE id=? AND enabled=1",(int(c.data.split(':')[1]),)).fetchone();con.close()
 if not r:return await c.answer("Кейс недоступен",show_alert=True)
 b=InlineKeyboardBuilder();b.button(text="🎁 Открыть",callback_data=f"open:{r['id']}");b.button(text="◀️ Назад",callback_data="play")
 await c.message.edit_text(f"📦 <b>{escape(r['name'])}</b>\n\n{escape(r['description'])}\n\n💰 Стоимость: <b>{r['price']} SD</b>",reply_markup=b.as_markup());await c.answer()
@dp.callback_query(F.data.startswith('open:'))
async def open_case(c):
 u=ensure(c.from_user);cid=int(c.data.split(':')[1]);con=db();ca=con.execute("SELECT * FROM cases WHERE id=? AND enabled=1",(cid,)).fetchone()
 if not ca:con.close();return await c.answer("Кейс недоступен",show_alert=True)
 if u['sd']<ca['price']:con.close();return await c.answer("Недостаточно SD",show_alert=True)
 rs=con.execute("SELECT i.*,ci.chance FROM case_items ci JOIN items i ON i.id=ci.item_id WHERE ci.case_id=? AND i.enabled=1",(cid,)).fetchall()
 it=random.choices(rs,weights=[r['chance'] for r in rs],k=1)[0]
 con.execute("UPDATE users SET sd=sd-?,xp=xp+10,last_activity=? WHERE user_id=?",(ca['price'],now(),c.from_user.id));con.execute("INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)",(c.from_user.id,it['id'],now()));con.execute("INSERT INTO case_opens(user_id,case_id,item_id,created_at) VALUES(?,?,?,?)",(c.from_user.id,cid,it['id'],now()));con.commit();con.close()
 await c.message.edit_text(f"✨ <b>ОТКРЫТИЕ</b>\n\n{RARITY.get(it['rarity'],'⚪')}\n<b>{escape(it['name'])}</b>\n\n🎒 Предмет добавлен в коллекцию!",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎮 Ещё",callback_data="play")],[InlineKeyboardButton(text="🎒 Коллекция",callback_data="collection")],[InlineKeyboardButton(text="🏠 Меню",callback_data="home")]]));await c.answer()
@dp.callback_query(F.data=='profile')
async def profile(c):
 u=ensure(c.from_user);con=db();items=con.execute("SELECT COUNT(*) n FROM inventory WHERE user_id=?",(u['user_id'],)).fetchone()['n'];opens=con.execute("SELECT COUNT(*) n FROM case_opens WHERE user_id=?",(u['user_id'],)).fetchone()['n'];con.close();await c.message.edit_text(f"👤 <b>ПРОФИЛЬ</b>\n\nID: <code>{u['user_id']}</code>\nUsername: @{escape(u['username'] or 'нет')}\n\n💰 SD: <b>{u['sd']}</b>\n⭐ Уровень: <b>{u['level']}</b>\n✨ XP: <b>{u['xp']}</b>\n\n🎁 Открыто: <b>{opens}</b>\n🎒 Предметов: <b>{items}</b>",reply_markup=back());await c.answer()
@dp.callback_query(F.data=='balance')
async def balance(c):
 u=ensure(c.from_user);await c.message.edit_text(f"💰 <b>БАЛАНС</b>\n\nТвой баланс: <b>{u['sd']} SD</b>\n\nSD — виртуальная валюта Cos-drop. Она не выводится и не обменивается на деньги.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Ежедневный бонус",callback_data="daily")],[InlineKeyboardButton(text="🎟 Промокод",callback_data="promo")],[InlineKeyboardButton(text="◀️ Назад",callback_data="home")]]));await c.answer()
@dp.callback_query(F.data=='daily')
async def daily(c):
 con=db();r=con.execute("SELECT daily_claim FROM users WHERE user_id=?",(c.from_user.id,)).fetchone();today=datetime.now(timezone.utc).date().isoformat()
 if r and r['daily_claim']==today:con.close();return await c.answer("Бонус уже получен сегодня",show_alert=True)
 con.execute("UPDATE users SET sd=sd+100,daily_claim=?,last_activity=? WHERE user_id=?",(today,now(),c.from_user.id));con.commit();con.close();await c.answer("🎁 +100 SD!",show_alert=True);await balance(c)
@dp.callback_query(F.data=='collection')
async def collection(c):
 con=db();rs=con.execute("SELECT i.name,i.rarity,COUNT(*) n FROM inventory inv JOIN items i ON i.id=inv.item_id WHERE inv.user_id=? GROUP BY inv.item_id",(c.from_user.id,)).fetchall();con.close();txt="🎒 <b>КОЛЛЕКЦИЯ</b>\n\n"+(("\n".join(f"{RARITY.get(r['rarity'],'⚪')} {escape(r['name'])} ×{r['n']}" for r in rs)) if rs else "Пока пусто.");await c.message.edit_text(txt,reply_markup=back());await c.answer()
@dp.callback_query(F.data=='rating')
async def rating(c):
 con=db();rs=con.execute("SELECT username,first_name,xp,(SELECT COUNT(*) FROM inventory i WHERE i.user_id=u.user_id) items FROM users u WHERE blocked=0 ORDER BY xp DESC,items DESC LIMIT 10").fetchall();con.close();txt="🏆 <b>ТОП-10</b>\n\n"+"\n".join(f"{i}. @{escape(r['username'] or r['first_name'] or '-')} — ⭐ {r['xp']} · 🎒 {r['items']}" for i,r in enumerate(rs,1));await c.message.edit_text(txt,reply_markup=back());await c.answer()
@dp.callback_query(F.data=='about')
async def about(c):await c.message.edit_text("ℹ️ <b>О COS-DROP</b>\n\nКоллекционный Telegram-проект с кейсами, предметами, профилями и рейтингами.\n\nВсе SD и предметы виртуальные и не имеют денежной стоимости.",reply_markup=back());await c.answer()
@dp.callback_query(F.data=='apps')
async def apps(c):
 con=db();rs=con.execute("SELECT id,kind,status FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 10",(c.from_user.id,)).fetchall();con.close();txt="📝 <b>МОИ ЗАЯВКИ</b>\n\n"+(("\n".join(f"#{r['id']} · {r['kind']} · {r['status']}" for r in rs)) if rs else "Заявок пока нет.");await c.message.edit_text(txt,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📝 Создать заявку",callback_data="newapp")],[InlineKeyboardButton(text="◀️ Назад",callback_data="home")]]));await c.answer()
@dp.callback_query(F.data=='newapp')
async def newapp(c,state):await state.set_state(Apply.name);await c.message.edit_text("📝 <b>ЗАЯВКА</b>\n\nВведите имя:");await c.answer()
@dp.message(StateFilter(Apply.name))
async def an(m,state):await state.update_data(name=(m.text or '')[:100]);await state.set_state(Apply.cls);await m.answer("🏫 Введите класс:")
@dp.message(StateFilter(Apply.cls))
async def ac(m,state):await state.update_data(cls=(m.text or '')[:30]);await state.set_state(Apply.phone);await m.answer("📱 Контакт для связи (по желанию):")
@dp.message(StateFilter(Apply.phone))
async def ap(m,state):await state.update_data(phone=(m.text or '')[:50]);await state.set_state(Apply.msg);await m.answer("💬 Напишите сообщение:")
@dp.message(StateFilter(Apply.msg))
async def am(m,state):
 d=await state.update_data(msg=(m.text or '')[:1000]);con=db();cur=con.execute("INSERT INTO applications(user_id,kind,name,class_name,phone,message,created_at) VALUES(?,?,?,?,?,?,?)",(m.from_user.id,'general',d['name'],d['cls'],d['phone'],d['msg'],now()));aid=cur.lastrowid;con.commit();con.close();await state.clear();await m.answer(f"✅ Заявка <b>#{aid}</b> создана.")
 try:await bot.send_message(ADMIN_ID,f"📝 <b>ЗАЯВКА #{aid}</b>\n\n👤 {escape(d['name'])}\n🏫 {escape(d['cls'])}\n📱 {escape(d['phone'])}\n💬 {escape(d['msg'])}\n🆔 <code>{m.from_user.id}</code>",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Принять',callback_data=f'appok:{aid}'),InlineKeyboardButton(text='❌ Отклонить',callback_data=f'appno:{aid}')]]))
 except Exception:logging.exception('admin notification')
@dp.callback_query(F.data.startswith('appok:'))
async def appok(c):
 if c.from_user.id!=ADMIN_ID:return
 aid=int(c.data.split(':')[1]);con=db();r=con.execute("SELECT * FROM applications WHERE id=?",(aid,)).fetchone();con.execute("UPDATE applications SET status='approved',admin_id=?,decided_at=? WHERE id=?",(ADMIN_ID,now(),aid));con.commit();con.close();await c.message.edit_reply_markup(reply_markup=None);await c.answer('Заявка принята');
 if r:await bot.send_message(r['user_id'],f'✅ Ваша заявка #{aid} принята.')
@dp.callback_query(F.data.startswith('appno:'))
async def appno(c):
 if c.from_user.id!=ADMIN_ID:return
 aid=int(c.data.split(':')[1]);con=db();r=con.execute("SELECT * FROM applications WHERE id=?",(aid,)).fetchone();con.execute("UPDATE applications SET status='rejected',admin_id=?,decided_at=? WHERE id=?",(ADMIN_ID,now(),aid));con.commit();con.close();await c.message.edit_reply_markup(reply_markup=None);await c.answer('Заявка отклонена');
 if r:await bot.send_message(r['user_id'],f'❌ Ваша заявка #{aid} отклонена.')
@dp.callback_query(F.data=='promo')
async def promo(c,state):await state.set_state(Promo.code);await c.message.edit_text('🎟 <b>ПРОМОКОД</b>\n\nВведите код:');await c.answer()
@dp.message(StateFilter(Promo.code))
async def usepromo(m,state):
 code=(m.text or '').strip().upper();con=db();p=con.execute("SELECT * FROM promo_codes WHERE code=? AND enabled=1",(code,)).fetchone()
 if not p:con.close();await state.clear();return await m.answer('❌ Промокод не найден.')
 used=con.execute("SELECT 1 FROM promo_uses WHERE promo_id=? AND user_id=?",(p['id'],m.from_user.id)).fetchone()
 if used or p['uses']>=p['max_uses']:con.close();await state.clear();return await m.answer('❌ Промокод уже использован или закончился.')
 con.execute("INSERT INTO promo_uses(promo_id,user_id,used_at) VALUES(?,?,?)",(p['id'],m.from_user.id,now()));con.execute("UPDATE promo_codes SET uses=uses+1 WHERE id=?",(p['id'],));con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(p['reward'],m.from_user.id));con.commit();con.close();await state.clear();await m.answer(f"🎉 Промокод активирован!\n💰 +{p['reward']} SD")
def admkb():
 b=InlineKeyboardBuilder()
 for t,d in [("📊 Статистика","adm_stats"),("👥 Пользователи","adm_users"),("📩 Заявки","adm_apps"),("📢 Рассылка","adm_broadcast"),("💰 Выдать SD","adm_give"),("🎟 Промокоды","adm_promo"),("📜 Логи","adm_logs")]:b.button(text=t,callback_data=d)
 b.adjust(2);return b.as_markup()
def admin(u):return u.id==ADMIN_ID
@dp.message(Command('admin'))
async def admin_cmd(m):
 if admin(m.from_user):await m.answer('🛠 <b>COS-DROP ADMIN</b>\n\nВыбери раздел:',reply_markup=admkb())
@dp.callback_query(F.data=='adm_stats')
async def ast(c):
 if not admin(c.from_user):return
 con=db();a=[con.execute(q).fetchone()['n'] for q in ["SELECT COUNT(*) n FROM users","SELECT COUNT(*) n FROM case_opens","SELECT COUNT(*) n FROM inventory","SELECT COUNT(*) n FROM applications WHERE status='pending'"]];con.close();await c.message.edit_text(f"📊 <b>СТАТИСТИКА</b>\n\n👥 {a[0]} пользователей\n🎁 {a[1]} открытий\n🎒 {a[2]} предметов\n📝 {a[3]} заявок ждут решения",reply_markup=admkb());await c.answer()
@dp.callback_query(F.data=='adm_users')
async def aus(c):
 if not admin(c.from_user):return
 con=db();rs=con.execute("SELECT user_id,username,sd,level FROM users ORDER BY id DESC LIMIT 20").fetchall();con.close();txt='👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n'+"\n".join(f"<code>{r['user_id']}</code> @{escape(r['username'] or '-')} · {r['sd']} SD · Lv.{r['level']}" for r in rs);await c.message.edit_text(txt,reply_markup=admkb());await c.answer()
@dp.callback_query(F.data=='adm_apps')
async def aapps(c):
 if not admin(c.from_user):return
 con=db();rs=con.execute("SELECT id,user_id,name,class_name,status FROM applications ORDER BY id DESC LIMIT 20").fetchall();con.close();txt='📩 <b>ЗАЯВКИ</b>\n\n'+("\n".join(f"#{r['id']} · <code>{r['user_id']}</code> · {escape(r['name'] or '-')} · {r['status']}" for r in rs) or 'Нет заявок.');await c.message.edit_text(txt,reply_markup=admkb());await c.answer()
@dp.callback_query(F.data=='adm_give')
async def ag(c,state):
 if not admin(c.from_user):return
 await state.set_state(Give.uid);await c.message.edit_text('Введите Telegram ID пользователя:');await c.answer()
@dp.message(StateFilter(Give.uid))
async def aguid(m,state):
 try:uid=int(m.text)
 except: return await m.answer('Неверный ID.')
 await state.update_data(uid=uid);await state.set_state(Give.amount);await m.answer('Введите количество SD:')
@dp.message(StateFilter(Give.amount))
async def agamt(m,state):
 try:a=int(m.text)
 except:return await m.answer('Введите целое число.')
 d=await state.get_data();con=db();con.execute("UPDATE users SET sd=sd+? WHERE user_id=?",(a,d['uid']));con.execute("INSERT INTO admin_logs(admin_id,action,target_user_id,details,created_at) VALUES(?,?,?,?,?)",(ADMIN_ID,'give_sd',d['uid'],str(a),now()));con.commit();con.close();await state.clear();await m.answer(f'✅ Начислено {a} SD пользователю {d["uid"]}.')
@dp.callback_query(F.data=='adm_broadcast')
async def ab(c,state):
 if not admin(c.from_user):return
 await state.set_state(Broadcast.text);await c.message.edit_text('Введите текст рассылки:');await c.answer()
@dp.message(StateFilter(Broadcast.text))
async def absend(m,state):
 if not admin(m.from_user):return
 con=db();rs=con.execute('SELECT user_id FROM users WHERE blocked=0').fetchall();con.close();ok=bad=0
 for r in rs:
  try:await bot.send_message(r['user_id'],m.text or '');ok+=1
  except:bad+=1
  await asyncio.sleep(.04)
 await state.clear();await m.answer(f'📢 Готово.\n\n✅ {ok}\n❌ {bad}')
@dp.callback_query(F.data=='adm_promo')
async def apromo(c):
 if not admin(c.from_user):return
 con=db();rs=con.execute('SELECT code,reward,uses,max_uses FROM promo_codes WHERE enabled=1 ORDER BY id DESC').fetchall();con.close()
 txt='🎟 <b>ПРОМОКОДЫ</b>\n\n'
 if rs:
  txt+='\n'.join(f'🔹 <code>{escape(r["code"])}</code> — +{r["reward"]} SD · {r["uses"]}/{r["max_uses"]}' for r in rs)
 else: txt+='Промокодов пока нет.'
 kb=InlineKeyboardMarkup(inline_keyboard=[
  [InlineKeyboardButton(text='➕ Добавить промокод',callback_data='promo_add')],
  [InlineKeyboardButton(text='🗑 Удалить промокод',callback_data='promo_del')],
  [InlineKeyboardButton(text='🔄 Обновить',callback_data='adm_promo')],
  [InlineKeyboardButton(text='◀️ Админ-панель',callback_data='admin_home')]
 ])
 await c.message.edit_text(txt,reply_markup=kb);await c.answer()

@dp.callback_query(F.data=='promo_add')
async def promo_add(c,state):
 if not admin(c.from_user):return
 await state.set_state(PromoCreate.code)
 await c.message.edit_text('➕ <b>СОЗДАНИЕ ПРОМОКОДА</b>\n\nНапиши название промокода, которое будут вводить пользователи.\n\nНапример: <code>SUMMER2026</code>')
 await c.answer()

@dp.message(StateFilter(PromoCreate.code))
async def promo_add_code(m,state):
 code=(m.text or '').strip().upper()
 if not code or len(code)>50 or not code.replace('_','').replace('-','').isalnum():
  return await m.answer('❌ Используй только латинские буквы, цифры, <code>_</code> или <code>-</code>.')
 con=db();exists=con.execute('SELECT 1 FROM promo_codes WHERE code=?',(code,)).fetchone();con.close()
 if exists:return await m.answer('❌ Такой промокод уже существует. Напиши другой:')
 await state.update_data(code=code);await state.set_state(PromoCreate.reward)
 await m.answer(f'Промокод: <code>{escape(code)}</code>\n\n💰 Сколько SD он будет давать? Напиши число:')

@dp.message(StateFilter(PromoCreate.reward))
async def promo_add_reward(m,state):
 try: reward=int((m.text or '').strip())
 except ValueError:return await m.answer('❌ Напиши целое число, например <code>500</code>.')
 if reward<=0 or reward>100000000:return await m.answer('❌ Сумма должна быть от 1 до 100000000 SD.')
 data=await state.get_data();con=db()
 try:
  con.execute('INSERT INTO promo_codes(code,reward,max_uses,uses,enabled) VALUES(?,?,999999999,0,1)',(data['code'],reward))
  con.execute('INSERT INTO admin_logs(admin_id,action,details,created_at) VALUES(?,?,?,?)',(ADMIN_ID,'create_promo',f'{data["code"]} +{reward} SD',now()))
  con.commit()
 except sqlite3.IntegrityError:
  con.close();await state.clear();return await m.answer('❌ Такой промокод уже существует.')
 con.close();await state.clear()
 await m.answer(f'✅ Промокод <code>{escape(data["code"])}</code> создан!\n💰 Награда: <b>+{reward} SD</b>\n♾ Использований: без ограничений для каждого пользователя один раз.')

@dp.callback_query(F.data=='promo_del')
async def promo_del(c,state):
 if not admin(c.from_user):return
 con=db();rs=con.execute('SELECT code,reward,uses FROM promo_codes WHERE enabled=1 ORDER BY id DESC').fetchall();con.close()
 if not rs:return await c.answer('Удалять пока нечего',show_alert=True)
 txt='🗑 <b>УДАЛЕНИЕ ПРОМОКОДА</b>\n\n'+'\n'.join(f'• <code>{escape(r["code"])}</code> — +{r["reward"]} SD · использован {r["uses"]} раз' for r in rs)+'\n\nНапиши название промокода, который удалить:'
 await state.set_state(PromoDelete.code);await c.message.edit_text(txt);await c.answer()

@dp.message(StateFilter(PromoDelete.code))
async def promo_del_code(m,state):
 code=(m.text or '').strip().upper();con=db();p=con.execute('SELECT * FROM promo_codes WHERE code=? AND enabled=1',(code,)).fetchone()
 if not p:
  con.close();return await m.answer('❌ Активный промокод с таким названием не найден. Напиши ещё раз:')
 con.execute('DELETE FROM promo_uses WHERE promo_id=?',(p['id'],))
 con.execute('DELETE FROM promo_codes WHERE id=?',(p['id'],))
 con.execute('INSERT INTO admin_logs(admin_id,action,details,created_at) VALUES(?,?,?,?)',(ADMIN_ID,'delete_promo',code,now()))
 con.commit();con.close();await state.clear();await m.answer(f'🗑 Промокод <code>{escape(code)}</code> удалён.')

@dp.callback_query(F.data=='admin_home')
async def admin_home(c):
 if not admin(c.from_user):return
 await c.message.edit_text('🛠 <b>COS-DROP ADMIN</b>\n\nВыбери раздел:',reply_markup=admkb());await c.answer()
@dp.callback_query(F.data=='adm_logs')
async def alogs(c):
 if not admin(c.from_user):return
 con=db();rs=con.execute('SELECT * FROM admin_logs ORDER BY id DESC LIMIT 20').fetchall();con.close();txt='📜 <b>ЛОГИ</b>\n\n'+("\n".join(f"{r['created_at'][:19]} · {escape(r['action'])} · {r['target_user_id'] or '-'}" for r in rs) or 'Пусто.');await c.message.edit_text(txt,reply_markup=admkb());await c.answer()
async def main():init_db();logging.info('Cos-drop started');await dp.start_polling(bot)
if __name__=='__main__':asyncio.run(main())
