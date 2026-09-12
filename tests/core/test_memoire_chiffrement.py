"""core/memory/chiffrement.py — le coffre, seul, sans la memoire personnelle.

Mission ARENA x AI MEMORY VAULT (DEC-0090).
"""
import base64
import json

import pytest

from core.memory.chiffrement import (
    ITERATIONS_PBKDF2,
    VARIABLE_PASSPHRASE,
    Coffre,
    EchecDechiffrement,
    _Enveloppe,
)


class TestConstruction:
    def test_une_phrase_vide_est_refusee(self):
        with pytest.raises(ValueError):
            Coffre("")

    def test_une_phrase_faite_uniquement_d_espaces_est_refusee(self):
        with pytest.raises(ValueError):
            Coffre("   ")

    def test_le_repr_ne_montre_jamais_la_phrase_de_passe(self):
        coffre = Coffre("une-phrase-secrete-jamais-affichee")
        assert "une-phrase-secrete-jamais-affichee" not in repr(coffre)


class TestDepuisEnvironnement:
    def test_variable_absente_rend_none(self, monkeypatch):
        monkeypatch.delenv(VARIABLE_PASSPHRASE, raising=False)
        assert Coffre.depuis_environnement() is None

    def test_variable_vide_rend_none(self, monkeypatch):
        monkeypatch.setenv(VARIABLE_PASSPHRASE, "   ")
        assert Coffre.depuis_environnement() is None

    def test_variable_presente_construit_un_coffre(self, monkeypatch):
        monkeypatch.setenv(VARIABLE_PASSPHRASE, "phrase-reelle-de-test")
        coffre = Coffre.depuis_environnement()
        assert coffre is not None
        assert coffre.dechiffrer(coffre.chiffrer("x")) == "x"


class TestRoundTrip:
    def test_le_clair_revient_identique(self):
        coffre = Coffre("phrase-de-test")
        clair = "Le proprietaire prefere le BA13 hydrofuge pour les salles d'eau."
        assert coffre.dechiffrer(coffre.chiffrer(clair)) == clair

    def test_le_texte_unicode_et_les_accents_survivent(self):
        coffre = Coffre("phrase-de-test")
        clair = "Chantier de Médina — 18 cloisons, propriétaire préfère le français."
        assert coffre.dechiffrer(coffre.chiffrer(clair)) == clair

    def test_le_clair_n_apparait_jamais_dans_l_enveloppe(self):
        coffre = Coffre("phrase-de-test")
        clair = "un identifiant tres reconnaissable XK7Q9Z"
        enveloppe = coffre.chiffrer(clair)
        assert "XK7Q9Z" not in enveloppe

    def test_deux_chiffrements_du_meme_clair_produisent_des_enveloppes_differentes(self):
        # Le NONCE est tire au hasard a chaque appel : deux chiffrements du
        # meme texte ne doivent jamais etre identiques, sinon un observateur du
        # stockage pourrait repérer deux souvenirs identiques par comparaison.
        # (Le sel, lui, est partage par lot depuis le 12/09/2026 — voir
        # `TestCoutDuDechiffrement`. C'est le nonce qui porte cette garantie,
        # et il la porte toujours.)
        coffre = Coffre("phrase-de-test")
        a = coffre.chiffrer("meme contenu")
        b = coffre.chiffrer("meme contenu")
        assert a != b

    def test_les_iterations_pbkdf2_sont_au_moins_celles_verifiees_chez_ai_memory_vault(self):
        # AI Memory Vault (frontend/src/cryptoVault.js, audit DEC-0090) utilise
        # 310 000 iterations PBKDF2-SHA256. ARENA ne descend jamais en dessous.
        assert ITERATIONS_PBKDF2 >= 310_000


class TestEchecsSurs:
    def test_mauvaise_phrase_de_passe_leve_echec_dechiffrement(self):
        coffre = Coffre("bonne-phrase")
        enveloppe = coffre.chiffrer("contenu confidentiel")
        autre = Coffre("mauvaise-phrase")
        with pytest.raises(EchecDechiffrement):
            autre.dechiffrer(enveloppe)

    def test_ciphertext_modifie_d_un_seul_octet_est_refuse(self):
        coffre = Coffre("phrase-de-test")
        enveloppe = coffre.chiffrer("contenu confidentiel")
        donnees = json.loads(enveloppe)
        octets = bytearray(base64.b64decode(donnees["ct"]))
        octets[0] ^= 0xFF
        donnees["ct"] = base64.b64encode(bytes(octets)).decode("ascii")
        altere = json.dumps(donnees)
        with pytest.raises(EchecDechiffrement):
            coffre.dechiffrer(altere)

    def test_tag_d_authentification_modifie_est_refuse(self):
        # Le tag GCM vit dans les derniers octets du ciphertext (AESGCM de
        # `cryptography` le concatène) : l'alterer doit aussi etre detecte.
        coffre = Coffre("phrase-de-test")
        enveloppe = coffre.chiffrer("contenu confidentiel")
        donnees = json.loads(enveloppe)
        octets = bytearray(base64.b64decode(donnees["ct"]))
        octets[-1] ^= 0xFF
        donnees["ct"] = base64.b64encode(bytes(octets)).decode("ascii")
        altere = json.dumps(donnees)
        with pytest.raises(EchecDechiffrement):
            coffre.dechiffrer(altere)

    def test_json_illisible_leve_echec_dechiffrement_pas_une_autre_exception(self):
        coffre = Coffre("phrase-de-test")
        with pytest.raises(EchecDechiffrement):
            coffre.dechiffrer("ceci n'est pas du JSON")

    def test_json_valide_mais_forme_inattendue_leve_echec_dechiffrement(self):
        coffre = Coffre("phrase-de-test")
        with pytest.raises(EchecDechiffrement):
            coffre.dechiffrer(json.dumps({"autre_chose": True}))

    def test_les_deux_causes_d_echec_rendent_le_meme_type_d_exception(self):
        # Deliberement le meme type pour mauvaise-cle et donnee-alteree : un
        # type distinct par cause ouvrirait un oracle sur la phrase de passe.
        coffre = Coffre("phrase-de-test")
        enveloppe = coffre.chiffrer("x")

        mauvaise_cle_echoue = False
        try:
            Coffre("autre-phrase").dechiffrer(enveloppe)
        except EchecDechiffrement:
            mauvaise_cle_echoue = True

        json_casse_echoue = False
        try:
            coffre.dechiffrer("pas du json")
        except EchecDechiffrement:
            json_casse_echoue = True

        assert mauvaise_cle_echoue and json_casse_echoue


class TestCoutDuDechiffrement:
    """Mesure du 12/09/2026 : lire 500 souvenirs sensibles prenait 2 min 14.

    Chaque enveloppe portait son propre sel, donc `dechiffrer` refaisait les
    600 000 iterations PBKDF2 **par souvenir** (275 ms chacune). Plus le
    proprietaire enregistrait de souvenirs sensibles, plus ARENA devenait
    lent — jusqu'a l'inutilisable, sur la donnee justement la plus precieuse.

    Deux changements, aucun sur le format d'enveloppe : un cache de cles par
    sel, et un sel reutilise par lot a l'ecriture. Ce que ces tests gardent :
    la compatibilite avec tout ce qui est deja ecrit, et le fait que le
    NONCE — la seule unicite qu'AES-GCM exige — reste tire a chaque message.
    """

    def test_le_nonce_reste_unique_meme_quand_le_sel_est_partage(self):
        coffre = Coffre("phrase-de-test")
        enveloppes = [_Enveloppe.depuis(coffre.chiffrer(f"secret {i}")) for i in range(50)]

        nonces = {e.nonce for e in enveloppes}
        assert len(nonces) == 50, "un nonce repete casse AES-GCM"
        assert len({e.sel for e in enveloppes}) == 1, (
            "le sel doit bien etre partage : c'est ce qui evite 50 derivations")

    def test_un_souvenir_ecrit_avec_un_sel_par_message_reste_lisible(self):
        """La compatibilite qui compte : ses souvenirs deja chiffres.

        On reproduit ici l'ANCIEN format — un sel propre a ce message, tire
        independamment de l'instance — et on verifie qu'il se dechiffre.
        """
        import os

        from core.memory.chiffrement import TAILLE_NONCE, TAILLE_SEL

        coffre = Coffre("phrase-de-test")
        sel_ancien, nonce = os.urandom(TAILLE_SEL), os.urandom(TAILLE_NONCE)
        cle = coffre._deriver_vraiment(sel_ancien)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ciphertext = AESGCM(cle).encrypt(nonce, "code du portail 4821".encode("utf-8"), None)
        ancienne = _Enveloppe(ciphertext=ciphertext, nonce=nonce, sel=sel_ancien).serialiser()

        assert coffre.dechiffrer(ancienne) == "code du portail 4821"

    def test_une_mauvaise_phrase_reste_refusee_malgre_le_cache(self):
        """Le cache ne doit jamais servir de porte de derriere."""
        enveloppe = Coffre("la bonne phrase").chiffrer("secret")

        autre = Coffre("une autre phrase")
        with pytest.raises(EchecDechiffrement):
            autre.dechiffrer(enveloppe)

    def test_le_cache_de_cles_est_borne(self):
        import os

        from core.memory.chiffrement import CLES_GARDEES

        coffre = Coffre("phrase-de-test")
        for _ in range(CLES_GARDEES + 20):
            coffre._deriver_cle(os.urandom(16))

        assert len(coffre._cles) == CLES_GARDEES, (
            "un cache non borne ferait grossir la memoire du processus sans fin")

    def test_le_sel_se_renouvelle_par_lot(self, monkeypatch):
        """Une cle ne doit pas servir indefiniment : la marge de collision de
        nonce reste intacte si le sel se renouvelle."""
        import core.memory.chiffrement as module

        monkeypatch.setattr(module, "MESSAGES_PAR_SEL", 3)
        coffre = Coffre("phrase-de-test")
        sels = [_Enveloppe.depuis(coffre.chiffrer(f"m{i}")).sel for i in range(7)]

        assert len(set(sels)) == 3, f"le sel n'a pas tourne comme prevu : {len(set(sels))}"

    def test_relire_500_souvenirs_ne_derive_qu_une_seule_fois(self):
        """La mesure qui justifie le changement, en test : 500 dechiffrements
        pour UNE derivation, au lieu de 500."""
        coffre = Coffre("phrase-de-test")
        enveloppes = [coffre.chiffrer(f"secret {i}") for i in range(500)]

        derivations = []
        vraie = coffre._deriver_vraiment

        def _compter(sel):
            derivations.append(sel)
            return vraie(sel)
        coffre._deriver_vraiment = _compter
        coffre._cles.clear()

        clairs = [coffre.dechiffrer(e) for e in enveloppes]

        assert clairs[0] == "secret 0" and clairs[-1] == "secret 499"
        assert len(derivations) == 1, (
            f"{len(derivations)} derivations pour 500 lectures — chacune coute "
            f"275 ms, soit ce que ce correctif devait supprimer")


class TestSelConserveEntreDeuxProcessus:
    """DEC-0097 : le sel d'ecriture survit a un redemarrage.

    Le cache de cles de DEC-0096 ne vit que dans un processus. Sans sel
    conserve, chaque demarrage du serveur memoire tirait un sel neuf, donc
    relire les souvenirs sensibles ecrits par le processus precedent repayait
    une derivation PAR SEL : 26,7 s mesurees pour 500 souvenirs ecrits au fil
    de 100 sessions, contre 285 ms avec le sel conserve.
    """

    @staticmethod
    def _sel_de(enveloppe: str) -> str:
        return json.loads(enveloppe)["sel"]

    def test_deux_coffres_successifs_partagent_le_sel_conserve(self, tmp_path):
        fichier = tmp_path / "vault_salt"
        premier = Coffre("phrase-partagee-entre-deux-processus", chemin_sel=fichier)
        premiere = premier.chiffrer("le code du portail est 4821")

        # Un second processus : une instance neuve, le meme fichier.
        second = Coffre("phrase-partagee-entre-deux-processus", chemin_sel=fichier)
        seconde = second.chiffrer("la cle du local est B-12")

        assert self._sel_de(premiere) == self._sel_de(seconde)
        assert self._sel_de(premiere) != json.loads(premiere)["iv"]

    def test_le_nonce_reste_different_malgre_le_sel_conserve(self, tmp_path):
        fichier = tmp_path / "vault_salt"
        enveloppes = [
            Coffre("phrase-de-test-longue", chemin_sel=fichier).chiffrer(f"secret {i}")
            for i in range(20)
        ]

        assert len({json.loads(e)["iv"] for e in enveloppes}) == 20
        assert len({self._sel_de(e) for e in enveloppes}) == 1

    def test_relire_ce_qu_un_autre_processus_a_ecrit_ne_derive_qu_une_fois(self, tmp_path):
        fichier = tmp_path / "vault_salt"
        ecrivain = Coffre("phrase-de-test-longue", chemin_sel=fichier)
        enveloppes = [ecrivain.chiffrer(f"secret {i}") for i in range(50)]

        lecteur = Coffre("phrase-de-test-longue", chemin_sel=fichier)
        derivations = []
        vrai = lecteur._deriver_vraiment
        lecteur._deriver_vraiment = lambda sel: (derivations.append(sel), vrai(sel))[1]

        clairs = [lecteur.dechiffrer(enveloppe) for enveloppe in enveloppes]

        assert clairs == [f"secret {i}" for i in range(50)]
        assert len(derivations) == 1, (
            f"{len(derivations)} derivations pour 50 souvenirs ecrits par un "
            "autre processus : le sel conserve n'est pas relu")

    def test_sans_chemin_le_comportement_reste_celui_d_avant(self):
        """Le sel conserve est une OPTION : sans chemin, deux instances gardent
        chacune le sien, exactement comme avant DEC-0097."""
        premier = Coffre("phrase-de-test-longue").chiffrer("un secret")
        second = Coffre("phrase-de-test-longue").chiffrer("un autre secret")

        assert self._sel_de(premier) != self._sel_de(second)

    def test_le_fichier_ne_contient_que_le_sel_jamais_la_phrase(self, tmp_path):
        fichier = tmp_path / "vault_salt"
        Coffre("phrase-secrete-a-ne-jamais-ecrire", chemin_sel=fichier).chiffrer("x")

        octets = fichier.read_bytes()

        assert len(octets) == 16, "un sel de 16 octets, rien d'autre"
        assert b"phrase-secrete-a-ne-jamais-ecrire" not in octets
        assert oct(fichier.stat().st_mode)[-3:] == "600"

    def test_un_fichier_tronque_ne_bloque_pas_et_ne_perd_rien(self, tmp_path):
        """Sabotage : le fichier de sel est corrompu entre deux demarrages. Le
        coffre doit continuer a ecrire, ET les souvenirs deja ecrits doivent
        rester lisibles — chaque enveloppe porte son propre sel."""
        fichier = tmp_path / "vault_salt"
        ancien = Coffre("phrase-de-test-longue", chemin_sel=fichier)
        enveloppe = ancien.chiffrer("le code du portail est 4821")

        fichier.write_bytes(b"tronque")
        apres = Coffre("phrase-de-test-longue", chemin_sel=fichier)

        assert apres.dechiffrer(enveloppe) == "le code du portail est 4821"
        assert apres.dechiffrer(apres.chiffrer("un nouveau secret")) == "un nouveau secret"
        assert len(fichier.read_bytes()) == 16, "le fichier corrompu est remplace"

    def test_un_dossier_en_lecture_seule_n_empeche_pas_d_ecrire(self, tmp_path):
        """Ne pas pouvoir conserver le sel coute des derivations, jamais un
        souvenir."""
        dossier = tmp_path / "interdit"
        dossier.mkdir()
        dossier.chmod(0o500)
        try:
            coffre = Coffre("phrase-de-test-longue", chemin_sel=dossier / "vault_salt")
            assert coffre.dechiffrer(coffre.chiffrer("un secret")) == "un secret"
        finally:
            dossier.chmod(0o700)

    def test_le_sel_renouvele_par_lot_est_conserve_a_son_tour(self, tmp_path, monkeypatch):
        import core.memory.chiffrement as module

        monkeypatch.setattr(module, "MESSAGES_PAR_SEL", 3)
        fichier = tmp_path / "vault_salt"
        coffre = Coffre("phrase-de-test-longue", chemin_sel=fichier)
        enveloppes = [coffre.chiffrer(f"secret {i}") for i in range(7)]

        sels = [self._sel_de(e) for e in enveloppes]

        assert len(set(sels)) == 3, "trois lots de trois messages"
        assert base64.b64decode(sels[-1]) == fichier.read_bytes(), (
            "le dernier sel utilise doit etre celui conserve, sinon le "
            "prochain processus en derive un autre pour rien")
