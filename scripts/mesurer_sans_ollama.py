"""Que fait ARENA sur une machine SANS Ollama ? La question du serveur.

    python scripts/mesurer_sans_ollama.py

DEC-0021 decide qu'ARENA sera heberge en ligne. Un petit serveur n'a pas de
carte graphique : **Ollama n'y sera pas**. Or `RouteurModeles._candidats()`
ajoute toujours `LOCAL` en dernier recours, et sa docstring l'annonce — « rend
toujours au moins Ollama : ARENA repond, quoi qu'il arrive ». Cette phrase est
vraie sur son PC. Elle ne l'est plus sur un serveur.

Ce script ne corrige rien. Il **mesure** ce que le routeur decide et ce qu'il
fait quand sa machine locale est absente, pour que la correction parte d'un
constat et pas d'une supposition.

**Trois regles :**

1. **L'absence est reelle, pas simulee.** Le fournisseur local pointe vers un
   port ou rien n'ecoute. C'est exactement ce que vit un serveur sans Ollama —
   pas un objet de test qui leve ce qu'on lui a dit de lever.

2. **La decision se mesure meme sans cle.** Quels candidats, dans quel ordre,
   pour quelle raison : cela ne demande aucun reseau. Ce qui en demande — la
   reponse elle-meme — se rapporte `UNKNOWN` quand aucun distant n'est
   configure, jamais suppose.

3. **Les phrases sont neutres et ecrites ici.** Aucune demande reelle du
   proprietaire ne sert de banc d'essai (meme regle que
   `scripts/comparer_fournisseurs.py`).
"""
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#: Un port ou rien n'ecoute : l'absence d'Ollama, pour de vrai.
OLLAMA_ABSENT = "http://127.0.0.1:1"

#: Trois demandes, une par niveau que le classement peut atteindre en HYBRIDE.
#: Neutres exprès : ni client, ni montant, ni chantier reel.
SCENES = (
    ("PUBLIC attendu", "Qu'est-ce qu'une cloison en plaques de platre ?"),
    ("PRIVE attendu", "Rappelle-moi ce que je t'ai demande hier."),
    ("SENSIBLE attendu", "Prepare le devis du client Dupont pour 450000 FCFA."),
)

UNKNOWN = "UNKNOWN"


async def mesurer(routeur: Any, prompt: str) -> Dict[str, Any]:
    """Ce que le routeur decide, puis ce qu'il fait. La decision d'abord."""
    from core.models.confidentialite import classer

    classement = classer(prompt)
    candidats, raison = routeur._candidats(classement)

    mesure: Dict[str, Any] = {
        "niveau": classement.niveau.value,
        "candidats": list(candidats),
        "raison": raison,
    }

    if candidats == ["local"] and not routeur.distants:
        # Rien a joindre : inutile d'attendre un reseau pour le savoir.
        pass

    try:
        reponse = await routeur.generate(prompt)
        mesure["issue"] = "REPONSE"
        mesure["detail"] = f"{len(reponse)} caractere(s)"
    except Exception as erreur:  # noqa: BLE001 — l'echec EST la mesure
        mesure["issue"] = type(erreur).__name__
        mesure["detail"] = str(erreur)
    return mesure


async def principal() -> List[Dict[str, Any]]:
    from apps.backend.config import MODE_IA, MODELE_PROFOND
    from core.models.deepinfra_provider import DeepInfraProvider
    from core.models.groq_provider import GroqProvider
    from core.models.ollama_provider import OllamaProvider
    from core.models.routeur import RouteurModeles

    routeur = RouteurModeles(
        local=OllamaProvider(base_url=OLLAMA_ABSENT, model_name=MODELE_PROFOND),
        distants={"groq": GroqProvider(), "deepinfra": DeepInfraProvider()},
        mode=MODE_IA,
    )

    print("=" * 78)
    print("  ARENA sans Ollama — ce que devient le routeur sur un serveur.")
    print("=" * 78)
    print(f"Mode        : {MODE_IA}")
    print(f"Local       : {OLLAMA_ABSENT} (rien n'ecoute)")
    distants = sorted(routeur.distants) or ["aucun"]
    print(f"Distants    : {', '.join(distants)}")
    if not routeur.distants:
        print(f"Reponses    : {UNKNOWN} — aucun distant configure sur cette machine.")
        print("              La DECISION du routeur reste mesurable ci-dessous.")
    print("-" * 78)
    print(f"{'scene':<18} {'niveau':<10} {'candidats':<22} issue")
    print("-" * 78)

    mesures = []
    for nom, prompt in SCENES:
        mesure = await mesurer(routeur, prompt)
        mesure["scene"] = nom
        mesures.append(mesure)
        print(f"{nom:<18} {mesure['niveau']:<10} "
              f"{','.join(mesure['candidats']):<22} {mesure['issue']}")
        print(f"{'':<18} pourquoi : {mesure['raison']}")
        if mesure["detail"]:
            print(f"{'':<18} detail   : {mesure['detail']}")
    print("=" * 78)
    return mesures


if __name__ == "__main__":
    asyncio.run(principal())
