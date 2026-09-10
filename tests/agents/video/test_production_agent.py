"""`VideoProductionAgent` — compose des capacites reelles sur un projet.

DEC-0037. Chaque collaborateur (vision, WanGP/MoneyPrinterTurbo, audio,
montage) est un DOUBLE ici : ses propres tests (test_vision.py,
test_video_analyzer.py, test_audio_agent.py, test_montage_agent.py)
verifient deja son comportement interne — ceux-ci verifient uniquement que
l'orchestrateur les compose correctement : le bon appel, dans le bon ordre,
avec les bonnes dependances, jamais un succes invente.
"""
import asyncio
import time
from pathlib import Path

import pytest

from agents.video.production_agent import VideoProductionAgent
from core.characters.registry import charger_personnage, creer_personnage


class ModeleDouble:
    """Rend un plan JSON scripte pour la planification — jamais la reponse
    finale d'un chat : cet agent ne redige aucun texte libre, seulement un
    graphe."""

    def __init__(self, reponses=None, disponible=True):
        self._reponses = list(reponses or ["[]"])
        self._disponible = disponible
        self.prompts = []

    async def is_available(self) -> bool:
        return self._disponible

    async def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        if len(self._reponses) > 1:
            return self._reponses.pop(0)
        return self._reponses[0]


class ProviderVisionDouble:
    def __init__(self, reponse="Une photo de chantier.", erreur=None, delai=0.0):
        self.appels = []
        self._reponse = reponse
        self._erreur = erreur
        self._delai = delai

    async def generate(self, prompt, images=None, **kw):
        self.appels.append({"prompt": prompt, "images": images})
        if self._delai:
            await asyncio.sleep(self._delai)
        if self._erreur is not None:
            raise self._erreur
        return self._reponse


class VideoAnalyzerDouble:
    """`planifier_scene`/`fabriquer` sont SYNCHRONES sur le vrai agent
    (`agents/video_analyzer/video_analyzer_agent.py`) — pas de `await` ici."""

    def __init__(self, reponse_scene=None, reponse_sujet=None):
        self.appels_scene = []
        self.appels_sujet = []
        self._reponse_scene = reponse_scene or {
            "statut": "NEEDS_CONFIRMATION", "message": "pret, en attente"}
        self._reponse_sujet = reponse_sujet or {
            "statut": "NEEDS_CONFIRMATION", "message": "pret, en attente"}

    def planifier_scene(self, description):
        self.appels_scene.append(description)
        return self._reponse_scene

    def fabriquer(self, sujet):
        self.appels_sujet.append(sujet)
        return self._reponse_sujet


class AudioAgentDouble:
    def __init__(self, reponse=None):
        self.appels = []
        self._reponse = reponse or {"status": "success", "response": "ok"}

    async def run(self, user_input, context=None):
        self.appels.append((user_input, context))
        return self._reponse


class MontageAgentDouble:
    def __init__(self, reponse=None):
        self.appels = []
        self._reponse = reponse or {"status": "success", "response": "monte"}

    async def run(self, demande, context=None):
        self.appels.append((demande, context))
        return self._reponse


class RegistreXaarDouble:
    def __init__(self, reponse=None):
        self.appels = []
        self._reponse = reponse or {
            "statut": "SUCCESS",
            "message": "Xaar termine",
            "output": "sortie_xaar.jpg",
        }

    async def executer(self, connecteur, capacite, **parametres):
        self.appels.append({
            "connecteur": connecteur,
            "capacite": capacite,
            "parametres": parametres,
        })
        return self._reponse


@pytest.fixture
def reference(tmp_path):
    fichier = tmp_path / "chantier.jpg"
    fichier.write_bytes(b"\xff\xd8\xff\xe0donnees-image-factices")
    return str(fichier)


class TestPlanRefuse:
    async def test_une_capacite_hors_liste_refuse_le_plan(self):
        modele = ModeleDouble(['[{"id": "a", "capacite": "capacite_inexistante"}]'])
        agent = VideoProductionAgent(provider=modele)

        resultat = await agent.run("fabrique une video")

        assert resultat["status"] == "error"
        assert "ne tient pas" in resultat["response"]

    async def test_un_plan_vide_refuse(self):
        modele = ModeleDouble(["[]"])
        agent = VideoProductionAgent(provider=modele)

        resultat = await agent.run("fabrique une video")

        assert resultat["status"] == "error"

    async def test_sans_modele_disponible_rien_n_est_tente(self):
        modele = ModeleDouble(disponible=False)
        agent = VideoProductionAgent(provider=modele)

        resultat = await agent.run("fabrique une video")

        assert resultat["status"] == "warning"
        assert modele.prompts == []

    async def test_une_capacite_inconnue_en_mode_team_refuse_avant_le_modele(self):
        modele = ModeleDouble()
        agent = VideoProductionAgent(provider=modele)

        resultat = await agent.run("fabrique une video",
                                   context={"capacites": ["capacite_inexistante"]})

        assert resultat["status"] == "error"
        assert modele.prompts == []


class TestUneSeuleCapacite:
    async def test_vision_seule(self, reference):
        modele = ModeleDouble(['[{"id": "lire", "capacite": "vision", '
                              '"parametres": {"reference": 0}}]'])
        vision = ProviderVisionDouble(reponse="Une dalle en beton, non finie.")
        agent = VideoProductionAgent(provider=modele, provider_vision=vision)

        resultat = await agent.run("que montre cette photo ?",
                                   context={"references": [reference]})

        assert resultat["status"] == "success"
        assert vision.appels[0]["images"] == [
            __import__("base64").b64encode(open(reference, "rb").read()).decode("ascii")]
        assert resultat["projet"]["resultat"]["aboutie"] is True

    async def test_vision_sans_collaborateur_branche_echoue_honnetement(self, reference):
        modele = ModeleDouble(['[{"id": "lire", "capacite": "vision"}]'])
        agent = VideoProductionAgent(provider=modele)  # provider_vision=None

        resultat = await agent.run("decris", context={"references": [reference]})

        assert resultat["status"] == "warning"
        trace = resultat["projet"]["resultat"]["etapes"][0]
        assert trace["etat"] == "FAILED"
        assert "aucun modele de vision" in trace["raison"]

    async def test_wangp_seul_soumet_pour_confirmation_jamais_un_succes_invente(self):
        modele = ModeleDouble(['[{"id": "scene", "capacite": "wangp", '
                              '"parametres": {"description": "un chantier au lever du jour"}}]'])
        analyzer = VideoAnalyzerDouble()
        agent = VideoProductionAgent(provider=modele, video_analyzer_agent=analyzer)

        resultat = await agent.run("genere une scene")

        assert analyzer.appels_scene == ["un chantier au lever du jour"]
        assert resultat["status"] == "success"
        # Soumis, pas fini : aucun artefact final n'est invente.
        assert resultat["projet"]["artefact_final"] is None

    async def test_montage_seul(self, reference):
        modele = ModeleDouble(['[{"id": "assembler", "capacite": "montage", '
                              '"parametres": {"references": [0]}}]'])
        montage = MontageAgentDouble(
            reponse={"status": "success", "response": "monte", "preuve": reference})
        agent = VideoProductionAgent(provider=modele, montage_agent=montage)

        resultat = await agent.run("assemble", context={"references": [reference]})

        assert montage.appels[0][1]["medias"] == [reference]
        assert resultat["projet"]["artefact_final"] == reference


class TestMultiCapacites:
    async def test_vision_puis_montage_respecte_la_dependance(self, reference):
        modele = ModeleDouble([
            '[{"id": "lire", "capacite": "vision", "parametres": {"reference": 0}},'
            ' {"id": "assembler", "capacite": "montage", "depend_de": ["lire"], '
            '"parametres": {"references": [0]}}]'
        ])
        vision = ProviderVisionDouble()
        montage = MontageAgentDouble(
            reponse={"status": "success", "response": "monte", "preuve": reference})
        agent = VideoProductionAgent(provider=modele, provider_vision=vision,
                                     montage_agent=montage)

        resultat = await agent.run("analyse puis assemble",
                                   context={"references": [reference]})

        assert resultat["status"] == "success"
        etapes = {e["etape"]: e["etat"] for e in resultat["projet"]["resultat"]["etapes"]}
        assert etapes == {"lire": "DONE", "assembler": "DONE"}

    async def test_une_dependance_manquante_arrete_le_montage(self, reference):
        """`lire` echoue (pas de provider_vision) -> `assembler` n'est jamais lance."""
        modele = ModeleDouble([
            '[{"id": "lire", "capacite": "vision"},'
            ' {"id": "assembler", "capacite": "montage", "depend_de": ["lire"]}]'
        ])
        montage = MontageAgentDouble()
        agent = VideoProductionAgent(provider=modele, montage_agent=montage)

        resultat = await agent.run("analyse puis assemble",
                                   context={"references": [reference]})

        assert montage.appels == []
        etapes = {e["etape"]: e["etat"] for e in resultat["projet"]["resultat"]["etapes"]}
        assert etapes["lire"] == "FAILED"
        assert etapes["assembler"] in ("FAILED", "NOT_REACHED")

    async def test_deux_capacites_independantes_tournent_en_parallele(self, reference):
        modele = ModeleDouble([
            '[{"id": "lire1", "capacite": "vision", "parametres": {"reference": 0}},'
            ' {"id": "ecoute", "capacite": "transcription", "parametres": {"reference": 0}}]'
        ])
        vision = ProviderVisionDouble(delai=0.08)
        audio = AudioAgentDouble()
        agent = VideoProductionAgent(provider=modele, provider_vision=vision,
                                     audio_agent=audio)
        # `_reference` exige une extension audio/video pour la transcription ;
        # le fichier de test est un .jpg -- on force le nom via une deuxieme
        # reference plutot que de faire semblant que l'image est ecoutable.
        video = str(reference).replace(".jpg", ".mp4")
        __import__("shutil").copy(reference, video)

        depart = time.perf_counter()
        resultat = await agent.run(
            "analyse et transcris",
            context={"references": [reference, video],
                     "capacites": ["vision", "transcription"]})
        duree = time.perf_counter() - depart

        assert resultat["status"] == "success"
        assert duree < 0.15, "les deux etapes independantes ont tourne en sequentiel"


class TestModeTeam:
    async def test_le_mode_team_restreint_les_capacites_proposees_au_modele(self):
        modele = ModeleDouble(['[{"id": "a", "capacite": "vision"}]'])
        agent = VideoProductionAgent(provider=modele, provider_vision=ProviderVisionDouble())

        await agent.run("fais quelque chose", context={"capacites": ["vision"]})

        bloc_capacites = modele.prompts[0].split("Capacites autorisees")[1].split(
            "N'utilise")[0]
        assert "vision" in bloc_capacites
        assert "moneyprinter" not in bloc_capacites

    async def test_le_mode_team_appelle_bien_uniquement_le_sous_ensemble(self, reference):
        modele = ModeleDouble(['[{"id": "a", "capacite": "vision", '
                              '"parametres": {"reference": 0}}]'])
        vision = ProviderVisionDouble()
        montage = MontageAgentDouble()
        agent = VideoProductionAgent(provider=modele, provider_vision=vision,
                                     montage_agent=montage)

        resultat = await agent.run(
            "analyse", context={"references": [reference], "capacites": ["vision"]})

        assert resultat["status"] == "success"
        assert montage.appels == []


class TestRessourceGpuPartagee:
    async def test_deux_etapes_vision_ne_tournent_pas_en_meme_temps(self, reference):
        modele = ModeleDouble([
            '[{"id": "a", "capacite": "vision", "parametres": {"reference": 0}},'
            ' {"id": "b", "capacite": "vision", "parametres": {"reference": 0}}]'
        ])
        vision = ProviderVisionDouble(delai=0.08)
        agent = VideoProductionAgent(provider=modele, provider_vision=vision)

        depart = time.perf_counter()
        await agent.run("deux analyses", context={"references": [reference]})
        duree = time.perf_counter() - depart

        assert duree >= 0.15, "deux etapes vision (GPU local) ont tourne en meme temps"

class TestXaarKaname:
    async def test_xaar_kaname_transmet_les_references_au_registre(self, tmp_path):
        source = tmp_path / "source.jpg"
        cible = tmp_path / "cible.jpg"
        source.write_bytes(b"source")
        cible.write_bytes(b"cible")

        modele = ModeleDouble([
            '[{"id": "xaar", "capacite": "xaar_kaname", '
            '"parametres": {"source_reference": 0, "target_reference": 1}}]'
        ])
        registre = RegistreXaarDouble()

        agent = VideoProductionAgent(
            provider=modele,
            registre=registre,
        )

        resultat = await agent.run(
            "traite la cible avec la source",
            context={"references": [str(source), str(cible)]},
        )

        assert resultat["status"] == "success"
        assert len(registre.appels) == 1

        appel = registre.appels[0]
        assert appel["connecteur"] == "xaar_kaname"
        assert appel["capacite"] == "traiter"
        assert appel["parametres"]["source"] == str(source.resolve())
        assert appel["parametres"]["target"] == str(cible.resolve())
        assert appel["parametres"]["many_faces"] is False
    async def test_xaar_kaname_produit_un_artefact_final(self, tmp_path):
        source = tmp_path / "source.jpg"
        cible = tmp_path / "cible.jpg"
        sortie = tmp_path / "sortie_xaar.jpg"
        source.write_bytes(b"source")
        cible.write_bytes(b"cible")
        sortie.write_bytes(b"resultat-xaar")

        modele = ModeleDouble([
            '[{"id": "xaar", "capacite": "xaar_kaname", '
            '"parametres": {"source_reference": 0, "target_reference": 1}}]'
        ])
        registre = RegistreXaarDouble(reponse={
            "statut": "SUCCESS",
            "message": "Xaar termine",
            "preuve": str(sortie),
            "output": str(sortie),
        })

        agent = VideoProductionAgent(
            provider=modele,
            registre=registre,
        )

        resultat = await agent.run(
            "traite la cible avec la source",
            context={"references": [str(source), str(cible)]},
        )

        assert resultat["status"] == "success"
        assert resultat["projet"]["artefact_final"] == str(sortie)

    async def test_xaar_kaname_donne_au_moteur_des_chemins_absolus(self, tmp_path, monkeypatch):
        """Le moteur tourne dans SON dossier, pas dans celui d'ARENA.

        Les deux tests au-dessus passent des references deja absolues
        (`tmp_path`), donc ils ne peuvent pas voir ce probleme-la. Une
        reference relative arrivee d'un plan ou d'une PWA designerait, une
        fois rendue au moteur, un fichier d'un autre dossier — ou aucun. Le
        moteur echouerait alors sur du vide, sans que rien ici ne le dise.
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / "source.jpg").write_bytes(b"source")
        (tmp_path / "cible.jpg").write_bytes(b"cible")

        modele = ModeleDouble([
            '[{"id": "xaar", "capacite": "xaar_kaname", '
            '"parametres": {"source_reference": 0, "target_reference": 1}}]'
        ])
        registre = RegistreXaarDouble()

        agent = VideoProductionAgent(provider=modele, registre=registre)

        await agent.run(
            "traite la cible avec la source",
            context={"references": ["source.jpg", "cible.jpg"]},
        )

        parametres = registre.appels[0]["parametres"]
        for cle in ("source", "target"):
            assert Path(parametres[cle]).is_absolute(), (
                f"{cle} part en relatif : le moteur le lirait depuis son "
                "propre dossier, donc a cote du bon fichier")
            assert Path(parametres[cle]).is_file()


class TestKrillinAI:
    """DEC-0049 : traduction/doublage d'une video EXISTANTE — jamais un
    index de reference pour tts/render (le fichier n'existe qu'apres
    confirmation d'une etape anterieure), jamais voice_clone_source."""

    async def test_krillin_subtitle_resout_la_reference_et_transmet_les_langues(self, reference):
        modele = ModeleDouble([
            '[{"id": "s", "capacite": "krillin_subtitle", '
            '"parametres": {"reference": 0, "langue_origine": "en", '
            '"langue_cible": "fr", "caption_source": "manual"}}]'
        ])
        registre = RegistreXaarDouble(reponse={"statut": "SUCCESS", "message": "ok",
                                               "preuve": "srt.srt"})

        agent = VideoProductionAgent(provider=modele, registre=registre)
        resultat = await agent.run("sous-titre en francais", context={"references": [reference]})

        assert resultat["status"] == "success"
        appel = registre.appels[0]
        assert appel["connecteur"] == "krillinai"
        assert appel["capacite"] == "subtitle"
        assert appel["parametres"]["entree"] == reference
        assert appel["parametres"]["langue_origine"] == "en"
        assert appel["parametres"]["langue_cible"] == "fr"

    async def test_krillin_tts_prend_un_chemin_deja_confirme_jamais_un_index(self):
        modele = ModeleDouble([
            '[{"id": "t", "capacite": "krillin_tts", '
            '"parametres": {"srt_cible": "/chantier/target.srt"}}]'
        ])
        registre = RegistreXaarDouble(reponse={"statut": "SUCCESS", "message": "ok",
                                               "preuve": "audio.wav"})

        agent = VideoProductionAgent(provider=modele, registre=registre)
        resultat = await agent.run("double la video", context={"references": []})

        assert resultat["status"] == "success"
        appel = registre.appels[0]
        assert appel["capacite"] == "tts"
        assert appel["parametres"]["srt_cible"] == "/chantier/target.srt"

    async def test_krillin_tts_ne_transmet_jamais_voice_clone_source_meme_fourni(self):
        modele = ModeleDouble([
            '[{"id": "t", "capacite": "krillin_tts", '
            '"parametres": {"srt_cible": "/x.srt", '
            '"voice_clone_source": "/une-voix-a-cloner.wav"}}]'
        ])
        registre = RegistreXaarDouble(reponse={"statut": "SUCCESS", "message": "ok",
                                               "preuve": "audio.wav"})

        agent = VideoProductionAgent(provider=modele, registre=registre)
        await agent.run("double la video", context={"references": []})

        assert "voice_clone_source" not in registre.appels[0]["parametres"]

    async def test_krillin_render_horizontal_devient_l_artefact_final(self, tmp_path):
        sortie = tmp_path / "horizontal_bilingual.mp4"
        sortie.write_bytes(b"video finale")
        modele = ModeleDouble([
            '[{"id": "r", "capacite": "krillin_render_horizontal", '
            '"parametres": {"video": "/chantier/in.mp4", "sous_titres": "/chantier/cible.srt"}}]'
        ])
        registre = RegistreXaarDouble(reponse={"statut": "SUCCESS", "message": "ok",
                                               "preuve": str(sortie)})

        agent = VideoProductionAgent(provider=modele, registre=registre)
        resultat = await agent.run("rendu horizontal", context={"references": []})

        assert resultat["status"] == "success"
        assert resultat["projet"]["artefact_final"] == str(sortie)

    async def test_krillin_sans_registre_echoue_honnetement(self):
        modele = ModeleDouble([
            '[{"id": "c", "capacite": "krillin_cover", "parametres": {"prompt": "un logo"}}]'
        ])
        agent = VideoProductionAgent(provider=modele, registre=None)
        resultat = await agent.run("genere une couverture", context={"references": []})
        assert resultat["status"] == "warning"


SCHEMA_TIMELINE = {"tools": [
    {"name": "split_on_beats",
     "inputSchema": {"properties": {"clip_id": {"type": "string"}}, "required": ["clip_id"]}},
    {"name": "place_clip",
     "inputSchema": {"properties": {"path": {"type": "string"}, "track": {"type": "string"}},
                     "required": ["path", "track"]}},
]}


class RegistreDriftDouble:
    """Un serveur Drift de test : `boite_a_outils` ne rend un schema QUE
    pour les toolboxes fournies — les neuf autres echouent, comme un vrai
    Drift qui n'a que « timeline » a offrir dans ce scenario."""

    def __init__(self, toolboxes=None, reponse_appliquer=None, echoue_catalogue=False):
        self.appels = []
        self._toolboxes = toolboxes if toolboxes is not None else {"timeline": SCHEMA_TIMELINE}
        self._reponse_appliquer = reponse_appliquer or {
            "statut": "SUCCESS", "message": "ok",
            "preuve": "apply : 1 opération(s) appliquée(s)", "detail": {"donnees": {}},
        }
        self._echoue_catalogue = echoue_catalogue

    async def executer(self, connecteur, capacite, **parametres):
        self.appels.append({"connecteur": connecteur, "capacite": capacite, "parametres": parametres})
        if capacite == "catalogue":
            if self._echoue_catalogue:
                return {"statut": "NOT_CONFIGURED", "message": "Drift absent"}
            return {"statut": "SUCCESS", "message": "catalog", "preuve": "catalog"}
        if capacite == "boite_a_outils":
            schema = self._toolboxes.get(parametres.get("name"))
            if schema is None:
                return {"statut": "FAILED", "message": "toolbox absente"}
            return {"statut": "SUCCESS", "message": "toolbox",
                    "preuve": parametres.get("name"), "detail": {"donnees": schema}}
        if capacite == "appliquer":
            return self._reponse_appliquer
        return {"statut": "FAILED", "message": f"capacite inconnue {capacite}"}


class TestDrift:
    """DEC-0057 : Drift, jamais pilote en direct — le texte du modele
    devient une liste d'operations validee contre le VRAI schema recu."""

    async def test_drift_via_le_graphe_video_complet(self, reference):
        modele = ModeleDouble([
            '[{"id": "d", "capacite": "drift", '
            '"parametres": {"demande": "coupe les silences", "references": [0]}}]',
            '[{"toolbox": "timeline", "operation": "split_on_beats", '
            '"parametres": {"clip_id": "c1"}}]',
        ])
        registre = RegistreDriftDouble()
        agent = VideoProductionAgent(provider=modele, registre=registre)

        resultat = await agent.run(
            "coupe les silences de cette video", context={"references": [reference]})

        assert resultat["status"] == "success", resultat["response"]
        capacites_appelees = [a["capacite"] for a in registre.appels]
        # catalogue, puis une boite_a_outils par toolbox fermee (10), puis appliquer.
        assert capacites_appelees[0] == "catalogue"
        assert capacites_appelees.count("boite_a_outils") == 10
        assert capacites_appelees[-1] == "appliquer"
        appel_appliquer = registre.appels[-1]
        assert appel_appliquer["parametres"]["ops"] == [
            {"toolbox": "timeline", "op": "split_on_beats", "params": {"clip_id": "c1"}}]

    async def test_drift_ne_montre_jamais_un_chemin_au_modele(self, reference):
        modele = ModeleDouble([
            '[{"id": "d", "capacite": "drift", '
            '"parametres": {"demande": "monte cette video", "references": [0]}}]',
            '[{"toolbox": "timeline", "operation": "split_on_beats", '
            '"parametres": {"clip_id": "c1"}}]',
        ])
        registre = RegistreDriftDouble()
        agent = VideoProductionAgent(provider=modele, registre=registre)

        await agent.run("monte cette video", context={"references": [reference]})

        prompt_drift = modele.prompts[-1]
        assert reference not in prompt_drift
        assert Path(reference).stem in prompt_drift

    async def test_drift_refuse_une_operation_hors_du_vrai_schema(self, reference):
        modele = ModeleDouble([
            '[{"id": "d", "capacite": "drift", '
            '"parametres": {"demande": "fais un truc impossible", "references": [0]}}]',
            '[{"toolbox": "timeline", "operation": "operation_inventee", "parametres": {}}]',
        ])
        registre = RegistreDriftDouble()
        agent = VideoProductionAgent(provider=modele, registre=registre)

        resultat = await agent.run("fais un truc impossible", context={"references": [reference]})

        assert resultat["status"] == "warning"
        capacites_appelees = [a["capacite"] for a in registre.appels]
        assert "appliquer" not in capacites_appelees, "un plan refuse n'atteint jamais Drift"

    async def test_drift_sans_registre_echoue_honnetement(self, reference):
        modele = ModeleDouble([
            '[{"id": "d", "capacite": "drift", '
            '"parametres": {"demande": "coupe les silences", "references": [0]}}]',
        ])
        agent = VideoProductionAgent(provider=modele, registre=None)

        resultat = await agent.run("coupe les silences", context={"references": [reference]})

        assert resultat["status"] == "warning"

    async def test_drift_sans_demande_echoue_honnetement(self, reference):
        modele = ModeleDouble([
            '[{"id": "d", "capacite": "drift", "parametres": {"references": [0]}}]',
        ])
        registre = RegistreDriftDouble()
        agent = VideoProductionAgent(provider=modele, registre=registre)

        resultat = await agent.run("coupe", context={"references": [reference]})

        assert resultat["status"] == "warning"
        assert registre.appels == []

    async def test_drift_indisponible_echoue_avant_tout_plan(self, reference):
        modele = ModeleDouble([
            '[{"id": "d", "capacite": "drift", '
            '"parametres": {"demande": "coupe les silences", "references": [0]}}]',
        ])
        registre = RegistreDriftDouble(echoue_catalogue=True)
        agent = VideoProductionAgent(provider=modele, registre=registre)

        resultat = await agent.run("coupe les silences", context={"references": [reference]})

        assert resultat["status"] == "warning"
        capacites_appelees = [a["capacite"] for a in registre.appels]
        assert capacites_appelees == ["catalogue"]

    async def test_smoke_drift_jusqu_a_un_fichier_reel_exporte(self, tmp_path):
        """Smoke test reel (mission Drift, 06/09/2026) : de la demande en
        langage naturel jusqu'a un fichier EXPORTE qui existe reellement sur
        le disque — le meme contrat que `_artefact_final` pour montage/
        xaar_kaname/krillin_render_*."""
        video_source = tmp_path / "chantier-avant.mp4"
        video_source.write_bytes(b"\x00\x00\x00\x18ftypmp42-source-avant")
        export = tmp_path / "chantier-avant-apres.mp4"
        export.write_bytes(b"\x00\x00\x00\x18ftypmp42-export-reel")

        schema_export = {"tools": [
            {"name": "export_video",
             "inputSchema": {"properties": {"format": {"type": "string"}}, "required": []}},
        ]}
        registre = RegistreDriftDouble(
            toolboxes={"timeline": schema_export},
            reponse_appliquer={
                "statut": "SUCCESS", "message": "export termine",
                "preuve": "apply : 1 opération(s) appliquée(s)",
                "detail": {"donnees": {"results": [{"op": "export_video",
                                                     "output_path": str(export)}]}},
            },
        )
        modele = ModeleDouble([
            '[{"id": "d", "capacite": "drift", '
            '"parametres": {"demande": "exporte la video finale", "references": [0]}}]',
            '[{"toolbox": "timeline", "operation": "export_video", "parametres": {"format": "mp4"}}]',
        ])
        agent = VideoProductionAgent(provider=modele, registre=registre)

        resultat = await agent.run(
            "prepare et exporte la video finale", context={"references": [str(video_source)]})

        assert resultat["status"] == "success", resultat["response"]
        assert resultat["projet"]["artefact_final"] == str(export)
        assert Path(resultat["projet"]["artefact_final"]).is_file()
        assert Path(resultat["projet"]["artefact_final"]).read_bytes().startswith(b"\x00\x00\x00\x18ftyp")


class TestNarrationConversationnelle:
    """Mission Sesame CSM, DEC-0080 : `conversationnel` bascule vers
    `AudioAgent._dialogue`, sans rien changer pour un plan qui ne le demande
    pas (voir `test_la_narration_video_passe_par_la_meme_porte` dans
    `tests/test_audio_agent.py` pour le chemin par defaut, inchange)."""

    @pytest.mark.asyncio
    async def test_sans_conversationnel_le_contexte_ne_change_pas(self):
        audio = AudioAgentDouble()
        agent = VideoProductionAgent(provider=ModeleDouble(), audio_agent=audio)

        await agent._appeler_narration({"texte": "Chantier Ouakam", "langue": "fr"})

        _, contexte = audio.appels[0]
        assert "conversationnel" not in contexte
        assert contexte["langue"] == "fr"

    @pytest.mark.asyncio
    async def test_conversationnel_est_transmis_et_defaut_a_l_anglais(self):
        audio = AudioAgentDouble()
        agent = VideoProductionAgent(provider=ModeleDouble(), audio_agent=audio)

        await agent._appeler_narration({"texte": "Hello.", "conversationnel": True})

        _, contexte = audio.appels[0]
        assert contexte["conversationnel"] is True
        assert contexte["langue"] == "en"

    @pytest.mark.asyncio
    async def test_conversation_et_speaker_sont_transmis_quand_fournis(self):
        audio = AudioAgentDouble()
        agent = VideoProductionAgent(provider=ModeleDouble(), audio_agent=audio)

        tours = [{"texte": "Hi", "speaker": 0}]
        await agent._appeler_narration({
            "texte": "Hello back.", "conversationnel": True,
            "conversation": tours, "speaker": 1})

        _, contexte = audio.appels[0]
        assert contexte["conversation"] == tours
        assert contexte["speaker"] == 1

    @pytest.mark.asyncio
    async def test_sans_texte_de_narration_echoue_meme_en_conversationnel(self):
        audio = AudioAgentDouble()
        agent = VideoProductionAgent(provider=ModeleDouble(), audio_agent=audio)

        with pytest.raises(RuntimeError):
            await agent._appeler_narration({"conversationnel": True})


class TestPersonnage:
    """Mission ARENA x AGENT HEROES (DEC-0084) : un `personnage_id` connu
    enrichit le graphe existant, il n'en cree jamais un second."""

    @pytest.fixture
    def personnage(self, tmp_path, monkeypatch):
        image = tmp_path / "visage.jpg"
        image.write_bytes(b"visage")
        dossier = tmp_path / "personnages"
        cree = creer_personnage(
            "Aissatou", "Presentatrice", [str(image)],
            "femme senegalaise, la trentaine, boubou bleu", dossier=dossier)

        import agents.video.production_agent as module
        from core.characters.registry import enregistrer_generation
        monkeypatch.setattr(
            module, "charger_personnage",
            lambda identifiant: charger_personnage(identifiant, dossier=dossier))
        monkeypatch.setattr(
            module, "enregistrer_generation",
            lambda personnage, *a, **k: enregistrer_generation(personnage, *a, dossier=dossier, **k))
        return cree

    async def test_personnage_inconnu_est_refuse_avant_tout_appel_modele(self):
        modele = ModeleDouble()
        agent = VideoProductionAgent(provider=modele)

        resultat = await agent.run("fais une scene", context={"personnage_id": "n-existe-pas"})

        assert resultat["status"] == "error"
        assert "inconnu" in resultat["response"].lower()
        assert modele.prompts == []

    async def test_les_images_du_personnage_rejoignent_les_references(self, personnage):
        modele = ModeleDouble(["[]"])
        agent = VideoProductionAgent(provider=modele)

        await agent.run("fais une scene", context={"personnage_id": personnage.identifiant})

        assert "ref0" in modele.prompts[0]

    async def test_le_profil_enrichit_le_prompt_sans_changer_l_objectif_rapporte(self, personnage):
        modele = ModeleDouble(['[{"id": "scene", "capacite": "wangp", '
                              '"parametres": {"description": "x"}}]'])
        analyzer = VideoAnalyzerDouble()
        agent = VideoProductionAgent(provider=modele, video_analyzer_agent=analyzer)

        resultat = await agent.run(
            "filme le personnage au marche", context={"personnage_id": personnage.identifiant})

        assert "boubou bleu" in modele.prompts[0]
        assert resultat["projet"]["objectif"] == "filme le personnage au marche"

    async def test_generer_image_personnage_compose_le_prompt(self, personnage):
        analyzer = VideoAnalyzerDouble()
        agent = VideoProductionAgent(provider=ModeleDouble(), video_analyzer_agent=analyzer)

        resultat = await agent.generer_image_personnage(personnage.identifiant, "marche au soleil")

        assert "boubou bleu" in analyzer.appels_scene[0]
        assert "marche au soleil" in analyzer.appels_scene[0]
        assert resultat["personnage_id"] == personnage.identifiant

    async def test_generer_image_personnage_inconnu_est_refuse(self):
        agent = VideoProductionAgent(provider=ModeleDouble())

        resultat = await agent.generer_image_personnage("n-existe-pas", "scene")

        assert resultat["status"] == "error"

    async def test_appliquer_identite_personnage_enregistre_la_provenance(self, personnage, tmp_path):
        cible = tmp_path / "scene_generee.jpg"
        cible.write_bytes(b"scene")
        sortie = tmp_path / "sortie.jpg"
        sortie.write_bytes(b"resultat")
        registre = RegistreXaarDouble(reponse={
            "statut": "SUCCESS", "message": "ok", "preuve": str(sortie), "output": str(sortie)})
        agent = VideoProductionAgent(provider=ModeleDouble(), registre=registre)

        resultat = await agent.appliquer_identite_personnage(personnage.identifiant, str(cible))

        assert resultat["statut"] == "SUCCESS"
        # Provenance reellement ecrite sur le disque, relue independamment
        # de l'objet garde en memoire par ce test.
        relu = charger_personnage(personnage.identifiant, dossier=tmp_path / "personnages")
        assert len(relu.historique) == 1
        assert relu.historique[0]["fichier"] == str(sortie)
        assert relu.historique[0]["moteur"] == "xaar_kaname"

    async def test_appliquer_identite_sans_fichier_produit_n_enregistre_rien(self, personnage, tmp_path):
        """Jamais de provenance sur un echec — mission §5 : la provenance
        n'existe que pour ce qui a reellement ete produit."""
        registre = RegistreXaarDouble(reponse={"statut": "FAILED", "message": "echec moteur"})
        agent = VideoProductionAgent(provider=ModeleDouble(), registre=registre)

        cible = tmp_path / "scene_generee.jpg"
        cible.write_bytes(b"scene")
        await agent.appliquer_identite_personnage(personnage.identifiant, str(cible))

        relu = charger_personnage(personnage.identifiant, dossier=tmp_path / "personnages")
        assert relu.historique == ()

    async def test_appliquer_identite_personnage_inconnu_est_refuse(self, tmp_path):
        agent = VideoProductionAgent(provider=ModeleDouble(), registre=RegistreXaarDouble())

        resultat = await agent.appliquer_identite_personnage(
            "n-existe-pas", str(tmp_path / "x.jpg"))

        assert resultat["status"] == "error"
