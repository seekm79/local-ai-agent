// Typed fetch client for the backend REST API. WS clients are added per phase.

export interface HealthConfig {
  model_big: string;
  model_helper: string;
  model_big_available: boolean;
}

export interface Health {
  status: string;
  backend_port: number;
  ollama_url: string;
  ollama_error: string | null;
  models: string[];
  config: HealthConfig;
}

export async function getHealth(): Promise<Health> {
  const resp = await fetch("/api/health");
  if (!resp.ok) throw new Error(`Health check failed: HTTP ${resp.status}`);
  return (await resp.json()) as Health;
}

// --- Chats -------------------------------------------------------------------
export interface Chat {
  id: number;
  project_id: number | null;
  title: string;
  created_at: string;
}

export interface Message {
  id: number;
  chat_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  reasoning: string | null;
  model: string | null;
  tokens: number | null;
  created_at?: string;
}

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  return (await resp.json()) as T;
}

export const getChats = () => fetch("/api/chats").then((r) => json<Chat[]>(r));

export const createChat = () =>
  fetch("/api/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }).then((r) => json<Chat>(r));

export const getMessages = (chatId: number) =>
  fetch(`/api/chats/${chatId}/messages`).then((r) => json<Message[]>(r));

export const renameChat = (chatId: number, title: string) =>
  fetch(`/api/chats/${chatId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }).then((r) => json<{ status: string }>(r));

export const deleteChat = (chatId: number) =>
  fetch(`/api/chats/${chatId}`, { method: "DELETE" }).then((r) =>
    json<{ status: string }>(r),
  );

// --- Projects & files --------------------------------------------------------
export interface Project {
  id: number;
  name: string;
  slug: string;
  path: string;
  archived: number;
  created_at: string;
}

export interface TreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
}

export const getProjects = () =>
  fetch("/api/projects").then((r) => json<Project[]>(r));

export const createProject = (name: string) =>
  fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }).then((r) => json<Project>(r));

export const deleteProject = (id: number, deleteFiles: boolean) =>
  fetch(`/api/projects/${id}?delete_files=${deleteFiles}`, {
    method: "DELETE",
  }).then((r) => json<{ status: string; deleted_files: boolean }>(r));

export const listTree = (pid: number, path = "") =>
  fetch(`/api/projects/${pid}/tree?path=${encodeURIComponent(path)}`).then((r) =>
    json<TreeNode[]>(r),
  );

export const readFile = (pid: number, path: string) =>
  fetch(`/api/projects/${pid}/read?path=${encodeURIComponent(path)}`).then((r) =>
    json<{ path: string; content: string }>(r),
  );

export const writeFile = (pid: number, path: string, content: string) =>
  fetch(`/api/projects/${pid}/write`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  }).then((r) => json<{ status: string; path: string }>(r));

export const createEntry = (pid: number, path: string, isDir: boolean) =>
  fetch(`/api/projects/${pid}/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, is_dir: isDir }),
  }).then((r) => json<TreeNode>(r));

export const renameEntry = (pid: number, path: string, newPath: string) =>
  fetch(`/api/projects/${pid}/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, new_path: newPath }),
  }).then((r) => json<TreeNode>(r));

export const deleteEntry = (pid: number, path: string) =>
  fetch(`/api/projects/${pid}/delete?path=${encodeURIComponent(path)}`, {
    method: "DELETE",
  }).then((r) => json<{ status: string }>(r));

export interface MediaItem {
  name: string;
  path: string;
  kind: "image" | "video";
}

export const listMedia = (pid: number) =>
  fetch(`/api/projects/${pid}/media`).then((r) => json<MediaItem[]>(r));

export const allFiles = (pid: number) =>
  fetch(`/api/projects/${pid}/all-files`).then((r) => json<string[]>(r));

// --- Codebase semantic search (8.3) ------------------------------------------
export interface SearchHit {
  path: string;
  start_line: number;
  end_line: number;
  text: string;
  score: number;
}

export const searchCode = (pid: number, q: string, k = 8) =>
  fetch(`/api/projects/${pid}/search?q=${encodeURIComponent(q)}&k=${k}`).then(
    (r) => json<{ results: SearchHit[] }>(r),
  );

export const indexProject = (pid: number) =>
  fetch(`/api/projects/${pid}/index`, { method: "POST" }).then((r) =>
    json<{ files: number; chunks: number }>(r),
  );

// URL for serving a project file's raw bytes (img/video src, iframe, etc.).
export const rawUrl = (pid: number, path: string) =>
  `/api/projects/${pid}/raw?path=${encodeURIComponent(path)}`;

export const uploadFiles = (pid: number, path: string, files: FileList) => {
  const fd = new FormData();
  fd.append("path", path);
  for (const f of Array.from(files)) fd.append("files", f);
  return fetch(`/api/projects/${pid}/upload`, {
    method: "POST",
    body: fd,
  }).then((r) => json<{ saved: string[] }>(r));
};

// --- Runners / processes -----------------------------------------------------
export interface RunnerDef {
  kind: string;
  label: string;
  argv: string[];
  cwd: string;
  available: boolean;
  missing_tool: string;
}

export interface ProcInfo {
  id: number;
  project_id: number;
  name: string;
  argv: string[];
  status: "running" | "exited" | "killed";
  exit_code: number | null;
  dev_url: string | null;
  pid: number | null;
}

export type RunStart =
  | { status: "started"; proc: ProcInfo }
  | { status: "needs_confirmation"; command: string; token: string };

export const detectRunners = (pid: number) =>
  fetch(`/api/run/detect?project_id=${pid}`).then((r) => json<RunnerDef[]>(r));

export const listProcesses = (pid: number) =>
  fetch(`/api/run/processes?project_id=${pid}`).then((r) => json<ProcInfo[]>(r));

export const runProject = (pid: number, kind: string) =>
  fetch("/api/run/project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: pid, kind }),
  }).then((r) => json<{ status: string; proc: ProcInfo }>(r));

export const runCommand = (pid: number, argv: string[], cwd = "") =>
  fetch("/api/run/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: pid, argv, cwd }),
  }).then((r) => json<RunStart>(r));

export const confirmRun = (token: string) =>
  fetch("/api/run/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  }).then((r) => json<{ status: string; proc: ProcInfo }>(r));

export const stopProcess = (procId: number) =>
  fetch("/api/run/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proc_id: procId }),
  }).then((r) => json<{ status: string }>(r));

// --- Agent pipeline ----------------------------------------------------------
export interface AgentRun {
  id: number;
  project_id: number;
  goal: string;
  status: string;
  summary: string | null;
  created_at: string;
}

export interface StartRunBody {
  project_id: number;
  goal: string;
  model?: string;
  max_iterations?: number;
  halt_on_fail?: boolean;
  // "single" = plan-once pipeline; "orchestrated" = backlog + ReAct worker loop.
  strategy?: "single" | "orchestrated";
  max_steps?: number;
}

export const startAgentRun = (body: StartRunBody) =>
  fetch("/api/agents/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => json<{ run_id: number }>(r));

export const listAgentRuns = () =>
  fetch("/api/agents/runs").then((r) => json<AgentRun[]>(r));

export interface AgentStepRow {
  id: number;
  run_id: number;
  idx: number;
  kind: string;
  title: string;
  detail: string | null;
  status: string;
  output: string | null;
}

export const getAgentRun = (runId: number) =>
  fetch(`/api/agents/runs/${runId}`).then((r) =>
    json<{ run: AgentRun; steps: AgentStepRow[] }>(r),
  );

export const cancelAgentRun = (runId: number) =>
  fetch("/api/agents/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  }).then((r) => json<{ status: string }>(r));

// --- Checkpoints (shadow git) ------------------------------------------------
export interface CheckpointRow {
  sha: string;
  label: string;
  time: string;
}

export const listCheckpoints = (pid: number) =>
  fetch(`/api/projects/${pid}/checkpoints`).then((r) => json<CheckpointRow[]>(r));

export const restoreCheckpoint = (pid: number, sha: string) =>
  fetch(`/api/projects/${pid}/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sha }),
  }).then((r) => json<{ status: string; sha: string }>(r));

export const snapshotCheckpoint = (pid: number, label: string) =>
  fetch(`/api/projects/${pid}/checkpoint`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  }).then((r) => json<{ sha: string; label: string }>(r));

// --- ComfyUI -----------------------------------------------------------------
export interface ComfyStatus {
  online: boolean;
  error: string | null;
  url: string;
}

export interface WorkflowSlot {
  key: string;
  label: string;
  type: "text" | "int" | "float";
  default: string | number;
}

export interface Workflow {
  file: string;
  name: string;
  description: string;
  slots: WorkflowSlot[];
}

export const getComfyStatus = () =>
  fetch("/api/comfy/status").then((r) => json<ComfyStatus>(r));

export const getWorkflows = () =>
  fetch("/api/comfy/workflows").then((r) => json<Workflow[]>(r));

export const startGenerate = (
  projectId: number,
  workflow: string,
  params: Record<string, unknown>,
) =>
  fetch("/api/comfy/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, workflow, params }),
  }).then((r) => json<{ status: string }>(r));

// --- Agent modes (personas) --------------------------------------------------
export interface Mode {
  id?: number;
  slug: string;
  name: string;
  system_prompt: string;
  model: string | null;
  temperature: number | null;
  top_p: number | null;
  allowed_tools: string[];
  file_globs: string[];
  built_in?: number;
}

export const getModes = () => fetch("/api/modes").then((r) => json<Mode[]>(r));

export const getModeTools = () =>
  fetch("/api/modes/tools").then((r) => json<string[]>(r));

export const upsertMode = (mode: Mode) =>
  fetch(`/api/modes/${encodeURIComponent(mode.slug)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(mode),
  }).then((r) => json<Mode>(r));

export const deleteMode = (slug: string) =>
  fetch(`/api/modes/${encodeURIComponent(slug)}`, { method: "DELETE" }).then((r) =>
    json<{ status: string }>(r),
  );

// --- Build tab (Phase 9) -----------------------------------------------------
export interface Palette {
  radius: string;
  light: Record<string, string>;
  dark: Record<string, string>;
}

export const scaffoldBuild = (name: string, prompt: string) =>
  fetch("/api/build/scaffold", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, prompt }),
  }).then((r) => json<{ project: Project; install_proc: ProcInfo }>(r));

export interface BuildProjectInfo {
  id: number;
  name: string;
  created_at: string;
  deps_installed: boolean;
  latest_run: { id: number; status: string; goal: string } | null;
}

export const listBuildProjects = () =>
  fetch("/api/build/projects").then((r) => json<BuildProjectInfo[]>(r));

export const startDev = (pid: number) =>
  fetch(`/api/build/dev/${pid}`, { method: "POST" }).then((r) =>
    json<{ proc: ProcInfo }>(r),
  );

export const buildStart = (body: {
  project_id: number;
  prompt: string;
  model?: string;
  design_only?: boolean;
  generate_images?: boolean;
}) =>
  fetch("/api/build/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => json<{ run_id: number }>(r));

export type AttachRole = "design_reference" | "asset" | "content";

export interface Attachment {
  id?: number;
  path: string;
  role: AttachRole;
  kind: string;
  colors?: string[];
  description?: string; // vision-model interpretation (images)
}

export const deleteAttachment = (pid: number, assetId: number) =>
  fetch(`/api/build/attachments/${pid}/${assetId}`, { method: "DELETE" }).then(
    (r) => json<{ status: string }>(r),
  );

export const attachBuild = (pid: number, file: File, role: AttachRole) => {
  const fd = new FormData();
  fd.append("role", role);
  fd.append("file", file);
  return fetch(`/api/build/attach/${pid}`, { method: "POST", body: fd }).then(
    (r) => json<Attachment>(r),
  );
};

export const listAttachments = (pid: number) =>
  fetch(`/api/build/attachments/${pid}`).then((r) => json<Attachment[]>(r));

export const getPalette = (pid: number) =>
  fetch(`/api/build/palette/${pid}`).then((r) => json<Palette>(r));

export const putPalette = (pid: number, palette: Palette) =>
  fetch(`/api/build/palette/${pid}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(palette),
  }).then((r) => json<Palette>(r));

// --- Settings ----------------------------------------------------------------
export type Settings = Record<string, string | number | string[]>;

export const getSettings = () =>
  fetch("/api/settings").then((r) => json<Settings>(r));

export const updateSettings = (updates: Settings) =>
  fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  }).then((r) => json<Settings>(r));
