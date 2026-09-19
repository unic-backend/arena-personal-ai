"""Anthropic — Claude Sonnet 5. Le protocole n'est pas celui d'OpenAI.

Aucun test ici ne touche le réseau et aucun n'a besoin d'une clé : le client
HTTP est injecté, et chaque test lit ce qu'ARENA a réellement mis dans la
requête.

Cinq tests portent l'étape, parce qu'ils décrivent cinq façons dont ce fichier
pourrait mentir :

- `test_la_cle_ne_fuit_jamais` : une clé reprise dans un message d'erreur finit
  dans un journal, et un journal se colle dans une conversation.
- `test_sans_cle_le_fournisseur_est_absent_et_ne_tente_rien` : sans clé, ARENA
  ne doit rien envoyer du tout — absent n'est pas en panne.
- `test_le_corps_ne_porte_rien_que_sonnet_5_refuse` : `temperature`,
  `budget_tokens` et compagnie rendent un 400. Les envoyer casserait chaque
  réponse, et le test le dit avant le réseau.
- `test_un_refus_est_rapporte_comme_un_refus` : Claude peut décliner (HTTP 200).
  Rendre le texte vide ferait passer un refus pour une panne.
- `test_le_flux_ne_laisse_pas_passer_la_reflexion` : un `thinking_delta` porte
  du texte lui aussi. Le laisser passer ferait lire le raisonnement à la place
  de la réponse.
"""
import asyncio
import json

import pytest

from core.models.anthropic_provider import EFFORTS, VERSION_API, AnthropicProvider

CLE = "sk-ant-cle-de-test-tres-secrete"


# --- Le faux service ---------------------------------------------------------------

def sse(*evenements):
    """Les lignes d'un flux SSE, au format exact d'Anthropic."""
    lignes = []
    for evenement in evenements:
        lignes.append(f"event: {evenement['type']}")
        lignes.append(f"data: {json.dumps(evenement)}")
        lignes.append("")
    return lignes


def debut(entree=None, sortie=None):
    usage = {}
    if entree is not None:
        usage["input_tokens"] = entree
    if sortie is not None:
        usage["output_tokens"] = sortie
    return {"type": "message_start", "message": {"id": "msg_1", "usage": usage}}


def mot(texte):
    return {"type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": texte}}


def reflexion(texte):
    return {"type": "content_block_delta", "index": 0,
            "delta": {"type": "thinking_delta", "thinking": texte}}


def fin(sortie=None, stop_reason="end_turn"):
    evenement = {"type": "message_delta", "delta": {"stop_reason": stop_reason}}
    if sortie is not None:
        evenement["usage"] = {"output_tokens": sortie}
    return evenement


class FausseReponse:
    def __init__(self, charge=None, lignes=None, leve=None, coupe_a=None):
        self._charge = charge
        self._lignes = lignes or []
        self._leve = leve
        self._coupe_a = coupe_a

    def raise_for_status(self):
        if self._leve is not None:
            raise self._leve

    def json(self):
        return self._charge

    async def aiter_lines(self):
        for index, ligne in enumerate(self._lignes):
            if self._coupe_a is not None and index == self._coupe_a:
                raise RuntimeError(f"le service a coupe (cle {CLE})")
            yield ligne


class _Flux:
    def __init__(self, reponse):
        self._reponse = reponse

    async def __aenter__(self):
        return self._reponse

    async def __aexit__(self, *args):
        return False


class FauxClient:
    """Un client HTTP de test : il note ce qu'on lui demande, sans réseau."""

    def __init__(self, charge=None, lignes=None, leve=None, coupe_a=None):
        self.appels = []
        self._charge = charge
        self._lignes = lignes
        self._leve = leve
        self._coupe_a = coupe_a

    async def get(self, url, headers=None, **kw):
        self.appels.append(("GET", url, dict(headers or {}), None))
        return FausseReponse(charge=self._charge, leve=self._leve)

    async def post(self, url, headers=None, json=None, **kw):
        self.appels.append(("POST", url, dict(headers or {}), json))
        return FausseReponse(charge=self._charge, leve=self._leve)

    def stream(self, methode, url, headers=None, json=None, **kw):
        self.appels.append((methode, url, dict(headers or {}), json))
        return _Flux(FausseReponse(lignes=self._lignes, leve=self._leve,
                                   coupe_a=self._coupe_a))

    async def aclose(self):
        pass

    @property
    def corps(self):
        """Les corps JSON envoyés, dans l'ordre."""
        return [appel[3] for appel in self.appels if appel[3] is not None]


def fournisseur(client=None, **kw):
    """Un fournisseur configuré pour les tests : une clé factice, jamais réelle."""
    options = {"api_key": CLE, "model_name": "claude-sonnet-5", "max_tokens": 1234}
    options.update(kw)
    return AnthropicProvider(client=client, **options)


def reponse_texte(contenu="Bonjour Saer.", usage=None):
    charge = {"id": "msg_1", "stop_reason": "end_turn",
              "content": [{"type": "text", "text": contenu}]}
    if usage is not None:
        charge["usage"] = usage
    return charge


def lire_flux(fourni, prompt="bonjour", system_prompt=None):
    async def _lire():
        return [m async for m in fourni.generate_stream(prompt, system_prompt)]
    return asyncio.run(_lire())


# --- Absent sans clé --------------------------------------------------------------

def test_sans_cle_le_fournisseur_est_absent_et_ne_tente_rien():
    """Pas de clé : `configure` est faux et rien n'est envoyé.

    C'est ce qui garantit qu'installer ce fichier ne change RIEN tant que le
    propriétaire n'a pas posé sa clé : l'aiguilleur écarte un fournisseur non
    configuré avant même de le sonder.
    """
    client = FauxClient(charge={"id": "claude-sonnet-5"})
    sans_cle = AnthropicProvider(api_key="", model_name="claude-sonnet-5",
                                 client=client)

    assert sans_cle.configure is False
    assert asyncio.run(sans_cle.is_available()) is False
    assert client.appels == [], "aucune requete ne doit partir sans cle"


def test_un_modele_vide_rend_le_fournisseur_absent(monkeypatch):
    """`ANTHROPIC_MODEL=` vidé : une clé sans modèle n'a personne à appeler.

    Le cas n'est pas théorique — c'est ce que donne une variable posée puis
    effacée dans Railway. Mieux vaut ABSENT qu'un 404 à chaque phrase.
    """
    from apps.backend import config

    monkeypatch.setattr(config, "ANTHROPIC_MODELE", "")
    assert AnthropicProvider(api_key=CLE, model_name="").configure is False


# --- La clé ne sort pas -------------------------------------------------------------

def test_la_cle_ne_fuit_jamais():
    """Le message d'erreur retenu ne contient jamais la clé."""
    client = FauxClient(leve=RuntimeError(f"401 unauthorized: {CLE}"))
    fourni = fournisseur(client)

    with pytest.raises(RuntimeError):
        asyncio.run(fourni.generate("bonjour"))

    assert CLE not in fourni.derniere_mesure.erreur
    assert "[cle retiree]" in fourni.derniere_mesure.erreur


def test_la_cle_ne_fuit_pas_non_plus_quand_le_flux_casse():
    """Un flux coupé en cours de route passe par le même nettoyage."""
    fourni = fournisseur(FauxClient(lignes=sse(debut(), mot("Bon")), coupe_a=3))

    with pytest.raises(RuntimeError):
        lire_flux(fourni)

    assert CLE not in fourni.derniere_mesure.erreur


# --- La forme exacte de la requête ----------------------------------------------------

def test_l_authentification_suit_le_protocole_d_anthropic():
    """`x-api-key` et `anthropic-version`, pas `Authorization: Bearer`."""
    client = FauxClient(charge=reponse_texte())
    asyncio.run(fournisseur(client).generate("bonjour"))

    _, url, entetes, _ = client.appels[0]
    assert url.endswith("/messages")
    assert entetes["x-api-key"] == CLE
    assert entetes["anthropic-version"] == VERSION_API
    assert "Authorization" not in entetes


def test_le_prompt_systeme_est_un_parametre_pas_un_message():
    """`system` est à part chez Anthropic. Le glisser dans `messages` le perdrait."""
    client = FauxClient(charge=reponse_texte())
    asyncio.run(fournisseur(client).generate("bonjour", system_prompt="Tu es Usman."))

    corps = client.corps[0]
    assert corps["system"] == "Tu es Usman."
    assert corps["messages"] == [{"role": "user", "content": "bonjour"}]
    assert all(message["role"] != "system" for message in corps["messages"])


def test_sans_prompt_systeme_la_cle_system_est_absente():
    """Un `system` vide n'est pas envoyé : une chaîne vide n'est pas une consigne."""
    client = FauxClient(charge=reponse_texte())
    asyncio.run(fournisseur(client).generate("bonjour"))

    assert "system" not in client.corps[0]


def test_le_corps_ne_porte_rien_que_sonnet_5_refuse():
    """`temperature`, `top_p`, `top_k` et `budget_tokens` rendent un 400.

    Ce test est la seule chose qui empêche quelqu'un de les « rétablir » un
    jour en croyant bien faire : chez Sonnet 5, les omettre n'est pas une
    simplification, c'est la seule forme valide.
    """
    client = FauxClient(charge=reponse_texte())
    asyncio.run(fournisseur(client).generate("bonjour", system_prompt="consigne"))

    corps = client.corps[0]
    for interdit in ("temperature", "top_p", "top_k", "budget_tokens"):
        assert interdit not in corps
    assert "budget_tokens" not in corps["thinking"]


def test_le_corps_porte_max_tokens_la_reflexion_et_l_effort():
    """`max_tokens` est obligatoire ; la réflexion adaptative est le mode allumé."""
    client = FauxClient(charge=reponse_texte())
    asyncio.run(fournisseur(client, max_tokens=4096, effort="max").generate("bonjour"))

    corps = client.corps[0]
    assert corps["model"] == "claude-sonnet-5"
    assert corps["max_tokens"] == 4096
    assert corps["thinking"] == {"type": "adaptive"}
    assert corps["output_config"] == {"effort": "max"}
    assert corps["stream"] is False


def test_le_flux_envoie_le_meme_corps_que_la_reponse_complete():
    """Une seule forme de requête, au drapeau `stream` près."""
    complet = FauxClient(charge=reponse_texte())
    asyncio.run(fournisseur(complet).generate("bonjour", system_prompt="consigne"))

    en_flux = FauxClient(lignes=sse(debut(), mot("Bon"), fin()))
    lire_flux(fournisseur(en_flux), system_prompt="consigne")

    assert en_flux.corps[0].pop("stream") is True
    assert complet.corps[0].pop("stream") is False
    assert complet.corps[0] == en_flux.corps[0]


@pytest.mark.parametrize("effort", EFFORTS)
def test_chaque_effort_declare_est_accepte(effort):
    client = FauxClient(charge=reponse_texte())
    asyncio.run(fournisseur(client, effort=effort).generate("bonjour"))

    assert client.corps[0]["output_config"]["effort"] == effort


def test_un_effort_inconnu_retombe_sur_high_sans_appeler_le_service():
    """Un réglage faux est refusé ici, avec sa raison, pas par un 400 distant."""
    client = FauxClient(charge=reponse_texte())
    fourni = fournisseur(client, effort="turbo")

    assert fourni.effort == "high"
    asyncio.run(fourni.generate("bonjour"))
    assert client.corps[0]["output_config"]["effort"] == "high"


# --- Ce que la réponse porte ------------------------------------------------------

def test_seuls_les_blocs_de_texte_forment_la_reponse():
    """Une réponse Claude est une LISTE de blocs typés.

    Prendre `content[0]` marcherait jusqu'au jour où le premier bloc serait une
    réflexion — et ce jour-là son écran afficherait le raisonnement à la place
    de la réponse.
    """
    charge = {"stop_reason": "end_turn", "content": [
        {"type": "thinking", "thinking": "je reflechis a la question"},
        {"type": "text", "text": "Bonjour "},
        {"type": "text", "text": "Saer."},
    ]}

    assert asyncio.run(fournisseur(FauxClient(charge=charge)).generate("b")) == \
        "Bonjour Saer."


def test_une_reponse_sans_bloc_de_texte_rend_une_chaine_vide():
    """Vide, pas inventé. L'aiguilleur replie sur une réponse vide."""
    charge = {"stop_reason": "end_turn",
              "content": [{"type": "thinking", "thinking": "…"}]}

    assert asyncio.run(fournisseur(FauxClient(charge=charge)).generate("b")) == ""


def test_une_charge_illisible_rend_une_chaine_vide():
    """Un service qui répond autre chose que du JSON attendu n'invente rien."""
    assert asyncio.run(fournisseur(FauxClient(charge="<html>502</html>")
                                   ).generate("b")) == ""


def test_un_refus_est_rapporte_comme_un_refus():
    """Claude décline : HTTP 200, `stop_reason == "refusal"`, aucun texte.

    Rendre une chaîne vide ferait replier l'aiguilleur sur un autre
    fournisseur, qui refuserait aussi — et le propriétaire verrait « aucun
    fournisseur n'a pu répondre » au lieu de la vérité.
    """
    charge = {"stop_reason": "refusal", "content": [],
              "stop_details": {"type": "refusal", "category": "dangerous_content"}}
    texte = asyncio.run(fournisseur(FauxClient(charge=charge)).generate("…"))

    assert "refuse" in texte.lower()
    assert "dangerous_content" in texte


def test_un_refus_sans_categorie_le_dit_au_lieu_de_l_inventer():
    charge = {"stop_reason": "refusal", "content": []}
    texte = asyncio.run(fournisseur(FauxClient(charge=charge)).generate("…"))

    assert "non precisee" in texte


# --- Les jetons, et ce qu'on ne devine pas ---------------------------------------

def test_les_jetons_viennent_de_la_reponse():
    client = FauxClient(charge=reponse_texte(
        usage={"input_tokens": 120, "output_tokens": 45}))
    fourni = fournisseur(client)
    asyncio.run(fourni.generate("bonjour"))

    assert fourni.derniere_mesure.jetons_entree == 120
    assert fourni.derniere_mesure.jetons_sortie == 45


def test_sans_usage_les_jetons_restent_inconnus():
    """`None`, jamais `0` : un zéro se lirait « gratuit »."""
    fourni = fournisseur(FauxClient(charge=reponse_texte(usage=None)))
    asyncio.run(fourni.generate("bonjour"))

    assert fourni.derniere_mesure.jetons_entree is None
    assert fourni.derniere_mesure.jetons_sortie is None


def test_un_usage_non_numerique_est_ignore_plutot_que_recopie():
    fourni = fournisseur(FauxClient(charge=reponse_texte(
        usage={"input_tokens": "beaucoup"})))
    asyncio.run(fourni.generate("bonjour"))

    assert fourni.derniere_mesure.jetons_entree is None


# --- Le flux ------------------------------------------------------------------------

def test_le_flux_rend_les_morceaux_dans_l_ordre():
    client = FauxClient(lignes=sse(debut(10), mot("Bon"), mot("jour "), mot("Saer."),
                                   fin(3)))

    assert lire_flux(fournisseur(client)) == ["Bon", "jour ", "Saer."]


def test_le_flux_ne_laisse_pas_passer_la_reflexion():
    """Un `thinking_delta` porte du texte. Il n'a rien à faire sur son écran."""
    client = FauxClient(lignes=sse(debut(), reflexion("hmm, une cloison…"),
                                   mot("Bonjour."), fin()))

    assert lire_flux(fournisseur(client)) == ["Bonjour."]


def test_le_flux_mesure_le_premier_mot_et_releve_les_jetons_aux_deux_bouts():
    """L'entrée arrive au `message_start`, la sortie au `message_delta`.

    Les relever au même endroit perdrait l'un des deux — et un compte de jetons
    à moitié faux vaut moins qu'un `None` honnête.
    """
    client = FauxClient(lignes=sse(debut(entree=120), mot("Bon"), mot("jour"),
                                   fin(sortie=45)))
    fourni = fournisseur(client)
    lire_flux(fourni)

    mesure = fourni.derniere_mesure
    assert mesure.secondes_premier_jeton is not None
    assert mesure.secondes_total is not None
    assert (mesure.jetons_entree, mesure.jetons_sortie) == (120, 45)


def test_un_message_delta_n_efface_pas_les_jetons_d_entree():
    """Le `message_delta` porte la sortie et **pas** l'entrée — c'est la forme réelle.

    Reprendre son `input_tokens` absent comme une valeur effacerait le compte
    annoncé au `message_start`, et chaque appel serait facturé « entrée
    inconnue » alors que le service l'avait dit.
    """
    client = FauxClient(lignes=sse(debut(entree=120, sortie=1), mot("Bon"),
                                   fin(sortie=45)))
    fourni = fournisseur(client)
    lire_flux(fourni)

    assert fourni.derniere_mesure.jetons_entree == 120


def test_un_flux_vide_ne_pretend_pas_avoir_eu_un_premier_mot():
    """Aucun morceau : `premier_jeton` reste `None`, pas « instantané »."""
    fourni = fournisseur(FauxClient(lignes=sse(debut(), fin())))

    assert lire_flux(fourni) == []
    assert fourni.derniere_mesure.secondes_premier_jeton is None


def test_une_ligne_illisible_ne_casse_pas_une_reponse_commencee():
    """Un flux réel porte des lignes `event:`, des lignes vides, et parfois pire."""
    lignes = ["event: message_start", "data: {pas du json}", "",
              f"data: {json.dumps(mot('Bon'))}", ": commentaire sse",
              f"data: {json.dumps(mot('jour'))}"]

    assert lire_flux(fournisseur(FauxClient(lignes=lignes))) == ["Bon", "jour"]


def test_un_flux_coupe_garde_ce_qui_etait_deja_mesure():
    """Coupé avant la fin : les jetons de sortie annoncés plus tard manquent,
    et ils restent `None` plutôt que devinés."""
    client = FauxClient(lignes=sse(debut(entree=120), mot("Bon"), fin(sortie=45)),
                        coupe_a=5)
    fourni = fournisseur(client)

    with pytest.raises(RuntimeError):
        lire_flux(fourni)

    assert fourni.derniere_mesure.jetons_entree == 120
    assert fourni.derniere_mesure.jetons_sortie is None


# --- La sonde de disponibilité ------------------------------------------------------

def test_la_sonde_demande_la_fiche_du_modele_configure():
    """La sonde la moins chère qui prouve à la fois la clé ET l'existence du modèle."""
    client = FauxClient(charge={"id": "claude-sonnet-5", "type": "model"})
    fourni = fournisseur(client)

    assert asyncio.run(fourni.is_available()) is True
    methode, url, _, _ = client.appels[0]
    assert (methode, url.endswith("/models/claude-sonnet-5")) == ("GET", True)


def test_une_sonde_qui_leve_rend_indisponible_sans_propager():
    """Une panne est un état, pas une exception qui remonte jusqu'au chat."""
    client = FauxClient(leve=RuntimeError(f"403 forbidden: {CLE}"))

    assert asyncio.run(fournisseur(client).is_available()) is False


def test_une_fiche_sans_identifiant_ne_compte_pas_pour_une_disponibilite():
    assert asyncio.run(fournisseur(FauxClient(charge={})).is_available()) is False
