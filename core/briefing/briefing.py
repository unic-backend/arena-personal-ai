"""Le briefing du matin : ce que le proprietaire doit savoir en se levant.

Demande du 29/09/2026 (etape 4 du chantier JARVIS, DEC-0166) : « chaque matin,
ARENA te resume seul : meteo, courrier, actualites, agenda ».

Ce module ne cherche rien lui-meme. Il **assemble** des rubriques fournies par
les capacites deja branchees (agenda, agent courrier, recherche web) et fixe
les deux regles qui font qu'un briefing est digne de confiance :

1. **Chaque rubrique dit son etat.** `OK` (la source a repondu),
   `NON_CONFIGURE` (rien n'est branche : l'agenda sans identifiants Google),
   `INDISPONIBLE` (branche, mais en echec ou muet), `INCONNU` (il manque une
   donnee pour chercher : la ville pour la meteo). Jamais une rubrique vide
   presentee comme « rien aujourd'hui » : un agenda non branche ne se lit pas
   « journee libre ».
2. **Une rubrique lente ou en panne ne retient pas les autres.** Toutes
   partent en meme temps, chacune avec son delai ; celle qui depasse est
   rapportee `INDISPONIBLE`, les autres arrivent.
"""
import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Dict, List, Mapping

from core.actions.resultat import ResultatAction, Statut

logger = logging.getLogger("usman.briefing")

OK = "OK"
NON_CONFIGURE = "NON_CONFIGURE"
INDISPONIBLE = "INDISPONIBLE"
INCONNU = "INCONNU"

#: Ce qu'une rubrique non OK affiche a cote de son titre.
LIBELLES_D_ETAT = {
    NON_CONFIGURE: "non configure",
    INDISPONIBLE: "indisponible",
    INCONNU: "information manquante",
}

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
        "septembre", "octobre", "novembre", "decembre")

#: Delai par rubrique. Une recherche web en compte deux ou trois passes.
DELAI_PAR_RUBRIQUE = 90.0


@dataclass
class Rubrique:
    titre: str
    etat: str
    texte: str

    def en_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Briefing:
    jour: date
    compose_a: datetime
    rubriques: List[Rubrique] = field(default_factory=list)

    def en_texte(self) -> str:
        """Le briefing tel qu'il s'affiche et se lit a voix haute."""
        lignes = [f"**Briefing du {jour_en_toutes_lettres(self.jour)}**"]
        for rubrique in self.rubriques:
            etat = LIBELLES_D_ETAT.get(rubrique.etat)
            entete = f"**{rubrique.titre}**" + (f" _({etat})_" if etat else "")
            lignes += ["", entete, rubrique.texte.strip()]
        return "\n".join(lignes)

    def en_dict(self) -> Dict[str, Any]:
        return {
            "jour": self.jour.isoformat(),
            "compose_a": self.compose_a.isoformat(timespec="minutes"),
            "rubriques": [r.en_dict() for r in self.rubriques],
        }


def jour_en_toutes_lettres(jour: date) -> str:
    """« lundi 29 septembre » — sans locale systeme, qui varie d'un PC a l'autre."""
    return f"{JOURS[jour.weekday()]} {jour.day} {MOIS[jour.month - 1]}"


# --- Des sources aux rubriques ----------------------------------------------------

def rubrique_agenda(resultat: ResultatAction) -> Rubrique:
    """La lecture de l'agenda du jour. Une liste vide n'est « rien de prevu »
    que si la lecture a REUSSI ; sinon elle dit pourquoi elle n'a pas lu."""
    titre = "Agenda"
    if resultat.statut == Statut.NON_CONFIGURE:
        return Rubrique(titre, NON_CONFIGURE, resultat.message)
    if resultat.statut != Statut.SUCCES:
        return Rubrique(titre, INDISPONIBLE, resultat.message)
    rendez_vous = resultat.detail.get("donnees") or []
    lignes = [
        f"- {_heure(r.get('debut'))}–{_heure(r.get('fin'))} {r.get('titre') or 'sans titre'}"
        for r in rendez_vous
    ]
    texte = "\n".join(lignes) if lignes else "Aucun rendez-vous aujourd'hui."
    illisibles = resultat.detail.get("illisibles") or 0
    if illisibles:
        texte += f"\n({illisibles} rendez-vous illisible(s), non comptes.)"
    return Rubrique(titre, OK, texte)


def _heure(horodatage: Any) -> str:
    try:
        return datetime.fromisoformat(str(horodatage)).strftime("%H:%M")
    except ValueError:
        return "?"


def rubrique_d_agent(titre: str, reponse: Mapping[str, Any]) -> Rubrique:
    """La reponse d'un agent (courrier, recherche web), telle quelle — avec
    ses propres avertissements de verification, jamais reecrite."""
    texte = str(reponse.get("response") or "").strip()
    if reponse.get("status") == "success" and texte:
        return Rubrique(titre, OK, texte)
    return Rubrique(titre, INDISPONIBLE, texte or "Pas de reponse.")


# --- L'assemblage -----------------------------------------------------------------

Source = Callable[[], Awaitable[Rubrique]]


async def _une_rubrique(titre: str, source: Source, delai: float) -> Rubrique:
    try:
        return await asyncio.wait_for(source(), timeout=delai)
    except asyncio.TimeoutError:
        return Rubrique(titre, INDISPONIBLE, f"Pas de reponse en {delai:.0f} s.")
    except Exception as erreur:  # noqa: BLE001 — une rubrique en panne n'emporte pas le briefing
        logger.warning("Rubrique %s en echec : %s", titre, erreur)
        return Rubrique(titre, INDISPONIBLE, f"En echec : {erreur}")


async def composer_briefing(
    sources: Mapping[str, Source],
    maintenant: datetime,
    delai: float = DELAI_PAR_RUBRIQUE,
) -> Briefing:
    """Toutes les rubriques en meme temps, dans l'ordre de `sources`."""
    titres = list(sources)
    rubriques = await asyncio.gather(
        *(_une_rubrique(titre, sources[titre], delai) for titre in titres))
    return Briefing(jour=maintenant.date(), compose_a=maintenant, rubriques=list(rubriques))
