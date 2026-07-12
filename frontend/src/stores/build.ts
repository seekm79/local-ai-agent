import { create } from "zustand";
import * as api from "../api/client";
import { useRun } from "./run";
import { useAgents } from "./agents";
import { useProject } from "./project";

interface BuildState {
  projectId: number | null;
  projectName: string;
  phase: "entry" | "work";
  runId: number | null; // the in-flight design/build run, tracked from buildStart
  installProcId: number | null;
  devProcId: number | null;
  devUrl: string | null;
  installing: boolean;
  error: string | null;
  projects: api.BuildProjectInfo[]; // recent builds shown on the entry screen

  loadBuildProjects: () => Promise<void>;
  openProject: (p: api.BuildProjectInfo) => Promise<void>;
  goHome: () => void; // back to entry WITHOUT cancelling anything in flight
  restore: () => Promise<void>; // reopen the last project after a page reload
  scaffold: (
    name: string,
    prompt: string,
    opts: { model?: string; attachments?: { file: File; role: api.AttachRole }[]; generateImages?: boolean },
  ) => Promise<void>;
  followUp: (prompt: string, opts?: { model?: string; generateImages?: boolean }) => Promise<void>;
  regenerateDesign: (model?: string) => Promise<void>;
  attachToProject: (file: File, role: api.AttachRole) => Promise<void>;
  onProcesses: () => void; // called when the run store updates
  stop: () => Promise<void>; // stop all in-flight progress (AI run + install)
  reset: () => Promise<void>;
}

const ENTRY_STATE = {
  projectId: null,
  projectName: "",
  phase: "entry" as const,
  runId: null,
  installProcId: null,
  devProcId: null,
  devUrl: null,
  installing: false,
  error: null,
};

export const useBuild = create<BuildState>((set, get) => ({
  projectId: null,
  projectName: "",
  phase: "entry",
  runId: null,
  installProcId: null,
  devProcId: null,
  devUrl: null,
  installing: false,
  error: null,
  projects: [],

  async loadBuildProjects() {
    try {
      set({ projects: await api.listBuildProjects() });
    } catch {
      /* entry list is best-effort */
    }
  },

  // Re-open an existing build project — the Claude-conversations model: a run
  // still executing keeps streaming (we re-attach to it), a finished one shows
  // its steps + summary, and the dev preview comes back up.
  async openProject(p) {
    set({
      ...ENTRY_STATE,
      projectId: p.id,
      projectName: p.name,
      phase: "work",
      runId: p.latest_run?.id ?? null,
    });
    localStorage.setItem("wb.build.projectId", String(p.id));
    // The Code tab reads the project store's selection — keep it in sync.
    await useProject.getState().loadProjects();
    await useProject.getState().selectProject(p.id);
    const agents = useAgents.getState();
    agents.pinProject(p.id);
    useRun.getState().connect();
    agents.connect();
    if (p.latest_run) {
      await agents.hydrateRun(p.latest_run.id);
    } else {
      agents.showIdle();
    }
    // Re-attach to whatever processes this project already has (install/dev);
    // onProcesses() adopts them from the refreshed list. If no dev server is
    // running and deps are in, start one so the preview works.
    try {
      await useRun.getState().refreshProcesses(p.id);
    } catch {
      /* ignore */
    }
    get().onProcesses();
    const procs = useRun.getState().processes.filter((x) => x.project_id === p.id);
    const devRunning = procs.some(
      (x) => x.name === "dev server" && x.status === "running",
    );
    const installRunning = procs.some(
      (x) => x.name === "install deps" && x.status === "running",
    );
    if (!devRunning && !installRunning && p.deps_installed) {
      try {
        const r = await api.startDev(p.id);
        set({ devProcId: r.proc.id });
      } catch (e) {
        set({ error: String((e as Error).message) });
      }
    }
  },

  goHome() {
    useAgents.getState().pinProject(null);
    localStorage.removeItem("wb.build.projectId");
    set({ phase: "entry" });
    void get().loadBuildProjects();
  },

  // After a browser reload the store starts empty — reopen the project that was
  // on screen (steps, code tab, and live preview all come back via openProject).
  async restore() {
    if (get().phase !== "entry" || get().projectId != null) return;
    const saved = Number(localStorage.getItem("wb.build.projectId"));
    if (!saved) return;
    try {
      const projects = await api.listBuildProjects();
      set({ projects });
      const p = projects.find((x) => x.id === saved);
      if (p) await get().openProject(p);
    } catch {
      /* fall back to the entry screen */
    }
  },

  // Stop everything in flight without leaving the project: cancel the AI
  // design/build run so it stops consuming the model, and stop the dependency
  // install if it's still going. The dev server (live preview) is left running.
  async stop() {
    const runId = get().runId ?? useAgents.getState().activeRunId;
    if (runId != null) {
      try {
        await api.cancelAgentRun(runId);
      } catch {
        /* ignore */
      }
    }
    const { installProcId } = get();
    if (installProcId != null) {
      try {
        await api.stopProcess(installProcId);
      } catch {
        /* ignore */
      }
    }
    set({ installing: false, runId: null });
  },

  async reset() {
    const { devProcId, installProcId } = get();
    // Cancel the in-flight design/build run so it stops consuming the model.
    const runId = useAgents.getState().activeRunId;
    if (runId != null) {
      try {
        await api.cancelAgentRun(runId);
      } catch {
        /* ignore */
      }
    }
    // Stop the dev server + install process so the port frees up and nothing
    // is left running in the background. Files on disk are kept.
    for (const pid of [devProcId, installProcId]) {
      if (pid != null) {
        try {
          await api.stopProcess(pid);
        } catch {
          /* ignore */
        }
      }
    }
    localStorage.removeItem("wb.build.projectId");
    set({ ...ENTRY_STATE });
  },

  async scaffold(name, prompt, opts) {
    set({ error: null, installing: true });
    try {
      useRun.getState().connect();
      useAgents.getState().connect();
      const { project, install_proc } = await api.scaffoldBuild(name, prompt);
      await useProject.getState().loadProjects();
      await useProject.getState().selectProject(project.id);
      // Pin the agents stream to the new project (and drop any previous
      // project's steps from view) before its run starts emitting.
      useAgents.getState().pinProject(project.id);
      useAgents.getState().showIdle();
      set({
        projectId: project.id,
        projectName: project.name,
        phase: "work",
        installProcId: install_proc.id,
        devProcId: null,
        devUrl: null,
        runId: null,
      });
      localStorage.setItem("wb.build.projectId", String(project.id));
      // Upload any attachments so the Designer/Builder can use them.
      for (const a of opts.attachments ?? []) {
        try {
          await api.attachBuild(project.id, a.file, a.role);
        } catch {
          /* skip a failed attachment */
        }
      }
      const { run_id } = await api.buildStart({
        project_id: project.id,
        prompt,
        model: opts.model,
        generate_images: opts.generateImages,
      });
      set({ runId: run_id });
    } catch (e) {
      set({ error: String((e as Error).message), installing: false });
    }
  },

  async attachToProject(file, role) {
    const { projectId } = get();
    if (projectId == null) return;
    try {
      await api.attachBuild(projectId, file, role);
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  // Called by BuildView whenever the run store's processes change: start the dev
  // server once install has exited, and capture the dev URL. Also adopts
  // processes this store didn't start itself — a reopened project's install or
  // dev server is picked up here so the UI reflects it.
  onProcesses() {
    const { projectId, installProcId, devProcId } = get();
    if (projectId == null) return;
    const procs = useRun.getState().processes.filter((p) => p.project_id === projectId);

    if (installProcId == null) {
      const runningInstall = procs.find(
        (p) => p.name === "install deps" && p.status === "running",
      );
      if (runningInstall)
        set({ installProcId: runningInstall.id, installing: true });
    }
    if (devProcId == null) {
      const runningDev = procs.find(
        (p) => p.name === "dev server" && p.status === "running",
      );
      if (runningDev)
        set({ devProcId: runningDev.id, devUrl: runningDev.dev_url ?? get().devUrl });
    }

    const install = procs.find((p) => p.id === get().installProcId);
    if (install && install.status !== "running" && get().installing && get().devProcId == null) {
      set({ installing: false });
      void api
        .startDev(projectId)
        .then((r) => set({ devProcId: r.proc.id }))
        .catch((e) => set({ error: String((e as Error).message) }));
    }

    const dev = procs.find((p) => p.id === get().devProcId);
    if (dev?.dev_url && dev.dev_url !== get().devUrl) {
      set({ devUrl: dev.dev_url });
    }
  },

  async followUp(prompt, opts) {
    const { projectId } = get();
    if (projectId == null) return;
    useAgents.getState().connect(); // ensure the progress stream is live
    try {
      const { run_id } = await api.buildStart({
        project_id: projectId,
        prompt,
        model: opts?.model,
        generate_images: opts?.generateImages,
      });
      set({ runId: run_id });
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async regenerateDesign(model) {
    const { projectId, projectName } = get();
    if (projectId == null) return;
    useAgents.getState().connect(); // ensure the progress stream is live
    try {
      const { run_id } = await api.buildStart({
        project_id: projectId,
        prompt: `Regenerate the design for: ${projectName}. New palette, same routes.`,
        model,
        design_only: true,
      });
      set({ runId: run_id });
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },
}));
