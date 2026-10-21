# COS-DROP Halloween Tapper

- Halloween tapper added to the Web App. Each accepted tap awards `0.4 SD` to the same `users.sd` field used by the Telegram bot.
- Rewards are credited server-side only after validating Telegram Web App `initData`. Client cannot choose a Telegram ID or reward amount.
- Duplicate batch IDs are not credited twice. Batches contain at most 20 taps.

## Railway deployment
1. Back up repository and database. Do not delete the existing Railway Volume.
2. Replace `index.html` and `webapp_api.py` with these files; leave the current `bot.py` unchanged.
3. Ensure API service has the correct `BOT_TOKEN` and `DB_FILE=/data/cosdrop.sqlite3`.
4. Keep the existing Volume mounted at `/data`; do not create a new database.
5. Check `/api/health`, open the Web App from Telegram, tap the pumpkin, then compare website and bot balances.

SQLite accepts fractional values even when a column was declared INTEGER, but the bot must not cast `sd` to `int` or round it for display. Balance is stored to tenths.
