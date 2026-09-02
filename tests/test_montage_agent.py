"""L'agent de montage : ce qu'il refuse de faire quand il ne peut pas.

Ollama n'est pas sur cette machine (`docs/REGLES_DE_TRAVAIL.md`). Le modèle
est donc un double ici — mais un double qui rend ce qu'un vrai modèle rend :
de la prose autour du JSON, une opération inventée, parfois rien du tout.
"""
from pathlib import Path

import pytest

from agents.montage.montage_agent import MontageAgent
from apps.backend.routers.chat import EXTENSIONS_MONTABLES, medias_montables
from core.actions.resultat import echec, succes


class ModeleDouble:
    """Rend ce qu'on lui dit de rendre, ou se déclare éteint."""

    def __init__(self, reponse: str = "", disponible: bool = True):
        self.reponse, self.disponible, self.prompts = reponse, disponible, []

    async def is_available(self) -> bool:
        return self.disponible

    async def generate(self, prompt: str, **_) -> str:
        self.prompts.append(prompt)
        return self.reponse


class RegistreDouble:
    def __init__(self, resultat=None):
        self.resultat, self.appels = resultat, []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return self.resultat or succes(
            action=capacite, cible=connecteur, message="Timeline bâtie.",
            preuve="2000 ms sur 1 piste(s)", projet={"pistes": []}, erreurs=[])


@pytest.fixture
def rushes(tmp_path):
    video, logo = tmp_path / "chantier.mp4", tmp_path / "logo.png"
    video.write_bytes(b"x")
    logo.write_bytes(b"x")
    return [str(video), str(logo)]


PLAN = ('Voici :\n```json\n[{"operation": "creer_projet", "nom": "c", '
        '"largeur": 1080, "hauteur": 1920}, '
        '{"operation": "importer_media", "nom": "chantier"}]\n```')


class TestCeQuIlRefuseDeSimuler:
    @pytest.mark.asyncio
    async def test_sans_ollama_il_le_dit_et_ne_monte_rien(self, rushes):
        agent = MontageAgent(provider=ModeleDouble(disponible=False),
                             registre=RegistreDouble())
        r = await agent.run("monte la vidéo", context={"medias": rushes})
        assert r["status"] == "warning"
        assert "ollama serve" in r["response"]
        assert "operations" not in r

    @pytest.mark.asyncio
    async def test_sans_media_il_ne_va_pas_chercher_le_modele(self, tmp_path):
        modele = ModeleDouble(PLAN)
        r = await MontageAgent(provider=modele, registre=RegistreDouble()).run(
            "monte la vidéo", context={"medias": [str(tmp_path / "absent.mp4")]})
        assert r["status"] == "error"
        assert modele.prompts == [], "le modèle a été appelé sans rien à monter"

    @pytest.mark.asyncio
    async def test_une_reponse_sans_json_ne_devient_pas_un_montage_par_defaut(self, rushes):
        agent = MontageAgent(provider=ModeleDouble("Je préfère ne pas."),
                             registre=RegistreDouble())
        r = await agent.run("monte la vidéo", context={"medias": rushes})
        assert r["status"] == "error"
        assert "operations" not in r

    @pytest.mark.asyncio
    async def test_un_plan_qui_ne_compose_pas_est_un_echec_pas_un_succes(self, rushes):
        registre = RegistreDouble(echec(action="composer", cible="montage",
                                        message="Piste introuvable."))
        r = await MontageAgent(provider=ModeleDouble(PLAN), registre=registre).run(
            "monte la vidéo", context={"medias": rushes})
        assert r["status"] == "error"
        assert "Piste introuvable" in r["response"]


class TestLaChaine:
    @pytest.mark.asyncio
    async def test_une_phrase_devient_des_operations_composees_pour_de_vrai(self, rushes):
        registre = RegistreDouble()
        r = await MontageAgent(provider=ModeleDouble(PLAN), registre=registre).run(
            "monte la vidéo du chantier", context={"medias": rushes})

        assert r["status"] == "success"
        connecteur, capacite, parametres = registre.appels[0]
        assert (connecteur, capacite) == ("montage", "composer")
        assert parametres["operations"][1]["chemin"] == rushes[0], (
            "le chemin réel n'a pas été substitué au nom"
        )

    @pytest.mark.asyncio
    async def test_une_ligne_inventee_est_ecartee_sans_perdre_le_reste(self, rushes):
        reponse = ('[{"operation": "creer_projet", "nom": "c"}, '
                   '{"operation": "envoyer_par_mail", "a": "x@y.z"}]')
        r = await MontageAgent(provider=ModeleDouble(reponse),
                               registre=RegistreDouble()).run(
            "monte la vidéo", context={"medias": rushes})
        # `success` jusqu'au 01/09/2026 — et c'etait faux : une partie du plan
        # est tombee. Le reste tient toujours (ce n'est pas une erreur), la
        # ligne ecartee est nommee, et le statut le dit maintenant aussi.
        assert r["status"] == "warning"
        assert any("envoyer_par_mail" in e for e in r["lignes_ecartees"])
        assert "envoyer_par_mail" in r["response"], (
            "la ligne ecartee doit apparaitre dans le texte lu, pas seulement "
            "dans un champ que l'interface n'affiche pas"
        )

    @pytest.mark.asyncio
    async def test_un_plan_entierement_valide_reste_un_succes(self, rushes):
        """`warning` ne doit pas devenir le statut par defaut du montage."""
        r = await MontageAgent(provider=ModeleDouble(PLAN),
                               registre=RegistreDouble()).run(
            "monte la vidéo", context={"medias": rushes})

        assert r["status"] == "success"
        assert r["lignes_ecartees"] == []

    @pytest.mark.asyncio
    async def test_le_prompt_liste_ses_medias_par_leur_nom(self, rushes):
        modele = ModeleDouble(PLAN)
        await MontageAgent(provider=modele, registre=RegistreDouble()).run(
            "monte la vidéo", context={"medias": rushes})
        assert "- chantier" in modele.prompts[0] and "- logo" in modele.prompts[0]


class TestInventaireDuServeur:
    """L'inventaire est bâti côté serveur : c'est la moitié backend de la garantie."""

    def test_les_extensions_couvrent_ce_que_la_timeline_sait_poser(self):
        assert {".mp4", ".png", ".mp3"} <= EXTENSIONS_MONTABLES

    def test_seuls_les_dossiers_de_rushes_sont_lus(self, tmp_path, monkeypatch):
        import apps.backend.routers.chat as chat

        for dossier in ("source", "rendered"):
            (tmp_path / dossier).mkdir()
            (tmp_path / dossier / f"{dossier}.mp4").write_bytes(b"x")
        (tmp_path / "source" / "notes.txt").write_bytes(b"x")
        monkeypatch.setattr(chat, "MEDIA_DIR", tmp_path)

        # `Path(...).name`, pas `.rsplit("/", 1)` : `medias_montables()` rend
        # des chemins au format natif de l'OS — des antislashs sous Windows,
        # ou ce split ne coupait jamais rien et rendait le chemin entier.
        # Mesure le 01/09/2026 sur la machine du proprietaire, invisible sur
        # Linux.
        trouves = [Path(p).name for p in chat.medias_montables()]
        assert trouves == ["source.mp4"], (
            "un rendu remonté dans l'inventaire ferait boucler le montage sur lui-même"
        )

    def test_un_dossier_media_absent_ne_leve_pas(self, tmp_path, monkeypatch):
        import apps.backend.routers.chat as chat
        monkeypatch.setattr(chat, "MEDIA_DIR", tmp_path / "nulle-part")
        assert medias_montables() == []
