// Minimal local stand-in for the Lovable-cloud error-capture module. Records the
// most recent unhandled error so the SSR handler can surface it. The bare import
// installs process-level listeners; consumeLastCapturedError() reads + clears it.
let lastError: unknown;

function record(err: unknown) {
  lastError = err;
}

if (typeof process !== "undefined" && process.on) {
  process.on("uncaughtException", record);
  process.on("unhandledRejection", record);
}

export function consumeLastCapturedError(): unknown {
  const e = lastError;
  lastError = undefined;
  return e;
}
