# Fichiers tiers embarqués

Ces fichiers ne sont pas écrits par ce projet. Ils sont copiés ici pour que
l'interface fonctionne **sans connexion Internet** — voir `DEC-0002`, local-first.

## tailwind.js

| | |
|---|---|
| Origine | `https://cdn.tailwindcss.com` |
| Version | Tailwind CSS 3.x (build navigateur) |
| Téléchargé le | 2026-08-26 |
| Taille | 407279 octets |
| SHA-256 | `176e894661aa9cdc9a5cba6c720044cbbf7b8bd80d1c9a142a7c24b1b6c50d15` |
| Licence | MIT (Tailwind Labs) |

**Pourquoi une copie et non un build.** Le build officiel demande Node et une
étape de compilation ; ce projet n'a pas de chaîne JavaScript et n'en veut pas
pour un fichier. La contrepartie est que la mise en forme est calculée dans le
navigateur au chargement.

**Pour le mettre à jour** : retélécharger depuis l'origine, remplacer le fichier,
et corriger la date, la taille et l'empreinte ci-dessus. `tests/test_frontend.py`
vérifie que l'empreinte déclarée correspond au fichier réellement présent.
