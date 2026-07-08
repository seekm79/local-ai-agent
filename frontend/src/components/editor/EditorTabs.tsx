import { useProject } from "../../stores/project";

export default function EditorTabs() {
  const { openFiles, activePath, setActive, closeFile } = useProject();

  if (openFiles.length === 0) return null;

  return (
    <div className="flex items-stretch overflow-x-auto border-b border-edge bg-panelalt">
      {openFiles.map((f) => {
        const dirty = f.content !== f.original;
        const active = f.path === activePath;
        const name = f.path.split("/").pop();
        return (
          <div
            key={f.path}
            className={
              "group flex items-center gap-2 border-r border-edge px-3 py-1.5 text-sm " +
              (active
                ? "bg-panel text-neutral-100"
                : "text-neutral-400 hover:bg-panel/50")
            }
          >
            <button
              className="flex items-center gap-1"
              onClick={() => setActive(f.path)}
              title={f.path}
            >
              {dirty && <span className="text-accent">●</span>}
              <span>{name}</span>
            </button>
            <button
              className="text-neutral-500 opacity-0 group-hover:opacity-100 hover:text-red-400"
              title="Close"
              onClick={() => closeFile(f.path)}
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
