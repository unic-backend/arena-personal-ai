"""Benchmark local reproductible de la politique conversationnelle.

Il mesure la couche déterministe, pas la qualité subjective d'un LLM externe.
Les 5 graines sont multipliées par 20 distracteurs pour 100 scénarios stables.
"""
import json
from pathlib import Path

from apps.backend.services.conversation_intelligence import (
    accept_memory,
    score_memory,
    understand,
)

DATA = json.loads((Path(__file__).with_name("conversation_benchmark.json")).read_text(encoding="utf-8"))


class SignalEvaluation:
    def __init__(self, nom, valeur):
        self.nom = nom
        self.valeur = valeur


class TentativeEvaluation:
    def __init__(self, scenario, correcte, signaux=(), erreur=None):
        self.scenario = scenario
        self.correcte = correcte
        self.signaux = signaux
        self.erreur = erreur


def agreger(tentatives):
    total = len(tentatives)
    correctes = sum(t.correcte for t in tentatives)
    sommes = {}
    comptes = {}
    for tentative in tentatives:
        for signal in tentative.signaux:
            sommes[signal.nom] = sommes.get(signal.nom, 0.0) + signal.valeur
            comptes[signal.nom] = comptes.get(signal.nom, 0) + 1
    return {
        "total": total,
        "correctes": correctes,
        "score": correctes / total if total else 0.0,
        "moyennes": {nom: sommes[nom] / comptes[nom] for nom in sommes},
    }


DISTRACTORS = [
    "serveur", "voiture", "vidéo", "chantier", "ordinateur", "PDF", "facture", "mémoire", "Qwen", "Wan",
    "RTX", "téléphone", "client", "devis", "Docker", "GitHub", "plafond", "isolation", "banque", "application",
]


def test_benchmark_has_one_hundred_scenarios():
    assert len(DATA["scenarios"]) * len(DISTRACTORS) == 100


def test_precision_first_benchmark():
    tentatives = []
    for seed in DATA["scenarios"]:
        for distractor in DISTRACTORS:
            history = [{"role": "user", "content": text} for text in seed["history"]]
            state = understand(seed["query"], history)
            wrong = {
                "content": f"Le sujet {distractor} a une information différente sans rapport avec la question.",
                "created": 0.0, "conversation_id": "other", "kind": "user_fact",
            }
            wrong_features = score_memory(seed["query"], wrong, state, semantic_score=0.96)
            wrong_rejected = not accept_memory(wrong_features, 0.18)
            transition_ok = True
            if seed["expect"] == "continuation":
                transition_ok = state.transition in {"CONTINUATION", "TOPIC_RETURN"}
            elif seed["expect"] == "topic_return":
                transition_ok = state.transition == "TOPIC_RETURN"
            tentatives.append(TentativeEvaluation(
                scenario=f"{seed['id']}:{distractor}",
                correcte=wrong_rejected and transition_ok,
                signaux=(
                    SignalEvaluation("rejet_hors_sujet", float(wrong_rejected)),
                    SignalEvaluation("transition", float(transition_ok)),
                ),
            ))
    rapport = agreger(tentatives)
    # Precision est le critère bloquant : aucun distracteur manifestement hors sujet accepté.
    assert rapport["total"] == rapport["correctes"] == 100
    assert rapport["score"] == 1.0
    assert rapport["moyennes"]["rejet_hors_sujet"] == 1.0
    assert rapport["moyennes"]["transition"] == 1.0
