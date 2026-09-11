"""La couche de contexte metier — jamais UniC Plaquiste en dur dans le code
(mission §11)."""

import core.executive.contexte_affaires as ctx


class TestChargerContexteAffaires:
    def test_charge_le_fichier_reellement_configure(self):
        """Aucun mock : c'est le vrai `config/metier.yaml` du depot, exactement
        ce que `agents/plaquiste/chemins.py::fichier_metier()` resout deja."""
        contexte = ctx.charger_contexte_affaires()
        assert contexte.disponible
        assert contexte.nom  # le nom present dans ce depot, quel qu'il soit
        assert contexte.grille_tarifaire_chargee
        assert contexte.nombre_articles_grille > 0

    def test_fichier_absent_rend_indisponible(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ctx, "fichier_metier", lambda: tmp_path / "n_existe_pas.yaml")
        contexte = ctx.charger_contexte_affaires()
        assert not contexte.disponible
        assert "n_existe_pas" in contexte.raison_indisponible

    def test_fichier_illisible_rend_indisponible(self, monkeypatch, tmp_path):
        fichier = tmp_path / "metier.yaml"
        fichier.write_text(": : : pas du yaml valide : : :\n\tfoo", encoding="utf-8")
        monkeypatch.setattr(ctx, "fichier_metier", lambda: fichier)
        contexte = ctx.charger_contexte_affaires()
        assert not contexte.disponible

    def test_format_inattendu_rend_indisponible(self, monkeypatch, tmp_path):
        fichier = tmp_path / "metier.yaml"
        fichier.write_text("- juste\n- une\n- liste\n", encoding="utf-8")
        monkeypatch.setattr(ctx, "fichier_metier", lambda: fichier)
        contexte = ctx.charger_contexte_affaires()
        assert not contexte.disponible
        assert "mapping" in contexte.raison_indisponible

    def test_aucun_champ_invente_quand_absent(self, monkeypatch, tmp_path):
        fichier = tmp_path / "metier.yaml"
        fichier.write_text("entreprise:\n  nom: Autre Metier\n", encoding="utf-8")
        monkeypatch.setattr(ctx, "fichier_metier", lambda: fichier)
        contexte = ctx.charger_contexte_affaires()
        assert contexte.disponible
        assert contexte.nom == "Autre Metier"
        assert contexte.devise is None
        assert not contexte.grille_tarifaire_chargee


class TestBlocPourPrompt:
    def test_indisponible_le_dit(self):
        contexte = ctx.ContexteAffaires(disponible=False, raison_indisponible="absent")
        assert "absent" in contexte.bloc_pour_prompt()

    def test_disponible_liste_les_champs(self):
        contexte = ctx.ContexteAffaires(
            disponible=True, nom="X", specialite="Y", devise="FCFA",
            grille_tarifaire_chargee=True, nombre_articles_grille=10,
        )
        bloc = contexte.bloc_pour_prompt()
        assert "X" in bloc and "Y" in bloc and "FCFA" in bloc and "10" in bloc


class TestPreuvesDocumentaires:
    def test_sans_moteur_rend_liste_vide(self):
        assert ctx.preuves_documentaires("question", lightrag_query=None) == []

    def test_moteur_en_echec_rend_liste_vide(self):
        def echoue(_):
            raise RuntimeError("panne")
        assert ctx.preuves_documentaires("question", lightrag_query=echoue) == []

    def test_reponse_vide_rend_liste_vide(self):
        assert ctx.preuves_documentaires("question", lightrag_query=lambda q: "   ") == []

    def test_reponse_reelle_est_gardee(self):
        preuves = ctx.preuves_documentaires("question", lightrag_query=lambda q: "un extrait pertinent")
        assert preuves == ["un extrait pertinent"]
