import { create } from "zustand";
import * as api from "../api/client";

type ProcInfo = api.ProcInfo;
type RunnerDef = api.RunnerDef;

// One connection to /ws/run for process lifecycle + output events.
let ws: WebSocket | null = null;

// Output listeners (the run-output log subscribes). Kept out of React state.
const outputListeners = new Set<(procId: number, data: string) => void>();

interface RunState {
  runners: RunnerDef[];
  processes: ProcInfo[];
  confirm: { command: string; token: string } | null;
  error: string | null;

  connect: () => void;
  detect: (projectId: number) => Promise<void>;
  runProject: (projectId: number, kind: string) => Promise<void>;
  runCommand: (projectId: number, argv: string[]) => Promise<void>;
  confirmRun: () => Promise<void>;
  cancelConfirm: () => void;
  stop: (procId: number) => Promise<void>;
  refreshProcesses: (projectId: number) => Promise<void>;
  clearError: () => void;

  onOutput: (fn: (procId: number, data: string) => void) => () => void;
}

export const useRun = create<RunState>((set, get) => {
  const upsert = (proc: ProcInfo) =>
    set((s) => {
      const rest = s.processes.filter((p) => p.id !== proc.id);
      return { processes: [...rest, proc] };
    });

  function handle(msg: { type: string; payload: any }) {
    const p = msg.payload ?? {};
    switch (msg.type) {
      case "run_started":
        upsert(p as ProcInfo);
        break;
      case "run_output":
        for (const fn of outputListeners) fn(p.proc_id, p.data);
        break;
      case "run_url":
        set((s) => ({
          processes: s.processes.map((x) =>
            x.id === p.proc_id ? { ...x, dev_url: p.url } : x,
          ),
        }));
        break;
      case "run_exited":
        set((s) => ({
          processes: s.processes.map((x) =>
            x.id === p.proc_id
              ? {
                  ...x,
                  status:
                    p.status ?? (x.status === "killed" ? "killed" : "exited"),
                  exit_code: p.exit_code,
                }
              : x,
          ),
        }));
        break;
    }
  }

  return {
    runners: [],
    processes: [],
    confirm: null,
    error: null,

    clearError: () => set({ error: null }),

    connect() {
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING))
        return;
      ws = new WebSocket(`ws://${location.host}/ws/run`);
      ws.onmessage = (e) => handle(JSON.parse(e.data));
      ws.onclose = () => {
        ws = null;
      };
    },

    async detect(projectId) {
      try {
        const runners = await api.detectRunners(projectId);
        set({ runners });
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    },

    async refreshProcesses(projectId) {
      try {
        const processes = await api.listProcesses(projectId);
        set({ processes });
      } catch {
        /* ignore */
      }
    },

    async runProject(projectId, kind) {
      get().connect();
      try {
        const r = await api.runProject(projectId, kind);
        upsert(r.proc);
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    },

    async runCommand(projectId, argv) {
      get().connect();
      try {
        const r = await api.runCommand(projectId, argv);
        if (r.status === "needs_confirmation") {
          set({ confirm: { command: r.command, token: r.token } });
        } else {
          upsert(r.proc);
        }
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    },

    async confirmRun() {
      const c = get().confirm;
      if (!c) return;
      set({ confirm: null });
      try {
        const r = await api.confirmRun(c.token);
        upsert(r.proc);
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    },

    cancelConfirm: () => set({ confirm: null }),

    async stop(procId) {
      try {
        await api.stopProcess(procId);
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    },

    onOutput(fn) {
      outputListeners.add(fn);
      return () => outputListeners.delete(fn);
    },
  };
});
