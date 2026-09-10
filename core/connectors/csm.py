"""Sesame CSM : parole CONVERSATIONNELLE, en pilotant un service local par HTTP.

**Audit complet** → `docs/audits/sesame_csm_audit.md`. Ce fichier applique ce
que cet audit a mesure, il ne le repete pas.

**CSM n'est PAS un moteur de VoiceStudio.** C'est un second projet, distinct,
etudie sur son propre depot (`SesameAILabs/csm`, commit `daed31e`). Code ET
poids Apache-2.0 (LICENSE du depot + fiche HF `sesame/csm-1b`, verifies
directement) — a la difference de VoiceStudio (AGPL-3.0) ou KrillinAI
(GPL-3.0), rien n'interdit juridiquement d'importer ce code dans ARENA. La
frontiere retenue ici est quand meme **la meme frontiere « service separe,
appele par HTTP »** que pour VoiceStudio et WanGP, et pour une raison
DIFFERENTE, purement technique cette fois (mission §7) : les dependances de
CSM (`torch==2.4.0`, `torchtune==0.4.0`, `torchao==0.9.0`, `moshi==0.2.2`)
sont des epingles etroites, exactement le genre qui a deja casse la CI de ce
depot une fois (Pillow vs `browser-use`, DEC-0079). Les meler a
`requirements.txt` d'ARENA cree un second conflit pour un seul benefice :
`tools/audio/csm_service/` isole ces dependances dans son propre
environnement, et ce connecteur ne lui parle que par HTTP.

**Ce que ce connecteur NE fait PAS, et c'est deliberer** :

- **Aucun clonage de voix, aucun conditionnement par un fichier audio fourni
  par l'appelant.** CSM sait pourtant le faire (« audio prompting » / contexte
  avec un `Segment` porteur d'un vrai enregistrement) — ce fichier n'expose
  jamais ce chemin. Meme regle absolue que `core/connectors/krillinai.py`
  (« si tu vois quelque chose de nouveau [pres du deep face], ignore-le, ne le
  touche meme pas ») : une identite vocale a partir d'un enregistrement fourni
  est un risque d'usurpation, et ARENA a deja un chemin **autorise et
  consenti** pour ca (`core/connectors/audio_voix.py::_cloner`) — en ouvrir un
  second, plus faible, serait la duplication que la mission interdit ET une
  regression de securite.
- **Aucune langue promise que la fiche officielle elle-meme ne promet pas.**
  Le FAQ du depot CSM est explicite : « has some capacity for non-English
  languages due to data contamination [...] but it likely won't do well ».
  `core/audio/routage_tts.py` ecarte donc ce moteur hors de l'anglais — pas ce
  fichier, qui reste agnostique de la decision de routage.

**Trois regles, au-dela du contrat commun `Connecteur`** :

1. **Rien ne sort de la machine.** Meme regle que VoiceStudio
   (`core/audio/verification.py::hote_local_ou_refuse`) : `CSM_URL` doit
   pointer sur la boucle locale.
2. **Le succes est le fichier, pas la reponse HTTP.** Meme sonde
   (`core/audio/verification.py::sonder_le_fichier`) : une duree nulle est un
   echec, jamais un succes silencieux.
3. **Le filigrane de Sesame n'est jamais retire.** `tools/audio/csm_service/`
   l'applique systematiquement (mission §12) — ce connecteur ne fait que
   verifier, via `/health`, que le service qu'il appelle le fait bien
   (`watermarking: true`), et refuse de parler sinon plutot que de produire
   un fichier sans provenance.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.audio.routage_tts import licence_de
from core.audio.verification import (
    AdresseNonLocale,
    hote_local_ou_refuse,
    ressemble_a_du_wav,
    sonder_le_fichier,
)
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

logger = logging.getLogger("usman.connecteurs.csm")

#: L'identifiant que `core/audio/routage_tts.py::LICENCES` connait pour ce
#: moteur. Une seule chaine, jamais recopiee : un desaccord entre ce fichier
#: et le tableau des licences rendrait le moteur "inconnu" en silence.
IDENTIFIANT = "sesame-csm-1b"

#: Ou `tools/audio/csm_service/server.py` ecoute. Port distinct de VoiceStudio
#: (3900) et de WanGP (8765) : les trois services locaux d'ARENA coexistent.
URL_PAR_DEFAUT = "http://127.0.0.1:8901"

#: Ou l'audio produit est ecrit.
DOSSIER_AUDIO = Path("data") / "audio"

#: Un modele de 1 Md de parametres qui charge depuis le disque, puis genere
#: token par token : plus lent qu'un moteur VoiceStudio deja tiedi. Mesure non
#: encore faite sur la RTX A2000 cible (voir l'audit, section GPU) : ce delai
#: est un plafond de securite, pas une mesure.
DELAI_SECONDES = 600.0

CE_QUI_MANQUE = (
    "Le service CSM ne repond pas sur {url}. C'est un serveur qu'ARENA fournit "
    "elle-meme (tools/audio/csm_service/) mais que le proprietaire demarre a part, "
    "dans son propre environnement isole : voir tools/audio/csm_service/README.md."
)


def url_du_service() -> str:
    """L'adresse du service CSM, refusee si elle n'est pas locale.

    Raises:
        AdresseNonLocale: l'hote configure n'est pas la boucle locale.
    """
    url = os.environ.get("CSM_URL", URL_PAR_DEFAUT).rstrip("/")
    return hote_local_ou_refuse(url, "CSM_URL")


def _tracer(appareil: Optional[str], filigrane: Optional[bool]) -> Dict[str, Any]:
    """Ce qui doit rester dans le journal a cote d'un fichier CSM produit."""
    licence = licence_de(IDENTIFIANT)
    return {
        "moteur": IDENTIFIANT,
        "appareil": appareil,
        "licence": licence.licence,
        "usage_commercial": licence.commercial.value,
        "filigrane_applique": filigrane,
    }


class ConnecteurCsm(Connecteur):
    """Parole conversationnelle, en pilotant le service CSM local par HTTP."""

    service = "csm"
    nom = "csm"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else DOSSIER_AUDIO

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "moteurs": Capacite(
                nom="moteurs", action="read",
                description="Dit si le service CSM repond, et ce qu'il a reellement charge.",
                ecriture=False),
            "parler": Capacite(
                nom="parler", action="document",
                description=(
                    "Genere une parole conversationnelle (anglais) avec Sesame CSM, "
                    "verifiee apres ecriture."),
                ecriture=True),
        }

    # --- Sante ------------------------------------------------------------

    def sonder(self) -> Sante:
        """Le service CSM repond-il, et a-t-il vraiment un modele charge ?"""
        from core.connectors.base import _maintenant

        try:
            url = url_du_service()
        except AdresseNonLocale as erreur:
            return Sante(etat=EtatSante.NON_CONFIGURE, message=str(erreur),
                         ce_qui_manque="une adresse locale pour CSM_URL",
                         mesure_le=_maintenant())
        try:
            with httpx.Client(timeout=10.0, trust_env=False) as client:
                reponse = client.get(f"{url}/health")
                reponse.raise_for_status()
                info = reponse.json()
        except (httpx.HTTPError, ValueError) as erreur:
            logger.info("Service CSM injoignable : %s", erreur)
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"Service CSM ne repond pas ({erreur.__class__.__name__}).",
                         ce_qui_manque=CE_QUI_MANQUE.format(url=url),
                         mesure_le=_maintenant())

        if not info.get("model_loaded"):
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"Service CSM repond sur {url}, mais aucun modele charge.",
                ce_qui_manque=str(
                    info.get("ce_qui_manque")
                    or "acces Hugging Face a sesame/csm-1b et meta-llama/Llama-3.2-1B "
                       "(huggingface-cli login, puis acceptation des deux conditions)."),
                mesure_le=_maintenant())

        appareil = info.get("device") or "?"
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=f"Service CSM repond sur {url}, modele charge ({appareil}).",
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : le service CSM ecoute en local, sans identifiant demande a ARENA.

        L'authentification Hugging Face (gated access) est une affaire du
        service lui-meme (`tools/audio/csm_service/`), jamais d'ARENA : ARENA
        ne detient et ne transmet aucun jeton HF.
        """
        return True

    # --- Le coeur -----------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        url = url_du_service()
        if capacite.nom == "moteurs":
            return self._moteurs(url)
        return self._parler(url, **parametres)

    def _moteurs(self, url: str) -> ResultatAction:
        try:
            with httpx.Client(timeout=10.0, trust_env=False) as client:
                info = client.get(f"{url}/health").json()
        except (httpx.HTTPError, ValueError) as erreur:
            return echec(action="moteurs", cible=self.nom,
                         message=f"Service CSM n'a pas repondu : {erreur}")

        if not info.get("model_loaded"):
            return non_configure(
                action="moteurs", cible=self.nom,
                ce_qui_manque=str(info.get("ce_qui_manque") or "modele CSM non charge."))

        licence = licence_de(IDENTIFIANT)
        appareil = info.get("device")
        accelere = bool(info.get("device_is_accelerated"))
        detail = [{
            "id": IDENTIFIANT,
            "appareil": appareil,
            "routage": "accelerated" if accelere else "cpu_only",
            "accelere": accelere,
            "licence": licence.licence,
            "usage_commercial": licence.commercial.value,
            "langues": sorted(licence.langues or ()),
            "conversationnel": licence.conversationnel,
            "filigrane": bool(info.get("watermarking")),
        }]
        return succes(
            action="moteurs", cible=self.nom,
            message=(f"CSM charge sur {appareil or 'un appareil non precise'} "
                     f"({'accelere' if accelere else 'processeur'}). "
                     f"Filigrane : {'actif' if info.get('watermarking') else 'INACTIF — a verifier'}."),
            preuve=f"modele charge sur {appareil or '?'}",
            tts=[IDENTIFIANT], voix=detail, appareils=[appareil] if appareil else [])

    def _parler(self, url: str, texte: str = "", speaker: int = 0,
                conversation: Optional[List[Dict[str, Any]]] = None,
                max_audio_length_ms: int = 10_000, **_: Any) -> ResultatAction:
        propre = (texte or "").strip()
        if not propre:
            return echec(action="parler", cible=self.nom,
                         message="Aucun texte a dire : rien a generer.")

        # `conversation` ne porte QUE du texte + un identifiant de locuteur —
        # jamais un chemin de fichier : le service lui-meme genere l'audio de
        # chaque tour avant de l'utiliser comme contexte du suivant. Un
        # appelant qui tenterait d'y glisser un chemin verrait ce champ ignore
        # cote service (`tools/audio/csm_service/server.py` ne lit que
        # `texte`/`locuteur` de chaque tour), jamais transmis tel quel.
        tours = []
        for tour in (conversation or []):
            texte_tour = str((tour or {}).get("texte") or "").strip()
            if not texte_tour:
                continue
            try:
                locuteur_tour = int((tour or {}).get("speaker", 0))
            except (TypeError, ValueError):
                locuteur_tour = 0
            tours.append({"texte": texte_tour, "speaker": locuteur_tour})

        corps = {
            "texte": propre,
            "speaker": int(speaker) if str(speaker).lstrip("-").isdigit() else 0,
            "conversation": tours,
            "max_audio_length_ms": int(max_audio_length_ms),
        }

        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
                reponse = client.post(f"{url}/generate", json=corps)
        except httpx.HTTPError as erreur:
            return echec(action="parler", cible=self.nom,
                         message=f"Service CSM n'a pas repondu : {erreur}")

        if reponse.status_code == 409:
            detail = reponse.json().get("detail", {})
            return non_configure(
                action="parler", cible=self.nom,
                ce_qui_manque=str(detail.get("message") or detail))
        if reponse.status_code != 200:
            return echec(action="parler", cible=self.nom,
                         message=f"Generation refusee ({reponse.status_code}) : "
                                 f"{reponse.text[:200]}")

        appareil = reponse.headers.get("X-CSM-Device")
        filigrane = reponse.headers.get("X-CSM-Watermarked")
        filigrane_bool = None if filigrane is None else filigrane.lower() == "true"
        if filigrane_bool is False:
            # Regle 3 du module : jamais un fichier sans provenance. Le
            # service DECLARE lui-meme ne pas avoir filigrane — le croire sur
            # parole pour le "oui" mais pas pour le "non" serait incoherent.
            return echec(
                action="parler", cible=self.nom,
                message="Le service CSM declare ne pas avoir filigrane cet audio : "
                        "rien n'est garde sans provenance verifiable.")

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"csm-{uuid.uuid4().hex[:8]}.wav"
        sortie.write_bytes(reponse.content)

        mesures = sonder_le_fichier(sortie)
        if mesures["duree_ms"]:
            return succes(
                action="parler", cible=self.nom,
                message=(f"Voix conversationnelle generee par CSM sur "
                         f"{appareil or 'un appareil non precise'} : "
                         f"{mesures['duree_ms']} ms, {mesures['octets']} octets."),
                preuve=str(sortie), **_tracer(appareil, filigrane_bool), **mesures)

        if mesures["sonde_disponible"] is False and ressemble_a_du_wav(sortie):
            return succes(
                action="parler", cible=self.nom,
                message=(f"Voix generee par CSM : {mesures['octets']} octets. "
                         "Duree non verifiee — ffprobe n'est pas installe sur "
                         "cette machine."),
                preuve=str(sortie), **_tracer(appareil, filigrane_bool), **mesures)

        sortie.unlink(missing_ok=True)
        return echec(
            action="parler", cible=self.nom,
            message="Le service CSM a repondu, mais le fichier n'a aucune duree "
                    "lisible : rien n'a ete garde.",
            **mesures)
