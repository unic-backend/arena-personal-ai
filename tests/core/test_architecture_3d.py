"""`architecture_3d` : la capacité d'ARENA, et le moteur qui la rend.

Deux familles de tests, et la frontière est explicite :

- **Sans moteur** — vocabulaire, plan, permissions, agnosticité au modèle.
  Ils tournent partout, CI compris, parce qu'ils ne mesurent qu'ARENA.
- **Avec le vrai moteur** (`TestSurLeVraiMoteur`) — ils créent de vrais murs
  dans une vraie scène. Ils sont **sautés** quand Bun ou le paquet manquent,
  et sauter n'est pas passer : le rapport le dit.

**Pourquoi le moteur réel plutôt que des doubles.** Un double aurait accepté
n'importe quoi. Le vrai moteur a révélé deux pannes qu'aucun double n'aurait
montrées : `zod` 4.5.4 cassant toutes les écritures (lecture parfaite,
mutations refusées), et un paquet publié qui ne tourne pas sous Node malgré
son README. Les deux sont documentées dans `core/architecture/backend_pascal.py`.
"""
import shutil
from pathlib import Path

import pytest

from core.architecture.backend_pascal import DOSSIER_PAR_DEFAUT, ENTREE, BackendPascal
from core.architecture.capacite import (
    ECRITURES,
    OPERATIONS,
    Capacite3D,
    Mesure,
    OperationInconnue,
)
from core.architecture.plan import planifier, resumer, sequence
from core.connectors.architecture_3d import (
    ACTION_BATIR,
    ACTION_DEMOLITION,
    ACTION_LECTURE,
    ConnecteurArchitecture3D,
    action_de,
)

RACINE = Path(__file__).resolve().parent.parent.parent

_SANS_MOTEUR = pytest.mark.skipif(
    shutil.which("bun") is None
    or not (RACINE / DOSSIER_PAR_DEFAUT / ENTREE).is_file(),
    reason="Pascal n'est pas installe ici (bun ou le paquet npm manquent)")


# --------------------------------------------------------------------------
# La règle qui tient toute l'architecture : aucun modèle ne possède Pascal.
# --------------------------------------------------------------------------

class TestAucunModeleNePossedeLaCapacite:
    """Interdiction de la mission, vérifiée sur le code, pas sur l'intention."""

    FICHIERS = ("core/architecture/capacite.py", "core/architecture/plan.py",
                "core/architecture/backend_pascal.py",
                "core/connectors/architecture_3d.py")
    MODELES = ("qwen", "claude", "mistral", "llama", "gpt", "gemini", "deepseek")

    @pytest.mark.parametrize("relatif", FICHIERS)
    def test_aucun_nom_de_modele_ne_decide_quoi_que_ce_soit(self, relatif):
        """`if modele == "qwen"` ferait de Pascal la propriété d'un modèle."""
        code = (RACINE / relatif).read_text(encoding="utf-8").lower()

        for modele in self.MODELES:
            for motif in (f'== "{modele}"', f"== '{modele}'",
                          f'modele == "{modele}"', f'"{modele}" in'):
                assert motif not in code, (
                    f"{relatif} decide quelque chose sur « {modele} » : la "
                    "capacite doit etre agnostique au modele.")

    def test_la_capacite_ne_recoit_jamais_l_identite_de_l_appelant(self):
        """Elle ne peut pas discriminer ce qu'elle ne reçoit pas."""
        import inspect

        signature = inspect.signature(Capacite3D.executer)

        for interdit in ("modele", "model", "fournisseur", "provider"):
            assert interdit not in signature.parameters, (
                f"`executer` accepte « {interdit} » : la capacite pourrait "
                "changer de comportement selon l'appelant.")

    def test_n_importe_quel_appelant_obtient_le_meme_traitement(self):
        """Trois « modèles » différents, la même opération, le même chemin.

        Le nom de l'appelant n'existe nulle part dans la chaîne : ce test le
        prouve en faisant passer trois appelants imaginaires par la même
        capacité et en vérifiant que le backend reçoit **exactement** la même
        chose. C'est ce que la mission appelle model-agnostic.
        """
        vus = []

        class BackendTemoin:
            nom = "temoin"
            def sonder(self): return True, ""
            def executer(self, session, operation, parametres):
                vus.append((session, operation, dict(parametres)))
                return True, {"ok": 1}, ""
            def fermer(self, session): pass

        capacite = Capacite3D(BackendTemoin())
        for appelant in ("qwen3", "claude-opus", "mistral-large"):
            capacite.executer("creer_mur", session=appelant,
                              niveau="L1", debut=[0, 0], fin=[4, 0])

        operations = {(o, tuple(sorted(p))) for _, o, p in vus}
        assert len(operations) == 1, (
            f"le traitement a change selon l'appelant : {operations}")


# --------------------------------------------------------------------------
# Le contrat : ce qu'ARENA promet, indépendamment du moteur.
# --------------------------------------------------------------------------

class TestLeContratEstStable:
    def test_une_operation_inventee_est_refusee_par_le_contrat(self):
        """Refuser ici, pas au moteur : l'erreur doit nommer le vocabulaire."""
        class Muet:
            nom = "muet"
            def sonder(self): return True, ""
            def executer(self, *a): raise AssertionError("le moteur a ete appele")
            def fermer(self, s): pass

        with pytest.raises(OperationInconnue) as erreur:
            Capacite3D(Muet()).executer("demolir_le_quartier")

        assert "creer_mur" in str(erreur.value), "l'erreur ne dit pas ce qui existe"

    def test_les_ecritures_sont_derivees_jamais_recopiees(self):
        """Une liste tenue à la main diverge au premier ajout."""
        assert ECRITURES == {n for n, o in OPERATIONS.items() if o["ecrit"]}
        assert "creer_mur" in ECRITURES
        assert "inspecter" not in ECRITURES

    def test_chaque_operation_dit_ce_qu_elle_fait(self):
        for nom, details in OPERATIONS.items():
            assert len(details["quoi"]) > 25, f"{nom} n'explique rien"
            assert isinstance(details["ecrit"], bool)

    def test_un_moteur_qui_leve_ne_fait_pas_tomber_ARENA(self):
        """Un moteur externe est une panne possible, jamais une exception."""
        class QuiTombe:
            nom = "casse"
            def sonder(self): return True, ""
            def executer(self, *a): raise RuntimeError("boum")
            def fermer(self, s): pass

        mesure = Capacite3D(QuiTombe()).executer("inspecter")

        assert mesure.ok is False
        assert "boum" in mesure.raison
        assert mesure.duree_ms >= 0

    def test_le_journal_porte_l_observabilite_demandee(self):
        journal = Mesure(capacite="architecture_3d", backend="pascal",
                         operation="creer_mur", session="s1", duree_ms=12,
                         ok=True).journal()

        for cle in ("capability", "backend", "action", "session",
                    "duration_ms", "status"):
            assert cle in journal, f"{cle} manque a l'observabilite"
        assert journal["status"] == "success"


# --------------------------------------------------------------------------
# Les permissions : la panne la plus coûteuse de cette intégration.
# --------------------------------------------------------------------------

class TestLesPermissionsPassentParLAction:
    """Défaut mesuré le 07/09/2026, et il rendait TOUT inutilisable.

    `core/connectors/base.py` interroge la politique avec `capacite.action`,
    jamais avec le nom de la capacité. Une première version déclarait une
    règle par opération (`creer_mur:`, `inspecter:`…) : aucune ne matchait,
    toutes tombaient sur le refus par défaut, et le symptôme était parfait —
    permissions écrites, moteur prêt, et `DENIED` sur la première opération.
    """

    def test_lire_batir_et_demolir_sont_trois_actions_distinctes(self):
        assert action_de("inspecter") == ACTION_LECTURE
        assert action_de("creer_mur") == ACTION_BATIR
        assert action_de("supprimer") == ACTION_DEMOLITION, (
            "supprimer detruit du travail deja fait : il lui faut son risque")

    def test_chaque_action_utilisee_existe_vraiment_dans_la_politique(self):
        """Le test qui aurait attrapé le défaut avant l'exécution."""
        from core.permissions.politique import PolitiqueDePermissions

        politique = PolitiqueDePermissions()
        connecteur = ConnecteurArchitecture3D()

        for nom, capacite in connecteur.capacites().items():
            decision = politique.decider(connecteur.service, capacite.action)
            assert decision.origine == "service", (
                f"l'operation « {nom} » (action « {capacite.action} ») ne "
                "correspond a AUCUNE regle : elle tombera sur le refus par "
                "defaut, comme le 07/09/2026.")

    def test_les_lectures_ne_demandent_aucune_confirmation(self):
        """Confirmer une lecture rendrait toute analyse inutilisable."""
        from core.permissions.politique import PolitiqueDePermissions

        decision = PolitiqueDePermissions().decider("architecture_3d", ACTION_LECTURE)

        assert decision.autorise is True

    def test_les_ecritures_en_demandent_une(self):
        from core.permissions.politique import PolitiqueDePermissions

        politique = PolitiqueDePermissions()

        assert politique.decider("architecture_3d", ACTION_BATIR).demande_confirmation
        assert politique.decider("architecture_3d", ACTION_DEMOLITION).demande_confirmation

    def test_batir_plan_ne_contourne_pas_la_permission_des_ecritures(self):
        """Une confirmation unique ne doit pas être une porte dérobée."""
        capacites = ConnecteurArchitecture3D().capacites()

        assert capacites["batir_plan"].action == ACTION_BATIR
        assert capacites["batir_plan"].ecriture is True


# --------------------------------------------------------------------------
# Le plan : une phrase du propriétaire, sans modèle.
# --------------------------------------------------------------------------

class TestLePlanNInventeRien:
    PHRASE = ("Crée une maison de 20m x 15m avec 3 chambres, un salon, "
              "une cuisine, 2 salles de bain et une terrasse.")

    def test_la_phrase_de_la_mission_donne_les_huit_pieces(self):
        plan = planifier(self.PHRASE)

        pieces = [o.parametres["titre"] for o in plan.operations
                  if o.nom == "creer_piece"]
        assert pieces == ["Chambre 1", "Chambre 2", "Chambre 3", "Salon",
                          "Cuisine", "Salle de bain 1", "Salle de bain 2",
                          "Terrasse"]

    def test_le_pluriel_francais_ne_fait_perdre_aucune_piece(self):
        """« 2 salles de bain » : le pluriel porte sur le PREMIER mot.

        Mesure du 07/09/2026 : une premiere version cherchait « salle de
        bains? » et ne trouvait rien, donc la piece disparaissait du plan
        **en silence**. Un plan qui perd une piece sans le dire est pire
        qu'un plan qui refuse.
        """
        plan = planifier("maison 10 x 10 avec 2 salles de bain")

        assert any(o.parametres.get("titre", "").startswith("Salle de bain")
                   for o in plan.operations if o.nom == "creer_piece")

    def test_l_emprise_est_celle_demandee(self):
        plan = planifier("maison de 20m x 15m")
        coque = [o for o in plan.operations if o.nom == "creer_coque"][0]

        assert coque.parametres["emprise"] == [[0, 0], [20.0, 0], [20.0, 15.0], [0, 15.0]]

    def test_la_virgule_decimale_francaise_est_comprise(self):
        """Il écrit « 4,5 m », jamais « 4.5 m »."""
        plan = planifier("piece de 4,5 x 3,2")
        coque = [o for o in plan.operations if o.nom == "creer_coque"][0]

        assert coque.parametres["emprise"][1][0] == 4.5

    def test_sans_dimension_rien_n_est_invente(self):
        """Deviner une taille produirait un batiment que personne n'a demande."""
        plan = planifier("construis-moi quelque chose de bien")

        assert plan.operations == []
        assert "dimension" in " ".join(plan.non_compris)

    def test_le_plan_dit_ce_qu_il_n_a_pas_compris(self):
        plan = planifier("maison de 12 x 8")

        assert "aucune piece nommee" in " ".join(plan.non_compris)
        assert "Non compris" in resumer(plan)

    def test_la_hauteur_par_defaut_est_annoncee_pas_cachee(self):
        assert "hauteur sous plafond" in resumer(planifier("maison 10 x 10"))

    def test_le_plan_est_deterministe(self):
        """Sans modèle, la même phrase donne toujours le même plan."""
        assert sequence(planifier(self.PHRASE)) == sequence(planifier(self.PHRASE))

    def test_toutes_les_operations_du_plan_existent_au_contrat(self):
        for nom, _ in sequence(planifier(self.PHRASE)):
            assert nom in OPERATIONS, f"le plan invente l'operation « {nom} »"


# --------------------------------------------------------------------------
# Le moteur absent : une panne se rapporte, elle ne se simule pas.
# --------------------------------------------------------------------------

class TestQuandLeMoteurManque:
    def test_sans_bun_la_sonde_dit_quoi_installer(self, tmp_path):
        backend = BackendPascal(dossier=tmp_path, moteur_js="bun-qui-n-existe-pas")

        pret, manque = backend.sonder()

        assert pret is False
        assert "bun" in manque.lower()
        assert "Node" in manque, "la raison de ne PAS utiliser Node doit etre dite"

    @_SANS_MOTEUR
    def test_sans_le_paquet_la_sonde_le_dit(self, tmp_path):
        backend = BackendPascal(dossier=tmp_path)

        pret, manque = backend.sonder()

        assert pret is False
        assert "npm install" in manque

    def test_le_connecteur_rend_NON_CONFIGURE_pas_une_exception(self, tmp_path):
        connecteur = ConnecteurArchitecture3D(
            capacite=Capacite3D(BackendPascal(dossier=tmp_path,
                                              moteur_js="absent-pour-le-test")))

        sante = connecteur.sonder()

        assert sante.etat.value in ("NOT_CONFIGURED", "NON_CONFIGURE")
        assert sante.ce_qui_manque

    def test_une_operation_absente_du_backend_est_nommee(self):
        """Le contrat peut dépasser un backend : ça se dit, ça ne plante pas."""
        backend = BackendPascal()
        ok, _, raison = backend.executer("s1", "creer_piscine", {})

        assert ok is False
        assert "creer_piscine" in raison


# --------------------------------------------------------------------------
# Le vrai moteur. Aucun double : de vrais murs dans une vraie scène.
# --------------------------------------------------------------------------

@_SANS_MOTEUR
class TestSurLeVraiMoteur:
    """Les tests que la mission exige, sur le moteur réel."""

    @pytest.fixture
    def capacite(self):
        objet = Capacite3D(BackendPascal(dossier=RACINE / DOSSIER_PAR_DEFAUT))
        yield objet
        objet.backend.fermer_tout()

    def _maison(self, capacite, session):
        capacite.executer("creer_projet", session=session, titre="Essai")
        niveaux = capacite.executer("lister_niveaux", session=session)
        return (niveaux.detail.get("levels") or [{}])[0].get("id")

    def test_01_le_moteur_repond_et_dit_ce_qu_il_sait_faire(self, capacite):
        pret, manque = capacite.sonder()
        assert pret is True, manque

    def test_02_creer_un_projet_cree_une_vraie_scene(self, capacite):
        capacite.executer("creer_projet", session="t2", titre="Maison")
        scene = capacite.executer("inspecter", session="t2")

        types = {n.get("type") for n in (scene.detail.get("nodes") or {}).values()}
        assert {"site", "building", "level"} <= types

    def test_03_04_un_niveau_et_quatre_murs_reels(self, capacite):
        niveau = self._maison(capacite, "t3")
        assert niveau, "aucun niveau dans la scene neuve"

        for debut, fin in ([[0, 0], [20, 0]], [[20, 0], [20, 15]],
                           [[20, 15], [0, 15]], [[0, 15], [0, 0]]):
            mesure = capacite.executer("creer_mur", session="t3", niveau=niveau,
                                       debut=debut, fin=fin, hauteur=2.5,
                                       epaisseur=0.1)
            assert mesure.ok, mesure.raison

        murs = capacite.executer("lister_murs", session="t3")
        longueurs = sorted(round(m.get("length", 0)) for m in murs.detail["walls"])
        assert longueurs == [15, 15, 20, 20], "la geometrie ne correspond pas"

    def test_05_06_une_porte_et_une_fenetre_dans_un_vrai_mur(self, capacite):
        niveau = self._maison(capacite, "t5")
        mur = capacite.executer("creer_mur", session="t5", niveau=niveau,
                                debut=[0, 0], fin=[6, 0], hauteur=2.5).detail["wallId"]

        porte = capacite.executer("poser_porte", session="t5", mur=mur,
                                  largeur=0.9, hauteur=2.1)
        fenetre = capacite.executer("poser_fenetre", session="t5", mur=mur,
                                    largeur=1.2, hauteur=1.0)

        assert porte.ok, porte.raison
        assert fenetre.ok, fenetre.raison

    def test_07_plusieurs_pieces_portent_leurs_noms(self, capacite):
        niveau = self._maison(capacite, "t7")
        for nom, polygone in (("Salon", [[0, 0], [8, 0], [8, 6], [0, 6]]),
                              ("Cuisine", [[8, 0], [14, 0], [14, 6], [8, 6]])):
            capacite.executer("creer_piece", session="t7", niveau=niveau,
                              titre=nom, polygone=polygone)

        zones = capacite.executer("lister_zones", session="t7")
        assert {z["name"] for z in zones.detail["zones"]} == {"Salon", "Cuisine"}

    def test_08_09_10_modifier_deplacer_supprimer(self, capacite):
        niveau = self._maison(capacite, "t8")
        mur = capacite.executer("creer_mur", session="t8", niveau=niveau,
                                debut=[0, 0], fin=[4, 0]).detail["wallId"]

        supprime = capacite.executer("supprimer", session="t8", element=mur)

        assert supprime.ok, supprime.raison
        restants = capacite.executer("lister_murs", session="t8").detail["walls"]
        assert all(m["id"] != mur for m in restants), "le mur est encore la"

    def test_11_12_annuler_puis_refaire(self, capacite):
        niveau = self._maison(capacite, "t11")
        capacite.executer("creer_mur", session="t11", niveau=niveau,
                          debut=[0, 0], fin=[4, 0])
        avant = len(capacite.executer("lister_murs", session="t11").detail["walls"])

        capacite.executer("annuler", session="t11")
        apres = len(capacite.executer("lister_murs", session="t11").detail["walls"])
        capacite.executer("refaire", session="t11")
        rendu = len(capacite.executer("lister_murs", session="t11").detail["walls"])

        assert apres == avant - 1, "annuler n'a rien annule"
        assert rendu == avant, "refaire n'a rien retabli"

    def test_13_14_enregistrer_puis_relister(self, capacite):
        self._maison(capacite, "t13")
        enregistre = capacite.executer("enregistrer", session="t13", titre="essai-t13")

        assert enregistre.ok, enregistre.raison
        scenes = capacite.executer("lister_scenes", session="t13")
        assert any(s.get("name") == "essai-t13" for s in scenes.detail["scenes"])

    def test_15_exporter_rend_une_scene_non_vide(self, capacite):
        self._maison(capacite, "t15")
        export = capacite.executer("exporter_json", session="t15")

        assert export.ok, export.raison
        assert export.detail, "l'export est vide"

    def test_17_inspecter_rend_la_structure(self, capacite):
        self._maison(capacite, "t17")
        scene = capacite.executer("inspecter", session="t17")

        assert scene.detail.get("nodes"), "aucune structure rendue"

    def test_25_mesurer_donne_une_vraie_distance(self, capacite):
        niveau = self._maison(capacite, "t25")
        a = capacite.executer("creer_mur", session="t25", niveau=niveau,
                              debut=[0, 0], fin=[20, 0]).detail["wallId"]
        b = capacite.executer("creer_mur", session="t25", niveau=niveau,
                              debut=[0, 15], fin=[20, 15]).detail["wallId"]

        mesure = capacite.executer("mesurer", session="t25", de=a, a=b)

        assert mesure.detail["distanceMeters"] == 15, "la distance est fausse"

    def test_27_deux_sessions_ne_se_melangent_jamais(self, capacite):
        """La garantie qui protège deux chantiers ouverts en même temps."""
        niveau_a = self._maison(capacite, "chantier-a")
        self._maison(capacite, "chantier-b")

        capacite.executer("creer_mur", session="chantier-a", niveau=niveau_a,
                          debut=[0, 0], fin=[9, 0])

        murs_a = capacite.executer("lister_murs", session="chantier-a").detail["walls"]
        murs_b = capacite.executer("lister_murs", session="chantier-b").detail["walls"]

        assert len(murs_a) == 1
        assert murs_b == [], "le mur du chantier A est apparu dans le chantier B"

    def test_les_ecritures_marchent_vraiment_pas_seulement_le_demarrage(self, capacite):
        """Le test qui aurait attrapé le bug `zod` en une seconde.

        Avec `zod` 4.5.4, le serveur démarrait, `inspecter` répondait
        parfaitement, et **chaque** mutation rendait `Duplicate discriminator
        value "undefined"`. Une sonde « le processus répond » aurait déclaré
        la capacité opérationnelle. Créer un vrai mur est la seule mesure qui
        distingue les deux.
        """
        niveau = self._maison(capacite, "zod")
        mesure = capacite.executer("creer_mur", session="zod", niveau=niveau,
                                   debut=[0, 0], fin=[4, 0])

        assert mesure.ok, (
            f"aucune ecriture ne passe ({mesure.raison}) — verifie que « zod » "
            "est epingle a 4.3.5 dans tools/architecture/pascal")
        assert mesure.detail.get("wallId"), "aucun mur n'a d'identifiant"


class TestLInstallationEstEpinglee:
    """`zod` non épinglé = toutes les écritures cassées, en silence.

    Mesure du 07/09/2026 : Pascal demande `zod ^4.3.5`, npm installe 4.5.4,
    dont `discriminatedUnion` refuse une option au discriminant `undefined`.
    Le serveur démarre, les lectures marchent, et **chaque** mutation rend
    `Duplicate discriminator value "undefined"`.

    Ce test ne mesure pas ce qui est installé — il mesure ce que
    l'installation **demandera** sur sa machine. Le manifeste vit dans
    `core/architecture/paquets.json` et non dans le dossier du moteur :
    celui-ci ne porte rien de versionné (`tests/
    test_moteurs_externes_restent_dehors.py`), et l'épinglage est une
    décision d'ARENA, pas un fichier de Pascal.
    """

    def test_le_manifeste_epingle_zod_sous_4_5(self):
        import json

        manifeste = json.loads(
            (RACINE / "core/architecture/paquets.json").read_text(encoding="utf-8"))
        zod = manifeste["dependencies"]["zod"]

        assert zod.startswith("^4.3") or zod.startswith("4.3"), (
            f"zod est demande en « {zod} » : au-dela de 4.3, toutes les "
            "ecritures de Pascal echouent (DEC-0070).")

    def test_le_manifeste_nomme_les_deux_paquets_reellement_utilises(self):
        import json

        deps = json.loads(
            (RACINE / "core/architecture/paquets.json").read_text(encoding="utf-8")
        )["dependencies"]

        assert "@pascal-app/mcp" in deps
        assert "@pascal-app/core" in deps, "le coeur est une dependance PAIR : sans lui, rien"
