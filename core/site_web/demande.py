"""« Mon site est en ligne ? » : la phrase qui parle de SES sites, et la
capacite Netlify qu'elle demande (DEC-0182).

Meme discipline que la conversion (DEC-0177) et l'architecture 3D
(DEC-0070) : aucun agent, aucun modele. La phrase devient une capacite du
connecteur `netlify`, qui applique permissions, confirmation et journal.

Deux conditions, toutes deux necessaires :

1. **une reference a SON site** (« mon site », « mes sites », « netlify »,
   « unicplaquiste.com ») — « le site de la mairie » n'est pas le sien ;
2. **aucune demande de fabrication** : « cree-moi un site », « ameliore le
   design de mon site » sont du code ou du design, que ce connecteur ne fait
   pas. Elles partent ailleurs.

Ensuite, la premiere capacite dont un mot apparait gagne, dans l'ordre de
`CAPACITES` : republier avant tout (c'est la seule qui ecrit, et « remets en
ligne » contient « en ligne »), puis les messages, les deploiements, la liste
des sites, l'etat du site.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional

REFERENCES_AU_SITE = (
    "mon site", "mes sites", "notre site", "nos sites", "netlify",
    "unicplaquiste.com",
)

#: Ce qui demande de FABRIQUER ou de changer le site : pas ce connecteur.
FABRICATION = (
    "cree", "creer", "cree-moi", "fais-moi un site", "fais moi un site",
    "construis", "construire", "design", "maquette", "ameliore", "ameliorer",
    "refais", "refaire", "modifie", "modifier", "ajoute", "ajouter",
    "code ", "code-", "coder", "developpe",
)

#: Capacite -> les mots qui la demandent. L'ordre compte. Un tuple exige TOUS
#: ses mots : « remets mon site en ligne » separe le verbe de « en ligne ».
CAPACITES = (
    ("redeployer", ("republie", "republier", "redeploie", "redeployer",
                    ("remets", "en ligne"), ("remettre", "en ligne"),
                    "relance le deploiement", "relance le build", "reconstruis")),
    ("soumissions", ("formulaire", "formulaires", "message", "messages",
                     "demande de devis", "demandes de devis", "contacts",
                     "prospects", "leads")),
    ("deploiements", ("deploiement", "deploiements", "build", "builds",
                      "mise en ligne", "mises en ligne")),
    ("sites", ("mes sites", "nos sites", "quels sites", "liste")),
    ("site_infos", ("etat", "en ligne", "marche", "fonctionne", "infos",
                    "informations", "statut", "adresse")),
)

#: Ce qu'un visiteur envoie avec son message, et qui ne sert pas a le lire.
CHAMPS_TECHNIQUES = ("ip", "user_agent", "referrer")


def _normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return " ".join(sans_accents.lower().replace("’", "'").split()) + " "


def capacite_du_site(phrase: str) -> Optional[str]:
    """La capacite `netlify` que la phrase demande, ou None si elle ne parle
    pas de ses sites — ou demande de les fabriquer."""
    texte = _normaliser(phrase)
    if not any(reference in texte for reference in REFERENCES_AU_SITE):
        return None
    if any(mot in texte for mot in FABRICATION):
        return None
    for capacite, mots in CAPACITES:
        if any(_present(mot, texte) for mot in mots):
            return capacite
    return None


def _present(mot: Any, texte: str) -> bool:
    if isinstance(mot, tuple):
        return all(partie in texte for partie in mot)
    return mot in texte


def rendre(capacite: str, message: str, donnees: Any) -> str:
    """Le message du connecteur, puis ce qu'il a lu — liste, jamais resume.

    Rien n'est reformule ni deduit : un champ absent s'affiche « ? ».
    """
    lignes: List[str] = [message]
    if capacite == "sites":
        for site in donnees or []:
            lignes.append(f"- {site.get('name') or '?'} — {site.get('ssl_url') or site.get('url') or '?'}"
                          f" (identifiant {site.get('id') or '?'})")
    elif capacite == "site_infos" and isinstance(donnees, dict):
        lignes.append(f"Adresse : {donnees.get('ssl_url') or donnees.get('url') or '?'}")
        lignes.append(f"Derniere publication : {donnees.get('derniere_publication') or '?'}")
    elif capacite == "deploiements":
        for deploiement in donnees or []:
            ligne = (f"- {deploiement.get('state') or '?'} · {deploiement.get('created_at') or '?'}"
                     f" · {deploiement.get('branch') or '?'}")
            if deploiement.get("error_message"):
                ligne += f" — erreur : {deploiement['error_message']}"
            lignes.append(ligne)
    elif capacite == "soumissions":
        for soumission in donnees or []:
            lignes.append(_soumission(soumission))
    return "\n".join(lignes)


def _soumission(soumission: Dict[str, Any]) -> str:
    champs = soumission.get("data") or {}
    contenu = "; ".join(f"{cle} : {valeur}" for cle, valeur in champs.items()
                        if cle not in CHAMPS_TECHNIQUES)
    return (f"- {soumission.get('form_name') or '?'}, {soumission.get('created_at') or '?'} — "
            f"{contenu or '(vide)'}")
