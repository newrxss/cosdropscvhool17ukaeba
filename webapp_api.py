import os, json, hmac, hashlib, sqlite3, random, secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qsl
from aiohttp import web

BASE = Path(__file__).resolve().parent
DB_FILE = os.getenv('DB_FILE', '/data/cosdrop.sqlite3' if os.path.isdir('/data') else str(BASE/'cosdrop.sqlite3'))
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
WEB_DIR = BASE / 'web'

CASES = [
 ('start','🎒 Старт','Стартовый',0),('basic','📦 Basic','Обычный',100),('school','🏫 School','Школьная',150),
 ('meme','😂 Meme','Мемы',200),('rare','💎 Rare','Редкие',300),('epic','🟣 Epic','Эпик',500),
 ('night','🌙 Night','Ночь',700),('cos','👑 COS','Главный',1000)]
RARITY = {'common':'🟢 Common','rare':'🔵 Rare','epic':'🟣 Epic','legendary':'🟡 Legendary','mythic':'🔴 Mythic'}
SLOT_SYMBOLS = ['🍒','🍋','🔔','💎','7️⃣','⭐']
SLOT_PAYOUTS = {('🍒','🍒','🍒'):3,('🍋','🍋','🍋'):4,('🔔','🔔','🔔'):6,('💎','💎','💎'):12,('7️⃣','7️⃣','7️⃣'):25,('⭐','⭐','⭐'):50}
LIMITS = {'starter_sd':100,'daily_base':50,'daily_streak_7':300,'daily_streak_30':2000,'case_cooldown':3,'sell_commission':0.10,'upgrade_chance':0.60,'casino_min':10,'casino_max':10000,'casino_max_win':50000,'casino_loss_limit':5000,'duel_min':100,'duel_commission':0.05,'ref_invite':500,'ref_donate':2000}


def db():
    c=sqlite3.connect(DB_FILE); c.row_factory=sqlite3.Row; return c

def now(): return datetime.now(timezone.utc).isoformat()
def today(): return datetime.now(timezone.utc).date().isoformat()

def limit(c,key):
    default=LIMITS.get(key,0)
    r=c.execute('SELECT value FROM settings WHERE key=?',(f'lim_{key}',)).fetchone()
    if not r:return default
    try:return float(r['value']) if isinstance(default,float) else int(r['value'])
    except:return default

def validate_init_data(init_data):
    if not init_data or not BOT_TOKEN:return None
    try:
        pairs=dict(parse_qsl(init_data, keep_blank_values=True))
        received=pairs.pop('hash',None)
        if not received:return None
        check='\n'.join(f'{k}={pairs[k]}' for k in sorted(pairs))
        secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest()
        expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,received):return None
        user=json.loads(pairs.get('user','{}'))
        if not user.get('id'):return None
        auth_date=int(pairs.get('auth_date','0'))
        if abs(int(datetime.now(timezone.utc).timestamp())-auth_date)>86400:return None
        return user
    except Exception:return None

async def auth(request):
    user=validate_init_data(request.headers.get('X-Telegram-Init-Data',''))
    if not user: raise web.HTTPUnauthorized(text=json.dumps({'ok':False,'error':'Открой сайт через кнопку Web App в Telegram-боте.'}, ensure_ascii=False),content_type='application/json')
    # The bot and Web App share DB_FILE; respect the same account block flag.
    try:
        c=db()
        row=c.execute('SELECT blocked FROM users WHERE user_id=?',(int(user['id']),)).fetchone()
        c.close()
        if row and row['blocked']:
            raise web.HTTPForbidden(text=json.dumps({'ok':False,'error':'Аккаунт заблокирован.'},ensure_ascii=False),content_type='application/json')
    except web.HTTPForbidden:
        raise
    except sqlite3.Error:
        # During initial boot the bot creates/migrates the database before serving requests.
        pass
    return user

def ensure_user(c,u):
    uid=int(u['id']); row=c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone()
    if row:
        c.execute('UPDATE users SET username=?, first_name=?, last_activity=? WHERE user_id=?',(u.get('username'),u.get('first_name',''),now(),uid)); c.commit()
        return c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone()
    c.execute('INSERT INTO users(user_id,username,first_name,sd,xp,level,blocked,created_at,last_activity) VALUES(?,?,?,?,?,?,?,?,?)',(uid,u.get('username'),u.get('first_name',''),limit(c,'starter_sd'),0,1,0,now(),now())); c.commit()
    return c.execute('SELECT * FROM users WHERE user_id=?',(uid,)).fetchone()

def public_user(c,u):
    uid=u['user_id']
    inv=c.execute('SELECT COUNT(*) n FROM inventory WHERE user_id=?',(uid,)).fetchone()['n']
    opens=c.execute('SELECT COUNT(*) n FROM case_opens WHERE user_id=?',(uid,)).fetchone()['n']
    ach=c.execute('SELECT COUNT(*) n FROM user_achievements WHERE user_id=?',(uid,)).fetchone()['n']
    refs=c.execute('SELECT COUNT(*) n FROM users WHERE referrer_id=?',(uid,)).fetchone()['n']
    return {'id':uid,'username':u['username'],'first_name':u['first_name'],'sd':u['sd'],'xp':u['xp'],'level':u['level'],'inventory':inv,'opens':opens,'achievements':ach,'referrals':refs,'premium':bool(u['sub_until'] and datetime.fromisoformat(u['sub_until'])>datetime.now(timezone.utc))}

async def me(request):
    tg=await auth(request); c=db(); u=ensure_user(c,tg); data=public_user(c,u); c.close(); return web.json_response({'ok':True,'user':data})

async def dashboard(request):
    tg=await auth(request); c=db(); u=ensure_user(c,tg)
    cases=[dict(x) for x in c.execute('SELECT id,code,name,description,price,enabled FROM cases ORDER BY id').fetchall() if x['enabled']]
    items=[dict(x) for x in c.execute('SELECT id,code,name,rarity,sell_price,enabled FROM items WHERE enabled=1 ORDER BY id').fetchall()]
    inv=c.execute('SELECT i.id,i.code,i.name,i.rarity,i.sell_price,COUNT(*) count FROM inventory v JOIN items i ON i.id=v.item_id WHERE v.user_id=? GROUP BY i.id ORDER BY i.id',(u['user_id'],)).fetchall()
    rating=[dict(x) for x in c.execute('SELECT user_id,username,sd,level,xp FROM users WHERE blocked=0 ORDER BY sd DESC LIMIT 50').fetchall()]
    achievements=[dict(x) for x in c.execute('SELECT a.id,a.code,a.name,a.description,a.reward,ua.obtained_at FROM achievements a LEFT JOIN user_achievements ua ON ua.achievement_id=a.id AND ua.user_id=? ORDER BY a.id',(u['user_id'],)).fetchall()]
    tasks=[dict(x) for x in c.execute('SELECT t.*,ut.progress,ut.done FROM tasks t LEFT JOIN user_tasks ut ON ut.task_id=t.id AND ut.user_id=? AND ut.date=? ORDER BY t.id',(u['user_id'],today())).fetchall()]
    c.close(); return web.json_response({'ok':True,'user':public_user(db_user:=db(),u) if False else public_user_from_cached(cases,u,inv,achievements,rating,tasks),'cases':cases,'items':items,'inventory':[dict(x) for x in inv],'rating':rating,'achievements':achievements,'tasks':tasks})

def public_user_from_cached(cases,u,inv,achievements,rating,tasks):
    return {'id':u['user_id'],'username':u['username'],'first_name':u['first_name'],'sd':u['sd'],'xp':u['xp'],'level':u['level'],'inventory':sum(x['count'] for x in inv),'opens':0,'achievements':sum(1 for x in achievements if x['obtained_at']),'referrals':0,'premium':bool(u['sub_until'] and datetime.fromisoformat(u['sub_until'])>datetime.now(timezone.utc))}

async def cases(request):
    tg=await auth(request); c=db(); ensure_user(c,tg); rows=c.execute('SELECT id,code,name,description,price,enabled FROM cases WHERE enabled=1 ORDER BY id').fetchall(); c.close(); return web.json_response({'ok':True,'cases':[dict(r) for r in rows]})

async def open_case(request):
    tg=await auth(request); body=await request.json(); code=str(body.get('code','')); c=db(); u=ensure_user(c,tg)
    case=c.execute('SELECT * FROM cases WHERE code=? AND enabled=1',(code,)).fetchone()
    if not case:return web.json_response({'ok':False,'error':'Case not found'},status=404)
    if case['price']>u['sd']:return web.json_response({'ok':False,'error':'Недостаточно SD'},status=400)
    if u['last_case_at']:
        try:
            if (datetime.now(timezone.utc)-datetime.fromisoformat(u['last_case_at'])).total_seconds()<limit(c,'case_cooldown'):return web.json_response({'ok':False,'error':'Подожди перед следующим открытием'},status=429)
        except:pass
    drops=c.execute('SELECT ci.chance,i.* FROM case_items ci JOIN items i ON i.id=ci.item_id WHERE ci.case_id=? AND i.enabled=1',(case['id'],)).fetchall()
    if not drops:return web.json_response({'ok':False,'error':'В кейсе нет предметов'},status=400)
    pick=random.uniform(0,sum(float(x['chance']) for x in drops)); acc=0; item=drops[-1]
    for x in drops:
        acc+=float(x['chance'])
        if pick<=acc:item=x;break
    c.execute('UPDATE users SET sd=sd-?,xp=xp+5,last_case_at=?,last_activity=? WHERE user_id=?',(case['price'],now(),now(),u['user_id']))
    c.execute('INSERT INTO inventory(user_id,item_id,obtained_at) VALUES(?,?,?)',(u['user_id'],item['id'],now()))
    c.execute('INSERT INTO case_opens(user_id,case_id,item_id,created_at) VALUES(?,?,?,?)',(u['user_id'],case['id'],item['id'],now()))
    c.execute('UPDATE users SET level=? WHERE user_id=?',(max(1,(u['xp']+5)//100+1),u['user_id'])); c.commit(); c.close()
    return web.json_response({'ok':True,'item':{'id':item['id'],'name':item['name'],'rarity':item['rarity'],'sell_price':item['sell_price']},'sd':u['sd']-case['price']})

async def daily(request):
    tg=await auth(request); c=db(); u=ensure_user(c,tg); t=today()
    if u['daily_claim']==t:c.close(); return web.json_response({'ok':False,'error':'Бонус уже получен'},status=400)
    streak=u['daily_streak'] or 0
    if u['daily_claim']:
        try:
            if (datetime.now(timezone.utc).date()-datetime.fromisoformat(u['daily_claim']).date()).days!=1:streak=0
        except:streak=0
    streak+=1; reward=limit(c,'daily_base')
    if streak>=30:reward+=limit(c,'daily_streak_30')
    elif streak>=7:reward+=limit(c,'daily_streak_7')
    if u['sub_until'] and datetime.fromisoformat(u['sub_until'])>datetime.now(timezone.utc):reward*=2
    c.execute('UPDATE users SET sd=sd+?,daily_claim=?,daily_streak=?,xp=xp+5,last_activity=? WHERE user_id=?',(reward,t,streak,now(),u['user_id'])); c.commit(); c.close()
    return web.json_response({'ok':True,'reward':reward,'streak':streak})

async def inventory(request):
    tg=await auth(request); c=db(); u=ensure_user(c,tg); rows=c.execute('SELECT i.id,i.name,i.code,i.rarity,i.sell_price,COUNT(v.id) count FROM inventory v JOIN items i ON i.id=v.item_id WHERE v.user_id=? GROUP BY i.id ORDER BY i.rarity,i.id',(u['user_id'],)).fetchall(); c.close(); return web.json_response({'ok':True,'items':[dict(r) for r in rows]})

async def sell(request):
    tg=await auth(request); body=await request.json(); iid=int(body.get('item_id',0)); mode=body.get('mode','one'); c=db(); u=ensure_user(c,tg); row=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone(); inv=c.execute('SELECT id FROM inventory WHERE user_id=? AND item_id=? LIMIT 100',(u['user_id'],iid)).fetchall()
    if not row or not inv:c.close(); return web.json_response({'ok':False,'error':'Предмет не найден'},status=404)
    ids=inv if mode!='all' else inv; count=len(ids) if mode=='all' else 1; ids=ids[:count]; q=','.join('?'*len(ids)); reward=int(row['sell_price']*count*(1-limit(c,'sell_commission')))
    c.execute(f'DELETE FROM inventory WHERE id IN ({q})',[x['id'] for x in ids]); c.execute('UPDATE users SET sd=sd+? WHERE user_id=?',(reward,u['user_id'])); c.commit(); c.close(); return web.json_response({'ok':True,'reward':reward})

async def promo(request):
    tg=await auth(request); body=await request.json(); code=str(body.get('code','')).strip().upper(); c=db(); u=ensure_user(c,tg); p=c.execute('SELECT * FROM promo_codes WHERE code=? AND enabled=1',(code,)).fetchone()
    if not p:c.close(); return web.json_response({'ok':False,'error':'Промокод не найден'},status=404)
    if p['max_uses']>0 and p['uses']>=p['max_uses']:c.close();return web.json_response({'ok':False,'error':'Лимит использований исчерпан'},status=400)
    if c.execute('SELECT 1 FROM promo_uses WHERE promo_id=? AND user_id=?',(p['id'],u['user_id'])).fetchone():c.close();return web.json_response({'ok':False,'error':'Ты уже использовал этот промокод'},status=400)
    c.execute('INSERT INTO promo_uses(promo_id,user_id,used_at) VALUES(?,?,?)',(p['id'],u['user_id'],now())); c.execute('UPDATE promo_codes SET uses=uses+1 WHERE id=?',(p['id'],)); c.execute('UPDATE users SET sd=sd+? WHERE user_id=?',(p['reward'],u['user_id'])); c.commit(); c.close(); return web.json_response({'ok':True,'reward':p['reward']})

async def rating(request):
    await auth(request); c=db(); rows=c.execute('SELECT user_id,username,first_name,sd,level,xp FROM users WHERE blocked=0 ORDER BY sd DESC LIMIT 100').fetchall(); c.close(); return web.json_response({'ok':True,'users':[dict(r) for r in rows]})

async def casino(request):
    tg=await auth(request); body=await request.json(); game=str(body.get('game','')); bet=int(body.get('bet',0)); choice=str(body.get('choice','')); c=db();u=ensure_user(c,tg)
    if bet<limit(c,'casino_min') or bet>limit(c,'casino_max') or bet>u['sd']:c.close();return web.json_response({'ok':False,'error':'Некорректная ставка'},status=400)
    c.execute('UPDATE users SET sd=sd-? WHERE user_id=?',(bet,u['user_id']))
    win=0; result=''
    if game=='slots':
        final=[random.choice(SLOT_SYMBOLS) for _ in range(3)]; mult=SLOT_PAYOUTS.get(tuple(final),0);win=min(bet*mult,limit(c,'casino_max_win'));result=' | '.join(final)
    elif game=='dice':
        a,b=random.randint(1,6),random.randint(1,6); total=a+b;result=f'{a}+{b}={total}';win=bet*(5 if choice=='eq' and total==7 else 2 if ((choice=='lt' and total<7) or (choice=='gt' and total>7)) else 0)
    elif game=='coin':
        result=random.choice(['o','r']);win=bet*2 if result==choice else 0
    elif game=='roulette':
        n=random.randint(0,36); result=str(n); color='green' if n==0 else 'red' if n in {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36} else 'black';win=bet*(14 if choice=='green' and color=='green' else 2 if choice==color else 0)
    elif game=='mines':
        mines=int(body.get('mines',3)); safe=random.random()>min(0.85,0.08+mines*0.025);result='safe' if safe else 'mine';win=bet*2 if safe else 0
    else:c.close();return web.json_response({'ok':False,'error':'Игра не найдена'},status=400)
    win=min(int(win),int(limit(c,'casino_max_win')))
    if win:c.execute('UPDATE users SET sd=sd+? WHERE user_id=?',(win,u['user_id']))
    c.execute('INSERT INTO casino_bets(user_id,game,bet,win,profit,created_at) VALUES(?,?,?,?,?,?)',(u['user_id'],game,bet,win,win-bet,now())); c.commit(); c.close(); return web.json_response({'ok':True,'result':result,'win':win,'profit':win-bet})

async def duel(request):
    tg=await auth(request); body=await request.json(); action=body.get('action'); c=db();u=ensure_user(c,tg)
    if action=='create':
        amount=int(body.get('amount',0));
        if amount<limit(c,'duel_min') or amount>u['sd']:c.close();return web.json_response({'ok':False,'error':'Некорректная ставка'},status=400)
        c.execute('UPDATE users SET sd=sd-? WHERE user_id=?',(amount,u['user_id'])); cur=c.execute('INSERT INTO duels(challenger_id,opponent_id,amount,status,created_at) VALUES(?,?,?,"open",?)',(u['user_id'],0,amount,now()));did=cur.lastrowid;c.commit();c.close();return web.json_response({'ok':True,'id':did})
    if action=='list':
        rows=c.execute('SELECT d.*,u.username FROM duels d LEFT JOIN users u ON u.user_id=d.challenger_id WHERE d.status="open" AND d.challenger_id!=? ORDER BY d.id DESC LIMIT 30',(u['user_id'],)).fetchall();c.close();return web.json_response({'ok':True,'duels':[dict(r) for r in rows]})
    if action=='accept':
        did=int(body.get('id'));row=c.execute('SELECT * FROM duels WHERE id=? AND status="open"',(did,)).fetchone()
        if not row or row['challenger_id']==u['user_id'] or u['sd']<row['amount']:c.close();return web.json_response({'ok':False,'error':'Дуэль недоступна'},status=400)
        c.execute('UPDATE users SET sd=sd-? WHERE user_id=?',(row['amount'],u['user_id']));winner=random.choice([row['challenger_id'],u['user_id']]);pot=row['amount']*2;prize=pot-int(pot*limit(c,'duel_commission'));c.execute('UPDATE users SET sd=sd+? WHERE user_id=?',(prize,winner));c.execute('UPDATE duels SET opponent_id=?,status="done",winner_id=?,finished_at=? WHERE id=?',(u['user_id'],winner,now(),did));c.commit();c.close();return web.json_response({'ok':True,'winner':winner,'prize':prize})
    c.close();return web.json_response({'ok':False,'error':'Unknown action'},status=400)


async def tasks_list(request):
    tg=await auth(request); c=db(); u=ensure_user(c,tg); d=today()
    rows=c.execute('SELECT t.id,t.code,t.name,t.description,t.goal,t.reward,COALESCE(ut.progress,0) progress,COALESCE(ut.done,0) done FROM tasks t LEFT JOIN user_tasks ut ON ut.task_id=t.id AND ut.user_id=? AND ut.date=? ORDER BY t.id',(u['user_id'],d)).fetchall()
    c.close()
    return web.json_response({'ok':True,'tasks':[{'id':r['id'],'code':r['code'],'title':r['name'],'name':r['name'],'description':r['description'],'goal':r['goal'],'reward':r['reward'],'progress':r['progress'],'completed':bool(r['done'])} for r in rows]})

async def task_claim(request):
    tg=await auth(request); body=await request.json(); raw=body.get('task_id',0)
    c=db(); u=ensure_user(c,tg); d=today()
    try: tid=int(raw)
    except (TypeError,ValueError): c.close(); return web.json_response({'ok':False,'error':'Некорректное задание'},status=400)
    task=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
    if not task: c.close(); return web.json_response({'ok':False,'error':'Задание не найдено'},status=404)
    row=c.execute('SELECT * FROM user_tasks WHERE user_id=? AND task_id=? AND date=?',(u['user_id'],tid,d)).fetchone()
    if row and row['done']: c.close(); return web.json_response({'ok':False,'error':'Задание уже получено сегодня'},status=400)
    # Only the daily login task can be claimed directly; other tasks need game progress.
    if task['code'] != 'daily':
        c.close(); return web.json_response({'ok':False,'error':'Выполни условие задания в игре, затем попробуй снова.'},status=400)
    c.execute('INSERT INTO user_tasks(user_id,task_id,date,progress,done) VALUES(?,?,?,?,1) ON CONFLICT(user_id,task_id,date) DO UPDATE SET progress=excluded.progress,done=1',(u['user_id'],tid,d,task['goal']))
    c.execute('UPDATE users SET sd=sd+?,xp=xp+5,last_activity=? WHERE user_id=?',(task['reward'],now(),u['user_id']))
    c.commit(); reward=task['reward']; c.close()
    return web.json_response({'ok':True,'reward':reward})

async def health(request): return web.json_response({'ok':True,'service':'COS-DROP WebApp'})

app=web.Application()
app.router.add_get('/',lambda r:web.FileResponse(WEB_DIR/'index.html'))
app.router.add_get('/api/health',health)
app.router.add_get('/api/me',me)
app.router.add_get('/api/dashboard',dashboard)
app.router.add_get('/api/cases',cases)
app.router.add_post('/api/cases/open',open_case)
app.router.add_post('/api/daily',daily)
app.router.add_get('/api/inventory',inventory)
app.router.add_post('/api/inventory/sell',sell)
app.router.add_post('/api/promo',promo)
app.router.add_get('/api/rating',rating)
app.router.add_get('/api/tasks',tasks_list)
app.router.add_post('/api/tasks/claim',task_claim)
app.router.add_post('/api/casino',casino)
app.router.add_post('/api/duel',duel)
for name in ['imagemain.png','casicw.png','caselol.png','profile.png','balance.png','collect.png','rait.png','promocodes.png','duel.png']:
    app.router.add_get('/assets/'+name,lambda r,n=name:web.FileResponse(WEB_DIR/n) if (WEB_DIR/n).exists() else web.Response(status=404))

async def start_web_server():
    runner=web.AppRunner(app); await runner.setup(); port=int(os.getenv('PORT','8080')); site=web.TCPSite(runner,'0.0.0.0',port); await site.start(); print(f'COS-DROP WebApp started on :{port}')
    try:
        import asyncio; await asyncio.Event().wait()
    finally: await runner.cleanup()
