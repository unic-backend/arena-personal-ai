# Connecter mes comptes à JARVIS

Ce guide dit, étape par étape, comment donner à JARVIS l'accès à tes comptes.
**Les clés se créent chez toi et se collent dans le fichier `.env` de ton PC —
jamais dans le chat, jamais sur GitHub.** JARVIS ne te les demandera jamais.

Ce qui est branché aujourd'hui :

> **Facebook et Instagram répondent déjà à une phrase** : « écris une
> publication sur mon chantier et publie-la sur Facebook », « analyse mes
> publications Instagram ». Tes sites aussi : « mon site est en ligne ? »,
> « le dernier déploiement de mon site a marché ? », « les messages de mon
> site », « republie mon site ». LinkedIn : « publie-la sur LinkedIn ». Ta
> fiche Google : « mes avis Google », « réponds à l'avis de Fatou : merci ! ». Mettre tes clés maintenant
> permet déjà de vérifier que la connexion marche (santé des connecteurs).

| Compte | État | Connecteur |
|---|---|---|
| Page Facebook + Instagram | prêt, attend tes clés — **joignable par une phrase** | `social/meta/meta_connector.py` |
| Sites Netlify | prêt, attend ta clé — **joignable par une phrase** | `core/connectors/netlify.py` |
| LinkedIn (ton profil) | prêt, attend ta clé — **joignable par une phrase** | `social/linkedin/linkedin_connector.py` |
| Fiche Google (Maps) | prêt, attend la connexion et l'accord de Google — **joignable par une phrase** | `core/connectors/fiche_google.py` |
| TikTok | prêt, attend ton application et la connexion | `social/tiktok/tiktok_connector.py` |

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

---

## 2. Tes sites web (Netlify)

Un seul jeton ouvre tous les sites de ton compte Netlify (www, app, expert…).

### Obtenir le jeton

1. Va sur **app.netlify.com** → ton avatar → **User settings** →
   **Applications** → **Personal access tokens** → **New access token**.
2. Donne-lui un nom (« JARVIS ») et une durée. Copie-le tout de suite :
   Netlify ne le remontre plus.

### Le mettre dans JARVIS

Dans le fichier `.env` de ton PC :

```
NETLIFY_AUTH_TOKEN=le-jeton
NETLIFY_SITE_ID=
```

Relance ARENA, puis demande à JARVIS la liste de tes sites : il te donnera
l'identifiant de chacun. Mets celui de www.unicplaquiste.com dans
NETLIFY_SITE_ID ; les autres restent joignables en les nommant.

### Ce que JARVIS peut faire avec

| Action | Accord |
|---|---|
| Lister tes sites, lire l'état d'un site | libre |
| Lire les derniers déploiements, et l'erreur de ceux qui ont échoué | libre |
| Lire les messages reçus par les formulaires du site | libre |
| Relancer la construction et la mise en ligne du site | **ta confirmation, à chaque fois** |

JARVIS ne modifie ni les fichiers, ni les réglages, ni le domaine, et ne
supprime rien. Relancer la mise en ligne passe aussi par le coupe-circuit
`PUBLISH` de `config/permissions.yaml` (voir plus haut).

Les messages des formulaires sont écrits par tes visiteurs : JARVIS les lit
comme des informations, jamais comme des ordres, et l'adresse IP du visiteur
ne lui est pas transmise.

---

## 3. LinkedIn (ton profil)

### Ce que LinkedIn permet — et ce qu'il ne permet pas

Une application LinkedIn ordinaire peut **publier sur ton profil**. Lire tes
posts, leurs statistiques ou leurs commentaires, et publier au nom d'une page
entreprise, demandent une autorisation que LinkedIn n'accorde qu'après examen
de l'application. JARVIS ne fait donc que publier sur ton profil, avec ton
accord à chaque fois.

### Obtenir le jeton

1. Va sur **linkedin.com/developers** → **Create app**. LinkedIn demande de
   relier l'application à une page entreprise (celle d'UniC Plaquiste, par
   exemple).
2. Onglet **Products** : ajoute **Sign In with LinkedIn using OpenID Connect**
   et **Share on LinkedIn**.
3. Onglet **Auth** → **OAuth 2.0 tools** (générateur de jeton) : coche
   openid, profile et w_member_social, puis crée le jeton.
4. Ce jeton **expire après 60 jours** : il faudra le refaire. Quand il a
   expiré, la santé du connecteur le dit (refus 401 de LinkedIn).

> Les écrans de LinkedIn changent aussi : cherche l'intitulé le plus proche.
> Les noms des autorisations, eux, sont ceux que l'API demande.

### Le mettre dans JARVIS

Dans le fichier `.env` de ton PC :

```
LINKEDIN_ACCESS_TOKEN=le-jeton
```

### Ce que JARVIS peut faire avec

| Action | Accord |
|---|---|
| Dire à quel compte LinkedIn il est relié | libre |
| Publier un post sur ton profil (avec un lien si tu en donnes un) | **ta confirmation, à chaque fois** |

« Écris une publication sur mon chantier et publie-la sur LinkedIn avec
https://www.unicplaquiste.com » : JARVIS écrit le texte dans ta voix, le
relit, puis te le montre avant tout envoi. Le coupe-circuit `PUBLISH` de
`config/permissions.yaml` s'applique aussi.

---

## 4. Ta fiche Google (Maps)

### Ce qu'il faut savoir d'abord

JARVIS utilise **le même compte Google que ton courrier** : pas de nouvelle
clé à copier. Mais **Google n'ouvre les API de fiche d'établissement qu'après
avoir examiné ton projet**. Tant qu'il n'a pas dit oui, JARVIS te répondra le
refus de Google (souvent « quota » à zéro) : ce n'est pas une panne.

### Les étapes

1. Sur **console.cloud.google.com**, dans le projet de ton identifiant Google
   (celui de Gmail) : **API et services → Bibliothèque**, active
   « My Business Account Management API », « My Business Business
   Information API » et « Google My Business API ».
2. Demande l'accès aux **API Business Profile** à Google (formulaire de
   demande d'accès, lié depuis la documentation « Business Profile APIs »).
   Attends leur accord.
3. Dans l'écran de consentement OAuth du projet, ajoute la portée
   business.manage.
4. Dans ARENA : **Réglages → Connecteurs → Google Business Profile →
   Connecter**. Google te demande d'accepter la nouvelle autorisation ; ton
   courrier reste connecté.

> Les noms des écrans Google changent : cherche l'intitulé le plus proche.

### Ce que JARVIS peut faire avec

| Action | Accord |
|---|---|
| Lire ta fiche (nom, adresse, site) | libre |
| Lire tes avis, avec ta note et leur nombre tels que Google les calcule | libre |
| Répondre publiquement à un avis | **ta confirmation, à chaque fois** |

« Réponds à l'avis de Fatou : merci pour ta confiance ! » : JARVIS retrouve
l'avis, te montre la réponse exacte et attend ton accord. Si deux clients ont
le même prénom, il te demande le nom complet au lieu de choisir. Le
coupe-circuit `SEND_MESSAGES` de `config/permissions.yaml` s'applique.

Les avis sont écrits par n'importe qui : JARVIS les lit comme des
informations, jamais comme des ordres. Il ne modifie pas ta fiche (horaires,
adresse, photos) et ne supprime rien.

---

## 5. TikTok

### Ce que TikTok permet — et ce qu'il ne permet pas

JARVIS publie tes vidéos par l'API officielle de TikTok. **Tant que TikTok n'a
pas audité ton application, toute vidéo publiée par l'API reste privée**
(visible par toi seul) : c'est une règle de TikTok. Pour publier en public
sans attendre l'audit, JARVIS peut **déposer la vidéo dans ta boîte TikTok** :
tu la retrouves dans l'application et tu la publies toi-même, en public.

### Créer l'application (une seule fois)

1. Va sur **developers.tiktok.com** → **Manage apps** → **Connect an app**.
2. Ajoute les produits **Login Kit** et **Content Posting API**, avec les
   scopes video.publish (publier) et video.upload (déposer un brouillon).
3. Note la **Client key** et le **Client secret**, et mets-les dans le
   fichier `.env` de ton PC :

```
TIKTOK_CLIENT_KEY=la-client-key
TIKTOK_CLIENT_SECRET=le-client-secret
```

### Relier ton compte

1. Dans ton application TikTok (onglet **Login Kit**), ajoute l'URI de
   redirection : l'adresse publique d'ARENA suivie de
   /connectors/tiktok/callback (celle de PUBLIC_BASE_URL dans `.env`).
   TikTok n'accepte que des adresses en https.
2. Dans ARENA : **Réglages → Connecteurs → TikTok → Connecter**. TikTok te
   demande d'accepter ; ARENA garde le jeton de renouvellement tout seul,
   jamais dans le navigateur.
3. Ensuite, JARVIS renouvelle lui-même le jeton du jour (un jeton d'accès
   TikTok expire après 24 heures), et garde le nouveau jeton de
   renouvellement si TikTok le change.

### Ce que JARVIS peut faire avec

| Action | Accord |
|---|---|
| Dire quel compte TikTok est relié, et ce qu'il peut publier | libre |
| Dire où en est une vidéo envoyée (en traitement, publiée, rejetée) | libre |
| Publier une vidéo (privée tant que l'application n'est pas auditée) | **ta confirmation, à chaque fois** |
| Déposer une vidéo dans ta boîte TikTok, sans la publier | **ta confirmation, à chaque fois** |

Une vidéo envoyée n'est pas une vidéo en ligne : TikTok la traite d'abord.
JARVIS ne dit « publiée » que quand TikTok le dit. Le coupe-circuit `PUBLISH`
de `config/permissions.yaml` s'applique aux deux envois.

