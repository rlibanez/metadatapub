"""Run after installing the ZIP in a temporary Calibre configuration."""
import csv
import os
import runpy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from qt.core import Qt, QApplication, QWidget, QMessageBox, QDialog, QPlainTextEdit, QPushButton, QFileDialog
from calibre.gui2.actions.polish import Polish, PolishAction
from calibre.library import db
from calibre.ebooks.metadata.book.base import Metadata
from calibre_plugins.metadatapub import ui
from calibre_plugins.metadatapub.ui import AuditDialog, Editor, MetadataPUBAction
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

    book_id = next(iter(added))
    original = api.format(book_id, 'EPUB')
    api.add_format(book_id, 'KEPUB', io.BytesIO(original), run_hooks=False)
    api.set_field('publisher', {book_id: 'Editorial en Calibre'})
    api.set_field('identifiers', {book_id: {'isbn': '9781234567897'}})
    without_epub = api.create_book_entry(Metadata('Sin EPUB', ['Autor']))
    broken = api.create_book_entry(Metadata('EPUB roto', ['Autor']))
    api.add_format(broken, 'EPUB', io.BytesIO(b'broken'), run_hooks=False)
    gui.library_view.get_selected_ids = lambda: [book_id, without_epub, broken]
    action = MetadataPUBAction(gui, None)
    settings_parents = []
    action.interface_action_base_plugin = SimpleNamespace(
        name='MetadataPUB', do_user_config=settings_parents.append)
    action.create_action()
    action.genesis()
    menu_actions = [item for item in action.qaction.menu().actions() if not item.isSeparator()]
    assert [item.text() for item in menu_actions] == [
        'Editar identificadores EPUB', 'Comparar metadatos con los archivos', 'Personalizar complemento', 'Ayuda']
    _, audit_action, customize_action, help_action = menu_actions
    customize_action.trigger()
    assert settings_parents == [gui]
    opened_urls = []
    original_open_url = ui.open_url
    ui.open_url = lambda url: opened_urls.append(url.toString())
    try:
        help_action.trigger()
    finally:
        ui.open_url = original_open_url
    assert opened_urls == ['https://github.com/rlibanez/metadatapub']

    export_path = Path(path) / 'audit.csv'
    def check_audit(dialog):
        assert isinstance(dialog, AuditDialog)
        default_height = dialog.table.verticalHeader().defaultSectionSize()
        assert all(dialog.table.rowHeight(row) >= default_height
                   for row in range(dialog.table.rowCount()))
        assert any(dialog.table.rowHeight(row) > default_height
                   for row in range(dialog.table.rowCount()))
        book_rows = [row for row in dialog.report if row[0] == book_id]
        assert [row[3] for row in book_rows] == ['EPUB', 'KEPUB']
        for _, _, author, _, fields, calibre, archive in book_rows:
            assert author == 'Autor'
            names = fields.split('\n')
            assert calibre.split('\n')[names.index('Editorial')] == 'Editorial en Calibre'
            assert calibre.split('\n')[names.index('Identificador · isbn')] == '9781234567897'
            assert archive.split('\n')[names.index('Editorial')] == ''
        assert any(row[0] == broken and row[3:5] == ('EPUB', 'Error de lectura') for row in dialog.report)
        assert all(row[0] != without_epub for row in dialog.report)
        dialog.export_csv()
        return 0

    old_save_dialog = QFileDialog.getSaveFileName
    QDialog.exec = check_audit
    QFileDialog.getSaveFileName = lambda *args: (str(export_path), 'CSV (*.csv)')
    try:
        audit_action.trigger()
    finally:
        QDialog.exec = old_dialog_exec
        QFileDialog.getSaveFileName = old_save_dialog
    with export_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['ID', 'Título', 'Autor', 'Formato', 'Campos', 'Calibre', 'Archivo']
        rows = list(reader)
    assert all(row['Autor'] == 'Autor' for row in rows if row['Título'] == 'Prueba')
    assert any('Editorial' in row['Campos'].splitlines() and 'Editorial en Calibre' in row['Calibre'].splitlines() for row in rows)
    selected_ids = [book_id, without_epub, broken]
    gui.library_view.get_selected_ids = lambda: list(selected_ids)
    gui.library_view.select_rows = lambda ids: selected_ids.__setitem__(slice(None), ids)
    class SelectedLibrary:
        id = staticmethod(selected_ids.__getitem__)
        formats = staticmethod(library.formats)

    selected_library = SelectedLibrary()
    gui.library_view.model = lambda: SimpleNamespace(db=selected_library)
    gui.library_view.selectionModel = lambda: SimpleNamespace(
        selectedRows=lambda: [SimpleNamespace(row=lambda row=row: row)
                              for row in range(len(selected_ids))])
    gui.iactions = {'Polish Books': PolishAction(gui, None)}
    polish_calls = []

    def select_polish_rows(dialog):
        polish_button = next(button for button in dialog.findChildren(QPushButton)
                             if button.text() == 'Pulir libros seleccionados…')
        assert not polish_button.isEnabled()
        assert dialog.table.horizontalHeaderItem(0).text() == 'Seleccionar'
        mark_all = next(button for button in dialog.findChildren(QPushButton) if button.text() == 'Seleccionar todo')
        clear_all = next(button for button in dialog.findChildren(QPushButton) if button.text() == 'Deseleccionar todo')
        mark_all.click()
        assert set(dialog.checked_book_ids()) == {book_id, broken}
        assert polish_button.isEnabled()
        dialog.search.setText('PRUEBA')
        dialog.column_filters[3].setText('kepub')
        assert dialog.visible_count.text() == '1 de 3 filas visibles'
        assert dialog.checked_book_ids() == [book_id]
        dialog.table.sortItems(2, Qt.SortOrder.DescendingOrder)
        visible = [row for row in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(row)]
        assert [dialog.table.item(row, 4).text() for row in visible] == ['KEPUB']
        clear_all.click()
        assert not polish_button.isEnabled()
        dialog.column_filters[3].setText('mobi')
        assert dialog.visible_count.text() == '0 de 3 filas visibles'
        assert not mark_all.isEnabled()
        clear_buttons = {button.accessibleName(): button for button in dialog.findChildren(QPushButton)
                         if button.text() == 'Limpiar'}
        clear_buttons['Limpiar búsqueda general'].click()
        assert dialog.search.text() == ''
        assert dialog.column_filters[3].text() == 'mobi'
        assert dialog.visible_count.text() == '0 de 3 filas visibles'
        dialog.search.setText('Prueba')
        dialog.column_filters[1].setText('Prueba')
        clear_buttons['Limpiar filtros por columna'].click()
        assert dialog.search.text() == 'Prueba'
        assert all(not field.text() for field in dialog.column_filters)
        assert dialog.visible_count.text() == '2 de 3 filas visibles'
        clear_buttons['Limpiar búsqueda general'].click()
        assert set(dialog.checked_book_ids()) == {book_id, broken}
        clear_all.click()
        assert not polish_button.isEnabled()
        dialog.table.sortItems(2, Qt.SortOrder.AscendingOrder)
        assert dialog.table.item(0, 2).text() == 'EPUB roto'
        rows = [row for row in range(dialog.table.rowCount()) if dialog.table.item(row, 2).text() == 'Prueba']
        assert len(rows) == 2
        for row in rows:
            dialog.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        dialog.table.sortItems(2, Qt.SortOrder.DescendingOrder)
        assert dialog.table.item(0, 2).text() == 'Prueba'
        assert dialog.checked_book_ids() == [book_id]
        polish_button.click()
        return dialog.result()

    def cancel_native_polish(dialog):
        polish_calls.append(dict(dialog.book_id_map))
        return QDialog.DialogCode.Rejected

    old_polish_exec = Polish.exec
    QDialog.exec = select_polish_rows
    Polish.exec = cancel_native_polish
    try:
        audit_action.trigger()
    finally:
        Polish.exec = old_polish_exec
        QDialog.exec = old_dialog_exec
    assert selected_ids == [book_id]
    assert polish_calls == [{book_id: {'EPUB', 'KEPUB'}}]
    assert api.format(book_id, 'EPUB') == original
    assert api.field_for('identifiers', book_id) == {'isbn': '9781234567897'}
    library.close()
print('PASS: diálogo Qt y tabla de identificadores en biblioteca temporal')
