# Audit — `allenai/molmo`, pour la vision d'ARENA

*Demandé le 30/08/2026 : auditer `github.com/allenai/molmo` comme couche de
perception visuelle réelle (description, OCR, captures d'écran, interfaces,
plans de construction, photos de chantier, relations entre objets, questions
sur une image, futur raisonnement multimodal). Audit d'abord, aucune
installation avant preuve — c'est la mission elle-même qui le demande.*

## Conclusion, avant le détail

**Ne pas intégrer `allenai/molmo`.** Trois raisons indépendantes, chacune
suffisante seule :

1. **ARENA a déjà cette capacité.** DEC-0019 (29/08/2026, la veille de cette
   mission) a construit un chemin complet — image jointe → `VisionAgent` →
   `qwen3-vl:4b` servi par Ollama → réponse — qui couvre **chacune** des
   capacités listées dans la mission. Installer Molmo à côté serait le doublon
   que la règle 4 interdit explicitement.
2. **Molmo ne peut pas être servi par Ollama.** Son architecture n'est pas
   supportée par `llama.cpp`/GGUF (demande ouverte et non résolue,
   `ggml-org/llama.cpp#9645`, « Feature Request: Molmo 72B vision support »).
   Le seul chemin d'exécution documenté par AllenAI est `transformers` +
   PyTorch — exactement le second moteur d'inférence local que DEC-0019 a
   refusé pour Qwen3-VL, pour la même raison : Ollama est « le défaut, le
   repli, et le seul chemin autorisé » pour tout ce qui est local ici
   (`core/models/routeur.py`).
3. **Le dépôt cité est un dépôt figé.** Dernier commit : 12 décembre 2024 —
   vingt mois avant cette mission. AllenAI a publié son successeur,
   **Molmo2** (`allenai/molmo2`, 9 janvier 2026 : multi-image, vidéo,
   *grounding* amélioré, base Qwen3-8B), ce qui confirme que Molmo (2024)
   n'est plus le travail actif d'AllenAI sur le sujet.

Le vrai manque n'est pas un modèle : **`qwen3-vl:4b` n'a jamais été chargé ni
mesuré sur sa RTX A2000.** DEC-0019 est *100 % logique vérifiée, 0 % mesurée*
(`PROJECT_MEMORY/COMPLETED_SYSTEMS.md`). C'est la seule action qui manque
avant de juger si ARENA « voit mal » — pas une nouvelle installation.

---

## 1. Ce qu'ARENA a déjà (audit de l'existant, avant tout le reste)

Chemin réel, déjà écrit, déjà testé (2006 tests hors ligne passent, un
sabotage a prouvé chaque garde) :

```
phrase → intention VISION (mots-clés ou modèle classeur)
       → agents/vision/vision_agent.py : VisionAgent.run()
       → pieces jointes filtrées aux images (jpg/jpeg/png/webp/gif)
       → OllamaProvider.generate(images=[...])   (core/models/ollama_provider.py)
       → qwen3-vl:4b (Ollama, local, 3,3 Go de poids, contexte 256K)
       → réponse
```

| Objectif de la mission | Couvert par DEC-0019 aujourd'hui ? |
|---|---|
| Décrire une image | Oui — `VisionAgent`, prompt libre |
| Lire du texte dans une image (OCR) | Oui — capacité native de Qwen3-VL |
| Comprendre une capture d'écran | Oui — même chemin, aucune distinction de type d'image |
| Comprendre une interface UI | Oui — idem ; pas de *grounding* pixel-précis testé (voir §4) |
| Comprendre un plan d'architecture | Oui — intention `VISION` reconnaît explicitement « analyse ce plan de construction » |
| Comprendre une photo de chantier | Oui — c'est le cas d'usage nommé dans DEC-0019 lui-même |
| Comprendre objets et relations | Oui — capacité native d'un VLM généraliste |
| Répondre à des questions sur une image | Oui — c'est la fonction du chemin entier |
| Raisonnement multimodal futur | Partiel — la voie `PROFONDE` existe ; vidéo/multi-image non implémenté (`SUGGESTION — NON IMPLÉMENTÉE` dans DEC-0019 même) |

**Zéro ligne de la mission n'est un manque de capacité codée.** Ce qui manque
est une mesure sur la vraie machine (§5).

---

## 2. Le dépôt audité : ce qu'il contient vraiment

Vérifié en interrogeant le dépôt et son historique, pas supposé :

- **Quatre modèles publiés en 2024** : `MolmoE-1B-0924` (1 Md actifs / 7 Md
  total, MoE, base OLMoE), `Molmo-7B-O-0924` (base OLMo-7B, entièrement
  ouvert), `Molmo-7B-D-0924` (base **Qwen2-7B**), `Molmo-72B-0924` (base
  **Qwen2-72B**). Licence Apache 2.0 déclarée pour chaque fiche HuggingFace,
  y compris les variantes à base Qwen2 (Qwen2 ≤ 7B était déjà Apache 2.0 côté
  Alibaba — pas de conflit de licence trouvé).
- **Dernier commit du dépôt `allenai/molmo` : 12 décembre 2024.** 31 issues,
  3 pull requests ouvertes à cette date, sans mouvement mesurable depuis.
- **Successeur publié le 9 janvier 2026 : `allenai/molmo2`** — multi-image,
  vidéo, *grounding* renforcé, variantes 4B/8B (base Qwen3) et 7B (base
  OLMo). C'est le projet vivant d'AllenAI sur le sujet ; le dépôt cité dans
  la mission (`allenai/molmo`, sans le « 2 ») ne l'est plus.
- **Aucun poids quantifié officiel, aucun tag Ollama.**
  `ollama.com/library/molmo` → **404**. La conversion GGUF de l'architecture
  Molmo n'est pas supportée par `llama.cpp` : demande de fonctionnalité
  ouverte et non résolue (`ggml-org/llama.cpp#9645`). Sans GGUF, pas de tag
  Ollama possible — la voie choisie par DEC-0019 pour Qwen3-VL n'existe
  simplement pas pour Molmo.
- **Chemin d'exécution documenté** : `transformers` (`AutoModelForCausalLM`
  avec code distant `trust_remote_code=True`) + PyTorch, la fiche HuggingFace
  recommandant `vLLM` pour l'inférence rapide — deux moteurs de plus, aucun
  des deux déjà présent dans l'architecture d'ARENA.

---

## 3. Pourquoi ça ne rentre pas dans l'architecture (et pas seulement le matériel)

`core/models/routeur.py` documente lui-même la règle : Ollama est **le seul
chemin local**, pour que « le jour où un fournisseur change, rien d'autre ne
bouge ». DEC-0019 a déjà tranché ce même dilemme pour Qwen3-VL — le dépôt
officiel `QwenLM/Qwen3-VL` propose aussi un chemin `transformers` par défaut,
et a été **refusé** pour cette raison précise : « vendre `transformers` comme
un second moteur d'inférence à côté d'Ollama aurait dupliqué toute
l'infrastructure de chargement de modèle pour un seul cas d'usage. »

Molmo n'offre aucun autre choix que ce chemin refusé. L'intégrer
demanderait :

- un second gestionnaire de modèle, en dehors de `RouteurModeles`
  (`core/models/routeur.py`), qui ne sait parler qu'à un `ModelProvider`
  Ollama-compatible ;
- une dépendance `transformers` + `torch` (déjà présente pour d'autres
  usages ? à vérifier — mais pas comme moteur d'inférence servi en
  continu) + probablement `bitsandbytes` pour tenir en mémoire ;
- un chargement et un cycle de vie de modèle propres, distincts de
  `scripts/doctor.py`'s `verifier_modele()` qui suppose un endpoint Ollama.

C'est le doublon que la règle 4 de cette mission interdit — avant même de
parler de VRAM.

---

## 4. Matériel : RTX A2000, 12 Go de VRAM, déjà partagée

Mesuré nulle part sur cette machine cloud (pas de GPU ici, comme pour toute
capacité locale d'ARENA — `CLAUDE.md`), donc les chiffres qui suivent viennent
des fiches publiées, pas d'une mesure : **`NON VÉRIFIÉ`, pas un fait.**

| Modèle déjà résident (DEC-0019) | Taille approx. |
|---|---|
| `qwen2.5-coder:14b` | ~9 Go (Q4_K_M) |
| `qwen3.5:9b` | ~5,5 Go (Q4_K_M) |
| `qwen3-vl:4b` (décidé, pas encore chargé) | 3,3 Go |

Ces trois seuls, chargés ensemble, approchent déjà les 12 Go de la carte —
c'est exactement pourquoi DEC-0019 a choisi le 4B et pas le 8B par défaut.

Molmo, lui, n'a **aucune publication officielle de poids quantifiés**. En
`bfloat16` (le format que la fiche HuggingFace recommande), `Molmo-7B-D`
(7 Md de paramètres) pèse environ **14 Go rien que pour les poids** — plus
que la carte entière, avant même d'y ajouter le contexte, l'encodeur visuel
ou les deux autres modèles. Une quantification 4 bits non officielle
(`bitsandbytes`, à construire soi-même, jamais publiée par AllenAI) tomberait
vers 4-5 Go — potentiellement viable seule, mais seule : elle ne coexisterait
pas avec `qwen2.5-coder:14b` et `qwen3.5:9b` sans les décharger, ce que rien
dans ARENA ne fait aujourd'hui (chaque fournisseur Ollama attend son modèle
déjà chargé).

**Conclusion matérielle : viable seulement en écartant ce qui tourne déjà,
et seulement après un travail de quantification qu'AllenAI n'a pas fait.**
Le 72B est hors sujet dès l'énoncé (72 Md de paramètres, aucune quantification
ne le fait tenir sur 12 Go).

---

## 5. Ce qui a une vraie valeur, et ce que ça coûterait

**Grounding / pointage.** Le signe distinctif de Molmo (et renforcé dans
Molmo2) est de désigner un point ou une zone précise dans l'image — utile
pour « clique ici » sur une interface, plus précis qu'une simple description
de zone. Qwen3-VL fait aussi du *grounding* (boîtes englobantes), mesuré nulle
part ici dans les deux cas. Si ce point précis s'avère un vrai manque une fois
`qwen3-vl:4b` mesuré sur de vraies captures d'écran, la piste à revisiter est
**Molmo2** (le projet vivant, pas celui audité ici) — seulement si un jour il
publie un chemin GGUF/Ollama. Aujourd'hui, il n'en a pas non plus (recherché,
non trouvé).

`SUGGESTION — NON IMPLÉMENTÉE` : rien de tout cela n'est demandé par la
mission actuelle, qui demande un audit, pas un second modèle de vision.

---

## 6. Licence et provenance

Apache 2.0 pour les quatre modèles Molmo (2024) et pour le code du dépôt
`allenai/molmo`. Aucun conflit trouvé avec les backbones Qwen2 utilisés
(Qwen2 ≤ 7B déjà Apache 2.0). La licence n'est **pas** ce qui bloque cette
intégration — c'est l'architecture (§3) et le matériel (§4), avant même
d'arriver à la question du droit.

---

## 7. Plan d'intégration — pourquoi il ne démarre pas maintenant

| Étape habituelle | État pour Molmo |
|---|---|
| 1. Modèle servable par Ollama | **Non — bloqué** (llama.cpp#9645, aucun tag `ollama.com/library`) |
| 2. Taille compatible avec 12 Go partagés | **Non, sans quantification non officielle** |
| 3. Pas de doublon avec l'existant | **Non — DEC-0019 couvre déjà tout** |
| 4. Dépôt maintenu | **Non — dernier commit il y a 20 mois, successeur déjà publié** |
| 5. Licence compatible | Oui — seule case cochée |

Une seule case sur cinq. Le plan d'intégration officiel de ce projet
(`INTEGRATE → TEST → REGRESSION CHECK → VALIDATE` et la discipline
sabotage-puis-preuve) ne s'ouvre pas avant que les quatre premières le
soient — ce n'est pas un jugement de qualité sur Molmo, c'est une question
de chemin d'exécution qui n'existe pas dans l'architecture d'ARENA telle
qu'elle est décidée.

---

## 8. Prochaine étape réelle — pas Molmo

Le geste qui répond vraiment à « ARENA voit mal » est déjà écrit et déjà
décidé (DEC-0019) : **charger et mesurer `qwen3-vl:4b` sur sa machine.**
Zéro nouvelle dépendance, zéro nouveau code, une seule commande, une vraie
mesure au lieu d'une supposition.

```
TERMINAL 1

ollama pull qwen3-vl:4b
```

Une fois téléchargé (3,3 Go), l'étape suivante sera de mesurer une vraie
image (photo de chantier, capture d'écran, plan) à travers `VisionAgent` et
`scripts/doctor.py`, pour remplacer les `NON VÉRIFIÉ` de DEC-0019 par des
mesures réelles — **une commande à la fois**, comme demandé, et seulement
après confirmation que ce terminal a bien tourné.

---

## Ce que ça coûte si cet audit est faux

Si un vrai manque de qualité apparaît une fois `qwen3-vl:4b` mesuré (mauvaise
lecture d'un plan, OCR imprécis), le coût de ce choix est nul à revenir en
arrière : rien n'a été installé, aucune dépendance ajoutée, ce document
resterait la référence pour rouvrir la question — vers Molmo2 si son chemin
Ollama existe un jour, pas vers le dépôt figé audité ici.
