import { useContext, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { ApplyContext } from "./applyContext";

// Extract raw text from a hast node subtree (for the copy button), independent
// of the highlighted <span> tree rehype-highlight produces.
function hastText(node: any): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  if (Array.isArray(node.children))
    return node.children.map(hastText).join("");
  return "";
}

function langOf(node: any): string | null {
  const code = node?.children?.find((c: any) => c.tagName === "code");
  const cls: string[] = code?.properties?.className ?? [];
  const hit = cls.find((c) => c.startsWith("language-"));
  return hit ? hit.slice("language-".length) : null;
}

function CodeBlock({ node, children }: { node?: any; children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const onApply = useContext(ApplyContext);
  const raw = hastText(node);
  const lang = langOf(node);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard blocked — ignore */
    }
  };

  return (
    <div className="group relative my-3 overflow-hidden rounded-md border border-edge bg-panelalt">
      <div className="flex items-center justify-between border-b border-edge px-3 py-1 text-xs text-neutral-400">
        <span>{lang ?? "code"}</span>
        <div className="flex items-center gap-1">
          {onApply && (
            <button
              onClick={() => onApply(raw)}
              className="rounded px-2 py-0.5 text-accent hover:bg-edge"
            >
              apply
            </button>
          )}
          <button
            onClick={copy}
            className="rounded px-2 py-0.5 hover:bg-edge hover:text-neutral-100"
          >
            {copied ? "copied ✓" : "copy"}
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto p-3 text-sm leading-relaxed">
        {children}
      </pre>
    </div>
  );
}

export default function Markdown({ content }: { content: string }) {
  return (
    <div className="wb-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{ pre: CodeBlock }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
