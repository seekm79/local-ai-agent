// Minimal local stand-in for the Lovable-cloud SSR error page.
export function renderErrorPage(): string {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Something went wrong</title>
    <style>
      body { font-family: system-ui, sans-serif; background: #0b0b0f; color: #e5e7eb;
             display: grid; place-items: center; height: 100vh; margin: 0; }
      .card { text-align: center; max-width: 28rem; padding: 2rem; }
      a { color: #93c5fd; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>This page didn't load</h1>
      <p>Something went wrong on the server. Try refreshing or head <a href="/">home</a>.</p>
    </div>
  </body>
</html>`;
}
