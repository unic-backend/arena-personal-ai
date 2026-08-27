/* ─────────────────────────────────────────────────────────────
   Real executors — these genuinely run things.
   · calc: shunting-yard expression evaluator (no eval)
   · runJavaScript: sandboxed execution with captured console
   · shell: a mini POSIX-ish shell over the virtual filesystem
   ───────────────────────────────────────────────────────────── */

import { runStaticChecks, discoverTests, vfs as vfsOps, VFS } from './vfs';

/* ─────────── calculator ─────────── */

export function calc(input: string): { value: number; pretty: string } {
  const expr = input.replace(/×/g, '*').replace(/÷/g, '/').replace(/,/g, '');
  const tokens = expr.match(/(\d+\.?\d*)|([+\-*/%^()])|(pi\b)|(\be\b)/gi);
  if (!tokens || tokens.join(' ').replace(/\s/g, '') !== expr.replace(/\s/g, '')) {
    throw new Error(`Could not parse expression: "${input}"`);
  }
  const out: (number | string)[] = [];
  const ops: string[] = [];
  const prec: Record<string, number> = { '+': 1, '-': 1, '*': 2, '/': 2, '%': 2, '^': 3, u: 4 };
  let prev: string | null = null;
  for (let tok of tokens) {
    if (/^(pi|\be\b)$/i.test(tok)) tok = tok.toLowerCase() === 'pi' ? String(Math.PI) : String(Math.E);
    if (/^\d/.test(tok)) out.push(parseFloat(tok));
    else if (tok === '(') ops.push(tok);
    else if (tok === ')') {
      while (ops.length && ops[ops.length - 1] !== '(') out.push(ops.pop()!);
      if (!ops.length) throw new Error('Mismatched parentheses');
      ops.pop();
    } else {
      let op = tok;
      if ((tok === '-' || tok === '+') && (prev === null || /[+\-*/%^()]/.test(prev))) {
        if (tok === '+') { prev = tok; continue; }
        op = 'u';
      }
      while (ops.length) {
        const top = ops[ops.length - 1];
        if (top === '(') break;
        if (prec[top] > prec[op] || (prec[top] === prec[op] && op !== '^' && op !== 'u')) out.push(ops.pop()!);
        else break;
      }
      ops.push(op);
    }
    prev = tok;
  }
  while (ops.length) {
    const op = ops.pop()!;
    if (op === '(') throw new Error('Mismatched parentheses');
    out.push(op);
  }
  const st: number[] = [];
  for (const t of out) {
    if (typeof t === 'number') st.push(t);
    else if (t === 'u') st.push(-st.pop()!);
    else {
      const b = st.pop()!, a = st.pop()!;
      st.push(t === '+' ? a + b : t === '-' ? a - b : t === '*' ? a * b : t === '/' ? a / b : t === '%' ? a % b : Math.pow(a, b));
    }
  }
  if (st.length !== 1 || !isFinite(st[0])) throw new Error('Invalid expression');
  const value = st[0];
  const pretty = Math.abs(value) >= 1e15 || (Math.abs(value) < 1e-9 && value !== 0)
    ? value.toExponential(6).replace(/\.?0+e/, 'e')
    : String(Math.round(value * 1e10) / 1e10);
  return { value, pretty };
}

/* ─────────── javascript sandbox ─────────── */

export interface RunResult {
  ok: boolean;
  lines: Array<{ level: 'log' | 'warn' | 'error'; text: string }>;
  error?: string;
  durationMs: number;
}

export function runJavaScript(code: string): RunResult {
  const lines: RunResult['lines'] = [];
  const MAX_LOG_LINES = 100;
  const MAX_LINE_LENGTH = 2000;

  const fmt = (v: unknown): string => {
    if (typeof v === 'string') return v.slice(0, MAX_LINE_LENGTH);
    if (v instanceof Error) return `${v.name}: ${v.message}`.slice(0, MAX_LINE_LENGTH);
    try {
      return (JSON.stringify(v) ?? String(v)).slice(0, MAX_LINE_LENGTH);
    } catch {
      return String(v).slice(0, MAX_LINE_LENGTH);
    }
  };

  const pushLine = (level: 'log' | 'warn' | 'error', a: unknown[]) => {
    if (lines.length >= MAX_LOG_LINES) return;
    lines.push({ level, text: a.map(fmt).join(' ') });
    if (lines.length === MAX_LOG_LINES) {
      lines.push({ level: 'warn', text: '[Output truncated: maximum 100 lines reached]' });
    }
  };

  const fakeConsole = Object.freeze({
    log: (...a: unknown[]) => pushLine('log', a),
    warn: (...a: unknown[]) => pushLine('warn', a),
    error: (...a: unknown[]) => pushLine('error', a),
    info: (...a: unknown[]) => pushLine('log', a),
    table: (v: unknown) => pushLine('log', [v]),
  });

  const t0 = performance.now();
  try {
    // Blocklist ambient browser, storage, network, and execution APIs for a secure deterministic sandbox
    const blockedGlobals = [
      'console',
      'window',
      'document',
      'fetch',
      'localStorage',
      'sessionStorage',
      'indexedDB',
      'XMLHttpRequest',
      'WebSocket',
      'Worker',
      'SharedWorker',
      'ServiceWorker',
      'navigator',
      'location',
      'history',
      'open',
      'close',
      'alert',
      'confirm',
      'prompt',
      'parent',
      'top',
      'frames',
      'self',
      'globalThis',
      'setTimeout',
      'setInterval',
      'setImmediate',
      'requestAnimationFrame',
      'eval',
      'Function',
    ];

    const fn = new Function(
      ...blockedGlobals,
      `"use strict";\n${code}`,
    );

    // Call sandbox with fakeConsole for 'console' and undefined for all dangerous globals
    fn(fakeConsole, ...new Array(blockedGlobals.length - 1).fill(undefined));

    return { ok: true, lines, durationMs: performance.now() - t0 };
  } catch (err) {
    return {
      ok: false,
      lines,
      durationMs: performance.now() - t0,
      error: err instanceof Error ? `${err.name}: ${err.message}` : String(err),
    };
  }
}

/** very small TS → JS for the code runner (types stripped, interfaces dropped) */
export function transpileLite(src: string): string {
  return src
    .replace(/^[^\n]*interface\s+\w+[^}]*}\s*$/gm, '')
    .replace(/:\s*(string|number|boolean|any|void|unknown|never|string\[\]|number\[\]|[A-Z]\w*(<[^>]+>)?(\[\])?)\b(?=\s*[,)=;{])/g, '')
    .replace(/\b(const|let|var)\s+(\w+)\s*:\s*[^=;]+=/g, '$1 $2 =')
    .replace(/<([A-Z][\w]*)>(?=\()/g, '')
    .replace(/\bas\s+[A-Z]\w*\b/g, '');
}

/* ─────────── mini shell over the VFS ─────────── */

export interface ShellResult {
  ok: boolean;
  exitCode: number;
  stdout: string[];
  stderr?: string;
  diagnostics?: ReturnType<typeof runStaticChecks>;
  testTotals?: { passed: number; failed: number; total: number; suites: Array<{ path: string; cases: number; ok: boolean }> };
}

export function runShell(v: VFS, cmd: string): ShellResult {
  const parts = cmd.trim().split(/\s+/);
  const [bin, ...args] = parts;

  if (bin === 'echo') return { ok: true, exitCode: 0, stdout: [args.join(' ')] };

  if (bin === 'ls') {
    const target = args.find((a) => !a.startsWith('-')) ?? '';
    const prefix = target ? target.replace(/\/$/, '') + '/' : '';
    const entries = new Set<string>();
    for (const p of vfsOps.list(v)) {
      if (!p.startsWith(prefix)) continue;
      const rest = p.slice(prefix.length);
      entries.add(rest.includes('/') ? rest.split('/')[0] + '/' : rest);
    }
    const list = [...entries].sort();
    return { ok: true, exitCode: 0, stdout: list.length ? list : [`ls: ${target || '.'}: no such file or directory`] };
  }

  if (bin === 'cat' || bin === 'head' || bin === 'tail') {
    const file = vfsOps.read(v, args[0] ?? '');
    if (file === undefined) return { ok: false, exitCode: 1, stdout: [], stderr: `${bin}: ${args[0]}: No such file or directory` };
    const lines = file.split('\n');
    const slice = bin === 'head' ? lines.slice(0, 10) : bin === 'tail' ? lines.slice(-10) : lines;
    return { ok: true, exitCode: 0, stdout: slice };
  }

  if (bin === 'wc' && args[0] === '-l') {
    const file = vfsOps.read(v, args[1] ?? '');
    if (file === undefined) return { ok: false, exitCode: 1, stdout: [], stderr: `wc: ${args[1]}: No such file or directory` };
    return { ok: true, exitCode: 0, stdout: [`${file.split('\n').length} ${args[1]}`] };
  }

  if (bin === 'grep' && args.length >= 2) {
    const pat = new RegExp(args[0].replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const hits = vfsOps.grep(v, pat).filter((h) => h.path.includes(args[1].replace(/\//g, '/')));
    return { ok: hits.length > 0, exitCode: hits.length ? 0 : 1, stdout: hits.map((h) => `${h.path}:${h.line}: ${h.text}`) };
  }

  if (bin === 'npm') {
    const sub = args.join(' ');
    if (sub === 'run build' || sub === 'run typecheck') {
      const diagnostics = runStaticChecks(v);
      if (diagnostics.length) {
        return {
          ok: false, exitCode: 2,
          stdout: ['> pulseboard@0.4.2 build', '> tsc -b && vite build', ''],
          stderr: [
            ...diagnostics.map((d) => `${d.file}(${d.line},1): error ${d.code}: ${d.message}`),
            '',
            `Found ${diagnostics.length} error${diagnostics.length > 1 ? 's' : ''}.`,
          ].join('\n'),
          diagnostics,
        };
      }
      const bytes = vfsOps.totalBytes(v);
      const kb = (n: number) => (n / 1024).toFixed(2);
      return {
        ok: true, exitCode: 0,
        stdout: [
          '> pulseboard@0.4.2 build', '> tsc -b && vite build', '',
          'vite v6.3.5 building for production...',
          `transforming... ${vfsOps.list(v).filter((p) => /\.tsx?$/.test(p)).length} modules transformed.`,
          'rendering chunks...',
          'dist/index.html                   0.46 kB │ gzip:  0.29 kB',
          `dist/assets/index-Bf2kQ9.css     ${kb(Math.min(bytes * 0.09, 42_000))} kB │ gzip:  ${kb(Math.min(bytes * 0.021, 9_000))} kB`,
          `dist/assets/index-P1mV4x.js     ${kb(Math.max(bytes * 0.62, 48_000))} kB │ gzip: ${kb(Math.max(bytes * 0.19, 16_000))} kB`,
          '',
          `✓ built in ${(1.1 + bytes / 90_000).toFixed(2)}s`,
        ],
      };
    }
    if (sub === 'test' || sub === 'run test' || sub === 't') {
      const suites = discoverTests(v);
      const diags = runStaticChecks(v);
      const broken = new Set(diags.map((d) => d.file));
      let passed = 0, failed = 0;
      const lines: string[] = ['> pulseboard@0.4.2 test', '> vitest run', ''];
      const suiteResults: Array<{ path: string; cases: number; ok: boolean }> = [];
      for (const s of suites) {
        // a suite fails when the module under test (or itself) has diagnostics
        const ownerGuesses = [s.path.replace(/\.test\.tsx?$/, '.ts'), s.path.replace(/\.test\.tsx?$/, '.tsx')];
        const isBroken = broken.has(s.path) || ownerGuesses.some((g) => broken.has(g))
          || s.imports.some((imp) => {
            const base = s.path.split('/').slice(0, -1).join('/');
            const full = imp.split('/').reduce<string[]>((acc, seg) => seg === '..' ? acc.slice(0, -1) : seg === '.' ? acc : [...acc, seg], base.split('/')).join('/');
            return [full, `${full}.ts`, `${full}.tsx`].some((c) => broken.has(c));
          });
        const failsHere = isBroken ? Math.min(2, s.cases) : 0;
        failed += failsHere; passed += s.cases - failsHere;
        suiteResults.push({ path: s.path, cases: s.cases, ok: !isBroken });
        lines.push(`${isBroken ? '✗' : '✓'} ${s.path} (${s.cases} tests${isBroken ? `, ${failsHere} failed` : ''})`);
      }
      const brokenSuites = suiteResults.filter((s) => !s.ok).length;
      lines.push('', `Test Files  ${failed ? `${brokenSuites} failed | ` : ''}${suites.length} total`);
      lines.push(`     Tests  ${failed ? `${failed} failed | ` : ''}${passed} passed (${passed + failed})`);
      const testTotals = { passed, failed, total: passed + failed, suites: suiteResults };
      return failed
        ? { ok: false, exitCode: 1, stdout: lines, stderr: `${failed} test${failed > 1 ? 's' : ''} failed`, diagnostics: diags, testTotals }
        : { ok: true, exitCode: 0, stdout: lines, testTotals };
    }
    if (sub === 'run lint') {
      const todos = vfsOps.grep(v, /TODO|FIXME/).length;
      return { ok: true, exitCode: 0, stdout: [`eslint: scanned ${vfsOps.list(v).filter((p) => /\.tsx?$/.test(p)).length} files`, todos ? `${todos} warnings (TODO/FIXME comments)` : 'no problems found'] };
    }
    return { ok: false, exitCode: 1, stdout: [], stderr: `npm error: Missing script: "${args.slice(1).join(' ') || args[0]}"` };
  }

  return { ok: false, exitCode: 127, stdout: [], stderr: `sh: command not found: ${bin}` };
}

export const SUPPORTED_LANGUAGES = [
  { id: 'javascript', label: 'JavaScript', runner: true },
  { id: 'typescript', label: 'TypeScript', runner: true },
  { id: 'shell', label: 'Shell', runner: true },
] as const;
