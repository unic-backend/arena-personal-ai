"""Le chat ne répond jamais depuis la démo du navigateur.

**Mesuré le 03/09/2026, sur le téléphone du propriétaire.** Il écrit
« Bonjour ». Son serveur était décroché, donc `chatStore` retombait
silencieusement sur `localTransport` — et une démo intégrée au navigateur lui
a répondu, **signée Usman**, en promettant « exécution terminal réelle » et
« une vraie arborescence projet ». Les deux sont faux : cette démo travaille
sur un projet inventé nommé *pulseboard*, gardé dans le `localStorage` du
téléphone. Rien à l'écran ne la distinguait de son IA.

C'est le défaut que tout ce dépôt refuse ailleurs — annoncer une capacité
qu'on n'a pas — et il se produisait au seul endroit qu'il lit vraiment.

Ces tests sont écrits en Python parce que `apps/pwa` n'a pas de lanceur de
tests (`docs/REPRISE.md`, *Ce qui reste ouvert*). Ils lisent le source : c'est
grossier, mais une garde grossière qui existe vaut mieux qu'une garde élégante
qui n'existe pas.
"""
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
PWA = RACINE / "apps" / "pwa" / "src"

CHAT_STORE = PWA / "lib" / "store" / "chatStore.ts"
TRANSPORT = PWA / "lib" / "activity" / "transport.ts"


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _code_numerote(source: str) -> list[tuple[int, str]]:
    """Les lignes de code, numerotees, commentaires exclus.

    Un `startswith("*")` ne suffit pas : les blocs `/* ... */` de ce depot
    alignent leur texte sans etoile de continuation, et le premier essai de
    ce test a donc signale son propre commentaire d'explication.
    """
    lignes, dans_bloc = [], False
    for numero, brute in enumerate(source.splitlines(), 1):
        ligne = brute.strip()
        if dans_bloc:
            if "*/" in ligne:
                dans_bloc = False
            continue
        if ligne.startswith("/*"):
            if "*/" not in ligne:
                dans_bloc = True
            continue
        if ligne.startswith(("//", "*")):
            continue
        lignes.append((numero, brute))
    return lignes


def _lignes_de_code(source: str) -> list[str]:
    """Les lignes de code seules — les commentaires sont retires.

    Necessaire : la directive eslint du transport hors ligne contient le mot
    « yield » sans etre du code, et le test le lisait comme une production de
    texte.
    """
    return [ligne.strip() for ligne in source.splitlines()
            if not ligne.strip().startswith(("//", "*", "/*"))]


def test_le_chat_ne_choisit_plus_le_transport_lui_meme():
    """Trois endroits décidaient chacun de leur côté, et chacun pouvait dériver.

    Un seul point de décision (`choisirTransport`) : la règle ne peut plus
    être vraie à deux endroits sur trois.
    """
    source = _lire(CHAT_STORE)

    assert "localTransport" not in source, (
        "chatStore choisit encore la demo du navigateur lui-meme")
    assert source.count("choisirTransport(") >= 3, (
        "les trois envois (message, regeneration, reprise) doivent passer "
        "par le meme point de decision")


def test_sans_serveur_rien_ne_repond_a_sa_place():
    """`offlineTransport` ne rend pas de texte. Il refuse, et dit pourquoi."""
    source = _lire(TRANSPORT)

    assert "offlineTransport" in source
    assert "BACKEND_OFFLINE" in source

    # Le corps de offlineTransport ne doit produire aucun jeton : un transport
    # qui « repondrait quand meme quelque chose » serait le defaut d'origine.
    # Les commentaires sont retires d'abord — la directive eslint du fichier
    # contient le mot « yield » sans etre du code.
    corps = source.split("export const offlineTransport")[1].split("export ")[0]
    code = _lignes_de_code(corps)
    assert not any("yield" in ligne for ligne in code), (
        "le transport hors ligne produit du texte : c'est exactement ce qu'on "
        "vient de retirer")
    assert any("BACKEND_OFFLINE" in ligne for ligne in code), (
        "il doit refuser explicitement, pas rendre une reponse vide")


def test_le_repli_sans_serveur_est_le_refus_et_rien_dautre():
    """**La garde qui compte, et elle a failli manquer.**

    Le premier sabotage tenté le 03/09/2026 — remettre `localTransport` comme
    valeur de repli de `choisirTransport` — passait tous les autres tests de
    ce fichier. C'est pourtant *exactement* le défaut d'origine qui revient :
    `offlineTransport` existerait toujours, sans être jamais choisi.

    Un test qui vérifie qu'une pièce existe ne vérifie pas qu'elle est
    branchée.
    """
    source = _lire(TRANSPORT)
    corps = source.split("export function choisirTransport")[1]
    code = _lignes_de_code(corps)

    retours = [ligne for ligne in code if ligne.startswith("return ")]
    assert retours, "choisirTransport ne rend plus rien"
    assert retours[-1] == "return offlineTransport;", (
        f"le repli sans serveur est « {retours[-1]} » : la demo redevient la "
        "reponse par defaut, ce qui est le defaut mesure le 03/09/2026")

    # `localTransport` n'est atteignable que par la garde `surAppareil`.
    lignes_locales = [ligne for ligne in code if "localTransport" in ligne]
    assert all("surAppareil" in ligne for ligne in lignes_locales), (
        "localTransport est atteignable hors du chemin « sur appareil »")


def test_la_video_reste_sur_lappareil():
    """Le montage vidéo tourne vraiment ici — il ne tombe pas avec la démo.

    C'est la moitié qu'il ne faut pas casser en réparant l'autre : sans ce
    test, supprimer le repli emporterait une capacité qui, elle, est réelle.
    """
    transport = _lire(TRANSPORT)
    store = _lire(CHAT_STORE)

    assert "surAppareil" in transport, "le transport ne distingue plus ce qui tourne ici"
    assert "surAppareil" in store, "le chat ne marque plus la video comme locale"
    assert "localTransport" in transport, (
        "le transport sur appareil a disparu : le montage video n'a plus de voie")


def test_le_message_hors_ligne_existe_dans_les_deux_langues():
    """Une clé manquante afficherait la clé brute — donc rien de compréhensible."""
    i18n = _lire(PWA / "lib" / "i18n" / "index.ts")

    assert i18n.count("'chat.offline':") == 2, (
        "il faut la version anglaise et la version francaise")


def test_le_message_dit_que_rien_na_repondu():
    """Le fond du correctif tient dans cette phrase : il doit savoir que
    **personne** n'a répondu, pas qu'une réponse a échoué."""
    i18n = _lire(PWA / "lib" / "i18n" / "index.ts")

    ligne = [x for x in i18n.splitlines() if "'chat.offline':" in x and "répondu" in x]
    assert ligne, "la version francaise ne dit pas que rien n'a repondu"


@pytest.mark.parametrize("mensonge", [
    "exécution terminal réelle",
    "vraie arborescence projet",
    # La phrase d'accueil elle-meme. « atelier IA observable » seul ne
    # conviendrait pas : c'est aussi le slogan de la marque
    # (`brand.sub`), et la chronologie d'activite, elle, est bien reelle.
    "Chaque outil que j",
    "pulseboard",
])
def test_les_promesses_fausses_ont_disparu_du_code_servi(mensonge):
    """Ces phrases étaient sur son écran le 03/09/2026, et elles étaient fausses.

    Elles ne sont plus seulement inatteignables : elles n'existent plus. Le
    test cherche dans tout ce que la PWA embarque, sauf les commentaires qui
    racontent ce qui a été retiré — un dépôt qui efface aussi la raison de
    l'effacement se fait remettre le défaut par le premier qui trouve le
    manque suspect.
    """
    trouves = []
    for chemin in PWA.rglob("*.ts*"):
        for numero, ligne in _code_numerote(_lire(chemin)):
            if mensonge.lower() in ligne.lower():
                trouves.append(f"{chemin.relative_to(PWA)}:{numero}")

    assert not trouves, f"« {mensonge} » est encore servi : {trouves}"


def test_les_modules_de_la_demo_nexistent_plus():
    """Le faux projet, le faux index, le faux terminal.

    Les garder « au cas où » les rendrait réactivables par un import d'une
    ligne — et c'est un import d'une ligne qui a produit le défaut.
    """
    for mort in ("vfs.ts", "exec.ts", "knowledge.ts", "knowledgeFr.ts"):
        assert not (PWA / "lib" / "agent" / mort).exists(), (
            f"{mort} est revenu : le faux projet peut se rebrancher")


def test_le_transport_sur_appareil_ne_sert_plus_que_ce_qui_tourne_ici():
    """`runAgent` n'a plus de voie par défaut qui produirait du texte."""
    source = _lire(PWA / "lib" / "agent" / "orchestrator.ts")

    for disparu in ("pipelineChat", "pipelineFixBuild", "pipelineResearch",
                    "pipelineCalc", "pipelineCode", "pipelineCommand",
                    "detectIntent"):
        assert f"function* {disparu}" not in source and f"function {disparu}" not in source, (
            f"{disparu} est de retour")

    assert "pipelineVideo" in source, "le montage video a ete emporte avec la demo"
    assert "BACKEND_OFFLINE" in source, (
        "arriver ici hors video doit refuser, pas rendre un texte")


def test_lerreur_hors_ligne_ne_se_prefixe_pas_de_moteur_en_erreur():
    """« Le moteur a renvoyé une erreur » désignerait un moteur qui n'a
    justement pas répondu — c'est ce malentendu qui faisait passer la démo
    pour son IA."""
    vue = _lire(PWA / "components" / "chat" / "ChatMessage.tsx")
    store = _lire(CHAT_STORE)

    assert "estMessageDeLiaison(msg.error)" in vue, (
        "le message hors ligne est prefixe comme une erreur moteur")
    # La comparaison texte a texte etait fragile : celui de `offlineWhy`
    # porte une raison variable. Le test verifie que les TROIS cles y passent,
    # sinon l'un des trois messages reprendrait le prefixe.
    cles = store.split("CLES_DE_LIAISON = [")[1].split("]")[0]
    for cle in ("chat.offline", "chat.offlineWhy", "chat.noBackend"):
        assert cle in cles, f"{cle} reprendrait le prefixe « erreur moteur »"


BACKEND_STORE = PWA / "lib" / "store" / "backendStore.ts"


class TestReconnexion:
    """Une coupure passagère ne déconnecte plus.

    **Mesure du 03/09/2026 :** `test()` mettait `enabled: false` dès la
    première sonde ratée, et l'enregistrait. Un tunnel, un changement
    d'antenne, et son IA restait injoignable jusqu'à ce qu'il ouvre le panneau
    backend pour la rebrancher à la main. C'est le mécanisme qui l'a amené,
    ce soir-là, à parler à la démo sans le savoir.
    """

    def test_la_sonde_reessaie_avant_dabandonner(self):
        source = _lire(BACKEND_STORE)

        assert "ATTENTES" in source, "aucune temporisation entre deux tentatives"
        assert "for (let essai" in source, "la sonde ne fait toujours qu'un seul essai"

    def test_une_sonde_ratee_ne_debranche_plus_le_serveur(self):
        """**La garde qui compte.** `enabled` dit ce que le propriétaire veut ;
        seul le bouton « Déconnecter » le change. L'état du réseau, lui, va
        dans `status`.
        """
        source = _lire(BACKEND_STORE)
        corps = source.split("async test()")[1].split("disconnect:")[0]

        for ligne in _lignes_de_code(corps):
            assert "enabled: false" not in ligne, (
                "la sonde debranche encore le serveur : une coupure passagere "
                "redevient une deconnexion durable")

    def test_le_bouton_deconnecter_debranche_toujours(self):
        """Retirer la déconnexion automatique ne doit pas retirer la manuelle :
        c'est la seule façon pour lui de reprendre la main."""
        source = _lire(BACKEND_STORE)
        corps = source.split("disconnect:")[1][:400]

        # Les DEUX doivent debrancher : `set` pour l'ecran, `persist` pour le
        # prochain demarrage. N'en verifier qu'un laissait passer le sabotage
        # du 03/09/2026 — `set` remis a `true`, `persist` intact, test vert.
        lignes = _lignes_de_code(corps)
        etat = [x for x in lignes if x.startswith("set(")]
        garde = [x for x in lignes if x.startswith("persist(")]
        assert etat and "enabled: false" in etat[0], (
            "le bouton « Deconnecter » ne debranche plus a l'ecran")
        assert garde and "enabled: false" in garde[0], (
            "le debranchement est oublie au prochain demarrage")

    def test_le_retour_du_reseau_relance_la_sonde(self):
        source = _lire(BACKEND_STORE)

        assert "addEventListener('online'" in source, (
            "rien ne se reconnecte quand le reseau revient : il faudrait "
            "toujours ouvrir le panneau et appuyer sur « Re-tester »")

    def test_le_retour_du_reseau_ne_sonde_pas_un_serveur_absent(self):
        """Re-sonder une adresse vide afficherait une erreur à quelqu'un qui
        n'a jamais demandé de serveur."""
        source = _lire(BACKEND_STORE)
        bloc = source.split("addEventListener('online'")[1][:400]

        assert "enabled" in bloc and "url" in bloc, (
            "la reprise ne verifie pas qu'un serveur est reellement branche")


class TestRepriseApresLeDefaut:
    """La coupure écrite par l'ancien défaut dort encore sur son téléphone.

    **Mesuré le 03/09/2026 à 02:19.** Le correctif de 01:36 empêchait une
    nouvelle coupure ; il n'effaçait pas celle déjà enregistrée. Le
    propriétaire revenait donc sur le même écran, et la seule issue était
    d'aller rebrancher à la main — lui faire réparer le défaut.
    """

    def test_une_coupure_non_signee_est_annulee_au_demarrage(self):
        source = _lire(BACKEND_STORE)
        corps = source.split("function load(")[1].split("function persist(")[0]

        assert "debrancheParLui" in corps, (
            "rien ne distingue une coupure subie d'une coupure choisie")
        assert "enabled: true" in corps, (
            "une coupure jamais choisie reste en place : il doit encore "
            "rebrancher a la main")

    def test_le_bouton_deconnecter_signe_sa_coupure(self):
        """Sinon la reprise ci-dessus annulerait aussi son choix à lui."""
        source = _lire(BACKEND_STORE)
        corps = source.split("disconnect:")[1][:400]

        assert "true" in corps.split("persist(")[1][:120], (
            "la deconnexion volontaire n'est pas signee : elle serait annulee "
            "au prochain demarrage")

    def test_la_veille_existe_vraiment(self):
        """**Le message affiché dit « il est réessayé tout seul ».**

        Sans cette veille, ce serait une promesse de plus — le défaut même
        qu'on vient de retirer de l'écran d'accueil. Une phrase et le code qui
        la tient s'écrivent ensemble.
        """
        source = _lire(BACKEND_STORE)

        assert "programmerVeille" in source, "rien ne reessaie pendant la panne"
        assert "VEILLE_MAX" in source, (
            "aucun plafond : une adresse morte serait martelee toute la nuit")

    def test_le_message_ne_promet_que_ce_qui_existe(self):
        """Si la veille disparaît, la phrase devient fausse — et ce test tombe."""
        i18n = _lire(PWA / "lib" / "i18n" / "index.ts")
        store = _lire(BACKEND_STORE)

        promet = "réessayé tout seul" in i18n
        tient = "programmerVeille" in store
        assert promet == tient, (
            "le message et le mecanisme ont diverge : l'un promet ce que "
            "l'autre ne fait pas")

    def test_les_trois_cas_sont_distingues(self):
        """« Aucun serveur enregistré » et « le serveur ne répond pas » ne se
        réparent pas pareil. Une seule phrase pour les deux envoyait chercher
        une panne sans dire laquelle."""
        transport = _lire(TRANSPORT)
        i18n = _lire(PWA / "lib" / "i18n" / "index.ts")

        assert "BACKEND_ABSENT" in transport
        assert i18n.count("'chat.noBackend':") == 2
        assert i18n.count("'chat.offlineWhy':") == 2

    def test_la_raison_mesuree_arrive_a_lecran(self):
        transport = _lire(TRANSPORT)
        store = _lire(CHAT_STORE)

        assert "BACKEND_OFFLINE::" in transport, "l'erreur reelle ne voyage pas"
        assert "BACKEND_OFFLINE::" in store, "l'erreur reelle n'est pas relue"
