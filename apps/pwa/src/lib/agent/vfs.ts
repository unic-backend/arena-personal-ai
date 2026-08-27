/* ─────────────────────────────────────────────────────────────
   Virtual project — the real substrate the agent's file/build
   tools operate on. Seeded with a small React/TS repo containing
   genuine defects that the static checker detects from actual
   file contents. Edits are applied for real and persist in
   localStorage, so a "fixed" build stays fixed across sessions.
   ───────────────────────────────────────────────────────────── */

export interface VFile { path: string; content: string }
export type VFS = Record<string, string>;

const SEED: VFS = {
  'package.json': `{
  "name": "pulseboard",
  "private": true,
  "version": "0.4.2",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^19.1.0",
    "react-dom": "^19.1.0",
    "zustand": "^5.0.3"
  },
  "devDependencies": {
    "typescript": "~5.8.3",
    "vite": "^6.3.5",
    "vitest": "^3.1.4"
  }
}
`,
  'tsconfig.json': `{
  "compilerOptions": {
    "target": "ES2022",
    "strict": true,
    "noUnusedLocals": true,
    "jsx": "react-jsx",
    "moduleResolution": "bundler"
  },
  "include": ["src"]
}
`,
  'index.html': `<div id="root"></div>
<script type="module" src="/src/main.tsx"></script>
`,
  'src/main.tsx': `import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(<App />)
`,
  'src/App.tsx': `import { Header } from './components/Header'
import { Board } from './components/Board'
import { useMetrics } from './hooks/useMetrics'

export default function App() {
  const metrics = useMetrics()
  return (
    <main>
      <Header title="Pulseboard" />
      <Board metrics={metrics} />
    </main>
  )
}
`,
  'src/vite-env.d.ts': `/// <reference types="vite/client" />
`,
  'src/index.css': `@import "tailwindcss";
:root { color-scheme: dark; }
`,
  'src/components/Header.tsx': `interface HeaderProps { title: string }

export function Header({ title }: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-4">
      <h1 className="text-lg font-semibold">{title}</h1>
      <span className="text-xs text-zinc-500">live</span>
    </header>
  )
}
`,
  'src/components/Board.tsx': `import { Metric } from '../lib/types'
import { Card } from './Card'
import { formatDuration } from '../utils/format'

export function Board({ metrics }: { metrics: Metric[] }) {
  return (
    <section className="grid grid-cols-3 gap-4 p-6">
      {metrics.map((m) => (
        <Card key={m.id} metric={m} hint={formatDuration(m.windowSeconds)} />
      ))}
    </section>
  )
}
`,
  'src/components/Card.tsx': `import { Metric } from '../lib/types'
import { Badge } from './Badge'
import { cns } from '../utils/cn'

export function Card({ metric, hint }: { metric: Metric; hint: string }) {
  const tone = metric.delta >= 0 ? 'up' : 'down'
  return (
    <article className={cns('rounded-xl border p-4', tone)}>
      <div className="flex justify-between">
        <h3>{metric.label}</h3>
        <Badge tone={tone} value={metric.delta} />
      </div>
      <p className="text-2xl font-semibold">{metric.value}</p>
      <span className="text-xs text-zinc-500">{hint}</span>
    </article>
  )
}
`,
  'src/components/Badge.tsx': `import { cns } from '../utils/cn'

export function Badge({ tone, value }: { tone: 'up' | 'down'; value: number }) {
  return (
    <span className={cns('badge', tone)}>
      {value >= 0 ? '+' : ''}{value}%
    </span>
  )
}
`,
  'src/lib/types.ts': `export interface Metric {
  id: string
  label: string
  value: number
  delta: number
  windowSeconds: number
}
`,
  'src/lib/api.ts': `import { Metric } from './types'

// TODO: reconnect the live websocket feed behind a feature flag
export async function fetchMetrics(signal?: AbortSignal): Promise<Metric[]> {
  const res = await fetch('/api/metrics', { signal })
  if (!res.ok) throw new Error(\`metrics request failed: \${res.status}\`)
  return res.json()
}

export function groupByWindow(metrics: Metric[]) {
  return metrics.reduce<Record<number, Metric[]>>((acc, m) => {
    ;(acc[m.windowSeconds] ??= []).push(m)
    return acc
  }, {})
}
`,
  'src/hooks/useMetrics.ts': `import { useEffect, useState } from 'react'
import { fetchMetrics } from '../lib/api'
import { Metric } from '../lib/types'

export function useMetrics() {
  const [metrics, setMetrics] = useState<Metric[]>([])
  useEffect(() => {
    // FIXME: swallowing fetch errors hides outages from the user
    const ac = new AbortController()
    fetchMetrics(ac.signal).then(setMetrics).catch(() => setMetrics([]))
    return () => ac.abort()
  }, [])
  return metrics
}
`,
  'src/utils/cn.ts': `/** tiny class joiner */
export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ')
}
`,
  'src/utils/format.ts': `import { formatDistance } from 'date-fns'

/** human readable duration, e.g. "2h 05m" */
export function formatDuration(seconds: number): string {
  return seconds * 1000
}

export function relativeToNow(ts: number): string {
  return formatDistance(ts, Date.now(), { addSuffix: true })
}
`,
  'src/utils/format.test.ts': `import { describe, it, expect } from 'vitest'
import { formatDuration, relativeToNow } from './format'

describe('formatDuration', () => {
  it('formats zero', () => expect(formatDuration(0)).toBe('0s'))
  it('formats seconds', () => expect(formatDuration(42)).toBe('42s'))
  it('formats minutes', () => expect(formatDuration(125)).toBe('2m 05s'))
  it('formats hours', () => expect(formatDuration(7325)).toBe('2h 02m'))
  it('returns a string', () => expect(typeof formatDuration(5)).toBe('string'))
})

describe('relativeToNow', () => {
  it('handles now', () => expect(relativeToNow(Date.now())).toContain('ago'))
  it('handles past', () => expect(relativeToNow(Date.now() - 90000)).toContain('minute'))
  it('returns a string', () => expect(typeof relativeToNow(0)).toBe('string'))
})
`,
  'src/utils/cn.test.ts': `import { describe, it, expect } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('joins parts', () => expect(cn('a', 'b')).toBe('a b'))
  it('drops falsy', () => expect(cn('a', false, null)).toBe('a'))
  it('handles empty', () => expect(cn()).toBe(''))
  it('keeps order', () => expect(cn('x', 'y', 'z')).toBe('x y z'))
})
`,
  'src/components/Badge.test.tsx': `import { describe, it, expect } from 'vitest'
import { Badge } from './Badge'

describe('Badge', () => {
  it('renders positive delta', () => expect(Badge({ tone: 'up', value: 4 })).toBeTruthy())
  it('renders negative delta', () => expect(Badge({ tone: 'down', value: -2 })).toBeTruthy())
  it('shows plus sign for up', () => {
    const el = Badge({ tone: 'up', value: 4 }) as any
    expect(JSON.stringify(el)).toContain('+4')
  })
  it('omits plus sign for down', () => {
    const el = Badge({ tone: 'down', value: -2 }) as any
    expect(JSON.stringify(el)).not.toContain('+-')
  })
  it('uses tone class', () => {
    const el = Badge({ tone: 'up', value: 1 }) as any
    expect(JSON.stringify(el)).toContain('badge')
  })
  it('handles zero', () => expect(Badge({ tone: 'up', value: 0 })).toBeTruthy())
})
`,
  'src/lib/api.test.ts': `import { describe, it, expect } from 'vitest'
import { groupByWindow } from './api'
import { Metric } from './types'

const m = (w: number): Metric => ({ id: String(w), label: 'x', value: 1, delta: 0, windowSeconds: w })

describe('groupByWindow', () => {
  it('groups by window', () => expect(Object.keys(groupByWindow([m(60), m(300)]))).toHaveLength(2))
  it('keeps counts', () => expect(groupByWindow([m(60), m(60)])[60]).toHaveLength(2))
  it('handles empty input', () => expect(groupByWindow([])).toEqual({}))
  it('does not mutate input', () => {
    const arr = [m(60)]
    groupByWindow(arr)
    expect(arr).toHaveLength(1)
  })
  it('exposes fetchMetrics signature', () => expect(true).toBe(true))
})
`,
  'src/hooks/useMetrics.test.ts': `import { describe, it, expect } from 'vitest'
import { useMetrics } from './useMetrics'

describe('useMetrics', () => {
  it('is a function', () => expect(typeof useMetrics).toBe('function'))
  it('has stable name', () => expect(useMetrics.name).toBe('useMetrics'))
  it('accepts no args', () => expect(useMetrics.length).toBe(0))
  it('is defined', () => expect(useMetrics).toBeDefined())
})
`,
  'README.md': `# Pulseboard

Realtime ops dashboard. Vite + React 19 + strict TS.

- \`npm run dev\` — start dev server
- \`npm test\` — run the suite
- \`npm run build\` — typecheck + bundle
`,
}

const STORAGE_KEY = 'usman.vfs.v1';

export function loadVFS(): VFS {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as VFS;
  } catch { /* ignore */ }
  return { ...SEED };
}

export function saveVFS(vfs: VFS) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(vfs)); } catch { /* ignore */ }
}

export function resetVFS(): VFS {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  return { ...SEED };
}

/* ── real operations over the tree ── */

export const vfs = {
  list(v: VFS): string[] { return Object.keys(v).sort(); },
  read(v: VFS, path: string): string | undefined { return v[path]; },
  write(v: VFS, path: string, content: string): VFS {
    const next = { ...v, [path]: content };
    saveVFS(next);
    return next;
  },
  remove(v: VFS, path: string): VFS {
    const next = { ...v }; delete next[path]; saveVFS(next); return next;
  },
  grep(v: VFS, pattern: RegExp): Array<{ path: string; line: number; text: string }> {
    const hits: Array<{ path: string; line: number; text: string }> = [];
    for (const [path, content] of Object.entries(v)) {
      content.split('\n').forEach((text, i) => {
        if (pattern.test(text)) hits.push({ path, line: i + 1, text: text.trim() });
      });
    }
    return hits;
  },
  totalBytes(v: VFS): number {
    return Object.values(v).reduce((a, c) => a + new Blob([c]).size, 0);
  },
  totalLines(v: VFS): number {
    return Object.values(v).reduce((a, c) => a + c.split('\n').length, 0);
  },
};

export function lineOf(content: string, needle: string): number {
  const idx = content.indexOf(needle);
  if (idx < 0) return 1;
  return content.slice(0, idx).split('\n').length;
}

/* ── genuine static analysis ── */

export interface Diagnostic {
  file: string;
  line: number;
  code: string;
  message: string;
}

/** collect named exports of a module from its actual source */
function exportedNames(source: string): Set<string> {
  const names = new Set<string>();
  const re = /export\s+(?:async\s+)?(?:function|const|let|class|interface|type)\s+([A-Za-z0-9_]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source))) names.add(m[1]);
  if (/export\s+default/.test(source)) names.add('default');
  return names;
}

function resolvePath(fromFile: string, spec: string): string | undefined {
  const parts = fromFile.split('/'); parts.pop();
  for (const seg of spec.split('/')) {
    if (seg === '.') continue;
    if (seg === '..') parts.pop();
    else parts.push(seg);
  }
  const base = parts.join('/');
  const candidates = [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`];
  return candidates.find((c) => SEED_OR_LOADED.has(c));
}

// the checker always runs against the CURRENT tree
let SEED_OR_LOADED: Map<string, string> = new Map();

export function runStaticChecks(v: VFS): Diagnostic[] {
  SEED_OR_LOADED = new Map(Object.entries(v));
  const diags: Diagnostic[] = [];
  const pkg = v['package.json'] ? JSON.parse(v['package.json']) : { dependencies: {}, devDependencies: {} };
  const deps = new Set([...Object.keys(pkg.dependencies ?? {}), ...Object.keys(pkg.devDependencies ?? {})]);

  for (const [path, content] of Object.entries(v)) {
    if (!/\.(ts|tsx)$/.test(path) || path.endsWith('.d.ts')) continue;

    // 1 — imports: bare specifiers must exist in dependencies
    const importRe = /import\s+(?:([A-Za-z0-9_]+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from\s*['"]([^'"]+)['"]/g;
    let m: RegExpExecArray | null;
    while ((m = importRe.exec(content))) {
      const [, defaultName, namedRaw, spec] = m;
      if (!spec.startsWith('.')) {
        const pkgName = spec.startsWith('@') ? spec.split('/').slice(0, 2).join('/') : spec.split('/')[0];
        if (!deps.has(pkgName) && !['react', 'react-dom'].includes(pkgName) && !spec.startsWith('vitest')) {
          diags.push({
            file: path, line: lineOf(content, m[0]), code: 'TS2307',
            message: `Cannot find module '${spec}' or its corresponding type declarations.`,
          });
        }
        continue;
      }
      // 2 — named imports must exist in the target module's real exports
      const target = resolvePath(path, spec);
      if (!target) {
        diags.push({ file: path, line: lineOf(content, m[0]), code: 'TS2307', message: `Cannot find module '${spec}'.` });
        continue;
      }
      const targetSource = v[target];
      const exported = exportedNames(targetSource ?? '');
      const named = (namedRaw ?? '').split(',').map((s) => s.trim()).filter(Boolean);
      for (const n of named) {
        const name = n.split(/\s+as\s+/)[0].trim();
        if (name && !exported.has(name)) {
          diags.push({
            file: path, line: lineOf(content, m[0]), code: 'TS2305',
            message: `Module '"${spec}"' has no exported member '${name}'.`,
          });
        }
      }
      if (defaultName && !exported.has('default') && namedRaw !== undefined && !/^\s*\{/.test(m[0].replace('import', '').trim())) {
        /* default import against module without default — rare in seed, skip */
      }
    }

    // 3 — declared string return type with an arithmetic (non-string) return expression
    const fnRe = /(?:export\s+)?function\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*:\s*string\s*\{[^}]*?return\s+([^;\n}]+)/gs;
    while ((m = fnRe.exec(content))) {
      const expr = m[2].trim();
      const looksNumeric = /^[A-Za-z0-9_.()\s]*[*/+-][A-Za-z0-9_.()\s]*$/.test(expr) && !/['"`]/.test(expr) && !/\.(toFixed|toString|replace|join|slice)\(/.test(expr);
      if (looksNumeric) {
        diags.push({
          file: path, line: lineOf(content, m[0]), code: 'TS2322',
          message: `Type 'number' is not assignable to type 'string'. — ${m[1]}() returns \`${expr}\``,
        });
      }
    }
  }
  return diags;
}

/** discover test suites + count real `it(` blocks */
export function discoverTests(v: VFS): Array<{ path: string; cases: number; imports: string[] }> {
  const suites: Array<{ path: string; cases: number; imports: string[] }> = [];
  for (const [path, content] of Object.entries(v)) {
    if (!/\.test\.tsx?$/.test(path)) continue;
    const cases = (content.match(/\bit\(/g) || []).length;
    const imports = [...content.matchAll(/from\s+['"](\.[^'"]+)['"]/g)].map((m) => m[1]);
    suites.push({ path, cases, imports });
  }
  return suites.sort((a, b) => a.path.localeCompare(b.path));
}
