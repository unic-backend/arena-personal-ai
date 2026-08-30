import { Component, ReactNode } from 'react';

/* Un message qui ne s'affiche pas ne doit pas emporter l'ecran avec lui.

   Mesure du 30/08/2026, sur le telephone du proprietaire : une reponse de
   recherche web rendait l'ecran entierement noir, et le rouvrir le renoircissait
   — la conversation etant enregistree, le plantage revenait a chaque affichage.
   Cause : `DomainMark` lisait `domain.length` sur une source qui n'en portait
   pas. Une seule exception pendant le rendu, et React demonte tout l'arbre :
   l'application n'affichait plus rien du tout, sans un mot d'explication.

   La cause precise est corrigee ailleurs. Ceci est la garde : **aucune erreur de
   rendu ne peut plus faire disparaitre l'interface**. Le message fautif est
   remplace par un encadre qui dit ce qui s'est passe, et le reste de la
   conversation continue de s'afficher. */
interface Props {
  children: ReactNode;
  /** Ce qui remplace l'enfant en echec. Par defaut : un encadre discret. */
  repli?: (erreur: Error) => ReactNode;
}

interface State {
  erreur: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { erreur: null };

  static getDerivedStateFromError(erreur: Error): State {
    return { erreur };
  }

  componentDidCatch(erreur: Error) {
    // La console garde la trace complete : sans elle, le diagnostic du
    // 30/08/2026 aurait ete impossible.
    console.error('Rendu interrompu :', erreur);
  }

  render() {
    const { erreur } = this.state;
    if (!erreur) return this.props.children;
    if (this.props.repli) return this.props.repli(erreur);
    return (
      <div className="rounded-xl border border-red-400/20 bg-red-400/[0.04] px-3.5 py-2.5 text-[12px] text-red-300/90">
        Ce message n'a pas pu s'afficher. Le reste de la conversation est intact.
        <div className="mt-1 font-mono text-[10.5px] text-zinc-500">{erreur.message}</div>
      </div>
    );
  }
}
