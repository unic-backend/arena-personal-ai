import { describe, expect, it } from 'vitest';
import { eventStats, filterEventLog, uniqueTools, type LoggedChunk } from './devtools';

const rows: LoggedChunk[] = [
  { ts: 1000, chunk: { type: 'activity', event: { id: '1', kind: 'tool', status: 'running', phase: 'started', title: 'Recherche', tool: 'web' } } },
  { ts: 1100, chunk: { type: 'token', text: 'Bonjour' } },
  { ts: 1250, chunk: { type: 'activity', event: { id: '2', kind: 'tool', status: 'completed', phase: 'completed', title: 'Recherche', tool: 'web' } } },
  { ts: 1400, chunk: { type: 'error', message: 'timeout provider' } },
];

describe('AI event devtools', () => {
  it('filters by event type, tool and free text', () => {
    expect(filterEventLog(rows, 'activity')).toHaveLength(2);
    expect(filterEventLog(rows, 'all', 'web')).toHaveLength(2);
    expect(filterEventLog(rows, 'all', '', 'TIMEOUT')).toEqual([rows[3]]);
  });

  it('reports measured stats without inventing token counts', () => {
    expect(eventStats(rows)).toEqual({
      total: 4, activity: 2, token: 1, done: 0, error: 1, tools: 1, durationMs: 400,
    });
  });

  it('discovers tool names deterministically', () => {
    expect(uniqueTools(rows)).toEqual(['web']);
  });

  it('keeps unknown duration null for an empty log', () => {
    expect(eventStats([]).durationMs).toBeNull();
  });
});
