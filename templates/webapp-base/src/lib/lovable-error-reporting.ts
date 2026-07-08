// Local no-op stand-in for the Lovable-cloud error reporter. The base template's
// __root.tsx imports this; locally we just log. Safe to extend.
export function reportLovableError(
  error: unknown,
  context?: Record<string, unknown>,
): void {
  // Keep it quiet but visible in the console for local debugging.
  console.error("[app error]", error, context ?? {});
}
