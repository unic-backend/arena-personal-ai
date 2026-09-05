"""Connecteur KrillinAI : traduction/doublage video, par sous-processus isole.

**Ce que le depot en amont est devenu, verifie avant d'ecrire une ligne** (clone
reel, `krillinai/krillinai` @ `346d08bb1f3c61c96301ec130c4db8879b3b8444`,
05/09/2026) : `krillinai/KrillinAI` a ete renomme `krillinai/OpenCreator` et
totalement rearchitecture — c'est aujourd'hui un espace de travail agent complet
(bureau Electron, daemon, harnais, marche de competences) qui utilise **Codex
CLI comme moteur d'execution**. Integrer CE produit-la reviendrait exactement a
construire le second orchestrateur/systeme d'agents que ce depot s'interdit.
**Ce n'est pas ce qui est branche ici.**

L'ancien moteur KrillinAI (transcription -> traduction -> sous-titres ->
doublage -> rendu, en ligne de commande) survit intact sous
`runtime/krillinai/` a l'interieur de ce meme depot : un module Go independant
(`go.mod` : `krillin-ai`), avec ses propres commandes (`subtitle`, `tts`,
`speech`, `render-horizontal`, `render-vertical`, `cover`, `pipeline`,
`voices`), sa propre sortie JSON structuree, et son propre manifest
(`krillinai_manifest.json`). C'est ce moteur-la, et seulement lui, que ce
connecteur appelle.

**La licence a change de valeur en cours de route, et c'est elle qui fixe la
frontiere.** Le README d'OpenCreator affiche Apache-2.0 ; celui du module
Go vendu sous `runtime/krillinai/` est **GPL-3.0-only** (`runtime/krillinai/
LICENSE`, verifie directement, pas suppose). `LICENSE` d'ARENA est
« All rights reserved » : importer ou copier du code GPL romprait cette
licence, exactement le raisonnement deja tenu pour VoiceStudio (AGPL-3.0,
`core/connectors/audio_voix.py`). La frontiere retenue est donc la MEME —
**aucune ligne du moteur n'entre dans ce fichier** ; il tourne comme un
binaire compile a part, appele par sous-processus, jamais importe. Une
simple agregation par execution externe n'etend pas les obligations du GPL a
qui l'appelle — copier ou lier son code le ferait.

**Le binaire n'est ni vendu, ni installe, ni telecharge par ce connecteur.**
`KRILLINAI_CLI_BIN` (variable d'environnement) ou `krillinai-cli` sur le PATH.
Absent -> `NON_CONFIGURE`, avec la commande de compilation a lancer
(`go build ./cmd/cli` depuis un clone de `runtime/krillinai/`) — jamais
devine, jamais recupere seul.

**Six regles, au-dela du contrat commun `Connecteur` :**

1. **Jamais de clonage de voix.** `tts` n'accepte et ne transmet jamais
   `--voice-clone-source` : ce parametre n'existe simplement pas dans ce
   fichier. Instruction du proprietaire, absolue et anterieure a cette
   integration : « si tu vois quelque chose de nouveau [pres du deep face],
   ignore-le, ne le touche meme pas ». Le clonage vocal est la meme famille
   de risque (media synthetique) que Xaar Kaname (Deep-Live-Cam) — la
   frontiere est la meme, et elle ne se negocie pas capacite par capacite.

2. **Aucune transcription locale doublee.** `subtitle` refuse
   `caption_source="whisper"`/`"auto"` : ARENA transcrit deja
   (FasterWhisper, `core/connectors/audio_voix.py`/`tools/audio/
   transcription_tool.py`) — lancer un second moteur de transcription
   chargerait un second modele sur la meme RTX A2000 12 Go pour rien. Le
   contrat retenu est `caption_source="manual"` (une transcription/SRT
   qu'ARENA fournit, deja produite par sa propre capacite) ou `"platform"`
   (les sous-titres deja fournis par la plateforme source, YouTube par
   exemple — pas une transcription, une simple recuperation).

3. **Aucun telechargement implicite.** `subtitle` avec une URL en entree
   exige `autoriser_telechargement=True` explicite — meme logique que
   GitIngest (`core/connectors/gitingest.py`) pour une URL distante,
   risque MEDIUM assume par l'appelant, jamais suppose.

4. **ffmpeg/ffprobe/yt-dlp doivent deja etre presents sur la machine.**
   Le moteur amont les telecharge lui-meme s'il ne les trouve pas sur le
   PATH (`internal/deps/checker.go::checkAndDownloadFfmpeg`, verifie dans
   le source clone) — un telechargement de binaire non controle par ARENA.
   `sonder()` et `_executer()` verifient leur presence AVANT tout appel
   reel : absents -> refus explicite, jamais un appel qui declencherait un
   telechargement silencieux. `ffmpeg`/`ffprobe` sont deja une dependance
   d'ARENA (`tools/video/ffmpeg_tool.py`) — les reutiliser evite un second
   jeu de binaires.

5. **`--dry-run` valide, il ne genere jamais.** Chaque capacite l'expose ;
   aucun appel de ce fichier ne pretend qu'un dry-run est une sortie reelle
   — `_executer()` porte `dry_run` explicitement dans son `detail`.

6. **`pipeline` n'est PAS composable par le planificateur Video
   (`core/production/plan_video.py`).** La capacite existe et est testee
   ici, pour completude — mais l'exposer au graphe de `plan_video.py`
   laisserait le moteur amont composer ses propres etapes a la place
   d'ARENA, exactement le « second orchestrateur » que la mission
   d'integration elle-meme interdit. La composition (sous-titres -> doublage
   -> rendu) reste au graphe ARENA, une etape a la fois.

**Ce qui reste `UNKNOWN`, honnetement** : ce conteneur cloud n'a ni ffmpeg,
ni ffprobe, ni yt-dlp, ni cle API de traduction/TTS/image configuree — une
generation reelle bout en bout n'a donc pas pu etre mesuree ici, seulement
`--dry-run` (JSON reel captures, contrat verifie) et les erreurs de
configuration absente. Comme la phase 7.2 (`docs/CURRENT_TASK.md`), la
mesure reelle attend la machine du proprietaire.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.krillinai")

#: Reglable : un poste peut l'avoir ailleurs que sur le PATH courant. Jamais
#: telecharge ni compile par ARENA lui-meme (regle 0 ci-dessus).
KRILLINAI_BIN = os.getenv("KRILLINAI_CLI_BIN", "").strip() or "krillinai-cli"

#: Sources de sous-titres qui n'exigent PAS une seconde transcription locale
#: (regle 2). "whisper"/"auto"/"openai"/"aliyun" en sont volontairement
#: absents : ARENA transcrit deja.
SOURCES_CAPTION_AUTORISEES = frozenset({"manual", "platform", "any"})

#: Les trois binaires qu'ARENA exige deja presents sur le PATH (regle 4) —
#: jamais laisses au moteur amont pour un telechargement silencieux.
BINAIRES_MEDIA_REQUIS = ("ffmpeg", "ffprobe", "yt-dlp")

DELAI_SECONDES = 900.0


def _binaire_present() -> bool:
    return shutil.which(KRILLINAI_BIN) is not None


def _binaires_media_manquants() -> List[str]:
    return [b for b in BINAIRES_MEDIA_REQUIS if shutil.which(b) is None]


def _est_une_url(valeur: str) -> bool:
    schema = urlparse(valeur).scheme
    return schema in ("http", "https")


class ConnecteurKrillinAI(Connecteur):
    """Traduction/doublage video existante — jamais une generation de novo,
    jamais un second orchestrateur, jamais de clonage vocal."""

    service = "krillinai"
    nom = "krillinai"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else RENDERED_DIR

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "subtitle": Capacite(
                nom="subtitle", action="generate",
                description=("Transcrit (si fourni) et traduit une video en sous-titres "
                            "source/cible/bilingues/verticaux courts."),
                ecriture=True),
            "tts": Capacite(
                nom="tts", action="generate",
                description="Doublage audio a partir d'un SRT cible (jamais de clonage vocal).",
                ecriture=True),
            "render_horizontal": Capacite(
                nom="render_horizontal", action="generate",
                description="Incruste des sous-titres (et le doublage, en option) sur une video au format paysage.",
                ecriture=True),
            "render_vertical": Capacite(
                nom="render_vertical", action="generate",
                description="Meme rendu, format portrait (TikTok/Shorts/Reels).",
                ecriture=True),
            "cover": Capacite(
                nom="cover", action="generate",
                description="Image de couverture generee a partir d'un prompt (fournisseur externe requis).",
                ecriture=True),
            "pipeline": Capacite(
                nom="pipeline", action="generate",
                description=("Composition interne du moteur amont — non branchee au "
                            "planificateur Video d'ARENA (voir en-tete, regle 6)."),
                ecriture=True),
        }

    def sonder(self) -> Sante:
        if not _binaire_present():
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="krillinai-cli n'est pas trouve.",
                ce_qui_manque=("compiler runtime/krillinai/ (go build -o krillinai-cli ./cmd/cli) "
                              "et placer le binaire sur le PATH, ou fixer KRILLINAI_CLI_BIN"),
                mesure_le=_maintenant())

        manquants = _binaires_media_manquants()
        if manquants:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"krillinai-cli est present ; il manque : {', '.join(manquants)}.",
                ce_qui_manque=f"installer {', '.join(manquants)} (deja une dependance d'ARENA pour ffmpeg/ffprobe)",
                mesure_le=_maintenant())

        return Sante(etat=EtatSante.OPERATIONNEL,
                     message="krillinai-cli et ffmpeg/ffprobe/yt-dlp sont presents.",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : les identifiants de fournisseur (LLM/TTS/image) vivent dans
        le config.toml du moteur amont, jamais dans ARENA — pas ici a verifier."""
        return True

    def _lancer(self, arguments: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """`cwd` fixe : le moteur amont ecrit un `app.log` au chemin RELATIF
        fixe (`log/zap.go`, verifie dans le source clone), sans option pour
        le rediriger. Sans ce `cwd`, ce fichier apparaitrait dans le dossier
        d'ou tourne ARENA lui-meme — jamais dans le depot."""
        return subprocess.run(
            [KRILLINAI_BIN, *arguments],
            capture_output=True, text=True, timeout=DELAI_SECONDES, check=False,
            cwd=str(cwd) if cwd else str(self.dossier),
        )

    def _sortie_json(self, acheve: subprocess.CompletedProcess) -> Optional[Dict[str, Any]]:
        """La derniere ligne JSON valide de stdout — le contrat de sortie du
        moteur (une ligne par cadre + une ligne finale). Jamais du texte
        humain interprete comme un succes."""
        for ligne in reversed(acheve.stdout.splitlines()):
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                return json.loads(ligne)
            except json.JSONDecodeError:
                continue
        return None

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if not _binaire_present():
            return non_configure(
                action=capacite.nom, cible=self.nom,
                ce_qui_manque="compiler runtime/krillinai/ (go build -o krillinai-cli ./cmd/cli)")

        dry_run = bool(parametres.get("dry_run", False))
        if not dry_run:
            manquants = _binaires_media_manquants()
            if manquants:
                return echec(action=capacite.nom, cible=self.nom,
                             message=f"Binaire(s) manquant(s) : {', '.join(manquants)}. "
                                     "ARENA ne laisse pas krillinai-cli les telecharger seul.")

        methode = getattr(self, f"_{capacite.nom}", None)
        if methode is None:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Capacite « {capacite.nom} » non implementee.")
        return methode(parametres, dry_run)

    # --- subtitle -----------------------------------------------------------

    def _subtitle(self, parametres: Dict[str, Any], dry_run: bool) -> ResultatAction:
        entree = str(parametres.get("entree") or "").strip()
        origine = str(parametres.get("langue_origine") or "").strip()
        cible = str(parametres.get("langue_cible") or "").strip()
        source_caption = str(parametres.get("caption_source") or "manual").strip().lower()

        if not entree:
            return echec(action="subtitle", cible=self.nom, message="Aucune video/URL en entree.")
        if not origine or not cible:
            return echec(action="subtitle", cible=self.nom,
                         message="langue_origine et langue_cible sont requis.")
        if source_caption not in SOURCES_CAPTION_AUTORISEES:
            return echec(
                action="subtitle", cible=self.nom,
                message=(f"caption_source « {source_caption} » refuse : ARENA transcrit deja "
                         "(FasterWhisper). Fournis la transcription via caption_source=manual, "
                         f"ou 'platform'/'any'. Valeurs autorisees : {sorted(SOURCES_CAPTION_AUTORISEES)}."))
        if _est_une_url(entree) and not bool(parametres.get("autoriser_telechargement", False)):
            return echec(action="subtitle", cible=self.nom,
                         message="Entree distante : autoriser_telechargement=True est requis explicitement.")

        tache = f"krillin-{uuid.uuid4().hex[:8]}"
        workdir = self.dossier / tache
        workdir.mkdir(parents=True, exist_ok=True)

        arguments = [
            "subtitle", entree,
            "--origin-lang", origine, "--target-lang", cible,
            "--workdir", str(workdir), "--task-id", tache,
            "--caption-source", source_caption,
        ]
        if dry_run:
            arguments.append("--dry-run")

        return self._executer_et_rendre("subtitle", arguments, workdir, dry_run)

    # --- tts (jamais de clonage vocal) --------------------------------------

    def _tts(self, parametres: Dict[str, Any], dry_run: bool) -> ResultatAction:
        srt = str(parametres.get("srt_cible") or "").strip()
        workdir_existant = str(parametres.get("workdir") or "").strip()
        if not srt:
            return echec(action="tts", cible=self.nom, message="srt_cible (chemin) est requis.")
        # Regle 1 : ce parametre n'est jamais lu ni transmis, meme fourni.
        parametres.pop("voice_clone_source", None)

        tache = f"krillin-{uuid.uuid4().hex[:8]}"
        workdir = Path(workdir_existant) if workdir_existant else self.dossier / tache
        workdir.mkdir(parents=True, exist_ok=True)

        arguments = [
            "tts", "--workdir", str(workdir), "--task-id", tache,
            "--input-srt", srt,
            "--line-mode", str(parametres.get("line_mode") or "target-only"),
        ]
        video = str(parametres.get("video") or "").strip()
        if video:
            arguments += ["--video", video]
        voix = str(parametres.get("voice") or "").strip()
        if voix:
            arguments += ["--voice", voix]
        if dry_run:
            arguments.append("--dry-run")

        return self._executer_et_rendre("tts", arguments, workdir, dry_run)

    # --- render_horizontal / render_vertical --------------------------------

    def _render(self, nom_capacite: str, drapeau: str, parametres: Dict[str, Any],
                dry_run: bool) -> ResultatAction:
        video = str(parametres.get("video") or "").strip()
        sous_titres = str(parametres.get("sous_titres") or "").strip()
        workdir_existant = str(parametres.get("workdir") or "").strip()
        if not video or not sous_titres:
            return echec(action=nom_capacite, cible=self.nom,
                         message="video et sous_titres (chemins) sont requis.")

        tache = f"krillin-{uuid.uuid4().hex[:8]}"
        workdir = Path(workdir_existant) if workdir_existant else self.dossier / tache
        workdir.mkdir(parents=True, exist_ok=True)

        arguments = [
            drapeau, "--workdir", str(workdir), "--task-id", tache,
            "--video", video, "--subtitle", sous_titres,
        ]
        audio = str(parametres.get("audio") or "").strip()
        if audio:
            arguments += ["--audio", audio]
        if bool(parametres.get("double", False)):
            arguments.append("--dubbed")
        if nom_capacite == "render_vertical":
            for cle, drapeau_cli in (("titre_principal", "--major-title"),
                                     ("titre_secondaire", "--minor-title")):
                valeur = str(parametres.get(cle) or "").strip()
                if valeur:
                    arguments += [drapeau_cli, valeur]
        if dry_run:
            arguments.append("--dry-run")

        return self._executer_et_rendre(nom_capacite, arguments, workdir, dry_run)

    def _render_horizontal(self, parametres: Dict[str, Any], dry_run: bool) -> ResultatAction:
        return self._render("render_horizontal", "render-horizontal", parametres, dry_run)

    def _render_vertical(self, parametres: Dict[str, Any], dry_run: bool) -> ResultatAction:
        return self._render("render_vertical", "render-vertical", parametres, dry_run)

    # --- cover ---------------------------------------------------------------

    def _cover(self, parametres: Dict[str, Any], dry_run: bool) -> ResultatAction:
        prompt = str(parametres.get("prompt") or "").strip()
        if not prompt:
            return echec(action="cover", cible=self.nom, message="prompt est requis.")

        tache = f"krillin-{uuid.uuid4().hex[:8]}"
        workdir = self.dossier / tache
        workdir.mkdir(parents=True, exist_ok=True)

        arguments = ["cover", "--workdir", str(workdir), "--task-id", tache, "--prompt", prompt]
        taille = str(parametres.get("taille") or "").strip()
        if taille:
            arguments += ["--size", taille]
        if dry_run:
            arguments.append("--dry-run")

        return self._executer_et_rendre("cover", arguments, workdir, dry_run)

    # --- pipeline (jamais compose par plan_video.py — voir en-tete) ---------

    def _pipeline(self, parametres: Dict[str, Any], dry_run: bool) -> ResultatAction:
        sorties = [s.strip() for s in str(parametres.get("sorties") or "").split(",") if s.strip()]
        if not sorties:
            return echec(action="pipeline", cible=self.nom, message="sorties (liste) est requis.")

        arguments = ["pipeline", "--outputs", ",".join(sorties)]
        if dry_run:
            arguments.append("--dry-run")

        self.dossier.mkdir(parents=True, exist_ok=True)
        return self._executer_et_rendre("pipeline", arguments, None, dry_run)

    # --- commun ---------------------------------------------------------------

    def _executer_et_rendre(self, nom_capacite: str, arguments: List[str],
                            workdir: Optional[Path], dry_run: bool) -> ResultatAction:
        try:
            acheve = self._lancer(arguments, cwd=workdir)
        except subprocess.TimeoutExpired:
            return echec(action=nom_capacite, cible=self.nom,
                         message=f"krillinai-cli n'a pas rendu la main sous {DELAI_SECONDES:.0f}s.")
        except OSError as erreur:
            return echec(action=nom_capacite, cible=self.nom,
                         message=f"krillinai-cli n'a pas pu etre lance : {erreur}")

        sortie = self._sortie_json(acheve)
        if sortie is None:
            return echec(action=nom_capacite, cible=self.nom,
                         message=f"Sortie illisible (code {acheve.returncode}) : "
                                 f"{acheve.stderr.strip()[:300] or acheve.stdout.strip()[:300]}")

        if not sortie.get("ok"):
            erreur = sortie.get("error") or {}
            return echec(action=nom_capacite, cible=self.nom,
                         message=str(erreur.get("message") or "echec sans message."),
                         code=erreur.get("code"), dry_run=dry_run)

        detail: Dict[str, Any] = {"dry_run": dry_run, "sortie": sortie}
        if dry_run:
            return succes(action=nom_capacite, cible=self.nom,
                         message=f"{nom_capacite} : dry-run valide (aucune generation reelle).",
                         preuve=str(workdir) if workdir else "", **detail)

        outputs_annonces = sortie.get("outputs") or {}
        chemins_verifies = self._verifier_artefacts(outputs_annonces)
        detail["artefacts_verifies"] = chemins_verifies
        if outputs_annonces and not chemins_verifies:
            # « ok: true » du processus, mais aucun fichier annonce n'existe
            # reellement sur disque — un retour a zero ne suffit jamais
            # (CLAUDE.md). C'est un echec, pas un succes sans preuve.
            return echec(action=nom_capacite, cible=self.nom,
                         message="krillinai-cli a rendu ok=true mais aucun artefact annonce "
                                 "n'existe reellement sur disque.",
                         outputs_annonces=outputs_annonces)

        preuve = next(iter(chemins_verifies.values()), None) or (str(workdir) if workdir else "")
        return succes(action=nom_capacite, cible=self.nom,
                     message=f"{nom_capacite} termine ({len(chemins_verifies)} artefact(s) verifie(s)).",
                     preuve=preuve, **detail)

    def _verifier_artefacts(self, outputs: Dict[str, str]) -> Dict[str, str]:
        """Ne credite que les fichiers qui existent VRAIMENT sur disque et ne
        sont pas vides — jamais parce que le processus a rendu 0 (CLAUDE.md :
        « ne retourne jamais SUCCESS simplement parce que subprocess.returncode
        == 0 »)."""
        verifies: Dict[str, str] = {}
        for cle, chemin in outputs.items():
            if chemin and Path(chemin).is_file() and Path(chemin).stat().st_size > 0:
                verifies[cle] = chemin
        return verifies
