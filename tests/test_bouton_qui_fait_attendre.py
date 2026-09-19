"""Un connecteur n'est sondé qu'une fois par tour, quoi qu'il arrive.

`_actions_en_attente()` tourne à la fin de **chaque** tour de conversation.
Pour chaque action qui attend l'accord du propriétaire, elle interroge le
moteur qui l'exécuterait — pour que l'interface puisse griser un bouton qui ne
peut pas aboutir. C'est la bonne intention, et elle reste.

**Mesure du 19/09/2026** : `faceplugin.sonder()` lance le sous-processus du SDK
et répond en **2 990 ms** (`ui_ux_pro_max` : 71 ms, `gmail` : 0 ms). La sonde
était faite une fois PAR ACTION : deux actions `faceplugin` en attente, c'était
deux sondes identiques à la même milliseconde, donc **six secondes ajoutées à
chaque réponse** jusqu'à ce qu'il confirme. Quatre actions, douze secondes —
mesuré, pas extrapolé.

Le commentaire du code disait « la file est vide la plupart du temps, donc ce
contrôle ne coûte rien au cas courant ». C'est vrai. C'était aussi l'hypothèse
qu'il ne fallait pas tenir pour acquise.
"""
from dataclasses import dataclass
from typing import List

import pytest

from apps.backend.routers import pwa_gateway


@dataclass
class ActionFactice:
    identifiant: str
    connecteur: str
    action: str = "envoyer"
    cible: str = "quelque part"
    risque: str = "moyen"
    expire_le: str = "2026-12-31"


class FileFactice:
    def __init__(self, actions: List[ActionFactice]):
        self._actions = actions

    def en_attente(self, limite: int = 50):
        return self._actions[:limite]


@pytest.fixture
def sondes(monkeypatch):
    """Compte les sondes réellement faites, par connecteur."""
    appels: List[str] = []

    def _sonder(nom):
        appels.append(nom)
        return {"disponible": True, "indisponible_raison": ""}

    monkeypatch.setattr(pwa_gateway, "_etat_du_moteur", _sonder)
    return appels


def installer(monkeypatch, *connecteurs):
    actions = [ActionFactice(identifiant=f"a{i}", connecteur=c)
               for i, c in enumerate(connecteurs)]
    monkeypatch.setattr(pwa_gateway, "file_attente", FileFactice(actions))
    return actions


def test_quatre_actions_sur_un_moteur_ne_font_qu_une_sonde(monkeypatch, sondes):
    installer(monkeypatch, "faceplugin", "faceplugin", "faceplugin", "faceplugin")

    pwa_gateway._actions_en_attente()

    assert sondes == ["faceplugin"], (
        f"{len(sondes)} sondes pour un seul moteur : a 2 990 ms chacune, "
        f"c'est {len(sondes) * 3} secondes ajoutees a chaque reponse")


def test_deux_moteurs_differents_sont_sondes_tous_les_deux(monkeypatch, sondes):
    """Dédoublonner ne veut pas dire deviner : la réponse d'un moteur ne dit
    rien d'un autre."""
    installer(monkeypatch, "faceplugin", "gmail", "faceplugin", "gmail")

    pwa_gateway._actions_en_attente()

    assert sorted(sondes) == ["faceplugin", "gmail"]


def test_chaque_action_garde_son_etat(monkeypatch):
    """Une seule sonde, mais chaque action porte quand même sa réponse."""
    def _sonder(nom):
        return {"disponible": nom != "faceplugin",
                "indisponible_raison": "" if nom != "faceplugin" else "SDK absent"}
    monkeypatch.setattr(pwa_gateway, "_etat_du_moteur", _sonder)
    installer(monkeypatch, "faceplugin", "gmail", "faceplugin")

    rendu = pwa_gateway._actions_en_attente()

    assert [a["disponible"] for a in rendu] == [False, True, False]
    assert rendu[0]["indisponible_raison"] == "SDK absent"
    assert [a["id"] for a in rendu] == ["a0", "a1", "a2"], (
        "le dedoublonnage a change l'ordre ou perdu une action")


def test_une_file_vide_ne_sonde_rien(monkeypatch, sondes):
    installer(monkeypatch)

    assert pwa_gateway._actions_en_attente() == []
    assert sondes == []


def test_une_file_illisible_ne_fait_pas_tomber_la_reponse(monkeypatch, sondes):
    class FileCassee:
        def en_attente(self, limite=50):
            raise RuntimeError("base verrouillee")

    monkeypatch.setattr(pwa_gateway, "file_attente", FileCassee())

    assert pwa_gateway._actions_en_attente() == []
    assert sondes == [], "on a sonde alors que la file etait illisible"
