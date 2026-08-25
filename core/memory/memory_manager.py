import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("arena.memory")

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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Short-Term Memory (Conversations)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS short_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Long-Term Memory (Faits, Préférences, Contexte)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    metadata TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Agent Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT,
                    status TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_chat_message(self, session_id: str, role: str, content: str):
        with self._get_connection() as conn:
            conn.cursor().execute(
                "INSERT INTO short_term_memory (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
            conn.commit()

    def get_recent_history(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content FROM short_term_memory WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def set_fact(self, category: str, key: str, value: Any, metadata: Optional[Dict] = None):
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        meta_str = json.dumps(metadata) if metadata else None
        
        with self._get_connection() as conn:
            conn.cursor().execute("""
                INSERT INTO long_term_memory (category, key, value, metadata, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    category=excluded.category,
                    value=excluded.value,
                    metadata=excluded.metadata,
                    updated_at=CURRENT_TIMESTAMP
            """, (category, key, val_str, meta_str))
            conn.commit()

    def get_fact(self, key: str) -> Optional[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM long_term_memory WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
            return None

if __name__ == "__main__":
    mem = MemoryManager()
    mem.set_fact("user_profile", "owner", "Saer", {"role": "Propriétaire"})
    mem.add_chat_message("default", "user", "Bonjour ARENA")
    mem.add_chat_message("default", "assistant", "Bonjour Saer, mémoire SQLite initialisée.")
    
    print("✅ MemoryManager SQLite initialisé avec succès !")
    print("   Propriétaire enregistré:", mem.get_fact("owner"))
    print("   Historique récupéré:", mem.get_recent_history("default"))