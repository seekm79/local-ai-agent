import { useCallback, useEffect, useState } from "react";
import * as api from "../../api/client";
import { useProject } from "../../stores/project";
import { usePreview } from "../../stores/preview";
import GenerateView from "./GenerateView";

export default function AssetsView() {
  const { projects, currentId, loadProjects, selectProject, uploadTo } =
    useProject();
  const openPreview = usePreview((s) => s.open);
  const [media, setMedia] = useState<api.MediaItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [tab, setTab] = useState<"gallery" | "generate">("gallery");

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const reload = useCallback(async () => {
    if (currentId == null) return setMedia([]);
    try {
      setMedia(await api.listMedia(currentId));
    } catch {
      setMedia([]);
    }
  }, [currentId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const doUpload = async (files: FileList) => {
    if (currentId == null || !files.length) return;
    await uploadTo("assets", files);
    await reload();
  };

  const images = media.filter((m) => m.kind === "image");
  const videos = media.filter((m) => m.kind === "video");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-edge bg-panelalt px-3 py-1.5 text-sm">
        <span className="text-xs uppercase tracking-wide text-neutral-500">
          Assets
        </span>
        <select
          className="rounded border border-edge bg-panel px-2 py-1"
          value={currentId ?? ""}
          onChange={(e) => e.target.value && void selectProject(Number(e.target.value))}
        >
          <option value="">— select project —</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <label className="cursor-pointer rounded bg-edge px-2 py-1 text-xs hover:bg-edge/70">
          Upload
          <input
            type="file"
            multiple
            accept="image/*,video/*"
            className="hidden"
            disabled={currentId == null}
            onChange={(e) => {
              if (e.target.files) void doUpload(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        <div className="ml-auto flex items-center gap-1">
          <button
            className={
              "rounded px-2 py-1 text-xs " +
              (tab === "gallery" ? "bg-edge text-neutral-100" : "hover:bg-edge")
            }
            onClick={() => setTab("gallery")}
          >
            Gallery
          </button>
          <button
            className={
              "rounded px-2 py-1 text-xs " +
              (tab === "generate" ? "bg-edge text-neutral-100" : "hover:bg-edge")
            }
            onClick={() => setTab("generate")}
          >
            Generate
          </button>
          {tab === "gallery" && (
            <button
              className="rounded px-2 py-1 text-xs hover:bg-edge"
              onClick={() => void reload()}
            >
              ↻ Refresh
            </button>
          )}
        </div>
      </div>

      {currentId == null ? (
        <div className="flex flex-1 items-center justify-center text-neutral-500">
          Select a project to view its media assets.
        </div>
      ) : tab === "generate" ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <GenerateView
            projectId={currentId}
            onGenerated={() => {
              setTab("gallery");
              void reload();
            }}
          />
        </div>
      ) : (
        <div
          className={
            "min-h-0 flex-1 overflow-y-auto p-4 " +
            (dragOver ? "bg-accent/5 outline-dashed outline-2 outline-accent" : "")
          }
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files?.length) void doUpload(e.dataTransfer.files);
          }}
        >
          {media.length === 0 && (
            <div className="mt-16 text-center text-neutral-500">
              No images or videos yet. Drag files here or use Upload — they're
              saved under <code>assets/</code>.
            </div>
          )}

          {images.length > 0 && (
            <>
              <h3 className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
                Images ({images.length})
              </h3>
              <div className="mb-6 grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
                {images.map((m) => (
                  <button
                    key={m.path}
                    className="group overflow-hidden rounded border border-edge bg-panelalt"
                    onClick={() =>
                      openPreview({
                        kind: "image",
                        src: api.rawUrl(currentId, m.path),
                        title: m.path,
                      })
                    }
                    title={m.path}
                  >
                    <img
                      src={api.rawUrl(currentId, m.path)}
                      alt={m.name}
                      loading="lazy"
                      className="h-28 w-full bg-black/20 object-contain"
                    />
                    <div className="truncate px-1 py-0.5 text-[10px] text-neutral-400">
                      {m.name}
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}

          {videos.length > 0 && (
            <>
              <h3 className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
                Videos ({videos.length})
              </h3>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
                {videos.map((m) => (
                  <div
                    key={m.path}
                    className="overflow-hidden rounded border border-edge bg-panelalt"
                  >
                    <video
                      src={api.rawUrl(currentId, m.path)}
                      controls
                      preload="metadata"
                      className="w-full bg-black"
                    />
                    <div className="truncate px-2 py-1 text-xs text-neutral-400">
                      {m.name}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
