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
