# Logique Generation Groupes et Seances

Document interne court pour expliquer le flux fonctionnel de generation automatique.

## 1) Generation des groupes (entree -> traitement -> sortie)

### Entree
- `formation_id`
- modules pedagogiques de la formation (`FormationModule`)
- inscriptions existantes
- auditeurs disponibles
- parametres generaux (`max_auditeurs_groupe_defaut`)

### Traitement
1. Charge les groupes existants.
   - si `reset=True`: suppression puis regeneration complete.
   - sinon: ajout des manquants uniquement.
2. Controle qu'il existe des modules de formation.
3. Construit/complete les inscriptions (backfill) selon compatibilite grade (`grade_cible_matches`).
4. Dedoublonne les auditeurs.
5. Selon **mixage des grades** (case a cocher ou `ParametreGeneral.groupes_auto_mixage_grades`) :
   - **non** : regroupement par grade, groupes nommes « Groupe N {grade} », repartition tournante des types de concours.
   - **oui** : regroupement par categorie, groupes nommes « Groupe N {cat} », mixage multi-grades a l'interieur de chaque categorie uniquement.
6. Cree les groupes et repartit les auditeurs (round-robin).
7. Lance la generation des seances pour chaque nouveau groupe.

### Sortie
- nombre de groupes crees
- membres affectes a chaque groupe
- planning genere (ou erreur explicite si blocage)

### Formation source (reprendre les auditeurs d'une autre formation)
- Filtre **Auditeurs disponibles** sur la page Groupes : chaque modale n'affiche que les auditeurs du **groupe homologue** (meme `Groupe.nom`) dans la formation source.
- A l'application du filtre (ou au report / copie d'inscriptions) : les groupes manquants sont **crees automatiquement** sur la formation cible avec les **memes noms**, capacite, **horaires**, **jours actifs** et **cadence mensuelle** que dans la source.
- Bouton **Creer un groupe** : creation manuelle d'un groupe vide (nom + capacite), puis affectation via **Gerer les membres**.
- Bouton **Reporter tous les groupes depuis la source** : cree les groupes homologues puis affecte en masse.
- Copie d'inscriptions depuis une formation source : apres inscription aux modules, creation des groupes homologues necessaires puis affectation.

### Regenerer une autre periode (meme formation, memes groupes)
- Modifier les dates de la formation et/ou des modules (`FormationModule.date_debut` / `date_fin`).
- Sur la page **Groupes**, utiliser **Regenerer le planning** (`groupes:regenerer_planning`) :
  relance `generer_pour_formation` en `best_effort` sans toucher aux `GroupeAuditeur`.
- Ne pas utiliser **Regenerer auto** : `reset=True` supprime et recree les groupes (nouvelle repartition auditeurs).

---

## 2) Generation des seances (entree -> traitement -> sortie)

### Entree
- `groupe_id`
- config groupe (horaires matin/soir + jours actifs)
- modules applicables au grade du groupe
- parametres (`max_seances_par_jour_defaut`, `duree_seance_defaut_minutes`)
- jours feries
- salles disponibles (parametrage)

### Traitement
1. Verifie que le groupe est configure (horaires + jours).
2. Filtre les modules compatibles grade.
3. Pour chaque module:
   - determine la fenetre de dates (module sinon formation),
   - place des seances jour par jour (matin/soir),
   - choisit une salle libre compatible.
4. Applique la regle metier de plafonnement:
   - **max 2 seances/jour par (module, salle)**.
   - cle de controle: `(date, module_id, salle_nom)`.
5. Si volume non place: renvoie une cause precise (salles, fenetre, jours actifs, etc.).

### Sortie
- mode normal: seances persistees en base
- mode preview/dry-run: seances calculees sans persistance
- rapport de couverture par module (preview)

---

## 3) Regles de lieux appliquees

- `site` obligatoire sur un module de formation.
- `batiment` et `salle` optionnels.
- si `salle` vide:
  - fallback automatique sur salles actives,
  - filtrage strict par `site`,
  - filtrage par `batiment` si renseigne.

---

## 4) Conflits affiches dans la preview

Le detecteur signale notamment:
- seance un jour ferie,
- seance hors plages horaires du groupe,
- salle deja occupee (chevauchement autre groupe),
- depassement du plafond quotidien **par (date, module, salle)**.

