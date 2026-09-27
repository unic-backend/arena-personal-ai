# call.md — adoption selective review (2026-09-27)

Source reviewed: `video-db/call.md`.

## What was verified

- Public TypeScript/Electron project focused on recorded meetings, transcription,
  live assistance, conversation metrics, summaries and action items.
- `package.json` declares `"license": "MIT"`.
- GitHub did not expose a repository-level `LICENSE` file during this review,
  so ARENA does not copy source code from the project.
- The upstream transcription/AI path relies on VideoDB services and credentials.
- The repository had recent maintenance activity in August 2026, including
  desktop security/runtime hardening changes.

## Decision

Do **not** vendor, install or depend on call.md/VideoDB.

ARENA already owns the required local building blocks: media upload, FFmpeg,
Faster-Whisper, the model router and the PWA chat path. The useful product ideas
are implemented natively through those existing components:

1. recorded audio/video meeting -> existing media storage;
2. FFmpeg -> existing local Faster-Whisper transcription;
3. deterministic metrics from transcript/duration;
4. grounded summary, key points, explicit decisions and action items;
5. speaker ratios only when upstream segments contain real speaker/channel
   labels; no diarization is invented.

## Intentionally not adopted

- VideoDB cloud dependency or API key;
- Electron desktop shell;
- duplicate SQLite/settings/MCP stacks;
- live dual-channel capture and real-time coaching, because ARENA does not yet
  have a verified system-audio + microphone capture path with trustworthy
  speaker separation on all target devices.

Those features should only be added when their capture path can be exercised
end-to-end, not as dormant UI or simulated capability.
