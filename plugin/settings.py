"""Persistent configuration shared by all libraries in this Calibre profile."""
from calibre.utils.config import JSONConfig
from calibre_plugins.metadatapub.defaults import DEFAULT_FIELDS, parse_fields

prefs = JSONConfig('plugins/metadatapub')
prefs.defaults['identifiers'] = list(DEFAULT_FIELDS)
prefs.defaults['show_all'] = False
prefs.defaults['default_action'] = 'edit'

DEFAULT_ACTIONS = (
    ('edit', 'Editar identificadores'),
    ('audit', 'Comparar metadatos con los archivos'),
    ('settings', 'Personalizar complemento'),
    ('help', 'Ayuda'),
)


def configured_fields():
    return parse_fields('\n'.join(prefs['identifiers']))
