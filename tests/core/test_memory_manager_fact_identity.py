import sqlite3

from core.memory.memory_manager import MemoryManager


def test_same_fact_key_can_exist_in_multiple_categories(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))

    memory.set_fact("profile", "status", "active")
    memory.set_fact("project", "status", "paused")

    assert memory.get_fact("status", category="profile") == "active"
    assert memory.get_fact("status", category="project") == "paused"
    assert len(memory.list_facts("profile")) == 1
    assert len(memory.list_facts("project")) == 1


def test_upsert_only_updates_matching_category_and_key(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    memory.set_fact("profile", "owner", "first")
    memory.set_fact("project", "owner", "other")
    memory.set_fact("profile", "owner", "updated")

    assert memory.get_fact("owner", category="profile") == "updated"
    assert memory.get_fact("owner", category="project") == "other"


def test_legacy_database_is_migrated_without_losing_facts(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE long_term_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            metadata TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO long_term_memory (category, key, value) VALUES (?, ?, ?)",
        ("profile", "owner", "Ousmane"),
    )
    conn.commit()
    conn.close()

    memory = MemoryManager(str(db_path))

    assert memory.get_fact("owner", category="profile") == "Ousmane"
    memory.set_fact("project", "owner", "Arena")
    assert memory.get_fact("owner", category="profile") == "Ousmane"
    assert memory.get_fact("owner", category="project") == "Arena"
