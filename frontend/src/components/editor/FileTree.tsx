import { useState } from "react";
import type { TreeNode } from "../../api/client";
import { useProject } from "../../stores/project";

// Recursive lazy file tree. Directories load their children on first expand.
export default function FileTree() {
  const { currentId, childrenByDir, createEntry, uploadTo } = useProject();
  const [creating, setCreating] = useState<null | { dir: boolean }>(null);
  const [name, setName] = useState("");

  if (currentId == null) return null;

  const submitCreate = () => {
    const n = name.trim();
    setCreating(null);
    setName("");
    if (n) void createEntry(n, creating?.dir ?? false);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-edge px-2 py-1 text-xs text-neutral-400">
        <span className="mr-auto uppercase tracking-wide">Files</span>
        <button
          title="New file"
          className="rounded px-1 hover:bg-edge"
          onClick={() => setCreating({ dir: false })}
        >
          ＋file
        </button>
        <button
          title="New folder"
          className="rounded px-1 hover:bg-edge"
          onClick={() => setCreating({ dir: true })}
        >
          ＋dir
        </button>
        <label title="Upload" className="cursor-pointer rounded px-1 hover:bg-edge">
          ⇪
          <input
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) void uploadTo("assets", e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>

      {creating && (
        <div className="border-b border-edge p-1">
          <input
            autoFocus
            className="w-full rounded border border-edge bg-panel px-1 text-sm"
            placeholder={creating.dir ? "folder name" : "file.ext"}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={submitCreate}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitCreate();
              if (e.key === "Escape") {
                setCreating(null);
                setName("");
              }
            }}
          />
        </div>
      )}

      <div className="flex-1 overflow-auto py-1 text-sm">
        <Nodes dir="" depth={0} nodes={childrenByDir[""] ?? []} />
      </div>
    </div>
  );
}

function Nodes({
  nodes,
  depth,
}: {
  dir: string;
  depth: number;
  nodes: TreeNode[];
}) {
  return (
    <>
      {nodes.map((n) =>
        n.type === "dir" ? (
          <DirRow key={n.path} node={n} depth={depth} />
        ) : (
          <FileRow key={n.path} node={n} depth={depth} />
        ),
      )}
    </>
  );
}

function DirRow({ node, depth }: { node: TreeNode; depth: number }) {
  const { expanded, childrenByDir, toggleDir } = useProject();
  const open = !!expanded[node.path];
  return (
    <div>
      <Row depth={depth} onClick={() => void toggleDir(node.path)}>
        <span className="text-neutral-500">{open ? "▾" : "▸"}</span>
        <span className="truncate">{node.name}</span>
      </Row>
      {open && (
        <Nodes
          dir={node.path}
          depth={depth + 1}
          nodes={childrenByDir[node.path] ?? []}
        />
      )}
    </div>
  );
}

function FileRow({ node, depth }: { node: TreeNode; depth: number }) {
  const { openFile, activePath, renameEntry, deleteEntry } = useProject();
  const active = activePath === node.path;
  return (
    <Row
      depth={depth}
      active={active}
      onClick={() => void openFile(node.path)}
      onContext={(e) => {
        e.preventDefault();
        const action = window.prompt(
          `Entry "${node.name}" — type "rename" or "delete"`,
          "",
        );
        if (action === "rename") {
          const to = window.prompt("New path (relative to project):", node.path);
          if (to && to !== node.path) void renameEntry(node.path, to);
        } else if (action === "delete") {
          if (confirm(`Delete "${node.path}"?`)) void deleteEntry(node.path);
        }
      }}
    >
      <span className="w-3" />
      <span className="truncate">{node.name}</span>
    </Row>
  );
}

function Row({
  depth,
  active,
  onClick,
  onContext,
  children,
}: {
  depth: number;
  active?: boolean;
  onClick?: () => void;
  onContext?: (e: React.MouseEvent) => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      onContextMenu={onContext}
      className={
        "flex w-full items-center gap-1 px-2 py-0.5 text-left hover:bg-edge/60 " +
        (active ? "bg-edge text-neutral-100" : "text-neutral-300")
      }
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
    >
      {children}
    </button>
  );
}
