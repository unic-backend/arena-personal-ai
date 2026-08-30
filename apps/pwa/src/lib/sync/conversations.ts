/* Synchronisation des conversations entre ses appareils.

   Les conversations vivent dans le `localStorage` de chaque navigateur : le
   telephone et le PC n'en partageaient donc aucune, avec la meme adresse et la
   meme cle. Ce module les fait transiter par le serveur (`/conversations/sync`,
   VOLET synchro phase 2), qui arbitre a la date de derniere ecriture.

   Trois regles, et elles disent toutes la meme chose — **la synchronisation ne
   doit jamais couter une conversation** :

   1. une panne de reseau ne change rien localement. On rend `null`, on garde ce
      qu'on a, et on reessaiera au prochain declenchement ;
   2. une conversation locale absente de la reponse du serveur est **conservee**,
      jamais supprimee. Seule une pierre tombale explicite efface quelque chose ;
   3. un serveur trop ancien, qui ne connait pas la route, n'est pas une erreur a
      montrer : la synchronisation se tait pour la session.
*/
import type { Conversation } from '../store/chatStore';

/** Ce que le serveur peut rendre a la place d'une conversation supprimee. */
interface PierreTombale {
  id: string;
  supprimee: true;
  updatedAt: number;
}

type Entree = Conversation | PierreTombale;

function estTombale(entree: Entree): entree is PierreTombale {
  return (entree as PierreTombale).supprimee === true;
}

export interface ConfigSync {
  url: string;
  apiKey?: string;
}

export interface ResultatSync {
  conversations: Conversation[];
  /** Identifiants que le serveur a refuses — trop gros. Jamais tus. */
  refusees: string[];
  /** Identifiants dont le serveur confirme la suppression. */
  supprimees: string[];
}

/** Vrai quand ce serveur ne connait pas encore la synchronisation. */
let routeAbsente = false;

export function reinitialiserDetectionDeRoute(): void {
  routeAbsente = false;
}

/**
 * Envoie les conversations locales et rend la verite fusionnee du serveur.
 *
 * Rend `null` quand rien ne doit changer : reseau coupe, serveur muet, ou
 * serveur trop ancien. L'appelant garde alors son etat intact.
 */
export async function pousserEtTirer(
  locales: Conversation[],
  tombales: PierreTombale[],
  cfg: ConfigSync,
  signal?: AbortSignal,
): Promise<ResultatSync | null> {
  if (routeAbsente || !cfg.url) return null;

  const base = cfg.url.replace(/\/+$/, '');
  let reponse: Response;
  try {
    reponse = await fetch(`${base}/conversations/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {}),
      },
      body: JSON.stringify({ conversations: [...locales, ...tombales] }),
      signal,
    });
  } catch {
    // Reseau coupe : ce n'est pas une raison de toucher a ses conversations.
    return null;
  }

  if (reponse.status === 404) {
    // Serveur deploye avant la phase 2. On cesse d'essayer pour cette session
    // plutot que d'echouer a chaque message.
    routeAbsente = true;
    return null;
  }
  if (!reponse.ok) return null;

  let corps: { conversations?: Entree[]; refusees?: string[] };
  try {
    corps = await reponse.json();
  } catch {
    return null;
  }

  const entrees = Array.isArray(corps.conversations) ? corps.conversations : [];
  const refusees = Array.isArray(corps.refusees) ? corps.refusees : [];

  const supprimees = new Set(entrees.filter(estTombale).map((e) => e.id));
  const duServeur = new Map(
    entrees.filter((e): e is Conversation => !estTombale(e)).map((c) => [c.id, c]),
  );

  // Une locale absente de la reponse est gardee : un refus, ou un alea du
  // serveur, ne doit pas effacer ce que le proprietaire a ecrit ici.
  const conservees = locales.filter((c) => !duServeur.has(c.id) && !supprimees.has(c.id));

  return {
    conversations: [...conservees, ...duServeur.values()].sort(
      (a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0),
    ),
    refusees,
    supprimees: [...supprimees],
  };
}
