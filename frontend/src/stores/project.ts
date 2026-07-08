import { create } from "zustand";
import * as api from "../api/client";

type Project = api.Project;
type TreeNode = api.TreeNode;

interface OpenFile {
  path: string;
  content: string; // live buffer
  original: string; // last-saved content (for dirty + diff)
}

const LAST_PROJECT_KEY = "wb:lastProjectId";
const remember = (id: number | null) => {
  try {
    if (id == null) localStorage.removeItem(LAST_PROJECT_KEY);
    else localStorage.setItem(LAST_PROJECT_KEY, String(id));
  } catch {
    /* non-fatal */
  }
};

const parentDir = (path: string) => {
  const i = path.lastIndexOf("/");
  return i === -1 ? "" : path.slice(0, i);
};

interface ProjectState {
  projects: Project[];
  currentId: number | null;
  // children keyed by directory path ("" = project root)
  childrenByDir: Record<string, TreeNode[]>;
  expanded: Record<string, boolean>;

  openFiles: OpenFile[];
  activePath: string | null;
  error: string | null;

  loadProjects: () => Promise<void>;
  createProject: (name: string) => Promise<void>;
  selectProject: (id: number) => Promise<void>;
  deleteProject: (id: number, deleteFiles: boolean) => Promise<void>;

  loadDir: (path: string) => Promise<void>;
  toggleDir: (path: string) => Promise<void>;
  refreshDir: (path: string) => Promise<void>;

  openFile: (path: string) => Promise<void>;
  closeFile: (path: string) => void;
  setActive: (path: string) => void;
  editBuffer: (path: string, content: string) => void;
  saveFile: (path: string) => Promise<void>;
  applyToActive: (content: string) => void;

  createEntry: (path: string, isDir: boolean) => Promise<void>;
  renameEntry: (path: string, newPath: string) => Promise<void>;
  deleteEntry: (path: string) => Promise<void>;
  uploadTo: (dir: string, files: FileList) => Promise<void>;

  clearError: () => void;
}

export const useProject = create<ProjectState>((set, get) => ({
  projects: [],
  currentId: null,
  childrenByDir: {},
  expanded: {},
  openFiles: [],
  activePath: null,
  error: null,

  clearError: () => set({ error: null }),

  async loadProjects() {
    try {
      const projects = await api.getProjects();
      set({ projects });
      if (get().currentId == null) {
        let saved: number | null = null;
        try {
          saved = Number(localStorage.getItem(LAST_PROJECT_KEY)) || null;
        } catch {
          /* ignore */
        }
        if (saved && projects.some((p) => p.id === saved)) {
          await get().selectProject(saved);
        }
      }
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async createProject(name) {
    try {
      const p = await api.createProject(name);
      set((s) => ({ projects: [p, ...s.projects] }));
      await get().selectProject(p.id);
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async selectProject(id) {
    remember(id);
    set({
      currentId: id,
      childrenByDir: {},
      expanded: {},
      openFiles: [],
      activePath: null,
    });
    await get().loadDir("");
  },

  async deleteProject(id, deleteFiles) {
    try {
      await api.deleteProject(id, deleteFiles);
      set((s) => {
        const projects = s.projects.filter((p) => p.id !== id);
        const clearing = s.currentId === id;
        if (clearing) remember(null);
        return {
          projects,
          currentId: clearing ? null : s.currentId,
          childrenByDir: clearing ? {} : s.childrenByDir,
          openFiles: clearing ? [] : s.openFiles,
          activePath: clearing ? null : s.activePath,
        };
      });
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async loadDir(path) {
    const pid = get().currentId;
    if (pid == null) return;
    try {
      const children = await api.listTree(pid, path);
      set((s) => ({ childrenByDir: { ...s.childrenByDir, [path]: children } }));
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async toggleDir(path) {
    const isOpen = get().expanded[path];
    if (!isOpen && !get().childrenByDir[path]) await get().loadDir(path);
    set((s) => ({ expanded: { ...s.expanded, [path]: !isOpen } }));
  },

  async refreshDir(path) {
    await get().loadDir(path);
  },

  async openFile(path) {
    const pid = get().currentId;
    if (pid == null) return;
    if (get().openFiles.some((f) => f.path === path)) {
      set({ activePath: path });
      return;
    }
    try {
      const { content } = await api.readFile(pid, path);
      set((s) => ({
        openFiles: [...s.openFiles, { path, content, original: content }],
        activePath: path,
      }));
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  closeFile(path) {
    set((s) => {
      const openFiles = s.openFiles.filter((f) => f.path !== path);
      let activePath = s.activePath;
      if (activePath === path) {
        activePath = openFiles.length ? openFiles[openFiles.length - 1].path : null;
      }
      return { openFiles, activePath };
    });
  },

  setActive: (path) => set({ activePath: path }),

  editBuffer(path, content) {
    set((s) => ({
      openFiles: s.openFiles.map((f) =>
        f.path === path ? { ...f, content } : f,
      ),
    }));
  },

  async saveFile(path) {
    const pid = get().currentId;
    const file = get().openFiles.find((f) => f.path === path);
    if (pid == null || !file) return;
    try {
      await api.writeFile(pid, path, file.content);
      set((s) => ({
        openFiles: s.openFiles.map((f) =>
          f.path === path ? { ...f, original: f.content } : f,
        ),
      }));
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  applyToActive(content) {
    const path = get().activePath;
    if (!path) return;
    get().editBuffer(path, content);
  },

  async createEntry(path, isDir) {
    const pid = get().currentId;
    if (pid == null) return;
    try {
      await api.createEntry(pid, path, isDir);
      await get().refreshDir(parentDir(path));
      if (!isDir) await get().openFile(path);
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async renameEntry(path, newPath) {
    const pid = get().currentId;
    if (pid == null) return;
    try {
      await api.renameEntry(pid, path, newPath);
      await get().refreshDir(parentDir(path));
      if (parentDir(newPath) !== parentDir(path))
        await get().refreshDir(parentDir(newPath));
      // update any open tab
      set((s) => ({
        openFiles: s.openFiles.map((f) =>
          f.path === path ? { ...f, path: newPath } : f,
        ),
        activePath: s.activePath === path ? newPath : s.activePath,
      }));
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async deleteEntry(path) {
    const pid = get().currentId;
    if (pid == null) return;
    try {
      await api.deleteEntry(pid, path);
      await get().refreshDir(parentDir(path));
      // close any open tab under the deleted path
      set((s) => {
        const openFiles = s.openFiles.filter(
          (f) => f.path !== path && !f.path.startsWith(path + "/"),
        );
        const activePath =
          s.activePath && openFiles.some((f) => f.path === s.activePath)
            ? s.activePath
            : (openFiles[openFiles.length - 1]?.path ?? null);
        return { openFiles, activePath };
      });
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },

  async uploadTo(dir, files) {
    const pid = get().currentId;
    if (pid == null) return;
    try {
      await api.uploadFiles(pid, dir, files);
      await get().refreshDir(dir);
    } catch (e) {
      set({ error: String((e as Error).message) });
    }
  },
}));
