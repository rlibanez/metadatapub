import io
import os
import runpy
import tempfile
from types import SimpleNamespace
from pathlib import Path
from qt.core import QApplication, QWidget, QMessageBox
from calibre.library import db
from calibre.ebooks.metadata.book.base import Metadata
from calibre.customize.ui import interface_actions
from calibre_plugins.metadatapub.settings import configured_fields, parse_fields, prefs, DEFAULT_FIELDS
from calibre_plugins.metadatapub.core import inspect_epub
from calibre_plugins.metadatapub.ui import Editor

fixture = runpy.run_path(os.path.join(os.path.dirname(__file__), 'check_calibre.py'))['fixture']
app = QApplication.instance() or QApplication([])
plugin = next(p for p in interface_actions() if p.name == 'MetadataPUB')
assert plugin.is_customizable()
config = plugin.config_widget()
for invalid in ('catalog_id\nCATALOG_ID', 'catalog_id:123', 'my identifier'):
    try:
        parse_fields(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(invalid)
config.editor.setPlainText(' custom_id \n CATALOG_ID \n')
assert config.validate()
plugin.save_settings(config)
assert configured_fields() == ('custom_id', 'catalog_id')
assert plugin.config_widget().editor.toPlainText() == 'custom_id\ncatalog_id'
with tempfile.TemporaryDirectory() as path:
    library = db(path)
    api = library.new_api
    added, _ = api.add_books([(Metadata('Prueba', ['Autor']), {'EPUB': io.BytesIO(fixture())})])
    book_id = next(iter(added))
    gui = QWidget()
    gui.current_db = SimpleNamespace(new_api=api)
    gui.library_view = SimpleNamespace(model=lambda: SimpleNamespace(refresh_ids=lambda ids: None))
    editor = Editor(gui, [book_id])
    assert editor.table.columnCount() == 5
    assert editor.table.horizontalHeaderItem(1).text() == 'custom_id'
    assert editor.table.item(0, 2).text() == '9080'
    # Existing dialogs keep their field snapshot even if preferences change.
    prefs['identifiers'] = ['catalog_id']
    assert editor.fields == ('custom_id', 'catalog_id')
    old_exec, old_info = QMessageBox.exec, QMessageBox.information
    QMessageBox.exec = lambda self: QMessageBox.StandardButton.Save
    QMessageBox.information = lambda *args: None
    try:
        editor.table.item(0, 1).setText('12345')
        editor.save()
        assert editor.table.item(0, editor.status_col).text() == 'Guardado y verificado'
        data = api.format(book_id, 'EPUB')
        assert inspect_epub(data, ('custom_id',))['values']['custom_id'] == '12345'
        assert inspect_epub(data, ('test_id',))['values']['test_id'] == '2.0'
        assert api.field_for('identifiers', book_id)['custom_id'] == '12345'
        assert len(list(Path(path).glob('metadatapub-backups/*/*.epub'))) == 1
    finally:
        QMessageBox.exec, QMessageBox.information = old_exec, old_info
    editor.close()
    library.close()
# Leave a custom value to check persistence in a separate process.
prefs['identifiers'] = ['custom_id', 'catalog_id']
print('PASS: Customize plugin, validación, columnas dinámicas, guardado personalizado y conservación')
