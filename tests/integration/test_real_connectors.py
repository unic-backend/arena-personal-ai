"""Opt-in probes against real external connector backends.

These tests are deliberately absent from the normal offline proof. A missing
credential/service is SKIPPED, never promoted to PASS. No write capability is
called here.
"""
from __future__ import annotations

import os
import shutil

import pytest

from core.connectors.agent_reach import ConnecteurAgentReach
from core.connectors.calendrier import CalendarConnector
from core.connectors.gmail import GmailConnector
from core.connectors.github import GitHubConnector
from core.connectors.base import EtatSante

pytestmark = pytest.mark.integration


def _enabled() -> None:
    if os.getenv("RUN_REAL_INTEGRATION") != "1":
        pytest.skip("SKIPPED — REAL_INTEGRATION opt-in disabled")


def _require(*names: str) -> None:
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        pytest.skip(
            "SKIPPED — REAL_INTEGRATION credentials unavailable: "
            + ", ".join(missing)
        )


def _assert_real_health(connector) -> None:
    health = connector.sonder()
    assert health.etat is EtatSante.OPERATIONNEL, (
        f"{connector.nom}: real health is {health.etat.value}: {health.message}"
    )


def test_gmail_real_auth_and_safe_read() -> None:
    _enabled()
    _require("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    # sonder() obtains a real OAuth access token and reads users/me/profile.
    _assert_real_health(GmailConnector())


def test_calendar_real_auth_and_safe_read() -> None:
    _enabled()
    _require("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    # sonder() authenticates and performs the connector's harmless health read.
    _assert_real_health(CalendarConnector())


def test_github_real_auth_and_safe_read() -> None:
    _enabled()
    _require("USMAN_GITHUB_TOKEN")
    # sonder() calls GitHub with the configured token; no mutation capability.
    _assert_real_health(GitHubConnector())


def test_agent_reach_real_doctor() -> None:
    _enabled()
    if shutil.which("agent-reach") is None:
        pytest.skip("SKIPPED — REAL_INTEGRATION service unavailable: agent-reach CLI")
    _assert_real_health(ConnecteurAgentReach())
