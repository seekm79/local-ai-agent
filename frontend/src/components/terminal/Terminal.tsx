import { useEffect, useRef } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

// Interactive PTY terminal bound to /ws/terminal for the given project.
export default function Terminal({ projectId }: { projectId: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const term = new XTerm({
      fontSize: 13,
      fontFamily: 'ui-monospace, "Cascadia Code", Consolas, monospace',
      cursorBlink: true,
      theme: { background: "#181825", foreground: "#cdd6f4" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(el);
    fit.fit();

    const ws = new WebSocket(
      `ws://${location.host}/ws/terminal?project_id=${projectId}`,
    );

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "output") term.write(msg.payload.data);
      else if (msg.type === "exit") term.write("\r\n[process exited]\r\n");
      else if (msg.type === "error")
        term.write(`\r\n[error] ${msg.payload.message}\r\n`);
    };

    const sendResize = () => {
      try {
        fit.fit();
      } catch {
        /* element not measurable yet */
      }
      if (ws.readyState === WebSocket.OPEN)
        ws.send(
          JSON.stringify({
            type: "resize",
            payload: { cols: term.cols, rows: term.rows },
          }),
        );
    };
    ws.onopen = () => sendResize();

    term.onData((d) => {
      if (ws.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ type: "input", payload: { data: d } }));
    });

    const ro = new ResizeObserver(() => sendResize());
    ro.observe(el);

    return () => {
      ro.disconnect();
      ws.close();
      term.dispose();
    };
  }, [projectId]);

  return <div ref={ref} className="h-full w-full overflow-hidden" />;
}
