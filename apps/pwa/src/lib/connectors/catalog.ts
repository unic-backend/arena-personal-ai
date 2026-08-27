/* ─────────────────────────────────────────────────────────────
   Connector catalog — the integrations your AI can use.
   Each entry declares how it authenticates; the actual data
   calls are performed by YOUR backend (see server/main.py),
   which receives the enabled connectors with every request.
   ───────────────────────────────────────────────────────────── */

import type { LucideIcon } from 'lucide-react';
import {
  Mail, Calendar, HardDrive, GitBranch, GitFork, Hash, Notebook, ListTodo,
  ClipboardList, AtSign, Building2, MessageCircle, Database, Webhook,
  Rss, Cloud, Target,
} from 'lucide-react';

export type ConnectorAuth = 'oauth' | 'apikey';

export type ConnectorCategory =
  | 'productivity'
  | 'code'
  | 'social'
  | 'web'
  | 'enterprise'
  | 'data';

export interface ConnectorDef {
  id: string;
  name: string;
  icon: LucideIcon;
  category: ConnectorCategory;
  auth: ConnectorAuth;
  /** for apikey connectors — what secret to paste */
  secretLabel: string;
  secretLabelFr: string;
  description: string;
  descriptionFr: string;
  /** capabilities shown in the card */
  scopes: string[];
  scopesFr: string[];
}

export const CONNECTOR_CATEGORIES: Array<{ id: ConnectorCategory; label: string; labelFr: string }> = [
  { id: 'productivity', label: 'Productivity', labelFr: 'Productivité' },
  { id: 'code', label: 'Code & projects', labelFr: 'Code & projets' },
  { id: 'social', label: 'Social networks', labelFr: 'Réseaux sociaux' },
  { id: 'web', label: 'Web & sites', labelFr: 'Web & sites' },
  { id: 'enterprise', label: 'Enterprise apps', labelFr: 'Applications entreprise' },
  { id: 'data', label: 'Data', labelFr: 'Données' },
];

export const CONNECTOR_CATALOG: ConnectorDef[] = [
  {
    id: 'gmail', name: 'Gmail', icon: Mail, category: 'productivity', auth: 'oauth',
    secretLabel: '', secretLabelFr: '',
    description: 'Read, search and draft emails',
    descriptionFr: 'Lire, rechercher et rédiger des e-mails',
    scopes: ['read mail', 'search', 'draft'],
    scopesFr: ['lecture', 'recherche', 'brouillons'],
  },
  {
    id: 'gcal', name: 'Google Calendar', icon: Calendar, category: 'productivity', auth: 'oauth',
    secretLabel: '', secretLabelFr: '',
    description: 'List events and schedule meetings',
    descriptionFr: 'Lister les événements et planifier des réunions',
    scopes: ['events', 'schedule'],
    scopesFr: ['événements', 'planification'],
  },
  {
    id: 'gdrive', name: 'Google Drive', icon: HardDrive, category: 'productivity', auth: 'oauth',
    secretLabel: '', secretLabelFr: '',
    description: 'Browse and read documents',
    descriptionFr: 'Parcourir et lire les documents',
    scopes: ['files', 'read'],
    scopesFr: ['fichiers', 'lecture'],
  },
  {
    id: 'notion', name: 'Notion', icon: Notebook, category: 'productivity', auth: 'apikey',
    secretLabel: 'Internal integration token',
    secretLabelFr: 'Jeton d’intégration interne',
    description: 'Query pages and databases',
    descriptionFr: 'Interroger pages et bases de données',
    scopes: ['pages', 'databases'],
    scopesFr: ['pages', 'bases'],
  },
  {
    id: 'github', name: 'GitHub', icon: GitBranch, category: 'code', auth: 'apikey',
    secretLabel: 'Personal access token (repo, read:org)',
    secretLabelFr: 'Jeton d’accès personnel (repo, read:org)',
    description: 'Repos, issues, PRs and code search',
    descriptionFr: 'Dépôts, issues, PR et recherche de code',
    scopes: ['repos', 'issues', 'pull requests'],
    scopesFr: ['dépôts', 'issues', 'pull requests'],
  },
  {
    id: 'gitlab', name: 'GitLab', icon: GitFork, category: 'code', auth: 'apikey',
    secretLabel: 'Personal access token (read_api)',
    secretLabelFr: 'Jeton d’accès personnel (read_api)',
    description: 'Projects, MRs and pipelines',
    descriptionFr: 'Projets, MR et pipelines',
    scopes: ['projects', 'merge requests', 'CI'],
    scopesFr: ['projets', 'merge requests', 'CI'],
  },
  {
    id: 'jira', name: 'Jira', icon: ClipboardList, category: 'code', auth: 'apikey',
    secretLabel: 'API token (email + token)',
    secretLabelFr: 'Jeton API (e-mail + jeton)',
    description: 'Issues, sprints and boards',
    descriptionFr: 'Tickets, sprints et tableaux',
    scopes: ['issues', 'sprints'],
    scopesFr: ['tickets', 'sprints'],
  },
  {
    id: 'linear', name: 'Linear', icon: ListTodo, category: 'code', auth: 'apikey',
    secretLabel: 'API key',
    secretLabelFr: 'Clé API',
    description: 'Issues and project cycles',
    descriptionFr: 'Tickets et cycles de projet',
    scopes: ['issues', 'cycles'],
    scopesFr: ['tickets', 'cycles'],
  },
  {
    id: 'x', name: 'X (Twitter)', icon: AtSign, category: 'social', auth: 'apikey',
    secretLabel: 'Bearer token (API v2)',
    secretLabelFr: 'Jeton Bearer (API v2)',
    description: 'Read timelines and post',
    descriptionFr: 'Lire les timelines et publier',
    scopes: ['timeline', 'post'],
    scopesFr: ['timeline', 'publication'],
  },
  {
    id: 'linkedin', name: 'LinkedIn', icon: Building2, category: 'social', auth: 'oauth',
    secretLabel: '', secretLabelFr: '',
    description: 'Profile and network posts',
    descriptionFr: 'Profil et publications du réseau',
    scopes: ['profile', 'posts'],
    scopesFr: ['profil', 'publications'],
  },
  {
    id: 'whatsapp', name: 'WhatsApp Business', icon: MessageCircle, category: 'social', auth: 'apikey',
    secretLabel: 'Permanent access token (Cloud API)',
    secretLabelFr: 'Jeton d’accès permanent (Cloud API)',
    description: 'Send and read business messages',
    descriptionFr: 'Envoyer et lire les messages professionnels',
    scopes: ['messages'],
    scopesFr: ['messages'],
  },
  {
    id: 'http', name: 'HTTP / REST API', icon: Webhook, category: 'web', auth: 'apikey',
    secretLabel: 'Base URL + Authorization header',
    secretLabelFr: 'URL de base + en-tête Authorization',
    description: 'Call any JSON API endpoint',
    descriptionFr: 'Appeler n’importe quel endpoint JSON',
    scopes: ['GET', 'POST'],
    scopesFr: ['GET', 'POST'],
  },
  {
    id: 'rss', name: 'RSS / Web feeds', icon: Rss, category: 'web', auth: 'apikey',
    secretLabel: 'Feed URLs (comma separated, optional)',
    secretLabelFr: 'URLs des flux (séparées par virgules, optionnel)',
    description: 'Follow blogs, news and changelogs',
    descriptionFr: 'Suivre blogs, actualités et changelogs',
    scopes: ['feeds', 'search'],
    scopesFr: ['flux', 'recherche'],
  },
  {
    id: 'slack', name: 'Slack', icon: Hash, category: 'enterprise', auth: 'apikey',
    secretLabel: 'Bot token (xoxb-…)',
    secretLabelFr: 'Jeton bot (xoxb-…)',
    description: 'Channels, search and messages',
    descriptionFr: 'Canaux, recherche et messages',
    scopes: ['channels', 'search', 'post'],
    scopesFr: ['canaux', 'recherche', 'publication'],
  },
  {
    id: 'salesforce', name: 'Salesforce', icon: Cloud, category: 'enterprise', auth: 'oauth',
    secretLabel: '', secretLabelFr: '',
    description: 'Accounts, leads and opportunities',
    descriptionFr: 'Comptes, leads et opportunités',
    scopes: ['CRM', 'reports'],
    scopesFr: ['CRM', 'rapports'],
  },
  {
    id: 'hubspot', name: 'HubSpot', icon: Target, category: 'enterprise', auth: 'apikey',
    secretLabel: 'Private app token',
    secretLabelFr: 'Jeton d’app privée',
    description: 'Contacts, deals and campaigns',
    descriptionFr: 'Contacts, deals et campagnes',
    scopes: ['CRM', 'marketing'],
    scopesFr: ['CRM', 'marketing'],
  },
  {
    id: 'postgres', name: 'PostgreSQL', icon: Database, category: 'data', auth: 'apikey',
    secretLabel: 'Connection string (read-only recommended)',
    secretLabelFr: 'Chaîne de connexion (lecture seule recommandée)',
    description: 'Run read queries and inspect schemas',
    descriptionFr: 'Exécuter des requêtes en lecture et inspecter les schémas',
    scopes: ['query', 'schema'],
    scopesFr: ['requêtes', 'schéma'],
  },
];

export function getConnector(id: string): ConnectorDef | undefined {
  return CONNECTOR_CATALOG.find((c) => c.id === id);
}
