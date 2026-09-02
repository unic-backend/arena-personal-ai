"""Les chemins ne nomment plus d'entreprise — sans perdre les fichiers déjà là.

Décision du propriétaire, 02/09/2026 : « ce projet est libre comme bonjour,
tout le monde peut s'en servir ». Un fichier appelé `unic_plaquiste.yaml`
disait le contraire à quiconque clonait le dépôt.

**Le risque réel du renommage n'est pas dans le code, il est sur son disque.**
`documents/` est exclu de git : renommer le dossier ici ne déplace rien chez
lui. Ses archives et sa signature manuscrite sont restées dans
`documents/unic_plaquiste/`, et une constante pointant sur le nouveau nom les
aurait rendues invisibles du jour au lendemain — sans erreur, sans message.

`TestLAncienDossierNEstPasPerdu` est la classe qui tient ça. Le reste vérifie
que les noms sont bien devenus génériques.
"""
import pytest

from agents.plaquiste import chemins


@pytest.fixture
def bac(tmp_path, monkeypatch):
    """Une fausse racine, pour mesurer sans toucher au dépôt."""
    monkeypatch.setattr(chemins, "RACINE", tmp_path)
    monkeypatch.setattr(chemins, "FICHIER_METIER", tmp_path / "config" / "metier.yaml")
    monkeypatch.setattr(chemins, "FICHIER_METIER_ANCIEN",
                        tmp_path / "config" / "unic_plaquiste.yaml")
    monkeypatch.setattr(chemins, "DOSSIER_DOCUMENTS", tmp_path / "documents" / "metier")
    monkeypatch.setattr(chemins, "DOSSIER_DOCUMENTS_ANCIEN",
                        tmp_path / "documents" / "unic_plaquiste")
    monkeypatch.setattr(chemins, "LOGO", tmp_path / "config" / "marque" / "logo.png")
    monkeypatch.setattr(chemins, "LOGO_ANCIEN",
                        tmp_path / "config" / "marque" / "logo_unic_plaquiste.png")
    return tmp_path


def _poser(chemin, contenu="x"):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# --- Ce qui protège ses fichiers ------------------------------------------------------

class TestLAncienDossierNEstPasPerdu:
    """Le dossier des documents est hors de git : le renommer ici ne le renomme
    nulle part. Ses archives et sa signature doivent rester trouvables."""

    def test_l_ancien_dossier_gagne_tant_qu_il_porte_des_documents(self, bac):
        _poser(bac / "documents" / "unic_plaquiste" / "devis_client.pdf")
        _poser(bac / "documents" / "metier" / "LISEZ_MOI.md")

        assert chemins.dossier_des_documents().name == "unic_plaquiste"

    def test_le_mode_d_emploi_seul_ne_fait_pas_un_dossier_qui_sert(self, bac):
        """Le nouveau dossier arrive par git avec son seul LISEZ_MOI : s'il
        suffisait à l'emporter, la bascule masquerait les vrais documents."""
        _poser(bac / "documents" / "unic_plaquiste" / "devis_client.pdf")
        _poser(bac / "documents" / "metier" / "LISEZ_MOI.md")
        _poser(bac / "documents" / "metier" / "readme.md")

        assert chemins.dossier_des_documents().name == "unic_plaquiste"

    def test_des_qu_un_document_entre_dans_le_nouveau_la_bascule_se_fait(self, bac):
        _poser(bac / "documents" / "unic_plaquiste" / "devis_client.pdf")
        _poser(bac / "documents" / "metier" / "devis_client.pdf")

        assert chemins.dossier_des_documents().name == "metier"

    def test_sans_ancien_dossier_c_est_le_nouveau(self, bac):
        _poser(bac / "documents" / "metier" / "LISEZ_MOI.md")

        assert chemins.dossier_des_documents().name == "metier"

    def test_sans_rien_du_tout_c_est_encore_le_nouveau(self, bac):
        """Une installation neuve n'a aucun des deux : elle doit viser le nom
        générique, pas celui d'une entreprise."""
        assert chemins.dossier_des_documents().name == "metier"

    def test_la_signature_suit_le_dossier_retenu(self, bac):
        _poser(bac / "documents" / "unic_plaquiste" / "devis_client.pdf")
        signature = _poser(bac / "documents" / "unic_plaquiste" / "signature_uthman.png")

        assert chemins.signature() == signature

    def test_une_signature_au_nom_generique_l_emporte(self, bac):
        _poser(bac / "documents" / "metier" / "devis_client.pdf")
        _poser(bac / "documents" / "metier" / "signature_uthman.png")
        generique = _poser(bac / "documents" / "metier" / "signature.png")

        assert chemins.signature() == generique


# --- Les noms sont devenus génériques --------------------------------------------------

class TestLesNomsNeDesignentPlusUneEntreprise:
    def test_le_fichier_metier_vise_le_nom_generique(self, bac):
        _poser(bac / "config" / "metier.yaml", "prix: {}")

        assert chemins.fichier_metier().name == "metier.yaml"

    def test_l_ancien_fichier_reste_lu_s_il_est_seul(self, bac):
        """Un fichier de prix perdu, c'est un devis qui ne se chiffre plus."""
        ancien = _poser(bac / "config" / "unic_plaquiste.yaml", "prix: {}")

        assert chemins.fichier_metier() == ancien

    def test_le_logo_vise_le_nom_generique(self, bac):
        _poser(bac / "config" / "marque" / "logo.png")

        assert chemins.logo().name == "logo.png"

    def test_l_ancien_logo_reste_lu_s_il_est_seul(self, bac):
        ancien = _poser(bac / "config" / "marque" / "logo_unic_plaquiste.png")

        assert chemins.logo() == ancien


# --- Ce qui est réellement dans le dépôt -----------------------------------------------

class TestLeDepotLuiMemeEstGenerique:
    """Les mesures ci-dessus tournent dans un bac à sable. Celles-ci regardent
    le vrai dépôt : c'est lui qu'un inconnu clone."""

    def test_aucun_chemin_du_depot_ne_nomme_l_entreprise(self):
        for chemin in (chemins.FICHIER_METIER, chemins.LOGO, chemins.DOSSIER_DOCUMENTS):
            assert "unic" not in chemin.name.lower(), f"{chemin} nomme une entreprise"

    def test_les_fichiers_generiques_existent_vraiment(self):
        assert chemins.FICHIER_METIER.is_file(), "config/metier.yaml a disparu"
        assert chemins.LOGO.is_file(), "config/marque/logo.png a disparu"

    def test_la_grille_de_prix_est_toujours_lisible(self):
        """Le renommage ne doit pas avoir coûté un seul article."""
        from agents.plaquiste.plaquiste_agent import charger_metier

        metier = charger_metier()
        articles = (metier.get("prix_materiaux") or {}) | (metier.get("prix_portes") or {})

        assert len(articles) >= 20, f"seulement {len(articles)} article(s) apres renommage"
