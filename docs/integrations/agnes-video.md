# Agnes Video Generator integration

ARENA integrates Agnes as a **video provider**, not as a second autonomous application.

Upstream: `lcy362/agnes-video-generator` (MIT license).

## Design

`tools.video.AgnesVideoProvider` exposes Agnes task creation, status, artifacts and final-video retrieval to ARENA. The provider can be used directly for an Agnes-only generation or as one stage in an ARENA workflow.

This keeps the existing ARENA video stack authoritative: FFmpeg, cropping, subtitles and future image/audio providers can consume Agnes artifacts instead of being duplicated.

## Supported Agnes modes

- simple text-to-video / image-to-video task contract
- creative multi-scene tasks
- manuscript-to-video tasks
- poetry tasks
- digital-anchor tasks
- model and voice discovery
- task status, stop and resume
- artifact discovery
- final video retrieval

## Configuration

Run Agnes Video Generator separately and set:

`AGNES_VIDEO_URL=http://127.0.0.1:8765`

The Agnes service owns its `AGNES_API_KEY`; ARENA does not copy or persist that secret.

## Composition

The provider boundary is intentionally narrow so ARENA's orchestrator can combine Agnes with other tools. Typical flow:

`research/reasoning -> script -> Agnes scenes -> ARENA audio/subtitles -> FFmpeg -> final artifact`

Agnes can also produce the whole video by itself when that is the best route.

## Provenance

The integration contract was derived from the upstream public REST API documentation. No upstream source tree is vendored into ARENA. Preserve the upstream MIT attribution if code is later copied or adapted directly.
