from core.memory.memory_manager import (
    MAX_LISTED_FACTS,
    MAX_RECENT_HISTORY,
    MemoryManager,
)


def test_negative_history_limit_never_means_unbounded(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    for index in range(3):
        memory.add_chat_message("session", "user", f"message-{index}")

    assert memory.get_recent_history("session", limit=-1) == []


def test_history_limit_is_capped(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    for index in range(MAX_RECENT_HISTORY + 5):
        memory.add_chat_message("session", "user", f"message-{index}")

    history = memory.get_recent_history("session", limit=10_000)

    assert len(history) == MAX_RECENT_HISTORY
    assert history[0]["content"] == "message-5"


def test_negative_fact_limit_never_means_unbounded(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    memory.set_fact("profile", "name", "Arena")

    assert memory.list_facts("profile", limit=-1) == []


def test_fact_limit_is_capped(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    for index in range(MAX_LISTED_FACTS + 5):
        memory.set_fact("profile", f"key-{index}", index)

    facts = memory.list_facts("profile", limit=10_000)

    assert len(facts) == MAX_LISTED_FACTS
