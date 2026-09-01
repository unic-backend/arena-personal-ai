# Audit général d'ARENA — nuit du 01/09/2026

*Méthode : **exécuter les chemins**, pas les lire. Chaque défaut ci-dessous a
été trouvé en faisant tourner quelque chose, et chaque correctif a été prouvé
en cassant volontairement ce que son test protège.*

Point de départ posé par le propriétaire : « Ne suppose pas qu'une suite de
tests verte veut dire que le projet est sain. » Elle l'était : 2542 tests au
vert. **Huit défauts réels ont été trouvés quand même.**

---

## Ce qui a été exécuté, et ce que ça a donné

| Axe | Méthode | Résultat |
|---|---|---|
| Connecteurs | Sonde de santé des 10 | 4 `OPERATIONAL`, 6 `NOT_CONFIGURED` **avec la raison exacte**. Aucun ne ment, aucun ne tombe. |
| Capacités déclarées | Chaque capacité de lecture appelée | **0** déclarée-mais-non-exécutable. |
| Routes API | Les 30 énumérées, GET sans paramètre appelées | **0** en 5xx. |
| Traversée de chemin | 5 charges contre `/media/rendered/{nom}` et `/icons/{nom}` | **0** fuite, tout en 404. |
| `eval` / `exec` / `shell=True` | Recherche dans tout le source | **Aucune occurrence.** |
| TODO / FIXME | Idem | **Zéro.** |
| File de travaux | Un travail réel soumis et attendu | Exécuté, `TERMINE`, résultat rendu. |
| Gardien | Cycle réel + 3 violations plantées | Les 3 détectées, 0 après nettoyage. **Il regarde vraiment.** |
| Routage de modèles | `generate()` sans Ollama | Échec **nommé** : quel fournisseur, pourquoi, quel mode l'aurait permis. |
| Journal des actions | Deux actions réelles jouées | Outil, action, résultat, permission et preuve enregistrés. |
| Mémoire | Écriture et relecture | Historique et faits conservés. |
| Devis PDF | Chiffrage réel | 12 postes, 3 298 000 FCFA depuis sa vraie grille. |
| Docteur | Lancé en entier | Honnête sur les 12 capacités absentes. |

---

## Les huit défauts trouvés, et ce qu'ils coûtaient

### 1. `/health` taisait six agents — dont son assistant devis

Une liste **écrite à la main** annonçait 16 agents. `PlaquisteAgent`,
`EmailAgent`, `SocialAgent`, `VisionAgent`, `MontageAgent` et `AudioAgent`
n'y étaient pas. Le même fichier avait déjà menti dans l'autre sens en
08/2026 (il annonçait `ReasoningEngine` qu'aucun chemin n'atteignait).

**Le test existant n'exigeait que `len(...) > 0`** — voilà pourquoi la dérive
a duré. La liste est désormais **dérivée** des agents que `runtime` construit
vraiment : elle ne peut plus dériver. Deux tests, dans les deux sens.

### 2. Le bac à sable prenait un problème d'installation pour une erreur de code

Docker actif mais image non construite : `docker run` rend un code non nul
**sans lever**. Le chemin d'exception n'était donc jamais pris, et
« Unable to find image » remontait comme un échec **du code** — un agent
serait alors parti corriger du code correct. C'est exactement ce que
`_refuser` existe pour éviter (« ce n'est pas le code qui a échoué »).

L'image est mesurée à côté du démon ; son absence est refusée avec la commande
de construction, derrière le même interrupteur `ALLOW_UNSAFE_EXEC` que tous
les autres replis.

### 3. Une recherche qui n'avait rien pu lire répondait « aucun résultat »

`search_dir` avalait toute erreur de lecture, puis rendait exactement la même
phrase qu'une vraie absence. Un agent en concluait que le terme n'existe pas.
Les fichiers illisibles sont maintenant comptés, nommés, et la réponse dit que
la recherche est **incomplète**.

### 4. `/api/chat/stream` mourait en silence

Ollama éteint : `200` et **zéro ligne**. L'exception remontait dans une
réponse déjà commencée — flux vide, sans `[DONE]`, sans raison. Le client ne
pouvait pas distinguer ça d'une réponse vide.

Pire : le message du propriétaire était **déjà écrit en mémoire**, laissant une
question orpheline dans l'historique. Le tour interrompu s'y inscrit désormais
comme interrompu — jamais comme une réponse fabriquée. Le correctif reprend le
motif que `pwa_gateway.flux` tenait déjà, au lieu d'en inventer un second.

### 5. Une recherche documentaire en panne s'annonçait comme une réponse

La capacité « documents » rendait `status: "success"` en portant
« ❌ Erreur de recherche documentaire LightRAG : No module named 'lightrag' ».
L'interface l'affichait comme un résultat.

`adaptateur_synchrone` codait `"success"` en dur. Un outil qui rend une chaîne
ne peut dire « j'ai échoué » que par un prédicat — et ce prédicat appartient à
l'outil : `LightRAGTool` connaît le préfixe de ses propres échecs.

**Le test qui gardait cet espace exigeait `status == "success"`** sur une
machine sans `lightrag` : il **épinglait le mensonge**. Il vérifie maintenant la
forme du contrat et la cohérence entre le statut et ce que la réponse dit.

### 6. Deux transcripteurs, aucun utilisé

Sur une machine sans `faster_whisper`, l'analyse vidéo s'arrêtait sur
« Transcription impossible » **pendant que VoiceStudio répondait sur la boucle
locale**. Le chemin normal ne bouge pas — le modèle local d'abord, il ne
dépend d'aucun autre programme — mais son absence déclenche désormais un repli
**annoncé**, qui rend `None` plutôt qu'une transcription fabriquée quand
VoiceStudio se tait aussi.

Vérifié en vrai : un MP4 avec piste AAC, audio extrait par ffmpeg, modèle local
levant `ModeleAbsent`, VoiceStudio rendant le texte.

### 7. La passerelle compatible OpenAI sortait en `500` nu

Ollama éteint, `/v1/chat/completions` rendait `500 Internal Server Error`,
`text/plain`, **corps vide**. C'est la surface que les outils *extérieurs*
utilisent : le client ne pouvait pas distinguer « le service est tombé » de
« ta requête est invalide ». Et son flux mourait en silence, exactement comme
`/api/chat/stream` (défaut 4) — le même défaut, à deux endroits.

Elle rend maintenant l'objet d'erreur qu'un client compatible OpenAI sait
lire, en **503** (le problème n'est pas la requête) ; le flux dit la panne et
se ferme par `[DONE]`. Un refus d'authentification reste un `401` : une panne
de service ne maquille pas un problème d'accès.

### 8. Le docteur ne connaissait pas la voix

Une capacité que le diagnostic ignore est invisible au propriétaire. Et un port
qui répond ne prouve rien : **VoiceStudio démarre très bien sans aucun moteur**.
La vérification interroge donc ses moteurs et nomme ce qui manque.

---

## Ce qui a été trouvé et **délibérément pas corrigé**

**Le métré n'accepte pas « une paroi de 12 x 2,50 m ».** Il accepte
« 1 paroi de 12 x 2,50 m » (chiffre) et « 486 m2 developpes », mais pas la
forme écrite en toutes lettres, ni « cloison de 12 x 2,50 m », ni
« mur de 12 m sur 2,50 m ».

**Pourquoi ne pas y toucher** : le comportement actuel est *sûr* — il refuse et
dit quoi donner. Une extension bâclée du parseur a un mode d'échec *dangereux* :
un mauvais prix sur un document qui part chez un client. Ce n'est pas une
correction de nuit, c'est une décision du propriétaire.

`OPTIONAL — NON IMPLÉMENTÉ.`

---

## Ce qui reste hors de portée de cette machine

- **Ollama** : ni modèle, ni embeddings, ni vision. Tout ce qui en dépend
  répond `NOT_CONFIGURED` et le dit.
- **Docker** : le bac à sable **refuse** d'exécuter plutôt que de le faire sans
  isolation. C'est la règle qui fonctionne, pas une panne.
- **GPU** : `vram_total_gb: 0.0`. Aucune mesure VRAM n'existe, et aucune n'a
  été inventée.
- **`lightrag`, `faster_whisper`** : absents côté ARENA ; les deux le disent.

---

## Vérification de cet audit

```
python -m ruff check .                                   -> All checks passed!
python -m pytest tests/ -q                               -> 2578 passed, 44 deselected
OMNIVOICE_URL=http://127.0.0.1:9 python -m pytest tests/ -q -> 2578 passed  (conditions CI)
python scripts/orphelins.py                              -> aucun module réel endormi
```

**Chaque correctif a été saboté avant d'être déclaré tenu** : la garantie
retirée, le test tombe ; restaurée, il passe. Aucun test n'a été supprimé,
désactivé ni affaibli — celui du point 5 a été **renforcé**.
