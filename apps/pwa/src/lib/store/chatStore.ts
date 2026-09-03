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
import { normaliserSources } from '../activity/sources';
import { estDebitDepasse, pousserEtTirer } from '../sync/conversations';
import { useCapacite } from '../capacites';
import { choisirTransport } from '../activity/transport';

/**
 * Rend l'erreur lisible par le proprietaire, pas par un developpeur.
 *
 * `BACKEND_OFFLINE` est le seul cas traduit : c'est celui qu'il rencontre
 * quand son serveur decroche. Avant, il ne le rencontrait pas du tout — une
 * demo du navigateur repondait a sa place en se faisant passer pour Usman
 * (mesure du 03/09/2026). Le reste garde sa forme brute : une erreur inconnue
 * qu'on habillerait en phrase rassurante serait le meme defaut, en plus petit.
 */
function messageErreur(err: unknown): string {
  if (err instanceof Error && err.message === 'BACKEND_OFFLINE') {
    return useI18n.getState().t('chat.offline');
  }
  return String(err);
}
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
  /** L'espace ou elle est nee — l'id d'une capacite, ou `null`/absent pour
   *  Usman general. Fixe a la creation : changer d'espace en cours de route
   *  deplacerait une conversation sans que rien ne l'ait demande. */
  espace?: string | null;
}

export interface LogEntry {
  ts: number;
  chunk: StreamChunk;
}

const CHAT_KEY = 'usman.chats.v1';

/* La conversation ouverte doit survivre a un F5 ou un changement d'appli —
   mais PAS a une fermeture complete de l'appli.

   `conversations` etait sauvegarde, `activeId` non : recharger la page pendant
   une conversation retombait toujours sur l'ecran vide (« Bonjour »), meme si
   la conversation existait encore dans la liste juste a cote. Mesure le
   30/08/2026, signale par le proprietaire.

   `sessionStorage`, pas `localStorage` : il survit a un F5 et a un aller-retour
   vers une autre appli (l'onglet reste ouvert), mais s'efface quand l'appli
   est vraiment fermee (l'onglet/le contexte de navigation est detruit) — la
   reouverture retombe alors sur l'ecran d'accueil et sa salutation, comme
   demande le 02/09/2026 : ouvrir une nouvelle conversation, pas reprendre
   l'ancienne. */
const ACTIVE_KEY = 'usman.chats.active.v1';

/** L'identifiant memorise, seulement s'il designe encore une conversation reelle.

    Une conversation supprimee entre-temps (par soi, ou par l'autre appareil via
    la synchronisation) ne doit pas rouvrir un ecran vide sur un fantome. */
function lireActiveId(conversations: Conversation[]): string | null {
  try {
    const id = sessionStorage.getItem(ACTIVE_KEY);
    return id && conversations.some((c) => c.id === id) ? id : null;
  } catch {
    return null;
  }
}

function ecrireActiveId(id: string | null) {
  try {
    if (id) sessionStorage.setItem(ACTIVE_KEY, id);
    else sessionStorage.removeItem(ACTIVE_KEY);
  } catch { /* stockage plein — ignore */ }
}

/* Les suppressions doivent voyager, elles aussi.

   Sans trace locale, l'appareil qui n'etait pas la au moment de la suppression
   renverrait la conversation au prochain envoi, et elle ressusciterait. On
   garde donc l'identifiant et la date, jusqu'a ce que le serveur les ait
   acceptes. */
const TOMBES_KEY = 'usman.chats.deleted.v1';

interface PierreTombale { id: string; supprimee: true; updatedAt: number }

function lireTombes(): PierreTombale[] {
  try {
    const brut = localStorage.getItem(TOMBES_KEY);
    return brut ? (JSON.parse(brut) as PierreTombale[]) : [];
  } catch {
    return [];
  }
}

function ecrireTombes(tombes: PierreTombale[]) {
  try {
    localStorage.setItem(TOMBES_KEY, JSON.stringify(tombes.slice(-200)));
  } catch { /* stockage plein — ignore */ }
}

function marquerSupprimee(ids: string[]) {
  if (!ids.length) return;
  const date = Date.now();
  const deja = new Set(lireTombes().map((t) => t.id));
  ecrireTombes([
    ...lireTombes(),
    ...ids.filter((id) => !deja.has(id)).map((id) => ({ id, supprimee: true as const, updatedAt: date })),
  ]);
}

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
              // Les reponses enregistrees avant le 30/08/2026 portent des
              // sources sans domaine — celles-la memes qui noircissaient
              // l'ecran. Elles sont reparees a la lecture, sinon elles
              // resteraient incompletes pour toujours.
              meta: m.meta?.sources
                ? { ...m.meta, sources: normaliserSources(m.meta.sources) }
                : m.meta,
              variants: m.variants
                ? m.variants.map((v) => ({
                    ...v,
                    activity: normalizeLoaded(v.activity ?? []),
                    meta: v.meta?.sources
                      ? { ...v.meta, sources: normaliserSources(v.meta.sources) }
                      : v.meta,
                  }))
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
  /** Vrai pendant que la reponse se revele encore a l'ecran (StreamingResponse),
   *  meme apres que le reseau a fini d'envoyer — un agent specialise renvoie
   *  tout son texte d'un coup, et la marche continue plusieurs secondes de
   *  plus. Sans cet etat, le bouton stop disparaissait avant que la reponse
   *  ait fini d'apparaitre : signale le 02/09/2026 ("je peux pas arreter la
   *  reponse"). */
  revealActif: boolean;
  commencerReveal(): void;
  terminerReveal(): void;
  /** Incremente a chaque demande de "sauter a la fin" — la marche en cours
   *  l'observe et affiche d'un coup ce qui est deja arrive. Il n'y a rien a
   *  annuler cote reseau dans ce cas : le texte est deja recu en entier. */
  revealSauterSignal: number;
  sauterReveal(): void;
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
  synchroniser(): Promise<void>;
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

export const useChat = create<ChatState>((set, get) => {
  const conversationsInitiales = loadConversations();
  const activeIdInitial = lireActiveId(conversationsInitiales);

  // La barre laterale filtre par espace : sans ceci, un F5 pendant une
  // conversation « Usman Coder » rouvrirait bien le bon message (grace a
  // `activeId`), mais dans une liste qui ne le montre plus, filtree sur
  // l'espace general par defaut. Les deux doivent se restaurer ensemble.
  const conversationActive = conversationsInitiales.find((c) => c.id === activeIdInitial);
  useCapacite.getState().choisir(conversationActive?.espace ?? null);

  return {
  conversations: conversationsInitiales,
  activeId: activeIdInitial,
  isRunning: false,
  revealActif: false,
  commencerReveal: () => set({ revealActif: true }),
  terminerReveal: () => set({ revealActif: false }),
  revealSauterSignal: 0,
  sauterReveal: () => set((s) => ({ revealSauterSignal: s.revealSauterSignal + 1 })),
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
    // N'ecrit rien dans `conversations` : une conversation n'existe, comme
    // partout ailleurs, qu'une fois un premier mot ecrit. `send()` la cree
    // reellement a ce moment-la. Ouvrir une capacite ou "+ Nouvelle
    // conversation" sans rien ecrire ne doit donc rien laisser dans
    // l'historique — juste changer l'id actif vers un ecran vide.
    const id = uid('conv');
    set({ activeId: id });
    return id;
  },

  selectConversation: (id) => {
    useSpeech.getState().stop();
    set({ activeId: id });
  },

  deleteConversation: (id) => {
    useSpeech.getState().stop();
    // La pierre tombale part AVANT la synchronisation : sans elle, l'autre
    // appareil renverrait la conversation et elle reviendrait.
    marquerSupprimee([id]);
    set((s) => {
      const conversations = s.conversations.filter((c) => c.id !== id);
      persist(conversations);
      return { conversations, activeId: s.activeId === id ? null : s.activeId };
    });
    void get().synchroniser();
  },

  renameConversation: (id, newTitle) => {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    set((s) => {
      // `updatedAt` doit bouger : l'arbitrage du serveur se fait sur cette
      // date, et un renommage non date perdrait contre la copie de l'autre
      // appareil.
      const conversations = s.conversations.map((c) => (c.id === id ? { ...c, title: trimmed, updatedAt: Date.now() } : c));
      persist(conversations);
      return { conversations };
    });
  },

  togglePinConversation: (id) => {
    set((s) => {
      const conversations = s.conversations.map((c) => (c.id === id ? { ...c, pinned: !c.pinned, updatedAt: Date.now() } : c));
      persist(conversations);
      return { conversations };
    });
  },

  clearAllConversations: () => {
    useSpeech.getState().stop();
    marquerSupprimee(get().conversations.map((c) => c.id));
    set({ conversations: [], activeId: null });
    persist([]);
    void get().synchroniser();
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

  /* Envoie les conversations locales au serveur et applique ce qu'il rend.

     Silencieuse par construction : si le serveur n'est pas configure, s'il ne
     repond pas, ou s'il ignore la route, rien ne change et rien n'est dit. Une
     synchronisation ratee est un non-evenement — ce qui serait grave, c'est
     qu'elle fasse disparaitre une conversation. */
  synchroniser: async () => {
    const cfg = activeRemoteCfg();
    if (!cfg) return;

    const tombes = lireTombes();
    const resultat = await pousserEtTirer(get().conversations, tombes, cfg);
    if (!resultat) return;
    if (estDebitDepasse(resultat)) {
      set({ attachmentError: useI18n.getState().t('sync.rateLimited') });
      return;
    }

    // Les pierres tombales que le serveur a prises en compte ont fini leur
    // travail : les garder ferait grossir le stockage sans rien protéger.
    const acceptees = new Set(resultat.supprimees);
    ecrireTombes(tombes.filter((tombe) => !acceptees.has(tombe.id)));

    persist(resultat.conversations);
    set((s) => ({
      conversations: resultat.conversations,
      // Le serveur nomme ce qu'il a refuse ; jusqu'ici la reponse etait jetee
      // ici meme. Une conversation trop grosse restait sur l'appareil sans que
      // personne ne sache qu'elle n'etait PAS sauvegardee — et le commentaire
      // du serveur disait deja que l'appareil doit le dire a son proprietaire
      // « plutot que de croire qu'elle est en surete ».
      attachmentError: resultat.refusees.length
        ? useI18n.getState().t('sync.refused', { n: resultat.refusees.length })
        : s.attachmentError,
      // Ne jamais fermer sous ses yeux la conversation ouverte : si le serveur
      // ne la connait pas encore, elle reste affichee.
      activeId: resultat.conversations.some((c) => c.id === s.activeId) ? s.activeId : null,
    }));
  },

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

    set((s) => {
      // `newChat()` ne cree plus l'entree : premier message ici, elle
      // n'existe encore nulle part dans `conversations` — il faut l'inserer,
      // pas seulement la mettre a jour.
      const existante = s.conversations.find((c) => c.id === convId);
      const base: Conversation = existante ?? {
        id: convId,
        title: 'New conversation',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
        // L'espace ouvert au moment ou le PREMIER mot est ecrit — jamais
        // celui d'un clic ulterieur, qui ne fait que consulter l'historique.
        espace: useCapacite.getState().active,
      };
      const misAJour: Conversation = {
        ...base,
        title: base.messages.length === 0 ? title.slice(0, 52) : base.title,
        updatedAt: Date.now(),
        messages: [...base.messages, userMsg, assistantMsg],
      };
      const conversations = existante
        ? s.conversations.map((c) => (c.id === convId ? misAJour : c))
        : [misAJour, ...s.conversations];
      return { isRunning: true, conversations };
    });

    abort = new AbortController();
    const log = (chunk: StreamChunk) =>
      set((s) => ({ eventLog: [...s.eventLog.slice(-399), { ts: Date.now(), chunk }] }));

    const startedAt = Date.now();
    try {
      /* Video editing stays on-device; other attachments use the secure remote upload. */
      const surAppareil = attachments.some((value) => value.kind === 'video');
      const remote = surAppareil ? null : activeRemoteCfg();
      const conv = get().conversations.find((c) => c.id === convId);
      const history = (conv?.messages ?? [])
        .filter((m) => m.text && m.id !== assistantMsg.id)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.text }));
      const transport = choisirTransport(remote, surAppareil);
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
              error: cancelled ? undefined : messageErreur(err),
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
      // Le tour est fini et enregistre : l'autre appareil peut le recevoir.
      // Volontairement non attendu — une synchronisation lente ne doit pas
      // retarder l'affichage de la reponse.
      void get().synchroniser();
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

      const transport = choisirTransport(remote);
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
              error: cancelled ? undefined : messageErreur(err),
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
      // Le tour est fini et enregistre : l'autre appareil peut le recevoir.
      // Volontairement non attendu — une synchronisation lente ne doit pas
      // retarder l'affichage de la reponse.
      void get().synchroniser();
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

      const transport = choisirTransport(remote);
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
              error: cancelled ? undefined : messageErreur(err),
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
      // Le tour est fini et enregistre : l'autre appareil peut le recevoir.
      // Volontairement non attendu — une synchronisation lente ne doit pas
      // retarder l'affichage de la reponse.
      void get().synchroniser();
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
};
});

/* Sauvegarde `activeId` des qu'il change, quelle qu'en soit la cause —
   selection manuelle, nouvelle conversation, suppression, ou synchronisation
   avec l'autre appareil. Un seul point d'ecriture plutot qu'un `ecrireActiveId`
   glisse dans chacune des actions ci-dessus, qui finirait par en oublier une. */
useChat.subscribe((etat, precedent) => {
  if (etat.activeId !== precedent.activeId) ecrireActiveId(etat.activeId);
});

