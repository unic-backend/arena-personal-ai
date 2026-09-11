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
        # Sel et nonce tires au hasard a chaque appel : deux chiffrements du meme
        # texte ne doivent jamais etre identiques, sinon un observateur du
        # stockage pourrait repérer deux souvenirs identiques par comparaison.
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
