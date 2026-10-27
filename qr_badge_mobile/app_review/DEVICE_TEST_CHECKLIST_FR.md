# Checklist tests sur device — application mobile INJS — Présences

Environnement : iPhone / Android physique, API configurée dans `assets/app.env` (`API_BASE_URL`).

Cocher chaque scénario après validation. Noter la date, l’appareil et la version (`pubspec.yaml`).

---

## 1. Connexion et démarrage

- [ ] **Login** — identifiants valides → accueil sans crash
- [ ] **GPS au 1er lancement** — dialogue explicatif puis prompt système
- [ ] **Refus GPS** — bandeau orange global + bouton « Activer »
- [ ] **Hot restart** (`R`) — session JWT conservée, pas de re-login

## 2. Badgeage entrée / sortie

- [ ] **Scan entrée** — QR valide, confirmation, message succès
- [ ] **Bandeau vert** — « En salle · … » visible sur tous les onglets
- [ ] **Heartbeat** — bandeau reste après 2–3 min au premier plan
- [ ] **Scan sortie** — bouton dynamique « Badger ma sortie », session fermée, bandeau disparaît
- [ ] **Historique** — entrée/sortie visibles, filtres Tous / Entrées / Sorties / Alertes

## 3. Reprise de session (kill app)

- [ ] Badger une **entrée** → bandeau vert
- [ ] **Fermer l’app** complètement (swipe multitâche)
- [ ] **Rouvrir** → snackbar « Session reprise — … » + bandeau vert **sans** re-scanner
- [ ] Accueil → carte « Session en cours » + CTA « Badger ma sortie »
- [ ] Badger la **sortie** → rouvrir l’app → **pas** de reprise

## 4. GPS et suivi suspendu

- [ ] Session ouverte → **désactiver GPS** (Réglages)
- [ ] Attendre ~30 s → bandeau orange « GPS indisponible »
- [ ] Bouton **Activer** → réglages → réactiver GPS → bandeau orange disparaît
- [ ] Mettre l’app en **arrière-plan** 5 min → revenir → heartbeat reprend (logs backend si dispo)

## 5. Navigation et profil

- [ ] **4 onglets** — Scanner, Accueil, Historique, Profil
- [ ] **Menu ⋮** — Évaluations (si auditeur), GPS, Confidentialité, Déconnexion (code `2026`)
- [ ] **Profil** — « Modifier mes informations » → PATCH réussi
- [ ] **Formateur** — édition bancaire si applicable
- [ ] **Pull-to-refresh** — Accueil et Historique

## 6. Évaluations (auditeurs)

- [ ] Badge menu ⋮ si questionnaires en attente
- [ ] Remplir un questionnaire → compteur décrémenté

## 7. Régression rapide

- [ ] Caméra Scanner s’arrête hors onglet Scanner (économie batterie)
- [ ] Déconnexion → retour login, bandeau session absent
- [ ] Mode avion au boot avec session sauvegardée → reprise locale (hors-ligne)

---

## Commandes utiles

```bash
cd qr_badge_mobile
flutter run                    # device branché
flutter test                   # tests unitaires
flutter analyze lib/
```

## Logs Flutter (iPhone)

Si pas de logs VM Service : macOS → Réglages → Confidentialité → **Réseau local** → autoriser Terminal / Cursor.
