# Génération EDT 2026-2027 — état du diagnostic (15 novembre 2026)

## Mesure de la démo (année ID 1)

Deux campagnes globales distinctes (2 et 3) rapportent chacune 177 groupes, 3 groupes planifiés, 90 séances placées sur 39 146 attendues ; 174 groupes sans placement. La campagne ciblée 4 rapporte 6 séances sur 140. La base a 4 EDT brouillons et 25 affectations actives au moment de la lecture. Les totaux de campagnes ne représentent **pas** les séances actives actuellement ; ne pas les additionner. Aucun routage public des conteneurs candidats n'a été confirmé.

## Causes identifiées dans le code

1. `generation._backtrack` annulait toutes les séances d'un groupe dès qu'un besoin échouait (même si d'autres besoins étaient faisables). Désormais le meilleur préfixe exploré est conservé et, dans le budget restant, les besoins faisables suivants sont essayés avec les mêmes contraintes. Un plan partiel n'est pas annoncé comme complet.
2. `_construire_resultat` identifiait les besoins placés par `affectation_pedagogique_id`, valeur `None` commune à toutes les ECUE des cohortes importées : un seul besoin placé masquait les autres dans le détail des non-placés. La comparaison se fait maintenant sur l'objet de besoin du run.
3. **Non résolu : sémantique de l'année.** `besoins_maquette` calcule le nombre de séances à partir du volume d'une ECUE ; `generation.candidats` produit pourtant un seul créneau récurrent entre la première et la dernière semaine demandée pour chaque besoin. `annee.generer_annee` transmet tous les besoins de l'année dans cette même fenêtre ; son quota « par semaine » tronque le total des besoins du groupe sans répartir les séances entre semaines. Les ressources sont comparées en créneaux hebdomadaires (`contraintes.conflit_ressource`) : une occupation d'une semaine peut bloquer une semaine disjointe. Compter `nb_seances` comme le nombre de séances réellement inscrites dans une plage de semaines est donc trompeur tant que la période de chaque séance n'est pas déterminée.
4. Le validateur C10 interdit de persister un plan dont le volume n'est pas couvert. Le nouveau plan partiel reste un résultat de prévisualisation diagnostique, **pas** une promesse de 39 146 séances effectivement écrites. La prévalidation empêche désormais la création d'un EDT brouillon vide lorsque C10 refuse ce plan.

## Suite sûre avant tout déploiement annuel

- Écrire des tests pour deux besoins de volumes distincts sur plusieurs semaines, pour deux ressources occupées sur des semaines disjointes, et pour le nombre réel d'`AffectationCreneau` persistées versus séances attendues.
- Concevoir puis tester une distribution des occurrences sur les semaines académiques et les semestres : ne pas inférer de dates de semestre absentes du modèle, ne pas inventer d'enseignants et ne pas publier automatiquement.
- Mesurer le coût sur une **prévisualisation réduite** et préserver les quatre brouillons. Ne pas lancer une campagne globale ou basculer `/api/` sur le seul correctif partiel : il ne résout pas la planification annuelle.

Tests exécutés pour le correctif partiel : 106 tests moteur/année/campagnes/compteur SQL, tous réussis en base de test isolée. La démo VPS n'a pas été modifiée.
