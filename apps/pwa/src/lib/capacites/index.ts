/* ─────────────────────────────────────────────────────────────
   Capacités — les entrées du menu de gauche.
   Une capacité n'active aucun mode caché : elle propose des
   phrases de départ. C'est la phrase qui oriente ARENA, comme
   quand tu écris toi-même. Rien n'est promis ici.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import { Code2, FileText, Globe, Hammer, Video, type LucideIcon } from 'lucide-react';

export interface Capacite {
  id: string;
  nomFr: string;
  nomEn: string;
  icone: LucideIcon;
  exemplesFr: string[];
  exemplesEn: string[];
}

export const CAPACITES: Capacite[] = [
  {
    id: 'code',
    nomFr: 'Usman Coder',
    nomEn: 'Usman Coder',
    icone: Code2,
    exemplesFr: [
      'Écris-moi un script Python qui renomme tous les fichiers d\'un dossier',
      'Explique-moi ce que fait ce code',
      'Corrige l\'erreur que je vais te coller',
    ],
    exemplesEn: [
      'Write a Python script that renames every file in a folder',
      'Explain what this code does',
      'Fix the error I am about to paste',
    ],
  },
  {
    id: 'plaquiste',
    nomFr: 'UniC Plaquiste',
    nomEn: 'UniC Plaquiste',
    icone: Hammer,
    exemplesFr: [
      'Calcule les matériaux pour 18 parois de 5,40 m sur 2,50 m',
      'Combien de plaques BA13 pour 120 m² de cloison ?',
      'Prépare un devis pour un plafond suspendu de 45 m²',
    ],
    exemplesEn: [
      'Compute the materials for 18 partitions of 5.40 m by 2.50 m',
      'How many BA13 boards for 120 m² of partition?',
      'Draft a quote for a 45 m² suspended ceiling',
    ],
  },
  {
    id: 'video',
    nomFr: 'Vidéo',
    nomEn: 'Video',
    icone: Video,
    exemplesFr: [
      'Analyse la vidéo que je vais joindre',
      'Résume-moi ce que montre cette vidéo de chantier',
      'Quelle est la durée et la résolution de ce fichier ?',
    ],
    exemplesEn: [
      'Analyse the video I am about to attach',
      'Summarise what this worksite video shows',
      'What is the duration and resolution of this file?',
    ],
  },
  {
    id: 'web',
    nomFr: 'Recherche web',
    nomEn: 'Web search',
    icone: Globe,
    exemplesFr: [
      'Cherche les derniers appels d\'offres BTP au Sénégal',
      'Quel est le prix actuel du ciment à Dakar ?',
      'Trouve-moi les nouveautés sur les plaques hydrofuges',
    ],
    exemplesEn: [
      'Search the latest construction tenders in Senegal',
      'What is the current price of cement in Dakar?',
      'Find what is new about moisture-resistant boards',
    ],
  },
  {
    id: 'documents',
    nomFr: 'Mes documents',
    nomEn: 'My documents',
    icone: FileText,
    exemplesFr: [
      'Cherche dans mes devis ce qui concerne les faux plafonds',
      'Résume le document que je vais joindre',
      'Retrouve le chantier où on a posé de la laine de verre',
    ],
    exemplesEn: [
      'Search my quotes for anything about suspended ceilings',
      'Summarise the document I am about to attach',
      'Find the worksite where we installed glass wool',
    ],
  },
];

interface CapaciteState {
  active: string | null;
  choisir: (id: string) => void;
  effacer: () => void;
}

export const useCapacite = create<CapaciteState>((set) => ({
  active: null,
  choisir: (id) => set({ active: id }),
  effacer: () => set({ active: null }),
}));

export function capaciteActive(id: string | null): Capacite | null {
  if (!id) return null;
  return CAPACITES.find((c) => c.id === id) ?? null;
}