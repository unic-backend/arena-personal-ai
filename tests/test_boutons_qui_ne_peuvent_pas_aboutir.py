"""Un bouton « Confirmer » n'est offert que si le moteur peut aboutir.

**Mesuré le 03/09/2026 à 02:46.** Le propriétaire reçoit deux boutons
« Confirmer » pour une synthèse vocale, juste sous un message disant que
VoiceStudio ne répond pas sur `http://127.0.0.1:3900`. Les boutons étaient
offerts quand même : confirmer ne pouvait qu'échouer, et il l'apprenait après
avoir appuyé.

C'est la faute de la nuit sous sa forme la plus chère : une phrase qui promet
ce qu'elle ne fait pas coûte une lecture ; un bouton qui ne peut pas aboutir
coûte un geste, puis la même déception.

La règle de doute est l'inverse de la prudence naïve : **une sonde qui échoue
laisse le bouton.** On n'interdit pas une action parce qu'on n'a pas su la
mesurer — ce serait remplacer un faux « ça marche » par un faux « c'est
cassé ».
"""
from pathlib import Path

from core.connectors.base import EtatSante, Sante

RACINE = Path(__file__).resolve().parent.parent
VUE = RACINE / "apps" / "pwa" / "src" / "components" / "chat" / "ChatMessage.tsx"


def _etat(monkeypatch, sante):
    """Rend `_etat_du_moteur` avec un connecteur double."""
    from apps.backend.routers import pwa_gateway

    class _Connecteur:
        def sonder(self):
            if isinstance(sante, Exception):
                raise sante
            return sante

    class _Registre:
        def obtenir(self, nom):
            return _Connecteur()

    monkeypatch.setattr(pwa_gateway, "registre", _Registre())
    return pwa_gateway._etat_du_moteur("audio")


def test_un_moteur_operationnel_garde_son_bouton(monkeypatch):
    etat = _etat(monkeypatch, Sante(etat=EtatSante.OPERATIONNEL))

    assert etat["disponible"] is True
    assert etat["indisponible_raison"] == ""


def test_un_moteur_absent_retire_le_bouton_et_dit_pourquoi(monkeypatch):
    etat = _etat(monkeypatch, Sante(
        etat=EtatSante.NON_CONFIGURE,
        message="VoiceStudio ne repond pas",
        ce_qui_manque="http://127.0.0.1:3900"))

    assert etat["disponible"] is False
    assert "VoiceStudio" in etat["indisponible_raison"]
    assert "127.0.0.1:3900" in etat["indisponible_raison"], (
        "la raison ne dit pas ou le moteur etait attendu")


def test_une_sonde_qui_leve_laisse_le_bouton(monkeypatch):
    """**La règle qui compte, et elle va contre l'instinct.**

    Ne pas savoir mesurer n'est pas un refus. Retirer le bouton ici
    remplacerait un faux « ça marche » par un faux « c'est cassé » — et le
    propriétaire perdrait une action qui aurait abouti.
    """
    etat = _etat(monkeypatch, OSError("socket"))

    assert etat["disponible"] is True


def test_linterface_nyoffre_pas_confirmer_quand_le_moteur_est_absent():
    vue = VUE.read_text(encoding="utf-8")

    assert "a.disponible === false ?" in vue, (
        "l'interface ignore l'etat du moteur et offre « Confirmer » quand meme")

    # La branche « moteur absent » va jusqu'au `) : (` qui ouvre la branche
    # normale. Couper sur `): (` sans l'espace ne trouvait rien et mesurait
    # alors tout le reste du fichier — donc un test qui ne prouvait rien.
    bloc = vue.split("a.disponible === false ?")[1].split(") : (")[0]
    assert "'annuler'" in bloc, (
        "sans « Annuler », l'action resterait dans la file sans moyen de la vider")
    assert "'confirmer'" not in bloc, (
        "« Confirmer » est encore propose pour un moteur qui ne repond pas")


def test_un_serveur_plus_ancien_ne_perd_pas_ses_boutons():
    """`disponible` absent (serveur antérieur à ce correctif) doit laisser le
    bouton : `=== false` et non `!a.disponible`."""
    vue = VUE.read_text(encoding="utf-8")

    assert "!a.disponible" not in vue, (
        "un serveur qui n'envoie pas le champ verrait tous ses boutons retires")
