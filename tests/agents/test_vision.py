"""VisionAgent : une image se decrit, elle ne s'invente jamais (DEC-0019).

Rien n'appelle Ollama : le fournisseur est le double du socle
(`tests/conftest.py`), le depot de pieces jointes est reel mais jetable.
"""
import httpx
import pytest

from agents.vision.vision_agent import (
    QUESTION_PAR_DEFAUT,
    VisionAgent,
    demande_metadonnees_techniques,
    demande_securite_chantier,
)
from apps.backend.pieces_jointes import DepotPiecesJointes
from core.actions.resultat import echec, non_configure, succes

OCTETS_IMAGE = b"\x89PNG\r\n\x1a\n" + b"faux-png-mais-suffit-pour-le-test"


@pytest.fixture
def depot():
    return DepotPiecesJointes()


class TestSansImage:
    async def test_sans_piece_jointe_l_agent_le_dit(self, fake_provider):
        agent = VisionAgent(provider=fake_provider, pieces_jointes=DepotPiecesJointes())

        reponse = await agent.run("Que vois-tu ?", context={"attachments": []})

        assert reponse["status"] == "error"
        assert "aucune image" in reponse["response"].lower()
        assert fake_provider.appels == []

    async def test_une_piece_jointe_texte_ne_compte_pas_comme_image(self, fake_provider, depot):
        piece = depot.deposer("devis.txt", b"486 m2 de BA13")
        agent = VisionAgent(provider=fake_provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "error"
        assert fake_provider.appels == []

    async def test_sans_depot_de_pieces_jointes_rien_ne_part(self, fake_provider):
        agent = VisionAgent(provider=fake_provider, pieces_jointes=None)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": ["peu-importe"]})

        assert reponse["status"] == "error"
        assert fake_provider.appels == []

    async def test_un_identifiant_inconnu_est_ignore_pas_invente(self, fake_provider, depot):
        agent = VisionAgent(provider=fake_provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": ["jamais-depose"]})

        assert reponse["status"] == "error"
        assert fake_provider.appels == []


class TestAvecImage:
    async def test_l_image_part_vers_le_modele(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Un mur en BA13, non fini.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "success"
        assert reponse["response"] == "Un mur en BA13, non fini."
        assert provider.appels[0]["images"] == [piece.image_base64]
        assert reponse["images_analysees"] == ["chantier.jpg"]

    async def test_la_question_par_defaut_sert_sans_texte(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        await agent.run("", context={"attachments": [piece.identifiant]})

        assert QUESTION_PAR_DEFAUT in provider.appels[0]["prompt"]

    async def test_le_rappel_donnee_accompagne_toujours_le_prompt(self, provider_factory, depot):
        """Une consigne ecrite sur l'image ne doit pas passer pour une consigne
        du proprietaire — meme discipline que pour un document joint."""
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert "DONNEE" in provider.appels[0]["prompt"]

    async def test_plusieurs_images_partent_toutes(self, provider_factory, depot):
        piece1 = depot.deposer("avant.jpg", OCTETS_IMAGE)
        piece2 = depot.deposer("apres.jpg", OCTETS_IMAGE)
        provider = provider_factory("Deux photos comparees.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run(
            "Compare ces deux photos.",
            context={"attachments": [piece1.identifiant, piece2.identifiant]})

        assert len(provider.appels[0]["images"]) == 2
        assert reponse["images_analysees"] == ["avant.jpg", "apres.jpg"]

    async def test_une_piece_texte_melangee_a_une_image_est_filtree(self, provider_factory, depot):
        image = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        texte = depot.deposer("devis.txt", b"486 m2")
        provider = provider_factory("Une photo de chantier.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run(
            "Que vois-tu ?", context={"attachments": [texte.identifiant, image.identifiant]})

        assert reponse["images_analysees"] == ["chantier.jpg"]
        assert len(provider.appels[0]["images"]) == 1


class TestOllamaIndisponible:
    async def test_ollama_eteint_rend_not_configured(self, depot):
        from tests.conftest import FakeProvider

        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = FakeProvider(disponible=False)
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "warning"
        assert "ollama" in reponse["response"].lower()


class TestDemandeSecuriteChantier:
    def test_chantier_declenche(self):
        assert demande_securite_chantier("analyse cette photo de chantier") is True

    def test_epi_declenche(self):
        assert demande_securite_chantier("verifie les EPI sur cette image") is True

    def test_une_question_ordinaire_ne_declenche_pas(self):
        assert demande_securite_chantier("que vois-tu ?") is False

    def test_un_plan_ne_declenche_pas(self):
        assert demande_securite_chantier("analyse ce plan de construction") is False


class FauxRegistreSecurite:
    """Un registre minimal : capture l'appel a `securite_chantier.analyser`,
    rend un `ResultatAction` REEL — jamais un dict libre (meme discipline que
    `agents/ui/ui_agent.py`)."""

    def __init__(self, resultat):
        self._resultat = resultat
        self.appels = []

    def executer(self, nom, capacite, **parametres):
        self.appels.append((nom, capacite, parametres))
        return self._resultat


class TestDetectionSecuriteChantier:
    async def test_declenchee_sur_demande_chantier_avec_registre(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier avec des ouvriers.")
        resultat = succes(
            action="analyser", cible="securite_chantier",
            message="1 personne detectee.", preuve="chantier.jpg",
            personnes=1, risques=[], resume="1 personne detectee(s) sur chantier.jpg.")
        registre = FauxRegistreSecurite(resultat)
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "analyse cette photo de chantier", context={"attachments": [piece.identifiant]})

        assert registre.appels == [
            ("securite_chantier", "analyser",
             {"image_base64": piece.image_base64, "nom_fichier": "chantier.jpg"})]
        assert reponse["securite_chantier"]["personnes"] == 1
        assert "DÉTECTION SÉCURITÉ" in reponse["response"]
        assert "1 personne detectee" in reponse["response"]

    async def test_jamais_declenchee_sans_mot_de_securite(self, provider_factory, depot):
        """Une image quelconque (capture d'ecran, plan) ne doit pas
        declencher une detection EPI pour rien."""
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Un mur en BA13.")
        registre = FauxRegistreSecurite(succes(
            action="analyser", cible="securite_chantier", message="x", preuve="x"))
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert registre.appels == []
        assert reponse["securite_chantier"] is None

    async def test_sans_registre_reste_absente(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=None)

        reponse = await agent.run(
            "analyse cette photo de chantier", context={"attachments": [piece.identifiant]})

        assert reponse["securite_chantier"] is None
        assert "DÉTECTION SÉCURITÉ" not in reponse["response"]

    async def test_non_configure_le_dit_jamais_silencieux(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier.")
        registre = FauxRegistreSecurite(non_configure(
            action="analyser", cible="securite_chantier", ce_qui_manque="SiteGuard"))
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "analyse cette photo de chantier, verifie les EPI",
            context={"attachments": [piece.identifiant]})

        assert reponse["securite_chantier"]["statut"] == "NOT_CONFIGURED"
        assert "SiteGuard" in reponse["response"]

    async def test_un_echec_le_dit_jamais_invente(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier.")
        registre = FauxRegistreSecurite(echec(
            action="analyser", cible="securite_chantier", message="SiteGuard injoignable"))
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "analyse cette photo de chantier", context={"attachments": [piece.identifiant]})

        assert reponse["securite_chantier"]["statut"] == "FAILED"
        assert reponse["securite_chantier"]["personnes"] is None


class TestModeleAbsent:
    """`OllamaProvider.generate` leve quand le modele de vision n'est pas
    installe — l'agent doit le dire, pas planter."""

    class ProviderQuiRefuse:
        async def is_available(self):
            return True

        async def generate(self, prompt, system_prompt=None, images=None):
            requete = httpx.Request("POST", "http://localhost/api/generate")
            reponse = httpx.Response(404, request=requete, text="model not found")
            raise httpx.HTTPStatusError("404", request=requete, response=reponse)

    async def test_le_modele_absent_est_signale_clairement(self, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        agent = VisionAgent(provider=self.ProviderQuiRefuse(), pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "warning"
        assert "qwen3-vl" in reponse["response"]


class TestDemandeMetadonneesTechniques:
    """Mission EXIF & Media Metadata (DEC-0081) : le mot-cle, sans registre ni modele."""

    def test_informations_techniques_declenche(self):
        assert demande_metadonnees_techniques(
            "Donne-moi toutes les informations techniques disponibles sur cette photo") is True

    def test_analyse_completement_declenche(self):
        assert demande_metadonnees_techniques("Analyse complètement cette photo") is True

    def test_exif_declenche(self):
        assert demande_metadonnees_techniques("quel est l'EXIF de cette image ?") is True

    def test_une_description_ordinaire_ne_declenche_pas(self):
        assert demande_metadonnees_techniques("que vois-tu sur cette photo ?") is False

    def test_analyse_chantier_ne_declenche_pas_a_tort(self):
        """« analyse cette photo de chantier » ne contient ni « complètement »
        ni « technique » : SiteGuard se declenche, pas les metadonnees."""
        assert demande_metadonnees_techniques("analyse cette photo de chantier") is False


class FauxRegistreMultiple:
    """Un registre a plusieurs connecteurs, cle par (nom, capacite) — pour les
    tests ou Vision et media_metadata sont tous deux sollicites."""

    def __init__(self, reponses):
        self._reponses = reponses
        self.appels = []

    def executer(self, nom, capacite, **parametres):
        self.appels.append((nom, capacite, parametres))
        return self._reponses[(nom, capacite)]


def _resultat_metadata(**detail):
    return succes(action="analyser", cible="media_metadata", message="mesure",
                 preuve="x", **detail)


class TestMetadonneesTechniques:
    """Mission EXIF & Media Metadata, §4 — INTÉGRATION VISION :
    ARENA -> Vision -> Media Metadata -> combinaison -> reponse. Les deux
    signaux restent distincts (meme discipline que SiteGuard) : jamais fondus
    dans un seul texte sans en-tete."""

    async def test_declenchee_et_combinee_sans_etre_fondue(self, provider_factory, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory("Un mur en placo, vue de face.")
        registre = FauxRegistreMultiple({
            ("media_metadata", "analyser"): _resultat_metadata(
                format_reel="JPEG", largeur=800, hauteur=600, fabricant="Canon",
                modele_appareil="EOS R5", iso=400, ouverture="f/2.8",
                vitesse_obturation="1/250s", focale_mm=50.0, date_prise="2026:09:10 12:00:00",
                logiciel=None, copyright=None, gps_present=False,
                gps_latitude=None, gps_longitude=None, alerte_extension=None),
        })
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "Analyse complètement cette photo", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "success"
        assert "Un mur en placo, vue de face." in reponse["response"]
        assert "INFORMATIONS TECHNIQUES" in reponse["response"]
        assert "EOS R5" in reponse["response"]
        assert "f/2.8" in reponse["response"]
        # Les deux signaux restent SEPARES, jamais fondus l'un dans l'autre.
        assert reponse["response"].index("Un mur en placo") < reponse["response"].index(
            "INFORMATIONS TECHNIQUES")
        assert reponse["metadonnees_techniques"]["modele_appareil"] == "EOS R5"

    async def test_le_registre_recoit_le_bon_appel(self, provider_factory, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo.")
        registre = FauxRegistreMultiple({
            ("media_metadata", "analyser"): _resultat_metadata(
                format_reel="JPEG", largeur=1, hauteur=1, fabricant=None,
                modele_appareil=None, iso=None, ouverture=None, vitesse_obturation=None,
                focale_mm=None, date_prise=None, logiciel=None, copyright=None,
                gps_present=False, gps_latitude=None, gps_longitude=None,
                alerte_extension=None),
        })
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        await agent.run("montre-moi les métadonnées", context={"attachments": [piece.identifiant]})

        assert ("media_metadata", "analyser",
               {"image_base64": piece.image_base64, "nom_fichier": "photo.jpg"}) in registre.appels

    async def test_jamais_declenchee_sur_une_description_ordinaire(self, provider_factory, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo ordinaire.")
        registre = FauxRegistreMultiple({})
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert registre.appels == []
        assert reponse["metadonnees_techniques"] is None
        assert "INFORMATIONS TECHNIQUES" not in reponse["response"]

    async def test_sans_registre_reste_absente(self, provider_factory, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=None)

        reponse = await agent.run(
            "analyse complètement cette photo", context={"attachments": [piece.identifiant]})

        assert reponse["metadonnees_techniques"] is None
        assert "INFORMATIONS TECHNIQUES" not in reponse["response"]

    async def test_un_echec_de_media_metadata_est_dit_jamais_invente(self, provider_factory, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo.")
        registre = FauxRegistreMultiple({
            ("media_metadata", "analyser"): echec(
                action="analyser", cible="media_metadata", message="fichier illisible"),
        })
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "informations techniques de cette photo", context={"attachments": [piece.identifiant]})

        assert reponse["metadonnees_techniques"] == {"erreur": "fichier illisible"}
        assert "Non disponibles" in reponse["response"]

    async def test_gps_absent_du_fichier_est_dit_jamais_invente(self, provider_factory, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo.")
        registre = FauxRegistreMultiple({
            ("media_metadata", "analyser"): _resultat_metadata(
                format_reel="JPEG", largeur=10, hauteur=10, fabricant=None,
                modele_appareil=None, iso=None, ouverture=None, vitesse_obturation=None,
                focale_mm=None, date_prise=None, logiciel=None, copyright=None,
                gps_present=False, gps_latitude=None, gps_longitude=None,
                alerte_extension=None),
        })
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "métadonnées de cette photo", context={"attachments": [piece.identifiant]})

        assert "GPS : absent du fichier" in reponse["response"]
        assert "14.6" not in reponse["response"], "aucune coordonnee ne doit apparaitre si absente"


class TestMetadonneesQuandVisionEchoue:
    """La photo reste analysable techniquement meme si Qwen3-VL ne repond pas
    — les metadonnees sont mesurees dans le fichier, pas par le modele."""

    async def test_ollama_eteint_rend_quand_meme_les_metadonnees(self, provider_factory, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory(disponible=False)
        registre = FauxRegistreMultiple({
            ("media_metadata", "analyser"): _resultat_metadata(
                format_reel="JPEG", largeur=800, hauteur=600, fabricant="Canon",
                modele_appareil="EOS R5", iso=400, ouverture="f/2.8",
                vitesse_obturation="1/250s", focale_mm=50.0, date_prise="2026:09:10 12:00:00",
                logiciel=None, copyright=None, gps_present=False,
                gps_latitude=None, gps_longitude=None, alerte_extension=None),
        })
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "Analyse complètement cette photo", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "success"
        assert "Ollama ne repond pas" in reponse["response"]
        assert "EOS R5" in reponse["response"]
        assert reponse["metadonnees_techniques"]["modele_appareil"] == "EOS R5"

    async def test_ollama_indisponible_sans_demande_technique_reste_un_avertissement(
        self, provider_factory, depot
    ):
        """Le comportement d'avant cette mission ne change pas pour une
        simple description quand Ollama est eteint."""
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        provider = provider_factory(disponible=False)
        agent = VisionAgent(provider=provider, pieces_jointes=depot, registre=None)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "warning"

    async def test_modele_non_installe_rend_quand_meme_les_metadonnees(self, depot):
        piece = depot.deposer("photo.jpg", OCTETS_IMAGE)
        registre = FauxRegistreMultiple({
            ("media_metadata", "analyser"): _resultat_metadata(
                format_reel="JPEG", largeur=1, hauteur=1, fabricant=None,
                modele_appareil="TestCam", iso=None, ouverture=None, vitesse_obturation=None,
                focale_mm=None, date_prise=None, logiciel=None, copyright=None,
                gps_present=False, gps_latitude=None, gps_longitude=None,
                alerte_extension=None),
        })
        agent = VisionAgent(
            provider=TestModeleAbsent.ProviderQuiRefuse(), pieces_jointes=depot, registre=registre)

        reponse = await agent.run(
            "informations techniques de cette photo", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "success"
        assert "TestCam" in reponse["response"]
        assert "modele de vision n'est probablement pas installe" not in reponse["response"]
