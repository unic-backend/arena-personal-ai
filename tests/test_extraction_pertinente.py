"""Le passage envoyé au modèle doit être celui qui répond, pas le début de la page.

Cas réel, mesuré le 2026-08-26 : à « qui a gagné la dernière coupe du monde »,
Usman a répondu *« la dernière Coupe du Monde remportée par l'équipe française a
eu lieu en 2018 »*, en citant une page de palmarès qui contenait la bonne
réponse — plus bas que la coupure. L'extrait était les N premiers caractères.
"""
from agents.fresh_info.fresh_info_agent import FreshInfoAgent

extraire = FreshInfoAgent.extraire_pertinent

PALMARES = "\n\n".join([
    "La Coupe du monde de football est une compétition internationale organisée "
    "par la FIFA. Elle se déroule tous les quatre ans depuis 1930, à l'exception "
    "des années de guerre. Cet article présente le palmarès des nations.",
    "Le trophée actuel a été dessiné en 1974. Il est remis au capitaine de "
    "l'équipe vainqueur lors de la cérémonie de clôture du tournoi.",
    "En 2018, la France a remporté le tournoi organisé en Russie.",
    "En 2022, l'Argentine a remporté le tournoi organisé au Qatar.",
    "En 2026, l'Espagne a remporté le tournoi organisé en Amérique du Nord.",
])


class TestExtractionPertinente:
    def test_le_passage_qui_repond_survit_a_la_coupe(self):
        """Le cas exact du 2026-08-26."""
        extrait = extraire(PALMARES, "qui a gagné la dernière coupe du monde 2026", 300)

        assert "2026" in extrait
        assert "Espagne" in extrait

    def test_l_ancien_comportement_aurait_echoue(self):
        """La preuve que le défaut était réel : les N premiers caractères."""
        ancien = PALMARES[:300]

        assert "2026" not in ancien
        assert "Espagne" not in ancien

    def test_l_ordre_du_document_est_conserve(self):
        """Un palmarès lu à l'envers se comprend mal."""
        extrait = extraire(PALMARES, "coupe du monde 2018 2022 2026", 400)

        positions = [extrait.find(a) for a in ("2018", "2022", "2026") if a in extrait]
        assert positions == sorted(positions)

    def test_un_texte_plus_court_que_le_budget_passe_entier(self):
        court = "Une seule phrase."
        assert extraire(court, "peu importe", 5000) == court

    def test_sans_mot_utile_on_retombe_sur_le_debut(self):
        """Aucune correspondance ne doit pas produire un extrait vide."""
        extrait = extraire(PALMARES, "??? !!!", 200)

        assert extrait
        assert extrait.startswith("La Coupe du monde")

    def test_le_budget_est_respecte(self):
        extrait = extraire(PALMARES, "coupe du monde argentine espagne france", 250)
        assert len(extrait) <= 250

    def test_le_passage_le_plus_riche_est_prefere(self):
        texte = "\n\n".join([
            "Paragraphe sans rapport avec quoi que ce soit d'utile ici.",
            "Le Sénégal a remporté la Coupe d'Afrique des nations en 2022.",
            "Autre paragraphe sans rapport, de remplissage.",
        ])
        extrait = extraire(texte, "quand le Sénégal a remporté la Coupe d'Afrique", 80)

        assert "Sénégal" in extrait
