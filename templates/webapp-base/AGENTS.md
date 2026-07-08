# AGENTS.md

> Read this file first, before planning or editing anything. Follow it on every
> request. Precedence when instructions conflict: the user's current message >
> this file > your defaults. When you make a significant design or architecture
> decision, append a short note to the relevant section below so future edits
> stay consistent.

## Project overview

<!-- One line: what this project is. Filled in when the project is created. -->
A web application scaffolded from the fixed base template.

## Stack and constraints (do not violate)

- Stack is locked: TanStack Start (React 19 + TanStack Router, file-based routes
  in `src/routes/`), Vite, Tailwind CSS v4, Bun, TypeScript, shadcn/ui.
- Design ONLY with the two allowed levers:
  1. Retheme by rewriting the `oklch` token *values* in `src/styles.css`
     (`:root` for light, `.dark` for dark). Never rename tokens. Never hardcode
     hex/oklch colors in components — use Tailwind classes that map to tokens
     (`bg-primary`, `text-muted-foreground`, `rounded-lg`).
  2. Compose the existing `src/components/ui/*` primitives into routes. Put
     app-specific components in `src/components/` — never in `ui/`.
- Never rebuild the shadcn primitives, swap the router, change the styling
  system, or add a second component library.
- All colors must be `oklch`.

## Design system

<!-- Current palette summary + notes. Updated when the design changes. -->
Default token palette (slate/neutral). All color flows through the CSS variables
in `src/styles.css`.

## Conventions

- Package manager: **Bun**.
- Icons: `lucide-react`. Charts: `recharts`.
- Keep the connected branch in a working state.

## Do not touch

- `src/components/ui/**` (generated shadcn primitives)
- `src/routeTree.gen.ts` (generated)
- The `@theme` block in `src/styles.css`

## Commands

- Install: `bun install`
- Dev: `bun run dev`
- Build: `bun run build`
- Lint: `bun run lint`

## User rules

<!-- Free section. The user edits this to add standing instructions, e.g.
     "warm editorial palette, serif headings", "buttons fully rounded",
     "no external analytics". The agent must honor these. -->
