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

Xaar Kaname (Deep-Live-Cam) n'a pas d'installateur : il s'installe à la main
dans `tools/video/xaar_kaname/`, hors du dépôt parce qu'il est en AGPL-3.0.

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
