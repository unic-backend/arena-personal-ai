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
FROM node:20-bookworm-slim AS pwa-builder

WORKDIR /pwa
COPY apps/pwa/package.json apps/pwa/package-lock.json ./
RUN npm ci
COPY apps/pwa/ ./
RUN npm run build

# --- Etape 2 : moteur Office Univer, version reproductible --------------------
# Le paquet public requiert Node >=24. Le runtime de developpement embarque
# n'est jamais confondu avec une licence de production par l'application.
FROM node:24-bookworm-slim AS univer-runtime
RUN npm install --global univer-cli@0.5.0 \
    && univer --version

# --- Etape 3 : l'image de service --------------------------------------------
# Meme base Debian que l'etape Node : les binaires copies ne traversent pas
# deux ABI systeme differentes.
FROM python:3.11-slim-bookworm

WORKDIR /app
ENV USMAN_CHROMA_PATH=/app/data/chroma_db

# Outils natifs réellement requis par les capacités livrées :
# - ffmpeg : audio/video ;
# - tesseract + données françaises : OCR des PDF scannés ;
# - LibreOffice Writer/Calc/Impress : conversions DOCX/XLSX/PPTX ;
# - cairo/pango/gdk-pixbuf : rendu WeasyPrint/CairoSVG ;
# - DejaVu : police déterministe des rendus/smoke tests ;
# - curl : sonde de santé ; gosu : abandon définitif des privilèges root.
# Les paquets LibreOffice sont ciblés plutôt que le méta-paquet complet et
# --no-install-recommends évite d'embarquer les composants sans usage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl gosu chromium \
    tesseract-ocr tesseract-ocr-fra \
    libreoffice-writer libreoffice-calc libreoffice-impress \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Node 24 et Univer CLI proviennent de l'etape epinglee ci-dessus. npm/npx/
# univer sont des liens vers /usr/local/lib/node_modules, donc ce repertoire
# voyage avec les executables.
COPY --from=univer-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=univer-runtime /usr/local/bin/npm /usr/local/bin/npm
COPY --from=univer-runtime /usr/local/bin/npx /usr/local/bin/npx
COPY --from=univer-runtime /usr/local/bin/univer /usr/local/bin/univer
COPY --from=univer-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

ENV UNIVER_RENDER_BROWSER=/usr/bin/chromium

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Moteur MIT specialise, version epinglee : utilise par /api/media/remove-gemini-watermark.
# `sharp` est le decodeur/encodeur requis par le chemin CLI fichier.
RUN npm install --global @pilio/gemini-watermark-remover@1.0.45 sharp@0.34.5 \
    && gwr --help >/dev/null \
    && node --version | grep -E '^v24\\.' \
    && univer --version \
    && chromium --version

COPY . .
COPY --from=pwa-builder /pwa/dist ./apps/pwa/dist

# Le proprietaire ne se connecte jamais a ce conteneur : il n'a besoin
# d'aucun privilege que le processus n'a pas lui-meme. Sans ces lignes,
# ARENA tournait en root — le compte le plus large qu'un conteneur puisse
# avoir, pour un serveur qui n'en a besoin d'aucun.
#
# Le conteneur demarre root — `USER arena` n'est PAS fixe ici — parce que
# `entrypoint.sh` doit pouvoir corriger les permissions d'un volume monte
# depuis l'hote avant de lacher les privileges. Voir ce fichier pour la
# panne reelle que ceci corrige.
RUN useradd --create-home --shell /usr/sbin/nologin arena \
    && chown -R arena:arena /app
RUN chmod +x apps/backend/entrypoint.sh

EXPOSE 8000

# `/health` repond 200 tant que le processus repond, meme si Ollama est
# injoignable ou la cle absente (`apps/backend/main.py` documente pourquoi :
# les champs publics restent publics). C'est la bonne sonde ICI : elle mesure
# que le serveur vit, pas que chaque service distant repond — cette
# deuxieme question est celle du diagnostic applicatif (DEC-0022), pas celle
# d'un chef d'orchestration de conteneurs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["apps/backend/entrypoint.sh"]
CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
