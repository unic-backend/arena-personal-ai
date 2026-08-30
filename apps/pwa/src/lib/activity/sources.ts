import type { SourceMeta } from './types';

/* Le serveur decrit ses sources par une ADRESSE ; l'interface les affiche par
   un DOMAINE. Personne ne faisait la conversion, si bien que `domain` arrivait
   absent dans un composant qui le croyait toujours present — et le rendu
   s'interrompait (mesure du 30/08/2026 : ecran entierement noir sur le
   telephone du proprietaire, qui revenait a chaque reouverture puisque la
   conversation est enregistree).

   La conversion vit ici, en un seul endroit, et elle est appliquee aux **deux**
   frontieres par lesquelles une source entre dans l'application :

   - la reception du flux (`remoteTransport`), pour les reponses nouvelles ;
   - la lecture du stockage (`chatStore`), pour celles deja enregistrees sans
     domaine — sans quoi elles afficheraient « ? » pour toujours. */

/** Le domaine d'une adresse, ou `undefined` si elle est illisible. */
export function domaineDe(url: unknown): string | undefined {
  if (typeof url !== 'string' || !url) return undefined;
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    // Une adresse illisible n'est pas une panne : la source garde son titre et
    // s'affiche sans domaine.
    return undefined;
  }
}

/** Complete les sources d'un domaine deduit, sans jamais ecraser l'existant. */
export function normaliserSources(sources: unknown): SourceMeta[] | undefined {
  if (!Array.isArray(sources)) return undefined;
  return sources
    .filter((s): s is Record<string, unknown> => !!s && typeof s === 'object')
    .map((s) => ({
      ...s,
      title: typeof s.title === 'string' && s.title ? s.title : String(s.url ?? ''),
      domain: typeof s.domain === 'string' && s.domain ? s.domain : domaineDe(s.url),
    })) as SourceMeta[];
}
