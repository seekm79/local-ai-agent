import { create } from "zustand";
import * as api from "../api/client";
import { useRun } from "./run";
import { useAgents } from "./agents";
import { useProject } from "./project";

interface BuildState {
  projectId: number | null;
  projectName: string;
  phase: "entry" | "work";
  installProcId: number | null;
  devProcId: number | null;
  devUrl: string | null;
  installing: boolean;
  error: string | null;

  scaffold: (
    name: string,
    prompt: string,
    opts: { model?: string; attachments?: { file: File; role: api.AttachRole }[]; generateImages?: boolean },
  ) => Promise<void>;
  followUp: (prompt: string, opts?: { model?: string; generateImages?: boolean }) => Promise<void>;
  regenerateDesign: (model?: string) => Promise<void>;
  attachToProject: (file: File, role: api.AttachRole) => Promise<void>;
  onProcesses: () => void; // called when the run store updates
  reset: () => Promise<void>;
}

const ENTRY_STATE = {
  projectId: null,
  projectName: "",
  phase: "entry" as const,
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
  installProcId: null,
  devProcId: null,
  devUrl: null,
  installing: false,
  error: null,

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
      set({
        projectId: project.id,
        projectName: project.name,
        phase: "work",
        installProcId: install_proc.id,
      });
      // Upload any attachments so the Designer/Builder can use them.
      for (const a of opts.attachments ?? []) {
        try {
          await api.attachBuild(project.id, a.file, a.role);
        } catch {
          /* skip a failed attachment */
        }
      }
      await api.buildStart({
        project_id: project.id,
        prompt,
        model: opts.model,
        generate_images: opts.generateImages,
      });
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
  // server once install has exited, and capture the dev URL.
  onProcesses() {
    const { projectId, installProcId, devProcId } = get();
    if (projectId == null) return;
    const procs = useRun.getState().processes.filter((p) => p.project_id === projectId);

    const install = procs.find((p) => p.id === installProcId);
    if (install && install.status !== "running" && get().installing && devProcId == null) {
      set({ installing: false });
      void api
        .startDev(projectId)
        .then((r) => set({ devProcId: r.proc.id }))
        .catch((e) => set({ error: String((e as Error).message) }));
    }

    const dev = procs.find((p) => p.id === devProcId);
    if (dev?.dev_url && dev.dev_url !== get().devUrl) {
      set({ devUrl: dev.dev_url });
    }
  },

  async followUp(prompt, opts) {
    const { projectId } = get();
    if (projectId == null) return;
    try {
      await api.buildStart({
        project_id: projectId,
        prompt,
        model: opts?.model,
        generate_images: opts?.generateImages,
      });
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async regenerateDesign(model) {
    const { projectId, projectName } = get();
    if (projectId == null) return;
    try {
      await api.buildStart({
        project_id: projectId,
        prompt: `Regenerate the design for: ${projectName}. New palette, same routes.`,
        model,
        design_only: true,
      });
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },
}));
