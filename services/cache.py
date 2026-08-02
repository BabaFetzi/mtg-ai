"""
services/cache.py – Serverseitiger Hybrid-Cache (Redis → SQLite Fallback)

Stellt eine einzige globale Cache-Instanz bereit, die von allen Routern
und Services importiert wird. Redis wird bevorzugt; fällt es aus, wird
automatisch auf eine SQLite-Tabelle gewechselt (Zero-Downtime).
"""

import json
import logging
import os
import threading
import time
import sqlite3
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Prozessinterner Speicher-Cache VOR Redis/SQLite. Kartendaten werden beim
# Rendern einer Sammlung hunderte Male gelesen; ohne diese Ebene kostet jeder
# einzelne Treffer einen Netzwerk- bzw. Datei-Zugriff.
MEM_CACHE_MAX_ENTRIES = int(os.getenv("CACHE_MEMORY_MAX_ENTRIES", "5000"))
# Bewusst kürzer als die Gesamt-TTL: laufen mehrere Worker-Prozesse, sollen
# Aktualisierungen (z.B. neue Preise) trotzdem zeitnah durchschlagen.
MEM_CACHE_TTL_SECONDS = int(os.getenv("CACHE_MEMORY_TTL_SECONDS", "300"))

# SQLite erlaubt nur begrenzt viele Parameter pro Query.
_SQLITE_MAX_VARIABLES = 500


class HybridCache:
    """
    Zweistufiger Cache: Redis (schnell, flüchtig) → SQLite (persistent, langsamer).

    - Bei Redis-Fehler zur Laufzeit wird automatisch auf SQLite umgeschaltet.
    - TTL (Time-to-Live) wird sowohl in Redis als auch in SQLite durchgesetzt.
    - Thread-safe für SQLite durch eigene Connection pro Aufruf.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        redis_url: Optional[str] = None,
        ttl_seconds: int = 86400,
    ):
        # WICHTIG: Der Karten-Cache liegt in einer EIGENEN SQLite-Datei, nicht in
        # der App-Datenbank. Vorher teilten sich Cache-Schreibvorgänge (bei einem
        # Sammlungs-Refresh hunderte pro Sekunde) die Datei mit nutzer/decks/
        # sammlung_alben -- SQLite sperrt beim Schreiben die ganze Datei, wodurch
        # Login und Sammlung minutenlang blockierten. Getrennte Dateien = keine
        # Sperr-Konkurrenz zwischen Cache und Nutzerdaten.
        self.db_path = db_path or os.getenv("CACHE_DB_PATH", "scryfall_cache.db")
        # Erst zur Instanziierung ausgewertet (nicht als Default-Parameter-
        # Wert bei Modul-Import) -- REDIS_URL wie an den anderen Stellen im
        # Projekt (services/limiter.py, services/usage_limiter.py) aus der
        # Umgebung gelesen, damit es sowohl lokal als auch containerisiert
        # korrekt funktioniert, statt fest auf localhost verdrahtet zu sein.
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.ttl = ttl_seconds
        self.redis_client = None
        self.use_redis = False

        # Speicher-Cache (LRU + TTL) und pro Thread wiederverwendete SQLite-
        # Verbindung. Vorher wurde für JEDEN Cache-Zugriff eine neue Verbindung
        # geöffnet -- bei einer Sammlung mit hunderten Karten waren das hunderte
        # Verbindungsaufbauten pro Seitenaufruf, synchron im Event-Loop.
        self._mem: "OrderedDict[str, tuple]" = OrderedDict()
        self._mem_lock = threading.Lock()
        self._mem_ttl = min(MEM_CACHE_TTL_SECONDS, ttl_seconds)
        self._local = threading.local()

        # --- Redis-Verbindung versuchen ---
        try:
            import redis
            self.redis_client = redis.from_url(self.redis_url, socket_timeout=1)
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
            # WAL: Leser blockieren Schreiber nicht (und umgekehrt) -- ohne WAL
            # serialisiert SQLite jeden Cache-Zugriff, was bei vielen
            # gleichzeitigen Nutzern zum Flaschenhals wird.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
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
        """Liefert die (pro Thread wiederverwendete) SQLite-Connection.

        Wiederverwendung statt Neuaufbau pro Aufruf: der Verbindungsaufbau war
        bei vielen Karten der dominierende Kostenfaktor.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        self._local.conn = conn
        return conn

    def _reset_sqlite_conn(self) -> None:
        """Verwirft eine defekte Verbindung, damit der nächste Zugriff neu aufbaut."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        self._local.conn = None

    # ------------------------------------------------------------------
    # Prozessinterner Speicher-Cache (LRU + TTL)
    # ------------------------------------------------------------------
    def _mem_get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._mem_lock:
            entry = self._mem.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= now:
                self._mem.pop(key, None)
                return None
            self._mem.move_to_end(key)
            return value

    def _mem_set(self, key: str, value: Any) -> None:
        with self._mem_lock:
            self._mem[key] = (value, time.time() + self._mem_ttl)
            self._mem.move_to_end(key)
            while len(self._mem) > MEM_CACHE_MAX_ENTRIES:
                self._mem.popitem(last=False)

    def _mem_delete(self, key: str) -> None:
        with self._mem_lock:
            self._mem.pop(key, None)

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------
    def get(self, key: str) -> Optional[Any]:
        """
        Liest einen Wert aus dem Cache.
        Gibt `None` zurück, wenn der Key nicht existiert oder abgelaufen ist.
        """
        # 0) Speicher-Cache (kein I/O)
        mem_hit = self._mem_get(key)
        if mem_hit is not None:
            return mem_hit

        # 1) Redis versuchen
        if self.use_redis:
            try:
                val = self.redis_client.get(key)
                if val:
                    parsed = json.loads(val.decode("utf-8"))
                    self._mem_set(key, parsed)
                    return parsed
                return None  # Key existiert nicht in Redis
            except Exception:
                logger.warning("Redis Fehler bei get()", exc_info=True)
                self.use_redis = False
                self._init_sqlite_cache()

        # 2) SQLite Fallback
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.execute(
                "SELECT value, timestamp FROM scryfall_cache WHERE key = ?", (key,)
            )
            row = cursor.fetchone()

            if row:
                value, timestamp = row
                if time.time() - timestamp < self.ttl:
                    parsed = json.loads(value)
                    self._mem_set(key, parsed)
                    return parsed
                # Abgelaufenen Eintrag löschen
                conn.execute("DELETE FROM scryfall_cache WHERE key = ?", (key,))
                conn.commit()
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-Get")
            self._reset_sqlite_conn()

        return None

    def get_many(self, keys: Iterable[str]) -> Dict[str, Any]:
        """
        Liest viele Keys in möglichst WENIGEN Zugriffen.

        Ohne diese Methode kostete das Rendern einer Sammlung einen eigenen
        Redis-Roundtrip bzw. eine eigene SQLite-Abfrage PRO KARTE. Jetzt: ein
        MGET bzw. eine `IN`-Abfrage je Block.

        Returns:
            Dict nur mit den tatsächlich gefundenen (nicht abgelaufenen) Keys.
        """
        result: Dict[str, Any] = {}
        # Reihenfolge erhalten, Duplikate entfernen
        pending: List[str] = list(dict.fromkeys(keys))
        if not pending:
            return result

        # 0) Speicher-Cache
        missing: List[str] = []
        for key in pending:
            hit = self._mem_get(key)
            if hit is not None:
                result[key] = hit
            else:
                missing.append(key)
        if not missing:
            return result

        # 1) Redis (ein einziger MGET)
        if self.use_redis:
            try:
                for key, raw in zip(missing, self.redis_client.mget(missing)):
                    if raw:
                        parsed = json.loads(raw.decode("utf-8"))
                        result[key] = parsed
                        self._mem_set(key, parsed)
                return result
            except Exception:
                logger.warning("Redis Fehler bei get_many()", exc_info=True)
                self.use_redis = False
                self._init_sqlite_cache()

        # 2) SQLite (eine IN-Abfrage je Block)
        try:
            conn = self._get_sqlite_conn()
            now = time.time()
            for start in range(0, len(missing), _SQLITE_MAX_VARIABLES):
                chunk = missing[start:start + _SQLITE_MAX_VARIABLES]
                placeholders = ",".join("?" * len(chunk))
                cursor = conn.execute(
                    f"SELECT key, value, timestamp FROM scryfall_cache WHERE key IN ({placeholders})",
                    chunk,
                )
                for key, value, timestamp in cursor.fetchall():
                    if now - timestamp < self.ttl:
                        parsed = json.loads(value)
                        result[key] = parsed
                        self._mem_set(key, parsed)
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-GetMany")
            self._reset_sqlite_conn()

        return result

    def set(self, key: str, data: Any) -> None:
        """Schreibt einen Wert in den Cache (Speicher + Redis oder SQLite)."""
        value_str = json.dumps(data)
        self._mem_set(key, data)

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
            conn.execute(
                "INSERT OR REPLACE INTO scryfall_cache (key, value, timestamp) VALUES (?, ?, ?)",
                (key, value_str, time.time()),
            )
            conn.commit()
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-Set")
            self._reset_sqlite_conn()

    def delete(self, key: str) -> None:
        """Löscht einen Eintrag aus dem Cache."""
        self._mem_delete(key)

        if self.use_redis:
            try:
                self.redis_client.delete(key)
                return
            except Exception:
                pass

        try:
            conn = self._get_sqlite_conn()
            conn.execute("DELETE FROM scryfall_cache WHERE key = ?", (key,))
            conn.commit()
        except Exception:
            logger.exception("FEHLER bei SQLite Cache-Delete")
            self._reset_sqlite_conn()

    def flush_expired(self) -> int:
        """Entfernt alle abgelaufenen Einträge. Gibt Anzahl gelöschter Zeilen zurück."""
        cutoff = time.time() - self.ttl
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.execute("DELETE FROM scryfall_cache WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        except Exception:
            logger.exception("FEHLER bei flush_expired")
            self._reset_sqlite_conn()
            return 0


# ======================================================================
# Globale Singleton-Instanz – wird von allen Modulen importiert
# ======================================================================
scryfall_cache = HybridCache(ttl_seconds=86400)
