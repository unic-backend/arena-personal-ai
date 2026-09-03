"""Le panneau ne propose que ce que la machine branchée sait faire.

**Mesuré le 03/09/2026 à 02:47.** Le propriétaire, sur son téléphone branché à
Railway, coche des capacités et lance un projet. Retour : `modele de vision :
All connection attempts failed`, `VoiceStudio ne repond pas sur
http://127.0.0.1:3900`. Aucun de ces moteurs n'existe sur Railway — ils
tournent sur son PC. Le panneau proposait les sept sans jamais demander
lesquelles la machine tenait, **et il n'avait aucun moyen de le demander : la
route n'existait pas**.

Le défaut est le même que celui de la nuit : annoncer une capacité qu'on n'a
pas. Ici il ne mentait pas dans une phrase, il mentait dans un bouton.
"""
import asyncio
from pathlib import Path

from core.connectors.base import EtatSante, Sante
from core.production.disponibilite import PAR_CONNECTEUR, disponibilite_video
from core.production.plan_video import CAPACITES_VIDEO

RACINE = Path(__file__).resolve().parent.parent
PWA = RACINE / "apps" / "pwa" / "src"


class _ConnecteurDouble:
    def __init__(self, sante):
        self._sante = sante

    def sonder(self):
        if isinstance(self._sante, Exception):
            raise self._sante
        return self._sante


class _RegistreDouble:
    def __init__(self, par_nom):
        self._par_nom = par_nom

    def obtenir(self, nom):
        return self._par_nom[nom]


class _VisionDouble:
    def __init__(self, valeur):
        self._valeur = valeur

    async def is_available(self):
        if isinstance(self._valeur, Exception):
            raise self._valeur
        return self._valeur


def _registre(etat=EtatSante.OPERATIONNEL, message=""):
    return _RegistreDouble({
        nom: _ConnecteurDouble(Sante(etat=etat, message=message))
        for nom in set(PAR_CONNECTEUR.values())
    })


def test_toutes_les_capacites_du_serveur_sont_couvertes():
    """Une capacité oubliée ici s'afficherait activable quoi qu'il arrive.

    C'est la garde qui compte : `xaar_kaname` avait déjà disparu d'une liste
    parallèle le même jour. Une liste qu'on recopie à la main dérive.
    """
    rendu = asyncio.run(disponibilite_video(_registre(), _VisionDouble(True)))

    assert set(rendu) == set(CAPACITES_VIDEO), (
        f"capacites sans verdict : {set(CAPACITES_VIDEO) - set(rendu)}")


def test_une_capacite_indisponible_porte_toujours_sa_raison():
    """« Indisponible » sans dire pourquoi renvoie chercher une panne sans la
    nommer — c'est ce que le propriétaire a vécu."""
    rendu = asyncio.run(disponibilite_video(
        _registre(EtatSante.NON_CONFIGURE, "VoiceStudio ne repond pas"),
        _VisionDouble(False)))

    for nom, etat in rendu.items():
        assert etat["disponible"] is False
        assert etat["raison"].strip(), f"{nom} est refuse sans raison"


def test_une_sonde_qui_leve_ne_fait_pas_disparaitre_les_autres():
    """Sans cette garde, un moteur en panne effacerait les six autres verdicts
    et le panneau n'afficherait plus rien du tout."""
    registre = _RegistreDouble({
        nom: _ConnecteurDouble(
            OSError("socket") if nom == "audio"
            else Sante(etat=EtatSante.OPERATIONNEL))
        for nom in set(PAR_CONNECTEUR.values())
    })

    rendu = asyncio.run(disponibilite_video(registre, _VisionDouble(True)))

    assert set(rendu) == set(CAPACITES_VIDEO)
    assert rendu["narration"]["disponible"] is False
    assert "OSError" in rendu["narration"]["raison"]
    assert rendu["montage"]["disponible"] is True


def test_sans_modele_de_vision_la_vision_est_refusee_avec_sa_raison():
    """Jamais supposée présente parce que le fournisseur manque."""
    rendu = asyncio.run(disponibilite_video(_registre(), None))

    assert rendu["vision"]["disponible"] is False
    assert rendu["vision"]["raison"]


def test_la_route_existe_et_est_protegee_par_la_cle():
    passerelle = (RACINE / "apps" / "backend" / "routers"
                  / "pwa_gateway.py").read_text(encoding="utf-8")
    bloc = passerelle.split('@router.get("/agent/capabilities"')[1][:200]

    assert "verify_api_key" in bloc, (
        "la route dirait ce que la machine sait faire a n'importe qui")


def test_linterface_grise_ce_qui_ne_peut_pas_tourner():
    modale = (PWA / "components" / "chat" / "VideoProjectModal.tsx").read_text(encoding="utf-8")

    assert "disabled={indisponible}" in modale, (
        "une capacite impossible reste cliquable")
    assert "indisponibles.map" in modale, (
        "la raison n'est lisible qu'au survol : un telephone n'a pas de survol")


def test_ne_rien_savoir_ne_saffiche_pas_comme_tout_marche():
    """Si le serveur ne répond pas à la sonde, l'état reste `null` et aucun
    verdict n'est affiché — ni « disponible », ni « indisponible »."""
    store = (PWA / "lib" / "store" / "videoProjectStore.ts").read_text(encoding="utf-8")
    # La methode se termine sur `\n  },` — a l'indentation de la methode.
    # Couper sur `},` tout court s'arretait a l'objet `headers`, deux lignes
    # plus haut, et le test mesurait alors un corps qui n'existait pas.
    corps = store.split("async chargerDisponibilite()")[1].split("\n  },")[0]

    # Les TROIS sorties d'echec doivent effacer le verdict, pas seulement
    # deux : compter les occurrences laissait passer le sabotage du
    # 03/09/2026 — le `catch` vide, les deux autres branches intactes, test
    # vert. Une garde qui compte sans regarder ou ne garde rien.
    for branche, extrait in (
        ("aucun serveur branche", corps.split("if (!cfg)")[1][:80]),
        ("reponse en erreur", corps.split("if (!res.ok)")[1][:80]),
        ("panne reseau", corps.split("} catch")[1][:80]),
    ):
        assert "disponibilite: null" in extrait, (
            f"« {branche} » garderait un ancien verdict a l'ecran")
