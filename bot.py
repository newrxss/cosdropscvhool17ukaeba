
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

@dp.callback_query(F.data == "a2_maintenance")
async def a2_maintenance(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.clear()
    if maintenance_active():
        enabled = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Включить бота", callback_data="a2_maintenance_off")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="a2_root")],
        ])
        await callback.message.edit_text(
            "🔴 <b>ТЕХРАБОТЫ УЖЕ ВКЛЮЧЕНЫ</b>\n\n" + maintenance_text(),
            reply_markup=enabled,
        )
    else:
        await state.set_state(A2Maintenance.reason)
        await callback.message.edit_text(
            "🔴 <b>ВЫКЛЮЧЕНИЕ БОТА ДЛЯ ИГРОКОВ</b>\n\n"
            "Напиши причину техработ.\n\n"
            "Например: <i>Обновление COS-DROP</i>",
            reply_markup=a2_cancel(),
        )
    await callback.answer()

@dp.message(StateFilter(A2Maintenance.reason))
async def a2_maintenance_reason(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    reason = (message.text or "").strip()
    if not reason:
        return await message.answer("❌ Причина не может быть пустой.")
    await state.update_data(reason=reason)
    await state.set_state(A2Maintenance.duration)
    await message.answer(
        "⏱ <b>Теперь укажи время.</b>\n\n"
        "Например: <code>2 часа</code>, <code>30 минут</code>, <code>1 день</code>."
    )

@dp.message(StateFilter(A2Maintenance.duration))
async def a2_maintenance_duration(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    duration = (message.text or "").strip()
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(минут(?:а|ы)?|мин|час(?:а|ов)?|ч|день|дн(?:я|ей)?)\s*", duration, re.I)
    if not m:
        return await message.answer("❌ Не понял время. Пример: <code>2 часа</code> или <code>30 минут</code>.")
    value = float(m.group(1).replace(',', '.'))
    unit = m.group(2).lower()
    if value <= 0:
        return await message.answer("❌ Время должно быть больше нуля.")
    if unit.startswith("мин"):
        seconds = value * 60
    elif unit.startswith("час") or unit == "ч":
        seconds = value * 3600
    else:
        seconds = value * 86400
    data = await state.get_data()
    until = datetime.now(timezone.utc).timestamp() + seconds
    setting_set("maintenance_enabled", "1")
    setting_set("maintenance_reason", data.get("reason", "Технические работы"))
    setting_set("maintenance_duration", duration)
    setting_set("maintenance_until", str(until))
    await state.clear()
    log_admin("maintenance_on", details=f"reason={data.get('reason','')}; duration={duration}")
    await message.answer(
        "🔴 <b>БОТ ВЫКЛЮЧЕН ДЛЯ ИГРОКОВ</b>\n\n"
        f"📌 Причина: <b>{escape(data.get('reason',''))}</b>\n"
        f"⏱ Время: <b>{escape(duration)}</b>\n\n"
        "👑 Для администратора бот продолжает работать.",
        reply_markup=a2_root_kb(),
    )

@dp.callback_query(F.data == "a2_maintenance_off")
async def a2_maintenance_off(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.clear()
    setting_set("maintenance_enabled", "0")
    setting_set("maintenance_until", "")
    log_admin("maintenance_off")
    await callback.message.edit_text("🟢 <b>БОТ СНОВА ДОСТУПЕН ИГРОКАМ</b>", reply_markup=a2_root_kb())
    await callback.answer("✅ Бот включён")

@dp.callback_query(F.data == "a2_wipe")
async def a2_wipe(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☢️ ДА, СБРОСИТЬ ВСЁ", callback_data="a2_wipe_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="a2_root")],
    ])
    await callback.message.edit_text(
        "☢️ <b>ПОЛНЫЙ WIPE ИГРОКОВ</b>\n\n"
        "Будут удалены/сброшены данные ВСЕХ игроков:\n"
        "💰 SD\n🎒 коллекции\n⭐ XP и уровни\n"
        "🎁 открытия кейсов\n🎰 ставки и статистика\n"
        "⚔️ дуэли\n🏅 достижения\n📋 задания\n"
        "🎟 использованные промокоды\n💸 выводы\n\n"
        "⚠️ Кейсы, предметы и настройки бота сохранятся.\n"
        "⚠️ Администратор сохраняется, чтобы панель не потерялась.\n\n"
        "Это действие необратимо.",
        reply_markup=kb,
    )
    await callback.answer()

@dp.callback_query(F.data == "a2_wipe_confirm")
async def a2_wipe_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return

    # ВАЖНО: пользователей НЕ удаляем. Их Telegram ID/аккаунты остаются в users,
    # поэтому список пользователей, поиск и рассылка продолжают работать.
    # Сбрасываем только игровой прогресс. Кейсы, предметы, их настройки и
    # настройки экономики/казино не трогаем. Администратор тоже сохраняется.
    con = db()
    starter_sd = int(get_limit("starter_sd"))
    try:
        counts = {}
        for table in (
            "inventory", "case_opens", "applications", "promo_uses", "withdraws",
            "casino_bets", "casino_stats", "duels", "user_achievements", "user_tasks"
        ):
            counts[table] = con.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]
            con.execute(f"DELETE FROM {table}")

        # Сохраняем сами аккаунты, username/имя, дату регистрации и блокировки.
        # Админские права не хранятся в users, а отдельная таблица admins не трогается.
        player_count = con.execute(
            "SELECT COUNT(*) n FROM users WHERE user_id != ?", (ADMIN_ID,)
        ).fetchone()["n"]

        con.execute("""
            UPDATE users SET
                sd=?,
                xp=0,
                level=1,
                last_activity=NULL,
                daily_claim=NULL,
                daily_streak=0,
                last_case_at=NULL,
                referrer_id=NULL,
                donated=0,
                sub_until=NULL,
                daily_loss=0,
                daily_loss_date=NULL,
                tag=NULL
            WHERE user_id != ?
        """, (starter_sd, ADMIN_ID))
        con.commit()
    except Exception:
        con.rollback()
        con.close()
        raise
    con.close()

    log_admin("FULL_WIPE_PROGRESS", details=f"players_reset={player_count};starter_sd={starter_sd}")
    await callback.message.edit_text(
        "☢️ <b>СБРОС ИГРОКОВ ЗАВЕРШЁН</b>\n\n"
        f"👥 Сброшено игроков: <b>{player_count}</b>\n"
        f"💰 Баланс → <b>{starter_sd} SD</b>\n"
        "🎒 Коллекции очищены\n"
        "⭐ XP и уровень → 0 / 1\n"
        "🎁 История открытий кейсов очищена\n"
        "🎰 Ставки и статистика казино очищены\n"
        "⚔️ Дуэли очищены\n"
        "🏅 Достижения очищены\n"
        "📋 Задания очищены\n"
        "🎟 Использованные промокоды очищены\n"
        "💸 Выводы очищены\n\n"
        "✅ <b>Аккаунты игроков НЕ удалены.</b>\n"
        "✅ Пользователи остались в списке и снова получают рассылки.\n"
        "✅ Кейсы, предметы, цены и настройки казино сохранены.\n"
        "👑 Администратор сохранён.",
        reply_markup=a2_root_kb(),
    )
    await callback.answer("☢️ Прогресс игроков сброшен")

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
