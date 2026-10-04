"""Run after installing the ZIP in a temporary Calibre configuration."""
import os
import runpy
import tempfile
from types import SimpleNamespace
from qt.core import QApplication, QWidget, QMessageBox, QDialog, QPlainTextEdit, QPushButton
from calibre.library import db
from calibre.ebooks.metadata.book.base import Metadata
from calibre_plugins.metadatapub.ui import Editor
from calibre_plugins.metadatapub.settings import prefs
import io

fixture_data = runpy.run_path(os.path.join(os.path.dirname(__file__), 'check_calibre.py'))
fixture = fixture_data['fixture']
prefs['identifiers'] = list(fixture_data['TEST_FIELDS'])
app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory() as path:
    library = db(path)
    api = library.new_api
    added, _ = api.add_books([(Metadata('Prueba', ['Autor']), {'EPUB': io.BytesIO(fixture())})])
    gui = QWidget()
    gui.current_db = SimpleNamespace(new_api=api)
    editor = Editor(gui, list(added))
    assert editor.table.rowCount() == 1
    assert editor.table.item(0, 4).text() == '9080'
    assert editor.table.item(0, 5).text() == '2.0'
    assert editor.table.item(0, 1).text() == ''
    gui.library_view = SimpleNamespace(model=lambda: SimpleNamespace(refresh_ids=lambda ids: None))
    original_exec = QMessageBox.exec
    original_information = QMessageBox.information
    QMessageBox.exec = lambda self: QMessageBox.StandardButton.Save
    QMessageBox.information = lambda *args: None
    try:
        editor.table.item(0, 1).setText('the-rose-of-fire')
        editor.table.item(0, 2).setText('461194')
        editor.table.item(0, 3).setText('30413356')
        editor.save()
        assert editor.table.item(0, 7).text() == 'Guardado y verificado'
        assert api.field_for('identifiers', next(iter(added)))['hardcover_book'] == '461194'
        backups = list(__import__('pathlib').Path(path).glob('metadatapub-backups/*/*.epub'))
        assert len(backups) == 1 and backups[0].read_bytes() == fixture()
    finally:
        QMessageBox.exec = original_exec
        QMessageBox.information = original_information
    old_dialog_exec = QDialog.exec
    checked = []
    def check_diagnostic(dialog):
        text = dialog.findChild(QPlainTextEdit)
        assert text is not None and text.isReadOnly()
        assert 'opf_leido' in text.toPlainText()
        assert '9080' in text.toPlainText()
        assert {b.text() for b in dialog.findChildren(QPushButton)} >= {'Copiar informe', 'Cerrar'}
        checked.append(True)
        return 0
    QDialog.exec = check_diagnostic
    try:
        editor.table.setCurrentCell(0, 0)
        editor.show_diagnostics()
        assert checked
    finally:
        QDialog.exec = old_dialog_exec
    editor.close()
    library.close()
print('PASS: diálogo Qt y tabla de identificadores en biblioteca temporal')
