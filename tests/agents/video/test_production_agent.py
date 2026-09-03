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

import pytest

from agents.video.production_agent import VideoProductionAgent


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
