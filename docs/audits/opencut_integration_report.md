# Intégration OpenCut — rapport final

*Mission ouverte le 01/09/2026. Ce rapport clôt ce qui a été fait, et nomme ce
qui ne l'a pas été.*

Il répond aux dix points demandés, dans l'ordre. Chaque chiffre a été mesuré
dans la session qui l'écrit ; ce qui ne l'a pas été porte `UNKNOWN` et le dit.

---

## 1. Les deux dépôts, audités avant toute intégration

Détail complet → `docs/audits/opencut_audit.md`. Le résultat qui a décidé de
tout :

| | Réécriture (`OpenCut`) | Classique (`OpenCut-classic`) |
|---|---|---|
| Taille | 1,6 Mo, 15 fichiers Rust | 16 Mo |
| Dernier commit | 2026-08-01 | archivé le 2026-05-17 |
| MCP / headless / editor api | **0 fichier chacun** | — |
| Rendu | absent | **natif navigateur** (`CanvasRenderer`, WebCodecs) |

La réécriture contient une architecture attirante et **rien qui tourne** : ni
couche MCP, ni API sans interface. La consigne « ne pas intégrer aveuglément
une réécriture inachevée pour son architecture future » a été suivie à la
lettre : **rien n'a été intégré des deux dépôts.**

## 2. Licences

| Composant | Licence | Conséquence |
|---|---|---|
| OpenCut (réécriture) | MIT | Compatible |
| OpenCut classic | MIT | Compatible |
| `opencut-wasm` 0.2.10 | MIT | Compatible |
| **`mediabunny` 1.55.5** | **MPL-2.0** | Copyleft faible au fichier — **pas MIT**, contrairement à ce que le dépôt principal laisse croire |

Aucune licence incompatible. `mediabunny` **n'est pas utilisé**. L'attribution
due à OpenCut est écrite dans `NOTICE.md` : le modèle de projet suit le sien,
aucun code n'a été copié.

## 3. Ce qui a été retenu, ce qui a été rejeté

**Retenu — le modèle de projet.** Projet → pistes → éléments, un type
d'élément par type de piste, la coupe portée par l'élément. C'est la partie
d'OpenCut qui vaut, et elle est indépendante de son moteur.

**Rejeté — le rendu.** Il est natif navigateur. Le faire tourner sans
interface demanderait un navigateur piloté, et la mesure faite sur le Chromium
de cette machine le condamne :

```
vp8            : supporté   → 15 images réellement encodées
av01.0.04M.08  : supporté
avc1.42001f    : NON supporté   (H.264 absent de ce Chromium)
```

Un pipeline vidéo qui ne peut pas produire de H.264 ne sert pas à publier sur
les réseaux. ARENA garde `ffmpeg`, **local**, derrière une frontière
remplaçable (`core/montage/rendu.py`) : aucun fichier vidéo ne sort de la
machine, ce que la mission exigeait.

*(Une mesure fausse a été corrigée en cours de route : le premier test disait
`VideoEncoder` absent. Il tournait sur `about:blank`, qui n'est pas un
contexte sécurisé. Refait correctement, WebCodecs est là — et ne change pas la
conclusion, faute de H.264.)*

## 4. Fichiers intégrés

| Fichier | Lignes | Rôle |
|---|---|---|
| `core/montage/projet.py` | 296 | La timeline : projet, pistes, éléments, sérialisation revalidée à la relecture |
| `core/montage/operations.py` | 374 | Les opérations, chacune rendant un `Resultat` |
| `core/montage/rendu.py` | 287 | Le graphe `filter_complex`, puis **le re-sondage de sa propre sortie** |
| `core/montage/planificateur.py` | 240 | La frontière entre le modèle et la timeline |
| `core/connectors/montage.py` | 188 | Le connecteur : permissions, confirmation, liste fermée d'opérations |
| `agents/montage/montage_agent.py` | 150 | La phrase → le plan → la composition réelle |

**1539 lignes de code, 931 lignes de tests.**

## 5. Composants ARENA réutilisés, jamais réécrits

`Connecteur` et ses capacités · `ControleAcces` et
`config/permissions_services.yaml` · `FileDAttente` (la confirmation du
propriétaire) · `ResultatAction` (un `SUCCES` ne se construit pas sans preuve)
· `JournalDesActions` · `FFmpegTool` · le registre de connecteurs ·
l'aiguilleur et `core/execution/voies.py`.

Le montage **n'a introduit aucune dépendance nouvelle**. Aucun paquet ajouté.

## 6. L'intelligence vidéo

Une phrase du propriétaire devient un plan d'opérations. Trois barrières, et la
deuxième est la seule qui soit une frontière de sécurité :

1. **Liste d'opérations fermée** (`OPERATIONS_OUVERTES`).
2. **Le modèle ne cite aucun chemin de fichier.** Il travaille sur un
   inventaire `{nom: chemin}` bâti côté serveur ; un chemin écrit dans un plan
   est refusé *même s'il est exact*.
3. **Les paramètres sont lus sur le code par introspection**, jamais recopiés.

C'est ce que la mission appelait « a structured operation layer ». Décision
complète → `docs/DECISIONS.md`, DEC-0026.

## 7. Ce qui a réellement tourné

**La chaîne entière, sauf l'appel au modèle.**

```
1. INVENTAIRE cote serveur : ['chantier_ouakam', 'logo_unic']
2. PROMPT : 1422 caracteres, aucun chemin
3. PLAN VALIDE : 9 operations | 2 refusees
   refuse -> #10 : operation refusee « publier_sur_instagram ».
   refuse -> #11 importer_media : un chemin ne se cite pas dans un plan
4. COMPOSER : SUCCESS | 6000 ms sur 3 piste(s)
5. RENDRE : SUCCESS  -> projet-5c9a480f.mp4
```

Le plan soumis est ce qu'un modèle rend réellement : de la prose autour d'un
bloc ```json, une opération inventée, un chemin cité.

**Le succès est le fichier, pas la commande.** Sondé indépendamment :

```
codec_name=h264   width=1080   height=1920
duration=6.000000   nb_frames=180   size=74464
```

Logo et titre incrustés vérifiés sur une image extraite. **Le cadrage a été
mesuré, pas estimé** : la source 16:9 occupe 1080 × 608 dans le cadre vertical,
soit 1.776 — l'aspect est préservé. (Une première lecture *à l'œil* de cette
image avait conclu à une déformation ; la mesure l'a démentie.)

## 8. Tests

```
python -m ruff check .      -> All checks passed!
python -m pytest tests/ -q  -> 2486 passed, 40 deselected
```

Dont **126 tests de montage** (108 hors ligne, 18 `integration`), et la suite complète rejouée **sans ffmpeg dans
le PATH** pour reproduire le CI : 2486 passed également.

Les tests unitaires n'ont pas été tenus pour suffisants : **18 tests marqués
`integration`** lancent un vrai ffmpeg et vérifient de vrais fichiers.

Sabotage fait avant de déclarer chaque garantie tenue : la barrière des chemins
retirée fait tomber deux tests ; `sonder()` remis en `NON_CONFIGURE` en fait
tomber deux autres.

## 9. Un défaut trouvé par le CI, pas par cette machine

`ConnecteurMontage.sonder()` rendait `NON_CONFIGURE` sans ffmpeg. La base lit
la santé **avant toute capacité** : ce refus coupait aussi `composer`, qui est
du Python pur. Cette machine a ffmpeg — la suite locale ne pouvait pas voir le
défaut. Le CI, qui ne l'a pas, a fait tomber quatre tests. Trois tests cachent
désormais ffmpeg de force.

C'est le seul défaut de l'intégration parti en production, et il a été corrigé
avant fusion.

## 10. Limites, `UNKNOWN`, et ce qui n'a pas été fait

**`UNKNOWN` — la qualité des plans produits par Qwen.** Ollama n'est pas sur la
machine de l'assistant (`docs/REGLES_DE_TRAVAIL.md`). L'aiguillage, la
validation, la composition et le rendu sont mesurés ; **ce que le modèle écrira
réellement ne l'est pas.** Cela attend le PC du propriétaire.

**Limite assumée — le modèle ne monte que les fichiers déposés dans `media/`.**
Un rush rangé ailleurs sur le disque est introuvable. C'est le prix de la
barrière : sans elle, un texte injecté dans une transcription qu'ARENA vient de
lire pourrait faire entrer n'importe quel fichier de la machine dans une vidéo.

**Non fait, et non demandé — le GPU.** La mission demandait de rester
compatible avec la RTX A2000 du propriétaire. `rendu.py` appelle `ffmpeg` sans
imposer d'encodeur : `h264_nvenc` s'y branche sans changer l'architecture.
**Aucune accélération GPU n'a été activée ni mesurée** — cette machine n'a pas
de GPU, et un encodeur choisi sans mesure serait une supposition.

**Non fait, délibérément — les assets de la marque.** Logo, photos de chantier
et informations de marque sont les fichiers du propriétaire. Les fabriquer
aurait mis une fausse marque dans son dépôt.

### Suggestions, non implémentées

- `OPTIONAL` — des formats sociaux nommés (9:16, 1:1, 16:9) plutôt que
  largeur/hauteur à chaque plan.
- `OPTIONAL` — un recadrage qui remplit le cadre vertical au lieu de le
  compléter en noir. Le rendu actuel préserve l'aspect et complète ; remplir
  demande de décider quoi perdre, ce qui est un choix du propriétaire.
- `OPTIONAL` — `h264_nvenc` sur sa machine, **après mesure**, jamais avant.

Aucune de ces trois n'est devenue une tâche.
