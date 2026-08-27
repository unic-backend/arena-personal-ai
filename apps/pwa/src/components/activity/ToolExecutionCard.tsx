import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import type { ToolDef } from '../../lib/agent/tools';
import { useI18n } from '../../lib/i18n';
import { kindIcon } from './StatusIcon';
import { cn } from '../../utils/cn';

/* ─────────────────────────────────────────────────────────────
   Generic tool card — icon, name, status, description, version.
   The list is rendered straight from the backend registry, so a
   tool registered server-side appears here automatically.
   ───────────────────────────────────────────────────────────── */
export function ToolExecutionCard({ tool, index }: { tool: ToolDef; index: number }) {
  const [open, setOpen] = useState(false);
  const { locale } = useI18n();
  const fr = locale === 'fr';
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25 }}
      className="rounded-lg border border-white/6 bg-white/[0.02] transition-colors hover:border-white/10"
    >
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2.5 px-2.5 py-2 text-left">
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-white/8 bg-white/[0.04] text-zinc-300">
          {kindIcon(tool.kind, tool.id)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[11.5px] font-medium text-zinc-200">{fr ? tool.nameFr ?? tool.name : tool.name}</span>
          <span className="block truncate font-mono text-[9px] text-zinc-600">v{tool.version}</span>
        </span>
        <span
          className={cn(
            'inline-block h-1.5 w-1.5 shrink-0 rounded-full',
            tool.status === 'online' ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.7)]' : tool.status === 'degraded' ? 'bg-amber-400' : 'bg-red-400',
          )}
          title={tool.status}
        />
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.15 }}>
          <ChevronRight size={11} className="text-zinc-600" />
        </motion.span>
      </button>
      {open && (
        <div className="border-t border-white/5 px-2.5 py-2">
          <p className="text-[10.5px] leading-relaxed text-zinc-500">{fr ? tool.descriptionFr ?? tool.description : tool.description}</p>
          <p className="mt-1 font-mono text-[9px] text-zinc-600">kind: {tool.kind} · id: {tool.id}</p>
        </div>
      )}
    </motion.div>
  );
}
