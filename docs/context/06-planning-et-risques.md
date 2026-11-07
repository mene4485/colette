# 06 — Planning du week-end et risques

## Timeline (Paris time)
| Quand | Milestone | Critère de succès |
|---|---|---|
| Sam 10h30–12h30 | Faisabilité H sur Free | Un run H fait la navigation jusqu'à la page de résiliation. Durée mesurée. |
| Sam 12h30 | **Point d'étape équipe** | Go / réduire les ambitions / pivoter. |
| Sam 14h–19h | Voix ↔ H connectés | Bot Pipecat lance run_demarche, narre les étapes, demande confirmation. |
| Sam 19h–21h | Page web + barre d'étapes + stop | Le jury peut voir la progression. Fermeture du lieu à 21h. |
| Dim 8h–11h | Fiabilisation | Démo répétée **3 fois sans échec**. Script vocal rodé. |
| Dim 11h–13h | Freeze + README + vidéo de secours | Repo propre, README avec partenaires (H, Gladia, Linkup/Stripe, Devin). |
| Dim 13h–14h | Soumission | Avant 14h00. Rien d'autre. |
| Dim 14h30–15h45 | Pitch prep | Rôles : qui parle, qui lance la démo, qui tient le téléphone. |
| Dim 15h45 | Pitches finaux | Démo live + vidéo prête en fallback. |

## Risques et fallbacks
| Risque | Probabilité | Fallback |
|---|---|---|
| Free bloque l'agent (bot detection, captcha, 2FA) | Moyenne | Compte de test ; session pré-authentifiée ; sinon **site maquette "espace client"** fidèle à Free. |
| Résiliation irréversible sur un vrai compte | Haute | S'arrêter avant la validation finale (c'est le point de confirmation du scénario) ou utiliser une démarche réversible (changer d'offre, télécharger une facture). |
| Dial-in téléphonique trop long à configurer | Moyenne | Bouton vocal WebRTC sur la page. Raconter le téléphone comme roadmap. |
| Latence H > 1 min sans feedback | Haute | Narration par étapes + TTS pendant l'exécution ; barre de progression. |
| Wi-Fi / démo live qui plante | Moyenne | Vidéo enregistrée dimanche matin, prête sur un laptop. |
| Pas de pause native dans l'API H | Moyenne | Découper en 2 runs (jusqu'à confirmation / après confirmation). |
| Temps : trop d'ambition UX | Haute | MVP d'abord. Extension Chrome = roadmap, pas livrable. |

## Livrables minimum pour soumettre
- Repo GitHub public avec README : problème, démo, archi, partenaires utilisés, comment lancer.
- Démo live fonctionnelle (ou vidéo).
- Pitch 3–5 min + réponses préparées (voir 07).
- Posts LinkedIn / X (500 € chacun, faible effort).
