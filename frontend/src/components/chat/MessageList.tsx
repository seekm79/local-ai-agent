import { useEffect, useRef } from "react";
import { useSession } from "../../stores/session";
import Message from "./Message";

export default function MessageList() {
  const { messages, streaming, condensed } = useSession();
  const endRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom as content streams in.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const lastUserId = [...messages].reverse().find((m) => m.role === "user")?.id;
  const lastAsstId = [...messages]
    .reverse()
    .find((m) => m.role === "assistant")?.id;

  if (messages.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-neutral-500">
        <div className="text-center">
          <div className="text-2xl">◈</div>
          <p className="mt-2">Start a conversation with a local model.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {condensed && (
        <details className="rounded border border-edge bg-panelalt/50 text-xs text-neutral-400">
          <summary className="cursor-pointer select-none px-3 py-1.5">
            ⚡ Earlier context was condensed to save tokens
          </summary>
          <pre className="whitespace-pre-wrap px-3 pb-3 pt-1">
            {condensed.summary}
          </pre>
        </details>
      )}
      {messages.map((m) => (
        <Message
          key={m.id}
          msg={m}
          isLastUser={m.id === lastUserId}
          isLastAssistant={m.id === lastAsstId}
          streaming={streaming}
        />
      ))}
      <div ref={endRef} />
    </div>
  );
}
