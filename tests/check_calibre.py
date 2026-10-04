import io
import os
import sys
import tempfile
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
sys.path.insert(0, os.path.abspath('plugin'))
from core import inspect_epub as inspect_raw, prepare as prepare_raw
from functools import partial
TEST_FIELDS = ("hardcover", "hardcover_book", "hardcover_edition", "catalog_id", "test_id")
inspect_epub = partial(inspect_raw, fields=TEST_FIELDS)
prepare = partial(prepare_raw, fields=TEST_FIELDS)
from calibre.library import db
from calibre.ebooks.metadata.book.base import Metadata
from qt.core import QDialog, QTableWidget, Qt, QMessageBox

opf = b'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Prueba</dc:title><dc:creator>Autor</dc:creator><dc:language>es</dc:language>
<dc:identifier id="BookId">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier>
<dc:identifier>catalog_id:9080</dc:identifier><dc:identifier>test_id:2.0</dc:identifier>
<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
</metadata><manifest><item id="ch" href="ch.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="ch"/></spine></package>'''

def fixture(opf_data=opf):
    s = io.BytesIO()
    with ZipFile(s, 'w') as z:
        z.writestr('mimetype', b'application/epub+zip', compress_type=ZIP_STORED)
        z.writestr('META-INF/container.xml', b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="Books/main.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=ZIP_DEFLATED)
        z.writestr('Books/main.opf', opf_data)
        z.writestr('Books/ch.xhtml', b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Prueba</title></head><body><p>Texto intacto</p></body></html>')
        z.writestr('Books/nav.xhtml', b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Indice</title></head><body><nav epub:type="toc"><ol><li><a href="ch.xhtml">Prueba</a></li></ol></nav></body></html>')
    return s.getvalue()

original = fixture()
changes = {'hardcover': 'the-rose-of-fire', 'hardcover_book': '461194', 'hardcover_edition': '30413356'}
result = prepare(original, changes)
assert inspect_epub(result)['values'] == {'catalog_id': '9080', 'test_id': '2.0', **changes}
second = prepare(result, {'test_id': '3.0', 'catalog_id': ''})
assert inspect_epub(second)['values']['test_id'] == '3.0'
assert inspect_epub(second)['values']['catalog_id'] == '9080'
try:
    inspect_epub(fixture(opf.replace(b'<dc:identifier>catalog_id:9080</dc:identifier>', b'<dc:identifier>catalog_id:9080</dc:identifier><dc:identifier>catalog_id:9</dc:identifier>')))
except ValueError:
    pass
else:
    raise AssertionError('Duplicate not rejected')
with tempfile.TemporaryDirectory() as path:
    library = db(path)
    api = library.new_api
    added, duplicates = api.add_books([(Metadata('Prueba', ['Autor']), {'EPUB': io.BytesIO(original)})])
    book_id = next(iter(added))
    assert api.add_format(book_id, 'EPUB', io.BytesIO(result), run_hooks=False)
    api.set_field('identifiers', {book_id: changes})
    assert api.field_for('identifiers', book_id) == changes
    assert api.format(book_id, 'EPUB') == result
    assert api.backend.library_path == path
    library.close()
print('PASS: lectura, alta, edición, valores vacíos, duplicados, conservación y API de biblioteca')
