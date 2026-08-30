# Image d'ARENA — construite depuis le premier commit du depot, jamais
# verifiee par rien jusqu'au 30/08/2026 (VOLET « ARENA en ligne », phase 3.1).
# `.github/workflows/ci.yml` avait deja trouve un probleme qu'elle aurait pu
# eviter (pywin32 sans marqueur de plateforme, resolu depuis) mais ne
# construisait jamais l'image elle-meme. Elle le fait desormais.

# --- Etape 1 : construction de la PWA (React + Vite) --------------------------
# `apps/pwa/dist/` est gitignore par construction (Vite le regenere) : sans
# cette etape, l'image ne contient jamais cette interface. `main.py` retombe
# alors sur l'ancienne interface classique, en silence — exactement ce qui
# s'est produit sur le premier deploiement en ligne (VOLET « ARENA en ligne »,
# chapitre 5).
FROM node:20-slim AS pwa-builder

WORKDIR /pwa
COPY apps/pwa/package.json apps/pwa/package-lock.json ./
RUN npm ci
COPY apps/pwa/ ./
RUN npm run build

# --- Etape 2 : l'image de service --------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# ffmpeg : audio/video (tools/audio, tools/video). curl : sonde de sante
# ci-dessous, sans lui HEALTHCHECK n'aurait aucun outil pour interroger le
# serveur depuis l'interieur du conteneur.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=pwa-builder /pwa/dist ./apps/pwa/dist

# Le proprietaire ne se connecte jamais a ce conteneur : il n'a besoin
# d'aucun privilege que le processus n'a pas lui-meme. Sans cette ligne,
# ARENA tournait en root — le compte le plus large qu'un conteneur puisse
# avoir, pour un serveur qui n'en a besoin d'aucun.
RUN useradd --create-home --shell /usr/sbin/nologin arena \
    && chown -R arena:arena /app
USER arena

EXPOSE 8000

# `/health` repond 200 tant que le processus repond, meme si Ollama est
# injoignable ou la cle absente (`apps/backend/main.py` documente pourquoi :
# les champs publics restent publics). C'est la bonne sonde ICI : elle mesure
# que le serveur vit, pas que chaque service distant repond — cette
# deuxieme question est celle du diagnostic applicatif (DEC-0022), pas celle
# d'un chef d'orchestration de conteneurs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
