"""Connecteur ARENA pour UI/UX Pro Max — intelligence de design.

Le moteur est **MIT** (`LICENSE`, Copyright (c) 2024 Next Level Builder) et
tient en Python pur : aucune dependance hors bibliotheque standard, 3 Mo de
donnees CSV. Il reste malgre tout **hors du depot**, dans
`tools/design/ui_ux_pro_max/` — non par contrainte de licence, mais par la
convention deja etablie ici pour tout moteur externe (VoiceStudio, WanGP,
MoneyPrinterTurbo, OpenTakeoff, Xaar Kaname) : le depot porte le connecteur,
ses tests et son installeur ; jamais le moteur. Un seul endroit ou regarder
quand un moteur bouge vaut mieux que deux regles selon la licence.

Son moteur de recherche n'est pas reecrit ici : `search.py` est appele tel
quel avec `--json`. Dupliquer son classement BM25 dans ARENA ferait deux
resultats possibles pour la meme question.

**Aucune ecriture.** `search.py` sait persister un design system sur le disque
(`--persist`) ; cette option n'est deliberement pas exposee. Une capacite de
raisonnement n'a pas besoin de droits d'ecriture, et la demander « au cas ou »
elargirait les permissions sans usage (regle de la mission, §8).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

UIUX_ROOT = (
    Path(__file__).resolve().parents[2] / "tools" / "design" / "ui_ux_pro_max"
)
UIUX_SEARCH = UIUX_ROOT / "src" / "ui-ux-pro-max" / "scripts" / "search.py"

#: Les domaines interrogeables, releves dans `core.py:CSV_CONFIG` du moteur
#: (03/09/2026). Liste **fermee** : un domaine invente serait refuse par le
#: moteur apres coup, et le refus arriverait trop tard pour etre utile.
DOMAINES = (
    "style", "color", "chart", "landing", "product", "ux",
    "typography", "icons", "gsap", "react", "web", "google-fonts",
)

#: Le moteur est en Python pur : il tourne avec l'interpreteur d'ARENA. Pas de
#: second environnement a installer, donc pas de second environnement a tenir
#: a jour.
DELAI = 90


class ConnecteurUiUxProMax(Connecteur):
    """Recommandations de design mesurees sur les donnees du moteur."""

    service = "design_ui"
    nom = "ui_ux_pro_max"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "chercher": Capacite(
                nom="chercher",
                action="read",
                description="Chercher styles, palettes, typographies ou regles UX.",
                ecriture=False,
            ),
            "design_system": Capacite(
                nom="design_system",
                action="read",
                description="Composer un design system complet pour un projet.",
                ecriture=False,
            ),
        }

    def authentifier(self) -> bool:
        return UIUX_SEARCH.is_file()

    def sonder(self) -> Sante:
        """L'etat du moteur, mesure en l'interrogeant vraiment.

        Un `search.py` present ne prouve pas que ses donnees le sont : le
        moteur lit une douzaine de CSV, et un depot a moitie copie garderait
        le script sans les tables.
        """
        if not UIUX_ROOT.is_dir():
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="UI/UX Pro Max n'est pas installé.",
                ce_qui_manque=str(UIUX_ROOT),
            )
        if not UIUX_SEARCH.is_file():
            return Sante(
                etat=EtatSante.EN_PANNE,
                message="Installation incomplète : search.py absent.",
                ce_qui_manque=str(UIUX_SEARCH),
            )

        issue = self._appeler("dashboard", domaine="style", maximum=1)
        if issue.get("ok"):
            return Sante(etat=EtatSante.OPERATIONNEL, message="UI/UX Pro Max disponible.")
        return Sante(
            etat=EtatSante.EN_PANNE,
            message="Le moteur ne répond pas.",
            ce_qui_manque=str(issue.get("erreur", ""))[:300],
        )

    def _appeler(self, requete: str, domaine: str | None = None,
                 maximum: int = 3, design_system: bool = False,
                 stack: str | None = None,
                 projet: str | None = None) -> Dict[str, Any]:
        """Lance `search.py --json` et rend son objet, ou une erreur nommee."""
        commande: List[str] = [sys.executable, str(UIUX_SEARCH), requete, "--json"]
        if design_system:
            commande.append("--design-system")
            if projet:
                commande += ["--project-name", projet]
        else:
            if domaine:
                commande += ["--domain", domaine]
            commande += ["--max-results", str(maximum)]
        if stack:
            commande += ["--stack", stack]

        try:
            processus = subprocess.run(
                commande, cwd=str(UIUX_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=DELAI, check=False)
        except (OSError, subprocess.TimeoutExpired) as erreur:
            return {"ok": False, "erreur": f"{type(erreur).__name__}: {erreur}"}

        sortie = (processus.stdout or "").strip()
        if not sortie:
            return {"ok": False,
                    "erreur": (processus.stderr or "").strip()[-500:] or "aucune reponse"}
        try:
            return {"ok": True, "donnees": json.loads(sortie)}
        except json.JSONDecodeError:
            return {"ok": False, "erreur": f"reponse illisible : {sortie[:300]}"}

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        nom = capacite.nom
        if not self.authentifier():
            return non_configure(
                nom, "UI/UX Pro Max",
                f"le moteur n'est pas installe dans {UIUX_ROOT}")

        requete = str(parametres.get("requete", "")).strip()
        if not requete:
            return echec(nom, "UI/UX Pro Max",
                         "Aucune demande fournie : dis pour quel projet ou quel ecran.")

        if nom == "design_system":
            issue = self._appeler(requete, design_system=True,
                                  projet=parametres.get("projet"),
                                  stack=parametres.get("stack"))
        else:
            domaine = parametres.get("domaine")
            if domaine is not None and domaine not in DOMAINES:
                # Refuse ici plutot que de laisser le moteur refuser : la liste
                # fermee est connue d'avance, et nommer les domaines valables
                # est plus utile qu'un code de sortie.
                return echec(
                    nom, "UI/UX Pro Max",
                    f"Domaine inconnu : {domaine}. Domaines : {', '.join(DOMAINES)}.")
            issue = self._appeler(requete, domaine=domaine,
                                  maximum=int(parametres.get("max_resultats", 3)),
                                  stack=parametres.get("stack"))

        if not issue.get("ok"):
            return echec(nom, "UI/UX Pro Max", str(issue.get("erreur", "echec inconnu")),
                         moteur="ui_ux_pro_max")

        donnees = issue["donnees"]
        if nom == "design_system":
            systeme = donnees.get("design_system") or {}
            if not systeme:
                # **Rien n'est compose a la place du moteur.** Un design system
                # vide se rapporte vide ; il ne se remplit pas de valeurs
                # plausibles.
                return echec(nom, "UI/UX Pro Max",
                             "Le moteur n'a compose aucun design system pour cette demande.",
                             moteur="ui_ux_pro_max")
            return succes(
                nom, "UI/UX Pro Max",
                f"Design system composé pour « {requete} ».",
                preuve=str(parametres.get("projet") or requete),
                design_system=systeme, moteur="ui_ux_pro_max")

        resultats = donnees.get("results") or []
        # **Les donnees du moteur sont en anglais** (mesure du 03/09/2026) :
        # « accessibilite formulaire » ne rend rien la ou « form validation »
        # rend deux resultats. Un zero muet se lirait « il n'existe rien sur ce
        # sujet » ; on nomme donc la cause probable au lieu de la laisser
        # deviner. Le statut reste un succes : la recherche a bien eu lieu, et
        # zero resultat est une reponse, pas une panne.
        message = f"{len(resultats)} résultat(s) dans « {donnees.get('domain', 'auto')} »."
        if not resultats:
            message += " Les données du moteur sont en anglais — réessaie en anglais."
        return succes(
            nom, "UI/UX Pro Max", message,
            preuve=requete,
            domaine=donnees.get("domain"), resultats=resultats,
            moteur="ui_ux_pro_max")
