"""
services/cache.py – Serverseitiger Hybrid-Cache (Redis → SQLite Fallback)

Stellt eine einzige globale Cache-Instanz bereit, die von allen Routern
und Services importiert wird. Redis wird bevorzugt; fällt es aus, wird
automatisch auf eine SQLite-Tabelle gewechselt (Zero-Downtime).
"""

import json
import logging
import time
import sqlite3
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HybridCache:
    """
    Zweistufiger Cache: Redis (schnell, flüchtig) → SQLite (persistent, langsamer).

    - Bei Redis-Fehler zur Laufzeit wird automatisch auf SQLite umgeschaltet.
    - TTL (Time-to-Live) wird sowohl in Redis als auch in SQLite durchgesetzt.
    - Thread-safe für SQLite durch eigene Connection pro Aufruf.
    """

    def __init__(
        self,
        db_path: str = "mtg_app.db",
        redis_url: str = "redis://localhost:6379",
        ttl_seconds: int = 86400,
    ):
        self.db_path = db_path
        self.redis_url = redis_url
        self.ttl = ttl_seconds
        self.redis_client = None
        self.use_redis = False

        # --- Redis-Verbindung versuchen ---
        try:
            import redis
            self.redis_client = redis.from_url(redis_url, socket_timeout=1)
            self.redis_client.ping()
            self.use_redis = True
            logger.info("Redis-Cache erfolgreich verbunden!")
        except Exception:
            logger.warning("Redis nicht verfügbar (Nutze SQLite Fallback)", exc_info=True)
            self.use_redis = False

        # --- SQLite Fallback-Tabelle anlegen ---
        if not self.use_redis:
            self._init_sqlite_cache()

    # ------------------------------------------------------------------
    # Internes Setup
    # ------------------------------------------------------------------
    def _init_sqlite_cache(self) -> None:
        """Erstellt die SQLite-Cache-Tabelle und den Timestamp-Index."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scryfall_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    timestamp REAL
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_ts ON scryfall_cache (timestamp)"
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-Initialisierung")

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        """Liefert eine frische SQLite-Connection (Thread-safe)."""
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------
    def get(self, key: str) -> Optional[Any]:
        """
        Liest einen Wert aus dem Cache.
        Gibt `None` zurück, wenn der Key nicht existiert oder abgelaufen ist.
        """
        # 1) Redis versuchen
        if self.use_redis:
            try:
                val = self.redis_client.get(key)
                if val:
                    return json.loads(val.decode("utf-8"))
                return None  # Key existiert nicht in Redis
            except Exception:
                logger.warning("Redis Fehler bei get()", exc_info=True)
                self.use_redis = False
                self._init_sqlite_cache()

        # 2) SQLite Fallback
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value, timestamp FROM scryfall_cache WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                value, timestamp = row
                if time.time() - timestamp < self.ttl:
                    return json.loads(value)
                else:
                    # Abgelaufenen Eintrag löschen
                    conn = self._get_sqlite_conn()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM scryfall_cache WHERE key = ?", (key,))
                    conn.commit()
                    conn.close()
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-Get")

        return None

    def set(self, key: str, data: Any) -> None:
        """Schreibt einen Wert in den Cache (Redis oder SQLite)."""
        value_str = json.dumps(data)

        # 1) Redis versuchen
        if self.use_redis:
            try:
                self.redis_client.setex(key, self.ttl, value_str)
                return
            except Exception:
                logger.warning("Redis Fehler bei set()", exc_info=True)
                self.use_redis = False
                self._init_sqlite_cache()

        # 2) SQLite Fallback
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO scryfall_cache (key, value, timestamp) VALUES (?, ?, ?)",
                (key, value_str, time.time()),
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-Set")

    def delete(self, key: str) -> None:
        """Löscht einen Eintrag aus dem Cache."""
        if self.use_redis:
            try:
                self.redis_client.delete(key)
                return
            except Exception:
                pass

        try:
            conn = self._get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scryfall_cache WHERE key = ?", (key,))
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-Delete")

    def flush_expired(self) -> int:
        """Entfernt alle abgelaufenen Einträge. Gibt Anzahl gelöschter Zeilen zurück."""
        cutoff = time.time() - self.ttl
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scryfall_cache WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            return deleted
        except Exception:
            logger.exception("FEHLER bei flush_expired")
            return 0


# ======================================================================
# Globale Singleton-Instanz – wird von allen Modulen importiert
# ======================================================================
scryfall_cache = HybridCache(ttl_seconds=86400)
