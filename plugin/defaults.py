"""Load editable defaults from the plugin ZIP, never from Python constants."""
import re


def parse_fields(text):
    fields = tuple(line.strip().lower() for line in text.splitlines() if line.strip())
    if any(not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', field) for field in fields):
        raise ValueError('Usa solo letras, números, guiones y guiones bajos. Escribe el tipo, sin dos puntos ni valor.')
    if len(fields) != len(set(fields)):
        raise ValueError('Hay identificadores repetidos.')
    return fields


def load_default_fields():
    data = get_resources('defaults.txt')
    if data is None:
        return ()
    try:
        return parse_fields(data.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as err:
        raise ValueError('defaults.txt no es válido: ' + str(err)) from err


DEFAULT_FIELDS = load_default_fields()
