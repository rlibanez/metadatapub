"""Inspection, Calibre writing and conservative verification."""
import hashlib
import io
from collections import Counter
from zipfile import ZipFile, ZIP_STORED
from lxml import etree

DC = 'http://purl.org/dc/elements/1.1/'
OPF = 'http://www.idpf.org/2007/opf'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_epub(data, fields):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    with ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Entradas ZIP duplicadas.')
        if z.testzip():
            raise ValueError('EPUB con errores CRC.')
        if 'META-INF/signatures.xml' in names:
            raise ValueError('EPUB firmado; no se modifica.')
        container = etree.fromstring(z.read('META-INF/container.xml'), parser)
        roots = container.findall('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
        if len(roots) != 1:
            raise ValueError('Se requiere un único OPF.')
        path = roots[0].get('full-path')
        root = etree.fromstring(z.read(path), parser)
        metadata = root.find('{%s}metadata' % OPF)
        if metadata is None:
            raise ValueError('No hay metadata OPF.')
        values, counts = {}, Counter()
        for node in metadata.findall('{%s}identifier' % DC):
            text = (node.text or '').strip()
            key, sep, value = text.partition(':')
            if sep and key.lower() in fields:
                key = key.lower()
                counts[key] += 1
                values[key] = value.strip()
        if any(n > 1 for n in counts.values()):
            raise ValueError('Identificadores de interés duplicados; revisar manualmente.')
        uid = root.get('unique-identifier')
        principal = root.xpath('//*[@id=$uid]', uid=uid or '')
        if len(principal) != 1 or principal[0].tag != '{%s}identifier' % DC:
            raise ValueError('Identificador principal inválido.')
        return dict(values=values, opf=path, principal=(uid, principal[0].text),
                    identifiers=[dict(text=node.text, attributes=dict(node.attrib))
                                 for node in metadata.findall('{%s}identifier' % DC)],
                    title=metadata.findtext('{%s}title' % DC) or '',
                    hashes={n: digest(z.read(n)) for n in names if n != path})


def prepare(data, changes, fields):
    from calibre.ebooks.metadata.epub import get_metadata, set_metadata
    before = inspect_epub(data, fields)
    changes = {k: v.strip() for k, v in changes.items() if v.strip()}
    if not set(changes).issubset(fields):
        raise ValueError('Campo desconocido.')
    if any('\n' in v or '\r' in v or '\x00' in v for v in changes.values()):
        raise ValueError('Los valores deben ocupar una sola línea.')
    stream = io.BytesIO(data)
    mi = get_metadata(stream, extract_cover=False)
    old_ids = mi.get_identifiers()
    for key, value in changes.items():
        mi.set_identifier(key, value)
    stream.seek(0)
    set_metadata(stream, mi, add_missing_cover=False)
    result = stream.getvalue()
    after = inspect_epub(result, fields)
    if before['hashes'] != after['hashes']:
        raise ValueError('Calibre cambió archivos fuera del OPF; no se aplica.')
    if before['principal'] != after['principal']:
        raise ValueError('Cambió el identificador principal; no se aplica.')
    for key, value in {**before['values'], **changes}.items():
        if after['values'].get(key) != value:
            raise ValueError('No se conservó el valor de ' + key)
    with ZipFile(io.BytesIO(result)) as z:
        first = z.infolist()[0]
        if first.filename != 'mimetype' or first.compress_type != ZIP_STORED or z.read('mimetype') != b'application/epub+zip':
            raise ValueError('Contenedor EPUB inválido.')
    stream.seek(0)
    actual = get_metadata(stream, extract_cover=False).get_identifiers()
    for key, value in {**old_ids, **changes}.items():
        if actual.get(key) != value:
            raise ValueError('Calibre alteró el identificador ' + key)
    return result
