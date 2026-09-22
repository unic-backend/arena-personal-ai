import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.memory")


class MemoryManager:
    def __init__(self, db_path: str = "data/database/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS short_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    metadata TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self._migrate_fact_identity(cursor)
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_long_term_memory_category_key "
                "ON long_term_memory(category, key)"
            )
            conn.commit()

    @staticmethod
    def _migrate_fact_identity(cursor: sqlite3.Cursor) -> None:
        """Replace the legacy global UNIQUE(key) constraint with category-scoped identity.

        A fact key such as ``status`` or ``owner`` is not globally unique across memory
        domains. The old schema silently moved an existing fact to another category when
        the same key was written there. Rebuilding the table preserves existing rows while
        making ``(category, key)`` the durable identity.
        """
        row = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='long_term_memory'"
        ).fetchone()
        schema = (row[0] if row else "") or ""
        normalized = " ".join(schema.upper().split())
        if "KEY TEXT UNIQUE" not in normalized:
            return

        cursor.execute("ALTER TABLE long_term_memory RENAME TO long_term_memory_legacy")
        cursor.execute("""
            CREATE TABLE long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                metadata TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO long_term_memory (id, category, key, value, metadata, updated_at)
            SELECT id, category, key, value, metadata, updated_at
            FROM long_term_memory_legacy
        """)
        cursor.execute("DROP TABLE long_term_memory_legacy")

    def add_chat_message(self, session_id: str, role: str, content: str):
        with closing(self._get_connection()) as conn:
            conn.cursor().execute(
                "INSERT INTO short_term_memory (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            conn.commit()

    def get_recent_history(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content FROM short_term_memory WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
            rows = cursor.fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def set_fact(self, category: str, key: str, value: Any, metadata: Optional[Dict] = None):
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        meta_str = json.dumps(metadata) if metadata else None

        with closing(self._get_connection()) as conn:
            conn.cursor().execute(
                """
                INSERT INTO long_term_memory (category, key, value, metadata, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(category, key) DO UPDATE SET
                    value=excluded.value,
                    metadata=excluded.metadata,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (category, key, val_str, meta_str),
            )
            conn.commit()

    def get_fact(self, key: str, category: Optional[str] = None) -> Optional[Any]:
        """Return a fact by key, optionally scoped to a category.

        The optional category keeps existing callers compatible while allowing callers
        that know their memory domain to avoid ambiguous cross-category reads.
        """
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
            if category is None:
                cursor.execute(
                    "SELECT value FROM long_term_memory WHERE key = ? "
                    "ORDER BY updated_at DESC, id DESC LIMIT 1",
                    (key,),
                )
            else:
                cursor.execute(
                    "SELECT value FROM long_term_memory WHERE category = ? AND key = ?",
                    (category, key),
                )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    return row["value"]
            return None

    def list_facts(self, category: str, limit: int = 8) -> List[Dict[str, Any]]:
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT key, value, metadata, updated_at FROM long_term_memory "
                "WHERE category = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
                (category, limit),
            )
            resultats = []
            for row in cursor.fetchall():
                try:
                    valeur = json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    valeur = row["value"]
                metadonnees = None
                if row["metadata"]:
                    try:
                        metadonnees = json.loads(row["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        metadonnees = row["metadata"]
                resultats.append(
                    {
                        "key": row["key"],
                        "value": valeur,
                        "metadata": metadonnees,
                        "updated_at": row["updated_at"],
                    }
                )
            return resultats


if __name__ == "__main__":
    mem = MemoryManager()
    mem.set_fact("user_profile", "owner", "Ousmane", {"role": "Propriétaire"})
    mem.add_chat_message("default", "user", "Bonjour Usman")
    mem.add_chat_message("default", "assistant", "Bonjour Usman, mémoire SQLite initialisée.")

    print("MemoryManager SQLite initialise avec succes !")
    print("   Proprietaire enregistre:", mem.get_fact("owner", category="user_profile"))
    print("   Historique recupere:", mem.get_recent_history("default"))
