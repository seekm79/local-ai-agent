import Editor from "@monaco-editor/react";
import { useProject } from "../../stores/project";
import { languageFor } from "./language";

// Monaco editor bound to one open file. Keyed by path upstream so each tab keeps
// its own model/undo stack. Cmd/Ctrl+S saves.
export default function CodeEditor({
  path,
  content,
}: {
  path: string;
  content: string;
}) {
  const editBuffer = useProject((s) => s.editBuffer);

  return (
    <Editor
      height="100%"
      theme="vs-dark"
      language={languageFor(path)}
      value={content}
      onChange={(v) => editBuffer(path, v ?? "")}
      onMount={(editor, monaco) => {
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
          // Read the live active path at save time from the store.
          const { activePath, saveFile } = useProject.getState();
          if (activePath) void saveFile(activePath);
        });
      }}
      options={{
        fontSize: 13,
        minimap: { enabled: false },
        automaticLayout: true,
        scrollBeyondLastLine: false,
        tabSize: 2,
      }}
    />
  );
}
