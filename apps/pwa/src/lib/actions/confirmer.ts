/* Dire oui a ce qui attend — depuis l'interface, en un clic.
 *
 * Defaut repare le 02/09/2026 : le serveur exposait
 * `POST /api/actions/{id}/confirm` depuis le debut, et **aucun code de cette
 * application ne l'appelait**. Un devis PDF prepare sur le telephone
 * affichait un identifiant de 32 caracteres que rien ne permettait de saisir,
 * et attendait indefiniment. Le proprietaire n'a jamais pu obtenir un seul
 * PDF.
 *
 * Le bouton reste le chemin principal, y compris pour ce qu'une phrase n'a
 * pas le droit de confirmer (envoi d'un mail, publication, suppression) :
 * lui nomme exactement ce qu'il valide.
 */
import { activeRemoteCfg } from '../store/backendStore';

/** Une action preparee qui attend un accord. Miroir de `_actions_en_attente`. */
export interface ActionEnAttente {
  id: string;
  action: string;
  cible: string;
  risque: string;
  expire_le?: string;
  /** Le moteur qui executerait cette action repond-il ? Absent d'un serveur
   *  plus ancien — on considere alors qu'il repond, plutot que de retirer un
   *  bouton par ignorance. */
  disponible?: boolean;
  /** Pourquoi il ne repond pas. Vide quand il repond. */
  indisponible_raison?: string;
}

export interface ResultatConfirmation {
  ok: boolean;
  /** Ce qu'il faut afficher : le compte-rendu du serveur, ou la panne. */
  message: string;
  /** Adresse ouvrable du document produit, clé comprise. Absente s'il n'y en a pas. */
  document?: string;
}

/* Le PDF produit doit s'ouvrir DEPUIS SON TELEPHONE.
 *
 * Jusqu'au 02/09/2026 les devis atterrissaient dans `data/devis/`, qu'aucune
 * route ne sert : le fichier existait sur le disque du PC et nulle part
 * ailleurs. Ils sortent desormais dans `media/rendered/`, servi par
 * `GET /media/rendered/{nom}`.
 *
 * La cle voyage en parametre `cle` et non en en-tete : un lien qu'on tape
 * navigue, il n'est pas appele en `fetch()` et ne peut donc poser aucun
 * en-tete. `verify_media_access` existe exactement pour ce cas. */
function adresseOuvrable(url: string | undefined, base: string, cle?: string): string | undefined {
  if (!url) return undefined;
  const complet = url.startsWith('http') ? url : `${base}${url}`;
  if (!cle) return complet;
  return `${complet}${complet.includes('?') ? '&' : '?'}cle=${encodeURIComponent(cle)}`;
}

async function appeler(id: string, quoi: 'confirm' | 'cancel'): Promise<ResultatConfirmation> {
  const cfg = activeRemoteCfg();
  if (!cfg) {
    return { ok: false, message: 'Aucun backend connecté : impossible de confirmer.' };
  }
  const base = cfg.url.replace(/\/+$/, '');
  try {
    const res = await fetch(`${base}/api/actions/${encodeURIComponent(id)}/${quoi}`, {
      method: 'POST',
      headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
    });
    const corps = await res.json().catch(() => null);
    if (!res.ok) {
      // Le serveur dit toujours pourquoi : on relaie sa raison plutot qu'un
      // code HTTP, que le proprietaire n'a aucune raison de savoir lire.
      return { ok: false, message: corps?.detail || `Le serveur a refusé (${res.status}).` };
    }
    return {
      ok: true,
      message: corps?.response || corps?.message || 'C’est fait.',
      document: adresseOuvrable(corps?.detail?.url, base, cfg.apiKey),
    };
  } catch {
    return { ok: false, message: 'Le serveur n’a pas répondu.' };
  }
}

/** Le « oui ». C'est le seul chemin, avec la phrase, qui execute quoi que ce soit. */
export const confirmerAction = (id: string) => appeler(id, 'confirm');

/** Le « non ». Le brouillon est efface avec l'action (garantie 5 de la file). */
export const annulerAction = (id: string) => appeler(id, 'cancel');
