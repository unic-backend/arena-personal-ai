# Docker

## Reproducibility first
- A deployment is reproducible before it is fast — a build that only works
  "on my machine" because of a cached layer or a locally-installed tool is
  not a working Dockerfile.
- Pin base image versions and dependency versions explicitly. A `:latest`
  tag or an unpinned `pip install -r requirements.txt` without a lockfile
  means the same Dockerfile can produce a different image tomorrow.

## Layers
- Order instructions from least to most frequently changing (system
  packages, then dependency manifests + install, then application code)
  so the dependency-install layer stays cached across ordinary code
  changes — rebuilding the world for a one-line code edit is a sign the
  layer order is wrong, not that the build is inherently slow.
- Copy only what the build actually needs (`.dockerignore` matters as much
  as the `Dockerfile` itself) — a stray `.env`, `node_modules`, or `.git`
  directory copied into an image is both slower and a potential secret
  leak.

## Secrets
- Secrets come from the environment at run time (`docker run -e`,
  a secrets manager, an orchestrator's own mechanism), never baked into an
  image layer with `ENV` or `COPY` — a layer is part of the image history
  and is not erased by a later layer that "removes" the file.

## Verification
- A container that starts is not a container that works. Verify the
  actual capability the image exists to provide (a real HTTP response, a
  real command executed inside it) — the same discipline this codebase
  already applies to its own CI (`Verify the container starts with no
  volume at all`, `apps/backend`'s own workflow).
- Test the rollback path, not only the forward deploy — a backup or image
  that has never been restored does not, for practical purposes, exist.
