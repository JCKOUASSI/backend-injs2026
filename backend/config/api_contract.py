"""P00-08 — snapshots de contrat d'API (source de vérité partageable).

Ce module dérive du schéma OpenAPI généré par *drf-spectacular* un contrat
aplati qui ne fige QUE la forme publique de l'API — jamais les valeurs :

* une route par ``METHOD chemin`` ;
* les paramètres acceptés (path/query) ;
* les clés du corps de requête (``request_keys``) ;
* les clés des réponses par code HTTP (``responses``), résolues
  récursivement à travers les ``$ref`` de composants (les tableaux sont
  figurés par la clé ``[]``).

Règle de non-régression (voir ``diff_contract``) :

* route ou clé **supprimée / renommée** ⇒ rupture de contrat (échec) ;
* route ou clé **ajoutée** ⇒ autorisée (extension non cassante).

Le renouvellement du snapshot passe obligatoirement par la commande
``update_api_contract --justification "…"`` qui tient
``docs/api/CHANGELOG_CONTRAT.md``.
"""

import os

from drf_spectacular.generators import SchemaGenerator

#: Marqueurs structuraux du snapshot.
CONTRACT_FORMAT = 'injs-api-contract'
CONTRACT_VERSION = 1
LIST_KEY = '[]'  # Figurine « éléments d'un tableau ».
MAX_DEPTH = 12

#: En-tête stable du snapshot (hors routes, qui sont triées à l'écriture).
META = {
    'format': CONTRACT_FORMAT,
    'version': CONTRACT_VERSION,
    'generator': 'drf-spectacular',
}


def docs_dir():
    """Dossier docs/ à la racine du dépôt (le backend vit dans backend/)."""
    from django.conf import settings
    return os.path.join(settings.BASE_DIR, '..', 'docs', 'api')


def snapshot_path():
    return os.path.join(docs_dir(), 'contract.snapshot.json')


def changelog_path():
    return os.path.join(docs_dir(), 'CHANGELOG_CONTRAT.md')


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------

def generate_schema():
    """Génère le schéma OpenAPI complet via drf-spectacular."""
    generator = SchemaGenerator()
    return generator.get_schema(request=None, public=True)


def _json_schema_keys(node, components, visited, depth=0):
    """
    Transforme un nœud de schéma JSON en arbre de clés :

    * objet      → ``{propriete: sous_arbre, …}``
    * tableau    → ``{"[]": sous_arbre_des_items}``
    * feuille    → ``None``
    Les compositions (``allOf/oneOf/anyOf``) sont fusionnées ; les ``$ref``
    sont résolues avec protection contre les cycles.
    """
    if depth > MAX_DEPTH or not isinstance(node, dict):
        return None

    # Résolution des $ref.
    if '$ref' in node:
        ref_name = node['$ref'].split('/')[-1]
        if ref_name in visited:
            # Déjà rencontré sur cette branche : on clôture pour éviter un cycle.
            return {'$ref': ref_name, 'cycle': True}
        target = components.get(ref_name)
        if target is None:
            return None
        return _json_schema_keys(
            target, components, visited | {ref_name}, depth + 1
        )

    # Compositions : on conserve l'union des propriétés des membres.
    for composer in ('allOf', 'oneOf', 'anyOf'):
        if composer in node:
            merged = {}
            for member in node[composer]:
                subtree = _json_schema_keys(member, components, visited, depth + 1)
                if isinstance(subtree, dict):
                    merged.update(subtree)
            # Le nœud peut aussi porter des propriétés directes.
            direct = _properties_tree(node, components, visited, depth)
            if isinstance(direct, dict):
                merged.update(direct)
            return merged or None

    return _properties_tree(node, components, visited, depth)


def _properties_tree(node, components, visited, depth):
    node_type = node.get('type')

    if node_type == 'array' or 'items' in node:
        items = node.get('items', {})
        return {LIST_KEY: _json_schema_keys(items, components, visited, depth + 1)}

    if node_type == 'object' or 'properties' in node:
        tree = {}
        for name, sub in (node.get('properties') or {}).items():
            tree[name] = _json_schema_keys(sub, components, visited, depth + 1)
        # additionalProperties (dictionnaires dynamiques, ex. flags) : clés
        # libres, non contractuelles → rien à figer.
        return tree or None

    # Types primitifs / aucun schéma exploitable.
    return None


def _request_keys(operation, components):
    body = (
        operation.get('requestBody', {})
        .get('content', {})
        .get('application/json', {})
        .get('schema')
    )
    if not body:
        return None
    return _json_schema_keys(body, components, set())


def _response_keys(operation, components):
    result = {}
    for code, response in (operation.get('responses') or {}).items():
        content = response.get('content', {}) if isinstance(response, dict) else {}
        schema = content.get('application/json', {}).get('schema')
        if schema is None:
            # Réponse sans corps (204…) : on fige simplement l'existence du code.
            result[str(code)] = None
            continue
        result[str(code)] = _json_schema_keys(schema, components, set())
    return dict(sorted(result.items()))


def _parameter_names(operation):
    names = []
    for param in operation.get('parameters', []) or []:
        if isinstance(param, dict) and param.get('name'):
            names.append(param['name'])
    return sorted(set(names))


def build_contract(schema=None):
    """Construit le contrat aplati (dict sérialisable en JSON)."""
    schema = schema or generate_schema()
    components = schema.get('components', {}).get('schemas', {})
    routes = {}
    for path, methods in (schema.get('paths') or {}).items():
        for method, operation in methods.items():
            if method in ('parameters', 'servers', 'summary', 'description'):
                continue
            if not isinstance(operation, dict):
                continue
            key = f'{method.upper()} {path}'
            routes[key] = {
                'parameters': _parameter_names(operation),
                'request_keys': _request_keys(operation, components),
                'responses': _response_keys(operation, components),
            }
    return {'meta': META, 'routes': dict(sorted(routes.items()))}


# ---------------------------------------------------------------------------
# Comparaison
# ---------------------------------------------------------------------------

def _missing_keys(expected, current, breadcrumb):
    """
    Rend les chemins présents dans ``expected`` (snapshot) mais absents de
    ``current`` (API actuelle). Les ajouts dans ``current`` sont ignorés.
    """
    manquants = []
    if expected is None:
        return manquants
    if not isinstance(expected, dict):
        return manquants
    if not isinstance(current, dict):
        # Le snapshot exigeait une structure (objet/tableau) qui a changé de
        # nature : toutes les clés figées sont considérées perdues.
        for name, sub in expected.items():
            manquants.append(f'{breadcrumb}.{name}' if breadcrumb else name)
            if isinstance(sub, dict):
                manquants.extend(
                    _missing_keys(sub, None, f'{breadcrumb}.{name}' if breadcrumb else name)
                )
        return manquants
    for name, sub in expected.items():
        path = f'{breadcrumb}.{name}' if breadcrumb else name
        if name not in current:
            manquants.append(path)
            # Une branche supprimée emporte ses sous-clés (déjà signalées par
            # la clé de branche, inutile de multiplier les lignes).
            continue
        if isinstance(sub, dict):
            manquants.extend(_missing_keys(sub, current.get(name), path))
    return manquants


def diff_contract(current, snapshot):
    """
    Compare le contrat courant au snapshot figé.

    :returns: liste de ruptures (chaînes lisibles) ; liste vide = compatible.
    """
    ruptures = []
    current_routes = current.get('routes', {})
    snapshot_routes = snapshot.get('routes', {})

    for route_id, expected_route in snapshot_routes.items():
        if route_id not in current_routes:
            ruptures.append(f'Route supprimée ou renommée : {route_id}')
            continue
        actual_route = current_routes[route_id]

        for param in expected_route.get('parameters', []):
            if param not in actual_route.get('parameters', []):
                ruptures.append(f'{route_id} — paramètre supprimé : {param}')

        for missing in _missing_keys(
            expected_route.get('request_keys'),
            actual_route.get('request_keys'),
            f'{route_id} → requête',
        ):
            ruptures.append(f'{route_id} — clé de requête supprimée : {missing}')

        for code, expected_body in (expected_route.get('responses') or {}).items():
            if code not in (actual_route.get('responses') or {}):
                ruptures.append(f'{route_id} — code de réponse supprimé : {code}')
                continue
            for missing in _missing_keys(
                expected_body,
                actual_route['responses'][code],
                f'{route_id} → réponse {code}',
            ):
                ruptures.append(f'{route_id} — clé de réponse {code} supprimée : {missing}')

    return ruptures
