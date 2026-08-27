/* ─────────────────────────────────────────────────────────────
   Agent Orchestrator — the backend.

   Receives a user request, detects its language, plans an
   execution pipeline, runs the real tools (VFS, shell, search
   index, executors) and emits a typed activity-event stream plus
   the final token stream — in the user's language.

   The frontend never invents a step: every rendered activity
   corresponds to an event yielded here.
   ───────────────────────────────────────────────────────────── */

import type {
  ActivityEvent, StreamChunk, SourceMeta, FileOpMeta,
} from '../activity/types';
import {
  VFS, vfs as vfsOps, discoverTests, Diagnostic,
} from './vfs';
import { searchCorpus, RankedDoc } from './knowledge';
import { CORPUS_FR } from './knowledgeFr';
import { calc, runJavaScript, runShell, transpileLite, SUPPORTED_LANGUAGES } from './exec';
import { agentStrings, AgentDict, FixFacts } from './strings';
import { detectLanguage, uiLocale, Lang } from '../i18n';
import {
  AttachedVideo, probeVideo, extractThumbnails, trimVideo, trimSupported,
  parseTrimRange, fmtTime, fmtBytes, VideoMeta,
} from './video';
import {
  PendingAttachment, prepareAttachment, summarizeAttachment,
} from '../attachments';
import { usePersona } from '../store/personaStore';

export interface AgentContext {
  getTree(): VFS;
  setTree(v: VFS): void;
}

/* ── primitives ── */

let _seq = 0;
const uid = () => `ev_${Date.now().toString(36)}_${(++_seq).toString(36)}`;
const beat = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const rnd = (a: number, b: number) => a + Math.random() * (b - a);

function assertLive(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('The run was cancelled', 'AbortError');
}

type Evt = Omit<ActivityEvent, 'id' | 'startedAt' | 'phase' | 'status'> & {
  status?: ActivityEvent['status'];
  phase?: ActivityEvent['phase'];
};

function* evStart(p: Evt): Generator<StreamChunk, ActivityEvent> {
  const ev: ActivityEvent = {
    id: uid(), startedAt: Date.now(), phase: 'started', status: 'running', ...p,
  };
  yield { type: 'activity', event: ev };
  return ev;
}

function* evPatch(
  ev: ActivityEvent,
  patch: Partial<ActivityEvent>,
): Generator<StreamChunk, ActivityEvent> {
  const merged: ActivityEvent = {
    ...ev, ...patch, id: ev.id, startedAt: ev.startedAt,
  };
  const terminal = ['completed', 'failed', 'cancelled'].includes(merged.status);
  if (terminal && !merged.completedAt) {
    merged.completedAt = Date.now();
    merged.durationMs = merged.completedAt - merged.startedAt;
  }
  yield { type: 'activity', event: merged };
  return merged;
}

const evDone = (ev: ActivityEvent, patch: Partial<ActivityEvent> = {}) =>
  evPatch(ev, { phase: 'completed', status: 'completed', ...patch });

const evFail = (ev: ActivityEvent, patch: Partial<ActivityEvent> = {}) =>
  evPatch(ev, { phase: 'failed', status: 'failed', ...patch });

/** thinking step — high-level summaries only, never private reasoning */
async function* think(
  title: string, description: string | undefined, signal: AbortSignal | undefined,
  workMs: number = rnd(420, 900),
): AsyncGenerator<StreamChunk, ActivityEvent> {
  const ev = yield* evStart({ kind: 'thinking', title, description });
  await beat(workMs);
  assertLive(signal);
  return yield* evDone(ev);
}

/** stream the composed answer word-by-word as it is produced */
async function* streamText(text: string, signal?: AbortSignal): AsyncGenerator<StreamChunk> {
  const words = text.split(/(?<=\s)/);
  const long = text.length > 1200;
  let buf = '';
  let n = 0;
  for (const w of words) {
    buf += w;
    if (++n % 2 === 0) {
      yield { type: 'token', text: buf };
      buf = '';
      if (n % 4 === 0) {
        await beat(long ? rnd(8, 16) : rnd(14, 30));
        assertLive(signal);
      }
    }
  }
  if (buf) yield { type: 'token', text: buf };
}

/* ── diff helper for honest add/remove counts ── */
function diffStat(before: string, after: string): { added: number; removed: number } {
  const a = before.split('\n');
  const b = after.split('\n');
  let added = 0, removed = 0;
  for (const line of a) if (!b.includes(line)) removed++;
  for (const line of b) if (!a.includes(line)) added++;
  return { added, removed };
}

/** corpus content in the conversation language */
function localized(doc: RankedDoc | undefined, lang: Lang): { excerpt: string; body: string[] } {
  if (!doc) return { excerpt: '', body: [] };
  if (lang === 'fr') {
    const fr = CORPUS_FR[doc.id];
    if (fr) return fr;
  }
  return { excerpt: doc.excerpt, body: doc.body };
}

/* ═══════════════════ PIPELINE: analyze project & fix build ═══════════════════ */

async function* pipelineFixBuild(
  ctx: AgentContext, signal: AbortSignal, d: AgentDict,
): AsyncGenerator<StreamChunk, { sources?: SourceMeta[] }> {
  yield* think(d.think.analyzing, d.think.understanding, signal);
  const plan = yield* evStart({
    kind: 'planning', title: d.think.planning,
    description: d.think.planDesc,
    metadata: { steps: d.planSteps },
  });
  await beat(rnd(300, 500));
  assertLive(signal);
  yield* evDone(plan);

  /* ── 1 · inspect repository (real walk with real progress numbers) ── */
  const scan = yield* evStart({
    kind: 'tool', tool: 'vfs_scan', title: d.fix.scan,
    description: d.fix.walk,
  });
  let tree = ctx.getTree();
  const files = vfsOps.list(tree);
  for (let i = 0; i < files.length; i += 2) {
    await beat(rnd(28, 60));
    assertLive(signal);
    yield* evPatch(scan, {
      phase: 'progress',
      description: d.fix.scanFile(files[Math.min(i + 1, files.length - 1)]!),
      progress: { done: Math.min(i + 2, files.length), total: files.length, unit: d.units.files },
    });
  }
  const tsFiles = files.filter((f) => /\.tsx?$/.test(f)).length;
  yield* evDone(scan, {
    description: d.fix.scanDone(files.length, vfsOps.totalLines(tree).toLocaleString()),
    output: { files: files.length, tsFiles, lines: vfsOps.totalLines(tree), bytes: vfsOps.totalBytes(tree) },
    progress: { done: files.length, total: files.length, unit: d.units.files },
  });

  /* ── 2 · dependencies ── */
  const deps = yield* evStart({ kind: 'tool', tool: 'file_reader', title: d.fix.deps });
  await beat(rnd(240, 420));
  const pkgRaw = vfsOps.read(tree, 'package.json') ?? '{}';
  const pkg = JSON.parse(pkgRaw);
  const depCount = Object.keys(pkg.dependencies ?? {}).length + Object.keys(pkg.devDependencies ?? {}).length;
  const readPkg = yield* evStart({
    kind: 'file', tool: 'file_reader', parentId: deps.id, title: 'package.json',
    description: d.fix.parseManifest,
    metadata: { op: 'read', path: 'package.json', bytes: pkgRaw.length } satisfies FileOpMeta & Record<string, unknown>,
  });
  await beat(rnd(160, 260));
  yield* evDone(readPkg, { description: d.fix.depsDeclared(depCount) });
  const cfgRaw = vfsOps.read(tree, 'tsconfig.json') ?? '{}';
  const readCfg = yield* evStart({
    kind: 'file', tool: 'file_reader', parentId: deps.id, title: 'tsconfig.json',
    metadata: { op: 'parse', path: 'tsconfig.json' } satisfies FileOpMeta & Record<string, unknown>,
  });
  await beat(rnd(140, 220));
  const strict = /"strict"\s*:\s*true/.test(cfgRaw);
  yield* evDone(readCfg, { description: strict ? d.fix.strictOn : d.fix.strictOff });
  yield* evDone(deps, {
    description: d.fix.depsDone(depCount),
    output: { dependencies: depCount, strict },
  });

  /* ── 3 · first build ── */
  const build1 = yield* evStart({
    kind: 'terminal', tool: 'terminal', title: d.fix.buildRun,
    input: { command: 'npm run build' },
    description: d.fix.buildDesc,
  });
  await beat(rnd(650, 950));
  assertLive(signal);
  const r1 = runShell(tree, 'npm run build');

  if (!r1.ok) {
    yield* evFail(build1, {
      description: d.fix.buildExit(r1.exitCode),
      output: { command: 'npm run build', stdout: r1.stdout, stderr: r1.stderr, exitCode: r1.exitCode, diagnostics: r1.diagnostics },
    });
  } else {
    yield* evDone(build1, {
      description: `${d.fix.exitOk} · ${r1.stdout[r1.stdout.length - 1]}`,
      output: { command: 'npm run build', stdout: r1.stdout, exitCode: 0 },
    });
  }

  const diags: Diagnostic[] = r1.diagnostics ?? [];
  const fixedFiles: Array<{ path: string; summary: string; added: number; removed: number }> = [];

  if (diags.length) {
    /* ── 4 · investigate ── */
    const inv = yield* evStart({
      kind: 'analysis', tool: 'analysis', title: d.fix.investigate,
      description: d.fix.invDesc,
    });
    await beat(rnd(500, 800));
    assertLive(signal);
    const affected = [...new Set(diags.map((x) => x.file))];
    yield* evDone(inv, {
      description: d.fix.invDone(diags.length, affected.length),
      output: { diagnostics: diags, files: affected },
    });

    /* ── 5 · apply real fixes ── */
    const edit = yield* evStart({
      kind: 'tool', tool: 'file_editor', title: d.fix.editing,
      description: d.fix.editDesc,
    });
    for (const diag of diags) {
      assertLive(signal);
      let target = diag.file;
      let before: string | undefined;
      let after: string | undefined;
      let summary = '';

      if (diag.code === 'TS2307' && /date-fns/.test(diag.message)) {
        target = 'package.json';
        before = vfsOps.read(tree, target);
        if (before) {
          const p = JSON.parse(before);
          p.dependencies = { ...p.dependencies, 'date-fns': '^4.1.0' };
          after = JSON.stringify(p, null, 2) + '\n';
          summary = d.fix.fixDep;
        }
      } else if (diag.code === 'TS2322') {
        before = vfsOps.read(tree, target);
        if (before && /return seconds \* 1000/.test(before)) {
          after = before.replace(
            /export function formatDuration\(seconds: number\): string \{\s*return seconds \* 1000\s*\}/,
            `export function formatDuration(seconds: number): string {
  if (seconds < 60) return \`\${seconds}s\`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return \`\${m}m \${String(s).padStart(2, '0')}s\`
  const h = Math.floor(m / 60)
  return \`\${h}h \${String(m % 60).padStart(2, '0')}m\`
}`,
          );
          summary = d.fix.fixRet;
        }
      } else if (diag.code === 'TS2305') {
        const member = /member '(\w+)'/.exec(diag.message)?.[1];
        before = vfsOps.read(tree, target);
        if (before && member === 'cns') {
          after = before.replace(/\bcns\b/g, 'cn');
          summary = d.fix.fixRename(member);
        }
      }

      if (before !== undefined && after !== undefined && after !== before) {
        const stat = diffStat(before, after);
        const f = yield* evStart({
          kind: 'file', tool: 'file_editor', parentId: edit.id, title: target,
          description: summary,
          metadata: { op: 'edit', path: target, ...stat } satisfies FileOpMeta & Record<string, unknown>,
        });
        await beat(rnd(300, 520));
        const written = vfsOps.write(tree, target, after);
        ctx.setTree(written);
        tree = written;
        yield* evDone(f, { description: summary, metadata: { op: 'edit', path: target, ...stat } });
        if (!fixedFiles.some((x) => x.path === target)) {
          fixedFiles.push({ path: target, summary, ...stat });
        }
      } else {
        const f = yield* evStart({
          kind: 'file', tool: 'file_editor', parentId: edit.id, title: target,
          description: d.fix.manual,
        });
        await beat(220);
        yield* evDone(f);
      }
    }
    yield* evDone(edit, {
      description: d.fix.filesModified(new Set(fixedFiles.map((f) => f.path)).size),
      output: { files: fixedFiles },
    });
  }

  /* ── 6 · tests (real discovery, per-suite progress) ── */
  const testCmd = yield* evStart({
    kind: 'terminal', tool: 'terminal', title: d.fix.tests,
    input: { command: 'npm test' },
    description: d.fix.testsDiscover,
  });
  const suites = discoverTests(ctx.getTree());
  const totalCases = suites.reduce((a, s) => a + s.cases, 0);
  for (let i = 0; i < suites.length; i++) {
    await beat(rnd(120, 220));
    assertLive(signal);
    const doneCases = suites.slice(0, i + 1).reduce((a, s) => a + s.cases, 0);
    yield* evPatch(testCmd, {
      phase: 'progress',
      description: d.fix.testsRun(suites[i]!.path),
      progress: { done: doneCases, total: totalCases, unit: d.units.tests },
    });
  }
  const rt = runShell(ctx.getTree(), 'npm test');
  const totals = rt.testTotals ?? { passed: rt.ok ? totalCases : 0, failed: rt.ok ? 0 : totalCases, total: totalCases, suites: [] };
  yield* (rt.ok ? evDone : evFail)(testCmd, {
    description: rt.ok ? d.fix.testsDone(totals.passed, suites.length) : (rt.stderr ?? d.fix.testFailed),
    output: {
      command: 'npm test', stdout: rt.stdout, exitCode: rt.exitCode,
      suites: totals.suites,
      totals: { passed: totals.passed, failed: totals.failed, total: totals.total },
    },
    progress: { done: totalCases, total: totalCases, unit: d.units.tests },
  });

  /* ── 7 · rebuild (only if we changed something) ── */
  let buildLine = 'build already green';
  if (fixedFiles.length > 0) {
    const build2 = yield* evStart({
      kind: 'terminal', tool: 'terminal', title: d.fix.rebuild,
      input: { command: 'npm run build' },
      description: d.fix.rebuildDesc,
    });
    await beat(rnd(750, 1100));
    const r2 = runShell(ctx.getTree(), 'npm run build');
    buildLine = r2.stdout[r2.stdout.length - 1] ?? 'build finished';
    yield* (r2.ok ? evDone : evFail)(build2, {
      description: r2.ok ? `${d.fix.exitOk} · ${buildLine}` : d.fix.buildExit(r2.exitCode),
      output: { command: 'npm run build', stdout: r2.stdout, stderr: r2.stderr, exitCode: r2.exitCode },
    });
  }

  yield* think(d.think.preparing, d.think.organizing, signal, rnd(380, 620));

  /* ── compose the answer from recorded facts ── */
  const facts: FixFacts = {
    diagCount: diags.length,
    fileCount: new Set(diags.map((x) => x.file)).size,
    diags: diags.map((x) => ({ file: x.file, line: x.line, code: x.code, message: x.message })),
    fixedFiles,
    testPassed: totals.passed,
    testTotal: totals.total,
    suites: suites.length,
    buildLine,
    files: files.length,
    lines: vfsOps.totalLines(ctx.getTree()).toLocaleString(),
    depCount,
  };
  yield* streamText(fixedFiles.length ? d.fixAnswer(facts) : d.fixGreenAnswer(facts), signal);
  return {};
}

/* ═══════════════════ PIPELINE: web research ═══════════════════ */

async function* pipelineResearch(
  query: string, signal: AbortSignal, d: AgentDict, lang: Lang,
): AsyncGenerator<StreamChunk, { sources?: SourceMeta[] }> {
  yield* think(d.think.analyzing, d.research.identify(query), signal);

  const search = yield* evStart({
    kind: 'search', tool: 'web_search', title: d.research.searching,
    input: { query },
    description: d.research.searchingDesc(query),
  });
  await beat(rnd(480, 760));
  assertLive(signal);
  yield* evPatch(search, { phase: 'progress', description: d.research.querying });
  await beat(rnd(320, 520));
  const ranked = searchCorpus(query);
  yield* evDone(search, {
    description: d.research.found(ranked.length),
    output: {
      query, result_count: ranked.length,
      results: ranked.slice(0, 8).map((r) => ({ title: r.title, domain: r.domain, date: r.date })),
    },
  });

  const top = ranked.slice(0, Math.min(5, ranked.length));
  if (!top.length) {
    yield* think(d.think.preparingShort, undefined, signal, 320);
    yield* streamText(d.research.none(query), signal);
    return { sources: [] };
  }

  const browse = yield* evStart({
    kind: 'tool', tool: 'browser', title: d.research.reading,
    description: d.research.opening,
  });
  const opened: RankedDoc[] = [];
  for (const doc of top) {
    assertLive(signal);
    const s = yield* evStart({
      kind: 'browser', tool: 'browser', parentId: browse.id,
      title: doc.domain, description: doc.title,
      input: { url: doc.url },
      metadata: { source: doc satisfies SourceMeta },
    });
    await beat(rnd(280, 520));
    yield* evDone(s, { description: doc.title });
    opened.push(doc);
    yield* evPatch(browse, {
      phase: 'progress',
      description: d.research.openedProg(opened.length, top.length),
      progress: { done: opened.length, total: top.length, unit: d.units.sources },
    });
  }
  yield* evDone(browse, {
    description: d.research.openedDone(opened.length),
    output: { sources: opened.map((x) => ({ title: x.title, domain: x.domain, date: x.date })) },
  });

  const compare = yield* evStart({
    kind: 'analysis', tool: 'analysis', title: d.research.comparing,
    description: d.research.comparingDesc,
  });
  await beat(rnd(550, 850));
  assertLive(signal);
  const first = opened[0]!;
  const range = `${opened[opened.length - 1]!.date} – ${first.date}`;
  yield* evDone(compare, { description: d.research.compared(opened.length, range) });

  yield* think(d.think.preparingShort, d.think.synthesizing, signal, rnd(420, 700));

  const lead = localized(first, lang);
  const facts: string[] = [];
  opened.forEach((doc, i) => localized(doc, lang).body.slice(0, 2).forEach((b) => facts.push(`${b} [${i + 1}]`)));
  const closing = localized(opened[1] ?? first, lang).excerpt.replace(/\.$/, '').toLowerCase();
  const doms = opened.map((x) => x.domain.replace(/\..*$/, '')).slice(0, 3).join(', ') + (opened.length > 3 ? ', …' : '');
  const text = [
    d.research.heresWhat(query),
    '',
    `> ${lead.excerpt} [1]`,
    '',
    d.research.keyFindings,
    ...facts.slice(0, 6).map((f) => `- ${f}`),
    '',
    d.research.across(opened.length, doms, closing),
  ].join('\n');
  yield* streamText(text, signal);
  return { sources: opened.map(({ title, domain, url, date, excerpt }) => ({ title, domain, url, date, excerpt })) };
}

/* ═══════════════════ PIPELINE: calculator ═══════════════════ */

async function* pipelineCalc(
  expr: string, signal: AbortSignal, d: AgentDict,
): AsyncGenerator<StreamChunk, Record<string, never>> {
  const tool = yield* evStart({
    kind: 'calculation', tool: 'calculator', title: d.calc.title,
    input: { expression: expr },
    description: d.calc.desc,
  });
  await beat(rnd(220, 420));
  let result: ReturnType<typeof calc> | undefined;
  let err: string | undefined;
  try { result = calc(expr); } catch (e) { err = e instanceof Error ? e.message : String(e); }
  assertLive(signal);
  if (result) {
    yield* evDone(tool, {
      description: `${expr} = ${result.pretty}`,
      output: { expression: expr, result: result.pretty },
    });
    yield* think(d.think.preparingShort, undefined, signal, rnd(220, 380));
    yield* streamText(d.calc.answer(expr, result.pretty), signal);
  } else {
    yield* evFail(tool, { title: d.calc.failTitle, description: err });
    yield* think(d.think.preparingShort, undefined, signal, 240);
    yield* streamText(d.calc.fail(expr, err ?? ''), signal);
  }
  return {};
}

/* ═══════════════════ PIPELINE: code execution ═══════════════════ */

async function* pipelineCode(
  lang: string, code: string, signal: AbortSignal, d: AgentDict,
): AsyncGenerator<StreamChunk, Record<string, never>> {
  const supported = SUPPORTED_LANGUAGES.some((l) => l.id === lang);
  const exec = yield* evStart({
    kind: 'code', tool: 'code_runner', title: d.code.title,
    input: { language: lang, code },
    description: supported
      ? d.code.running(SUPPORTED_LANGUAGES.find((l) => l.id === lang)!.label)
      : d.code.noRunner(lang),
  });
  await beat(rnd(280, 520));
  if (!supported) {
    yield* evFail(exec, {
      title: d.code.failTitle,
      description: d.code.noRunnerDesc(lang, SUPPORTED_LANGUAGES.map((l) => l.id).join(', ')),
    });
    yield* think(d.think.preparingShort, undefined, signal, 260);
    yield* streamText(
      d.code.noRunnerAnswer(SUPPORTED_LANGUAGES.map((l) => l.label).join(', '), lang),
      signal,
    );
    return {};
  }
  assertLive(signal);
  const js = lang === 'typescript' ? transpileLite(code) : code;
  const out = runJavaScript(js);
  const ms = out.durationMs.toFixed(1);
  yield* (out.ok ? evDone : evFail)(exec, {
    title: out.ok ? d.code.title : d.code.failTitle,
    description: out.ok ? d.code.doneDesc(out.lines.length, ms) : out.error,
    output: { language: lang, code, stdout: out.lines, error: out.error, durationMs: out.durationMs },
  });
  yield* think(d.think.preparingShort, undefined, signal, rnd(260, 420));
  const label = lang === 'typescript' ? 'TypeScript' : lang === 'shell' ? 'Shell' : 'JavaScript';
  const text = out.ok
    ? d.code.okAnswer(label, out.lines.length, ms, out.lines.map((l) => l.text))
    : d.code.errAnswer(out.error ?? 'Error', out.lines.map((l) => l.text));
  yield* streamText(text, signal);
  return {};
}

/* ═══════════════════ PIPELINE: terminal command ═══════════════════ */

async function* pipelineCommand(
  command: string, ctx: AgentContext, signal: AbortSignal, d: AgentDict,
): AsyncGenerator<StreamChunk, Record<string, never>> {
  const term = yield* evStart({
    kind: 'terminal', tool: 'terminal', title: d.command.title,
    input: { command },
    description: d.command.desc,
    metadata: { retryable: true },
  });
  await beat(rnd(420, 780));
  assertLive(signal);
  const r = runShell(ctx.getTree(), command);
  const out = r.stdout.length > 18 ? [...r.stdout.slice(0, 18), d.command.moreLines(r.stdout.length - 18)] : r.stdout;
  yield* (r.ok ? evDone : evFail)(term, {
    title: r.ok ? d.command.title : d.command.titleFailed,
    description: r.ok ? d.fix.exitOk : (r.stderr ? r.stderr.split('\n')[0] : d.fix.buildExit(r.exitCode)),
    output: { command, stdout: out, stderr: r.stderr, exitCode: r.exitCode, diagnostics: r.diagnostics },
    metadata: { retryable: true },
  });
  yield* think(d.think.preparingShort, undefined, signal, rnd(280, 460));
  const text = r.ok
    ? [
        d.command.okLead(command),
        '', '```', ...out.slice(0, 12), ...(out.length > 12 ? [d.command.moreLines(out.length - 12)] : []), '```',
        '',
        command.includes('build') ? d.command.noteBuild : command.includes('test') ? d.command.noteTest : d.command.noteGeneric,
      ].join('\n')
    : [
        d.command.failLead(command, r.exitCode),
        '', '```', ...(r.stderr ? r.stderr.split('\n').slice(0, 12) : out.slice(0, 12)), '```',
        '',
        r.diagnostics?.length ? d.command.diagNote(r.diagnostics.length) : d.command.retryNote,
      ].join('\n');
  yield* streamText(text, signal);
  return {};
}

/* ═══════════════════ PIPELINE: general chat ═══════════════════ */

async function* pipelineChat(
  text: string, signal: AbortSignal, d: AgentDict, lang: Lang,
): AsyncGenerator<StreamChunk, { sources?: SourceMeta[] }> {
  yield* think(d.think.understandingReq, d.think.readingMsg, signal, rnd(380, 640));

  const gather = yield* evStart({
    kind: 'analysis', tool: 'analysis', title: d.chat.gatherTitle,
    description: d.chat.gatherDesc,
  });
  await beat(rnd(300, 520));
  const hits = searchCorpus(text).slice(0, 4);
  assertLive(signal);
  yield* evDone(gather, {
    description: hits.length ? d.chat.found(hits.length) : d.chat.noneNeeded,
  });

  yield* think(d.think.composing, hits.length ? d.think.weaving : d.think.structuring, signal, rnd(380, 640));

  const lower = text.toLowerCase();
  let out: string;
  let sources: SourceMeta[] | undefined;

  const isGreeting = /^(hi|hello|hey|yo|good (morning|afternoon|evening))\b/.test(lower)
    || /^(salut|bonjour|bonsoir|coucou|hello)\b/.test(lower);
  const isCaps = /what can you do|your (tools|capabilities)|help$/.test(lower)
    || /que peux[- ]tu|tes (outils|capacités)|fonctionnalités|^\s*aide\s*[?!.]?\s*$/.test(lower);

  const userProfile = usePersona.getState();
  const userName = userProfile.userName.trim();

  if (isGreeting) {
    if (userName) {
      out = lang === 'fr'
        ? d.chat.greeting.replace('Bonjour —', `Bonjour ${userName} —`)
        : d.chat.greeting.replace('Hello —', `Hello ${userName} —`);
    } else {
      out = d.chat.greeting;
    }
  } else if (isCaps) {
    out = d.chat.caps;
  } else if (hits.length) {
    sources = hits.map(({ title, domain, url, date, excerpt }) => ({ title, domain, url, date, excerpt }));
    const facts: string[] = [];
    hits.slice(0, 3).forEach((doc, i) => localized(doc, lang).body.slice(0, 2).forEach((b) => facts.push(`${b} [${i + 1}]`)));
    const top = hits[0]!;
    const topExcerpt = localized(top, lang).excerpt.replace(/\.$/, '').toLowerCase();
    out = [
      `${d.chat.hitsIntro}`,
      '',
      ...facts.slice(0, 5).map((f) => `- ${f}`),
      '',
      d.chat.strongest(top.title, top.domain, topExcerpt),
      '',
      d.chat.deeperAsk,
    ].join('\n');
  } else {
    out = d.chat.fallback;
  }

  yield* streamText(out, signal);
  return { sources };
}

/* ═══════════════════ PIPELINE: video processing ═══════════════════ */

async function* pipelineVideo(
  video: AttachedVideo, text: string, signal: AbortSignal, d: AgentDict, lang: Lang,
): AsyncGenerator<StreamChunk, Record<string, never>> {
  yield* think(d.think.analyzing, d.think.readingMsg, signal, rnd(300, 560));

  /* ── 1 · probe: real container metadata ── */
  const probe = yield* evStart({
    kind: 'video', tool: 'video_probe', title: d.video.probeTitle,
    description: d.video.probeDesc,
    input: { name: video.name, size: video.size, type: video.type },
  });
  let meta: VideoMeta;
  try {
    meta = await probeVideo(video);
  } catch (err) {
    yield* evFail(probe, {
      title: d.video.probeTitle,
      description: err instanceof Error ? err.message : String(err),
    });
    yield* think(d.think.preparingShort, undefined, signal, 240);
    yield* streamText(
      lang === 'fr'
        ? `Impossible de décoder **${video.name}** avec les codecs du navigateur. Le fichier n'a pas pu être analysé — la carte d'activité montre l'erreur exacte.`
        : `**${video.name}** could not be decoded by the browser codecs, so nothing was analyzed — the activity card shows the exact error.`,
      signal,
    );
    return {};
  }
  assertLive(signal);
  yield* evDone(probe, {
    description: d.video.probeDone(fmtTime(meta.duration), `${meta.width}×${meta.height}`),
    output: { video: true, ...meta, durationLabel: fmtTime(meta.duration), sizeLabel: fmtBytes(meta.size) },
  });

  /* ── 2 · real frame extraction with real per-frame progress ── */
  const frames = yield* evStart({
    kind: 'video', tool: 'video_frames', title: d.video.framesTitle,
    description: d.video.framesDesc,
  });
  let frameCount = 0;
  let framesSettled = false;
  const thumbsPromise = extractThumbnails(video, meta.duration, 5, (done) => { frameCount = done; })
    .then((t) => { framesSettled = true; return t; });
  while (!framesSettled) {
    await beat(120);
    assertLive(signal);
    yield* evPatch(frames, {
      phase: 'progress',
      progress: { done: frameCount, total: 5, unit: 'frames' },
    });
  }
  const thumbs = await thumbsPromise;
  yield* evDone(frames, {
    description: d.video.framesDone(thumbs.length),
    output: { frames: thumbs.length, thumbs: thumbs.map((t) => ({ ts: t.ts, dataUrl: t.dataUrl })) },
    progress: { done: thumbs.length, total: 5, unit: 'frames' },
  });

  /* ── 3 · optional trim — real MediaRecorder re-encode ── */
  const range = parseTrimRange(text);
  let trimNote: string | undefined;
  if (range && meta.duration > 0) {
    const start = Math.min(range.start, Math.max(meta.duration - 0.5, 0));
    const end = Math.min(range.end, meta.duration);
    if (end - start >= 0.5) {
      const trim = yield* evStart({
        kind: 'video', tool: 'video_editor', title: d.video.trimTitle,
        description: d.video.trimDesc(fmtTime(start), fmtTime(end)),
        input: { start, end, startLabel: fmtTime(start), endLabel: fmtTime(end) },
      });
      if (!trimSupported()) {
        yield* evFail(trim, { title: d.video.trimFail, description: d.video.unsupported });
      } else {
        /* poll genuine recorder progress while the encoder runs in real time */
        let probe = { ratio: 0, at: start };
        let settled = false;
        const run = trimVideo(video, start, end, (ratio, at) => { probe = { ratio, at }; }, () => signal.aborted)
          .then((r) => { settled = true; return r; });
        while (!settled) {
          await beat(320);
          assertLive(signal);
          yield* evPatch(trim, {
            phase: 'progress',
            description: `${fmtTime(probe.at)} · ${Math.round(probe.ratio * 100)}%`,
            progress: { done: Math.round(probe.ratio * 100), total: 100, unit: '%' },
          });
        }
        try {
          const result = await run;
          yield* evDone(trim, {
            description: d.video.trimDone(fmtBytes(result.size)),
            output: {
              start, end, startLabel: fmtTime(start), endLabel: fmtTime(end),
              download: {
                url: result.blobUrl,
                name: `${video.name.replace(/\.[^.]+$/, '')}_clip.${result.mimeType.includes('mp4') ? 'mp4' : 'webm'}`,
                size: result.size, sizeLabel: fmtBytes(result.size), mime: result.mimeType,
              },
            },
            progress: { done: 100, total: 100, unit: '%' },
          });
          trimNote = d.video.trimNoteOk(fmtTime(start), fmtTime(end), fmtBytes(result.size));
        } catch (err) {
          yield* evFail(trim, {
            title: d.video.trimFail,
            description: err instanceof Error ? err.message : String(err),
          });
        }
      }
    }
  }

  /* ── 4 · compose the report ── */
  const summary = yield* evStart({
    kind: 'analysis', tool: 'analysis', title: d.video.summaryTitle,
    description: d.video.summaryDesc,
  });
  await beat(rnd(340, 560));
  assertLive(signal);
  yield* evDone(summary);

  yield* think(d.think.preparingShort, undefined, signal, rnd(240, 380));
  const codec = (meta.type || 'video/*').replace(/;.*$/, '');
  const text2 = d.video.answerMeta(
    meta.name,
    d.video.metaLines(fmtTime(meta.duration), `${meta.width}×${meta.height}`, fmtBytes(meta.size), codec, thumbs.length),
    trimNote ?? (range ? undefined : d.video.trimNoteHint),
  );
  yield* streamText(text2, signal);
  return {};
}

/* ═══════════════════ PIPELINE: local attachment inspection ═══════════════════ */

async function* pipelineAttachments(
  attachments: PendingAttachment[],
  signal: AbortSignal,
  d: AgentDict,
  lang: Lang,
): AsyncGenerator<StreamChunk, Record<string, never>> {
  yield* think(
    d.think.analyzing,
    lang === 'fr' ? 'Identification des formats joints' : 'Identifying attached formats',
    signal,
    rnd(220, 380),
  );

  let root = yield* evStart({
    kind: 'tool',
    tool: 'attachment_inspector',
    title: lang === 'fr' ? 'Inspection des pièces jointes' : 'Inspecting attachments',
    description: lang === 'fr'
      ? `${attachments.length} fichier(s) à vérifier…`
      : `${attachments.length} file(s) to inspect…`,
    progress: { done: 0, total: attachments.length, unit: lang === 'fr' ? 'fichiers' : 'files' },
  });
  const inspected: PendingAttachment[] = [];
  const failed: PendingAttachment[] = [];

  for (const original of attachments) {
    assertLive(signal);
    let child = yield* evStart({
      parentId: root.id,
      kind: original.kind === 'video' ? 'video' : 'file',
      tool: `${original.kind}_inspector`,
      title: original.name,
      description: lang === 'fr' ? 'Lecture du fichier…' : 'Reading file…',
      input: { name: original.name, size: original.size, type: original.type },
      metadata: { op: 'parse', path: original.name, bytes: original.size },
    });
    const value = await prepareAttachment(original);
    assertLive(signal);
    if (value.status === 'failed') {
      failed.push(value);
      child = yield* evFail(child, { description: value.error });
    } else {
      inspected.push(value);
      const facts = Object.entries(value.metadata ?? {})
        .filter(([, fact]) => fact !== undefined)
        .map(([key, fact]) => `${key}: ${fact}`)
        .join(' · ');
      child = yield* evDone(child, {
        description: facts || (lang === 'fr' ? 'Format vérifié' : 'Format verified'),
        output: { attachment: summarizeAttachment(value), extractedCharacters: value.extractedText?.length ?? 0 },
      });
    }
    const done = inspected.length + failed.length;
    root = yield* evPatch(root, {
      phase: 'progress',
      description: lang === 'fr'
        ? `${done}/${attachments.length} fichiers inspectés`
        : `${done}/${attachments.length} files inspected`,
      progress: { done, total: attachments.length, unit: lang === 'fr' ? 'fichiers' : 'files' },
    });
  }

  root = yield* (failed.length ? evFail : evDone)(root, {
    description: failed.length
      ? (lang === 'fr' ? `${failed.length} fichier(s) illisible(s)` : `${failed.length} unreadable file(s)`)
      : (lang === 'fr' ? `${inspected.length} fichier(s) vérifié(s)` : `${inspected.length} file(s) verified`),
    output: { files: inspected.length, failed: failed.length },
    progress: { done: attachments.length, total: attachments.length, unit: lang === 'fr' ? 'fichiers' : 'files' },
  });

  yield* think(d.think.preparingShort, undefined, signal, rnd(220, 360));
  const lines = inspected.map((value) => {
    const meta = value.metadata ?? {};
    const details = [
      fmtBytes(value.size),
      meta.width && meta.height ? `${meta.width}×${meta.height}` : '',
      meta.duration ? fmtTime(Number(meta.duration)) : '',
      meta.pages ? `${meta.pages} ${lang === 'fr' ? 'pages' : 'pages'}` : '',
      meta.characters ? `${Number(meta.characters).toLocaleString()} ${lang === 'fr' ? 'caractères' : 'characters'}` : '',
    ].filter(Boolean).join(' · ');
    return `- **${value.name}** — ${value.kind} · ${details || value.type}`;
  });
  const excerpts = inspected
    .filter((value) => value.extractedText)
    .slice(0, 2)
    .map((value) => `### ${value.name}\n\n> ${value.extractedText!.slice(0, 280).replace(/\s+/g, ' ')}${value.extractedText!.length > 280 ? '…' : ''}`);
  const answer = lang === 'fr'
    ? [
        `J’ai inspecté localement **${inspected.length}/${attachments.length} pièces jointes**.`,
        '', ...lines, '',
        'Cette inspection locale confirme les formats et métadonnées réels. Pour une analyse sémantique complète des images, PDF ou fichiers audio, connecte le backend IA : les fichiers seront alors envoyés par le canal sécurisé et transmis au modèle compatible.',
        ...(excerpts.length ? ['', ...excerpts] : []),
      ].join('\n')
    : [
        `I locally inspected **${inspected.length}/${attachments.length} attachments**.`,
        '', ...lines, '',
        'This local inspection confirms real formats and metadata. For full semantic analysis of images, PDFs or audio, connect the AI backend: files will then use the secure upload channel and reach the compatible model.',
        ...(excerpts.length ? ['', ...excerpts] : []),
      ].join('\n');
  yield* streamText(answer, signal);
  return {};
}

/* ═══════════════════ INTENT ROUTER ═══════════════════ */

type Intent =
  | { kind: 'code'; lang: string; code: string }
  | { kind: 'calc'; expr: string }
  | { kind: 'command'; command: string }
  | { kind: 'fix' }
  | { kind: 'research'; query: string }
  | { kind: 'chat'; text: string };

export function detectIntent(raw: string): Intent {
  const text = raw.trim();
  const lower = text.toLowerCase();

  // explicit code block
  const fence = /```(\w+)?\s*\n([\s\S]*?)```/.exec(text);
  if (fence && /run|exec|exécut|execute|lance|what does|output|affiche/i.test(lower.replace(fence[0], ''))) {
    const lang = (fence[1] || 'javascript').toLowerCase().replace(/^js$/, 'javascript').replace(/^ts$/, 'typescript').replace(/^(sh|bash)$/, 'shell');
    return { kind: 'code', lang, code: fence[2].trim() };
  }

  // quoted command
  const quoted = /(?:run|execute|exécut(?:e|er|ez)|lance(?:r|z)?|démarre(?:r)?)\s+`([^`]+)`/i.exec(text);
  if (quoted) return { kind: 'command', command: quoted[1]!.trim() };

  // shortcut commands
  if (/\brun\s+(the\s+)?(tests?|test\s+suite)\b/.test(lower) || /(lance|exécute|exécuter)\s+(les\s+)?tests?\b/.test(lower)) {
    return { kind: 'command', command: 'npm test' };
  }
  if (/^(run\s+)?(npm|ls|cat|grep|wc|head|tail|echo)\b/.test(lower)) {
    return { kind: 'command', command: text.replace(/^(run|lance|lancer|exécute|exécuter|exécutez)\s+/i, '').trim() };
  }

  // project repair pipeline
  if (
    /(fix|repair|investigate|debug|diagnose).*(build|error|project|test|repo)/.test(lower) ||
    /(build|tests?)\s+(is\s+)?(fail|broken|not\s+work)/.test(lower) ||
    /analy[sz]e\s+(my|the|this|mon|ce|le|ton)\s+(project|repo|codebase|projet|dépôt|code)/.test(lower) ||
    /(corrige[rz]?|répare[rz]?|débog\w*|diagnostique[rz]?)[\s\S]*(build|projet|erreur|compilation|tests?|dépôt)/.test(lower) ||
    /(build|compilation|tests?|projet)\s+(ne\s+(passe|marche|fonctionne)\s+pas|échoue|en\s+échec|cassé)/.test(lower) ||
    /revois?\s+(mon|le|ce)\s+(projet|code|dépôt)/.test(lower)
  ) {
    return { kind: 'fix' };
  }

  // calculator
  const mathCandidate = text
    .replace(/^(what\s+is|what's|calculate|compute|solve|evaluate|how\s+much\s+is|calcule(?:r|z)?|calcul(?:ez)?\s+de|combien\s+fait|que\s+vaut|évalue(?:r|z)?|résous|résoudre)\s*/i, '')
    .replace(/[?=.]\s*$/, '')
    .trim();
  if (/^[-+0-9(\s]/.test(mathCandidate) && /[0-9]/.test(mathCandidate) && /[+\-*/^%×÷]|pi\b/.test(mathCandidate) && !/[a-df-z]/i.test(mathCandidate.replace(/pi/g, ''))) {
    return { kind: 'calc', expr: mathCandidate };
  }

  // web research
  const searchVerbs = /^(please\s+)?(search|look\s*up|find|research|google|browse|recherche(?:r|z)?|cherche(?:r|z)?|trouve(?:r|z)?)\s*/i;
  if (searchVerbs.test(text) || /latest|news|state of|trends?|what'?s happening|tell me (about|what)|derni[eè]re?s?|nouveaut[ée]s?|actualit[ée]s?|parle[- ]moi de/i.test(lower)) {
    const q = text
      .replace(searchVerbs, '')
      .replace(/^\s*(the\s+web|online|the\s+internet|sur\s+le\s+web|en\s+ligne)\s*:?-?\s*(for|pour)?/i, '')
      .replace(/^\s*for\s+/i, '')
      .replace(/^\s*(what\s+is|what's|what\s+are|tell\s+me\s+about|quels?\s+sont|quelles\s+sont|parle[- ]moi\s+de)\s+/i, '')
      .replace(/^\s*(the\s+)?(latest|derniers?|derni[eè]res?)\s+(on|about|in|developments\s+in|sur|de|des|concernant)\s+/i, '')
      .trim() || text;
    return { kind: 'research', query: q.replace(/[?.!]+$/, '') };
  }

  return { kind: 'chat', text };
}

/* ═══════════════════ ENTRY POINT ═══════════════════ */

export interface AgentRequest {
  text: string;
  video?: AttachedVideo;
  attachments?: PendingAttachment[];
  /** recent conversation turns, for remote backends */
  history?: Array<{ role: 'user' | 'assistant'; content: string }>;
}

export async function* runAgent(
  request: AgentRequest,
  ctx: AgentContext,
  signal?: AbortSignal,
): AsyncGenerator<StreamChunk> {
  await beat(rnd(220, 420)); // connection ramp — first event arrives shortly after send
  const lang: Lang = detectLanguage(request.text) ?? uiLocale();
  const d = agentStrings(lang);

  // A single video keeps the specialized edit/thumbnail pipeline.
  if (request.video) {
    yield* pipelineVideo(request.video, request.text, signal!, d, lang);
    yield { type: 'done', meta: {} };
    return;
  }

  if (request.attachments?.length) {
    yield* pipelineAttachments(request.attachments, signal!, d, lang);
    yield { type: 'done', meta: {} };
    return;
  }

  const intent = detectIntent(request.text);
  let meta: { sources?: SourceMeta[] } = {};
  switch (intent.kind) {
    case 'fix': meta = yield* pipelineFixBuild(ctx, signal!, d); break;
    case 'research': meta = yield* pipelineResearch(intent.query, signal!, d, lang); break;
    case 'calc': meta = yield* pipelineCalc(intent.expr, signal!, d); break;
    case 'code': meta = yield* pipelineCode(intent.lang, intent.code, signal!, d); break;
    case 'command': meta = yield* pipelineCommand(intent.command, ctx, signal!, d); break;
    default: meta = yield* pipelineChat(intent.text, signal!, d, lang);
  }
  yield { type: 'done', meta };
}
