/* Unified, client-side attachment preparation. No analysis result is invented. */

export type AttachmentKind = 'image' | 'pdf' | 'document' | 'audio' | 'video';
export type AttachmentStatus = 'processing' | 'ready' | 'failed';

export interface AttachmentMetadata {
  [key: string]: string | number | boolean | undefined;
  width?: number;
  height?: number;
  duration?: number;
  pages?: number;
  characters?: number;
  lines?: number;
  format?: string;
}

export interface AttachmentSummary {
  id: string;
  name: string;
  size: number;
  type: string;
  kind: AttachmentKind;
  preview?: string;
  metadata?: AttachmentMetadata;
}

export interface PendingAttachment extends AttachmentSummary {
  file: File;
  url: string;
  status: AttachmentStatus;
  error?: string;
  /** Local text extraction for plain-text formats; capped before storage. */
  extractedText?: string;
}

export const MAX_ATTACHMENTS = 5;
export const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;

const DOCUMENT_EXTENSIONS = new Set([
  'txt', 'md', 'markdown', 'csv', 'json', 'xml', 'html', 'htm', 'yaml', 'yml',
  'log', 'js', 'jsx', 'ts', 'tsx', 'py', 'css', 'sql', 'docx',
]);

function extension(name: string) {
  return name.toLowerCase().split('.').pop() ?? '';
}

export function attachmentKind(file: Pick<File, 'name' | 'type'>): AttachmentKind | null {
  const ext = extension(file.name);
  if (file.type.startsWith('image/')) return 'image';
  if (file.type === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (file.type.startsWith('audio/')) return 'audio';
  if (file.type.startsWith('video/')) return 'video';
  if (
    file.type.startsWith('text/') ||
    file.type.includes('json') ||
    file.type.includes('xml') ||
    file.type.includes('wordprocessingml') ||
    DOCUMENT_EXTENSIONS.has(ext)
  ) return 'document';
  return null;
}

function uid() {
  return `att_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function mediaMetadata(url: string, kind: 'audio' | 'video') {
  return new Promise<AttachmentMetadata>((resolve, reject) => {
    const el = document.createElement(kind);
    const timeout = setTimeout(() => {
      el.src = '';
      reject(new Error('media metadata timeout'));
    }, 8000);
    el.preload = 'metadata';
    el.onloadedmetadata = () => {
      clearTimeout(timeout);
      const video = el as HTMLVideoElement;
      resolve({
        duration: Number.isFinite(el.duration) ? el.duration : undefined,
        ...(kind === 'video' ? { width: video.videoWidth, height: video.videoHeight } : {}),
      });
      el.src = '';
    };
    el.onerror = () => {
      clearTimeout(timeout);
      reject(new Error('unsupported media container or codec'));
    };
    el.src = url;
  });
}

function prepareImage(url: string): Promise<{ preview: string; metadata: AttachmentMetadata }> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const max = 180;
      const scale = Math.min(1, max / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      const ctx = canvas.getContext('2d');
      if (!ctx) return reject(new Error('canvas is unavailable'));
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      resolve({
        preview: canvas.toDataURL('image/jpeg', 0.65),
        metadata: { width: image.naturalWidth, height: image.naturalHeight },
      });
    };
    image.onerror = () => reject(new Error('image could not be decoded'));
    image.src = url;
  });
}

async function inspectPdf(file: File): Promise<AttachmentMetadata> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.length < 5 || new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-') {
    throw new Error('invalid PDF signature');
  }
  // A conservative structural page estimate; authoritative extraction happens server-side.
  const source = new TextDecoder('latin1').decode(bytes);
  const pages = (source.match(/\/Type\s*\/Page\b/g) ?? []).length;
  return { pages: pages || undefined, format: 'PDF' };
}

async function inspectDocument(file: File): Promise<{
  metadata: AttachmentMetadata;
  extractedText?: string;
}> {
  const ext = extension(file.name);
  const binaryDocx = ext === 'docx' || file.type.includes('wordprocessingml');
  if (binaryDocx) return { metadata: { format: 'DOCX' } };
  const text = await file.text();
  return {
    metadata: {
      characters: text.length,
      lines: text ? text.split(/\r?\n/).length : 0,
      format: ext.toUpperCase() || 'TEXT',
    },
    extractedText: text.slice(0, 200_000),
  };
}

export function pendingShell(file: File): PendingAttachment {
  const kind = attachmentKind(file);
  if (!kind) throw new Error('unsupported file type');
  return {
    id: uid(),
    name: file.name,
    size: file.size,
    type: file.type || 'application/octet-stream',
    kind,
    file,
    url: URL.createObjectURL(file),
    status: 'processing',
  };
}

export async function prepareAttachment(shell: PendingAttachment): Promise<PendingAttachment> {
  try {
    if (shell.size > MAX_ATTACHMENT_BYTES) {
      throw new Error(`file exceeds ${MAX_ATTACHMENT_BYTES / 1024 / 1024} MB`);
    }
    if (shell.kind === 'image') {
      const result = await prepareImage(shell.url);
      return { ...shell, ...result, status: 'ready' };
    }
    if (shell.kind === 'audio' || shell.kind === 'video') {
      const metadata = await mediaMetadata(shell.url, shell.kind);
      return { ...shell, metadata, status: 'ready' };
    }
    if (shell.kind === 'pdf') {
      return { ...shell, metadata: await inspectPdf(shell.file), status: 'ready' };
    }
    const result = await inspectDocument(shell.file);
    return { ...shell, ...result, status: 'ready' };
  } catch (error) {
    return {
      ...shell,
      status: 'failed',
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

export function summarizeAttachment(value: PendingAttachment): AttachmentSummary {
  return {
    id: value.id,
    name: value.name,
    size: value.size,
    type: value.type,
    kind: value.kind,
    preview: value.preview,
    metadata: value.metadata,
  };
}

export function releaseAttachment(value: PendingAttachment) {
  try { URL.revokeObjectURL(value.url); } catch { /* ignore */ }
}
