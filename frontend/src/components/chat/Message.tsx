import { useState } from "react";
import type { Message as Msg } from "../../api/client";
import { useSession } from "../../stores/session";
import { usePreview } from "../../stores/preview";
import { extractHtmlDoc } from "../preview/html";
import Markdown from "./Markdown";

export default function Message({
  msg,
  isLastUser,
  isLastAssistant,
  streaming,
}: {
  msg: Msg;
  isLastUser: boolean;
  isLastAssistant: boolean;
  streaming: boolean;
}) {
  const { regenerate, editResend } = useSession();
  const openPreview = usePreview((s) => s.open);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(msg.content);

  const isUser = msg.role === "user";
  const htmlDoc = !isUser ? extractHtmlDoc(msg.content) : null;

  if (isUser && editing) {
    return (
      <div className="flex justify-end">
        <div className="w-full max-w-[80%]">
          <textarea
            className="w-full rounded-md border border-edge bg-panelalt p-2 text-sm"
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoFocus
          />
          <div className="mt-1 flex justify-end gap-2 text-xs">
            <button
              className="rounded px-2 py-1 hover:bg-edge"
              onClick={() => {
                setEditing(false);
                setDraft(msg.content);
              }}
            >
              cancel
            </button>
            <button
              className="rounded bg-accent px-2 py-1 text-black"
              onClick={() => {
                setEditing(false);
                if (draft.trim()) void editResend(msg.id, draft.trim());
              }}
            >
              save & resend
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={"flex " + (isUser ? "justify-end" : "justify-start")}>
      <div className={"max-w-[85%] " + (isUser ? "text-right" : "text-left")}>
        {/* Collapsible thinking section for assistants */}
        {!isUser && msg.reasoning && (
          <details className="mb-2 rounded-md border border-edge bg-panelalt/60 text-sm">
            <summary className="cursor-pointer select-none px-3 py-1.5 text-neutral-400">
              💭 Thinking{streaming && isLastAssistant ? "…" : ""}
            </summary>
            <div className="whitespace-pre-wrap px-3 pb-3 pt-1 text-neutral-400">
              {msg.reasoning}
            </div>
          </details>
        )}

        <div
          className={
            "inline-block rounded-lg px-4 py-2 text-left " +
            (isUser ? "bg-accent/20" : "bg-panel border border-edge")
          }
        >
          {isUser ? (
            <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
          ) : msg.content ? (
            <Markdown content={msg.content} />
          ) : (
            <span className="text-neutral-500">
              {streaming ? "…" : "(empty)"}
            </span>
          )}
        </div>

        {/* Footer / actions */}
        <div className="mt-1 flex items-center gap-3 text-xs text-neutral-500">
          {!isUser && msg.model && <span>{msg.model}</span>}
          {!isUser && msg.tokens ? <span>{msg.tokens} tok</span> : null}
          {isUser && isLastUser && !streaming && (
            <button className="hover:text-neutral-300" onClick={() => setEditing(true)}>
              edit
            </button>
          )}
          {!isUser && isLastAssistant && !streaming && (
            <button
              className="hover:text-neutral-300"
              onClick={() => void regenerate()}
            >
              regenerate
            </button>
          )}
          {htmlDoc && (
            <button
              className="text-accent hover:text-accent/80"
              onClick={() =>
                openPreview({ kind: "html", html: htmlDoc, title: "HTML preview" })
              }
            >
              ▶ Preview
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
