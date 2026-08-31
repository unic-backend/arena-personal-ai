/* ─────────────────────────────────────────────────────────────
   Connector catalog — the integrations ARENA can actually use.

   Reconciled 31/08/2026 (chapitre 8.2) with the real backend:
   this used to list 17 connectors (Notion, GitHub, Slack, Jira,
   Salesforce...) with zero backend code behind any of them, and a
   "Connect" button that called a route (`/connectors/{id}/auth`)
   that did not exist anywhere in apps/backend. Only what has a
   real, tested backend path stays here — a button that cannot
   possibly work is worse than no button.

   Gmail is the only entry today (audit + owner decision,
   31/08/2026) : real OAuth against apps/backend/routers/connectors.py,
   which drives core/connectors/gmail.py (already complete: list,
   search, read, send — send locked behind confirmation).
   ───────────────────────────────────────────────────────────── */

import type { LucideIcon } from 'lucide-react';
import { Mail } from 'lucide-react';

export type ConnectorAuth = 'oauth' | 'apikey';

export type ConnectorCategory = 'productivity';

export interface ConnectorDef {
  id: string;
  name: string;
  icon: LucideIcon;
  category: ConnectorCategory;
  auth: ConnectorAuth;
  description: string;
  descriptionFr: string;
  /** capabilities shown in the card — must match what the backend actually exposes */
  scopes: string[];
  scopesFr: string[];
}

export const CONNECTOR_CATEGORIES: Array<{ id: ConnectorCategory; label: string; labelFr: string }> = [
  { id: 'productivity', label: 'Productivity', labelFr: 'Productivité' },
];

export const CONNECTOR_CATALOG: ConnectorDef[] = [
  {
    id: 'gmail', name: 'Gmail', icon: Mail, category: 'productivity', auth: 'oauth',
    description: 'Read, search emails — draft & send only with your confirmation',
    descriptionFr: 'Lire, rechercher — brouillon et envoi seulement avec ta confirmation',
    scopes: ['read mail', 'search', 'send (confirmed)'],
    scopesFr: ['lecture', 'recherche', 'envoi (confirmé)'],
  },
];

export function getConnector(id: string): ConnectorDef | undefined {
  return CONNECTOR_CATALOG.find((c) => c.id === id);
}
