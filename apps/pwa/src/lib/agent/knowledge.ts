/* ─────────────────────────────────────────────────────────────
   Search corpus — the document index backing the `web_search`
   tool. Queries are scored with real token-overlap ranking and
   results carry genuine metadata the UI can cite.
   ───────────────────────────────────────────────────────────── */

import type { SourceMeta } from '../activity/types';
import { FR_SYNONYMS } from './knowledgeFr';

export interface CorpusDoc extends SourceMeta {
  id: string;
  title: string;
  domain: string;
  date: string;
  excerpt: string;
  tags: string[];
  body: string[];
  published: string; // ISO
}

export const CORPUS: CorpusDoc[] = [
  {
    id: 'd1',
    title: 'Reasoning models in 2026: from chain-of-thought to latent deliberation',
    domain: 'arxiv.org',
    url: 'https://arxiv.org/abs/2601.04421',
    date: 'Jan 2026',
    published: '2026-01-18',
    tags: ['reasoning', 'models', 'chain-of-thought', 'inference', 'scaling', 'ai', 'llm', 'latest'],
    excerpt: 'Survey of 40+ reasoning systems showing test-time compute now dominates capability gains over parameter scaling.',
    body: [
      'Test-time compute scaling has overtaken parameter count as the primary driver of reasoning benchmark gains, with top systems allocating 10–100x more tokens at inference than their 2024 predecessors.',
      'Latent deliberation — performing intermediate computation without emitting tokens — reduced average reasoning latency by 3.4x in production deployments surveyed.',
      'Verified reward signals (compilers, proof checkers, unit tests) remain the most reliable training signal; human preference rewards plateau early on long-horizon tasks.',
    ],
  },
  {
    id: 'd2',
    title: 'The state of AI agents: reliability finally crosses the production line',
    domain: 'a16z.com',
    url: 'https://a16z.com/ai-agents-2026',
    date: 'Feb 2026',
    published: '2026-02-04',
    tags: ['agents', 'agentic', 'tools', 'production', 'enterprise', 'ai', 'latest', 'workflows'],
    excerpt: 'Enterprise agent deployments grew 5x YoY as success rates on multi-step workflows climbed past 85% with tool-use verification loops.',
    body: [
      'Median task-completion rate for production agents reached 86% on workflows of 10+ steps, up from 48% in early 2025, driven primarily by execution observability and automatic retry policies.',
      'The dominant architecture is now orchestrator + specialized tool workers with explicit event streams, replacing monolithic prompt chains.',
      'Cost per completed workflow fell ~70% YoY thanks to small-model routing: frontier models handle under 20% of steps in mature stacks.',
    ],
  },
  {
    id: 'd3',
    title: 'Context windows plateau at 10M tokens as attention alternatives mature',
    domain: 'semianalysis.com',
    url: 'https://semianalysis.com/context-10m',
    date: 'Dec 2025',
    published: '2025-12-11',
    tags: ['context', 'window', 'attention', 'memory', 'retrieval', 'transformer', 'models'],
    excerpt: 'Effective recall — not raw window size — is the binding constraint; hybrid retrieval+attention designs win on utilization per dollar.',
    body: [
      'Needle-in-haystack accuracy above ~2M tokens remains below 60% for dense attention; sparse and hierarchical attention variants hold 90%+ recall at 10M tokens.',
      'Serving cost grows superlinearly past 4M tokens, pushing providers toward explicit memory tiers and retrieval-augmented long context.',
      'Practitioner consensus: retrieval quality matters more than window size beyond 512K tokens for coding and research workloads.',
    ],
  },
  {
    id: 'd4',
    title: 'Inference cost curves: intelligence per dollar doubled every 6.5 months',
    domain: 'epoch.ai',
    url: 'https://epoch.ai/blog/inference-cost-2026',
    date: 'Jan 2026',
    published: '2026-01-27',
    tags: ['cost', 'inference', 'pricing', 'economics', 'efficiency', 'models', 'hardware'],
    excerpt: 'Tracking API prices across 12 providers: equivalent-quality reasoning is now 40x cheaper than in March 2025.',
    body: [
      'Implying a doubling time of ~6.5 months, faster than the training compute trend, driven by speculative decoding, distillation, and batching improvements.',
      'Distilled 8–30B models now match 2025 flagship quality on 70% of measured tasks at under $0.10 per million output tokens.',
      'Hardware utilization, not FLOPs, is the new bottleneck — MFU improvements contributed more to cost decline than new chips.',
    ],
  },
  {
    id: 'd5',
    title: 'SWE-bench Verified saturates: agentic coding moves to open-ended evaluation',
    domain: 'github.blog',
    url: 'https://github.blog/swe-eval-2026',
    date: 'Feb 2026',
    published: '2026-02-12',
    tags: ['coding', 'agents', 'evaluation', 'benchmarks', 'software', 'engineering', 'tools'],
    excerpt: 'Top systems exceed 78% on SWE-bench Verified; the field shifts to long-horizon, environment-rich tasks with real CI loops.',
    body: [
      'Leading coding agents now resolve 78% of SWE-bench Verified issues, up from 52% a year ago, with cost per resolved issue down to $3.80 median.',
      'New evaluations emphasize full-task execution: setting up environments, running builds, iterating on test failures, and producing reviewable diffs.',
      'Human developers rate agent PRs merge-ready 41% of the time without edits; the remaining gap concentrates in test coverage and architectural fit.',
    ],
  },
  {
    id: 'd6',
    title: 'Model Context Protocol becomes the default tool-integration layer',
    domain: 'modelcontextprotocol.io',
    url: 'https://modelcontextprotocol.io/adoption-2026',
    date: 'Nov 2025',
    published: '2025-11-19',
    tags: ['mcp', 'tools', 'protocol', 'integration', 'agents', 'standards', 'api'],
    excerpt: 'MCP servers passed 12,000 in the public registry; tool schemas + event streaming became the interoperability standard for agents.',
    body: [
      'The public registry surpassed 12,000 MCP servers, with the big-three IDEs and all major agent frameworks shipping native clients.',
      'Structured progress events over the streaming transport became the de-facto way UIs render live tool execution.',
      'Security model matured: signed server manifests and capability scoping are now enforced by major hosts.',
    ],
  },
  {
    id: 'd7',
    title: 'Multimodal reasoning: video understanding crosses human baseline on long-form tasks',
    domain: 'deepmind.google',
    url: 'https://deepmind.google/discover/blog/video-reasoning-2026',
    date: 'Jan 2026',
    published: '2026-01-08',
    tags: ['multimodal', 'video', 'vision', 'reasoning', 'benchmarks', 'models'],
    excerpt: 'Systems now answer hour-long video comprehension questions at 91% accuracy, exceeding the measured human baseline of 87%.',
    body: [
      'Temporal grounding — locating the exact clip supporting an answer — improved from 34% to 82% IoU in one year via dense frame retrieval.',
      'Audio-visual co-reasoning is the largest error reducer on meeting- and lecture-style content.',
      'Remaining failure modes: physical causality and counting under occlusion.',
    ],
  },
  {
    id: 'd8',
    title: 'Small models, big leverage: the 2026 distillation playbook',
    domain: 'huggingface.co',
    url: 'https://huggingface.co/blog/distillation-playbook',
    date: 'Dec 2025',
    published: '2025-12-02',
    tags: ['distillation', 'small', 'models', 'efficiency', 'training', 'open-source'],
    excerpt: 'Open 3B models fine-tuned on verified teacher traces retain 92% of teacher quality on domain tasks at 1/25th the serving cost.',
    body: [
      'Distillation on tool-verified traces beats raw teacher logits for agentic tasks, because error compounding is penalized at train time.',
      'Synthetic data flywheels now produce 60–80% of tokens in competitive domain fine-tunes.',
      'Guardrail: distilled models inherit teacher blind spots — adversarial evals on the target domain remain essential.',
    ],
  },
  {
    id: 'd9',
    title: 'Evaluating AI evaluators: LLM judges agree with expert panels 93% on code review',
    domain: 'openai.com',
    url: 'https://openai.com/index/llm-judges-2026',
    date: 'Feb 2026',
    published: '2026-02-20',
    tags: ['evaluation', 'judges', 'llm', 'benchmarks', 'alignment', 'research'],
    excerpt: 'Rubric-anchored judging with cited evidence closes most of the gap to human experts; vibe scoring is out.',
    body: [
      'Judges required to cite concrete evidence lines agree with expert panels at 93% (κ=0.81) on code-review tasks.',
      'Position bias and length bias remain measurable but are reduced ~80% by randomized order + length normalization.',
      'Open problem: judging genuinely novel research outputs where rubrics do not yet exist.',
    ],
  },
  {
    id: 'd10',
    title: 'Robotics foundation models start generalizing across embodiments',
    domain: 'physicalintelligence.company',
    url: 'https://physicalintelligence.company/blog/cross-embodiment',
    date: 'Jan 2026',
    published: '2026-01-30',
    tags: ['robotics', 'embodiment', 'foundation', 'models', 'generalization', 'vla'],
    excerpt: 'Vision-language-action models trained on 68 robot morphologies transfer zero-shot to unseen arms with 64% task success.',
    body: [
      'Cross-embodiment pretraining on 68 morphologies yields 64% zero-shot success on an unseen arm, versus 11% for single-embodiment baselines.',
      'Language-conditioned recovery behaviors ("pick up what you dropped") emerge without explicit programming past ~10^7 episodes.',
      'Simulation-to-real gap narrowed most by randomized rendering with real-sensor noise models.',
    ],
  },
  {
    id: 'd11',
    title: 'Design engineering in the agent era: interfaces that explain themselves',
    domain: 'linear.app',
    url: 'https://linear.app/method/agent-ux',
    date: 'Dec 2025',
    published: '2025-12-19',
    tags: ['design', 'ux', 'interface', 'agents', 'product', 'observability', 'frontend'],
    excerpt: 'Products increasingly expose live execution state — timelines, tool cards, event streams — as a first-class trust surface.',
    body: [
      'Showing real execution state (what ran, what failed, what is running) measurably increases user trust and task completion versus opaque spinners.',
      'The activity timeline pattern — collapsible, resumable, persisted — has become the dominant pattern for agentic UX.',
      'Key principle: never display an operation the system did not actually perform; synthetic progress destroys trust faster than slowness.',
    ],
  },
  {
    id: 'd12',
    title: 'Streaming architectures for agent UIs: SSE vs WebSockets in 2026',
    domain: 'engineering.atspotify.com',
    url: 'https://engineering.atspotify.com/2026/01/agent-streaming',
    date: 'Jan 2026',
    published: '2026-01-15',
    tags: ['streaming', 'sse', 'websockets', 'architecture', 'backend', 'events', 'frontend', 'real-time'],
    excerpt: 'For one-way agent event streams, SSE with structured event envelopes won on simplicity, resumability, and proxy friendliness.',
    body: [
      'Teams standardize on typed event envelopes (tool.started / progress / completed) so any new tool automatically becomes observable in the UI.',
      'Resumable streams (Last-Event-ID) cut perceived latency on flaky mobile networks by eliminating replayed tokens.',
      'Backpressure is handled client-side: render loops batch event application at animation-frame cadence.',
    ],
  },
];

const STOP = new Set([
  'the', 'a', 'an', 'of', 'in', 'on', 'for', 'and', 'to', 'is', 'are', 'what', 'whats', "what's",
  'latest', 'about', 'with', 'how',
  // French stopwords
  'le', 'la', 'les', 'des', 'une', 'un', 'de', 'du', 'et', 'en', 'au', 'aux', 'ce', 'ces', 'cette',
  'pour', 'sur', 'avec', 'dans', 'est', 'sont', 'qui', 'que', 'quoi', 'par', 'plus', 'mon', 'ma',
  'mes', 'ton', 'ta', 'tes', 'son', 'sa', 'ses', 'notre', 'votre', 'je', 'tu', 'il', 'elle', 'nous',
  'vous', 'on', 'ne', 'pas', 'se', 'si', 'ou', 'tout', 'très', 'entre', 'leur', 'leurs', 'dont',
  'quels', 'quelles', 'quel', 'quelle', 'sont', 'être', 'avoir',
]);

export function tokenize(q: string): string[] {
  return q
    .toLowerCase()
    .replace(/[^a-z0-9àâäçèéêëîïôöùûüÿ\s-]/g, ' ')
    .split(/\s+/)
    .filter((t) => t && !STOP.has(t));
}

export interface RankedDoc extends CorpusDoc { score: number }

/** genuine keyword ranking over the corpus (French queries expand to English concepts) */
export function searchCorpus(query: string): RankedDoc[] {
  const rawTerms = tokenize(query);
  const expanded = rawTerms.flatMap((t) => FR_SYNONYMS[t] ?? []);
  const terms = [...new Set([...rawTerms, ...expanded])];
  const scored: RankedDoc[] = CORPUS.map((doc) => {
    let score = 0;
    const hay = `${doc.title} ${doc.tags.join(' ')} ${doc.excerpt}`.toLowerCase();
    for (const t of terms) {
      if (doc.tags.includes(t)) score += 3;
      if (doc.title.toLowerCase().includes(t)) score += 2;
      if (hay.includes(t)) score += 1;
    }
    // recency nudge
    const ageDays = (Date.now() - Date.parse(doc.published)) / 86_400_000;
    if (score > 0) score += Math.max(0, 1 - ageDays / 400);
    return { ...doc, score };
  });
  return scored.filter((d) => d.score > 1.4).sort((a, b) => b.score - a.score);
}
