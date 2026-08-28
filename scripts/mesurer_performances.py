"""Chronometre les sept scenes de la specification, sur cette machine.

    python scripts/mesurer_performances.py

Sept scenes : premier jeton, question simple, question normale, question
complexe, recuperation, recherche web, outil. Chacune est chronometree pour de
vrai ou rapportee `UNKNOWN` avec sa raison — jamais remplacee par un chiffre
plausible.

Ce que la commande ne fait pas : elle n'installe rien, ne configure rien et ne
retente rien. Si Ollama est arrete, quatre lignes sortiront `UNKNOWN`, et c'est
le resultat correct.

Ruling : la scene « recuperation » mesure la recuperation **lexicale**, celle
qui tourne aujourd'hui dans le chemin de reponse. La recuperation semantique
existe (phase 6.3) mais n'est branchee nulle part : la chronometrer donnerait
un chiffre sur une voie que personne n'emprunte.
"""
import asyncio
import logging
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from agents.plaquiste.plaquiste_agent import charger_metier  # noqa: E402
from apps.backend.config import MODELE_PROFOND, MODELE_RAPIDE, OLLAMA_URL  # noqa: E402
from core.execution.mesures import Rapport, chronometrer  # noqa: E402
from core.execution.voies import Voie  # noqa: E402
from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir  # noqa: E402
from core.memory.recuperation import recuperer  # noqa: E402
from core.models.ollama_provider import OllamaProvider  # noqa: E402

QUESTION_SIMPLE = "Bonjour, comment vas-tu ?"
QUESTION_NORMALE = (
    "Explique en trois phrases la difference entre une cloison et un doublage."
)
QUESTION_COMPLEXE = (
    "Un chantier compte 18 parois de 5,40 m par 2,50 m, fermees des deux cotes. "
    "Detaille le raisonnement qui mene au nombre de plaques necessaires, puis "
    "verifie ton propre calcul."
)

#: Assez de souvenirs pour que la recuperation ait quelque chose a trier.
SOUVENIRS_DE_MESURE = 200


def memoire_de_mesure(dossier: str) -> MemoirePersonnelle:
    """Une memoire jetable, remplie hors du chronometre."""
    memoire = MemoirePersonnelle(db_path=str(Path(dossier) / "mesures.db"))
    for numero in range(SOUVENIRS_DE_MESURE):
        memoire.retenir(
            contenu=f"Chantier numero {numero} : {40 + numero} m2 de BA13 poses a Medina.",
            type=TypeSouvenir.EPISODIQUE, nature=Nature.FAIT,
            source="mesure de performance", projet=f"chantier-{numero % 7}",
            importance=0.5,
        )
    return memoire


async def premier_jeton(fournisseur: OllamaProvider) -> None:
    """S'arrete au tout premier morceau recu : c'est la latence percue."""
    async for morceau in fournisseur.generate_stream(prompt=QUESTION_SIMPLE):
        if morceau:
            return
    raise RuntimeError("aucun jeton recu")


def recherche_web() -> None:
    from tools.search.web_search_tool import WebSearchTool

    resultats = WebSearchTool().search("prix du ciment a Dakar", max_results=3)
    if not resultats:
        raise RuntimeError("recherche sans resultat : rien a chronometrer d'utile")


async def campagne() -> Rapport:
    rapide = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_RAPIDE)
    profond = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_PROFOND)
    metier = charger_metier()
    rapport = Rapport()

    with tempfile.TemporaryDirectory() as dossier:
        memoire = memoire_de_mesure(dossier)

        rapport.ajouter(await chronometrer(
            "premier jeton", Voie.LEGERE, lambda: premier_jeton(rapide)))
        rapport.ajouter(await chronometrer(
            "question simple", Voie.LEGERE, lambda: rapide.generate(prompt=QUESTION_SIMPLE)))
        rapport.ajouter(await chronometrer(
            "question normale", Voie.LEGERE, lambda: rapide.generate(prompt=QUESTION_NORMALE)))
        rapport.ajouter(await chronometrer(
            "question complexe", Voie.PROFONDE,
            lambda: profond.generate(prompt=QUESTION_COMPLEXE)))
        rapport.ajouter(await chronometrer(
            "recuperation", Voie.LEGERE,
            lambda: recuperer(memoire, "combien de m2 de BA13 a Medina"),
            repetitions=5))
        rapport.ajouter(await chronometrer(
            "recherche web", Voie.RECHERCHE, recherche_web))

        from agents.plaquiste.calcul_materiaux import quantites_pour
        rapport.ajouter(await chronometrer(
            "outil (calcul materiaux)", Voie.LEGERE,
            lambda: quantites_pour(486.0, metier, parois=18, deja_developpee=True),
            repetitions=5))

    return rapport


def principal() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    print(f"Ollama : {OLLAMA_URL}")
    print(f"Modele rapide : {MODELE_RAPIDE} · modele profond : {MODELE_PROFOND}")
    print()

    rapport = asyncio.run(campagne())
    print(rapport.rendre())
    print()

    if rapport.manquantes:
        print("Les lignes UNKNOWN ne sont pas des echecs de la mesure : elles disent")
        print("ce que cette machine ne peut pas faire en l'etat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
