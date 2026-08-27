"""Les documents réels du propriétaire, retrouvés par la demande.

La grille de prix ne porte pas ses **formulations** : la façon dont il annonce
un geste commercial, explique la surface développée, liste ce qui n'est pas
inclus. Ces phrases sont dans ses devis.

Ces tests n'utilisent jamais ses vrais documents — ils portent le nom de son
client. Ils fabriquent leurs propres fichiers dans un dossier temporaire.
"""
from pathlib import Path

import pytest

from agents.plaquiste.archives import (
    Extrait,
    documents_disponibles,
    extraits_pour,
    formater,
)

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def archives(tmp_path) -> Path:
    (tmp_path / "devis_exemple.txt").write_text(
        "Objet du devis\n\n"
        "Fourniture et pose de 18 parois en plaques BA13 sur ossature metallique.\n\n"
        "Un geste commercial pour une collaboration durable : une remise de 5 % "
        "marque le debut de cette collaboration.\n\n"
        "Ne sont pas inclus : les travaux d'electricite, luminaires et bandeaux LED.\n",
        encoding="utf-8",
    )
    (tmp_path / "lettre_exemple.txt").write_text(
        "Madame, Monsieur,\n\nNous vous remercions sincerement pour la confiance "
        "que vous accordez a notre entreprise.\n",
        encoding="utf-8",
    )
    return tmp_path


class TestLectureDuDossier:
    def test_un_dossier_absent_ne_leve_pas(self, tmp_path):
        assert documents_disponibles(tmp_path / "nexiste_pas") == []

    def test_les_documents_sont_listes(self, archives):
        assert len(documents_disponibles(archives)) == 2

    def test_le_mode_d_emploi_n_est_pas_une_archive(self, archives):
        (archives / "LISEZ_MOI.md").write_text("mode d'emploi", encoding="utf-8")
        noms = [c.name for c in documents_disponibles(archives)]
        assert "LISEZ_MOI.md" not in noms

    def test_un_fichier_d_un_autre_type_est_ignore(self, archives):
        (archives / "photo.jpg").write_bytes(b"pas un document")
        assert len(documents_disponibles(archives)) == 2


class TestSelectionDesExtraits:
    def test_la_demande_ramene_le_passage_qui_en_parle(self, archives):
        extraits = extraits_pour("parle-moi du geste commercial", archives)

        assert extraits
        assert "geste commercial" in extraits[0].texte

    def test_le_passage_le_plus_proche_passe_devant(self, archives):
        extraits = extraits_pour("remise commerciale collaboration durable", archives)
        assert "remise" in extraits[0].texte.lower()

    def test_une_demande_hors_sujet_ne_ramene_rien(self, archives):
        """Mieux vaut ne rien citer que citer un passage sans rapport."""
        assert extraits_pour("recette de tiramisu au mascarpone", archives) == []

    def test_une_demande_vide_ne_ramene_rien(self, archives):
        assert extraits_pour("", archives) == []

    def test_la_provenance_accompagne_chaque_extrait(self, archives):
        extraits = extraits_pour("electricite luminaires", archives)

        assert extraits
        assert "devis_exemple.txt" in extraits[0].source

    def test_le_nombre_d_extraits_est_plafonne(self, archives):
        assert len(extraits_pour("devis parois entreprise confiance", archives, maximum=1)) == 1


class TestMiseEnForme:
    def test_sans_extrait_rien_n_est_ajoute(self):
        """`None` distingue « pas d'archive » de « une archive vide »."""
        assert formater([]) is None

    def test_les_extraits_sont_numerotes_avec_leur_source(self):
        texte = formater([Extrait("un passage", "devis.pdf, page 2", 3)])

        assert "[1]" in texte
        assert "devis.pdf, page 2" in texte
        assert "un passage" in texte

    def test_la_consigne_interdit_d_inventer_un_chiffre(self):
        texte = formater([Extrait("passage", "source", 1)])
        assert "N'invente aucun chiffre" in texte


class TestConfidentialite:
    """Ses documents portent le nom de son client, ses montants, son chantier."""

    def test_le_dossier_client_est_ignore_par_git(self):
        gitignore = (RACINE / ".gitignore").read_text(encoding="utf-8")
        assert "documents/unic_plaquiste/*" in gitignore

    def test_seul_le_mode_d_emploi_reste_versionnable(self):
        gitignore = (RACINE / ".gitignore").read_text(encoding="utf-8")
        assert "!documents/unic_plaquiste/LISEZ_MOI.md" in gitignore

    def test_aucun_document_client_n_est_dans_le_depot(self):
        """Le contrôle qui compte : rien de versionné dans ce dossier."""
        import subprocess

        suivis = subprocess.run(
            ["git", "ls-files", "documents/unic_plaquiste/"],
            cwd=RACINE, capture_output=True, text=True, check=False,
        ).stdout.split()

        assert suivis in ([], ["documents/unic_plaquiste/LISEZ_MOI.md"]), (
            f"document client versionne : {suivis}"
        )


class TestLAgentUtiliseVraimentLesArchives:
    """Un sabotage a montré que rien ne le prouvait : l'agent pouvait les ignorer
    sans qu'aucun test ne tombe. C'est ce que ces deux tests tiennent."""

    async def test_les_extraits_arrivent_dans_l_instruction_du_modele(self, monkeypatch, archives):
        import agents.plaquiste.plaquiste_agent as module
        from agents.plaquiste.plaquiste_agent import PlaquisteAgent, charger_metier

        monkeypatch.setattr(module, "extraits_pour", lambda demande: extraits_pour(demande, archives))

        class Double:
            systeme = None

            async def generate(self, prompt, system_prompt=None, **kw):
                Double.systeme = system_prompt
                return "ok"

        agent = PlaquisteAgent(provider=Double(), metier=charger_metier())
        res = await agent.run("parle du geste commercial")

        assert "geste commercial" in Double.systeme, "les archives n'atteignent pas le modele"
        assert res["extraits_archives"], "aucune provenance rapportee"

    async def test_sans_archive_l_agent_repond_quand_meme(self, monkeypatch, tmp_path):
        """Un dossier vide n'est pas une panne : la grille de prix suffit."""
        import agents.plaquiste.plaquiste_agent as module
        from agents.plaquiste.plaquiste_agent import PlaquisteAgent, charger_metier

        monkeypatch.setattr(module, "extraits_pour", lambda demande: extraits_pour(demande, tmp_path))

        class Double:
            async def generate(self, prompt, system_prompt=None, **kw):
                return "ok"

        agent = PlaquisteAgent(provider=Double(), metier=charger_metier())
        res = await agent.run("fais un devis")

        assert res["status"] == "success"
        assert res["extraits_archives"] == []
