import type { StreamChunk } from './types';

export interface LoggedChunk {
  ts: number;
  chunk: StreamChunk;
}

export type EventFilter = 'all' | StreamChunk['type'];

export function toolName(entry: LoggedChunk): string | null {
  if (entry.chunk.type !== 'activity') return null;
  return entry.chunk.event.tool?.trim() || null;
}

export function uniqueTools(entries: LoggedChunk[]): string[] {
  return [...new Set(entries.map(toolName).filter((v): v is string => Boolean(v)))].sort();
}

export function filterEventLog(
  entries: LoggedChunk[],
  type: EventFilter = 'all',
  tool = '',
  query = '',
): LoggedChunk[] {
  const needle = query.trim().toLocaleLowerCase();
  return entries.filter((entry) => {
    if (type !== 'all' && entry.chunk.type !== type) return false;
    if (tool && toolName(entry) !== tool) return false;
    if (!needle) return true;
    return JSON.stringify(entry.chunk).toLocaleLowerCase().includes(needle);
  });
}

export function eventStats(entries: LoggedChunk[]) {
  const counts: Record<StreamChunk['type'], number> = {
    activity: 0, token: 0, done: 0, error: 0,
  };
  for (const entry of entries) counts[entry.chunk.type] += 1;
  const first = entries[0]?.ts;
  const last = entries.at(-1)?.ts;
  return {
    total: entries.length,
    ...counts,
    tools: uniqueTools(entries).length,
    durationMs: first === undefined || last === undefined ? null : Math.max(0, last - first),
  };
}
