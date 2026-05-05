# Frontend (UI) Guide

The klaus dashboard is a **React + TypeScript + Tailwind CSS** single-page app built with Vite. This guide covers the architecture, how to add pages, connect to APIs, and follow the design system.

## Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Framework | React 19 | Component rendering |
| Language | TypeScript | Type safety |
| Styling | Tailwind CSS | Utility-first CSS |
| Build | Vite | Dev server + production bundler |
| Visualization | React Flow (`@xyflow/react`) | Pipeline and knowledge graphs |
| Markdown | `react-markdown` + `remark-gfm` + `rehype-highlight` | Chat message rendering |
| Icons | `lucide-react` | Consistent icon set |
| Utils | `clsx` | Conditional class names |

## Project Structure

```
ui/
├── index.html              Entry HTML (loads fonts, applies theme)
├── vite.config.ts          Vite config (proxy, build output)
├── tsconfig.json           TypeScript config
├── package.json            Dependencies and scripts
└── src/
    ├── main.tsx             React mount point
    ├── App.tsx              Root component, page state, session management
    ├── index.css            Tailwind imports, theme tokens, global styles
    ├── hooks/
    │   ├── useEventStream.ts SSE connection + REST helpers
    │   └── useTheme.ts      Dark/light theme toggle (localStorage)
    ├── components/
    │   ├── Layout.tsx       App shell — header, nav, sidebar slot
    │   ├── Sidebar.tsx      Conversation history panel
    │   └── Markdown.tsx     Markdown renderer with syntax highlighting
    └── pages/
        ├── Chat.tsx         Main chat interface
        ├── Knowledge.tsx    Memory graph visualization
        ├── Flow.tsx         Agent → model pipeline visualization
        ├── Models.tsx       Model backend dashboard
        ├── Routing.tsx      Task routing rules editor
        └── Activity.tsx     Live event log
```

## Development Setup

```bash
cd ui
npm install        # install dependencies
npm run dev        # start Vite dev server on http://localhost:5173
```

The Vite dev server proxies `/api` and `/health` requests to `http://localhost:8000` (the backend). Run both servers simultaneously:

```bash
# Terminal 1 — backend
uv run klaus-dev

# Terminal 2 — frontend
cd ui && npm run dev
```

### Build for production

```bash
npm run build   # outputs to ../src/klaus/ui/dist/
```

The backend serves these static files automatically.

## Adding a New Page

### 1. Create the page component

Create `ui/src/pages/YourPage.tsx`:

```tsx
import { useEffect, useState } from 'react';

interface YourData {
  id: string;
  name: string;
}

export default function YourPage() {
  const [items, setItems] = useState<YourData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/your-endpoint')
      .then((r) => r.json())
      .then((data) => setItems(data.items ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="h-full overflow-y-auto p-6">
      <h2 className="text-lg font-semibold text-stone-800 dark:text-stone-200 mb-4">
        Your Page
      </h2>
      {loading ? (
        <p className="text-sm text-stone-400">Loading...</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="p-3 rounded-lg bg-stone-50 dark:bg-stone-800/50
                         border border-stone-200 dark:border-stone-700"
            >
              <span className="text-sm text-stone-700 dark:text-stone-300">
                {item.name}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

### 2. Register the page in `App.tsx`

Add the page ID to the `Page` type:

```tsx
export type Page = 'chat' | 'flow' | 'models' | 'routing' | 'activity' | 'knowledge' | 'yourpage';
```

Import and render it:

```tsx
import YourPage from './pages/YourPage';

// Inside the render, where other pages are conditionally rendered:
{page === 'yourpage' && <YourPage />}
```

### 3. Add navigation in `Layout.tsx`

Add a nav entry to the nav items array:

```tsx
import { YourIcon } from 'lucide-react';

// In the NAV array or wherever nav items are defined:
{ id: 'yourpage', label: 'Your Page', icon: YourIcon }
```

## Connecting to APIs

### REST endpoints

Use `fetch` with relative URLs. The Vite proxy handles routing to the backend:

```tsx
// GET
const data = await fetch('/api/memory/graph').then(r => r.json());

// POST with JSON body
await fetch('/api/routing/rules', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ task: 'coding', rule: { preferred_backend: 'ollama' } }),
});

// DELETE
await fetch('/api/routing/rules/coding', { method: 'DELETE' });
```

### Event Stream (SSE + REST)

Use the `useEventStream` hook for real-time events and the `postChat` / `postPlanAction` helpers for sending:

```tsx
import { useEventStream, postChat } from '../hooks/useEventStream';

function MyComponent({ sessionId }: { sessionId: string }) {
  const ws = useEventStream(sessionId);

  useEffect(() => {
    return ws.on((msg) => {
      if (msg.type === 'chat.token') {
        // Handle streaming token
      }
    });
  }, [ws]);

  const sendChat = () => {
    postChat({
      id: sessionId,
      messages: [{ role: 'user', content: 'Hello' }],
    });
  };
}
```

### REST endpoints (Client → Server)

| Endpoint | Body | Purpose |
|----------|------|---------|
| `POST /api/events/chat/send` | `{ id, messages, images?, model?, backend?, temperature? }` | Send chat message |
| `POST /api/events/chat/{id}/plan-action` | `{ action, edits?, reason? }` | Approve/reject/edit plan |

### SSE events (Server → Client)

| Type | Fields | Purpose |
|------|--------|---------|
| `model.routed` | `backend`, `model`, `reason`, `chat_id` | Which model was selected |
| `chat.token` | `token`, `chat_id` | Streaming response token |
| `chat.done` | `chat_id` | Stream complete |
| `chat.error` | `error`, `chat_id` | Error during generation |
| `mcp.tool_called` | `name`, `args`, `chat_id` | Agent called a tool |
| `tool.result` | `name`, `content`, `chat_id` | Tool returned a result |
| `backend.registered` | `name`, `type`, `locality` | New backend added |
| `routing.rule_set` | `task`, `rule` | Routing rule updated |

## Design System

### Theme Tokens

Defined in `ui/src/index.css` as CSS custom properties:

```css
:root {
  --color-surface: #fafaf9;      /* Main background */
  --color-surface-alt: #f5f5f4;  /* Sidebar, cards */
  --color-border: #e7e5e4;       /* Borders */
  --color-accent: #78716c;       /* Primary accent */
  --color-accent-hover: #57534e; /* Hover state */
}

.dark {
  --color-surface: #1c1917;
  --color-surface-alt: #1c1917;
  --color-border: #292524;
  --color-accent: #a8a29e;
  --color-accent-hover: #d6d3d1;
}
```

Use them with Tailwind's arbitrary values: `bg-[var(--color-surface)]` or use the stone color palette directly.

### Color Palette

The UI uses Tailwind's **stone** palette for a warm, neutral look:

| Use | Light | Dark |
|-----|-------|------|
| Background | `bg-stone-50` | `dark:bg-stone-900` |
| Surface | `bg-stone-100` | `dark:bg-stone-800` |
| Text primary | `text-stone-800` | `dark:text-stone-200` |
| Text secondary | `text-stone-500` | `dark:text-stone-400` |
| Text muted | `text-stone-400` | `dark:text-stone-500` |
| Border | `border-stone-200` | `dark:border-stone-700` |
| Accent (tools) | `text-amber-600` | `dark:text-amber-400` |
| Success | `text-emerald-600` | `dark:text-emerald-400` |

### Typography

| Element | Size | Weight |
|---------|------|--------|
| Page title | `text-lg` (18px) | `font-semibold` |
| Section heading | `text-sm` (14px) | `font-medium` |
| Body text | `text-[14px]` | Normal |
| Labels | `text-[12px]` | `font-medium` |
| Monospace/code | `text-[10px]` | `font-mono` |
| Micro (badges) | `text-[10px]` | Normal |

### Component Patterns

**Card:**
```tsx
<div className="p-3 rounded-lg bg-stone-50 dark:bg-stone-800/50
                border border-stone-200 dark:border-stone-700">
```

**Button (primary):**
```tsx
<button className="px-3 py-1.5 rounded-lg text-sm font-medium
                   bg-stone-800 dark:bg-stone-200
                   text-white dark:text-stone-900
                   hover:bg-stone-700 dark:hover:bg-stone-300
                   transition-colors">
```

**Badge/chip:**
```tsx
<span className="text-[10px] px-2 py-0.5 rounded-full
                 bg-stone-100 dark:bg-stone-800
                 text-stone-500 dark:text-stone-400">
```

**Input:**
```tsx
<input className="w-full px-3 py-2 rounded-lg text-sm
                  bg-transparent border border-stone-200 dark:border-stone-700
                  text-stone-800 dark:text-stone-200
                  focus:outline-none focus:ring-1 focus:ring-stone-400" />
```

### Dark Mode

Dark mode is toggled via the `useTheme` hook which adds/removes the `dark` class on `<html>`. Always use `dark:` prefixes on Tailwind classes:

```tsx
<div className="bg-white dark:bg-stone-900 text-stone-800 dark:text-stone-200">
```

## Key Conventions

1. **No React Router** — Page state is managed in `App.tsx` via `useState<Page>`. Navigation is handled by `setPage()` passed as a prop.

2. **No state management library** — Use React's built-in `useState` and `useEffect`. Data is fetched per-page via `fetch`.

3. **Singleton EventSource** — The `useEventStream` hook manages a single SSE connection shared across all components. Don't create additional EventSource connections.

4. **Session persistence** — `sessionId` and theme are stored in `localStorage`. Chat history loads from the backend on mount.

5. **Icons** — Use `lucide-react` exclusively. Import individual icons: `import { Brain, Cpu } from 'lucide-react'`.

6. **Build output** — `npm run build` outputs to `../src/klaus/ui/dist/` which the backend serves. This directory is gitignored.

## Files to Touch When Adding a Feature

| What you're doing | Files |
|-------------------|-------|
| New page | `pages/YourPage.tsx`, `App.tsx` (type + render), `Layout.tsx` (nav) |
| New shared component | `components/YourComponent.tsx` |
| New hook | `hooks/useYourHook.ts` |
| New API integration | Your page + backend route file |
| Theme change | `index.css` |
| New dependency | `package.json` (run `npm install`) |
