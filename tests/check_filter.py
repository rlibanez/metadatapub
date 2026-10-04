import io
import os
import runpy
import tempfile
from types import SimpleNamespace
from qt.core import QApplication, QWidget
from calibre.library import db
from calibre.ebooks.metadata.book.base import Metadata
from calibre.customize.ui import interface_actions
from calibre_plugins.metadatapub.ui import Editor
from calibre_plugins.metadatapub.settings import prefs

fixture_data = runpy.run_path(os.path.join(os.path.dirname(__file__), 'check_calibre.py'))
fixture, opf = fixture_data['fixture'], fixture_data['opf']
app = QApplication.instance() or QApplication([])
plugin = next(p for p in interface_actions() if p.name == 'MetadataPUB')
config = plugin.config_widget()
assert not config.show_all.isChecked()
config.editor.setPlainText('catalog_id\ntest_id')
plugin.save_settings(config)
with tempfile.TemporaryDirectory() as path:
    library = db(path)
    api = library.new_api
    ids = []
    for title, data in [
        ('Completo', fixture()),
        ('Ausente', fixture(opf.replace(b'<dc:identifier>catalog_id:9080</dc:identifier>', b''))),
        ('Vacio', fixture(opf.replace(b'catalog_id:9080', b'catalog_id:'))),
        ('Error', b'not a zip'),
    ]:
        added, _ = api.add_books([(Metadata(title, ['Autor']), {'EPUB': io.BytesIO(data)})])
        ids.append(next(iter(added)))
    # Complete file, but library disagrees: excluded in missing-only mode.
    api.set_field('identifiers', {ids[0]: {'catalog_id': 'another', 'test_id': '1.0'}})
    gui = QWidget()
    gui.current_db = SimpleNamespace(new_api=api)
    editor = Editor(gui, ids)
    assert [row[0] for row in editor.rows] == ids[1:]
    editor.close()
    config.show_all.setChecked(True)
    plugin.save_settings(config)
    assert plugin.config_widget().show_all.isChecked()
    editor = Editor(gui, ids)
    assert [row[0] for row in editor.rows] == ids
    assert editor.table.item(0, editor.status_col).text() == 'Diferencias con Calibre'
    editor.close()
    library.close()
print('PASS: filtro de ausentes/vacíos, todos, diferencias de biblioteca y errores')
