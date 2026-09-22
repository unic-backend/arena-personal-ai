"""Regression guards for Arena's global typography system.

These tests intentionally inspect the PWA source instead of a single screen:
the original defect was repeated one-off pixel sizes spread across shared UI.
"""
from pathlib import Path
import re

from apps.backend.config import BASE_DIR

PWA = BASE_DIR / "apps" / "pwa" / "src"
CSS = (PWA / "index.css").read_text(encoding="utf-8")


def test_semantic_typography_tokens_exist():
    required = [
        "--type-caption:",
        "--type-meta:",
        "--type-body:",
        "--type-body-lg:",
        "--type-nav:",
        "--type-history:",
        "--type-title:",
        "--weight-medium:",
        "--weight-semibold:",
        ".text-ui-nav",
        ".text-ui-history",
        ".text-ui-input",
    ]
    missing = [token for token in required if token not in CSS]
    assert not missing, f"semantic typography tokens missing: {missing}"


def test_mobile_form_text_never_falls_below_16px():
    assert "@media (max-width: 767px)" in CSS
    assert "font-size: max(16px, 1em);" in CSS


def test_user_facing_components_do_not_reintroduce_microscopic_text():
    tiny = re.compile(r"text-\[(?:9|9\.5|10|10\.5|11|11\.5)px\]")
    offenders: list[str] = []

    for folder in [PWA / "components" / "chat", PWA / "components" / "activity"]:
        for path in folder.glob("*.tsx"):
            matches = tiny.findall(path.read_text(encoding="utf-8"))
            if matches:
                offenders.append(f"{path.relative_to(BASE_DIR)}: {sorted(set(matches))}")

    assert not offenders, "microscopic hardcoded UI text returned:\n" + "\n".join(offenders)


def test_sidebar_uses_semantic_navigation_and_history_typography():
    sidebar = (PWA / "components" / "chat" / "Sidebar.tsx").read_text(encoding="utf-8")
    assert "text-ui-nav" in sidebar
    assert "text-ui-history" in sidebar
    assert "text-ui-section" in sidebar
    assert "text-ui-input" in sidebar
