"""Qui répond : sa machine, ou le réseau ?

Trois tests portent l'étape.

`test_un_secret_ne_part_jamais_au_cloud` — c'est la seule chose qui ne se
rattrape pas.
`test_tout_tombe_sauf_ollama_et_arena_repond_quand_meme` — sans réseau, sans
clé, budget atteint : ARENA doit répondre.
`test_le_repli_n_a_pas_lieu_apres_le_premier_mot` — recommencer chez un autre
lui ferait lire deux débuts de réponse.

Aucun test n'appelle un service : tous les fournisseurs sont des doubles.
"""
import pytest

from core.models.confidentialite import Confidentialite
from core.models.routeur import LOCAL, RouteurModeles
from core.models.usage import Appel, CompteurUsage


class FauxFournisseur:
    """Un fournisseur de test : il note, il répond, ou il tombe."""

    def __init__(self, nom, texte="reponse", disponible=True, leve=False,
                 configure=True, morceaux=None, leve_au_mot=None):
        self.nom = nom
        self.model_name = f"modele-{nom}"
        self.configure = configure
        self.texte = texte
        self.disponible = disponible
        self.leve = leve
        self.morceaux = morceaux
        self.leve_au_mot = leve_au_mot
        self.appels = []
        self.derniere_mesure = None

    async def is_available(self):
        return self.disponible

    async def generate(self, prompt, system_prompt=None):
        self.appels.append(prompt)
        if self.leve:
            raise ConnectionError(f"{self.nom} injoignable")
        return f"{self.texte} ({self.nom})"

    async def generate_stream(self, prompt, system_prompt=None):
        self.appels.append(prompt)
        if self.leve:
            raise ConnectionError(f"{self.nom} injoignable")
        for index, morceau in enumerate(self.morceaux or ["Bon", "jour"]):
            if self.leve_au_mot is not None and index == self.leve_au_mot:
                raise ConnectionError("le flux a casse")
            yield morceau


def routeur(mode="HYBRIDE", demande="AUTO", groq=None, deepinfra=None,
            local=None, compteur=None):
    return RouteurModeles(
        local=local or FauxFournisseur(LOCAL),
        distants={"groq": groq or FauxFournisseur("groq"),
                  "deepinfra": deepinfra or FauxFournisseur("deepinfra")},
        mode=mode, fournisseur_demande=demande, compteur=compteur)


# --- Les trois tests qui portent l'étape ---------------------------------------------

@pytest.mark.parametrize("mode", ["HYBRIDE", "CLOUD_PREFERRED"])
async def test_un_secret_ne_part_jamais_au_cloud(mode):
    """La seule chose qui ne se rattrape pas."""
    groq = FauxFournisseur("groq")
    r = routeur(mode=mode, groq=groq)

    reponse = await r.generate("mon mot de passe est Azerty123")

    assert "local" in reponse
    assert groq.appels == [], "rien ne doit avoir ete envoye au cloud"
    assert r.dernier_choix.fournisseur == LOCAL
    assert r.dernier_choix.classement.niveau is Confidentialite.TRES_SENSIBLE


async def test_tout_tombe_sauf_ollama_et_arena_repond_quand_meme():
    """Sans réseau, ARENA reste un assistant."""
    r = routeur(groq=FauxFournisseur("groq", disponible=False),
                deepinfra=FauxFournisseur("deepinfra", disponible=False))

    reponse = await r.generate("bonjour")

    assert "local" in reponse
    assert r.dernier_choix.fournisseur == LOCAL
    assert r.dernier_choix.replis == ["groq", "deepinfra"]


async def test_le_repli_n_a_pas_lieu_apres_le_premier_mot():
    """Recommencer chez un autre lui ferait lire deux débuts de réponse."""
    groq = FauxFournisseur("groq", morceaux=["Bon", "jour"], leve_au_mot=1)
    local = FauxFournisseur(LOCAL)
    r = routeur(groq=groq, local=local)

    recus = []
    with pytest.raises(ConnectionError):
        async for morceau in r.generate_stream("bonjour"):
            recus.append(morceau)

    assert recus == ["Bon"], "ce qui est arrive reste arrive"
    assert local.appels == [], "on ne rejoue pas la reponse ailleurs"


# --- L'ordre des questions -------------------------------------------------------------

async def test_le_cloud_sert_quand_rien_ne_l_interdit():
    groq = FauxFournisseur("groq")
    r = routeur(groq=groq)

    reponse = await r.generate("quelle est la capitale du Senegal ?")

    assert "groq" in reponse
    assert groq.appels == ["quelle est la capitale du Senegal ?"]


async def test_ses_affaires_restent_sur_sa_machine_en_hybride():
    groq = FauxFournisseur("groq")
    r = routeur(mode="HYBRIDE", groq=groq)

    await r.generate("fais le devis du client Fast Group")

    assert groq.appels == []
    assert r.dernier_choix.fournisseur == LOCAL


async def test_le_mode_local_seul_ne_laisse_rien_partir():
    groq = FauxFournisseur("groq")
    r = routeur(mode="LOCAL_ONLY", groq=groq)

    await r.generate("bonjour")

    assert groq.appels == []


async def test_le_proprietaire_peut_imposer_un_fournisseur():
    groq, deepinfra = FauxFournisseur("groq"), FauxFournisseur("deepinfra")
    r = routeur(demande="DEEPINFRA", groq=groq, deepinfra=deepinfra)

    await r.generate("bonjour")

    assert deepinfra.appels and groq.appels == []


async def test_un_fournisseur_impose_mais_absent_retombe_sur_sa_machine():
    r = RouteurModeles(local=FauxFournisseur(LOCAL), distants={},
                       mode="HYBRIDE", fournisseur_demande="GROQ")

    reponse = await r.generate("bonjour")

    assert "local" in reponse
    assert "n'est pas configure" in r.dernier_choix.raison


async def test_un_service_sans_cle_n_est_pas_une_option():
    """Un service sans clé n'est pas une option à essayer : il n'existe pas."""
    r = RouteurModeles(
        local=FauxFournisseur(LOCAL),
        distants={"groq": FauxFournisseur("groq", configure=False)},
        mode="HYBRIDE")

    assert "groq" not in r.distants


# --- Le repli --------------------------------------------------------------------------

async def test_groq_tombe_deepinfra_prend_le_relais():
    groq = FauxFournisseur("groq", leve=True)
    deepinfra = FauxFournisseur("deepinfra")
    r = routeur(groq=groq, deepinfra=deepinfra)

    reponse = await r.generate("bonjour")

    assert "deepinfra" in reponse
    assert r.dernier_choix.replis == ["groq"]


async def test_chaque_fournisseur_n_est_essaye_qu_une_fois():
    """Ne pas boucler : un service qui tombe ne se redemande pas indéfiniment."""
    groq = FauxFournisseur("groq", leve=True)
    deepinfra = FauxFournisseur("deepinfra", leve=True)
    local = FauxFournisseur(LOCAL)
    r = routeur(groq=groq, deepinfra=deepinfra, local=local)

    await r.generate("bonjour")

    assert len(groq.appels) == 1 and len(deepinfra.appels) == 1
    assert len(local.appels) == 1


async def test_un_service_qui_echoue_est_mis_au_frais():
    groq = FauxFournisseur("groq", leve=True)
    r = routeur(groq=groq)

    await r.generate("bonjour")
    await r.generate("bonjour encore")

    assert len(groq.appels) == 1, "il ne doit pas etre redemande a chaque phrase"
    assert r.etats["groq"].au_repos(__import__("time").monotonic())


async def test_un_service_qui_ne_repond_pas_a_la_sonde_est_aussi_mis_au_frais():
    """Sonder un service éteint à chaque phrase coûte une attente à chaque phrase."""
    class Compteuse(FauxFournisseur):
        def __init__(self):
            super().__init__("groq", disponible=False)
            self.sondes = 0

        async def is_available(self):
            self.sondes += 1
            return False

    groq = Compteuse()
    r = routeur(groq=groq)

    await r.generate("bonjour")
    await r.generate("bonjour encore")

    assert groq.sondes == 1, "un service eteint ne se redemande pas a chaque phrase"
    assert r.etats["groq"].au_repos(__import__("time").monotonic())


async def test_la_sante_n_est_pas_remesuree_a_chaque_phrase():
    class Compteuse(FauxFournisseur):
        def __init__(self):
            super().__init__("groq")
            self.sondes = 0

        async def is_available(self):
            self.sondes += 1
            return True

    groq = Compteuse()
    r = routeur(groq=groq)

    await r.generate("bonjour")
    await r.generate("bonjour encore")

    assert groq.sondes == 1


# --- Le budget ---------------------------------------------------------------------------

async def test_un_plafond_atteint_fait_redescendre_sur_sa_machine():
    """Un plafond ne casse rien : il fait redescendre."""
    compteur = CompteurUsage(requetes_par_jour=1, budget_journalier=0)
    groq = FauxFournisseur("groq")
    r = routeur(groq=groq, compteur=compteur)

    await r.generate("bonjour")          # 1er : cloud
    reponse = await r.generate("re")     # 2e : plafond atteint

    assert "local" in reponse
    assert "plafond atteint" in r.dernier_choix.raison
    assert len(groq.appels) == 1


async def test_l_appel_local_n_est_pas_compte():
    compteur = CompteurUsage()
    r = routeur(mode="LOCAL_ONLY", compteur=compteur)

    await r.generate("bonjour")

    assert compteur.requetes_aujourdhui == 0


async def test_un_cout_sans_tarif_reste_inconnu():
    """`None` n'est pas `0.0` : un zéro se lirait « gratuit »."""
    compteur = CompteurUsage()
    compteur.enregistrer(Appel(fournisseur="groq", modele="inconnu",
                               jetons_entree=10, jetons_sortie=5))

    assert compteur.cout_aujourdhui is None
    assert compteur.resume()["cout_aujourdhui"] is None


def test_le_compteur_ne_garde_aucune_phrase():
    """Un compteur d'usage n'est pas un enregistreur de conversations."""
    appel = Appel(fournisseur="groq", modele="m", classement="PUBLIC")

    assert "prompt" not in appel.to_dict()
    assert all(not isinstance(v, str) or "bonjour" not in v.lower()
               for v in appel.to_dict().values())


# --- Ce que l'interface peut montrer -------------------------------------------------------

async def test_l_etat_dit_qui_a_repondu_et_avec_quoi():
    r = routeur()

    await r.generate("quelle est la capitale du Senegal ?")
    etat = r.etat()

    assert etat["dernier_choix"]["fournisseur"] == "groq"
    assert etat["modele"] == "modele-groq"
    assert etat["dernier_choix"]["confidentialite"] == "PUBLIC"
    assert etat["usage"]["requetes_aujourdhui"] == 1


async def test_le_choix_dit_toujours_pourquoi():
    r = routeur()

    await r.generate("mon mot de passe")

    assert "secret" in r.dernier_choix.raison


async def test_le_routeur_est_disponible_des_qu_un_seul_repond():
    r = routeur(groq=FauxFournisseur("groq", disponible=False),
                deepinfra=FauxFournisseur("deepinfra", disponible=False))

    assert await r.is_available() is True


# --- Streaming -----------------------------------------------------------------------------

async def test_le_flux_passe_par_le_fournisseur_retenu():
    groq = FauxFournisseur("groq", morceaux=["Bon", "jour", " Saer"])
    r = routeur(groq=groq)

    morceaux = [m async for m in r.generate_stream("quelle est la capitale ?")]

    assert morceaux == ["Bon", "jour", " Saer"]
    assert r.dernier_choix.fournisseur == "groq"


async def test_un_flux_qui_casse_avant_le_premier_mot_replie():
    groq = FauxFournisseur("groq", leve=True)
    deepinfra = FauxFournisseur("deepinfra", morceaux=["Bon", "jour"])
    r = routeur(groq=groq, deepinfra=deepinfra)

    morceaux = [m async for m in r.generate_stream("quelle est la capitale ?")]

    assert morceaux == ["Bon", "jour"]
    assert r.dernier_choix.fournisseur == "deepinfra"


async def test_un_fournisseur_sans_streaming_rend_sa_reponse_d_un_bloc():
    """C'est dégradé, ce n'est pas une panne."""
    class SansFlux(FauxFournisseur):
        generate_stream = None

    r = routeur(groq=SansFlux("groq"))

    morceaux = [m async for m in r.generate_stream("quelle est la capitale ?")]

    assert morceaux == ["reponse (groq)"]


async def test_le_contexte_joint_compte_dans_le_classement():
    """Une question anodine posée sur un document de client ne l'est pas."""
    groq = FauxFournisseur("groq")
    r = routeur(groq=groq)

    await r.generate("resume ca", contexte=["Devis UC-2026 pour Fast Group"])

    assert groq.appels == []
    assert r.dernier_choix.fournisseur == LOCAL


class TestQuandPersonneNePeutRepondre:
    """L'échec doit dire sa cause, et ce qui la lèverait.

    Mesuré le 30/08/2026 (`scripts/mesurer_sans_ollama.py`, phase 2.1) : sur un
    serveur sans Ollama, une demande classée `SENSIBLE` est routée vers la
    machine du propriétaire **et vers elle seule** — qui n'existe pas là-bas.
    L'ancien message, « Aucun fournisseur n'a pu répondre. », ne distinguait
    pas *« ce modèle n'existe pas ici »* de *« tout est tombé une minute »*.

    `test_une_demande_sensible_sans_machine_locale_dit_ce_qui_la_debloquerait`
    est le test qui porte la garantie : sur le serveur, cet échec est
    **permanent**, et un message qui ne le dit pas envoie le propriétaire
    chercher une coupure réseau qui n'existe pas.
    """

    def _tous_absents(self, mode="HYBRIDE"):
        return routeur(
            mode=mode,
            local=FauxFournisseur("local", leve=True),
            groq=FauxFournisseur("groq", disponible=False),
            deepinfra=FauxFournisseur("deepinfra", disponible=False))

    # --- Le test qui porte la garantie ---------------------------------------

    async def test_une_demande_sensible_sans_machine_locale_dit_ce_qui_la_debloquerait(self):
        r = self._tous_absents()

        with pytest.raises(RuntimeError) as echec:
            await r.generate("Prepare le devis du client Dupont pour 450000 FCFA.")

        message = str(echec.value)
        assert "Seule sa machine etait autorisee" in message, (
            "le message ne dit pas que c'est le classement qui a fermé la porte")
        assert "CLOUD_PREFERRED" in message, (
            "le message ne dit pas ce qui lèverait le blocage")

    # --- Ce que l'échec dit dans les autres cas -------------------------------

    async def test_un_echec_ordinaire_nomme_les_fournisseurs_essayes(self):
        r = self._tous_absents()

        with pytest.raises(RuntimeError) as echec:
            await r.generate("bonjour, comment vas-tu ?")

        message = str(echec.value)
        assert "groq" in message and "local" in message, (
            f"les fournisseurs essayés ne sont pas nommés : {message}")
        assert "CLOUD_PREFERRED" not in message, (
            "le cloud avait déjà le droit : proposer de l'autoriser n'a aucun sens")

    async def test_le_flux_echoue_avec_le_meme_diagnostic_que_la_generation(self):
        """Deux chemins, une seule vérité : le flux ne dit pas autre chose."""
        r = self._tous_absents()

        with pytest.raises(RuntimeError) as echec:
            async for _ in r.generate_stream("Prepare le devis du client Dupont."):
                pass

        assert "CLOUD_PREFERRED" in str(echec.value)

    async def test_en_cloud_prefere_le_message_ne_propose_plus_ce_mode(self):
        """Proposer un réglage déjà actif ferait tourner le propriétaire en rond."""
        r = self._tous_absents(mode="CLOUD_PREFERRED")

        with pytest.raises(RuntimeError) as echec:
            await r.generate("Prepare le devis du client Dupont.")

        assert "CLOUD_PREFERRED" not in str(echec.value)

    async def test_un_secret_ne_se_voit_jamais_proposer_le_cloud(self):
        """`TRES_SENSIBLE` ne sort dans aucun mode : le suggérer serait un piège."""
        r = self._tous_absents()

        with pytest.raises(RuntimeError) as echec:
            await r.generate("mon mot de passe est Azerty123")

        message = str(echec.value)
        assert "CLOUD_PREFERRED" not in message, (
            "le message invite à un réglage qui ne débloquerait rien, et qui "
            "donnerait au propriétaire l'idée d'envoyer un secret au cloud")
        assert "Azerty123" not in message, "le secret est recopié dans l'erreur"
