"""Schéma OpenAPI de l'API INJS.

Constat d'audit : la génération du schéma (`manage.py spectacular`) émettait
1 032 avertissements ``operationId … has collisions``. Cause : la classe
standard de drf-spectacular **supprime les paramètres de chemin** avant de
construire l'``operationId``, si bien que `/formations/{id}/formateurs/` et
`/formations/formateurs/{id}/` produisaient tous deux
``api_v1_formations_formateurs_retrieve``.

Conséquence concrète : les clients générés (SDK, collections) recevaient deux
opérations de même identifiant, donc une seule des deux survivait.

La correction conserve les paramètres sous la forme ``by_<nom>``, ce qui rend
les identifiants uniques **et** lisibles, sans suffixe numérique arbitraire
dont l'ordre dépendrait de l'itération du `URLconf`.
"""

import re

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.settings import spectacular_settings

_CARACTERES_NON_AUTORISES = re.compile(r'[^A-Za-z0-9_]+')


class INJSAutoSchema(AutoSchema):
    """``operationId`` uniques, paramètres de chemin conservés."""

    def get_operation_id(self) -> str:
        chemin = self.path
        if self.path_prefix:
            chemin = re.sub(
                pattern=self.path_prefix, repl='', string=chemin, flags=re.IGNORECASE,
            )
        # `{participant_pk}` → `by_participant_pk` : deux routes qui ne
        # diffèrent que par la position d'un paramètre ne se confondent plus.
        chemin = re.sub(r'\{(\w+)\}', r'by_\1', chemin)
        jetons = [
            _CARACTERES_NON_AUTORISES.sub('_', jeton).strip('_')
            for jeton in re.split(r'[/\-]', chemin)
        ]
        jetons = [jeton for jeton in jetons if jeton]

        if self.method == 'GET' and self._is_list_view():
            action = 'list'
        else:
            action = self.method_mapping[self.method.lower()]

        if not jetons:
            jetons.append('root')

        if re.search(r'<drf_format_suffix\w*:\w+>', self.path_regex):
            jetons.append('formatted')

        if spectacular_settings.OPERATION_ID_METHOD_POSITION == 'PRE':
            return '_'.join([action] + jetons)
        return '_'.join(jetons + [action])
