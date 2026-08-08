import sqlite3
import os

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
            SELECT a.id, a.title, COUNT(e.id) AS episode_count
            FROM animes a
            LEFT JOIN episodes e ON e.anime_id = a.id
            GROUP BY a.id, a.title
            ORDER BY a.id
        """)
    else:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.id, a.title, COUNT(e.id) AS episode_count
            FROM animes a
            LEFT JOIN episodes e ON e.anime_id = a.id
            GROUP BY a.id, a.title
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
