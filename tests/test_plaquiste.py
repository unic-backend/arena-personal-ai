"""L'assistant métier d'UniC Plaquiste.

Ce qui est tenu ici n'est pas du style, c'est de l'argent : **aucun prix n'est
inventé**. Les tarifs viennent des devis réels du propriétaire, versés dans
`config/unic_plaquiste.yaml` le 27/08/2026. Un devis faux part chez un client
et engage l'entreprise.
"""
from pathlib import Path

import pytest
import yaml

from agents.plaquiste.plaquiste_agent import (
    PlaquisteAgent,
    charger_metier,
    composer_instruction,
)
from apps.backend.config import AGENTS_SPECIALISES
from core.actions.resultat import Statut, a_confirmer, non_configure, succes

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "config" / "unic_plaquiste.yaml"


class ModeleDouble:
    def __init__(self):
        self.prompts = []
        self.systemes = []

    async def generate(self, prompt, system_prompt=None, **kw):
        self.prompts.append(prompt)
        self.systemes.append(system_prompt)
        return "  reponse redigee  "


class TestConnaissancesMetier:
    def test_le_fichier_metier_existe_et_se_lit(self):
        assert charger_metier(FICHIER)

    def test_les_prix_viennent_des_devis_reels(self):
        """Vérifiés un par un contre le devis Fast Group du 14/07/2026."""
        prix = charger_metier(FICHIER)["prix_materiaux"]

        assert prix["Plaque standard BA13"] == 4500
        assert prix["Montant 48 mm"] == 1600
        assert prix["Rails 48 mm"] == 1500
        assert prix["Sac enduit"] == 12000
        assert prix["Peinture en eau Gylatex (coloris)"] == 11500

    def test_le_tarif_de_main_oeuvre_est_celui_du_devis(self):
        assert charger_metier(FICHIER)["main_oeuvre"]["tarif_m2"] == 5000

    def test_les_informations_legales_sont_exactes(self):
        e = charger_metier(FICHIER)["entreprise"]

        assert e["ninea"] == "013141677"
        assert e["rccm"] == "SN.DKR.2026.A.22010"
        assert e["telephone"] == "+221 77 708 50 92"
        assert e["gerant"] == "Uthman"

    def test_un_fichier_absent_ne_leve_pas(self):
        """Le serveur doit démarrer même sans les connaissances métier."""
        assert charger_metier(RACINE / "config" / "inexistant.yaml") == {}

    def test_un_fichier_illisible_ne_leve_pas(self, tmp_path):
        casse = tmp_path / "casse.yaml"
        casse.write_text("ceci: [n'est pas: du yaml valide", encoding="utf-8")
        assert charger_metier(casse) == {}


class TestInstructionSysteme:
    def test_les_prix_sont_transmis_au_modele(self):
        instruction = composer_instruction(charger_metier(FICHIER))

        assert "4500" in instruction
        assert "Plaque standard BA13" in instruction
        assert "5000" in instruction

    def test_l_interdiction_d_inventer_un_prix_est_explicite(self):
        instruction = composer_instruction(charger_metier(FICHIER))

        assert "n'inventes jamais un prix" in instruction
        assert "prix a confirmer" in instruction

    def test_la_regle_de_surface_developpee_est_transmise(self):
        """Une cloison fermée double face se facture ×2. Règle de la maison."""
        instruction = composer_instruction(charger_metier(FICHIER))
        assert "surface developpee" in instruction

    def test_les_exclusions_habituelles_sont_transmises(self):
        instruction = composer_instruction(charger_metier(FICHIER))
        assert "electricite" in instruction

    def test_sans_connaissances_l_instruction_interdit_de_chiffrer(self):
        instruction = composer_instruction({})

        assert "ne dois chiffrer aucun devis" in instruction
        assert "4500" not in instruction

    def test_changer_un_prix_dans_le_fichier_change_l_instruction(self):
        """Les prix vivent dans le YAML, jamais dans le code."""
        metier = yaml.safe_load(FICHIER.read_text(encoding="utf-8"))
        metier["prix_materiaux"]["Plaque standard BA13"] = 9999

        assert "9999" in composer_instruction(metier)


class TestAgent:
    async def test_l_agent_repond_avec_l_instruction_metier(self):
        modele = ModeleDouble()
        agent = PlaquisteAgent(provider=modele, metier=charger_metier(FICHIER))

        res = await agent.run("fais un devis pour 18 parois")

        assert res["status"] == "success"
        assert res["response"] == "reponse redigee"
        assert "UniC Plaquiste" in modele.systemes[0]
        assert "4500" in modele.systemes[0]

    async def test_sans_connaissances_l_agent_refuse_et_n_appelle_pas_le_modele(self):
        """Le cas qui compte : pas de fichier, donc pas de devis chiffré."""
        modele = ModeleDouble()
        agent = PlaquisteAgent(provider=modele, metier={})

        res = await agent.run("fais un devis")

        assert res["status"] == "warning"
        assert modele.prompts == [], "le modele a ete appele sans grille de prix"
        assert "invente" in res["response"]

    async def test_le_nombre_d_articles_connus_est_rapporte(self):
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER))
        res = await agent.run("bonjour")

        assert res["articles_connus"] >= 23


class TestAiguillage:
    @pytest.mark.parametrize("demande", [
        "fais-moi un devis pour 12 parois",
        "ecris un mail au client pour le chantier de Diamniadio",
        "combien de plaques BA13 pour 40 m2",
        "prepare la facture de main-d'oeuvre",
        "planifie le chantier de la semaine prochaine",
    ])
    def test_ces_demandes_vont_a_l_agent_metier(self, demande):
        from agents.orchestrator.orchestrator_agent import OrchestratorAgent
        assert OrchestratorAgent._classer_par_mots_cles(None, demande) == "PLAQUISTE"

    def test_l_intention_est_aiguillee_vers_un_agent(self):
        assert "PLAQUISTE" in AGENTS_SPECIALISES

    # Le menu de LibreChat verifiait ici que « usman-plaquiste » etait
    # proposable. LibreChat est retire le 2026-08-28 ; la garantie qui compte
    # reste, juste en dessous : le modele est SERVI par l'API.

    def test_le_modele_est_servi_par_l_api(self):
        import asyncio

        from apps.backend.routers import openai_gateway
        modeles = asyncio.run(openai_gateway.list_openai_models())
        assert "usman-plaquiste" in [m["id"] for m in modeles["data"]]


class FauxRegistre:
    """Un registre de test : il note ce qu'on lui demande, sans rien écrire."""

    def __init__(self, resultat=None):
        self.appels = []
        self._resultat = resultat or a_confirmer(
            action="produire", cible="devis", message="Pret. Rien n'est parti.")

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, dict(parametres)))
        return self._resultat


DESTINATAIRE = {"client": "Fast Group", "lieu": "Medina", "objet": "cloisons"}


class TestDocumentPdf:
    """Le branchement de `devis_pdf.py` sur l'agent.

    Mesuré le 28/08/2026 : le rendu PDF existait depuis le premier jour et
    **aucun chemin de réponse ne l'appelait**. Le propriétaire demandait un
    devis et recevait du texte. Ces tests tiennent le branchement, et surtout
    ses deux limites : le fichier est demandé explicitement, et le destinataire
    n'est jamais deviné.
    """

    @pytest.mark.asyncio
    async def test_sans_demande_de_fichier_aucun_document_n_est_soumis(self):
        registre = FauxRegistre()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("chiffre-moi 18 parois de 5,40 x 2,50 m",
                                   context=DESTINATAIRE)

        assert resultat["document"] is None
        assert registre.appels == [], "un document a été soumis sans qu'on le demande"

    @pytest.mark.asyncio
    async def test_le_destinataire_n_est_jamais_devine_dans_la_phrase(self):
        registre = FauxRegistre()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run(
            "fais le pdf du devis pour Fast Group à Medina, 18 parois de 5,40 x 2,50 m")

        assert resultat["document"]["statut"] == "INCOMPLET"
        assert set(resultat["document"]["manquants"]) == {"client", "lieu", "objet"}
        assert registre.appels == [], "le connecteur a été appelé sans destinataire connu"

    @pytest.mark.asyncio
    async def test_le_document_demande_passe_par_le_connecteur_devis(self):
        registre = FauxRegistre()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("le pdf du devis, 18 parois de 5,40 x 2,50 m",
                                   context=DESTINATAIRE)

        assert registre.appels, "aucun appel : `devis_pdf` reste endormi"
        connecteur, capacite, parametres = registre.appels[0]
        assert (connecteur, capacite) == ("devis", "produire")
        assert parametres["client"] == "Fast Group"
        assert parametres["type_document"] == "DEVIS"
        assert resultat["document"]["statut"] == "NEEDS_CONFIRMATION"
        assert resultat["document"]["message"] in resultat["response"]

    @pytest.mark.asyncio
    async def test_une_facture_demandee_produit_le_bon_type_document(self):
        """Le renderer sait deja faire une facture ; seule l'orchestration manquait."""
        registre = FauxRegistre()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run(
            "génère la facture, 18 parois de 5,40 x 2,50 m", context=DESTINATAIRE)

        assert registre.appels, "aucun appel : « génère la facture » ne declenche rien"
        _, _, parametres = registre.appels[0]
        assert parametres["type_document"] == "FACTURE"
        assert resultat["document"]["statut"] == "NEEDS_CONFIRMATION"

    @pytest.mark.asyncio
    async def test_sans_registre_l_agent_le_dit_au_lieu_de_promettre_un_fichier(self):
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER))

        resultat = await agent.run("le pdf du devis, 120 m2", context=DESTINATAIRE)

        assert resultat["document"]["statut"] == "NOT_CONFIGURED"


class RegistreScripte:
    """Un registre de test : un resultat different par (connecteur, capacite).

    `FauxRegistre` (ci-dessus) rend toujours le meme resultat — insuffisant
    des qu'un test fait appel a DEUX connecteurs (mesurer, puis exporter).
    """

    def __init__(self, resultats):
        self.appels = []
        self._resultats = resultats

    def _repondre(self, connecteur, capacite, parametres):
        self.appels.append((connecteur, capacite, dict(parametres)))
        resultat = self._resultats.get((connecteur, capacite))
        if resultat is None:
            raise AssertionError(f"appel non scripte : {connecteur}.{capacite}")
        return resultat

    def executer(self, connecteur, capacite, **parametres):
        return self._repondre(connecteur, capacite, parametres)

    def executer_confirmee(self, connecteur, capacite, **parametres):
        return self._repondre(connecteur, capacite, parametres)


DETAIL_PLAN_UNE_PIECE = {
    "pieces": [{"feuille": "A-101.pdf", "numero": "101", "surface_pi2": 437.98,
               "perimetre_pi": 86.61, "confiance": 1.0}],
    "pieces_totales": 1, "feuilles_totales": 1,
    "feuilles_mesurees": ["A-101.pdf"], "feuilles_sans_echelle": [],
    "perimetre_disponible": True,
    "resume": {"totals": {"total_sf_net": 437.98, "lf_net": 86.61}},
}


class TestMesurerLePlan:
    """Le branchement du connecteur OpenTakeoff sur l'agent (DEC-0012).

    Trois choses sont tenues : un chemin de plan absent n'appelle rien ;
    mesurer n'exporte jamais tout seul ; un chiffrage de materiaux ne part
    JAMAIS d'un perimetre mesure pour une cloison — seul un plafond, sans
    ambiguite, le peut (voir `metre_plan.py`).
    """

    @pytest.mark.asyncio
    async def test_sans_chemin_de_plan_rien_n_est_appele(self):
        registre = RegistreScripte({})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("chiffre-moi 18 parois de 5,40 x 2,50 m")

        assert resultat["plan"] is None
        assert registre.appels == []

    @pytest.mark.asyncio
    async def test_sans_registre_le_plan_le_dit_au_lieu_de_se_taire(self):
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER))

        resultat = await agent.run("analyse le plan /chantiers/A-101.pdf")

        assert resultat["plan"]["statut"] == "NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_un_chemin_de_plan_declenche_la_mesure_et_rien_d_autre(self):
        resultat_mesure = succes(action="mesurer", cible="opentakeoff",
                                 message="1 piece(s) mesuree(s) sur 1 feuille(s).",
                                 preuve="/chantiers/A-101.pdf", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("analyse le plan /chantiers/A-101.pdf")

        assert registre.appels == [("opentakeoff", "mesurer", {"chemin": "/chantiers/A-101.pdf"})]
        assert resultat["plan"]["surface_totale_m2"] == pytest.approx(40.69, abs=0.01)
        assert resultat["plan"]["export"] is None

    @pytest.mark.asyncio
    async def test_un_chemin_dans_le_depot_d_arena_est_refuse(self):
        """`chemin_dans` lit n'importe quel chemin absolu ecrit dans la phrase —
        y compris `.env` ou `config/unic_plaquiste.yaml`, les seuls endroits ou
        ARENA garde ses propres secrets. Rien ne doit atteindre OpenTakeoff."""
        from apps.backend.config import BASE_DIR

        registre = RegistreScripte({})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)
        chemin_secret = str(BASE_DIR / "config" / "unic_plaquiste.yaml.pdf")

        resultat = await agent.run(f"analyse le plan {chemin_secret}")

        assert resultat["plan"]["statut"] == "REFUSE"
        assert registre.appels == [], "aucun chemin du depot ne doit atteindre OpenTakeoff"

    @pytest.mark.asyncio
    async def test_demander_aussi_un_pdf_declenche_l_export_derriere_confirmation(self):
        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="/chantiers/A-101.pdf", **DETAIL_PLAN_UNE_PIECE)
        resultat_export = a_confirmer(action="exporter", cible="opentakeoff",
                                      message="Pret. Rien n'est ecrit.")
        registre = RegistreScripte({
            ("opentakeoff", "mesurer"): resultat_mesure,
            ("opentakeoff", "exporter"): resultat_export,
        })
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("analyse le plan /chantiers/A-101.pdf et fais-en un pdf")

        noms = [(c, cap) for c, cap, _ in registre.appels]
        assert ("opentakeoff", "mesurer") in noms
        assert ("opentakeoff", "exporter") in noms
        assert resultat["plan"]["export"]["statut"] == "NEEDS_CONFIRMATION"
        assert resultat["plan"]["export"]["message"] in resultat["response"]

    @pytest.mark.asyncio
    async def test_un_plafond_nomme_se_chiffre_depuis_la_surface_mesuree(self):
        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="/chantiers/A-101.pdf", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("calcule le faux plafond du plan /chantiers/A-101.pdf")

        assert resultat["metre"] is not None
        # Un plafond compte UNE face : pas de doublement, contrairement a une
        # cloison fermee des deux cotes.
        assert resultat["metre"]["surface_developpee"] == pytest.approx(40.69, abs=0.01)
        assert "/chantiers/A-101.pdf" in resultat["metre"]["lu"]

    @pytest.mark.asyncio
    async def test_une_cloison_sans_hauteur_ne_chiffre_rien(self):
        """Le perimetre d'une piece entiere n'est pas une surface de mur a
        poser tant qu'aucune hauteur n'est donnee : rien ne se calcule tout
        seul depuis un perimetre."""
        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="/chantiers/A-101.pdf", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("calcule la surface de la cloison, plan /chantiers/A-101.pdf")

        assert resultat["metre"] is None
        assert resultat["plan"]["surface_totale_m2"] == pytest.approx(40.69, abs=0.01)

    @pytest.mark.asyncio
    async def test_une_cloison_avec_hauteur_se_chiffre_depuis_le_perimetre(self):
        """Correction du propriétaire (29/08/2026) : la surface d'un mur, c'est
        largeur (le perimetre mesure) x hauteur — deux faces par defaut pour
        une cloison/separation."""
        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="/chantiers/A-101.pdf", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run(
            "calcule la cloison, hauteur de 2,50 m, plan /chantiers/A-101.pdf")

        assert resultat["metre"] is not None
        # perimetre 86.61 pi = 26.4 ml ; 26.4 x 2,50 m x 2 faces = 132.0 m2 developpes
        assert resultat["metre"]["surface_developpee"] == pytest.approx(132.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_un_doublage_avec_hauteur_ne_compte_qu_une_face(self):
        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="/chantiers/A-101.pdf", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run(
            "calcule le doublage, hauteur de 2,50 m, plan /chantiers/A-101.pdf")

        assert resultat["metre"] is not None
        # meme perimetre x hauteur, UNE seule face : 66.0 m2, pas 132.0
        assert resultat["metre"]["surface_developpee"] == pytest.approx(66.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_un_rampant_ne_chiffre_jamais_meme_avec_une_hauteur(self):
        """Un rampant suit la pente du toit : ni la surface au sol, ni le
        perimetre x une hauteur verticale ne la donnent. Aucune mesure de ce
        plan ne doit produire un chiffrage, meme avec une hauteur dictee."""
        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="/chantiers/A-101.pdf", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run(
            "calcule le rampant, hauteur de 2,50 m, plan /chantiers/A-101.pdf")

        assert resultat["metre"] is None


def _pdf_valide() -> bytes:
    """Un vrai PDF, pas une chaine qui y ressemble — comme le reste du projet le fait."""
    from io import BytesIO

    from reportlab.pdfgen import canvas

    tampon = BytesIO()
    c = canvas.Canvas(tampon)
    c.drawString(100, 700, "plan")
    c.save()
    return tampon.getvalue()


class TestPlanParPieceJointe:
    """Un plan envoye par upload PWA (pas un chemin tape) atteint OpenTakeoff.

    Decide par le propriétaire le 30/08/2026 : surtout sur son téléphone, au
    chantier, PC éteint le jour — taper un chemin ne marche pas pour lui dans
    ce cas. L'upload doit suffire, et le fichier ne doit toucher le disque
    que le temps de la mesure — jamais plus.
    """

    @pytest.mark.asyncio
    async def test_une_piece_jointe_pdf_est_mesuree(self):
        from apps.backend.pieces_jointes import DepotPiecesJointes

        depot = DepotPiecesJointes()
        piece = depot.deposer("plan_almadies.pdf", _pdf_valide())

        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="peu importe", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre, pieces_jointes=depot)

        resultat = await agent.run(
            "mesure ce plan", context={"attachments": [piece.identifiant]})

        assert resultat["plan"]["statut"] == Statut.SUCCES.value
        connecteur, capacite, parametres = registre.appels[0]
        assert (connecteur, capacite) == ("opentakeoff", "mesurer")
        chemin_utilise = parametres["chemin"]
        assert not Path(chemin_utilise).exists(), "le fichier temporaire n'a pas ete efface"
        # Il ne voit jamais un chemin temporaire genere par ARENA — seulement
        # le nom du fichier qu'il a lui-meme envoye.
        assert resultat["plan"]["chemin"] == "plan_almadies.pdf"

    @pytest.mark.asyncio
    async def test_un_chemin_tape_prime_sur_une_piece_jointe(self):
        """Le texte est plus explicite : s'il y a les deux, le chemin tape gagne."""
        from apps.backend.pieces_jointes import DepotPiecesJointes

        depot = DepotPiecesJointes()
        piece = depot.deposer("plan_almadies.pdf", _pdf_valide())

        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="peu importe", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre, pieces_jointes=depot)

        resultat = await agent.run(
            "mesure /chantiers/A-101.pdf", context={"attachments": [piece.identifiant]})

        assert resultat["plan"]["chemin"] == "/chantiers/A-101.pdf"

    @pytest.mark.asyncio
    async def test_sans_depot_une_piece_jointe_ne_declenche_rien(self):
        """Retro-compatible : un agent sans depot se comporte comme avant."""
        resultat = await PlaquisteAgent(
            provider=ModeleDouble(), metier=charger_metier(FICHIER),
            registre=RegistreScripte({}),
        ).run("mesure ce plan", context={"attachments": ["un-identifiant"]})

        assert resultat["plan"] is None


class TestMemoireDuPlan:
    """Les chiffres mesures restent, pour les reprendre sans renvoyer le plan.

    Décidé par le propriétaire le 30/08/2026 — jamais l'image du plan,
    seulement ce qu'OpenTakeoff en a mesuré.
    """

    def _memoire(self, tmp_path):
        from core.memory.personnelle import MemoirePersonnelle

        return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))

    @pytest.mark.asyncio
    async def test_une_mesure_reussie_est_retenue(self, tmp_path):
        from core.memory.personnelle import Nature, TypeSouvenir

        memoire = self._memoire(tmp_path)
        resultat_mesure = succes(action="mesurer", cible="opentakeoff", message="ok",
                                 preuve="peu importe", **DETAIL_PLAN_UNE_PIECE)
        registre = RegistreScripte({("opentakeoff", "mesurer"): resultat_mesure})
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre, memoire_personnelle=memoire)

        await agent.run("analyse le plan /chantiers/A-101.pdf",
                        context={"client": "Fast Group", "lieu": "Almadies"})

        souvenirs = memoire.souvenirs()
        assert len(souvenirs) == 1
        assert souvenirs[0].type is TypeSouvenir.EPISODIQUE
        assert souvenirs[0].nature is Nature.FAIT
        assert souvenirs[0].projet == "Almadies"
        assert "A-101.pdf" in souvenirs[0].contenu
        assert "OpenTakeoff" in souvenirs[0].source

    @pytest.mark.asyncio
    async def test_une_mesure_qui_echoue_n_est_pas_retenue(self, tmp_path):
        """Un chemin refuse ou une panne n'a rien mesure : rien a retenir."""
        memoire = self._memoire(tmp_path)
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               memoire_personnelle=memoire)  # sans registre -> NOT_CONFIGURED

        await agent.run("analyse le plan /chantiers/A-101.pdf")

        assert memoire.souvenirs() == []

    @pytest.mark.asyncio
    async def test_un_plan_deja_mesure_est_rappele_des_jours_apres(self, tmp_path):
        """Le proprietaire ne renvoie pas le plan : les chiffres suffisent."""
        from core.memory.personnelle import Nature, TypeSouvenir

        memoire = self._memoire(tmp_path)
        memoire.retenir(
            contenu="Plan /chantiers/A-101.pdf mesure : 1 piece, 40.69 m2",
            type=TypeSouvenir.EPISODIQUE, nature=Nature.FAIT,
            source="OpenTakeoff, plan /chantiers/A-101.pdf", projet="Almadies",
        )
        modele = ModeleDouble()
        agent = PlaquisteAgent(provider=modele, metier=charger_metier(FICHIER),
                               memoire_personnelle=memoire)

        await agent.run("le chantier Almadies, ou en est la mesure du plan ?")

        assert "A-101.pdf" in modele.systemes[-1]
        assert "PLANS DEJA MESURES" in modele.systemes[-1]

    @pytest.mark.asyncio
    async def test_sans_rapport_rien_n_est_ajoute_a_l_instruction(self, tmp_path):
        """Pas un reflexe a chaque reponse : seulement quand ca se rapporte."""
        from core.memory.personnelle import Nature, TypeSouvenir

        memoire = self._memoire(tmp_path)
        memoire.retenir(
            contenu="Plan /chantiers/A-101.pdf mesure : 1 piece, 40.69 m2",
            type=TypeSouvenir.EPISODIQUE, nature=Nature.FAIT,
            source="OpenTakeoff, plan /chantiers/A-101.pdf", projet="Almadies",
        )
        modele = ModeleDouble()
        agent = PlaquisteAgent(provider=modele, metier=charger_metier(FICHIER),
                               memoire_personnelle=memoire)

        # Aucun mot en commun avec le souvenir stocke (verifie : ni "plaques"
        # ni "22" ne recoupent "plan/chantiers/A-101/mesure/piece/m2").
        await agent.run("chiffre-moi 22 plaques BA13 pour un client")

        assert "PLANS DEJA MESURES" not in modele.systemes[-1]


class FauxAgenda:
    """Un registre d'agenda de test : il note, il n'appelle jamais Google."""

    def __init__(self, creneaux=None, refus=None, creation=None):
        self.appels = []
        self._creneaux = creneaux if creneaux is not None else [
            {"debut": "2026-08-31T12:00+00:00", "fin": "2026-08-31T18:00+00:00"},
            {"debut": "2026-09-02T08:00+00:00", "fin": "2026-09-02T18:00+00:00"},
        ]
        self._refus = refus
        self._creation = creation or a_confirmer(
            action="creer", cible="calendrier",
            message="Pret a poser. Rien n'est dans l'agenda : confirme.")

    def executer_confirmee(self, connecteur, capacite, **parametres):
        """Le chemin d'APRES la confirmation. L'agent ne doit jamais l'emprunter.

        Il rend un succes exprès : si l'agent le prenait, le rendez-vous serait
        pose pour de bon, et le test doit le voir plutôt que planter.
        """
        self.appels.append((connecteur, f"{capacite}-deja-confirmee", dict(parametres)))
        return succes(action="creer", cible="calendrier", message="Rendez-vous pose.",
                      preuve="evenement-1")

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, dict(parametres)))
        if capacite == "creneaux":
            if self._refus is not None:
                return self._refus
            return succes(action="creneaux", cible="calendrier",
                          message=f"{len(self._creneaux)} creneau(x) libre(s).",
                          preuve="GET events", donnees=self._creneaux, illisibles=0)
        if capacite == "creer":
            return self._creation
        raise AssertionError(f"capacite non prevue : {capacite}")


class TestAgenda:
    """Le branchement du calendrier (chapitre 9.1) sur l'assistant métier.

    L'agent annonçait « planning » dans sa description depuis le premier jour.
    Jusqu'au 28/08/2026, il n'avait accès à aucun agenda : le modèle proposait
    des jours au hasard.
    """

    @pytest.mark.asyncio
    async def test_les_creneaux_reels_entrent_dans_l_instruction(self):
        modele = ModeleDouble()
        agent = PlaquisteAgent(provider=modele, metier=charger_metier(FICHIER),
                               registre=FauxAgenda())

        await agent.run("suis-je libre cette semaine pour un chantier ?")

        assert "CRENEAUX REELLEMENT LIBRES" in modele.systemes[0]
        assert "2026-08-31T12:00" in modele.systemes[0]
        assert "N'en invente aucun autre" in modele.systemes[0]

    @pytest.mark.asyncio
    async def test_une_demande_de_prix_ne_consulte_pas_l_agenda(self):
        """Chiffrer n'a rien à voir avec ses dates."""
        registre = FauxAgenda()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("combien coute une plaque BA13 ?")

        assert registre.appels == []
        assert resultat["agenda"] is None

    @pytest.mark.asyncio
    async def test_un_agenda_illisible_interdit_de_proposer_une_date(self):
        """Une capacité absente se rapporte : elle n'invente pas un jour libre."""
        refus = non_configure(action="creneaux", cible="calendrier",
                              ce_qui_manque="GOOGLE_CLIENT_ID")
        modele = ModeleDouble()
        agent = PlaquisteAgent(provider=modele, metier=charger_metier(FICHIER),
                               registre=FauxAgenda(refus=refus))

        resultat = await agent.run("planifie le chantier de Diamniadio")

        assert "N'EST PAS LISIBLE" in modele.systemes[0]
        assert "Ne propose aucune date" in modele.systemes[0]
        assert resultat["agenda"]["creneaux"] == []

    @pytest.mark.asyncio
    async def test_sans_connecteur_l_agent_le_dit(self):
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER))

        resultat = await agent.run("quels sont mes creneaux libres ?")

        assert resultat["agenda"]["statut"] == "NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_poser_un_rendez_vous_passe_par_la_confirmation(self):
        from datetime import datetime, timezone

        registre = FauxAgenda()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)
        debut = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)

        resultat = await agent.run("planifie le chantier", context={
            "titre": "Chantier Diamniadio", "debut": debut,
            "fin": debut.replace(hour=12)})

        assert resultat["rendez_vous"]["statut"] == Statut.A_CONFIRMER.value
        assert "Rien n'est dans l'agenda" in resultat["response"]

    @pytest.mark.asyncio
    async def test_une_heure_manquante_empeche_de_poser(self):
        """Une date devinée met une équipe sur la route un mauvais jour."""
        registre = FauxAgenda()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("planifie", context={"titre": "Chantier"})

        assert resultat["rendez_vous"]["statut"] == "INCOMPLET"
        assert "debut" in resultat["rendez_vous"]["manquants"]
        assert [a for a in registre.appels if a[1] == "creer"] == []

    @pytest.mark.asyncio
    async def test_sans_demande_de_rendez_vous_rien_n_est_soumis(self):
        registre = FauxAgenda()
        agent = PlaquisteAgent(provider=ModeleDouble(), metier=charger_metier(FICHIER),
                               registre=registre)

        resultat = await agent.run("suis-je libre jeudi ?")

        assert resultat["rendez_vous"] is None
        assert [a for a in registre.appels if a[1] == "creer"] == []

    @pytest.mark.parametrize("phrase", [
        "suis-je libre cette semaine ?", "quels creneaux j'ai", "mon agenda de la semaine",
        "planifie le chantier", "quand puis-je venir",
    ])
    def test_ces_demandes_vont_a_l_agent_metier(self, phrase):
        from agents.orchestrator.orchestrator_agent import OrchestratorAgent

        assert OrchestratorAgent._classer_par_mots_cles(None, phrase) == "PLAQUISTE"
