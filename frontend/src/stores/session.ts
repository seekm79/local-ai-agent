import { create } from "zustand";
import * as api from "../api/client";

type Msg = api.Message;
type Chat = api.Chat;

// The one WS connection to /ws/chat. Kept out of React state on purpose.
let ws: WebSocket | null = null;

// Persist the open chat id so a page refresh restores the conversation.
const LAST_CHAT_KEY = "wb:lastChatId";
const rememberChat = (id: number | null) => {
  try {
    if (id == null) localStorage.removeItem(LAST_CHAT_KEY);
    else localStorage.setItem(LAST_CHAT_KEY, String(id));
  } catch {
    /* storage unavailable — non-fatal */
  }
};

function waitOpen(sock: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    if (sock.readyState === WebSocket.OPEN) return resolve();
    sock.addEventListener("open", () => resolve(), { once: true });
    sock.addEventListener("error", () => reject(new Error("WS error")), {
      once: true,
    });
  });
}

interface SessionState {
  models: string[];
  model: string | null; // only ever an installed model
  think: boolean;

  chats: Chat[];
  currentChatId: number | null;
  messages: Msg[];

  streaming: boolean;
  streamingId: number | null;
  error: string | null;
  condensed: { summary: string } | null; // 8.6 context-condensed marker

  // When set (coding mode), generations include this file as system context.
  codingContext: { projectId: number; filePath: string } | null;
  setCodingContext: (ctx: { projectId: number; filePath: string } | null) => void;

  setModels: (models: string[], preferred?: string) => void;
  setModel: (m: string) => void;
  toggleThink: () => void;
  clearError: () => void;

  loadChats: () => Promise<void>;
  newChat: () => Promise<void>;
  selectChat: (id: number) => Promise<void>;
  renameChat: (id: number, title: string) => Promise<void>;
  deleteChat: (id: number) => Promise<void>;

  send: (content: string) => Promise<void>;
  regenerate: () => Promise<void>;
  editResend: (messageId: number, content: string) => Promise<void>;
  stop: () => void;
}

export const useSession = create<SessionState>((set, get) => {
  // Update a message in place by id.
  const patchMsg = (id: number, fn: (m: Msg) => Msg) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? fn(m) : m)),
    }));

  function handle(msg: { type: string; payload: any }) {
    const p = msg.payload ?? {};
    switch (msg.type) {
      case "start":
        set((s) => ({
          streaming: true,
          streamingId: p.message_id,
          messages: [
            ...s.messages,
            {
              id: p.message_id,
              chat_id: get().currentChatId ?? 0,
              role: "assistant",
              content: "",
              reasoning: null,
              model: get().model,
              tokens: null,
            },
          ],
        }));
        break;
      case "delta":
        patchMsg(get().streamingId!, (m) => ({
          ...m,
          content: m.content + p.content,
        }));
        break;
      case "reasoning_delta":
        patchMsg(get().streamingId!, (m) => ({
          ...m,
          reasoning: (m.reasoning ?? "") + p.content,
        }));
        break;
      case "chat_titled":
        set((s) => ({
          chats: s.chats.map((c) =>
            c.id === p.chat_id ? { ...c, title: p.title } : c,
          ),
        }));
        break;
      case "condensed":
        set({ condensed: { summary: p.summary } });
        break;
      case "done":
      case "stopped":
        set({ streaming: false, streamingId: null });
        // Reconcile with canonical server state (real ids for edit/regen).
        void reconcile();
        break;
      case "error":
        set({ streaming: false, streamingId: null, error: p.message });
        break;
    }
  }

  async function reconcile() {
    const id = get().currentChatId;
    if (id == null) return;
    try {
      const messages = await api.getMessages(id);
      set({ messages });
    } catch {
      /* keep optimistic state on failure */
    }
  }

  async function ensureSocket(): Promise<WebSocket> {
    if (ws && ws.readyState === WebSocket.OPEN) return ws;
    if (!ws || ws.readyState === WebSocket.CLOSED) {
      ws = new WebSocket(`ws://${location.host}/ws/chat`);
      ws.onmessage = (e) => handle(JSON.parse(e.data));
      ws.onclose = () => {
        ws = null;
        if (get().streaming) set({ streaming: false, streamingId: null });
      };
      ws.onerror = () => set({ error: "Chat connection error" });
    }
    await waitOpen(ws);
    return ws;
  }

  async function ensureChat(): Promise<number> {
    let id = get().currentChatId;
    if (id == null) {
      const chat = await api.createChat();
      rememberChat(chat.id);
      set((s) => ({ chats: [chat, ...s.chats], currentChatId: chat.id }));
      id = chat.id;
    }
    return id;
  }

  return {
    models: [],
    model: null,
    think: false,
    chats: [],
    currentChatId: null,
    messages: [],
    streaming: false,
    streamingId: null,
    error: null,
    condensed: null,
    codingContext: null,

    setCodingContext: (ctx) => set({ codingContext: ctx }),

    setModels(allModels, preferred) {
      // Embedding models (e.g. nomic-embed-text) can't do chat — keep them out
      // of the picker so they're never selected for chat/agents/build.
      const models = allModels.filter((m) => !/embed/i.test(m));
      set((s) => {
        let model = s.model;
        if (!model || !models.includes(model)) {
          model =
            preferred && models.includes(preferred)
              ? preferred
              : (models[0] ?? null);
        }
        return { models, model };
      });
    },
    setModel: (m) => set({ model: m }),
    toggleThink: () => set((s) => ({ think: !s.think })),
    clearError: () => set({ error: null }),

    async loadChats() {
      const chats = await api.getChats();
      set({ chats });
      // Restore the previously open chat after a refresh.
      if (get().currentChatId == null) {
        let saved: number | null = null;
        try {
          saved = Number(localStorage.getItem(LAST_CHAT_KEY)) || null;
        } catch {
          /* ignore */
        }
        if (saved && chats.some((c) => c.id === saved)) {
          await get().selectChat(saved);
        }
      }
    },

    async newChat() {
      const chat = await api.createChat();
      rememberChat(chat.id);
      set((s) => ({
        chats: [chat, ...s.chats],
        currentChatId: chat.id,
        messages: [],
      }));
    },

    async selectChat(id) {
      rememberChat(id);
      set({ currentChatId: id, messages: [] });
      const messages = await api.getMessages(id);
      set({ messages });
    },

    async renameChat(id, title) {
      await api.renameChat(id, title);
      set((s) => ({
        chats: s.chats.map((c) => (c.id === id ? { ...c, title } : c)),
      }));
    },

    async deleteChat(id) {
      await api.deleteChat(id);
      if (get().currentChatId === id) rememberChat(null);
      set((s) => {
        const chats = s.chats.filter((c) => c.id !== id);
        const wasCurrent = s.currentChatId === id;
        return {
          chats,
          currentChatId: wasCurrent ? null : s.currentChatId,
          messages: wasCurrent ? [] : s.messages,
        };
      });
    },

    async send(content) {
      const { model } = get();
      if (!model) {
        set({ error: "No model selected — is Ollama running?" });
        return;
      }
      const chatId = await ensureChat();
      // Optimistic user bubble (reconciled to real id on done).
      set((s) => ({
        messages: [
          ...s.messages,
          {
            id: -Date.now(),
            chat_id: chatId,
            role: "user",
            content,
            reasoning: null,
            model: null,
            tokens: null,
          },
        ],
      }));
      const sock = await ensureSocket();
      const ctx = get().codingContext;
      sock.send(
        JSON.stringify({
          type: "user_message",
          chat_id: chatId,
          content,
          model,
          think: get().think,
          project_id: ctx?.projectId,
          file_path: ctx?.filePath,
        }),
      );
    },

    async regenerate() {
      const { model, currentChatId, messages } = get();
      if (!model || currentChatId == null) return;
      // Drop the last assistant bubble optimistically.
      const lastAssistant = [...messages]
        .reverse()
        .find((m) => m.role === "assistant");
      if (lastAssistant)
        set({ messages: messages.filter((m) => m.id !== lastAssistant.id) });
      const sock = await ensureSocket();
      const ctx = get().codingContext;
      sock.send(
        JSON.stringify({
          type: "regenerate",
          chat_id: currentChatId,
          model,
          think: get().think,
          project_id: ctx?.projectId,
          file_path: ctx?.filePath,
        }),
      );
    },

    async editResend(messageId, content) {
      const { model, currentChatId, messages } = get();
      if (!model || currentChatId == null) return;
      // Truncate at the edited message and update its text optimistically.
      const idx = messages.findIndex((m) => m.id === messageId);
      const kept = idx >= 0 ? messages.slice(0, idx) : messages;
      set({
        messages: [
          ...kept,
          {
            id: messageId,
            chat_id: currentChatId,
            role: "user",
            content,
            reasoning: null,
            model: null,
            tokens: null,
          },
        ],
      });
      const sock = await ensureSocket();
      const ctx = get().codingContext;
      sock.send(
        JSON.stringify({
          type: "edit_resend",
          chat_id: currentChatId,
          message_id: messageId,
          content,
          model,
          think: get().think,
          project_id: ctx?.projectId,
          file_path: ctx?.filePath,
        }),
      );
    },

    stop() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "stop" }));
      }
    },
  };
});
