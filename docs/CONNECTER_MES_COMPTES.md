# Connecter mes comptes à JARVIS

Ce guide dit, étape par étape, comment donner à JARVIS l'accès à tes comptes.
**Les clés se créent chez toi et se collent dans le fichier `.env` de ton PC —
jamais dans le chat, jamais sur GitHub.** JARVIS ne te les demandera jamais.

Ce qui est branché aujourd'hui :

| Compte | État | Connecteur |
|---|---|---|
| Page Facebook + Instagram | prêt, attend tes clés | `social/meta/meta_connector.py` |
| Site Netlify | à venir | — |
| LinkedIn | à venir | — |
| Fiche Google (Maps) | à venir | — |
| TikTok | à venir | — |

> Les écrans de Meta changent souvent. Si un bouton n'a plus le même nom,
> cherche l'intitulé le plus proche ; les **noms des autorisations** plus bas,
> eux, sont ceux que l'API demande.

---

## 1. Facebook et Instagram (Meta)

Un seul jeton sert les deux : Instagram passe par la page Facebook à laquelle
il est relié.

### Ce qu'il faut avant

1. Ton compte Instagram **unic_plaquiste** doit être un compte
   **professionnel** (Instagram → Paramètres → Type de compte).
2. Il doit être **relié à ta page Facebook** (Paramètres de la page →
   Comptes liés → Instagram).

### Créer l'application (une seule fois)

1. Va sur **developers.facebook.com** → Mes applications → Créer une
   application. Type : « Entreprise ». Nom : ce que tu veux (par exemple
   « JARVIS Unic »).
2. Dans l'application, ajoute les produits **Facebook Login** et
   **Instagram Graph API** si on te le propose.

### Obtenir le jeton

1. Ouvre **Outils → Explorateur de l'API Graph**.
2. Choisis ton application en haut à droite, puis « Obtenir un jeton
   d'utilisateur ». Coche ces autorisations :
   - pages_show_list, pages_read_engagement
   - pages_manage_posts (publier sur la page)
   - pages_manage_engagement (répondre aux commentaires Facebook)
   - instagram_basic, instagram_content_publish, instagram_manage_comments
3. Dans le champ de requête, tape `me/accounts` puis « Envoyer ». La réponse
   liste tes pages : note l'**id** de la page Unic Plaquiste et son
   **access_token** (c'est le jeton de PAGE, pas celui du haut).
4. Rends ce jeton durable : **Outils → Débogueur de jeton d'accès**, colle le
   jeton, bouton « Prolonger le jeton d'accès ». Un jeton de page issu d'un
   jeton d'utilisateur prolongé n'expire pas tant que tu ne changes pas ton mot
   de passe ou tes autorisations.
5. Pour l'identifiant Instagram, tape dans l'explorateur
   `<id de ta page>?fields=instagram_business_account` : la réponse donne
   l'**id** du compte Instagram.

### Le mettre dans JARVIS

Ouvre le fichier `.env` à la racine du projet sur ton PC (copie de
`.env.example` s'il n'existe pas) et remplis :

```
META_PAGE_ACCESS_TOKEN=le-jeton-de-page
META_PAGE_ID=l-id-de-la-page
META_IG_USER_ID=l-id-instagram
```

Relance ARENA. La santé du connecteur « meta » passe à « opérationnel » quand
Meta a répondu ; sinon elle dit le refus exact de Meta.

### Ce que JARVIS peut faire avec

| Action | Accord |
|---|---|
| Lire la page, le compte Instagram, les dernières publications et leurs chiffres | libre |
| Lire les commentaires d'une publication | libre |
| Publier un post Facebook | **ta confirmation, à chaque fois** |
| Publier une photo Instagram | **ta confirmation, à chaque fois** |
| Répondre à un commentaire | **ta confirmation, à chaque fois** |

Instagram publie une photo à partir d'une **adresse publique** (https://…) :
c'est une règle de l'API, pas de JARVIS.

### Le coupe-circuit des publications

Dans `config/permissions.yaml`, la ligne `PUBLISH: false` **interdit toute
publication**, même confirmée. Elle est coupée aujourd'hui, et JARVIS n'y
touche pas : c'est ta décision. Quand tu veux qu'il puisse publier, passe-la à
`PUBLISH: true`. Chaque publication te sera quand même présentée — le texte
exact — et ne partira qu'après ton accord.
