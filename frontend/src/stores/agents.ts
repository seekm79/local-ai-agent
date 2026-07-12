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
  runProjectId: number | null; // project the displayed run belongs to
  pinnedProjectId: number | null; // when set, ignore run_started from other projects
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
  pinProject: (projectId: number | null) => void;
  hydrateRun: (runId: number) => Promise<void>;
  showIdle: () => void;
  setGoal: (g: string) => void;
  clearError: () => void;
}

// DB run status → store status (pending is "running" from the UI's viewpoint;
// interrupted reads as failed).
const RUN_STATUS: Record<string, AgentsState["status"]> = {
  pending: "running",
  running: "running",
  done: "done",
  cancelled: "cancelled",
  failed: "failed",
  interrupted: "failed",
};

export const useAgents = create<AgentsState>((set, get) => {
  const patchStep = (stepId: number, fn: (s: StepView) => StepView) =>
    set((st) => ({
      steps: st.steps.map((s) => (s.id === stepId ? fn(s) : s)),
    }));

  function handle(msg: { type: string; payload: any }) {
    const p = msg.payload ?? {};
    // Events for a run other than the one on screen must not clobber the view —
    // a background build keeps streaming while the user looks at another project.
    const foreign = p.run_id != null && p.run_id !== get().activeRunId;
    switch (msg.type) {
      case "run_started": {
        const pinned = get().pinnedProjectId;
        if (pinned != null && p.project_id != null && p.project_id !== pinned) {
          void get().loadRuns(); // keep badges fresh, but don't switch views
          break;
        }
        set({
          activeRunId: p.run_id,
          runProjectId: p.project_id ?? null,
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
      }
      case "step_started":
        if (foreign) break;
        patchStep(p.step_id, (s) => ({ ...s, status: "running" }));
        break;
      case "model_message":
        if (foreign) break;
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
        if (foreign) break;
        patchStep(p.step_id, (s) => ({
          ...s,
          tools: [...s.tools, { tool: p.tool, args: p.args }],
        }));
        break;
      case "tool_result":
        if (foreign) break;
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
        if (foreign) break;
        set((st) => ({
          checkpoints: [
            { sha: p.sha, label: p.label, step_id: p.step_id },
            ...st.checkpoints,
          ],
        }));
        break;
      case "step_update":
        if (foreign) break;
        patchStep(p.step_id, (s) => ({ ...s, status: p.status }));
        break;
      case "run_done":
        if (!foreign) {
          set({
            status: p.status,
            summary: p.summary,
          });
        }
        void get().loadRuns(); // background runs finishing still refresh badges
        break;
      case "error":
        if (foreign) break;
        set({ error: p.message });
        break;
    }
  }

  return {
    runs: [],
    activeRunId: null,
    runProjectId: null,
    pinnedProjectId: null,
    goal: "",
    steps: [],
    checkpoints: [],
    planner: "",
    status: "idle",
    summary: "",
    error: null,

    clearError: () => set({ error: null }),
    setGoal: (g) => set({ goal: g }),

    pinProject: (projectId) => set({ pinnedProjectId: projectId }),

    // Reset the view to a blank slate (e.g. opening a project with no runs yet)
    // without touching any run that is still executing in the background.
    showIdle: () =>
      set({
        activeRunId: null,
        runProjectId: null,
        goal: "",
        steps: [],
        checkpoints: [],
        planner: "",
        status: "idle",
        summary: "",
      }),

    // Restore a run from the DB — used when switching back to a project whose
    // build ran (or is still running) while another project was on screen. Live
    // WS events keep patching afterwards because the step ids match.
    async hydrateRun(runId) {
      get().connect();
      try {
        const { run, steps } = await api.getAgentRun(runId);
        set({
          activeRunId: run.id,
          runProjectId: run.project_id,
          goal: run.goal,
          status: RUN_STATUS[run.status] ?? "idle",
          summary: run.summary ?? "",
          planner: "",
          checkpoints: [],
          steps: steps.map((s) => {
            let messages: StepView["messages"] = [];
            let tools: StepView["tools"] = [];
            try {
              const log = JSON.parse(s.output ?? "{}");
              messages = log.messages ?? [];
              tools = log.tools ?? [];
            } catch {
              /* incomplete step output — show it bare */
            }
            return {
              id: s.id,
              idx: s.idx,
              kind: s.kind,
              title: s.title,
              detail: s.detail ?? "",
              status: s.status,
              targetFiles: [],
              messages,
              tools,
            };
          }),
        });
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    },

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
