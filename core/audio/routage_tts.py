"""Le routeur de voix d'ARENA : **un seul**, et il connaît les licences.

ARENA ne possède pas de moteur de synthèse. Elle pilote VoiceStudio, qui en
expose une quinzaine (`core/connectors/audio_voix.py`). Choisir lequel parle
était jusqu'ici *« le premier que le service déclare disponible »* — et c'est
le défaut que ce module corrige.

---

## Le défaut mesuré le 07/09/2026

`_REGISTRY` de VoiceStudio (`backend/services/tts_backend.py:2260`, commit
`53ff367`) est un dictionnaire **ordonné** dont la première entrée est
`omnivoice`, et `list_backends()` l'énumère dans cet ordre. ARENA prenait
`disponibles[0]`. Donc, dès que le paquet est installé — ce que
`docs/COMMANDES_PC.md` lui dit lui-même de faire —, **OmniVoice devient le
moteur de toutes les voix off d'UniC Plaquiste**.

Or ses poids pré-entraînés sont **CC-BY-NC** : usage commercial interdit.
Source primaire, lue sur cette machine et pas supposée — `LICENSE-NOTICE.md`
de VoiceStudio :

> *« Downloaded model weights are not relicensed by VoiceStudio. The default
> `k2-fsa/OmniVoice` model card identifies its code as Apache-2.0 and
> pretrained weights as CC-BY-NC. »*

Le dépôt `k2-fsa/OmniVoice` lui-même (commit `08be0b4`) ne porte qu'un
`LICENSE` Apache-2.0, qui couvre le **code**, et **aucune** mention de la
licence des poids. Lire le dépôt seul menait donc exactement à la conclusion
fausse : « Apache-2.0, donc libre pour le commerce ».

UniC Plaquiste est une entreprise. Une voix off sur une vidéo de chantier est
un usage commercial.

---

## Les quatre règles de ce module

1. **Ce que la machine sait mesurer, on le lui demande.** Disponibilité,
   clonage (`supports_cloning`), appareil réel (`effective_device`) et état
   d'accélération (`routing_status`) viennent de `/engines/tts`, à chaque
   appel. Rien de tout cela n'est écrit ici.

2. **Ce qu'aucune API n'expose, et seulement cela, vit dans la table.** La
   licence des poids et le support de `instruct` ne sont exposés par aucun
   point d'entrée de VoiceStudio : ils sont donc écrits ici, chacun avec sa
   source et sa date.

3. **L'usage par défaut est commercial.** Se tromper dans ce sens coûte une
   gêne (il doit déclarer `usage="recherche"` pour entendre OmniVoice) ; se
   tromper dans l'autre lui fait produire des vidéos commerciales avec un
   modèle qui l'interdit, sans que rien ne le lui dise.

4. **`INCONNU` n'est pas une autorisation.** Un moteur dont la licence n'est
   pas vérifiée reste utilisable — sinon ARENA se tairait —, mais il n'est
   jamais préféré à un moteur dont la licence est établie, et le résultat le
   dit.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class Usage(str, Enum):
    """Pour quoi cette voix va servir. Décide quelles licences sont ouvertes."""

    #: Une voix off pour UniC, un devis lu, une vidéo de chantier. Par défaut.
    COMMERCIAL = "commercial"
    #: Essai, démonstration, comparaison de moteurs. Ouvre les poids CC-BY-NC.
    RECHERCHE = "recherche"


class Commercial(str, Enum):
    """Ce que la licence des POIDS permet — jamais celle du code."""

    AUTORISE = "AUTORISE"
    INTERDIT = "INTERDIT"
    INCONNU = "INCONNU"


@dataclass(frozen=True)
class LicenceMoteur:
    """Ce qu'aucune API ne dit : la licence des poids, et qui l'affirme."""

    commercial: Commercial
    licence: str
    #: `instruct` (voice design) est-il honoré ? `None` = dépend du modèle chargé.
    voice_design: Optional[bool]
    source: str
    #: Langues où ce moteur est CONNU bon — mesuré, jamais suppose. `None` =
    #: aucune restriction connue (les moteurs VoiceStudio sont multilingues par
    #: construction et rien ici ne dit le contraire). Un ensemble non vide
    #: RESTREINT : demander une langue absente de cet ensemble exclut le
    #: moteur, meme nomme explicitement (mission Sesame CSM, §5 — « do NOT
    #: claim French or Wolof support simply because audio was generated »).
    langues: Optional[frozenset] = None
    #: Ce moteur est-il specifiquement bon en PAROLE CONVERSATIONNELLE
    #: (prosodie multi-tour, continuite de locuteur) ? Par defaut False : ce
    #: n'est pas une capacite qu'un moteur TTS classique revendique. Sert
    #: uniquement au departage quand l'appelant demande explicitement une
    #: conversation (`conversationnel=True` dans `choisir`) — jamais a exclure
    #: qui que ce soit.
    conversationnel: bool = False


#: Le tableau des moteurs de VoiceStudio, colonne « License » de son `README.md`
#: (commit `53ff367`, lu le 07/09/2026) et `LICENSE-NOTICE.md` pour la famille
#: OmniVoice. La colonne « Instruct » du même tableau donne `voice_design`.
#:
#: **Ce tableau parle des POIDS.** La licence du code (Apache-2.0 pour
#: OmniVoice, AGPL-3.0 pour l'application VoiceStudio) ne gouverne pas l'audio
#: produit ; celle des poids, si. Confondre les deux est précisément l'erreur
#: que ce module existe pour empêcher.
_VS = "VoiceStudio README.md + LICENSE-NOTICE.md, commit 53ff367, lu le 07/09/2026"

LICENCES: Dict[str, LicenceMoteur] = {
    "omnivoice": LicenceMoteur(
        Commercial.INTERDIT, "poids CC-BY-NC (code Apache-2.0)", True, _VS),
    "omnivoice-subprocess": LicenceMoteur(
        Commercial.INTERDIT, "poids CC-BY-NC (code Apache-2.0)", True, _VS),
    "omnivoice-gguf": LicenceMoteur(
        Commercial.INCONNU,
        "quantification derivee de poids CC-BY-NC ; termes du derive non verifies",
        True, _VS),
    "cosyvoice": LicenceMoteur(Commercial.AUTORISE, "Apache-2.0", True, _VS),
    "voxcpm2": LicenceMoteur(Commercial.AUTORISE, "Apache-2.0", True, _VS),
    "moss-tts-nano": LicenceMoteur(Commercial.AUTORISE, "Apache-2.0", False, _VS),
    "moss-tts-v15": LicenceMoteur(Commercial.AUTORISE, "Apache-2.0", False, _VS),
    "dots-tts": LicenceMoteur(Commercial.AUTORISE, "Apache-2.0", False, _VS),
    "confucius4-tts": LicenceMoteur(Commercial.AUTORISE, "Apache-2.0", False, _VS),
    "sherpa-onnx": LicenceMoteur(Commercial.AUTORISE, "Apache-2.0", False, _VS),
    "gpt-sovits": LicenceMoteur(Commercial.AUTORISE, "MIT", False, _VS),
    "kittentts": LicenceMoteur(Commercial.AUTORISE, "MIT", False, _VS),
    "pockettts": LicenceMoteur(
        Commercial.AUTORISE, "CC-BY-4.0 (attribution requise), acces sous condition",
        False, _VS),
    "supertonic3": LicenceMoteur(
        Commercial.AUTORISE, "OpenRAIL-M (restrictions d'usage, pas de commerce)",
        False, _VS),
    "indextts2": LicenceMoteur(
        Commercial.AUTORISE,
        "licence modele Bilibili : libre en dessous de 100 M d'utilisateurs "
        "mensuels et 1 Md RMB de revenus — UniC est tres en dessous",
        False, _VS),
    # `mlx-audio` charge un modele tiers choisi par l'utilisateur : sa licence
    # depend de ce modele, et VoiceStudio l'ecrit « Varies ». INCONNU est donc
    # la mesure exacte, pas une paresse.
    "mlx-audio": LicenceMoteur(
        Commercial.INCONNU, "depend du modele charge (VoiceStudio : « Varies »)",
        None, _VS),
    # Sesame CSM-1B — PAS un moteur de VoiceStudio : un second connecteur
    # (`core/connectors/csm.py`), un service local separe qu'ARENA pilote par
    # HTTP, jamais importe. Code ET poids Apache-2.0 (LICENSE du depot,
    # commit `daed31e`, et `license: apache-2.0` de la fiche modele HF —
    # verifies directement le 10/09/2026, pas supposes du README). Sa FAQ
    # officielle est explicite : « has some capacity for non-English languages
    # due to data contamination [...] but it likely won't do well » — donc
    # `langues` le restreint a l'anglais, mesure jamais suppose ; French/Wolof
    # restent au tableau des moteurs VoiceStudio (DEC-0080).
    "sesame-csm-1b": LicenceMoteur(
        Commercial.AUTORISE, "Apache-2.0 (code et poids)", False,
        "LICENSE de SesameAILabs/csm @ daed31e + fiche HF sesame/csm-1b, "
        "lues le 10/09/2026",
        langues=frozenset({"en"}), conversationnel=True),
}

#: Ce qu'on répond d'un moteur absent du tableau. Un moteur neuf apparu chez
#: VoiceStudio ne doit pas hériter d'une autorisation par défaut.
LICENCE_INCONNUE = LicenceMoteur(
    Commercial.INCONNU, "moteur inconnu du tableau des licences d'ARENA", None,
    "aucune source : ce moteur n'existait pas au 07/09/2026")


def licence_de(identifiant: str) -> LicenceMoteur:
    """La licence connue de ce moteur, ou l'ignorance déclarée comme telle."""
    return LICENCES.get(identifiant, LICENCE_INCONNUE)


@dataclass(frozen=True)
class MoteurTTS:
    """Un moteur tel que VoiceStudio le décrit MAINTENANT, plus sa licence.

    Tout sauf `licence` vient de `/engines/tts` : c'est une photo de la
    machine, pas une croyance d'ARENA.
    """

    identifiant: str
    disponible: bool
    #: `supports_cloning` : `None` quand la capacite depend du modele charge.
    clonage: Optional[bool]
    #: `effective_device` : l'appareil que CE moteur utilise sur CET hote.
    appareil: Optional[str]
    #: `routing_status` : accelerated | cpu_fallback | cpu_only | unavailable.
    routage: Optional[str]
    gpu_compatible: tuple

    @property
    def licence(self) -> LicenceMoteur:
        return licence_de(self.identifiant)

    @property
    def accelere(self) -> bool:
        """Ce moteur tourne-t-il vraiment sur un accélérateur ?

        Mesure de VoiceStudio, pas une déduction : un moteur peut être
        `gpu_compatible` et retomber sur le processeur faute de VRAM — c'est
        exactement ce que `cpu_fallback` signale.
        """
        return self.routage == "accelerated"


def moteurs_depuis(donnees: Dict[str, Any]) -> List[MoteurTTS]:
    """Lit la réponse de `/engines/tts`. Un champ absent reste `None`."""
    moteurs = []
    for entree in donnees.get("backends", []) or []:
        identifiant = entree.get("id")
        if not identifiant:
            continue
        moteurs.append(MoteurTTS(
            identifiant=str(identifiant),
            disponible=bool(entree.get("available")),
            clonage=entree.get("supports_cloning"),
            appareil=entree.get("effective_device"),
            routage=entree.get("routing_status"),
            gpu_compatible=tuple(entree.get("gpu_compat") or ()),
        ))
    return moteurs


class ErreurDeMoteur(RuntimeError):
    """Aucun moteur ne peut faire ce travail, et on dit lesquels existent."""


def _normalise_langue(langue: str) -> str:
    """`fr-FR`, `FR`, `french` -> `fr`. Vide reste vide (aucune restriction)."""
    propre = (langue or "").strip().lower()
    if not propre:
        return ""
    return propre.split("-")[0].split("_")[0]


def _exclusion(moteur: MoteurTTS, usage: Usage, clonage: bool,
               voice_design: bool, langue: str = "") -> Optional[str]:
    """Pourquoi ce moteur ne convient pas — ou `None` s'il convient.

    Un seul endroit décide, pour que le refus d'un moteur nommé donne
    exactement la raison qui l'aurait écarté d'un choix automatique.
    """
    if not moteur.disponible:
        return "non installe dans VoiceStudio"
    if clonage and moteur.clonage is not True:
        return ("ne declare pas le clonage (`supports_cloning`)"
                if moteur.clonage is False
                else "clonage dependant du modele charge : non prouve")
    if voice_design and moteur.licence.voice_design is not True:
        return "n'honore pas `instruct` (voice design)"
    if usage is Usage.COMMERCIAL and moteur.licence.commercial is Commercial.INTERDIT:
        return (f"{moteur.licence.licence} : usage commercial interdit. "
                "Declare un usage non commercial pour l'entendre quand meme.")
    langue_normalisee = _normalise_langue(langue)
    restriction = moteur.licence.langues
    if langue_normalisee and restriction is not None and langue_normalisee not in restriction:
        # Restriction MESUREE, jamais supposee (mission CSM §5) : un moteur
        # dont on sait qu'il est mauvais dans cette langue n'est pas choisi
        # pour elle, meme nomme explicitement — nommer un moteur n'ouvre
        # aucune porte, ici comme pour la licence.
        connues = ", ".join(sorted(restriction))
        return f"non evalue/mauvais en « {langue_normalisee} » (langues connues : {connues})"
    return None


def _rang(moteur: MoteurTTS, conversationnel: bool) -> tuple:
    """L'ordre de préférence. Plus petit est meilleur.

    D'abord la licence — une licence établie passe avant une licence inconnue,
    parce qu'un fichier produit sous une licence non vérifiée est un risque
    qu'on ne rattrape plus. Puis, SEULEMENT si l'appelant demande explicitement
    une parole conversationnelle, un moteur qui revendique cette force précise
    (mission Sesame CSM §3/§4) — jamais par defaut, pour ne pas le faire
    concourir avec Qwen/Vision/Video sur la meme carte pour un travail ou il
    n'apporte rien. Enfin l'accélération, seule mesure de latence qu'ARENA
    obtienne sans faire parler le moteur pour voir.
    """
    return (0 if moteur.licence.commercial is Commercial.AUTORISE else 1,
            0 if (conversationnel and moteur.licence.conversationnel) else 1,
            0 if moteur.accelere else 1)


def choisir(moteurs: Sequence[MoteurTTS], *, usage: Usage = Usage.COMMERCIAL,
            clonage: bool = False, voice_design: bool = False,
            langue: str = "", conversationnel: bool = False,
            demande: str = "") -> MoteurTTS:
    """Le moteur qui parlera. **Le seul endroit où ce choix se fait.**

    Args:
        moteurs: ce que `/engines/tts` (VoiceStudio) et/ou le connecteur CSM
            viennent de répondre — cette fonction est agnostique de la source,
            elle ne lit qu'une liste de `MoteurTTS`.
        usage: commercial par défaut — voir la règle 3 de ce module.
        clonage: le travail exige de cloner une voix.
        voice_design: le travail exige `instruct` (genre, âge, accent…).
        langue: langue du texte a dire (ex. "fr", "en", "wo"). Vide = aucune
            restriction verifiee. Un moteur dont les langues connues sont
            mesurees et n'incluent pas celle-ci est ecarte (mission CSM §5).
        conversationnel: le travail est une parole CONVERSATIONNELLE (dialogue
            multi-tour), pas une simple lecture. Fait departager en faveur
            d'un moteur qui revendique cette force — jamais une exclusion.
        demande: un moteur nommé par l'appelant. Il est vérifié comme les
            autres : nommer un moteur n'ouvre aucune porte.

    Raises:
        ErreurDeMoteur: aucun moteur ne convient, avec pour chaque écarté la
            raison exacte.
    """
    if demande:
        for moteur in moteurs:
            if moteur.identifiant == demande:
                raison = _exclusion(moteur, usage, clonage, voice_design, langue)
                if raison is None:
                    return moteur
                raise ErreurDeMoteur(
                    f"le moteur « {demande} » ne convient pas : {raison}")
        connus = ", ".join(m.identifiant for m in moteurs) or "aucun"
        raise ErreurDeMoteur(
            f"le moteur « {demande} » n'existe pas ici. Connus : {connus}.")

    retenus = [m for m in moteurs
               if _exclusion(m, usage, clonage, voice_design, langue) is None]
    if retenus:
        return min(retenus, key=lambda m: _rang(m, conversationnel))

    raise ErreurDeMoteur(
        _pourquoi_personne(moteurs, usage, clonage, voice_design, langue))


def _pourquoi_personne(moteurs: Sequence[MoteurTTS], usage: Usage,
                       clonage: bool, voice_design: bool,
                       langue: str = "") -> str:
    """Le message d'un refus. Il doit lui dire quoi faire, pas seulement non."""
    travail = ("cloner une voix" if clonage
               else "concevoir une voix (`instruct`)" if voice_design
               else "parler")
    if not moteurs:
        return (f"aucun moteur de voix installe dans VoiceStudio : rien ne peut "
                f"{travail}.")

    ecartes = []
    licence_bloque = False
    for moteur in moteurs:
        raison = _exclusion(moteur, usage, clonage, voice_design, langue)
        ecartes.append(f"{moteur.identifiant} ({raison})")
        if (usage is Usage.COMMERCIAL
                and moteur.licence.commercial is Commercial.INTERDIT):
            licence_bloque = True

    message = (f"aucun moteur disponible ne peut {travail} pour un usage "
               f"{usage.value}. Ecartes : {' ; '.join(ecartes)}.")
    if licence_bloque:
        permissifs = ", ".join(sorted(
            identifiant for identifiant, licence in LICENCES.items()
            if licence.commercial is Commercial.AUTORISE))
        message += (" Installe dans VoiceStudio un moteur a licence permissive "
                    f"({permissifs}), ou declare explicitement un usage non "
                    "commercial si c'est le cas de ce travail.")
    return message
