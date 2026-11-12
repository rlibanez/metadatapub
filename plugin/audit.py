import unicodedata

from calibre.ebooks.metadata import epub, mobi
from calibre.utils.date import is_date_undefined


READERS = {
    'EPUB': epub.get_quick_metadata,
    'KEPUB': epub.get_quick_metadata,
    'MOBI': mobi.get_metadata,
    'AZW': mobi.get_metadata,
    'AZW3': mobi.get_metadata,
}


def clean(value):
    return unicodedata.normalize('NFC', (value or '').strip())


def comparable_fields(metadata):
    date = metadata.pubdate
    return {
        'Título': clean(metadata.title),
        'Autores': tuple(map(clean, metadata.authors or ())),
        'Editorial': clean(metadata.publisher),
        'Serie': clean(metadata.series),
        'Número de serie': metadata.series_index if clean(metadata.series) else None,
        'Etiquetas': tuple(sorted(set(map(clean, metadata.tags or ())))),
        'Idiomas': tuple(sorted(set(metadata.languages or ()) - {'und'})),
        'Fecha de publicación': date.date().isoformat() if date and not is_date_undefined(date) else '',
        'Descripción (HTML)': clean(metadata.comments),
        **{f'Identificador · {key}': clean(value)
           for key, value in sorted(metadata.get_identifiers().items())},
    }


def display(value):
    if isinstance(value, tuple):
        return ', '.join(value)
    return '' if value is None else str(value)


def compare_book(db, book_id, fmt):
    path = db.format_abspath(book_id, fmt)
    if not path:
        raise FileNotFoundError(f'No se encontró el archivo {fmt}.')
    library = comparable_fields(db.get_proxy_metadata(book_id))
    with open(path, 'rb') as stream:
        embedded = comparable_fields(READERS[fmt](stream))
    return [
        (field, display(library.get(field)), display(embedded.get(field)))
        for field in dict.fromkeys((*library, *embedded))
        if library.get(field, '') != embedded.get(field, '')
    ]
