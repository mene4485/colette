# 07 — Notes pour le pitch et le Q&A

## Structure de pitch (3–5 min)
1. **Persona** : "Géraldine, 78 ans, veut résilier son abonnement Free. Elle n'y arrive pas. Avant, elle appelait son petit-fils ou allait en maison France Services."
2. **Le chiffre** : 13 M de Français en difficulté avec le numérique ; 1/3 ont déjà renoncé à une démarche ; France Services = 800 000 démarches/mois avec RDV et files d'attente.
3. **Colette** : elle appelle un numéro. Elle parle. L'agent fait. Démo live.
4. **Ce qui est nouveau** : voix + computer use + l'utilisateur garde le contrôle (narration, barre d'étapes, confirmation orale, stop).
5. **Généralisable** : opérateurs, administrations, banques, assurances. Marché secondaire : tous ceux qui n'ont pas le temps.
6. **Business** : B2B2C (l'opérateur / l'administration intègre Colette sur son site — "un bouton Appelez Colette"). Stripe pour la facturation. Clin d'œil : Xavier Niel = 42 + Free.

## Déroulé de la démo live (à répéter)
- Écran partagé en 2 : page web avec barre d'étapes + navigateur de l'agent H.
- Un membre tient le téléphone sur haut-parleur (ou clique le bouton vocal).
- Dialogue court et scripté : demande → l'agent navigue et narre → demande une info → **demande confirmation** → résumé.
- Durée cible : < 3 min. Vidéo de secours prête.

## Questions probables du jury et réponses
- **Les sites ne vont-ils pas bloquer l'agent ?** Test réel sur free.fr : l'agent navigue sans blocage. Vision : les sites intègrent eux-mêmes Colette (B2B2C), donc pas de contournement.
- **Et les mots de passe ?** Jamais dictés, jamais vus par l'agent. Session authentifiée côté utilisateur / SSO côté opérateur. Pour la démo : compte de test pré-connecté.
- **Et si l'agent se trompe ?** Il ne fait jamais seul une action irréversible : confirmation orale explicite. L'utilisateur peut dire "stop" à tout moment. Replay complet de la session (plateforme H) pour audit.
- **Pourquoi la voix / le téléphone ?** C'est l'outil que ce public maîtrise déjà. Zéro interface à apprendre.
- **Pourquoi pas juste un humain ?** France Services : RDV, déplacement, attente. Les proches n'ont pas toujours le temps, et il faut leur confier ses identifiants.
- **Fiabilité ?** Une démarche à la fois, définie à l'avance (skills), gardes-fous, confirmation. On commence par les démarches courtes et à fort volume.
- **Business model ?** L'opérateur/l'administration paie (réduction des appels au service client, inclusion numérique obligatoire). Stripe pour la facturation.
- **Quels partenaires ?** H (computer use), Gladia (STT temps réel), Pipecat + Daily (voix), Linkup (recherche de la procédure / comparaison d'offres), Stripe (facturation), Devin (dev parallèle si utilisé).
- **Et après ?** Historique des démarches, rappel proactif, extension Chrome, autres démarches (CAF, Ameli, retraite).

## Social media (500 € chacun)
- LinkedIn : vidéo 30 s de la démo + 3 lignes sur le problème (13 M). Tag H Company, 42AI, Gladia, Cognition, Linkup.
- X : même vidéo, une phrase.
