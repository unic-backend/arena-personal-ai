# Les commandes de ton PC — la liste, une fois pour toutes

*Écrit le 04/09/2026. Toutes les commandes viennent des scripts du dépôt ou de
`scripts/doctor.py`, jamais de mémoire.*

Ton PC tourne environ quatre heures par jour. Ce fichier existe pour que tu
n'aies jamais à te rappeler d'une commande, et pour qu'aucune session future ne
t'en invente une.

**Ouvre PowerShell dans le dossier ARENA** (celui qui contient
`Lancer_ARENA.bat`). Toutes les commandes ci-dessous partent de là.

---

## 1. Tous les jours — un seul geste

```
.\Lancer_ARENA.bat
```

Double-clic depuis l'explorateur marche aussi. Ça démarre Ollama, le serveur,
le tunnel, **et ça annonce ton adresse du jour** à Railway pour que ton
téléphone la trouve seul (DEC-0040).

Tu dois voir passer `[ok] adresse annoncee au serveur permanent`. S'il affiche
`[X] annonce ... impossible`, ARENA tourne quand même — mais le téléphone ne te
trouvera pas tout seul ce jour-là.

**C'est la seule commande dont tu as besoin au quotidien.** Le reste de ce
fichier ne sert que quand quelque chose cloche ou quand tu veux un moteur lourd.

---

## 2. Quand j'ai poussé du travail

```
git pull origin master
```

Puis relance `.\Lancer_ARENA.bat`. Le lanceur reconstruit l'interface tout seul
si elle manque.

---

## 3. Savoir ce qui marche vraiment

```
python scripts/doctor.py
```

Il interroge chaque capacité au lieu de la supposer. Trois états, jamais deux :
`[OK]` marche, `[CONF]` il manque un réglage, `[ABS]` ce n'est pas installé.

C'est **lui** l'autorité sur l'état de ta machine, pas ce fichier ni un message
de chat. Chaque ligne en défaut affiche elle-même la commande qui la répare.

---

## 4. Le réglage à avoir dans `.env`

Trois lignes comptent pour le montage téléphone + PC :

```
USMAN_API_KEY=<ta cle>
USMAN_ANNONCE_URL=https://arena-personal-ai-production.up.railway.app
```

`USMAN_ANNONCE_URL` est la ligne sans laquelle tu recopies une adresse dans ton
téléphone chaque jour. Toutes les variables lues par les scripts sont dans
`.env.example`, et un test refuse désormais qu'une seule en sorte.

**Ne mets jamais ce fichier dans git**, et ne m'envoie jamais ta clé.

---

## 5. Les moteurs lourds — seulement quand tu en as besoin

Ils ne démarrent pas avec ARENA, et c'est voulu : ils prennent ta carte
graphique. Chacun se lance dans **sa propre fenêtre**, depuis **son** dossier.

| Moteur | Commande | Port |
|---|---|---|
| Vidéo courte (MoneyPrinterTurbo) | `python -m uvicorn app.asgi:app --host 127.0.0.1 --port 8080` | 8080 |
| Voix (VoiceStudio) | `uv run uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900` | 3900 |
| Vidéo (WanGP) | son serveur MCP | 8765 |

ARENA les voit dès qu'ils répondent — rien à redémarrer de son côté.

**WanGP n'a pas de commande écrite ici parce que je ne l'ai jamais mesurée.**
Le diagnostic dit seulement « Lancer WanGP avec son serveur MCP ». Écrire une
commande plausible serait pire que ce blanc.

OpenTakeoff (métré de plan) et Xaar Kaname (visage) **ne se lancent pas** :
ARENA démarre et arrête leur processus lui-même à chaque usage.

---

## 6. Les installations — une seule fois par moteur

```
powershell -ExecutionPolicy Bypass -File scripts\installer_opentakeoff.ps1
powershell -ExecutionPolicy Bypass -File scripts\installer_faceplugin.ps1
powershell -ExecutionPolicy Bypass -File scripts\installer_ui_ux_pro_max.ps1
powershell -ExecutionPolicy Bypass -File scripts\installer_moneyprinter.ps1
```

Ces moteurs s'installent **à côté** d'ARENA, dans `tools/`, jamais dedans : ils
ont leurs licences et leurs dépendances, et un test vérifie qu'ils restent
dehors (`tests/test_moteurs_externes_restent_dehors.py`).

Chaque installateur vérifie ce qu'il lance et **s'arrête au lieu d'annoncer un
succès par-dessus un échec** — un défaut mesuré le 03/09/2026, où « Termine »
s'affichait sur une installation entièrement ratée.

**OmniVoice (moteur de clonage/voice design de VoiceStudio) n'a pas non plus
d'installateur — et n'en a plus besoin.** Vérifié le 07/09/2026 sur le source
de VoiceStudio (`debpalash/VoiceStudio`, commit `53ff367c`, 05/09/2026) : ce
qui manquait le 01/09/2026 (« `omnivoice` : No module named 'transformers' »,
`docs/audits/voicestudio_audit.md`) a changé — `torch`, `torchaudio` et
`transformers>=5.5.0` sont maintenant des dépendances **de base** de
VoiceStudio lui-même (`pyproject.toml`), plus une option a part. Le geste qui
manquait est donc simplement de mettre VoiceStudio a jour :

```
cd VoiceStudio
git pull
uv sync
```

`uv sync` (jamais `pip install`) reste la regle du §7 ci-dessus. Les poids du
modele (`k2-fsa/OmniVoice` sur Hugging Face, plusieurs Go) restent
telecharges **au premier usage reel**, pas par cette commande — c'est
VoiceStudio qui gere ce telechargement et son cache, ARENA n'y touche pas
(meme raison que le paragraphe sur la VRAM au §5 : une politique de
telechargement/eviction qui existe deja, ARENA n'en cree pas une seconde).
Cette machine-ci (l'assistant, dans le cloud) n'a ni GPU ni acces a
Hugging Face — verifie, pas suppose : `huggingface.co` y est bloque par la
politique reseau. Aucune synthese OmniVoice reelle n'a donc pu etre generee
depuis cette session ; seul le routage cote ARENA (`core/connectors/audio_voix.py`)
a ete verifie, avec un VoiceStudio simule.

> **⚠️ Avant de lancer ce `uv sync` : les poids d'OmniVoice sont CC-BY-NC —
> usage commercial interdit** (DEC-0069, mesure du 07/09/2026 sur le fichier
> de licences de VoiceStudio). Une voix off de chantier pour UniC est un usage
> commercial. **ARENA refusera donc de s'en servir pour ton travail**, et te
> dira pourquoi plutot que de produire un fichier en silence — c'est voulu.
>
> Pour parler *vraiment* pour UniC, installe a cote un moteur a licence
> permissive : **`cosyvoice`** (Apache-2.0) est le plus proche d'OmniVoice, il
> clone et il accepte `instruct`. `voxcpm2` (Apache-2.0), `kittentts` et
> `gpt-sovits` (MIT) marchent aussi.
>
> OmniVoice reste utilisable pour un essai ou une comparaison, en le declarant :
> `python scripts/verifier_voix.py --usage recherche`.

**Verifier la chaine vocale, pour de vrai, sur ta machine :**

```
python scripts/verifier_voix.py
```

Elle passe **par ARENA** (pas par VoiceStudio en direct, sinon elle mesurerait
VoiceStudio), et rend, ligne par ligne : les moteurs installes avec l'appareil
qu'ils utilisent reellement et leur licence, puis une synthese reelle en
francais, anglais et **wolof**, chacune avec sa duree, sa cadence, son
amplitude et son facteur temps reel mesures. Un fichier parfaitement
silencieux y est un ECHEC, pas un succes.

Pour tester aussi le clonage — jamais sans autorisation declaree :

```
python scripts/verifier_voix.py --ref-audio media/ma_voix.wav \
    --autorisation "Ousmane Diop, proprietaire de la voix"
```

**Pascal — l'architecture 3D (DEC-0070).** Sans lui, ARENA ne peut dessiner
aucun batiment : elle le dit au lieu de faire semblant. Le moteur est
**MIT**, mais son arbre npm pese 205 Mo, donc il reste hors du depot.

Il exige **Bun**, pas Node — mesure du 07/09/2026 : le paquet publie importe
ses modules sans extension, ce que Node refuse et que Bun accepte. Une seule
fois :

```
curl -fsSL https://bun.sh/install | bash
mkdir tools\architecture\pascal
copy core\architecture\paquets.json tools\architecture\pascal\package.json
cd tools\architecture\pascal
npm install
```

`core/architecture/paquets.json` **epingle `zod` a 4.3.5**, et ce n'est pas
un detail : avec 4.5.4, le serveur demarre, les lectures marchent, et
**toutes les ecritures echouent en silence**. Ne releve pas cette version
sans relancer `python -m pytest tests/core/test_architecture_3d.py`.

Verifier que ca marche :

```
python scripts/doctor.py
```

La ligne « Architecture 3D » doit dire `[OK]` et compter les operations. Si
elle dit `[CONF]`, elle nomme ce qui manque : Bun, le dossier, ou le paquet.

Ensuite, une phrase suffit : « Cree une maison de 20m x 15m avec 3 chambres,
un salon, une cuisine, 2 salles de bain et une terrasse. » ARENA montre le
plan complet, attend **une** confirmation, puis construit.

**Lean 4 — la vérification formelle (DEC-0067).** Sans lui, ARENA ne peut
*rien* prouver : elle le dit au lieu de laisser un modèle l'affirmer. Le
toolchain est Apache-2.0 mais fait **2,9 Go** décompressé, donc il reste hors
du dépôt. Une seule fois, dans ton dossier ARENA :

```
mkdir tools\formel
cd tools\formel
curl -L -o lean.tar.zst https://github.com/leanprover/lean4/releases/download/v4.33.1/lean-4.33.1-linux.tar.zst
```

Puis décompresse-le et renomme le dossier obtenu en `lean` (il doit exister
un `tools\formel\lean\bin\lean`). Sous Windows, la version à prendre est
`lean-4.33.1-windows.zip` sur la même page de releases.

`v4.33.1` n'est pas un choix au hasard : c'est **exactement** la version que
le dépôt de référence (`anthropics/fermats-last-theorem`) épingle dans son
`lean-toolchain`. Si tu as déjà Lean installé autrement (elan), inutile de
retélécharger : mets son chemin dans `LEAN_BIN` et ARENA le prendra.

**Mathlib n'est pas installé, et c'est voulu** : c'est une bibliothèque de
plusieurs gigaoctets qui demande des heures de compilation. Sans elle, Lean
vérifie les preuves qui n'utilisent que sa bibliothèque standard — largement
de quoi trancher un raisonnement, jamais de quoi refaire Fermat.

**Le clic qui manque** : `EXECUTE_COMMANDS` est à `false` dans
`config/permissions.yaml`. Tant qu'il y est, ARENA refusera de lancer Lean —
et c'est normal : vérifier une preuve écrite par un modèle, c'est exécuter du
code. Mets-le à `true` quand tu veux t'en servir.

Xaar Kaname (Deep-Live-Cam) n'a pas d'installateur : il s'installe à la main
dans `tools/video/xaar_kaname/`, hors du dépôt parce qu'il est en AGPL-3.0.

KrillinAI (traduction/doublage vidéo, DEC-0049) non plus, même raison — il
est en GPL-3.0 : cloner `krillinai/krillinai`, puis compiler seulement
`runtime/krillinai/` (l'ancien moteur ; le reste du dépôt est devenu
OpenCreator, un produit différent, non utilisé ici) :

```
git clone --depth 1 https://github.com/krillinai/krillinai
cd krillinai/runtime/krillinai
go build -o krillinai-cli ./cmd/cli
```

Place ensuite `krillinai-cli` sur le PATH (ou fixe `KRILLINAI_CLI_BIN` sur son
chemin exact). `ffmpeg`, `ffprobe` et `yt-dlp` doivent déjà être installés —
ARENA refuse de laisser KrillinAI les télécharger seul.

---

## 7. Les modèles Ollama

Ceux qu'ARENA nomme dans `apps/backend/config.py`, relevés le 04/09/2026 :

```
ollama pull qwen3.5:9b          # conversation, et raisonnement profond
ollama pull qwen2.5-coder:14b   # Dioumtoukay, le modele de code
ollama pull qwen3-vl:4b         # vision
ollama pull bge-m3              # recherche dans tes documents
```

Si Ollama ne répond pas : `ollama serve`. Sans lui, ARENA ne répond pas non
plus — c'est la seule panne qui arrête tout.

Ne recopie pas ces noms aveuglément : `python scripts/doctor.py` te dira
lesquels manquent réellement, et te donnera la ligne exacte.

---

## Ce que ce fichier ne fait pas

Il ne remplace pas le diagnostic. Un fichier écrit un jour donné vieillit sans
que ça se voie — c'est exactement le défaut corrigé une dizaine de fois dans ce
dépôt. **En cas de doute, la mesure gagne sur ce fichier :**

```
python scripts/doctor.py
```
