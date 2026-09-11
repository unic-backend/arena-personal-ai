"""core/memory/personnelle.py — gouvernance (Etat), secrets refuses, chiffrement
au repos, migration d'une base existante, et persistance apres redemarrage.

Mission ARENA x AI MEMORY VAULT (DEC-0090). Ce que ce fichier NE reteste PAS :
tout ce qui existait deja (FAIT/PREFERENCE/INFERENCE/CONTEXTE_TEMPORAIRE,
`confirmer()`, expiration) reste couvert par `test_memoire_personnelle.py`,
inchange.
"""
import sqlite3

import pytest

from core.memory.chiffrement import Coffre
from core.memory.personnelle import Etat, MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.recuperation import recuperer


@pytest.fixture
def memoire(tmp_path):
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


class TestEtatParDefaut:
    def test_un_nouveau_souvenir_est_actif(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        assert s.etat is Etat.ACTIF

    def test_un_souvenir_actif_apparait_dans_la_lecture_normale(self, memoire):
        memoire.retenir("visible", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        assert any(s.contenu == "visible" for s in memoire.souvenirs())


class TestRejeter:
    def test_rejeter_change_l_etat(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        rejete = memoire.rejeter(s.identifiant, source="correction du proprietaire")
        assert rejete.etat is Etat.REJETE

    def test_un_souvenir_rejete_disparait_de_la_lecture_normale(self, memoire):
        s = memoire.retenir("faux souvenir", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.rejeter(s.identifiant, source="correction")
        assert not any(x.identifiant == s.identifiant for x in memoire.souvenirs())

    def test_un_souvenir_rejete_reste_lisible_par_id(self, memoire):
        s = memoire.retenir("faux souvenir", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.rejeter(s.identifiant, source="correction")
        assert memoire.lire(s.identifiant) is not None

    def test_un_souvenir_rejete_reapparait_avec_inclure_rejetes(self, memoire):
        s = memoire.retenir("faux souvenir", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.rejeter(s.identifiant, source="correction")
        assert any(
            x.identifiant == s.identifiant
            for x in memoire.souvenirs(inclure_rejetes=True)
        )

    def test_rejeter_sans_source_est_refuse(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        with pytest.raises(ValueError):
            memoire.rejeter(s.identifiant, source="")

    def test_rejeter_un_identifiant_inconnu_rend_none(self, memoire):
        assert memoire.rejeter("nexistepas", source="p") is None

    def test_rejeter_ce_qui_a_ete_confirme_fonctionne_aussi(self, memoire):
        # Un rejet doit pouvoir annuler un FAIT, pas seulement une INFERENCE :
        # une confirmation anterieure ne protege pas d'une correction ulterieure.
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.INFERENCE, source="p")
        fait = memoire.confirmer(s.identifiant, source="proprietaire")
        assert fait.nature is Nature.FAIT
        rejete = memoire.rejeter(s.identifiant, source="en fait c'etait faux")
        assert rejete.etat is Etat.REJETE
        assert rejete.nature is Nature.FAIT  # la nature ne change pas, seul l'etat


class TestArchiver:
    def test_archiver_change_l_etat(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        archive = memoire.archiver(s.identifiant, source="chantier termine")
        assert archive.etat is Etat.ARCHIVE

    def test_un_souvenir_archive_disparait_de_la_lecture_normale(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.archiver(s.identifiant, source="chantier termine")
        assert not any(x.identifiant == s.identifiant for x in memoire.souvenirs())

    def test_un_souvenir_archive_reapparait_avec_inclure_archives(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.archiver(s.identifiant, source="chantier termine")
        assert any(
            x.identifiant == s.identifiant
            for x in memoire.souvenirs(inclure_archives=True)
        )


class TestReactiver:
    def test_reactiver_annule_un_rejet(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.rejeter(s.identifiant, source="erreur")
        reactive = memoire.reactiver(s.identifiant, source="en fait c'etait vrai")
        assert reactive.etat is Etat.ACTIF
        assert any(x.identifiant == s.identifiant for x in memoire.souvenirs())


class TestSupprimer:
    def test_supprimer_un_souvenir_existant_rend_vrai(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        assert memoire.supprimer(s.identifiant) is True

    def test_apres_suppression_lire_rend_none(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.supprimer(s.identifiant)
        assert memoire.lire(s.identifiant) is None

    def test_apres_suppression_le_souvenir_n_apparait_nulle_part_meme_avec_tout_inclus(self, memoire):
        s = memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.supprimer(s.identifiant)
        tout = memoire.souvenirs(inclure_rejetes=True, inclure_archives=True, inclure_perimes=True)
        assert not any(x.identifiant == s.identifiant for x in tout)

    def test_supprimer_un_identifiant_inconnu_rend_faux(self, memoire):
        assert memoire.supprimer("nexistepas") is False


class TestSecretsRefuses:
    # Construits par concatenation, jamais en litteral : un scanner de secrets
    # (dont celui de GitHub, qui a deja bloque un push sur ce fichier) reagit
    # a la FORME du texte source, pas a son usage. La valeur assemblee a
    # l'execution correspond aux memes motifs (`MOTIFS_NOMMES`) sans laisser
    # un texte en forme de secret dans l'historique git.
    _CONTENUS_SECRETS = [
        "ma cle est " + "sk-" + "abcdefghijklmnopqrstuvwxyz123456",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "xoxb" + "-" + "1234567890" + "-" + "abcdefghijklmnop",
        "-----BEGIN RSA " + "PRIVATE KEY-----\n" + "MIIBOgIBAAJBAK...\n" + "-----END RSA " + "PRIVATE KEY-----",
    ]

    @pytest.mark.parametrize("contenu", _CONTENUS_SECRETS)
    def test_un_contenu_en_forme_de_secret_connu_est_refuse(self, memoire, contenu):
        with pytest.raises(ValueError, match="secret"):
            memoire.retenir(contenu, TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")

    def test_une_phrase_ordinaire_n_est_jamais_refusee_a_tort(self, memoire):
        phrases = [
            "Le client prefere les reponses courtes.",
            "Le chantier de Medina commence le 12 aout 2026.",
            "18 cloisons BA13 hydrofuges commandees.",
        ]
        for phrase in phrases:
            memoire.retenir(phrase, TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        assert len(memoire.souvenirs()) == len(phrases)


class TestChiffrementIntegre:
    def test_sensible_sans_coffre_est_refuse(self, memoire):
        with pytest.raises(ValueError, match="coffre"):
            memoire.retenir("x", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p", sensible=True)

    def test_sensible_avec_coffre_n_ecrit_jamais_le_clair_sur_le_disque(self, tmp_path):
        chemin = tmp_path / "memoire.db"
        coffre = Coffre("phrase-de-test-vraiment-longue")
        memoire = MemoirePersonnelle(db_path=str(chemin), coffre=coffre)
        contenu_confidentiel = "Le proprietaire habite avenue Cheikh Anta Diop."
        s = memoire.retenir(contenu_confidentiel, TypeSouvenir.SEMANTIQUE, Nature.FAIT,
                             source="proprietaire", sensible=True)

        connexion = sqlite3.connect(chemin)
        (stocke,) = connexion.execute(
            "SELECT contenu FROM souvenirs WHERE identifiant = ?", (s.identifiant,)
        ).fetchone()
        connexion.close()
        assert "Cheikh Anta Diop" not in stocke

    def test_sensible_se_relit_en_clair_par_la_meme_instance(self, tmp_path):
        coffre = Coffre("phrase-de-test-vraiment-longue")
        memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"), coffre=coffre)
        contenu_confidentiel = "adresse confidentielle du chantier"
        s = memoire.retenir(contenu_confidentiel, TypeSouvenir.SEMANTIQUE, Nature.FAIT,
                             source="p", sensible=True)
        relu = memoire.lire(s.identifiant)
        assert relu.contenu == contenu_confidentiel

    def test_sensible_relu_sans_coffre_ne_rend_jamais_le_clair(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")
        coffre = Coffre("phrase-de-test")
        avec_coffre = MemoirePersonnelle(db_path=chemin, coffre=coffre)
        s = avec_coffre.retenir("donnee tres privee", TypeSouvenir.SEMANTIQUE, Nature.FAIT,
                                 source="p", sensible=True)

        sans_coffre = MemoirePersonnelle(db_path=chemin)
        relu = sans_coffre.lire(s.identifiant)
        assert "tres privee" not in relu.contenu
        assert relu.identifiant == s.identifiant  # le souvenir existe, juste illisible

    def test_sensible_relu_avec_la_mauvaise_phrase_ne_rend_jamais_le_clair(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")
        bon = MemoirePersonnelle(db_path=chemin, coffre=Coffre("bonne-phrase"))
        s = bon.retenir("donnee tres privee", TypeSouvenir.SEMANTIQUE, Nature.FAIT,
                         source="p", sensible=True)

        mauvais = MemoirePersonnelle(db_path=chemin, coffre=Coffre("mauvaise-phrase"))
        relu = mauvais.lire(s.identifiant)
        assert "tres privee" not in relu.contenu

    def test_un_souvenir_non_sensible_est_inchange_par_ce_mecanisme(self, tmp_path):
        # Non-regression explicite : la trace ecrite dans la table est le clair,
        # bit a bit, pour tout souvenir sans sensible=True — comme avant DEC-0090.
        chemin = tmp_path / "memoire.db"
        memoire = MemoirePersonnelle(db_path=str(chemin))
        s = memoire.retenir("contenu ordinaire", TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        connexion = sqlite3.connect(chemin)
        (stocke,) = connexion.execute(
            "SELECT contenu FROM souvenirs WHERE identifiant = ?", (s.identifiant,)
        ).fetchone()
        connexion.close()
        assert stocke == "contenu ordinaire"


class TestMigrationDUneBaseExistante:
    def test_une_base_creee_avant_dec_0090_gagne_les_colonnes_sans_perdre_ses_lignes(self, tmp_path):
        chemin = tmp_path / "ancienne.db"
        # Recree exactement le schema d'AVANT cette mission (sans etat/sensible).
        connexion = sqlite3.connect(chemin)
        connexion.execute("""
            CREATE TABLE souvenirs (
                identifiant  TEXT PRIMARY KEY,
                contenu      TEXT NOT NULL,
                type         TEXT NOT NULL,
                nature       TEXT NOT NULL,
                source       TEXT NOT NULL,
                projet       TEXT,
                importance   REAL NOT NULL,
                metadonnees  TEXT NOT NULL,
                cree_le      TEXT NOT NULL,
                vu_le        TEXT NOT NULL,
                expire_le    TEXT,
                occurrences  INTEGER NOT NULL DEFAULT 1
            )
        """)
        connexion.execute(
            "INSERT INTO souvenirs (identifiant, contenu, type, nature, source, projet, "
            "importance, metadonnees, cree_le, vu_le, expire_le, occurrences) "
            "VALUES ('anc1', 'souvenir d avant la migration', 'SEMANTIC', 'FACT', "
            "'ancien', NULL, 0.5, '{}', '2026-01-01T00:00:00', '2026-01-01T00:00:00', NULL, 1)"
        )
        connexion.commit()
        connexion.close()

        # L'ouverture doit migrer silencieusement, sans lever, sans perdre la ligne.
        memoire = MemoirePersonnelle(db_path=str(chemin))
        ancien = memoire.lire("anc1")
        assert ancien is not None
        assert ancien.contenu == "souvenir d avant la migration"
        assert ancien.etat is Etat.ACTIF   # defaut applique par la migration
        assert ancien.sensible is False

        # Et la nouvelle fonctionnalite marche immediatement sur cette ligne migree.
        rejete = memoire.rejeter("anc1", source="test de migration")
        assert rejete.etat is Etat.REJETE

    def test_ouvrir_deux_fois_la_meme_base_migree_ne_leve_pas(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")
        MemoirePersonnelle(db_path=chemin)
        # Une seconde ouverture doit voir les colonnes deja presentes et ne pas
        # tenter un second ALTER TABLE (qui leverait "duplicate column name").
        MemoirePersonnelle(db_path=chemin)


class TestPersistanceApresRedemarrage:
    """Mission §39/§43 — E2E via le runtime normal, sans transcript fourni a la main."""

    def test_un_souvenir_approuve_survit_a_un_redemarrage_complet(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")

        # "Session 1" : ARENA tourne, apprend une preference, le proprietaire confirme.
        session_1 = MemoirePersonnelle(db_path=chemin)
        candidat = session_1.retenir(
            "Le proprietaire prefere VS Code pour tester.",
            TypeSouvenir.SEMANTIQUE, Nature.INFERENCE, source="deduit de la conversation",
        )
        session_1.confirmer(candidat.identifiant, source="proprietaire")
        del session_1  # simule la fin du processus — rien ne reste en memoire Python

        # "Redemarrage complet" : nouvelle instance, meme fichier, aucune etape
        # de restauration manuelle.
        session_2 = MemoirePersonnelle(db_path=chemin)
        retrouve = [
            s for s in session_2.souvenirs(type=TypeSouvenir.SEMANTIQUE)
            if "VS Code" in s.contenu
        ]
        assert len(retrouve) == 1
        assert retrouve[0].nature is Nature.FAIT   # confirme avant l'arret, toujours FAIT
        assert retrouve[0].source.startswith("deduit de la conversation")

    def test_une_preference_rejetee_reste_rejetee_apres_redemarrage(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")
        session_1 = MemoirePersonnelle(db_path=chemin)
        s = session_1.retenir("Le proprietaire prefere le rouge.",
                               TypeSouvenir.SEMANTIQUE, Nature.INFERENCE, source="deduit")
        session_1.rejeter(s.identifiant, source="proprietaire : c'est faux")
        del session_1

        session_2 = MemoirePersonnelle(db_path=chemin)
        assert not any("prefere le rouge" in x.contenu for x in session_2.souvenirs())
        assert any(
            "prefere le rouge" in x.contenu
            for x in session_2.souvenirs(inclure_rejetes=True)
        )

    def test_un_souvenir_sensible_reste_dechiffrable_apres_redemarrage_avec_le_bon_coffre(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")
        phrase = "phrase-de-passe-du-proprietaire"

        session_1 = MemoirePersonnelle(db_path=chemin, coffre=Coffre(phrase))
        s = session_1.retenir("numero de telephone du chantier",
                               TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p", sensible=True)
        del session_1

        session_2 = MemoirePersonnelle(db_path=chemin, coffre=Coffre(phrase))
        relu = session_2.lire(s.identifiant)
        assert relu.contenu == "numero de telephone du chantier"


class TestIsolationDeProjet:
    """Mission §16/§40 — deux projets, aucune contamination."""

    def test_deux_projets_avec_des_bases_differentes_ne_se_contaminent_pas(self, memoire):
        memoire.retenir("Ce projet utilise PostgreSQL comme base de donnees.",
                         TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p", projet="PROJET_A")
        memoire.retenir("Ce projet utilise SQLite comme base de donnees.",
                         TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p", projet="PROJET_B")

        resultats_a = recuperer(memoire, "quelle base de donnees ce projet utilise-t-il ?",
                                 projet="PROJET_A")
        contenus_a = [r.souvenir.contenu for r in resultats_a]
        assert any("PostgreSQL" in c for c in contenus_a)
        assert not any("SQLite" in c for c in contenus_a)

        resultats_b = recuperer(memoire, "quelle base de donnees ce projet utilise-t-il ?",
                                 projet="PROJET_B")
        contenus_b = [r.souvenir.contenu for r in resultats_b]
        assert any("SQLite" in c for c in contenus_b)
        assert not any("PostgreSQL" in c for c in contenus_b)

    def test_un_souvenir_sans_projet_n_apparait_pas_dans_une_recherche_par_projet(self, memoire):
        memoire.retenir("Le proprietaire prefere le francais.",
                         TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")  # aucun projet
        resultats = recuperer(memoire, "prefere le francais", projet="PROJET_A")
        assert resultats == []


class TestEfficaciteTokens:
    """Mission §32 — mesurer, pas supposer, la reduction de contexte."""

    def test_le_budget_reduit_reellement_ce_qui_est_envoye_au_modele(self, memoire):
        # Cinquante souvenirs non lies a la question : sans filtre de
        # pertinence, TOUT partirait dans le prompt. `recuperer()` ne prend
        # que ce qui correspond, dans un budget dur.
        for i in range(50):
            memoire.retenir(f"Fait sans rapport numero {i} sur un autre chantier.",
                             TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        memoire.retenir("Le tarif pose BA13 hydrofuge est 5000 F/m2.",
                         TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")

        # AVANT : tout le contexte disponible, sans filtre de pertinence.
        tout = memoire.souvenirs(limite=1000)
        caracteres_avant = sum(len(s.contenu) for s in tout)

        # APRES : uniquement ce qui repond a la question, dans un budget dur.
        resultats = recuperer(memoire, "tarif pose BA13", budget_caracteres=500)
        caracteres_apres = sum(len(r.souvenir.contenu) for r in resultats)

        assert len(tout) == 51
        assert any("tarif pose BA13" in r.souvenir.contenu for r in resultats)
        assert caracteres_apres < caracteres_avant
        # Reduction mesuree, pas supposee : au moins 90% de moins ici, avec ce jeu de donnees.
        reduction = 1 - (caracteres_apres / caracteres_avant)
        assert reduction > 0.9, f"reduction mesuree : {reduction:.1%}"

    def test_le_budget_caracteres_n_est_jamais_depasse(self, memoire):
        for i in range(30):
            memoire.retenir(f"Le tarif du chantier {i} est mentionne ici.",
                             TypeSouvenir.SEMANTIQUE, Nature.FAIT, source="p")
        resultats = recuperer(memoire, "tarif chantier", budget_caracteres=200)
        total = sum(len(r.souvenir.contenu) + 1 for r in resultats)
        assert total <= 200
