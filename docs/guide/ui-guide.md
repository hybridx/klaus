# Frontend (UI) Guide

The klaus dashboard is a **React + TypeScript + Tailwind CSS** single-page app built with Vite.

## Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Framework | React 19 | Component rendering |
| Language | TypeScript | Type safety |
| Styling | Tailwind CSS | Utility-first CSS |
| Build | Vite | Dev server + production bundler |
| Visualization | React Flow (`@xyflow/react`) | Pipeline and knowledge graphs |
| Markdown | `react-markdown` + `remark-gfm` + `rehype-highlight` | Chat rendering |
| Icons | `lucide-react` | Consistent icon set |
| Utils | `clsx` | Conditional class names |

## Development Setup

::: code-group

```bash [Terminal 1 — Backend]
uv run klaus-dev
```

```bash [Terminal 2 — Frontend (HMR)]
cd ui && npm run dev
```

:::

Vite proxies `/api` and `/health` to the backend at `localhost:8000`.

## Adding a New Page

### 1. Create the page component

```tsx
// ui/src/pages/YourPage.tsx
import { useEffect, useState } from 'react';

interface YourData {
  id: string;
  name: string;
}

export default function YourPage() {
  const [items, setItems] = useState<YourData[]>([]);

  useEffect(() => {
    fetch('/api/your-endpoint')
      .then((r) => r.json())
      .then((data) => setItems(data.items ?? []))
      .catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-y-auto p-6">
      <h2 className="text-lg font-semibold text-stone-800 dark:text-stone-200 mb-4">
        Your Page
      </h2>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.id}
               className="p-3 rounded-lg bg-stone-50 dark:bg-stone-800/50
                          border border-stone-200 dark:border-stone-700">
            <span className="text-sm text-stone-700 dark:text-stone-300">
              {item.name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 2. Register in `App.tsx`

Add the page ID to the `Page` type and render it:

```tsx
export type Page = 'chat' | 'flow' | 'models' | ... | 'yourpage';

// In the render:
{page === 'yourpage' && <YourPage />}
```

### 3. Add navigation in `Layout.tsx`

```tsx
import { YourIcon } from 'lucide-react';

// In the nav items:
{ id: 'yourpage', label: 'Your Page', icon: YourIcon }
```

## Connecting to APIs

### REST

```tsx
// GET
const data = await fetch('/api/memory/graph').then(r => r.json());

// POST
await fetch('/api/routing/rules', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ task: 'coding', rule: { preferred_backend: 'ollama' } }),
});

// DELETE
await fetch('/api/routing/rules/coding', { method: 'DELETE' });
```

### WebSocket

Use the singleton `useWebSocket` hook:

```tsx
import { useWebSocket } from '../hooks/useWebSocket';

function MyComponent() {
  const ws = useWebSocket();

  useEffect(() => {
    return ws.on((msg) => {
      if (msg.type === 'chat.token') {
        // Handle streaming token
      }
    });
  }, [ws]);

  const sendChat = () => {
    ws.send({
      type: 'chat',
      id: sessionId,
      messages: [{ role: 'user', content: 'Hello' }],
    });
  };
}
```

## Design System

### Color Palette

The UI uses Tailwind's **stone** palette for a warm, neutral look:

| Use | Light | Dark |
|-----|-------|------|
| Background | `bg-stone-50` | `dark:bg-stone-900` |
| Surface | `bg-stone-100` | `dark:bg-stone-800` |
| Text primary | `text-stone-800` | `dark:text-stone-200` |
| Text secondary | `text-stone-500` | `dark:text-stone-400` |
| Border | `border-stone-200` | `dark:border-stone-700` |
| Accent (tools) | `text-amber-600` | `dark:text-amber-400` |
| Success | `text-emerald-600` | `dark:text-emerald-400` |

### Component Patterns

::: code-group

```tsx [Card]
<div className="p-3 rounded-lg bg-stone-50 dark:bg-stone-800/50
                border border-stone-200 dark:border-stone-700">
```

```tsx [Button]
<button className="px-3 py-1.5 rounded-lg text-sm font-medium
                   bg-stone-800 dark:bg-stone-200
                   text-white dark:text-stone-900
                   hover:bg-stone-700 dark:hover:bg-stone-300
                   transition-colors">
```

```tsx [Badge]
<span className="text-[10px] px-2 py-0.5 rounded-full
                 bg-stone-100 dark:bg-stone-800
                 text-stone-500 dark:text-stone-400">
```

```tsx [Input]
<input className="w-full px-3 py-2 rounded-lg text-sm
                  bg-transparent border border-stone-200 dark:border-stone-700
                  text-stone-800 dark:text-stone-200
                  focus:outline-none focus:ring-1 focus:ring-stone-400" />
```

:::

### Dark Mode

Toggle via `useTheme` hook which adds/removes `dark` class on `<html>`. Always use `dark:` prefixes:

```tsx
<div className="bg-white dark:bg-stone-900 text-stone-800 dark:text-stone-200">
```

## Conventions

| Convention | Details |
|------------|---------|
| **No React Router** | Page state managed in `App.tsx` via `useState<Page>` |
| **No state library** | Built-in `useState` and `useEffect` only |
| **Singleton WebSocket** | One `useWebSocket` shared across all components |
| **Session persistence** | `sessionId` and theme in `localStorage` |
| **Icons** | `lucide-react` only. Import individually. |
| **Build output** | `npm run build` → `../src/klaus/ui/dist/` (gitignored) |
