/* ─────────────────────────────────────────────────────────────
   Video engine — genuine client-side video operations.
   · probe:      real container metadata via HTMLVideoElement
   · thumbnails: real frame captures via canvas seeking
   · trim:       real re-encode via captureStream + MediaRecorder
   Every number the UI shows comes from the actual media pipeline.
   ───────────────────────────────────────────────────────────── */

export interface AttachedVideo {
  name: string;
  size: number;
  type: string;
  url: string; // blob: URL, session-scoped
}

export interface VideoMeta {
  name: string;
  size: number;
  type: string;
  duration: number;
  width: number;
  height: number;
}

function makeVideo(url: string): Promise<HTMLVideoElement> {
  return new Promise((resolve, reject) => {
    const v = document.createElement('video');
    v.preload = 'metadata';
    v.muted = true;
    v.playsInline = true;
    v.src = url;
    v.onloadedmetadata = () => resolve(v);
    v.onerror = () => reject(new Error('The container could not be decoded'));
  });
}

export async function probeVideo(file: AttachedVideo): Promise<VideoMeta> {
  const v = await makeVideo(file.url);
  const meta: VideoMeta = {
    name: file.name,
    size: file.size,
    type: file.type || v.currentSrc.split(';')[0] || 'video/*',
    duration: isFinite(v.duration) ? v.duration : 0,
    width: v.videoWidth,
    height: v.videoHeight,
  };
  v.src = '';
  return meta;
}

function seekTo(v: HTMLVideoElement, t: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const to = setTimeout(() => reject(new Error('seek timeout')), 5000);
    v.onseeked = () => { clearTimeout(to); resolve(); };
    v.currentTime = t;
  });
}

export interface Thumb { ts: number; dataUrl: string }

export async function extractThumbnails(
  file: AttachedVideo,
  duration: number,
  count = 5,
  onFrame?: (done: number, total: number) => void,
): Promise<Thumb[]> {
  const v = await makeVideo(file.url);
  v.preload = 'auto';
  const w = 200;
  const h = Math.max(2, Math.round((w * (v.videoHeight || 9)) / (v.videoWidth || 16)));
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const g = canvas.getContext('2d')!;
  const thumbs: Thumb[] = [];
  const span = Math.max(duration - 0.2, 0.5);
  for (let i = 0; i < count; i++) {
    const ts = duration <= 0.5 ? i * 0.1 : 0.1 + (span * (i + 0.5)) / count;
    await seekTo(v, Math.min(ts, Math.max(duration - 0.05, 0)));
    g.drawImage(v, 0, 0, w, h);
    thumbs.push({ ts: v.currentTime, dataUrl: canvas.toDataURL('image/jpeg', 0.72) });
    onFrame?.(i + 1, count);
  }
  v.src = '';
  return thumbs;
}

export interface TrimResult {
  blobUrl: string;
  size: number;
  mimeType: string;
}

const MIME_CANDIDATES = [
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm',
  'video/mp4',
];

export function trimSupported(): boolean {
  return (
    typeof MediaRecorder !== 'undefined' &&
    'captureStream' in HTMLVideoElement.prototype &&
    MIME_CANDIDATES.some((m) => MediaRecorder.isTypeSupported(m))
  );
}

export async function trimVideo(
  file: AttachedVideo,
  start: number,
  end: number,
  onProgress?: (ratio: number, at: number) => void,
  shouldAbort?: () => boolean,
): Promise<TrimResult> {
  const v = await makeVideo(file.url);
  const stream: MediaStream =
    (v as HTMLVideoElement & { captureStream?: () => MediaStream }).captureStream!();
  const mimeType = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m))!;
  const rec = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 2_500_000 });
  const parts: BlobPart[] = [];
  rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };

  const done = new Promise<void>((resolve, reject) => {
    let lastEmit = 0;
    v.ontimeupdate = () => {
      const now = performance.now();
      if (now - lastEmit > 400) {
        lastEmit = now;
        onProgress?.(Math.min(1, (v.currentTime - start) / (end - start)), v.currentTime);
      }
      if (v.currentTime >= end || (shouldAbort && shouldAbort())) v.pause();
    };
    v.onpause = () => { if (rec.state !== 'inactive') rec.stop(); };
    rec.onstop = () => resolve();
    rec.onerror = () => reject(new Error('recorder error'));
  });

  await seekTo(v, start);
  rec.start(250);
  await v.play();
  await done;
  v.src = '';

  const blob = new Blob(parts, { type: mimeType.split(';')[0] });
  if (!blob.size) throw new Error('recording produced no data');
  return { blobUrl: URL.createObjectURL(blob), size: blob.size, mimeType: blob.type };
}

/* ── formatting ── */

export function fmtTime(sec: number): string {
  if (!isFinite(sec)) return '∞';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** parse trim boundaries from natural text: "de 0:05 à 0:20", "trim 5s to 25s" */
export function parseTrimRange(text: string): { start: number; end: number } | undefined {
  if (!/trim|coupe|découpe|decoupe|cut|extrait|clip|garde/i.test(text)) return undefined;
  const times: number[] = [];
  const clock = /(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?/g;
  let m: RegExpExecArray | null;
  while ((m = clock.exec(text))) {
    const a = parseInt(m[1], 10);
    const b = parseInt(m[2], 10);
    const c = m[3] ? parseInt(m[3], 10) : 0;
    times.push(m[3] ? a * 3600 + b * 60 + c : a * 60 + b);
  }
  if (times.length < 2) {
    const sec = /(\d+(?:\.\d+)?)\s*(?:s|sec|secondes?)\b/gi;
    while ((m = sec.exec(text))) times.push(parseFloat(m[1]));
  }
  if (times.length >= 2) {
    const [start, end] = [times[0], times[1]];
    if (end > start) return { start, end };
  }
  if (times.length === 1 && /trim|coupe|découpe|decoupe|cut/i.test(text)) {
    return { start: 0, end: times[0] };
  }
  return undefined;
}
