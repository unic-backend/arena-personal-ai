"""`RegistreDeCrochets` : deux chaines, et la regle qui les protege — un
crochet casse n'arrete jamais l'appel qu'il observe.
"""
from core.actions.resultat import succes
from core.execution.hooks import RegistreDeCrochets


class TestAvantExecution:
    def test_sans_crochet_rien_ne_bloque(self):
        registre = RegistreDeCrochets()

        assert registre.executer_avant("svc", "cap", {}) is None

    def test_le_premier_veto_arrete_la_chaine(self):
        registre = RegistreDeCrochets()
        appels = []
        registre.avant(lambda c, cap, p: appels.append("un") or "refuse par le premier")
        registre.avant(lambda c, cap, p: appels.append("deux") or "refuse par le second")

        raison = registre.executer_avant("svc", "cap", {})

        assert raison == "refuse par le premier"
        assert appels == ["un"], "le second crochet n'aurait pas du etre consulte"

    def test_un_crochet_qui_laisse_passer_cede_au_suivant(self):
        registre = RegistreDeCrochets()
        registre.avant(lambda c, cap, p: None)
        registre.avant(lambda c, cap, p: "refuse par le second")

        assert registre.executer_avant("svc", "cap", {}) == "refuse par le second"

    def test_un_crochet_qui_leve_n_arrete_pas_la_chaine(self):
        registre = RegistreDeCrochets()

        def casse(c, cap, p):
            raise RuntimeError("boum")

        registre.avant(casse)
        registre.avant(lambda c, cap, p: "raison du second")

        assert registre.executer_avant("svc", "cap", {}) == "raison du second"

    def test_les_parametres_atteignent_le_crochet(self):
        registre = RegistreDeCrochets()
        recu = {}
        registre.avant(lambda c, cap, p: recu.update(connecteur=c, capacite=cap, params=p))

        registre.executer_avant("opentakeoff", "mesurer", {"chemin": "/x/a.pdf"})

        assert recu == {"connecteur": "opentakeoff", "capacite": "mesurer",
                        "params": {"chemin": "/x/a.pdf"}}


class TestApresExecution:
    def test_tous_les_observateurs_sont_notifies(self):
        registre = RegistreDeCrochets()
        vus = []
        registre.apres(lambda c, cap, r: vus.append("un"))
        registre.apres(lambda c, cap, r: vus.append("deux"))

        registre.executer_apres("svc", "cap", succes("cap", "svc", "ok", "preuve"))

        assert vus == ["un", "deux"]

    def test_un_observateur_qui_leve_n_empeche_pas_les_autres(self):
        registre = RegistreDeCrochets()
        vus = []

        def casse(c, cap, r):
            raise RuntimeError("boum")

        registre.apres(casse)
        registre.apres(lambda c, cap, r: vus.append("second"))

        registre.executer_apres("svc", "cap", succes("cap", "svc", "ok", "preuve"))

        assert vus == ["second"]

    def test_le_resultat_recu_est_bien_celui_transmis(self):
        registre = RegistreDeCrochets()
        recu = {}
        resultat = succes("cap", "svc", "ok", "preuve-1")
        registre.apres(lambda c, cap, r: recu.setdefault("resultat", r))

        registre.executer_apres("svc", "cap", resultat)

        assert recu["resultat"] is resultat
