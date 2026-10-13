
import os
import json
import hmac
import hashlib
import sqlite3
import random
import secrets
import asyncio
import logging

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web


# ==================== CONFIG ====================

logging.basicConfig(level=logging.INFO)

BASE = Path(__file__).resolve().parent

DB_FILE = os.getenv(
    "DB_FILE",
    "/data/cosdrop.sqlite3"
    if os.path.isdir("/data")
    else str(BASE / "cosdrop.sqlite3"),
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEB_DIR = BASE

logging.info("COS-DROP WebApp module: %s", __file__)
logging.info("COS-DROP WebApp directory: %s", WEB_DIR)
logging.info("COS-DROP database path: %s", DB_FILE)


CASES = [
    ("start", "🎒 Старт", "Стартовый", 0),
    ("basic", "📦 Basic", "Обычный", 100),
    ("school", "🏫 School", "Школьная", 150),
    ("meme", "😂 Meme", "Мемы", 200),
    ("rare", "💎 Rare", "Редкие", 300),
    ("epic", "🟣 Epic", "Эпик", 500),
    ("night", "🌙 Night", "Ночь", 700),
    ("cos", "👑 COS", "Главный", 1000),
]

RARITY = {
    "common": "🟢 Common",
    "rare": "🔵 Rare",
    "epic": "🟣 Epic",
    "legendary": "🟡 Legendary",
    "mythic": "🔴 Mythic",
}

SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣", "⭐"]

SLOT_PAYOUTS = {
    ("🍒", "🍒", "🍒"): 3,
    ("🍋", "🍋", "🍋"): 4,
    ("🔔", "🔔", "🔔"): 6,
    ("💎", "💎", "💎"): 12,
    ("7️⃣", "7️⃣", "7️⃣"): 25,
    ("⭐", "⭐", "⭐"): 50,
}

LIMITS = {
    "starter_sd": 100,
    "daily_base": 50,
    "daily_streak_7": 300,
    "daily_streak_30": 2000,
    "case_cooldown": 3,
    "sell_commission": 0.10,
    "upgrade_chance": 0.60,
    "casino_min": 10,
    "casino_max": 10000,
    "casino_max_win": 50000,
    "casino_loss_limit": 5000,
    "duel_min": 100,
    "duel_commission": 0.05,
    "ref_invite": 500,
    "ref_donate": 2000,
}


# ==================== DATABASE ====================

def db():
    connection = sqlite3.connect(DB_FILE, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    return connection


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).date().isoformat()


def limit(connection, key):
    default = LIMITS.get(key, 0)

    row = connection.execute(
        "SELECT value FROM settings WHERE key=?",
        (f"lim_{key}",),
    ).fetchone()

    if not row:
        return default

    try:
        if isinstance(default, float):
            return float(row["value"])
        return int(row["value"])
    except (TypeError, ValueError):
        return default


# ==================== TELEGRAM AUTH ====================

def validate_init_data(init_data):
    if not init_data or not BOT_TOKEN:
        return None

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))

        received_hash = pairs.pop("hash", None)

        if not received_hash:
            return None

        check_string = "\n".join(
            f"{key}={pairs[key]}"
            for key in sorted(pairs)
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        expected_hash = hmac.new(
            secret_key,
            check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, received_hash):
            return None

        user = json.loads(pairs.get("user", "{}"))

        if not user.get("id"):
            return None

        auth_date = int(pairs.get("auth_date", "0"))
        current_time = int(datetime.now(timezone.utc).timestamp())

        if abs(current_time - auth_date) > 86400:
            return None

        return user

    except (ValueError, TypeError, json.JSONDecodeError):
        logging.warning("Telegram init data validation failed")
        return None
    except Exception:
        logging.exception("Unexpected Telegram authorization error")
        return None


async def auth(request):
    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        "",
    )

    user = validate_init_data(init_data)

    if not user:
        raise web.HTTPUnauthorized(
            text=json.dumps({
                "ok": False,
                "error": "Telegram Web App authorization required",
            }),
            content_type="application/json",
        )

    return user


# ==================== USERS ====================

def ensure_user(connection, telegram_user):
    user_id = int(telegram_user["id"])

    row = connection.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,),
    ).fetchone()

    if row:
        connection.execute(
            """
            UPDATE users
            SET username=?, first_name=?, last_activity=?
            WHERE user_id=?
            """,
            (
                telegram_user.get("username"),
                telegram_user.get("first_name", ""),
                now(),
                user_id,
            ),
        )
        connection.commit()

        return connection.execute(
            "SELECT * FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()

    connection.execute(
        """
        INSERT INTO users
        (user_id, username, first_name, sd, xp, level,
         blocked, created_at, last_activity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            telegram_user.get("username"),
            telegram_user.get("first_name", ""),
            limit(connection, "starter_sd"),
            0,
            1,
            0,
            now(),
            now(),
        ),
    )

    connection.commit()

    return connection.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,),
    ).fetchone()


def public_user(connection, user):
    user_id = user["user_id"]

    inventory_count = connection.execute(
        "SELECT COUNT(*) AS n FROM inventory WHERE user_id=?",
        (user_id,),
    ).fetchone()["n"]

    opens_count = connection.execute(
        "SELECT COUNT(*) AS n FROM case_opens WHERE user_id=?",
        (user_id,),
    ).fetchone()["n"]

    achievements_count = connection.execute(
        """
        SELECT COUNT(*) AS n
        FROM user_achievements
        WHERE user_id=?
        """,
        (user_id,),
    ).fetchone()["n"]

    referrals_count = connection.execute(
        "SELECT COUNT(*) AS n FROM users WHERE referrer_id=?",
        (user_id,),
    ).fetchone()["n"]

    premium = False

    if user["sub_until"]:
        try:
            expires = datetime.fromisoformat(user["sub_until"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            premium = expires > datetime.now(timezone.utc)
        except (ValueError, TypeError):
            premium = False

    return {
        "id": user_id,
        "username": user["username"],
        "first_name": user["first_name"],
        "sd": user["sd"],
        "xp": user["xp"],
        "level": user["level"],
        "inventory": inventory_count,
        "opens": opens_count,
        "achievements": achievements_count,
        "referrals": referrals_count,
        "premium": premium,
    }


# ==================== WEB APP ROUTES ====================

async def index(request):
    index_path = WEB_DIR / "index.html"

    logging.info("WEB DEBUG | request path=%s", request.path)
    logging.info("WEB DEBUG | module=%s", __file__)
    logging.info("WEB DEBUG | index path=%s", index_path)
    logging.info("WEB DEBUG | index exists=%s", index_path.is_file())

    if not index_path.is_file():
        message = (
            "COS-DROP WebApp: index.html not found.\n"
            f"Expected file: {index_path}\n"
            f"Module: {__file__}\n"
            f"Directory: {WEB_DIR}\n"
        )

        logging.error(message)

        return web.Response(
            text=message,
            status=500,
            content_type="text/plain",
        )

    return web.FileResponse(index_path)


async def health(request):
    return web.json_response({
        "ok": True,
        "service": "COS-DROP WebApp",
        "index_exists": (WEB_DIR / "index.html").is_file(),
    })


async def me(request):
    telegram_user = await auth(request)
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        data = public_user(connection, user)

        return web.json_response({
            "ok": True,
            "user": data,
        })
    finally:
        connection.close()


async def dashboard(request):
    telegram_user = await auth(request)
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        cases_data = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, code, name, description, price, enabled
                FROM cases
                WHERE enabled=1
                ORDER BY id
                """
            ).fetchall()
        ]

        items_data = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, code, name, rarity, sell_price, enabled
                FROM items
                WHERE enabled=1
                ORDER BY id
                """
            ).fetchall()
        ]

        inventory_data = [
            dict(row)
            for row in connection.execute(
                """
                SELECT i.id, i.code, i.name, i.rarity,
                       i.sell_price, COUNT(*) AS count
                FROM inventory v
                JOIN items i ON i.id=v.item_id
                WHERE v.user_id=?
                GROUP BY i.id
                ORDER BY i.id
                """,
                (user["user_id"],),
            ).fetchall()
        ]

        rating_data = [
            dict(row)
            for row in connection.execute(
                """
                SELECT user_id, username, sd, level, xp
                FROM users
                WHERE blocked=0
                ORDER BY sd DESC
                LIMIT 50
                """
            ).fetchall()
        ]

        achievements_data = [
            dict(row)
            for row in connection.execute(
                """
                SELECT a.id, a.code, a.name, a.description,
                       a.reward, ua.obtained_at
                FROM achievements a
                LEFT JOIN user_achievements ua
                  ON ua.achievement_id=a.id
                 AND ua.user_id=?
                ORDER BY a.id
                """,
                (user["user_id"],),
            ).fetchall()
        ]

        tasks_data = [
            dict(row)
            for row in connection.execute(
                """
                SELECT t.*, ut.progress, ut.done
                FROM tasks t
                LEFT JOIN user_tasks ut
                  ON ut.task_id=t.id
                 AND ut.user_id=?
                 AND ut.date=?
                ORDER BY t.id
                """,
                (user["user_id"], today()),
            ).fetchall()
        ]

        user_data = public_user(connection, user)

        return web.json_response({
            "ok": True,
            "user": user_data,
            "cases": cases_data,
            "items": items_data,
            "inventory": inventory_data,
            "rating": rating_data,
            "achievements": achievements_data,
            "tasks": tasks_data,
        })

    finally:
        connection.close()


async def cases(request):
    telegram_user = await auth(request)
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        rows = connection.execute(
            """
            SELECT id, code, name, description, price, enabled
            FROM cases
            WHERE enabled=1
            ORDER BY id
            """
        ).fetchall()

        return web.json_response({
            "ok": True,
            "cases": [dict(row) for row in rows],
        })

    finally:
        connection.close()


# ==================== CASE OPENING ====================

async def open_case(request):
    telegram_user = await auth(request)
    body = await request.json()

    code = str(body.get("code", ""))
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        case = connection.execute(
            "SELECT * FROM cases WHERE code=? AND enabled=1",
            (code,),
        ).fetchone()

        if not case:
            return web.json_response(
                {"ok": False, "error": "Кейс не найден"},
                status=404,
            )

        if case["price"] > user["sd"]:
            return web.json_response(
                {"ok": False, "error": "Недостаточно SD"},
                status=400,
            )

        if user["last_case_at"]:
            try:
                last_open = datetime.fromisoformat(
                    user["last_case_at"]
                )

                if last_open.tzinfo is None:
                    last_open = last_open.replace(
                        tzinfo=timezone.utc
                    )

                elapsed = (
                    datetime.now(timezone.utc) - last_open
                ).total_seconds()

                if elapsed < limit(connection, "case_cooldown"):
                    return web.json_response(
                        {
                            "ok": False,
                            "error": "Подожди перед следующим открытием",
                        },
                        status=429,
                    )
            except (ValueError, TypeError):
                pass

        drops = connection.execute(
            """
            SELECT ci.chance, i.*
            FROM case_items ci
            JOIN items i ON i.id=ci.item_id
            WHERE ci.case_id=? AND i.enabled=1
            """,
            (case["id"],),
        ).fetchall()

        if not drops:
            return web.json_response(
                {"ok": False, "error": "В кейсе нет предметов"},
                status=400,
            )

        total_chance = sum(float(item["chance"]) for item in drops)

        if total_chance <= 0:
            return web.json_response(
                {"ok": False, "error": "Некорректные шансы предметов"},
                status=400,
            )

        pick = random.uniform(0, total_chance)
        accumulated = 0
        selected = drops[-1]

        for item in drops:
            accumulated += float(item["chance"])

            if pick <= accumulated:
                selected = item
                break

        timestamp = now()
        new_xp = user["xp"] + 5
        new_level = max(1, new_xp // 100 + 1)

        connection.execute(
            """
            UPDATE users
            SET sd=sd-?, xp=?, level=?, last_case_at=?, last_activity=?
            WHERE user_id=?
            """,
            (
                case["price"],
                new_xp,
                new_level,
                timestamp,
                timestamp,
                user["user_id"],
            ),
        )

        connection.execute(
            """
            INSERT INTO inventory(user_id, item_id, obtained_at)
            VALUES (?, ?, ?)
            """,
            (user["user_id"], selected["id"], timestamp),
        )

        connection.execute(
            """
            INSERT INTO case_opens(user_id, case_id, item_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                user["user_id"],
                case["id"],
                selected["id"],
                timestamp,
            ),
        )

        connection.commit()

        return web.json_response({
            "ok": True,
            "item": {
                "id": selected["id"],
                "name": selected["name"],
                "rarity": selected["rarity"],
                "sell_price": selected["sell_price"],
            },
            "sd": user["sd"] - case["price"],
        })

    finally:
        connection.close()


# ==================== DAILY REWARD ====================

async def daily(request):
    telegram_user = await auth(request)
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        current_day = today()

        if user["daily_claim"] == current_day:
            return web.json_response(
                {"ok": False, "error": "Бонус уже получен"},
                status=400,
            )

        streak = user["daily_streak"] or 0

        if user["daily_claim"]:
            try:
                previous_day = datetime.fromisoformat(
                    user["daily_claim"]
                ).date()

                current_date = datetime.now(timezone.utc).date()

                if (current_date - previous_day).days != 1:
                    streak = 0

            except (ValueError, TypeError):
                streak = 0

        streak += 1
        reward = limit(connection, "daily_base")

        if streak >= 30:
            reward += limit(connection, "daily_streak_30")
        elif streak >= 7:
            reward += limit(connection, "daily_streak_7")

        if user["sub_until"]:
            try:
                expires = datetime.fromisoformat(user["sub_until"])

                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)

                if expires > datetime.now(timezone.utc):
                    reward *= 2
            except (ValueError, TypeError):
                pass

        connection.execute(
            """
            UPDATE users
            SET sd=sd+?, daily_claim=?, daily_streak=?,
                xp=xp+5, last_activity=?
            WHERE user_id=?
            """,
            (
                reward,
                current_day,
                streak,
                now(),
                user["user_id"],
            ),
        )

        connection.commit()

        return web.json_response({
            "ok": True,
            "reward": reward,
            "streak": streak,
        })

    finally:
        connection.close()


# ==================== INVENTORY ====================

async def inventory(request):
    telegram_user = await auth(request)
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        rows = connection.execute(
            """
            SELECT i.id, i.name, i.code, i.rarity,
                   i.sell_price, COUNT(v.id) AS count
            FROM inventory v
            JOIN items i ON i.id=v.item_id
            WHERE v.user_id=?
            GROUP BY i.id
            ORDER BY i.rarity, i.id
            """,
            (user["user_id"],),
        ).fetchall()

        return web.json_response({
            "ok": True,
            "items": [dict(row) for row in rows],
        })

    finally:
        connection.close()


async def sell(request):
    telegram_user = await auth(request)
    body = await request.json()

    try:
        item_id = int(body.get("item_id", 0))
    except (ValueError, TypeError):
        return web.json_response(
            {"ok": False, "error": "Некорректный предмет"},
            status=400,
        )

    mode = body.get("mode", "one")
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        item = connection.execute(
            "SELECT * FROM items WHERE id=?",
            (item_id,),
        ).fetchone()

        if not item:
            return web.json_response(
                {"ok": False, "error": "Предмет не найден"},
                status=404,
            )

        if mode == "all":
            owned = connection.execute(
                """
                SELECT id FROM inventory
                WHERE user_id=? AND item_id=?
                """,
                (user["user_id"], item_id),
            ).fetchall()
        else:
            owned = connection.execute(
                """
                SELECT id FROM inventory
                WHERE user_id=? AND item_id=?
                LIMIT 1
                """,
                (user["user_id"], item_id),
            ).fetchall()

        if not owned:
            return web.json_response(
                {"ok": False, "error": "Предмет не найден в инвентаре"},
                status=404,
            )

        inventory_ids = [row["id"] for row in owned]
        count = len(inventory_ids)

        reward = int(
            item["sell_price"]
            * count
            * (1 - limit(connection, "sell_commission"))
        )

        placeholders = ",".join("?" for _ in inventory_ids)

        connection.execute(
            f"DELETE FROM inventory WHERE id IN ({placeholders})",
            inventory_ids,
        )

        connection.execute(
            "UPDATE users SET sd=sd+? WHERE user_id=?",
            (reward, user["user_id"]),
        )

        connection.commit()

        return web.json_response({
            "ok": True,
            "reward": reward,
        })

    finally:
        connection.close()


# ==================== PROMO CODES ====================

async def promo(request):
    telegram_user = await auth(request)
    body = await request.json()

    code = str(body.get("code", "")).strip().upper()

    if not code:
        return web.json_response(
            {"ok": False, "error": "Введи промокод"},
            status=400,
        )

    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        promo_code = connection.execute(
            """
            SELECT * FROM promo_codes
            WHERE code=? AND enabled=1
            """,
            (code,),
        ).fetchone()

        if not promo_code:
            return web.json_response(
                {"ok": False, "error": "Промокод не найден"},
                status=404,
            )

        if (
            promo_code["max_uses"] > 0
            and promo_code["uses"] >= promo_code["max_uses"]
        ):
            return web.json_response(
                {"ok": False, "error": "Лимит использований исчерпан"},
                status=400,
            )

        already_used = connection.execute(
            """
            SELECT 1 FROM promo_uses
            WHERE promo_id=? AND user_id=?
            """,
            (promo_code["id"], user["user_id"]),
        ).fetchone()

        if already_used:
            return web.json_response(
                {
                    "ok": False,
                    "error": "Ты уже использовал этот промокод",
                },
                status=400,
            )

        connection.execute(
            """
            INSERT INTO promo_uses(promo_id, user_id, used_at)
            VALUES (?, ?, ?)
            """,
            (promo_code["id"], user["user_id"], now()),
        )

        connection.execute(
            "UPDATE promo_codes SET uses=uses+1 WHERE id=?",
            (promo_code["id"],),
        )

        connection.execute(
            "UPDATE users SET sd=sd+? WHERE user_id=?",
            (promo_code["reward"], user["user_id"]),
        )

        connection.commit()

        return web.json_response({
            "ok": True,
            "reward": promo_code["reward"],
        })

    finally:
        connection.close()


# ==================== RATING ====================

async def rating(request):
    await auth(request)
    connection = db()

    try:
        rows = connection.execute(
            """
            SELECT user_id, username, first_name, sd, level, xp
            FROM users
            WHERE blocked=0
            ORDER BY sd DESC
            LIMIT 100
            """
        ).fetchall()

        return web.json_response({
            "ok": True,
            "users": [dict(row) for row in rows],
        })

    finally:
        connection.close()


# ==================== CASINO API ====================

async def casino(request):
    telegram_user = await auth(request)
    body = await request.json()

    try:
        game = str(body.get("game", ""))
        bet = int(body.get("bet", 0))
        choice = str(body.get("choice", ""))
    except (ValueError, TypeError):
        return web.json_response(
            {"ok": False, "error": "Некорректные параметры"},
            status=400,
        )

    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        if (
            bet < limit(connection, "casino_min")
            or bet > limit(connection, "casino_max")
            or bet > user["sd"]
        ):
            return web.json_response(
                {"ok": False, "error": "Некорректная ставка"},
                status=400,
            )

        win = 0
        result = ""

        if game == "slots":
            final = [
                random.choice(SLOT_SYMBOLS)
                for _ in range(3)
            ]

            multiplier = SLOT_PAYOUTS.get(tuple(final), 0)
            win = min(
                bet * multiplier,
                limit(connection, "casino_max_win"),
            )
            result = " | ".join(final)

        elif game == "dice":
            first = random.randint(1, 6)
            second = random.randint(1, 6)
            total = first + second

            result = f"{first}+{second}={total}"

            if choice == "eq" and total == 7:
                win = bet * 5
            elif (
                (choice == "lt" and total < 7)
                or (choice == "gt" and total > 7)
            ):
                win = bet * 2

        elif game == "coin":
            result = random.choice(["o", "r"])
            win = bet * 2 if result == choice else 0

        elif game == "roulette":
            number = random.randint(0, 36)
            result = str(number)

            red_numbers = {
                1, 3, 5, 7, 9, 12, 14, 16, 18,
                19, 21, 23, 25, 27, 30, 32, 34, 36,
            }

            color = (
                "green" if number == 0
                else "red" if number in red_numbers
                else "black"
            )

            if choice == "green" and color == "green":
                win = bet * 14
            elif choice == color:
                win = bet * 2

        elif game == "mines":
            try:
                mines_count = int(body.get("mines", 3))
            except (ValueError, TypeError):
                mines_count = 3

            mines_count = max(1, min(24, mines_count))
            safe = random.random() > min(
                0.85,
                0.08 + mines_count * 0.025,
            )

            result = "safe" if safe else "mine"
            win = bet * 2 if safe else 0

        else:
            return web.json_response(
                {"ok": False, "error": "Игра не найдена"},
                status=400,
            )

        win = min(
            int(win),
            int(limit(connection, "casino_max_win")),
        )

        connection.execute(
            "UPDATE users SET sd=sd-? WHERE user_id=?",
            (bet, user["user_id"]),
        )

        if win:
            connection.execute(
                "UPDATE users SET sd=sd+? WHERE user_id=?",
                (win, user["user_id"]),
            )

        connection.execute(
            """
            INSERT INTO casino_bets
            (user_id, game, bet, win, profit, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user["user_id"],
                game,
                bet,
                win,
                win - bet,
                now(),
            ),
        )

        connection.commit()

        return web.json_response({
            "ok": True,
            "result": result,
            "win": win,
            "profit": win - bet,
        })

    finally:
        connection.close()


# ==================== DUELS ====================

async def duel(request):
    telegram_user = await auth(request)
    body = await request.json()

    action = body.get("action")
    connection = db()

    try:
        user = ensure_user(connection, telegram_user)

        if user["blocked"]:
            return web.json_response(
                {"ok": False, "error": "Аккаунт заблокирован"},
                status=403,
            )

        if action == "create":
            try:
                amount = int(body.get("amount", 0))
            except (ValueError, TypeError):
                amount = 0

            if (
                amount < limit(connection, "duel_min")
                or amount > user["sd"]
            ):
                return web.json_response(
                    {"ok": False, "error": "Некорректная ставка"},
                    status=400,
                )

            connection.execute(
                "UPDATE users SET sd=sd-? WHERE user_id=?",
                (amount, user["user_id"]),
            )

            cursor = connection.execute(
                """
                INSERT INTO duels
                (challenger_id, opponent_id, amount, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
                """,
                (user["user_id"], 0, amount, now()),
            )

            duel_id = cursor.lastrowid
            connection.commit()

            return web.json_response({
                "ok": True,
                "id": duel_id,
            })

        if action == "list":
            rows = connection.execute(
                """
                SELECT d.*, u.username
                FROM duels d
                LEFT JOIN users u ON u.user_id=d.challenger_id
                WHERE d.status='open'
                  AND d.challenger_id!=?
                ORDER BY d.id DESC
                LIMIT 30
                """,
                (user["user_id"],),
            ).fetchall()

            return web.json_response({
                "ok": True,
                "duels": [dict(row) for row in rows],
            })

        if action == "accept":
            try:
                duel_id = int(body.get("id", 0))
            except (ValueError, TypeError):
                duel_id = 0

            row = connection.execute(
                """
                SELECT * FROM duels
                WHERE id=? AND status='open'
                """,
                (duel_id,),
            ).fetchone()

            if (
                not row
                or row["challenger_id"] == user["user_id"]
                or user["sd"] < row["amount"]
            ):
                return web.json_response(
                    {"ok": False, "error": "Дуэль недоступна"},
                    status=400,
                )

            connection.execute(
                "UPDATE users SET sd=sd-? WHERE user_id=?",
                (row["amount"], user["user_id"]),
            )

            winner = random.choice([
                row["challenger_id"],
                user["user_id"],
            ])

            pot = row["amount"] * 2

            prize = pot - int(
                pot * limit(connection, "duel_commission")
            )

            connection.execute(
                "UPDATE users SET sd=sd+? WHERE user_id=?",
                (prize, winner),
            )

            connection.execute(
                """
                UPDATE duels
                SET opponent_id=?, status='done',
                    winner_id=?, finished_at=?
                WHERE id=? AND status='open'
                """,
                (
                    user["user_id"],
                    winner,
                    now(),
                    duel_id,
                ),
            )

            connection.commit()

            return web.json_response({
                "ok": True,
                "winner": winner,
                "prize": prize,
            })

        return web.json_response(
            {"ok": False, "error": "Неизвестное действие"},
            status=400,
        )

    finally:
        connection.close()


# ==================== APP SETUP ====================

@web.middleware
async def error_middleware(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        logging.exception(
            "WEB ERROR | %s %s",
            request.method,
            request.path,
        )

        return web.json_response(
            {
                "ok": False,
                "error": "Внутренняя ошибка сервера",
            },
            status=500,
        )


app = web.Application(
    middlewares=[error_middleware],
)

# Main page: index.html in the same folder as this file.
app.router.add_get("/", index)

# Health check.
app.router.add_get("/api/health", health)

# User and game APIs.
app.router.add_get("/api/me", me)
app.router.add_get("/api/dashboard", dashboard)
app.router.add_get("/api/cases", cases)
app.router.add_post("/api/cases/open", open_case)
app.router.add_post("/api/daily", daily)
app.router.add_get("/api/inventory", inventory)
app.router.add_post("/api/inventory/sell", sell)
app.router.add_post("/api/promo", promo)
app.router.add_get("/api/rating", rating)
app.router.add_post("/api/casino", casino)
app.router.add_post("/api/duel", duel)


# Static image assets.
def make_asset_handler(filename):
    async def asset_handler(request):
        path = WEB_DIR / filename

        if not path.is_file():
            return web.Response(
                text=f"Asset not found: {filename}",
                status=404,
                content_type="text/plain",
            )

        return web.FileResponse(path)

    return asset_handler


for asset_name in [
    "imagemain.png",
    "casicw.png",
    "caselol.png",
    "profile.png",
    "balance.png",
    "collect.png",
    "rait.png",
    "promocodes.png",
    "duel.png",
]:
    app.router.add_get(
        f"/assets/{asset_name}",
        make_asset_handler(asset_name),
    )


# ==================== START WEB SERVER ====================

async def start_web_server():
    runner = web.AppRunner(app)
    await runner.setup()

    index_path = WEB_DIR / "index.html"

    logging.info("WEB DEBUG | module=%s", __file__)
    logging.info("WEB DEBUG | base=%s", BASE)
    logging.info(
        "WEB DEBUG | index=%s exists=%s",
        index_path,
        index_path.is_file(),
    )
    logging.info("WEB DEBUG | database=%s", DB_FILE)
    logging.info(
        "WEB DEBUG | routes=%s",
        [
            f"{route.method} {route.resource.canonical}"
            for route in app.router.routes()
        ],
    )

    port = int(os.getenv("PORT", "8080"))

    try:
        site = web.TCPSite(
            runner,
            "0.0.0.0",
            port,
        )

        await site.start()

        logging.info(
            "COS-DROP WebApp started on 0.0.0.0:%s",
            port,
        )

        await asyncio.Event().wait()

    finally:
        await runner.cleanup()
