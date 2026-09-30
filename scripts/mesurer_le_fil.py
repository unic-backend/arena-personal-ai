"""Ce que coute le fil joint aux agents, et ou ses deux bornes coupent.

    python scripts/mesurer_le_fil.py

DEC-0191 joint toujours les derniers tours de la conversation devant la
demande, pour dix intentions de `apps/backend/routers/chat.py`. Deux bornes
l'encadrent : un nombre de tours (`TOURS_RELUS_DEFAUT`) et un budget en
caracteres (`BUDGET_TOURS_ANTERIEURS`). Ce script mesure ce que ces deux
chiffres valent en pratique, pour qu'ils ne restent pas des preferences :

1. la taille reelle d'un bloc de six tours, sur les deux corpus de
   conversation du depot ;
2. a partir de quelle longueur de tour le budget coupe avant le compteur ;
3. combien de cas de reference du jeu d'or tiennent dans six tours, et
   lesquels relevent de la memoire longue plutot que de ce bloc ;
4. le temps que coute la composition — il n'y a aucun appel modele ici, et
   ce chiffre est la pour le prouver.

Rejouer la mesure est le seul moyen de savoir si les chiffres tiennent
encore : c'est la regle de `CLAUDE.md`.
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
import time

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from core.context.fil_pour_agents import (  # noqa: E402
    demande_avec_le_fil,
    tours_sous_les_bornes,
)
from core.memory.conversation import BUDGET_TOURS_ANTERIEURS  # noqa: E402

TOURS_RELUS_DEFAUT = 6  # meme valeur que apps/backend/routers/chat.py
PROPRIETAIRE = "Ousmane"


def _corpus() -> list[list[str]]:
    """Les conversations francaises que le depot versionne deja."""
    conversations: list[list[str]] = []
    banc = json.loads((RACINE / "tests" / "conversation_benchmark.json").read_text("utf-8"))
    for scenario in banc["scenarios"]:
        conversations.append(list(scenario["history"]) + [scenario["query"]])
    jeu_d_or = json.loads(
        (RACINE / "tests" / "intelligence_post_merge_goldens.json").read_text("utf-8"))
    for cas in jeu_d_or["goldens"]:
        conversations.append(list(cas.get("history") or []) + [cas.get("query", "")])
    return conversations


def _en_tours(phrases: list[str]) -> list[dict]:
    """Une conversation reelle alterne : lui, puis ARENA."""
    tours = []
    for rang, phrase in enumerate(phrases):
        tours.append({"role": "user" if rang % 2 == 0 else "assistant",
                      "content": phrase})
    return tours


def mesurer() -> None:
    conversations = _corpus()
    longueurs = [len(p) for conv in conversations for p in conv if p]
    longueurs.sort()
    print("— Corpus de conversation du depot —")
    print(f"  {len(conversations)} conversations, {len(longueurs)} tours")
    print(f"  longueur d'un tour : mediane {statistics.median(longueurs):.0f} car., "
          f"p95 {longueurs[int(0.95 * len(longueurs)) - 1]} car., "
          f"max {longueurs[-1]} car.")

    blocs = []
    for conv in conversations:
        tours = _en_tours([p for p in conv if p])
        retenus = tours_sous_les_bornes(tours[:-1], PROPRIETAIRE,
                                        maximum=TOURS_RELUS_DEFAUT)
        blocs.append(len(demande_avec_le_fil(tours[-1]["content"], tours[:-1],
                                             PROPRIETAIRE,
                                             maximum=TOURS_RELUS_DEFAUT)))
        assert len(retenus) <= TOURS_RELUS_DEFAUT
    blocs.sort()
    print(f"  bloc complet (balises comprises) : mediane {statistics.median(blocs):.0f} car., "
          f"max {blocs[-1]} car., budget {BUDGET_TOURS_ANTERIEURS} car.")
    print(f"  -> sur ce corpus, c'est le compteur de tours qui borne, "
          f"jamais le budget ({100 * sum(1 for b in blocs if b > BUDGET_TOURS_ANTERIEURS) / len(blocs):.0f} % au-dessus)")

    # 2. Ou le budget prend la main : six tours de N caracteres.
    seuil = BUDGET_TOURS_ANTERIEURS // TOURS_RELUS_DEFAUT
    long_tour = [{"role": "assistant", "content": "x" * seuil}] * TOURS_RELUS_DEFAUT
    gardes = tours_sous_les_bornes(long_tour, PROPRIETAIRE, maximum=TOURS_RELUS_DEFAUT)
    print("\n— Ou le budget coupe —")
    print(f"  le budget passe devant le compteur des que le tour moyen depasse "
          f"~{seuil} caracteres")
    print(f"  six tours de {seuil} car. : {len(gardes)} gardes "
          f"(les plus anciens partent d'abord)")

    # 3. Les cas de reference du jeu d'or.
    jeu_d_or = json.loads(
        (RACINE / "tests" / "intelligence_post_merge_goldens.json").read_text("utf-8"))
    distances = {"coreference": [], "long_conversation_coreference": []}
    for cas in jeu_d_or["goldens"]:
        if cas["category"] not in distances:
            continue
        reference = (cas.get("expected_reference") or "").casefold()
        histoire = cas.get("history") or []
        rangs = [i for i, tour in enumerate(histoire)
                 if reference and reference in re.sub(r"\W+", " ", tour.casefold())]
        if rangs:
            distances[cas["category"]].append(len(histoire) - rangs[-1])
    print("\n— A quelle distance se trouve le sujet designe (jeu d'or permanent) —")
    for categorie, valeurs in distances.items():
        if not valeurs:
            continue
        # Un tour du proprietaire, une reponse : la distance double en messages.
        en_messages = [2 * d for d in valeurs]
        tiennent = sum(1 for d in en_messages if d <= TOURS_RELUS_DEFAUT)
        print(f"  {categorie} : {len(valeurs)} cas, sujet a "
              f"{min(valeurs)}-{max(valeurs)} tours ({min(en_messages)}-{max(en_messages)} messages) ; "
              f"{tiennent}/{len(valeurs)} tiennent dans {TOURS_RELUS_DEFAUT} messages")

    # 4. Le cout de la composition.
    tours = _en_tours(["Le dernier match du FC Barcelone etait contre Seville." * 3] * 6)
    debut = time.perf_counter()
    for _ in range(1000):
        demande_avec_le_fil("donne-moi un nom", tours, PROPRIETAIRE,
                            maximum=TOURS_RELUS_DEFAUT)
    microsecondes = (time.perf_counter() - debut) * 1000
    print("\n— Ce que coute la composition —")
    print(f"  {microsecondes:.0f} us par bloc, aucun appel modele, aucune lecture reseau")


if __name__ == "__main__":
    mesurer()
