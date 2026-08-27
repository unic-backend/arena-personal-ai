/* ─────────────────────────────────────────────────────────────
   Tool registry — the backend's catalog of capabilities.
   The UI renders this list (sidebar) and the orchestrator
   dispatches through it. Registering a new tool here makes it
   automatically observable in the activity timeline.
   ───────────────────────────────────────────────────────────── */

import type { ActivityKind } from '../activity/types';

export interface ToolDef {
  id: string;
  name: string;
  nameFr?: string;
  kind: ActivityKind;
  description: string;
  descriptionFr?: string;
  version: string;
  status: 'online' | 'degraded' | 'offline';
}

export const TOOL_REGISTRY: ToolDef[] = [
  { id: 'web_search', name: 'Web Search', nameFr: 'Recherche web', kind: 'search', description: 'Query the indexed web corpus with ranked retrieval', descriptionFr: 'Interroge le corpus web indexé avec classement', version: '2.4.1', status: 'online' },
  { id: 'browser', name: 'Browser', nameFr: 'Navigateur', kind: 'browser', description: 'Open sources and extract readable content', descriptionFr: 'Ouvre les sources et extrait le contenu lisible', version: '1.9.0', status: 'online' },
  { id: 'vfs_scan', name: 'File Search', nameFr: 'Recherche de fichiers', kind: 'file', description: 'Walk and search the project tree', descriptionFr: 'Parcourt et recherche dans l’arborescence du projet', version: '3.1.2', status: 'online' },
  { id: 'file_reader', name: 'File Reader', nameFr: 'Lecteur de fichiers', kind: 'file', description: 'Read and parse project files', descriptionFr: 'Lit et analyse les fichiers du projet', version: '3.1.2', status: 'online' },
  { id: 'file_editor', name: 'File Editor', nameFr: 'Éditeur de fichiers', kind: 'file', description: 'Create, edit, move and delete files', descriptionFr: 'Crée, modifie, déplace et supprime des fichiers', version: '3.1.2', status: 'online' },
  { id: 'terminal', name: 'Terminal', nameFr: 'Terminal', kind: 'terminal', description: 'Run shell commands in the project sandbox', descriptionFr: 'Exécute des commandes shell dans le bac à sable', version: '1.4.0', status: 'online' },
  { id: 'code_runner', name: 'Code Executor', nameFr: 'Exécuteur de code', kind: 'code', description: 'Execute JavaScript / TypeScript / shell snippets', descriptionFr: 'Exécute des extraits JavaScript / TypeScript / shell', version: '2.0.3', status: 'online' },
  { id: 'calculator', name: 'Calculator', nameFr: 'Calculatrice', kind: 'calculation', description: 'Exact arithmetic expression evaluation', descriptionFr: 'Évaluation exacte d’expressions arithmétiques', version: '1.2.0', status: 'online' },
  { id: 'analysis', name: 'Analysis Engine', nameFr: 'Moteur d’analyse', kind: 'analysis', description: 'Static analysis, diagnostics and comparisons', descriptionFr: 'Analyse statique, diagnostics et comparaisons', version: '4.0.1', status: 'online' },
  { id: 'attachment_upload', name: 'Secure File Upload', nameFr: 'Envoi sécurisé', kind: 'file', description: 'Validate and upload attachments to the private AI backend', descriptionFr: 'Valide et transmet les pièces jointes au backend IA privé', version: '1.0.0', status: 'online' },
  { id: 'attachment_inspector', name: 'Document Inspector', nameFr: 'Inspecteur de documents', kind: 'file', description: 'Inspect images, PDFs, documents and audio metadata', descriptionFr: 'Inspecte images, PDF, documents et métadonnées audio', version: '1.0.0', status: 'online' },
  { id: 'video_probe', name: 'Video Probe', nameFr: 'Sonde vidéo', kind: 'video', description: 'Read container metadata: duration, resolution, bitrate, codecs', descriptionFr: 'Lit les métadonnées : durée, résolution, débit, codecs', version: '1.1.0', status: 'online' },
  { id: 'video_frames', name: 'Frame Extractor', nameFr: 'Extracteur d’images', kind: 'video', description: 'Sample frames across the timeline as thumbnails', descriptionFr: 'Échantillonne des images de la timeline en vignettes', version: '1.1.0', status: 'online' },
  { id: 'video_editor', name: 'Video Editor', nameFr: 'Éditeur vidéo', kind: 'video', description: 'Trim and re-encode clips with MediaRecorder', descriptionFr: 'Découpe et ré-encode des clips via MediaRecorder', version: '1.1.0', status: 'online' },
  { id: 'memory_vault', name: 'Personal Memory', nameFr: 'Mémoire personnelle', kind: 'database', description: 'Inspect and recall long-term user facts and preferences', descriptionFr: 'Consulte et rappelle les faits et préférences utilisateur', version: '1.0.0', status: 'online' },
];

export function getTool(id: string): ToolDef | undefined {
  return TOOL_REGISTRY.find((t) => t.id === id);
}
