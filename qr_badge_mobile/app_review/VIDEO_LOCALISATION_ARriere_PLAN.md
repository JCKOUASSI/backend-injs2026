# Vidéo Play Console — localisation en arrière-plan (application mobile INJS — Présences)

Document de tournage pour le formulaire Google Play **« Accès aux données de localisation en arrière-plan »**.

Durée cible : **20 à 30 secondes**. Plateforme : **Android réel** (12+ recommandé).

---

## Ce que Google doit voir

| Exigence Google | Élément à filmer dans l’app |
|-----------------|----------------------------|
| Fonctionnalité déclarée en action | Connexion → scan QR → badgeage entrée → suivi de présence actif |
| Usage de la localisation en arrière-plan | Notification « Suivi de présence actif » + app en arrière-plan / écran verrouillé |
| Divulgation bien visible **avant** la demande « Toujours » | Dialogue **« Suivi en arrière-plan »**, puis invite système Android |
| Autorisation appareil + consentement utilisateur | Dialogue **« Autoriser la localisation »** → **« Pendant l’utilisation »** → **« Toujours autoriser »** (+ notifications si demandé) |

---

## Prérequis avant tournage

- Téléphone **Android physique** (pas émulateur).
- Application **INJS — Présences** installée, backend INJS-LMD accessible.
- Compte de test (auditeur, formateur ou encadrant).
- **QR code valide** d’une séance en cours.
- Réinitialiser les autorisations : *Paramètres → Apps → INJS Présences → Autorisations → Localisation → Aucune*.
- Enregistrement **écran + voix** (OBS, enregistreur natif Android, etc.).

---

## Storyboard (25–30 s)

### Plan 1 — Divulgation « premier plan » (0:00 – 0:08)

1. Ouvrir **INJS Présences** (premier lancement ou après reset des permissions).
2. Montrer le dialogue **« Autoriser la localisation »** :
   > *« L’application INJS de présence a besoin de votre position GPS pour valider votre présence sur le site de formation lors du badgeage et du suivi de session. »*
3. Appuyer sur **Continuer**.
4. Montrer l’invite **système Android** → choisir **« Pendant l’utilisation de l’app »**.

**Voix off :**  
*« Avant toute collecte GPS, l’application affiche une explication claire, puis demande le consentement via l’écran système Android. »*

---

### Plan 2 — Divulgation arrière-plan + « Toujours autoriser » (0:08 – 0:15)

5. Montrer le dialogue **« Suivi en arrière-plan »** :
   > *« Pour valider votre présence pendant toute la séance (même écran verrouillé), L’application INJS de présence a besoin de l’autorisation « Toujours autoriser » pour la position. Sur l’écran suivant, choisissez « Toujours autoriser ». »*
6. Appuyer sur **Continuer**.
7. Montrer l’invite système **« Autoriser tout le temps » / « Toujours autoriser »** → **accepter**.
8. Si demandé : autorisation **Notifications** (Android 13+) → **Autoriser**.

**Voix off :**  
*« Une seconde divulgation, visible à l’écran, précède la demande de localisation en arrière-plan. L’utilisateur choisit explicitement « Toujours autoriser ». »*

---

### Plan 3 — Fonctionnalité en action (0:15 – 0:22)

9. Se **connecter**.
10. Onglet **Scanner** → scanner le **QR** de séance.
11. Montrer le bandeau géolocalisation (*« Vous êtes dans la zone de badgeage »* ou équivalent).
12. Confirmer **« Badger l’entrée »**.
13. Montrer la confirmation **« Entrée enregistrée »** et le message **« Suivi de présence actif »**.

**Voix off :**  
*« La localisation sert à valider le badgeage sur le lieu de formation et à activer le suivi de session. »*

---

### Plan 4 — Localisation en arrière-plan (0:22 – 0:30)

14. Afficher la **notification persistante** :
    - Titre : **« INJS Présences »**
    - Texte : **« Suivi de présence actif »**
15. Mettre l’app en **arrière-plan** (bouton Home) ou **verrouiller l’écran** 2–3 secondes.
16. Rouvrir l’app : le bandeau **« Suivi de présence actif »** est toujours visible.

**Voix off :**  
*« Pendant la séance, l’app envoie périodiquement la position GPS au serveur INJS-LMD pour attester la présence continue, même si l’application n’est pas au premier plan. Android affiche un service de localisation en notification. »*

---

## Texte à coller dans Play Console (champ « Instructions vidéo »)

```
La vidéo montre : (1) les dialogues in-app « Autoriser la localisation » puis
« Suivi en arrière-plan » affichés AVANT les invites système ; (2) l’acceptation
des autorisations Android (position pendant l’utilisation, puis Toujours autoriser) ;
(3) un badgeage QR avec validation géolocalisée ; (4) la notification persistante
« Suivi de présence actif » pendant que l’app est en arrière-plan, illustrant
l’envoi périodique de la position GPS au serveur pour le heartbeat de présence.
```

---

## Publication YouTube

- **Publique** ou **non répertoriée**.
- **Sans limite d’âge**, **sans publicité**.
- Coller l’URL dans le champ « Instructions vidéo » du formulaire Play Console.

---

## Conseils pour l’acceptation Google

- **Ne pas couper** entre la divulgation in-app et l’invite système : elles doivent apparaître **à la suite**.
- Si « Toujours autoriser » n’apparaît pas : accorder d’abord **« Pendant l’utilisation »** (ordre Android obligatoire).
- Voix off ou **sous-titres** en français ou anglais.

---

## Rappel technique (voix off / notes internes)

| Moment | Comportement |
|--------|--------------|
| Badgeage entrée | GPS envoyé à `/api/scan/secure/` |
| Session ouverte | Heartbeat périodique avec lat/lon → `/api/scan/secure/heartbeat/` |
| Android | Foreground service + notification « Suivi de présence actif » |
| Fin | Badgeage sortie ou fin de session → notification disparaît |

Fichiers source : `lib/utils/location_permission.dart`, `lib/services/background_keepalive.dart`, `lib/providers/session_provider.dart`.
