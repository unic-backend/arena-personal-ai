"""Trois corrections demandées par le propriétaire le 27/08/2026.

Ses mots : *« je ne peux pas à chaque fois que je parle avec l'IA qu'il me dise
des parois ou Fast Group »*, *« je peux pas lui dire de faire un devis et il met
une mauvaise date »*, *« tout ce qui est électricité ne dépend pas de moi »*.

Trois défauts réels, dont deux venaient de mon propre travail.
"""
from datetime import date

import pytest

from agents.plaquiste.archives import exemple_demande
from agents.plaquiste.devis_pdf import Devis, Ligne
from agents.plaquiste.plaquiste_agent import (
    charger_metier,
    composer_instruction,
    date_en_toutes_lettres,
    metiers_evoques,
    numero_du_jour,
)

METIER = charger_metier()


class ModeleDouble:
    def __init__(self):
        self.systemes = []

    async def generate(self, prompt, system_prompt=None, **kw):
        self.systemes.append(system_prompt)
        return "reponse"


class TestLesArchivesNeSOuvrentQueSurDemande:
    """Injectées à chaque réponse, elles ramenaient l'ancien client partout."""

    @pytest.mark.parametrize("demande", [
        "fais un devis de 89 m2 pour M. Diallo",
        "ecris un mail au client",
        "combien de plaques pour 40 m2",
        "prepare la facture",
    ])
    def test_une_demande_ordinaire_n_ouvre_pas_les_archives(self, demande):
        assert exemple_demande(demande) is False

    @pytest.mark.parametrize("demande", [
        "fais un devis comme le devis Fast Group",
        "reprends le style de mes devis",
        "utilise le meme format que d'habitude",
        "montre-moi un exemple de lettre",
    ])
    def test_une_demande_de_reference_les_ouvre(self, demande):
        assert exemple_demande(demande) is True

    async def test_aucun_ancien_client_dans_une_demande_ordinaire(self):
        """Le cas exact rapporté : un nouveau devis ne doit pas parler de l'ancien."""
        from agents.plaquiste.plaquiste_agent import PlaquisteAgent

        modele = ModeleDouble()
        res = await PlaquisteAgent(provider=modele, metier=METIER).run(
            "fais un devis de 89 m2 pour M. Diallo a Ouakam"
        )

        assert res["extraits_archives"] == []
        assert "Fast Group" not in modele.systemes[0]


class TestLaDateVientDeLHorloge:
    """Un devis mal daté est un devis juridiquement fragile."""

    def test_l_instruction_annonce_la_date_reelle(self):
        instruction = composer_instruction(METIER)
        assert date_en_toutes_lettres(date.today()) in instruction

    def test_l_instruction_interdit_une_autre_date(self):
        assert "jamais une autre date" in composer_instruction(METIER)

    def test_le_devis_est_date_du_jour_sans_qu_on_le_demande(self):
        devis = Devis(client="M. Diallo", lieu="Ouakam", objet="Cloisons",
                      lignes=[Ligne("Plaque standard BA13", 10)])

        assert devis.date == date_en_toutes_lettres(date.today())

    def test_le_numero_suit_la_numerotation_maison(self):
        devis = Devis(client="M. Diallo", lieu="Ouakam", objet="Cloisons",
                      suffixe_client="DIA")

        assert devis.numero == numero_du_jour(date.today(), "DIA")
        assert devis.numero.startswith("UC-")

    def test_une_date_donnee_explicitement_est_respectee(self):
        """Refaire un ancien document reste possible."""
        devis = Devis(client="X", lieu="Y", objet="Z", date="14 juillet 2026")
        assert devis.date == "14 juillet 2026"


class TestLeClientEstCeluiQuOnDonne:
    def test_l_instruction_interdit_d_inventer_un_client(self):
        instruction = composer_instruction(METIER)

        assert "LE CLIENT EST CELUI QU'ON TE DONNE" in instruction
        assert "jamais ceux d'une affaire passee" in instruction

    def test_l_instruction_demande_au_lieu_de_supposer(self):
        assert "tu les demandes" in composer_instruction(METIER)


class TestLesMetiersQuiNeSontPasLesSiens:
    """« Électricité ne dépend pas de moi. Tu le laisses dormir. »"""

    @pytest.mark.parametrize("demande,attendu", [
        ("devis de 89 m2 de cloison", []),
        ("devis cloison plus electricite", ["electricite"]),
        ("refais la plomberie", ["plomberie"]),
        ("installe la climatisation", ["climatisation"]),
    ])
    def test_les_metiers_hors_perimetre_sont_reperes(self, demande, attendu):
        assert metiers_evoques(demande, METIER) == attendu

    def test_l_instruction_interdit_de_les_chiffrer(self):
        instruction = composer_instruction(METIER)

        assert "N'EST PAS SON METIER" in instruction
        assert "Tu ne chiffres jamais ces postes" in instruction

    def test_la_capacite_dort_mais_n_est_pas_retiree(self):
        """Réveillée seulement si le gérant le demande explicitement."""
        assert "si le gerant te le demande" in composer_instruction(METIER)

    async def test_l_agent_rapporte_ce_qui_est_hors_perimetre(self):
        from agents.plaquiste.plaquiste_agent import PlaquisteAgent

        res = await PlaquisteAgent(provider=ModeleDouble(), metier=METIER).run(
            "devis cloison et electricite"
        )
        assert res["hors_perimetre"] == ["electricite"]

    def test_la_liste_vient_du_fichier_metier(self):
        modifie = {**METIER, "metiers_hors_perimetre": ["carrelage"]}
        assert metiers_evoques("pose du carrelage", modifie) == ["carrelage"]
