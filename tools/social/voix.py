"""Sa voix : apprise, gardee, jamais inventee.

`voice-builder` (source : `charlie947/social-media-skills`, MIT) fabrique deux
fichiers, `about-me.md` et `voice.md`, en interrogeant l'auteur. Ici, ces
reponses ne deviennent pas des fichiers : elles deviennent des **souvenirs**,
dans la memoire personnelle qu'ARENA a deja (`core/memory/personnelle.py`).

C'est ce qui change tout : un fichier se refait a chaque session, un souvenir
dure — et quand le proprietaire corrige (« je n'ecris jamais comme ca »), la
correction entre au meme endroit et pese plus lourd que le reste.

**Quatre regles :**

1. **Sa voix ne s'invente pas.** Une section absente reste absente ; l'agent
   demande au lieu de supposer un ton. Un texte ecrit dans une voix inventee
   part sous son nom.

2. **Une correction pese plus qu'une reponse d'interview.** Ce qu'il rectifie
   apres coup est ce qu'il pense vraiment.

3. **Rien n'est efface.** Une voix qui change garde ses etats precedents : c'est
   la memoire personnelle qui le garantit, pas ce module.

4. **La source voyage.** Chaque element de voix porte d'ou il vient — une
   interview, une correction, une publication approuvee.
"""
import logging
from typing import Any, Dict, List, Optional

from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir

logger = logging.getLogger("usman.social.voix")

#: Le projet sous lequel vivent les souvenirs de voix. Les isoler evite qu'une
#: recherche sur un chantier ramene son style d'ecriture.
PROJET = "voix"

#: Les sections, reprises de `about-me.md` et `voice.md` de la source. L'ordre
#: est celui dans lequel elles seront montrees au modele.
SECTIONS: Dict[str, str] = {
    "qui": "Qui je suis et ce que je fais",
    "audience": "Pour qui j'ecris",
    "piliers": "Les 3 a 5 sujets sur lesquels je veux etre connu",
    "point_de_vue": "Ce que je crois et que les autres ne croient pas",
    "promesse": "Ce que je veux qu'on pense en voyant mon nom",
    "interdits": "Ce dont je refuse de parler",
    "ton": "Mon ton",
    "rythme": "Mon rythme de phrase",
    "ouvertures": "Comment j'ouvre",
    "clotures": "Comment je termine",
    "expressions": "Mes expressions",
    "jamais": "Ce que ma voix ne fait jamais",
}

#: Les sections sans lesquelles on n'ecrit pas en son nom. Les autres affinent ;
#: celles-ci decident.
ESSENTIELLES = ("qui", "audience", "piliers", "ton")

#: Une correction pese plus qu'une reponse d'interview : c'est ce qu'il pense
#: vraiment, dit apres avoir vu le resultat.
IMPORTANCE_INTERVIEW = 0.6
IMPORTANCE_CORRECTION = 0.9


def apprendre(memoire: MemoirePersonnelle, section: str, contenu: str,
              source: str = "interview") -> Optional[str]:
    """Retient un element de voix. Rend l'identifiant du souvenir, ou `None`.

    Une section inconnue est refusee plutot que rangee n'importe ou : elle ne
    serait jamais relue.
    """
    if section not in SECTIONS or not (contenu or "").strip():
        logger.info("Element de voix refuse : section=%r, contenu vide=%s",
                    section, not (contenu or "").strip())
        return None
    souvenir = memoire.retenir(
        contenu=f"[{section}] {contenu.strip()}",
        type=TypeSouvenir.SEMANTIQUE,
        # Une voix est une PREFERENCE : ce n'est pas un fait du monde, c'est
        # le sien. La distinction est celle de la memoire personnelle.
        nature=Nature.PREFERENCE,
        source=source,
        projet=PROJET,
        importance=IMPORTANCE_CORRECTION if source == "correction"
        else IMPORTANCE_INTERVIEW,
    )
    return souvenir.identifiant


def corriger(memoire: MemoirePersonnelle, correction: str,
             section: str = "jamais") -> Optional[str]:
    """Retient une correction du proprietaire. Elle pese plus que le reste.

    « Je n'ecris jamais comme ca » est l'information la plus utile qu'il puisse
    donner : elle vient apres avoir vu un resultat.
    """
    return apprendre(memoire, section, correction, source="correction")


def lire(memoire: MemoirePersonnelle, limite: int = 100) -> Dict[str, List[str]]:
    """Sa voix, section par section, du plus important au moins.

    Rend un dictionnaire des seules sections **renseignees**. Une section
    absente reste absente : c'est ce qui permet a l'agent de demander.
    """
    souvenirs = memoire.souvenirs(projet=PROJET, limite=limite)
    voix: Dict[str, List[str]] = {}
    for souvenir in sorted(souvenirs, key=lambda s: s.importance, reverse=True):
        contenu = souvenir.contenu
        if not contenu.startswith("["):
            continue
        fin = contenu.find("]")
        section = contenu[1:fin]
        if section in SECTIONS:
            voix.setdefault(section, []).append(contenu[fin + 1:].strip())
    return voix


def manquantes(voix: Dict[str, List[str]]) -> List[str]:
    """Les sections essentielles absentes. Vide = on peut ecrire en son nom."""
    return [section for section in ESSENTIELLES if not voix.get(section)]


def formater(voix: Dict[str, List[str]]) -> str:
    """Le bloc a poser dans l'instruction du modele.

    Vide quand rien n'est connu : mieux vaut une instruction sans voix qu'une
    instruction avec une voix inventee.
    """
    if not voix:
        return ""
    lignes = ["SA VOIX, telle qu'il l'a dite lui-meme. Ecris avec, pas a cote :"]
    for section, titre in SECTIONS.items():
        elements = voix.get(section)
        if not elements:
            continue
        lignes.append(f"- {titre} : " + " ; ".join(elements))
    lignes.append("N'invente aucun trait de voix qui ne soit pas ecrit ci-dessus.")
    return "\n".join(lignes)


def resume(voix: Dict[str, List[str]]) -> Dict[str, Any]:
    """Ce que l'interface peut montrer : ce qui est su, ce qui manque."""
    return {
        "sections_connues": sorted(voix),
        "sections_manquantes": manquantes(voix),
        "elements": sum(len(v) for v in voix.values()),
        "prete": not manquantes(voix),
    }
