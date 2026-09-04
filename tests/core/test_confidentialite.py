"""Ce qui a le droit de sortir de sa machine, et ce qui n'en sort jamais.

ARENA est devenu hybride le 2026-08-28 (DEC-0009). Ce module est la seule chose
qui se tient entre son mot de passe et un serveur qui n'est pas le sien.

Le test qui porte la phase est
`test_un_secret_ne_sort_jamais_quel_que_soit_le_reglage` : aucune politique,
aucun réglage, aucune préférence ne doit pouvoir le contourner.

Le second est `test_le_doute_penche_vers_sa_machine` : une phrase qu'on ne sait
pas classer est à lui, pas au monde.
"""
import pytest

from core.models.confidentialite import (
    ORDRE,
    AutorisationCloud,
    Confidentialite,
    classer,
    cloud_autorise,
    rang,
)

MODES = ("LOCAL_ONLY", "HYBRIDE", "CLOUD_PREFERRED")


# --- Le test qui porte la phase ----------------------------------------------------

@pytest.mark.parametrize("mode", [*MODES, "CLOUD_PREFERRED", "MODE_INVENTE"])
@pytest.mark.parametrize("phrase", [
    "mon mot de passe est Azerty123",
    "voici ma cle API : sk-abcdefghijklmnopqrstuvwxyz0123",  # scanner-secrets: ignore
    "le token GitHub ghp_abcdefghijklmnopqrstuvwxyz0123",
    "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmno",
    "-----BEGIN RSA PRIVATE KEY-----",  # scanner-secrets: ignore
    "mon code pin est 4512",
])
def test_un_secret_ne_sort_jamais_quel_que_soit_le_reglage(phrase, mode):
    """Un mot de passe envoyé une fois est envoyé pour toujours."""
    classement = classer(phrase)

    assert classement.niveau is Confidentialite.TRES_SENSIBLE
    assert classement.sortie_interdite is True
    assert cloud_autorise(classement, mode).autorise is False


def test_le_doute_penche_vers_sa_machine():
    """ARENA est son assistant, pas un moteur de recherche."""
    classement = classer("zzz quelque chose d'incomprehensible")

    assert classement.niveau is Confidentialite.PRIVE


# --- Les quatre niveaux ---------------------------------------------------------------

@pytest.mark.parametrize("phrase,attendu", [
    ("Quelle est la capitale du Senegal ?", Confidentialite.PUBLIC),
    ("que veut dire BA13", Confidentialite.PUBLIC),
    ("explique-moi une boucle en python", Confidentialite.PUBLIC),
    ("je prefere travailler le matin", Confidentialite.PRIVE),
    ("rappelle-moi mon planning", Confidentialite.PRIVE),
    ("bonjour", Confidentialite.PRIVE),
    ("fais le devis du client Fast Group", Confidentialite.SENSIBLE),
    ("quel est le montant de la facture", Confidentialite.SENSIBLE),
    ("trie mon courrier", Confidentialite.SENSIBLE),
    ("mon iban commence par SN", Confidentialite.TRES_SENSIBLE),
])
def test_chaque_niveau_est_reconnu(phrase, attendu):
    assert classer(phrase).niveau is attendu


def test_un_secret_l_emporte_sur_une_question_anodine():
    """L'ordre des contrôles compte : le secret est cherché en premier."""
    assert classer("quel est le mot de passe wifi ?").niveau is Confidentialite.TRES_SENSIBLE


def test_ses_affaires_l_emportent_sur_la_connaissance_generale():
    assert classer("quelle est la facture de Fast Group ?").niveau is Confidentialite.SENSIBLE


# --- Le contexte monte le niveau, jamais l'inverse -------------------------------------

def test_une_piece_jointe_rend_une_question_anodine_sensible():
    """Une question banale posée sur un document de client ne l'est pas."""
    sans = classer("resume ca")
    avec = classer("resume ca", contexte=["Devis UC-2026-0804 pour Fast Group, 2 400 000 FCFA"])

    assert rang(avec.niveau) > rang(sans.niveau)
    assert avec.niveau is Confidentialite.SENSIBLE


def test_un_contexte_ne_fait_jamais_redescendre_le_niveau():
    avec = classer("explique-moi une boucle en python",
                   contexte=["notes personnelles du proprietaire"])

    assert rang(avec.niveau) >= rang(Confidentialite.PRIVE)


def test_un_secret_cache_dans_le_contexte_est_vu():
    """Ce qui part AVEC la demande compte autant que la demande."""
    classement = classer("resume", contexte=["GROQ_API_KEY=gsk_abcdefghijklmnopqrstuv"])

    assert classement.niveau is Confidentialite.TRES_SENSIBLE


# --- Un nom de champ n'est un secret que suivi de sa valeur --------------------------------


@pytest.mark.parametrize("phrase", [
    # Le cas mesuré le 30/08/2026 sur le serveur en ligne : la page Wikipédia
    # du Sénégal explique que le président est élu au scrutin secret. Le mot
    # « secret » y est un mot ordinaire.
    "Le president est elu au suffrage universel direct et au scrutin secret.",
    "Le secret : bien melanger avant de servir.",
    "un token est une unite lexicale en informatique",
    "ce site depose un cookie de mesure d'audience",
    "l'authorization du parlement etait requise",
])
def test_un_mot_ordinaire_dans_une_page_publique_n_est_pas_un_secret(phrase):
    """Refuser une page publique ne protège rien : ça empêche seulement de répondre.

    Mesuré le 30/08/2026 : `TRES_SENSIBLE` interdit le cloud, et aucun Ollama ne
    tourne sur le serveur — la question restait donc sans aucune réponse
    possible, pour un mot lu dans une encyclopédie.
    """
    assert classer(phrase).niveau is not Confidentialite.TRES_SENSIBLE


@pytest.mark.parametrize("phrase", [
    "USMAN_API_KEY=4409dde42d4099b9296b5cca987b7c00",
    'config: {"token": "abcdefghijklmnop"}',
    "secret = monMotDePasseTresLong",
    "session_key: aZ09-_./+xyzabcd",
    # Le possessif suffit : il annonce le secret sans en coller la valeur.
    "mon password ne marche plus",
    "j'ai perdu mon token",
])
def test_un_champ_suivi_de_sa_valeur_reste_un_secret(phrase):
    """La forme d'une configuration collée, elle, ne veut rien dire d'autre."""
    classement = classer(phrase)

    assert classement.niveau is Confidentialite.TRES_SENSIBLE
    assert classement.sortie_interdite is True


def test_le_motif_ne_recopie_jamais_la_valeur_du_secret():
    """Un motif est journalisé : y recopier la clé la ferait fuir par le journal."""
    classement = classer("USMAN_API_KEY=4409dde42d4099b9296b5cca987b7c00")

    assert "4409dde42d4099b9296b5cca987b7c00" not in classement.pourquoi()


# --- La politique ------------------------------------------------------------------------

@pytest.mark.parametrize("niveau,mode,attendu", [
    (Confidentialite.PUBLIC, "LOCAL_ONLY", False),
    (Confidentialite.PUBLIC, "HYBRIDE", True),
    (Confidentialite.PRIVE, "HYBRIDE", True),
    (Confidentialite.SENSIBLE, "HYBRIDE", False),
    (Confidentialite.SENSIBLE, "CLOUD_PREFERRED", True),
    (Confidentialite.TRES_SENSIBLE, "CLOUD_PREFERRED", False),
])
def test_la_politique_dit_ce_qui_sort(niveau, mode, attendu):
    from core.models.confidentialite import Classement

    assert cloud_autorise(Classement(niveau), mode).autorise is attendu


def test_un_mode_inconnu_refuse_au_lieu_de_supposer():
    """Devant un réglage qu'on ne comprend pas, sa machine est la seule réponse sûre."""
    from core.models.confidentialite import Classement

    autorisation = cloud_autorise(Classement(Confidentialite.PUBLIC), "N'IMPORTE QUOI")

    assert autorisation.autorise is False
    assert "local par securite" in autorisation.raison


def test_le_mode_local_seul_ne_laisse_rien_sortir():
    from core.models.confidentialite import Classement

    assert all(not cloud_autorise(Classement(niveau), "LOCAL_ONLY").autorise
               for niveau in ORDRE)


# --- Ce qui rend la décision vérifiable ---------------------------------------------------

def test_chaque_classement_dit_pourquoi():
    """Un classement qu'on ne peut pas vérifier se croit."""
    assert "mot de passe" in classer("mon mot de passe").pourquoi()
    assert "devis" in classer("fais un devis").pourquoi()


def test_le_classement_ne_recopie_jamais_le_secret():
    """Le motif nomme ce qui a déclenché, pas la valeur qui a fui."""
    secret = "sk-abcdefghijklmnopqrstuvwxyz0123"  # scanner-secrets: ignore
    classement = classer(f"ma cle est {secret}")

    assert secret not in classement.pourquoi()
    assert secret not in str(classement.to_dict())


def test_l_autorisation_porte_sa_raison():
    from core.models.confidentialite import Classement

    autorisation = cloud_autorise(Classement(Confidentialite.SENSIBLE), "HYBRIDE")

    assert isinstance(autorisation, AutorisationCloud)
    assert "reste sur sa machine" in autorisation.raison
