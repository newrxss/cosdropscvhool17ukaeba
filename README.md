# Cos-drop

Готовый Telegram-бот на Python + aiogram 3 + SQLite.

## Структура
- `bot.py` — основной код
- `requirements.txt` — зависимости
- `Procfile` — запуск Railway
- `imagemain.png` — картинка стартового экрана (замени своей)
- `.env.example` — переменные окружения
- `.gitignore` — исключение секретов и локальной БД

## Настройка

Открой `bot.py` и в самом верху вставь токен бота в `BOT_TOKEN`. ID администратора уже прописан в `ADMIN_ID`.

## Railway
1. Подключи GitHub-репозиторий.
2. Создай Volume и смонтируй его в `/data`.
3. Variables:
   - `BOT_TOKEN` = токен бота
   - `ADMIN_ID` = `8146320391`
   - `DB_FILE` = `/data/cosdrop.sqlite3`
   - `IMAGE_FILE` = `imagemain.png`
4. Команда из Procfile: `worker: python bot.py`.

Не загружай BOT_TOKEN в GitHub. SQLite хранится на Railway Volume.

SD и предметы в этой версии виртуальные и не имеют денежной стоимости.
