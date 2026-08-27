/* ─────────────────────────────────────────────────────────────
   Chat store — consumes the activity-event stream in real time
   and projects it into renderable state. Completed activity is
   persisted with the conversation; transient running states are
   normalized to 'cancelled' on reload (never stuck).
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import {
  ActivityNode, MessageMeta, StreamChunk, upsertNode, normalizeLoaded, findNode,
} from '../activity/types';
import { localTransport } from '../activity/transport';
import { makeRemoteTransport } from '../activity/remoteTransport';
import { activeRemoteCfg } from './backendStore';
import { AgentContext } from '../agent/orchestrator';
import { loadVFS, saveVFS, resetVFS, VFS } from '../agent/vfs';
import { runShell } from '../agent/exec';
import { agentStrings } from '../agent/strings';
import {
  MAX_ATTACHMENTS,
  PendingAttachment,
  pendingShell,
  prepareAttachment,
  releaseAttachment,
  summarizeAttachment,
} from '../attachments';
import { useSpeech } from '../speech';
import { triggerHaptic } from '../theme';
import { uiLocale, useI18n } from '../i18n';

export interface MessageVariant {
  id: string;
  text: string;
  activity?: ActivityNode[];
  meta?: MessageMeta & { durationMs?: number };
  error?: string;
  createdAt: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  live: string;
  status: 'idle' | 'working' | 'streaming' | 'done' | 'error' | 'cancelled';
  activity: ActivityNode[];
  createdAt: number;
  meta?: MessageMeta & { durationMs?: number };
  error?: string;
  variants?: MessageVariant[];
  variantIndex?: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
  pinned?: boolean;
}

export interface LogEntry {
  ts: number;
  chunk: StreamChunk;
}

const CHAT_KEY = 'usman.chats.v1';

function uid(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(CHAT_KEY);
    if (!raw) return [];
    const convs = JSON.parse(raw) as Conversation[];
    return convs.map((c) => ({
      ...c,
      messages: c.messages.map((m) =>
        m.role === 'assistant'
          ? {
              ...m,
              activity: normalizeLoaded(m.activity),
              status: m.status === 'working' || m.status === 'streaming' ? 'done' : m.status,
              text: m.text || m.live,
              variants: m.variants
                ? m.variants.map((v) => ({ ...v, activity: normalizeLoaded(v.activity ?? []) }))
                : undefined,
            }
          : m,
      ),
    }));
  } catch {
    return [];
  }
}

function persist(conversations: Conversation[]) {
  try {
    // Session previews are data URLs; omit them to keep mobile localStorage healthy.
    localStorage.setItem(
      CHAT_KEY,
      JSON.stringify(conversations.slice(0, 30), (key, value) => (key === 'preview' ? undefined : value)),
    );
  } catch {
    /* storage full — ignore */
  }
}

interface ChatState {
  conversations: Conversation[];
  activeId: string | null;
  isRunning: boolean;
  eventLog: LogEntry[];
  logOpen: boolean;
  pendingAttachments: PendingAttachment[];
  attachmentError?: string;
  toggleLog(): void;
  clearLog(): void;
  newChat(): string;
  selectConversation(id: string): void;
  deleteConversation(id: string): void;
  renameConversation(id: string, newTitle: string): void;
  togglePinConversation(id: string): void;
  clearAllConversations(): void;
  importConversations(imported: Conversation[], mode?: 'merge' | 'replace'): number;
  addPendingFiles(files: File[]): Promise<void>;
  removePendingAttachment(id: string): void;
  send(text: string): Promise<void>;
  editUserMessage(messageId: string, newText: string): Promise<void>;
  regenerateAssistant(messageId: string): Promise<void>;
  switchVariant(messageId: string, targetIndex: number): void;
  cancel(): void;
  rerunCommand(conversationId: string, messageId: string, nodeId: string): Promise<void>;
  resetWorkspace(): void;
  vfsVersion: number;
}

let abort: AbortController | null = null;
let tree: VFS = loadVFS();

export const vfsContext: AgentContext = {
  getTree: () => tree,
  setTree: (v) => {
    tree = v;
    saveVFS(v);
  },
};

export const useChat = create<ChatState>((set, get) => ({
  conversations: loadConversations(),
  activeId: null,
  isRunning: false,
  eventLog: [],
  logOpen: false,
  pendingAttachments: [],
  attachmentError: undefined,
  vfsVersion: 0,

  async addPendingFiles(files) {
    const capacity = Math.max(0, MAX_ATTACHMENTS - get().pendingAttachments.length);
    if (!capacity) {
      set({ attachmentError: useI18n.getState().t('composer.maxFiles', { n: MAX_ATTACHMENTS }) });
      return;
    }
    const shells: PendingAttachment[] = [];
    let rejected = 0;
    for (const file of files.slice(0, capacity)) {
      try {
        shells.push(pendingShell(file));
      } catch {
        rejected++;
      }
    }
    if (files.length > capacity) rejected += files.length - capacity;
    set((s) => ({
      pendingAttachments: [...s.pendingAttachments, ...shells],
      attachmentError: rejected ? useI18n.getState().t('composer.rejectedFiles', { n: rejected }) : undefined,
    }));
    await Promise.all(
      shells.map(async (shell) => {
        const ready = await prepareAttachment(shell);
        set((s) => ({
          pendingAttachments: s.pendingAttachments.map((value) => (value.id === ready.id ? ready : value)),
          attachmentError: ready.status === 'failed' ? `${ready.name}: ${ready.error}` : s.attachmentError,
        }));
      }),
    );
  },

  removePendingAttachment: (id) =>
    set((s) => {
      const value = s.pendingAttachments.find((item) => item.id === id);
      if (value) releaseAttachment(value);
      return {
        pendingAttachments: s.pendingAttachments.filter((item) => item.id !== id),
        attachmentError: undefined,
      };
    }),

  toggleLog: () => set((s) => ({ logOpen: !s.logOpen })),
  clearLog: () => set({ eventLog: [] }),

  newChat: () => {
    useSpeech.getState().stop();
    const id = uid('conv');
    const conv: Conversation = {
      id,
      title: 'New conversation',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    set((s) => {
      const conversations = [conv, ...s.conversations];
      persist(conversations);
      return { conversations, activeId: id };
    });
    return id;
  },

  selectConversation: (id) => {
    useSpeech.getState().stop();
    set({ activeId: id });
  },

  deleteConversation: (id) => {
    useSpeech.getState().stop();
    set((s) => {
      const conversations = s.conversations.filter((c) => c.id !== id);
      persist(conversations);
      return { conversations, activeId: s.activeId === id ? null : s.activeId };
    });
  },

  renameConversation: (id, newTitle) => {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    set((s) => {
      const conversations = s.conversations.map((c) => (c.id === id ? { ...c, title: trimmed } : c));
      persist(conversations);
      return { conversations };
    });
  },

  togglePinConversation: (id) => {
    set((s) => {
      const conversations = s.conversations.map((c) => (c.id === id ? { ...c, pinned: !c.pinned } : c));
      persist(conversations);
      return { conversations };
    });
  },

  clearAllConversations: () => {
    useSpeech.getState().stop();
    set({ conversations: [], activeId: null });
    persist([]);
  },

  importConversations: (imported, mode = 'merge') => {
    useSpeech.getState().stop();
    if (!imported.length) return 0;

    let updated: Conversation[];
    if (mode === 'replace') {
      updated = imported;
    } else {
      const existingIds = new Set(get().conversations.map((c) => c.id));
      const newItems = imported.filter((c) => !existingIds.has(c.id));
      updated = [...newItems, ...get().conversations];
    }

    persist(updated);
    set({
      conversations: updated,
      activeId: updated[0]?.id || null,
    });
    return imported.length;
  },

  cancel: () => abort?.abort(),

  resetWorkspace: () => {
    tree = resetVFS();
    set((s) => ({ vfsVersion: s.vfsVersion + 1 }));
  },

  async send(text: string) {
    if (get().isRunning) return;
    const attachments = get().pendingAttachments;
    if (attachments.some((value) => value.status !== 'ready')) return;
    if (!text.trim() && !attachments.length) return;
    const videoAttachment =
      attachments.length === 1 && attachments[0]?.kind === 'video' ? attachments[0] : undefined;
    const video = videoAttachment
      ? {
          name: videoAttachment.name,
          size: videoAttachment.size,
          type: videoAttachment.type,
          url: videoAttachment.url,
        }
      : undefined;
    let convId = get().activeId;
    if (!convId) convId = get().newChat();
    set({ pendingAttachments: [], attachmentError: undefined });

    const visibleText = text.trim() || useI18n.getState().t('composer.attachmentDefault');
    const title = text.trim() || attachments[0]?.name || 'Attachment';

    const userMsg: ChatMessage = {
      id: uid('msg'),
      role: 'user',
      text: visibleText,
      live: '',
      status: 'done',
      activity: [],
      createdAt: Date.now(),
      variants: [{ id: uid('var'), text: visibleText, createdAt: Date.now() }],
      variantIndex: 0,
      ...(attachments.length ? { meta: { attachments: attachments.map(summarizeAttachment) } } : {}),
    };
    const assistantMsg: ChatMessage = {
      id: uid('msg'),
      role: 'assistant',
      text: '',
      live: '',
      status: 'working',
      activity: [],
      createdAt: Date.now(),
    };

    const patchMessages = (fn: (m: ChatMessage) => ChatMessage) =>
      set((s) => {
        const conversations = s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                updatedAt: Date.now(),
                title: c.messages.length === 0 ? title.slice(0, 52) : c.title,
                messages: c.messages.map(fn),
              }
            : c,
        );
        return { conversations };
      });

    set((s) => ({
      isRunning: true,
      conversations: s.conversations.map((c) =>
        c.id === convId
          ? {
              ...c,
              title: c.messages.length === 0 ? title.slice(0, 52) : c.title,
              updatedAt: Date.now(),
              messages: [...c.messages, userMsg, assistantMsg],
            }
          : c,
      ),
    }));

    abort = new AbortController();
    const log = (chunk: StreamChunk) =>
      set((s) => ({ eventLog: [...s.eventLog.slice(-399), { ts: Date.now(), chunk }] }));

    const startedAt = Date.now();
    try {
      /* Video editing stays on-device; other attachments use the secure remote upload. */
      const remote = attachments.some((value) => value.kind === 'video') ? null : activeRemoteCfg();
      const conv = get().conversations.find((c) => c.id === convId);
      const history = (conv?.messages ?? [])
        .filter((m) => m.text && m.id !== assistantMsg.id)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.text }));
      const transport = remote ? makeRemoteTransport(remote) : localTransport;
      const stream = transport.run({ text: visibleText, video, attachments, history }, vfsContext, abort.signal);
      for await (const chunk of stream) {
        log(chunk);
        if (chunk.type === 'activity') {
          const ev = chunk.event;
          patchMessages((m) => (m.id === assistantMsg.id ? { ...m, activity: upsertNode(m.activity, ev) } : m));
        } else if (chunk.type === 'token') {
          patchMessages((m) =>
            m.id === assistantMsg.id ? { ...m, live: m.live + chunk.text, status: 'streaming' } : m,
          );
        } else if (chunk.type === 'done') {
          triggerHaptic('success');
          patchMessages((m) => {
            if (m.id !== assistantMsg.id) return m;
            const finalVariant: MessageVariant = {
              id: uid('var'),
              text: m.live,
              activity: m.activity,
              meta: { ...chunk.meta, durationMs: Date.now() - startedAt },
              createdAt: Date.now(),
            };
            return {
              ...m,
              text: m.live,
              status: 'done',
              meta: { ...chunk.meta, durationMs: Date.now() - startedAt },
              variants: [finalVariant],
              variantIndex: 0,
            };
          });
        }
      }
    } catch (err) {
      const cancelled = err instanceof DOMException && err.name === 'AbortError';
      if (!cancelled) triggerHaptic('warning');
      patchMessages((m) =>
        m.id === assistantMsg.id
          ? {
              ...m,
              status: cancelled ? 'cancelled' : 'error',
              text: m.live || (cancelled ? useI18n.getState().t('msg.cancelled') : ''),
              error: cancelled ? undefined : String(err),
              activity: m.activity,
            }
          : m,
      );
    } finally {
      attachments.forEach(releaseAttachment);
      abort = null;
      set((s) => {
        const conversations = s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === assistantMsg.id ? { ...m, activity: normalizeLoaded(m.activity) } : m,
                ),
              }
            : c,
        );
        persist(conversations);
        return { isRunning: false, conversations };
      });
    }
  },

  /* Edit a user message and re-stream the answer from that turn */
  async editUserMessage(messageId: string, newText: string) {
    if (get().isRunning || !newText.trim()) return;
    const convId = get().activeId;
    if (!convId) return;
    const conv = get().conversations.find((c) => c.id === convId);
    if (!conv) return;

    useSpeech.getState().stop();

    const userMsgIndex = conv.messages.findIndex((m) => m.id === messageId);
    if (userMsgIndex === -1) return;
    const oldUserMsg = conv.messages[userMsgIndex];
    if (oldUserMsg.role !== 'user') return;

    const trimmedText = newText.trim();
    const prevVariants: MessageVariant[] =
      oldUserMsg.variants && oldUserMsg.variants.length > 0
        ? oldUserMsg.variants
        : [{ id: uid('var'), text: oldUserMsg.text, createdAt: oldUserMsg.createdAt }];

    const newVariant: MessageVariant = {
      id: uid('var'),
      text: trimmedText,
      createdAt: Date.now(),
    };

    const updatedUserMsg: ChatMessage = {
      ...oldUserMsg,
      text: trimmedText,
      variants: [...prevVariants, newVariant],
      variantIndex: prevVariants.length,
    };

    const assistantMsg: ChatMessage = {
      id: uid('msg'),
      role: 'assistant',
      text: '',
      live: '',
      status: 'working',
      activity: [],
      createdAt: Date.now(),
    };

    // Keep messages before this user message, place updated user message, then fresh assistant message
    const truncatedMessages = [...conv.messages.slice(0, userMsgIndex), updatedUserMsg, assistantMsg];

    const patchMessages = (fn: (m: ChatMessage) => ChatMessage) =>
      set((s) => {
        const conversations = s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                updatedAt: Date.now(),
                messages: c.messages.map(fn),
              }
            : c,
        );
        return { conversations };
      });

    set((s) => ({
      isRunning: true,
      conversations: s.conversations.map((c) =>
        c.id === convId ? { ...c, updatedAt: Date.now(), messages: truncatedMessages } : c,
      ),
    }));

    abort = new AbortController();
    const log = (chunk: StreamChunk) =>
      set((s) => ({ eventLog: [...s.eventLog.slice(-399), { ts: Date.now(), chunk }] }));

    const startedAt = Date.now();
    try {
      const remote = activeRemoteCfg();
      const history = truncatedMessages
        .slice(0, -1) // exclude current assistant message
        .filter((m) => m.text)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.text }));

      const transport = remote ? makeRemoteTransport(remote) : localTransport;
      const stream = transport.run({ text: trimmedText, history }, vfsContext, abort.signal);

      for await (const chunk of stream) {
        log(chunk);
        if (chunk.type === 'activity') {
          const ev = chunk.event;
          patchMessages((m) => (m.id === assistantMsg.id ? { ...m, activity: upsertNode(m.activity, ev) } : m));
        } else if (chunk.type === 'token') {
          patchMessages((m) =>
            m.id === assistantMsg.id ? { ...m, live: m.live + chunk.text, status: 'streaming' } : m,
          );
        } else if (chunk.type === 'done') {
          patchMessages((m) => {
            if (m.id !== assistantMsg.id) return m;
            const finalVariant: MessageVariant = {
              id: uid('var'),
              text: m.live,
              activity: m.activity,
              meta: { ...chunk.meta, durationMs: Date.now() - startedAt },
              createdAt: Date.now(),
            };
            return {
              ...m,
              text: m.live,
              status: 'done',
              meta: { ...chunk.meta, durationMs: Date.now() - startedAt },
              variants: [finalVariant],
              variantIndex: 0,
            };
          });
        }
      }
    } catch (err) {
      const cancelled = err instanceof DOMException && err.name === 'AbortError';
      patchMessages((m) =>
        m.id === assistantMsg.id
          ? {
              ...m,
              status: cancelled ? 'cancelled' : 'error',
              text: m.live || (cancelled ? useI18n.getState().t('msg.cancelled') : ''),
              error: cancelled ? undefined : String(err),
              activity: m.activity,
            }
          : m,
      );
    } finally {
      abort = null;
      set((s) => {
        const conversations = s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === assistantMsg.id ? { ...m, activity: normalizeLoaded(m.activity) } : m,
                ),
              }
            : c,
        );
        persist(conversations);
        return { isRunning: false, conversations };
      });
    }
  },

  /* Regenerate an assistant response with a new variant */
  async regenerateAssistant(messageId: string) {
    if (get().isRunning) return;
    const convId = get().activeId;
    if (!convId) return;
    const conv = get().conversations.find((c) => c.id === convId);
    if (!conv) return;

    useSpeech.getState().stop();

    const assistantIndex = conv.messages.findIndex((m) => m.id === messageId);
    if (assistantIndex === -1) return;
    const oldAssistant = conv.messages[assistantIndex];
    if (oldAssistant.role !== 'assistant') return;

    // Find the preceding user message
    const precedingUserMsg = conv.messages
      .slice(0, assistantIndex)
      .reverse()
      .find((m) => m.role === 'user');
    if (!precedingUserMsg || !precedingUserMsg.text) return;

    // Save existing assistant response in variants if not saved
    const existingVariants: MessageVariant[] =
      oldAssistant.variants && oldAssistant.variants.length > 0
        ? oldAssistant.variants
        : oldAssistant.text
          ? [
              {
                id: uid('var'),
                text: oldAssistant.text,
                activity: oldAssistant.activity,
                meta: oldAssistant.meta,
                error: oldAssistant.error,
                createdAt: oldAssistant.createdAt,
              },
            ]
          : [];

    const patchMessages = (fn: (m: ChatMessage) => ChatMessage) =>
      set((s) => {
        const conversations = s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                updatedAt: Date.now(),
                messages: c.messages.map(fn),
              }
            : c,
        );
        return { conversations };
      });

    // Reset this assistant message to working state while keeping variants history
    patchMessages((m) =>
      m.id === messageId
        ? {
            ...m,
            text: '',
            live: '',
            status: 'working',
            activity: [],
            error: undefined,
            meta: undefined,
            variants: existingVariants,
          }
        : m,
    );

    set({ isRunning: true });
    abort = new AbortController();
    const log = (chunk: StreamChunk) =>
      set((s) => ({ eventLog: [...s.eventLog.slice(-399), { ts: Date.now(), chunk }] }));

    const startedAt = Date.now();
    try {
      const remote = activeRemoteCfg();
      const history = conv.messages
        .slice(0, assistantIndex)
        .filter((m) => m.text)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.text }));

      const transport = remote ? makeRemoteTransport(remote) : localTransport;
      const stream = transport.run({ text: precedingUserMsg.text, history }, vfsContext, abort.signal);

      for await (const chunk of stream) {
        log(chunk);
        if (chunk.type === 'activity') {
          const ev = chunk.event;
          patchMessages((m) => (m.id === messageId ? { ...m, activity: upsertNode(m.activity, ev) } : m));
        } else if (chunk.type === 'token') {
          patchMessages((m) => (m.id === messageId ? { ...m, live: m.live + chunk.text, status: 'streaming' } : m));
        } else if (chunk.type === 'done') {
          patchMessages((m) => {
            if (m.id !== messageId) return m;
            const newVariant: MessageVariant = {
              id: uid('var'),
              text: m.live,
              activity: m.activity,
              meta: { ...chunk.meta, durationMs: Date.now() - startedAt },
              createdAt: Date.now(),
            };
            const updatedVariants = [...existingVariants, newVariant];
            return {
              ...m,
              text: m.live,
              status: 'done',
              meta: { ...chunk.meta, durationMs: Date.now() - startedAt },
              variants: updatedVariants,
              variantIndex: updatedVariants.length - 1,
            };
          });
        }
      }
    } catch (err) {
      const cancelled = err instanceof DOMException && err.name === 'AbortError';
      patchMessages((m) =>
        m.id === messageId
          ? {
              ...m,
              status: cancelled ? 'cancelled' : 'error',
              text: m.live || (cancelled ? useI18n.getState().t('msg.cancelled') : ''),
              error: cancelled ? undefined : String(err),
              activity: m.activity,
            }
          : m,
      );
    } finally {
      abort = null;
      set((s) => {
        const conversations = s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === messageId ? { ...m, activity: normalizeLoaded(m.activity) } : m,
                ),
              }
            : c,
        );
        persist(conversations);
        return { isRunning: false, conversations };
      });
    }
  },

  /* Switch between variants of a user or assistant message */
  switchVariant(messageId: string, targetIndex: number) {
    const convId = get().activeId;
    if (!convId) return;

    useSpeech.getState().stop();

    set((s) => {
      const conversations = s.conversations.map((c) => {
        if (c.id !== convId) return c;
        return {
          ...c,
          messages: c.messages.map((m) => {
            if (m.id !== messageId || !m.variants || targetIndex < 0 || targetIndex >= m.variants.length) {
              return m;
            }
            const targetVariant = m.variants[targetIndex];
            if (!targetVariant) return m;

            if (m.role === 'user') {
              return {
                ...m,
                text: targetVariant.text,
                variantIndex: targetIndex,
              };
            }

            // Assistant message
            return {
              ...m,
              text: targetVariant.text,
              activity: targetVariant.activity ? normalizeLoaded(targetVariant.activity) : [],
              meta: targetVariant.meta,
              error: targetVariant.error,
              variantIndex: targetIndex,
            };
          }),
        };
      });
      persist(conversations);
      return { conversations };
    });
  },

  /* Re-execute a failed terminal command — real retry through the shell. */
  async rerunCommand(conversationId: string, messageId: string, nodeId: string) {
    const conv = get().conversations.find((c) => c.id === conversationId);
    const msg = conv?.messages.find((m) => m.id === messageId);
    const node = msg ? findNode(msg.activity, nodeId) : undefined;
    const command = (node?.input as { command?: string } | undefined)?.command;
    if (!node || !command) return;
    const d = agentStrings(uiLocale());

    const rerunStarted: typeof node = {
      ...node,
      phase: 'started',
      status: 'running',
      description: d.command.retrying,
      startedAt: Date.now(),
      completedAt: undefined,
      durationMs: undefined,
    };
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === conversationId
          ? { ...c, messages: c.messages.map((m) => (m.id === messageId ? { ...m, activity: upsertNode(m.activity, rerunStarted) } : m)) }
          : c,
      ),
    }));

    await new Promise((r) => setTimeout(r, 520));
    const res = runShell(vfsContext.getTree(), command);
    const finished: typeof node = {
      ...rerunStarted,
      phase: res.ok ? 'completed' : 'failed',
      status: res.ok ? 'completed' : 'failed',
      completedAt: Date.now(),
      durationMs: Date.now() - rerunStarted.startedAt,
      description: res.ok ? d.command.retryOk : res.stderr?.split('\n')[0] ?? d.fix.buildExit(res.exitCode),
      output: { command, stdout: res.stdout, stderr: res.stderr, exitCode: res.exitCode },
    };
    set((s) => {
      const conversations = s.conversations.map((c) =>
        c.id === conversationId
          ? { ...c, messages: c.messages.map((m) => (m.id === messageId ? { ...m, activity: upsertNode(m.activity, finished) } : m)) }
          : c,
      );
      persist(conversations);
      return { conversations };
    });
  },
}));
