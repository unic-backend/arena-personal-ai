"""Qui a le droit d'appeler l'API depuis un navigateur.

Le montage visé par le propriétaire, et c'est lui qui explique cette liste :

    la PAGE vient de Railway (toujours allumé)
    le CERVEAU est son PC quand il tourne, Railway sinon

Sans l'origine Railway, le navigateur bloque l'appel de la page vers son PC,
et la bascule à deux adresses ne sert à rien : il n'aurait accès à sa machine
qu'en ouvrant l'adresse du tunnel, **qui change à chaque démarrage**.

Ce fichier tient les deux bouts. Une origine manquante casse son usage ; une
origine de trop ouvre son API à un site tiers. Les deux se mesurent.
"""
from pathlib import Path

import pytest

from apps.backend.config import ALLOWED_ORIGINS, ORIGINES_PAR_DEFAUT

RACINE = Path(__file__).resolve().parent.parent


def test_le_domaine_railway_est_autorise_par_defaut():
    """Un réglage qu'on ne peut pas livrer est un réglage qui ne sera pas mis.

    L'alternative était de lui faire éditer `.env` à la main, sur sa machine,
    à chaque installation.
    """
    assert "https://arena-personal-ai-production.up.railway.app" in ORIGINES_PAR_DEFAUT


def test_localhost_reste_autorise():
    """Cette liste **remplace** la valeur par défaut quand elle est définie.

    Y mettre Railway sans garder `localhost` couperait l'accès depuis son
    propre PC — le correctif casserait ce qu'il répare.
    """
    for port in ("3000", "8000"):
        assert f"http://localhost:{port}" in ORIGINES_PAR_DEFAUT


def test_aucun_joker_dans_les_origines():
    """**La garde qui compte.**

    `*` laisserait n'importe quel site appeler son API depuis le navigateur
    d'un visiteur. `*.up.railway.app` serait à peine mieux : toute application
    hébergée là-bas passerait.
    """
    for origine in ALLOWED_ORIGINS:
        assert "*" not in origine, f"joker dans les origines : {origine}"


@pytest.mark.parametrize("origine", ALLOWED_ORIGINS)
def test_chaque_origine_est_bien_formee(origine):
    """Une origine porte un schéma et **pas de barre finale**.

    `https://exemple.com/` ne correspond à rien : le navigateur compare une
    chaîne exacte, et le blocage resterait sans que rien ne le dise.
    """
    assert origine.startswith(("http://", "https://")), (
        f"« {origine} » n'est pas une origine : il manque le schema")
    assert not origine.endswith("/"), (
        f"« {origine} » finit par une barre : aucune page ne correspondra")
    assert " " not in origine


def test_le_reglage_du_proprietaire_reste_prioritaire(monkeypatch):
    """La liste par défaut est un confort, pas une contrainte : `.env` gagne.

    **La variable porte le préfixe `USMAN_`** (`reglage()` le pose). Ce test
    a d'abord échoué en cherchant `ALLOWED_ORIGINS` tout court — et c'est
    exactement le nom que le propriétaire avait reçu pour son `.env`, donc un
    réglage qui n'aurait jamais été lu. Une consigne fausse coûte plus cher
    qu'un test rouge.
    """
    import importlib

    from apps.backend import config

    monkeypatch.setenv("USMAN_ALLOWED_ORIGINS", "https://ailleurs.test")
    recharge = importlib.reload(config)
    try:
        assert recharge.ALLOWED_ORIGINS == ["https://ailleurs.test"]
    finally:
        monkeypatch.delenv("USMAN_ALLOWED_ORIGINS", raising=False)
        importlib.reload(config)
