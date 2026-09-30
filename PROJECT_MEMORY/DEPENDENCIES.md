# DÉPENDANCES

*Mise à jour : 2026-08-28.*

## Externes — services (aucun n'est vendu dans ce dépôt)

| Service | Où | Sans lui |
|---|---|---|
| **Ollama** | `127.0.0.1:11434` | ARENA ne répond pas du tout |
| **ffmpeg** | binaire système | pas de vidéo, ni sous-titres, ni transcription |
| **Docker** | démon local | ARENA **refuse** d'exécuter du code plutôt que sans isolation |
| **WanGP** | MCP `127.0.0.1:8765` | pas de génération d'images vidéo |
| **MoneyPrinterTurbo** | HTTP `127.0.0.1:8080/api/v1` | pas de vidéo courte sur un sujet |
| **OpenTakeoff** | processus Node, lancé/arrêté par ARENA à chaque métré (`OPENTAKEOFF_MCP_DIR`) | pas de métré de plan PDF |
| **Google (Gmail + Calendar)** | API, un seul identifiant OAuth | pas de courrier ni d'agenda |
| **GalsenAPI** | API publique, sans clé | pas de données administratives du Sénégal |
| **LightRAG** | bibliothèque + Ollama | pas de recherche dans ses documents |
| **CoinGecko** | API publique `api.coingecko.com`, sans clé | pas de prix ni d'historique de marché — `FINANCE` répond `NON_CONFIGURE` (DEC-0078) |
| **Codebase-Memory MCP** | processus binaire natif (`codebase-memory-mcp`), lancé/arrêté par ARENA via MCP stdio (`USMAN_CODEBASE_MEMORY_BIN`) | repli automatique sur gitingest et l'arborescence (`NOT_CONFIGURED`) |
| **Netronome** (optionnel, DEC-0202) | binaire autobrr/netronome lancé par le propriétaire, API HTTP `127.0.0.1:7575` (`NETRONOME_URL`) | repli automatique sur la sonde réseau native d'ARENA (`core/reseau/sante_reseau.py`) ; débit/perte/gigue `None` |

## Externes — paquets

`requirements.txt` ne liste **que ce que le code importe**. `requirements.lock.txt`
est un gel non réinstallable tel quel (conflits connus et documentés en tête du
fichier). La CI installe le sous-ensemble hors ligne — voir `.github/workflows/ci.yml`.

## Variables d'environnement (toutes vides dans `.env.example`)

| Variable | Sans elle |
|---|---|
| `USMAN_API_KEY` | la passerelle `/api` et `/v1` est **désactivée par sécurité** |
| `GOOGLE_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` | pas de courrier, pas d'agenda (anciens noms `GMAIL_*` acceptés) |
| `MONEYPRINTER_URL` / `_API_KEY` | défaut local ; la clé n'est utile que s'il en a mis une |
| `OPENTAKEOFF_MCP_DIR` / `_NODE_BIN` | pas de métré de plan PDF (`NOT_CONFIGURED`) |
| `NETRONOME_URL` / `NETRONOME_SESSION` | défaut local `127.0.0.1:7575` ; sans Netronome lancé, repli sur la sonde réseau native (DEC-0202) |
| `AGENDA_HEURE_DEBUT` / `_FIN` | défaut 8 h – 18 h |
| `OLLAMA_BASE_URL`, `DEFAULT_LOCAL_MODEL`, `CODER_LOCAL_MODEL` | défauts locaux |
| `ALLOW_UNSAFE_EXEC` | **laisser vide** : sans elle, ARENA refuse d'exécuter hors bac à sable |

**Clés mortes, à ne jamais remettre** : `CREDS_KEY`, `JWT_SECRET`,
`JWT_REFRESH_SECRET`, `WEBUI_SECRET_KEY` (DEC-0007). Un test échoue si elles
réapparaissent.

## Internes — qui dépend de qui

```
resultat ← journal ← connectors/base ← tous les connecteurs
permissions ← connectors/base
attente ← connectors/base (confirmation)
voies ← orchestrator, pwa_gateway (budget mémoire), mesures
memory/personnelle ← recuperation ← semantique ← pwa_gateway
travaux ← suivi_video ← video_analyzer
google_oauth ← gmail, calendrier
registre ← plaquiste, video_analyzer, email
metre_plan ← plaquiste_agent (chemin de plan PDF lu dans la demande)
stdio_transport ← connectors/opentakeoff (le seul connecteur MCP en stdio)
runtime ← TOUT (c'est le câblage : un seul objet partagé de chaque)
```

**Conséquence** : modifier `resultat`, `base` ou `permissions` touche tout le
projet. Voir LOCKED_ZONES.md.
