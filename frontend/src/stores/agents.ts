import { create } from "zustand";
import * as api from "../api/client";

let ws: WebSocket | null = null;

export interface StepView {
  id: number;
  idx: number;
  kind: string;
  title: string;
  detail: string;
  status: string;
  targetFiles: string[];
  messages: { role: string; content: string }[];
  tools: {
    tool: string;
    args?: any;
    ok?: boolean;
    output?: string;
    before?: string;
    after?: string;
    path?: string;
    screenshots?: string[];
  }[];
}

export interface Checkpoint {
  sha: string;
  label: string;
  step_id?: number;
}

interface AgentsState {
  runs: api.AgentRun[];
  activeRunId: number | null;
  goal: string;
  steps: StepView[];
  checkpoints: Checkpoint[];
  planner: string; // planner/helper messages not tied to a step
  status: "idle" | "running" | "done" | "failed" | "cancelled";
  summary: string;
  error: string | null;

  connect: () => void;
  loadRuns: () => Promise<void>;
  start: (body: api.StartRunBody) => Promise<void>;
  cancel: () => Promise<void>;
  setGoal: (g: string) => void;
  clearError: () => void;
}

export const useAgents = create<AgentsState>((set, get) => {
  const patchStep = (stepId: number, fn: (s: StepView) => StepView) =>
    set((st) => ({
      steps: st.steps.map((s) => (s.id === stepId ? fn(s) : s)),
    }));

  function handle(msg: { type: string; payload: any }) {
    const p = msg.payload ?? {};
    switch (msg.type) {
      case "run_started":
        set({
          activeRunId: p.run_id,
          goal: p.goal,
          status: "running",
          summary: "",
          planner: "",
          checkpoints: [],
          steps: (p.steps as any[]).map((s) => ({
            id: s.id,
            idx: s.idx,
            kind: s.kind,
            title: s.title,
            detail: s.detail,
            status: s.status,
            targetFiles: s.target_files ?? [],
            messages: [],
            tools: [],
          })),
        });
        break;
      case "step_started":
        patchStep(p.step_id, (s) => ({ ...s, status: "running" }));
        break;
      case "model_message":
        if (p.step_id == null) {
          // planner/helper message
          set((st) => ({
            planner:
              st.planner + `\n[${p.role}] ${p.content}`.slice(0, 100000),
          }));
        } else {
          patchStep(p.step_id, (s) => ({
            ...s,
            messages: [...s.messages, { role: p.role, content: p.content }],
          }));
        }
        break;
      case "tool_call":
        patchStep(p.step_id, (s) => ({
          ...s,
          tools: [...s.tools, { tool: p.tool, args: p.args }],
        }));
        break;
      case "tool_result":
        patchStep(p.step_id, (s) => ({
          ...s,
          tools: [
            ...s.tools,
            {
              tool: p.tool,
              ok: p.ok,
              output: p.output,
              before: p.before,
              after: p.after,
              path: p.path,
              screenshots: p.screenshots,
            },
          ],
        }));
        break;
      case "checkpoint":
        set((st) => ({
          checkpoints: [
            { sha: p.sha, label: p.label, step_id: p.step_id },
            ...st.checkpoints,
          ],
        }));
        break;
      case "step_update":
        patchStep(p.step_id, (s) => ({ ...s, status: p.status }));
        break;
      case "run_done":
        set({
          status: p.status,
          summary: p.summary,
        });
        void get().loadRuns();
        break;
      case "error":
        set({ error: p.message });
        break;
    }
  }

  return {
    runs: [],
    activeRunId: null,
    goal: "",
    steps: [],
    checkpoints: [],
    planner: "",
    status: "idle",
    summary: "",
    error: null,

    clearError: () => set({ error: null }),
    setGoal: (g) => set({ goal: g }),

    connect() {
      if (
        ws &&
        (ws.readyState === WebSocket.OPEN ||
          ws.readyState === WebSocket.CONNECTING)
      )
        return;
      ws = new WebSocket(`ws://${location.host}/ws/agents`);
      ws.onmessage = (e) => handle(JSON.parse(e.data));
      ws.onclose = () => {
        ws = null;
      };
    },

    async loadRuns() {
      try {
        set({ runs: await api.listAgentRuns() });
      } catch {
        /* ignore */
      }
    },

    async start(body) {
      get().connect();
      set({
        steps: [],
        checkpoints: [],
        summary: "",
        planner: "",
        status: "running",
        error: null,
      });
      try {
        await api.startAgentRun(body);
      } catch (e) {
        set({ status: "failed", error: String((e as Error).message) });
      }
    },

    async cancel() {
      const id = get().activeRunId;
      if (id == null) return;
      try {
        await api.cancelAgentRun(id);
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    },
  };
});
