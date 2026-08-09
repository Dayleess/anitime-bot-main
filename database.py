import sqlite3
import os
import time

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSCOPG2_AVAILABLE = True
except ImportError:
    PSCOPG2_AVAILABLE = False

from config import DATABASE_URL

DB_PATH = os.path.join(os.path.dirname(__file__), "anime.db")

def get_connection():
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        # PostgreSQL (Render/Railway uchun)
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        # SQLite (Local/VPS uchun)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    
    # SQLite va PostgreSQL uchun mos keladigan SQL
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        # PostgreSQL
        cur.execute("""
            CREATE TABLE IF NOT EXISTS animes (
                id          SERIAL PRIMARY KEY,
                title       TEXT NOT NULL,
                description TEXT,
                photo_file_id TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id       SERIAL PRIMARY KEY,
                anime_id INTEGER NOT NULL REFERENCES animes(id),
                season   INTEGER NOT NULL DEFAULT 1,
                episode  INTEGER NOT NULL,
                file_id  TEXT NOT NULL
            );
        """)
        cur.execute("""
            ALTER TABLE animes
            ADD COLUMN IF NOT EXISTS is_premium BOOLEAN NOT NULL DEFAULT FALSE;
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS premium_subscriptions (
                user_id     BIGINT PRIMARY KEY,
                expires_at  BIGINT,
                is_vip      BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS premium_payments (
                id                         SERIAL PRIMARY KEY,
                user_id                    BIGINT NOT NULL,
                plan_code                  TEXT NOT NULL,
                amount                     INTEGER NOT NULL,
                currency                   TEXT NOT NULL,
                telegram_payment_charge_id TEXT NOT NULL UNIQUE,
                provider_payment_charge_id TEXT,
                created_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    else:
        # SQLite
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS animes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                photo_file_id TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS episodes (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER NOT NULL,
                season   INTEGER NOT NULL DEFAULT 1,
                episode  INTEGER NOT NULL,
                file_id  TEXT NOT NULL,
                FOREIGN KEY (anime_id) REFERENCES animes(id)
            );
        """)
        cur.execute("PRAGMA table_info(animes)")
        anime_columns = {row[1] for row in cur.fetchall()}
        if "is_premium" not in anime_columns:
            cur.execute(
                "ALTER TABLE animes ADD COLUMN is_premium INTEGER NOT NULL DEFAULT 0"
            )
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS premium_subscriptions (
                user_id     INTEGER PRIMARY KEY,
                expires_at  INTEGER,
                is_vip      INTEGER NOT NULL DEFAULT 0,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS premium_payments (
                id                         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id                    INTEGER NOT NULL,
                plan_code                  TEXT NOT NULL,
                amount                     INTEGER NOT NULL,
                currency                   TEXT NOT NULL,
                telegram_payment_charge_id TEXT NOT NULL UNIQUE,
                provider_payment_charge_id TEXT,
                created_at                 DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
    conn.commit()
    conn.close()

def add_anime(title: str, description: str = "", photo_file_id: str = None) -> int | None:
    conn = get_connection()
    cur = conn.cursor()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur.execute(
            "INSERT INTO animes (title, description, photo_file_id) VALUES (%s, %s, %s) RETURNING id",
            (title, description, photo_file_id)
        )
        anime_id = cur.fetchone()[0]
    else:
        cur.execute("INSERT INTO animes (title, description, photo_file_id) VALUES (?, ?, ?)", (title, description, photo_file_id))
        anime_id = cur.lastrowid
    conn.commit()
    conn.close()
    return anime_id

def get_anime(anime_id: int) -> dict | None:
    conn = get_connection()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM animes WHERE id = %s", (anime_id,))
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM animes WHERE id = ?", (anime_id,))
    
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def add_episode(anime_id: int, season: int, episode: int, file_id: str) -> int | None:
    conn = get_connection()
    cur = conn.cursor()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur.execute(
            "INSERT INTO episodes (anime_id, season, episode, file_id) VALUES (%s, %s, %s, %s) RETURNING id",
            (anime_id, season, episode, file_id)
        )
        ep_id = cur.fetchone()[0]
    else:
        cur.execute(
            "INSERT INTO episodes (anime_id, season, episode, file_id) VALUES (?, ?, ?, ?)",
            (anime_id, season, episode, file_id),
        )
        ep_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ep_id

def get_episodes(anime_id: int) -> list[dict]:
    conn = get_connection()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM episodes WHERE anime_id = %s ORDER BY season, episode", (anime_id,))
    else:
        cur = conn.cursor()
        cur.execute("SELECT * FROM episodes WHERE anime_id = ? ORDER BY season, episode", (anime_id,))
    
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def list_animes() -> list[dict]:
    conn = get_connection()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, title FROM animes ORDER BY id")
    else:
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM animes ORDER BY id")
    
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def list_animes_with_episode_counts() -> list[dict]:
    conn = get_connection()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT a.id, a.title, a.is_premium, COUNT(e.id) AS episode_count
            FROM animes a
            LEFT JOIN episodes e ON e.anime_id = a.id
            GROUP BY a.id, a.title, a.is_premium
            ORDER BY a.id
        """)
    else:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.id, a.title, a.is_premium, COUNT(e.id) AS episode_count
            FROM animes a
            LEFT JOIN episodes e ON e.anime_id = a.id
            GROUP BY a.id, a.title, a.is_premium
            ORDER BY a.id
        """)

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_anime(anime_id: int):
    conn = get_connection()
    cur = conn.cursor()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur.execute("DELETE FROM episodes WHERE anime_id = %s", (anime_id,))
        cur.execute("DELETE FROM animes WHERE id = %s", (anime_id,))
    else:
        cur.execute("DELETE FROM episodes WHERE anime_id = ?", (anime_id,))
        cur.execute("DELETE FROM animes WHERE id = ?", (anime_id,))
    conn.commit()
    conn.close()

def update_anime(anime_id: int, title: str = None, description: str = None, photo_file_id: str = None):
    anime = get_anime(anime_id)
    if not anime:
        return False
    
    title = title if title is not None else anime['title']
    description = description if description is not None else anime['description']
    photo_file_id = photo_file_id if photo_file_id is not None else anime['photo_file_id']
    
    conn = get_connection()
    cur = conn.cursor()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur.execute(
            "UPDATE animes SET title = %s, description = %s, photo_file_id = %s WHERE id = %s",
            (title, description, photo_file_id, anime_id)
        )
    else:
        cur.execute(
            "UPDATE animes SET title = ?, description = ?, photo_file_id = ? WHERE id = ?",
            (title, description, photo_file_id, anime_id)
        )
    conn.commit()
    conn.close()
    return True

def set_anime_premium(anime_id: int, is_premium: bool) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur.execute(
            "UPDATE animes SET is_premium = %s WHERE id = %s",
            (is_premium, anime_id),
        )
    else:
        cur.execute(
            "UPDATE animes SET is_premium = ? WHERE id = ?",
            (int(is_premium), anime_id),
        )
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_premium_status(user_id: int) -> dict:
    conn = get_connection()
    if DATABASE_URL and PSCOPG2_AVAILABLE:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT expires_at, is_vip FROM premium_subscriptions WHERE user_id = %s",
            (user_id,),
        )
    else:
        cur = conn.cursor()
        cur.execute(
            "SELECT expires_at, is_vip FROM premium_subscriptions WHERE user_id = ?",
            (user_id,),
        )
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"active": False, "is_vip": False, "expires_at": None}

    status = dict(row)
    is_vip = bool(status["is_vip"])
    expires_at = status["expires_at"]
    active = is_vip or (expires_at is not None and int(expires_at) > int(time.time()))
    return {
        "active": active,
        "is_vip": is_vip,
        "expires_at": int(expires_at) if expires_at is not None else None,
    }

def activate_premium(
    user_id: int,
    plan_code: str,
    duration_days: int | None,
    amount: int,
    currency: str,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str = "",
) -> dict:
    """To'lovni bir marta yozadi va premium muddatini uzaytiradi."""
    conn = get_connection()
    cur = conn.cursor()
    is_postgres = bool(DATABASE_URL and PSCOPG2_AVAILABLE)

    if is_postgres:
        # Bir foydalanuvchining bir vaqtdagi to'lovlari muddatni yo'qotib qo'ymasligi uchun.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
        cur.execute(
            """
            INSERT INTO premium_payments (
                user_id, plan_code, amount, currency,
                telegram_payment_charge_id, provider_payment_charge_id
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (telegram_payment_charge_id) DO NOTHING
            """,
            (
                user_id,
                plan_code,
                amount,
                currency,
                telegram_payment_charge_id,
                provider_payment_charge_id,
            ),
        )
    else:
        cur.execute(
            """
            INSERT OR IGNORE INTO premium_payments (
                user_id, plan_code, amount, currency,
                telegram_payment_charge_id, provider_payment_charge_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                plan_code,
                amount,
                currency,
                telegram_payment_charge_id,
                provider_payment_charge_id,
            ),
        )

    if cur.rowcount == 0:
        conn.close()
        return get_premium_status(user_id)

    if is_postgres:
        cur.execute(
            "SELECT expires_at, is_vip FROM premium_subscriptions WHERE user_id = %s FOR UPDATE",
            (user_id,),
        )
    else:
        cur.execute(
            "SELECT expires_at, is_vip FROM premium_subscriptions WHERE user_id = ?",
            (user_id,),
        )
    current_row = cur.fetchone()
    if current_row and is_postgres:
        current = {"expires_at": current_row[0], "is_vip": current_row[1]}
    else:
        current = dict(current_row) if current_row else None

    now = int(time.time())
    already_vip = bool(current and current["is_vip"])
    if already_vip or duration_days is None:
        expires_at = None
        is_vip = True
    else:
        current_expiry = int(current["expires_at"]) if current and current["expires_at"] else 0
        expires_at = max(now, current_expiry) + duration_days * 24 * 60 * 60
        is_vip = False

    if is_postgres:
        cur.execute(
            """
            INSERT INTO premium_subscriptions (user_id, expires_at, is_vip, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
                expires_at = EXCLUDED.expires_at,
                is_vip = EXCLUDED.is_vip,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, expires_at, is_vip),
        )
    else:
        cur.execute(
            """
            INSERT INTO premium_subscriptions (user_id, expires_at, is_vip, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                expires_at = excluded.expires_at,
                is_vip = excluded.is_vip,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, expires_at, int(is_vip)),
        )

    conn.commit()
    conn.close()
    return {"active": True, "is_vip": is_vip, "expires_at": expires_at}
