/* ─────────────────────────────────────────────────────────────
   Usman Export, Share & Backup Module
   · Formats: Markdown (.md), JSON backup (.json), Plain Text (.txt)
   · Native Web Share API integration
   · Backup importer with integrity validation
   ───────────────────────────────────────────────────────────── */

import type { Conversation, ChatMessage } from '../store/chatStore';

function sanitizeFilename(title: string): string {
  return (
    title
      .toLowerCase()
      .replace(/[^a-z0-9àâäçèéêëîïôöùûüÿ -]/g, '')
      .trim()
      .replace(/\s+/g, '-')
      .slice(0, 50) || 'conversation'
  );
}

function formatDate(ts: number): string {
  return new Date(ts).toLocaleString('fr-FR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Convert a conversation into a rich, structured Markdown document
 */
export function exportToMarkdown(conv: Conversation, appName = 'Usman'): string {
  const lines: string[] = [
    `# ${conv.title || 'Conversation'}`,
    '',
    `*Exporté depuis ${appName} le ${formatDate(Date.now())}*`,
    `*Créé le ${formatDate(conv.createdAt)} · ${conv.messages.length} messages*`,
    '',
    '---',
    '',
  ];

  conv.messages.forEach((msg) => {
    const isUser = msg.role === 'user';
    const roleTitle = isUser ? '### 👤 Utilisateur' : `### 🪐 ${appName}`;
    const timeStr = formatDate(msg.createdAt);

    lines.push(`${roleTitle}  *(le ${timeStr})*`);
    lines.push('');

    // Attachments info if present
    if (msg.meta?.attachments && msg.meta.attachments.length > 0) {
      lines.push('**Pièces jointes :**');
      msg.meta.attachments.forEach((att) => {
        lines.push(`- 📎 \`${att.name}\` (${att.kind}, ${(att.size / 1024).toFixed(1)} KB)`);
      });
      lines.push('');
    }

    // Message text
    if (msg.text) {
      lines.push(msg.text);
      lines.push('');
    }

    // Sources citations if present
    if (msg.meta?.sources && msg.meta.sources.length > 0) {
      lines.push('**Sources consultées :**');
      msg.meta.sources.forEach((src, idx) => {
        lines.push(`[${idx + 1}] [${src.title || src.domain}](${src.url || '#'}) (${src.domain}${src.date ? ` · ${src.date}` : ''})`);
      });
      lines.push('');
    }

    lines.push('---');
    lines.push('');
  });

  return lines.join('\n');
}

/**
 * Convert a conversation into clean Plain Text
 */
export function exportToPlainText(conv: Conversation, appName = 'Usman'): string {
  const lines: string[] = [
    `=== ${conv.title || 'Conversation'} ===`,
    `Date: ${formatDate(conv.createdAt)}`,
    `Exporté depuis ${appName}`,
    '====================================\n',
  ];

  conv.messages.forEach((msg) => {
    const isUser = msg.role === 'user';
    const prefix = isUser ? 'UTILISATEUR' : appName.toUpperCase();
    lines.push(`[${formatDate(msg.createdAt)}] ${prefix} :`);
    lines.push(msg.text);
    lines.push('\n------------------------------------\n');
  });

  return lines.join('\n');
}

/**
 * Export conversation(s) to formatted JSON
 */
export function exportToJson(data: Conversation | Conversation[]): string {
  return JSON.stringify(
    {
      app: 'Usman AI',
      version: '1.0.0',
      exportedAt: Date.now(),
      data: Array.isArray(data) ? data : [data],
    },
    null,
    2,
  );
}

/**
 * Trigger browser file download
 */
export function downloadFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Download a single conversation as Markdown
 */
export function downloadConversationMarkdown(conv: Conversation) {
  const md = exportToMarkdown(conv);
  const name = `${sanitizeFilename(conv.title || 'conversation')}_${new Date().toISOString().slice(0, 10)}.md`;
  downloadFile(name, md, 'text/markdown');
}

/**
 * Download a single conversation as Plain Text
 */
export function downloadConversationText(conv: Conversation) {
  const txt = exportToPlainText(conv);
  const name = `${sanitizeFilename(conv.title || 'conversation')}_${new Date().toISOString().slice(0, 10)}.txt`;
  downloadFile(name, txt, 'text/plain');
}

/**
 * Download a single conversation as JSON
 */
export function downloadConversationJson(conv: Conversation) {
  const json = exportToJson(conv);
  const name = `${sanitizeFilename(conv.title || 'conversation')}_${new Date().toISOString().slice(0, 10)}.json`;
  downloadFile(name, json, 'application/json');
}

/**
 * Download all conversations as a full JSON backup file
 */
export function downloadAllBackup(conversations: Conversation[]) {
  const json = exportToJson(conversations);
  const name = `usman_backup_${new Date().toISOString().slice(0, 10)}.json`;
  downloadFile(name, json, 'application/json');
}

/**
 * Use native Web Share API or copy to clipboard fallback
 */
export async function shareConversation(conv: Conversation): Promise<{ shared: boolean; method: 'native' | 'clipboard' }> {
  const text = exportToMarkdown(conv);
  const title = conv.title || 'Discussion Usman';

  if (typeof navigator !== 'undefined' && 'share' in navigator) {
    try {
      await navigator.share({
        title,
        text: text.slice(0, 4000), // Web share payload limit safety
      });
      return { shared: true, method: 'native' };
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        return { shared: false, method: 'native' };
      }
      // Fall through to clipboard
    }
  }

  // Fallback to clipboard
  try {
    await navigator.clipboard.writeText(text);
    return { shared: true, method: 'clipboard' };
  } catch {
    return { shared: false, method: 'clipboard' };
  }
}

/**
 * Validates and parses a JSON backup file content
 */
export function parseAndValidateBackup(jsonString: string): {
  valid: boolean;
  conversations?: Conversation[];
  error?: string;
} {
  try {
    const parsed = JSON.parse(jsonString);
    let items: any[] = [];

    if (Array.isArray(parsed)) {
      items = parsed;
    } else if (parsed && Array.isArray(parsed.data)) {
      items = parsed.data;
    } else if (parsed && typeof parsed.id === 'string' && Array.isArray(parsed.messages)) {
      items = [parsed];
    } else {
      return { valid: false, error: 'Structure de sauvegarde non reconnue.' };
    }

    const validConversations: Conversation[] = [];

    for (const item of items) {
      if (!item || typeof item.id !== 'string' || !Array.isArray(item.messages)) {
        continue;
      }

      const validMessages: ChatMessage[] = [];
      for (const m of item.messages) {
        if (m && (m.role === 'user' || m.role === 'assistant') && typeof m.text === 'string') {
          validMessages.push({
            id: m.id || `msg_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
            role: m.role,
            text: m.text,
            live: '',
            status: 'done',
            activity: Array.isArray(m.activity) ? m.activity : [],
            createdAt: typeof m.createdAt === 'number' ? m.createdAt : Date.now(),
            meta: m.meta,
            variants: Array.isArray(m.variants) ? m.variants : undefined,
            variantIndex: typeof m.variantIndex === 'number' ? m.variantIndex : undefined,
          });
        }
      }

      validConversations.push({
        id: item.id || `conv_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        title: item.title || 'Discussion importée',
        messages: validMessages,
        createdAt: typeof item.createdAt === 'number' ? item.createdAt : Date.now(),
        updatedAt: typeof item.updatedAt === 'number' ? item.updatedAt : Date.now(),
        pinned: Boolean(item.pinned),
      });
    }

    if (validConversations.length === 0) {
      return { valid: false, error: 'Aucune discussion valide trouvée dans ce fichier.' };
    }

    return { valid: true, conversations: validConversations };
  } catch (err) {
    return { valid: false, error: 'Fichier JSON corrompu ou illisible.' };
  }
}
