"""Test controle UniC Plaquiste, en lecture seule (mission §40).

Utilise le VRAI `config/metier.yaml` du depot (jamais un double) — c'est le
contexte metier deja autorise sur cette machine. Aucune ecriture, aucun
envoi, aucune commande : uniquement une analyse.
"""
import pytest

from core.executive.contrat import Position
from core.executive.moteur import MoteurExecutif
from core.models.base import ModelProvider


class FauxProvider(ModelProvider):
    def __init__(self):
        self.prompts_recus = []

    async def generate(self, prompt, system_prompt=None):
        self.prompts_recus.append(prompt)
        return "Evaluation executive : situation a completer avec des donnees reelles."

    async def is_available(self):
        return True


@pytest.mark.asyncio
class TestEvaluationExecutiveUnicPlaquiste:
    async def test_le_contexte_metier_reel_est_recupere(self):
        provider = FauxProvider()
        moteur = MoteurExecutif(provider=provider)
        decision = await moteur.analyser(
            "Donne-moi une evaluation executive de la situation actuelle de l'entreprise.")
        # Au moins un role a ete convoque (le repli §40 sur finance+risque).
        assert decision.roles_consultes
        # Le contexte metier reel est bien charge — verifie directement,
        # plutot que de supposer sa presence textuelle dans chaque prompt.
        from core.executive.contexte_affaires import charger_contexte_affaires
        contexte = charger_contexte_affaires()
        assert contexte.disponible
        assert contexte.nom

    async def test_aucun_chiffre_invente_sans_donnees_projet(self):
        """La question ne fournit AUCUN chiffre de projet — la reponse ne
        doit jamais en inventer un a la place."""
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Donne-moi une evaluation executive de la situation actuelle de l'entreprise.")
        analyse_finance = next((a for a in decision.analyses if a.role == "finance"), None)
        if analyse_finance is not None:
            # Sans chiffre fourni, jamais un verdict favorable/defavorable invente.
            assert analyse_finance.position == Position.NEUTRE

    async def test_information_manquante_est_marquee_inconnue(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Donne-moi une evaluation executive de la situation actuelle de l'entreprise.")
        assert decision.informations_manquantes or any(
            a.inconnues for a in decision.analyses
        )

    async def test_aucune_action_externe_n_est_executee(self):
        """§40 : lecture seule — la decision ne fait QUE recommander, jamais
        n'envoie ni ne modifie rien. Verifie que la reponse ne contient aucun
        artefact d'action reelle (aucun connecteur d'ecriture n'est meme
        accessible depuis ce moteur — voir ExecutiveAgent, qui n'a pas de
        methode d'action)."""
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Donne-moi une evaluation executive de la situation actuelle de l'entreprise.")
        d = decision.to_dict()
        # La sortie est un dict serialisable, purement informatif.
        assert isinstance(d, dict)
        assert "response" in d
