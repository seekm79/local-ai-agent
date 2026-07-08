import { create } from "zustand";
import * as api from "../api/client";

let ws: WebSocket | null = null;

interface ComfyState {
  status: api.ComfyStatus | null;
  workflows: api.Workflow[];
  generating: boolean;
  progress: { value: number; max: number } | null;
  lastError: string | null;
  savedPaths: string[]; // relative paths saved this session

  connect: () => void;
  loadStatus: () => Promise<void>;
  loadWorkflows: () => Promise<void>;
  generate: (
    projectId: number,
    workflow: string,
    params: Record<string, unknown>,
  ) => Promise<void>;
  onDone?: () => void;
  setOnDone: (fn: () => void) => void;
}

export const useComfy = create<ComfyState>((set, get) => {
  function handle(msg: { type: string; payload: any }) {
    const p = msg.payload ?? {};
    switch (msg.type) {
      case "started":
        set({ generating: true, progress: null, lastError: null, savedPaths: [] });
        break;
      case "progress":
        set({ progress: { value: p.value ?? 0, max: p.max ?? 1 } });
        break;
      case "saved":
        set((s) => ({ savedPaths: [...s.savedPaths, p.path] }));
        break;
      case "done":
        set({ generating: false, progress: null });
        get().onDone?.();
        break;
      case "error":
        set({ generating: false, progress: null, lastError: p.message });
        break;
    }
  }

  return {
    status: null,
    workflows: [],
    generating: false,
    progress: null,
    lastError: null,
    savedPaths: [],

    setOnDone: (fn) => set({ onDone: fn }),

    connect() {
      if (
        ws &&
        (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)
      )
        return;
      ws = new WebSocket(`ws://${location.host}/ws/comfy`);
      ws.onmessage = (e) => handle(JSON.parse(e.data));
      ws.onclose = () => {
        ws = null;
      };
    },

    async loadStatus() {
      try {
        set({ status: await api.getComfyStatus() });
      } catch (e) {
        set({ status: { online: false, error: String((e as Error).message), url: "" } });
      }
    },

    async loadWorkflows() {
      try {
        set({ workflows: await api.getWorkflows() });
      } catch {
        set({ workflows: [] });
      }
    },

    async generate(projectId, workflow, params) {
      get().connect();
      set({ generating: true, lastError: null, savedPaths: [], progress: null });
      try {
        await api.startGenerate(projectId, workflow, params);
      } catch (e) {
        set({ generating: false, lastError: String((e as Error).message) });
      }
    },
  };
});
