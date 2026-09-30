"""« Mon Internet est lent, vérifie » : la phrase qui parle de SA connexion,
et ce qu'elle demande vraiment (DEC-0203).

Même discipline que ses sites (DEC-0182) et sa fiche Google (DEC-0184) :
aucun agent, aucun modèle. La phrase devient l'une des deux capacités que
DEC-0202 a ouvertes — et rien d'autre :

- **`etat`** : lire la santé réseau déjà connue par l'adaptateur
  (`core/reseau/sante_reseau.py`) — Netronome quand il répond, sonde native
  sinon. Bon marché, ne lance aucun test.
- **`mesurer_debit`** : un vrai test de débit. Coûteux — il occupe la ligne —
  donc il passe TOUJOURS par la confirmation du connecteur
  (`network.measure` → CONFIRMATION dans `config/permissions_services.yaml`).
  Une détection trop large ici ne coûte donc jamais un test : elle coûte une
  question de confirmation.

Deux conditions pour reconnaître la demande, toutes deux nécessaires :

1. **une référence à SA connexion** (« internet », « ma connexion », « le
   wifi », « le débit »…) — ses réseaux SOCIAUX (« publie sur mes réseaux »,
   « ma connexion TikTok ») ne sont pas son réseau ;
2. **un signe de diagnostic ou de mesure** (« lent », « vérifie », « test de
   débit »…) — « c'est quoi Internet ? » reste une conversation.

Le rendu (`rendre_sante`) sépare strictement **ce qui est mesuré** de **ce qui
ne l'est pas** : un champ `None` s'affiche « non mesuré », jamais `0`, et
aucune phrase ne juge la connexion (« ton Internet est mauvais ») — le texte
rapporte les mesures, leur source, et ce qu'il faudrait brancher pour en
avoir davantage.
"""
from __future__ import annotations

import unicodedata
from typing import Any, List, Optional, Tuple

from core.reseau.sante_reseau import SanteReseau, StatutReseau

#: Ce qui désigne SA connexion. « réseau » nu n'y est pas : trop proche de ses
#: réseaux sociaux — il n'entre que précédé d'un article ou d'un possessif, et
#: les exclusions ci-dessous gardent la porte.
REFERENCES_A_SA_CONNEXION = (
    "internet", "ma connexion", "la connexion", "de connexion",
    "mon reseau", "le reseau", "du reseau", "reseau local",
    "wifi", "wi-fi", "le debit", "mon debit", "bande passante",
    "la latence", "le ping", "mon ping",
    # Un test de debit nomme est sa connexion, meme sans la nommer :
    # « fais un speedtest », « lance un test de debit ».
    "speedtest", "speed test", "test de debit", "test de vitesse",
)

#: Ce qui parle d'autre chose que de SA connexion : ses réseaux sociaux, un
#: compte à connecter, un réseau qui n'est pas informatique. Une seule de ces
#: locutions et la phrase part ailleurs.
PAS_SA_CONNEXION = (
    "reseau social", "reseaux sociaux", "mes reseaux", "tes reseaux",
    "tiktok", "linkedin", "instagram", "facebook", "youtube", "whatsapp",
    "twitter", "snapchat", "compte", "electri", "reseau de chantier",
    # Une CONNEXION a un service n'est pas SA ligne : page de connexion,
    # identifiants — c'est du code, du design ou un souci d'acces.
    "page de connexion", "ecran de connexion", "interface de connexion",
    "formulaire de connexion", "mot de passe", "identifiant",
)

#: Ce qui demande explicitement un VRAI test de débit — la capacité coûteuse.
#: Un tuple exige TOUS ses mots (« mesure … débit » sépare le verbe du nom).
DEMANDE_DE_MESURE = (
    "speedtest", "speed test", "test de debit", "test de vitesse",
    "test de bande passante", "teste le debit", "teste mon debit",
    ("mesure", "debit"), ("mesurer", "debit"), ("mesure", "bande passante"),
    ("lance", "test", "debit"), ("lance", "test", "vitesse"),
    ("vitesse", "connexion"), ("vitesse", "internet"), ("rapide", "internet"),
    ("rapide", "connexion"),
)

#: Ce qui demande un DIAGNOSTIC — la lecture bon marché. Des plaintes
#: (« lent », « rame », « coupe ») et des verbes de vérification.
SIGNES_DE_DIAGNOSTIC = (
    "lent", "lente", "rame", "coupe", "instable", "saccade",
    "verifie", "verifier", "diagnostic", "diagnostique", "controle",
    "marche", "fonctionne", "probleme", "panne", "en panne",
    "etat", "sante", "teste", "tester", "check", "ca va",
)


def _normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return " ".join(sans_accents.lower().replace("’", "'").split()) + " "


def _present(mot: Any, texte: str) -> bool:
    if isinstance(mot, tuple):
        return all(partie in texte for partie in mot)
    return mot in texte


def capacite_reseau(phrase: str) -> Optional[str]:
    """La capacité réseau que la phrase demande, ou None si elle ne parle pas
    de sa connexion — ou parle de ses réseaux sociaux.

    Returns:
        `"mesurer_debit"` pour un test de débit explicite (il passera par la
        confirmation), `"etat"` pour un diagnostic en lecture, `None` sinon.
    """
    texte = _normaliser(phrase)
    if any(mot in texte for mot in PAS_SA_CONNEXION):
        return None
    if not any(reference in texte for reference in REFERENCES_A_SA_CONNEXION):
        return None
    if any(_present(mot, texte) for mot in DEMANDE_DE_MESURE):
        return "mesurer_debit"
    if any(_present(mot, texte) for mot in SIGNES_DE_DIAGNOSTIC):
        return "etat"
    return None


#: Champ du schéma -> (étiquette lisible, unité). L'ordre est celui du rendu.
_MESURES_AFFICHEES: Tuple[Tuple[str, str, str], ...] = (
    ("download", "Débit descendant", "Mbps"),
    ("upload", "Débit montant", "Mbps"),
    ("latency", "Latence", "ms"),
    ("jitter", "Gigue", "ms"),
    ("packet_loss", "Perte de paquets", "%"),
    ("dns_latency", "Latence DNS", "ms"),
)

_SOURCES = {
    "netronome": "Netronome (service local, mesure réelle)",
    "natif": "sonde native ARENA (connectivité TCP + DNS, sans Netronome)",
}


def rendre_sante(sante: SanteReseau) -> str:
    """Le diagnostic en texte : la mesure d'abord, jamais un jugement.

    Trois blocs, strictement séparés :

    1. ce que la source a dit d'elle-même (`message`, source, statut) ;
    2. **Mesuré** : les seuls champs réellement portés, avec leur unité ;
    3. **Non mesuré** : ce qui reste inconnu — inconnu, pas zéro — et, quand
       c'est le débit, ce qu'il faudrait brancher pour l'obtenir.

    Rien ici ne conclut « ta connexion est bonne/mauvaise » : le texte rend
    les mesures, le propriétaire et le modèle raisonnent dessus.
    """
    lignes: List[str] = [sante.message]
    lignes.append(f"Source : {_SOURCES.get(sante.source, sante.source)} — "
                  f"statut {sante.statut.value}.")
    if sante.erreur:
        lignes.append(f"Cause : {sante.erreur}")

    mesures = sante.mesures or {}
    mesurees: List[str] = []
    absentes: List[str] = []
    for champ, etiquette, unite in _MESURES_AFFICHEES:
        valeur = mesures.get(champ)
        if valeur is None:
            absentes.append(etiquette.lower())
        else:
            mesurees.append(f"- {etiquette} : {valeur} {unite}")
    if mesures.get("dns_status") is not None:
        mesurees.append(f"- Résolution DNS : {mesures['dns_status']}")
    if mesures.get("server"):
        mesurees.append(f"- Serveur de test : {mesures['server']}")
    if mesures.get("provider"):
        mesurees.append(f"- Fournisseur de la mesure : {mesures['provider']}")
    if mesures.get("timestamp"):
        mesurees.append(f"- Mesure datée de : {mesures['timestamp']}")

    lignes.append("")
    if mesurees:
        lignes.append("Mesuré :")
        lignes.extend(mesurees)
    else:
        lignes.append("Mesuré : rien — aucune mesure exploitable.")
    if absentes:
        lignes.append(f"Non mesuré : {', '.join(absentes)}.")

    if mesures.get("download") is None and sante.statut is not StatutReseau.NON_CONFIGURE:
        lignes.append("")
        lignes.append(
            "Le débit n'a pas été mesuré : seul Netronome sait le prendre. "
            "S'il tourne, demande « lance un test de débit » — le test occupe "
            "la ligne et partira après ta confirmation.")
    return "\n".join(lignes)
