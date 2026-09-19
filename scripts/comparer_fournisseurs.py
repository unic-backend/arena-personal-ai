"""Comparer Ollama, Groq et DeepInfra sur les memes phrases. Mesure, pas promesse.

    python scripts/comparer_fournisseurs.py

Ce script existe a cause du point 24 de la mission : **« Do not claim 5x faster
unless measured. »** Tant qu'il n'a pas tourne, ARENA n'annonce aucun chiffre de
vitesse, et ce depot n'en ecrit aucun.

**Quatre regles :**

1. **Les memes phrases pour tous.** Comparer deux fournisseurs sur deux prompts
   differents ne compare rien.
2. **Un fournisseur absent se rapporte ABSENT.** Pas lent, pas mauvais : absent.
   Une colonne vide est une information, une colonne inventee est un mensonge.
3. **On mesure ce qu'il ressent** : le temps jusqu'au PREMIER MOT d'abord. Une
   reponse qui arrive en 8 s mais commence a 0,3 s se lit mieux qu'une reponse
   qui arrive d'un bloc a 4 s.
4. **Aucune phrase du proprietaire n'est utilisee.** Les prompts sont neutres et
   ecrits ici : un banc d'essai n'est pas un endroit ou passe sa vie privee.
"""
import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#: Trois scenes, du plus court au plus long. Neutres exprès.
SCENES = (
    ("courte", "Reponds en une phrase : qu'est-ce qu'une cloison ?"),
    ("normale", "Explique en trois phrases comment on pose une plaque de platre."),
    ("longue", "Redige un paragraphe de dix lignes sur l'isolation thermique."),
)

ABSENT = "ABSENT"
ECHEC = "ECHEC"


async def mesurer_un(fournisseur: Any, prompt: str) -> Dict[str, Any]:
    """Chronometre une generation en flux. Rend l'etat, jamais une estimation."""
    debut = time.perf_counter()
    premier: Optional[float] = None
    morceaux = 0
    try:
        async for _ in fournisseur.generate_stream(prompt):
            if premier is None:
                premier = time.perf_counter()
            morceaux += 1
    except Exception as erreur:  # noqa: BLE001 — un echec est un resultat
        return {"etat": ECHEC, "detail": type(erreur).__name__}
    fin = time.perf_counter()
    return {
        "etat": "MESURE",
        # `None` quand aucun mot n'est arrive : ce n'est pas « instantane ».
        "premier_mot_s": None if premier is None else round(premier - debut, 3),
        "total_s": round(fin - debut, 3),
        "morceaux": morceaux,
    }


async def comparer(repetitions: int = 1) -> Dict[str, Any]:
    """Fait tourner les trois scenes sur chaque fournisseur configure."""
    from apps.backend.config import MODELE_PROFOND, OLLAMA_URL
    from core.models.deepinfra_provider import DeepInfraProvider
    from core.models.groq_provider import GroqProvider
    from core.models.ollama_provider import OllamaProvider

    fournisseurs = {
        "ollama": OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_PROFOND),
        "groq": GroqProvider(),
        "deepinfra": DeepInfraProvider(),
    }

    resultats: Dict[str, Any] = {}
    for nom, fournisseur in fournisseurs.items():
        if not await fournisseur.is_available():
            resultats[nom] = {"etat": ABSENT,
                              "detail": "pas de cle, ou service injoignable",
                              "modele": getattr(fournisseur, "model_name", "?")}
            continue

        scenes: Dict[str, Any] = {}
        for scene, prompt in SCENES:
            passages = [await mesurer_un(fournisseur, prompt) for _ in range(repetitions)]
            mesures = [p for p in passages if p["etat"] == "MESURE"]
            if not mesures:
                scenes[scene] = passages[0]
                continue
            premiers = [p["premier_mot_s"] for p in mesures if p["premier_mot_s"] is not None]
            scenes[scene] = {
                "etat": "MESURE",
                # La mediane : une seule execution mesure autant le hasard que
                # la machine.
                "premier_mot_s": round(statistics.median(premiers), 3) if premiers else None,
                "total_s": round(statistics.median([p["total_s"] for p in mesures]), 3),
                "passages": len(mesures),
            }
        resultats[nom] = {"etat": "MESURE",
                          "modele": getattr(fournisseur, "model_name", "?"),
                          "scenes": scenes}
    return resultats


def rendre(resultats: Dict[str, Any]) -> str:
    """Le tableau. Les absents y restent : c'est eux qui disent ce qui manque."""
    lignes = [f"{'fournisseur':<12} {'modele':<34} {'scene':<9} "
              f"{'1er mot':>9} {'total':>9}"]
    lignes.append("-" * 78)
    for nom, resultat in resultats.items():
        if resultat["etat"] != "MESURE":
            lignes.append(f"{nom:<12} {resultat.get('modele', '?'):<34} "
                          f"{ABSENT:<9} {resultat['detail']}")
            continue
        for scene, mesure in resultat["scenes"].items():
            if mesure["etat"] != "MESURE":
                lignes.append(f"{nom:<12} {resultat['modele']:<34} {scene:<9} "
                              f"{mesure['etat']} {mesure.get('detail', '')}")
                continue
            premier = ("UNKNOWN" if mesure["premier_mot_s"] is None
                       else f"{mesure['premier_mot_s']:.3f}s")
            lignes.append(f"{nom:<12} {resultat['modele']:<34} {scene:<9} "
                          f"{premier:>9} {mesure['total_s']:>8.3f}s")
    mesures = [n for n, r in resultats.items() if r["etat"] == "MESURE"]
    lignes.append("")
    lignes.append(f"{len(mesures)} fournisseur(s) mesure(s), "
                  f"{len(resultats) - len(mesures)} absent(s).")
    if len(mesures) < 2:
        lignes.append("Moins de deux fournisseurs : AUCUNE comparaison n'est possible. "
                      "Ne rien conclure.")
    return "\n".join(lignes)


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--repetitions", type=int, default=1,
                           help="passages par scene ; la mediane est retenue")
    options = analyseur.parse_args()

    print("=" * 78)
    print("  ARENA — comparaison des fournisseurs. Mesure reelle, pas promesse.")
    print("=" * 78)
    resultats = asyncio.run(comparer(max(1, options.repetitions)))
    print(rendre(resultats))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
