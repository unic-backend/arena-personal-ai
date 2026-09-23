"""Connecteur Agnes — generation video par un service auto-heberge separe.

**Le trou mesure le 23/09/2026.** `tools.video.AgnesProductionBridge` existait
deja, teste dans l'isolation de vingt fichiers de tests, avec sa propre ADR
(`docs/decisions/DEC-AGNES-PROVIDER.md`, « Status: active ») et sa propre
documentation d'integration — mais **aucun appelant reel ne l'atteignait**.
`grep -i agnes` sur `apps/backend/`, `agents/` (hors `tools/video/__init__.py`
lui-meme) et `core/connectors/registre.py` ne rendait rien. La documentation
citait meme un chemin d'import qui n'existe pas
(`agents.video.AgnesProductionBridge` — le module reel est
`tools.video.AgnesProductionBridge`, et `agents/video/__init__.py` est vide).
Les tests ajoutes ensuite pour "verifier la reachabilite" ne testaient que
des capacites PRE-EXISTANTES (VISION, AUDIO, MONTAGE...) par recherche de
chaine dans le code source — jamais Agnes elle-meme. `scripts/orphelins.py`
disait "0 orphelin reel" parce qu'il mesure au niveau du FICHIER : la classe
comptait comme "atteinte" seulement parce que `FFmpegTool`, dans le meme
fichier, l'est reellement.

Ce connecteur ferme ce trou en suivant EXACTEMENT le meme chemin que
WanGP/MoneyPrinterTurbo/HiDream-I1/Xaar Kaname : passer par le registre, pas
un appel direct depuis l'agent, pour que la generation respecte
`video_generation.generate = CONFIRMATION` (`config/permissions_services.yaml`)
comme n'importe quelle autre generation video. Agnes tourne HORS de ce
depot, sur son propre service HTTP (`AGNES_VIDEO_URL`,
`http://127.0.0.1:8765` par defaut) — jamais importe dans l'environnement
principal, jamais lance par ARENA (meme categorie que WanGP/MoneyPrinter/
HiDream : `scripts/orphelins.py::SERVICE_LANCE_PAR_LE_PROPRIETAIRE` ne
s'applique pas ici puisqu'Agnes n'a pas de point d'entree `__main__` dans ce
depot — c'est un service tiers, pas du code ARENA a lancer).

**Ce que ce connecteur ajoute sur `AgnesProductionBridge` lui-meme :**

1. **`etat_travail` collecte, il ne se contente pas de lire un statut.** Une
   tache Agnes annoncee terminee n'est pas prise pour une preuve : cette
   capacite appelle `collect()` des que le provider dit "completed" — meme
   discipline « termine n'est jamais pris pour une preuve » que
   `core/connectors/hidream.py`/`xaar_kaname.py` appliquent deja a un
   fichier annonce. Le fichier existe reellement sous `RENDERED_DIR` avant
   qu'un `success: True` ne soit rendu.
2. **Le contrat `{done, result: {success, generated_files}}`** est exactement
   celui que `core/connectors/suivi_video.py::suivre_generation` sait deja
   suivre — ecrit pour WanGP, generique par construction, reutilise ici SANS
   modification.
3. **L'annulation est reelle, pas un succes invente.** `AgnesProductionBridge`
   n'expose pas `stop()` dans son propre contrat public, mais
   `AgnesVideoProvider` (la couche HTTP qu'il enveloppe) si :
   `self._bridge.orchestrator.agnes.stop(...)`. Ce connecteur l'appelle
   plutot que de rendre un `NOT_IMPLEMENTED` deguise en `SUCCESS`.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from tools.video import AgnesError, AgnesProductionBridge

#: Meme plafond que les autres generateurs video (wangp/moneyprinter) :
#: une soumission Agnes monopolise le meme genre de ressource externe.
GENERATIONS_PAR_MINUTE = 4
QUOTA_LECTURE_PAR_MINUTE = 60

#: Les etats que le provider Agnes rapporte pour une tache achevee — memes
#: valeurs que `tools.video._SUCCESS`, redites ici pour ne pas dependre d'un
#: attribut prive d'un autre module.
_ACHEVE = {"completed", "complete", "success", "succeeded"}

CE_QUI_MANQUE = (
    "Le service Agnes, auto-heberge a part et joignable sur AGNES_VIDEO_URL "
    "(http://127.0.0.1:8765 par defaut)."
)


class AgnesConnector(Connecteur):
    """Generation video Agnes, par son pont HTTP — jamais en direct."""

    service = "video_generation"
    nom = "agnes"

    def __init__(self, bridge: Optional[AgnesProductionBridge] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bridge = bridge or AgnesProductionBridge()

    # --- Capacites ---------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "generer": Capacite(
                nom="generer", action="generate",
                description=("Soumet une generation video a Agnes "
                             "(workflow simple/creative/manuscript/poetry/anchor)."),
                ecriture=True, quota_par_minute=GENERATIONS_PAR_MINUTE),
            "etat_travail": Capacite(
                nom="etat_travail", action="read",
                description=("Ou en est une tache Agnes ; collecte et valide "
                             "le fichier des qu'elle est terminee."),
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "annuler_travail": Capacite(
                nom="annuler_travail", action="cancel",
                description="Arrete une tache Agnes en cours.",
                ecriture=True),
        }

    def authentifier(self) -> bool:
        return True

    # --- Sante ---------------------------------------------------------------

    def sonder(self) -> Sante:
        from core.connectors.base import _maintenant

        etat = self._bridge.health()
        if not etat.get("available"):
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"Agnes ne repond pas : {etat.get('reason') or 'raison inconnue'}.",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message="Service Agnes joignable.", mesure_le=_maintenant())

    # --- Execution -------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "generer":
            return self._generer(capacite, parametres)
        if capacite.nom == "etat_travail":
            return self._etat(capacite, parametres)
        return self._annuler(capacite, parametres)

    def _generer(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        """Lance une generation. Appelee **uniquement** apres confirmation
        (`video_generation.generate = CONFIRMATION`)."""
        prompt = str(parametres.get("prompt") or "").strip()
        if not prompt:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun prompt : rien a generer.")
        workflow = str(parametres.get("workflow") or "simple")
        options = {cle: valeur for cle, valeur in parametres.items()
                   if cle not in ("prompt", "workflow") and valeur is not None}

        corps = self._bridge.submit(prompt, workflow=workflow, **options)
        if corps.get("statut") == "ERROR":
            message = str(corps.get("message") or "Agnes a refuse la generation.")
            if "unavailable" in message.lower():
                return non_configure(action=capacite.nom, cible=self.nom,
                                    ce_qui_manque=CE_QUI_MANQUE, detail_erreur=message)
            return echec(action=capacite.nom, cible=self.nom, message=message)

        identifiant = corps.get("task_id")
        if not identifiant:
            return echec(
                action=capacite.nom, cible=self.nom,
                message="Agnes a accepte l'appel sans rendre d'identifiant de tache.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"Generation Agnes ({workflow}) lancee (tache {identifiant}). "
                     "Elle avance en fond ; le chat ne l'attend pas."),
            preuve=str(identifiant), workflow=workflow, engine="agnes")

    def _etat(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        identifiant = str(parametres.get("job_id") or "").strip()
        if not identifiant:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun identifiant de tache : rien a regarder.")

        try:
            statut = self._bridge.status(identifiant)
        except (AgnesError, ValueError, TypeError) as erreur:
            return echec(action=capacite.nom, cible=self.nom, message=str(erreur))

        etat_provider = str(statut.get("etat_provider") or "").lower()
        if etat_provider not in _ACHEVE:
            instantane = {"done": False, "result": {}}
            return succes(action=capacite.nom, cible=self.nom,
                         message=f"Tache Agnes {identifiant} : {etat_provider or 'en cours'}.",
                         preuve=identifiant, donnees=instantane)

        # Termine n'est jamais pris pour une preuve : la collecte relit
        # reellement le fichier, meme discipline que HiDream/Xaar Kaname.
        try:
            collecte = self._bridge.collect(identifiant)
        except (AgnesError, ValueError, TypeError, OSError) as erreur:
            instantane = {"done": True, "result": {
                "success": False, "generated_files": [], "errors": [str(erreur)]}}
            return succes(action=capacite.nom, cible=self.nom,
                         message=f"Tache Agnes {identifiant} terminee cote provider, "
                                 "mais la collecte a echoue.",
                         preuve=identifiant, donnees=instantane)

        if collecte.get("statut") != "SUCCESS":
            instantane = {"done": True, "result": {
                "success": False, "generated_files": [],
                "errors": [str(collecte.get("message") or "collecte Agnes sans succes")]}}
            return succes(action=capacite.nom, cible=self.nom,
                         message=f"Tache Agnes {identifiant} terminee cote provider, "
                                 "mais la collecte a echoue.",
                         preuve=identifiant, donnees=instantane)

        fichier = str(collecte.get("preuve") or "")
        instantane = {"done": True, "result": {
            "success": bool(fichier), "generated_files": [fichier] if fichier else []}}
        return succes(action=capacite.nom, cible=self.nom,
                     message=f"Tache Agnes {identifiant} terminee et collectee.",
                     preuve=identifiant, donnees=instantane)

    def _annuler(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        identifiant = str(parametres.get("job_id") or "").strip()
        if not identifiant:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun identifiant de tache : rien a annuler.")
        try:
            self._bridge.orchestrator.agnes.stop(identifiant)
        except (AgnesError, ValueError, TypeError) as erreur:
            return echec(action=capacite.nom, cible=self.nom, message=str(erreur))
        return succes(action=capacite.nom, cible=self.nom,
                     message=f"Annulation demandee pour la tache Agnes {identifiant}.",
                     preuve=identifiant)
