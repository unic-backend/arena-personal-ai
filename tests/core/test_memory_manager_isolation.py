import pytest

from core.memory.memory_manager import AmbiguousMemoryFactError, MemoryManager


def test_scoped_facts_with_same_key_remain_isolated(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    memory.set_fact("user_profile", "status", "available")
    memory.set_fact("project", "status", "blocked")

    assert memory.get_fact("status", category="user_profile") == "available"
    assert memory.get_fact("status", category="project") == "blocked"


def test_unscoped_fact_read_rejects_cross_category_ambiguity(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    memory.set_fact("user_profile", "owner", "Ousmane")
    memory.set_fact("project", "owner", "Arena")

    with pytest.raises(AmbiguousMemoryFactError, match="pass category explicitly"):
        memory.get_fact("owner")


def test_unscoped_fact_read_keeps_legacy_single_match_behavior(tmp_path):
    memory = MemoryManager(str(tmp_path / "memory.db"))
    memory.set_fact("user_profile", "owner", "Ousmane")

    assert memory.get_fact("owner") == "Ousmane"
    assert memory.get_fact("missing") is None
