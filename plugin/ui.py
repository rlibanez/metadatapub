import csv
import io
import json
import os
from datetime import datetime
from html import escape
from uuid import uuid4
from qt.core import (QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
                     QTableWidget, QTableWidgetItem, Qt, QMessageBox, QProgressDialog, QPlainTextEdit, QApplication, QFileDialog, QHeaderView, QUrl, QSignalBlocker, QLineEdit)
from calibre.gui2 import open_url
from calibre.gui2.actions import InterfaceAction
from calibre_plugins.metadatapub import MetadataPUBPlugin
from calibre_plugins.metadatapub.audit import READERS, compare_book
from calibre_plugins.metadatapub.core import inspect_epub, prepare, digest
from calibre_plugins.metadatapub.settings import configured_fields, prefs


def cell_tooltip(text):
    return '<qt>' + escape(text).replace('\n', '<br>') + '</qt>' if text else ''


class MetadataPUBAction(InterfaceAction):
    name = 'MetadataPUB'
    action_add_menu = True
    action_menu_clone_qaction = 'Editar identificadores'
    action_spec = ('MetadataPUB', None, 'Completar identificadores de los libros seleccionados', None)

    def genesis(self):
        self.qaction.setIcon(get_icons('images/metadatapub.png', 'MetadataPUB'))
        self.qaction.triggered.connect(self.open_dialog)
        menu = self.qaction.menu()
        self.create_menu_action(menu, 'audit_metadata',
                                'Comparar metadatos con los archivos',
                                shortcut=False, triggered=self.open_audit)

        menu.addSeparator()
        self.create_menu_action(menu, 'customize', 'Personalizar complemento',
                                shortcut=False, triggered=self.open_settings)
        self.create_menu_action(menu, 'help', 'Ayuda',
                                shortcut=False, triggered=self.open_help)

    def open_settings(self):
        self.interface_action_base_plugin.do_user_config(self.gui)

    def open_help(self):
        open_url(QUrl('https://github.com/rlibanez/metadatapub'))

    def open_audit(self):
        ids = self.gui.library_view.get_selected_ids()
        if not ids:
            QMessageBox.information(self.gui, 'MetadataPUB', 'Selecciona los libros que quieres comparar.')
            return
        db = self.gui.current_db.new_api
        dialog = AuditDialog(self.gui, ids)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.polish_ids:
            return
        if self.gui.current_db.new_api is not db:
            QMessageBox.warning(self.gui, 'MetadataPUB', 'La biblioteca ha cambiado. Vuelve a analizar.')
            return
        view = self.gui.library_view
        previous_ids = view.get_selected_ids()
        view.select_rows(dialog.polish_ids)
        if set(view.get_selected_ids()) != set(dialog.polish_ids):
            view.select_rows(previous_ids)
            QMessageBox.warning(self.gui, 'MetadataPUB',
                                'No se pudo seleccionar todos los libros en Calibre. Vuelve a analizar.')
            return
        self.gui.iactions['Polish Books'].polish_books()

    def open_dialog(self):
        if not configured_fields():
            QMessageBox.information(self.gui, 'MetadataPUB',
                                    'No hay identificadores configurados. Añádelos desde MetadataPUB → Personalizar complemento.')
            return
        ids = self.gui.library_view.get_selected_ids()
        if not ids:
            QMessageBox.information(self.gui, 'MetadataPUB', 'Selecciona los libros que quieres revisar. Para toda la lista usa Ctrl+A.')
            return
        Editor(self.gui, ids).exec()


class AuditDialog(QDialog):
    headers = ('ID', 'Título', 'Autor', 'Formato', 'Campos', 'Calibre', 'Archivo')

    def __init__(self, gui, ids):
        super().__init__(gui)
        self.polish_ids = []
        self.setWindowTitle('MetadataPUB — comparar metadatos con los archivos')
        self.resize(1050, 600)
        layout = QVBoxLayout(self)
        summary = QLabel()
        layout.addWidget(summary)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar en todas las columnas…')
        self.search.setAccessibleName('Buscar en todas las columnas')
        self.search.setClearButtonEnabled(True)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search)
        clear_search = QPushButton('Limpiar')
        clear_search.setAccessibleName('Limpiar búsqueda general')
        clear_search.clicked.connect(self.search.clear)
        search_row.addWidget(clear_search)
        layout.addLayout(search_row)
        filters = QHBoxLayout()
        self.column_filters = []
        for name in self.headers:
            field = QLineEdit()
            field.setPlaceholderText(name)
            field.setAccessibleName(f'Filtrar por {name}')
            field.setClearButtonEnabled(True)
            filters.addWidget(field)
            self.column_filters.append(field)
        clear_filters = QPushButton('Limpiar')
        clear_filters.setAccessibleName('Limpiar filtros por columna')
        clear_filters.clicked.connect(self.clear_column_filters)
        filters.addWidget(clear_filters)
        layout.addLayout(filters)
        self.visible_count = QLabel()
        layout.addWidget(self.visible_count)
        self.table = QTableWidget(0, len(self.headers) + 1)
        self.table.setHorizontalHeaderLabels(('Seleccionar', *self.headers))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.mark_all_button = mark_all = QPushButton('Seleccionar todo')
        mark_all.setToolTip('Seleccionar todas las filas visibles.')
        mark_all.clicked.connect(lambda: self.set_all_checks(Qt.CheckState.Checked))
        buttons.addWidget(mark_all)
        self.clear_all_button = clear_all = QPushButton('Deseleccionar todo')
        clear_all.setToolTip('Deseleccionar todas las filas visibles.')
        clear_all.clicked.connect(lambda: self.set_all_checks(Qt.CheckState.Unchecked))
        buttons.addWidget(clear_all)
        export = QPushButton('Exportar CSV')
        export.clicked.connect(self.export_csv)
        buttons.addWidget(export)
        self.polish_button = polish = QPushButton('Pulir libros seleccionados…')
        polish.setToolTip('Envía los libros marcados en las filas visibles. Calibre puede pulir todos sus formatos compatibles.')
        polish.setEnabled(False)
        polish.clicked.connect(self.request_polish)
        buttons.addWidget(polish)
        buttons.addStretch()
        close = QPushButton('Cerrar')
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        db = gui.current_db.new_api
        self.report = []
        compared = changed = skipped = errors = processed = 0
        progress = QProgressDialog('Comparando metadatos…', 'Cancelar', 0, len(ids), gui)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        for index, book_id in enumerate(ids):
            progress.setValue(index)
            if progress.wasCanceled():
                break
            formats = sorted(READERS.keys() & set(db.formats(book_id, verify_formats=False)))
            processed += 1
            if not formats:
                skipped += 1
                continue
            title = db.field_for('title', book_id)
            authors = ', '.join(db.field_for('authors', book_id) or ())
            for fmt in formats:
                try:
                    differences = compare_book(db, book_id, fmt)
                except Exception as error:
                    errors += 1
                    self.report.append((book_id, title, authors, fmt, 'Error de lectura', '', str(error)))
                    continue
                compared += 1
                if differences:
                    changed += 1
                    grouped = (
                        '\n'.join(' ⏎ '.join(value.splitlines()) for value in values)
                        for values in zip(*differences)
                    )
                    self.report.append((book_id, title, authors, fmt, *grouped))
        progress.close()
        pending = len(ids) - processed
        summary.setText(f'{compared} archivos comparados · {changed} con diferencias · '
                        f'{errors} errores · {skipped} libros sin formato compatible · '
                        f'{pending} libros pendientes')
        self.table.setRowCount(len(self.report))
        for row, values in enumerate(self.report):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, checkbox)
            for column, value in enumerate(values, 1):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, value)
                if isinstance(value, str):
                    item.setToolTip(cell_tooltip(value))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
        self.table.setSortingEnabled(True)
        export.setEnabled(bool(self.report))
        self.table.itemChanged.connect(self.update_polish_button)
        for field in (self.search, *self.column_filters):
            field.textChanged.connect(self.apply_filters)
        self.table.model().layoutChanged.connect(self.apply_filters)
        self.apply_filters()

    def clear_column_filters(self):
        for field in self.column_filters:
            with QSignalBlocker(field):
                field.clear()
        self.apply_filters()

    def apply_filters(self):
        query = self.search.text().strip().casefold()
        column_queries = [field.text().strip().casefold() for field in self.column_filters]
        visible = 0
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, column).text().casefold()
                      for column in range(1, self.table.columnCount())]
            matches = (not query or any(query in value for value in values)) and all(
                term in value for term, value in zip(column_queries, values)
            )
            self.table.setRowHidden(row, not matches)
            visible += int(matches)
        self.visible_count.setText(f'{visible} de {self.table.rowCount()} filas visibles')
        self.mark_all_button.setEnabled(bool(visible))
        self.clear_all_button.setEnabled(bool(visible))
        self.update_polish_button()

    def update_polish_button(self):
        self.polish_button.setEnabled(bool(self.checked_book_ids()))

    def set_all_checks(self, state):
        with QSignalBlocker(self.table):
            for row in range(self.table.rowCount()):
                if not self.table.isRowHidden(row):
                    self.table.item(row, 0).setCheckState(state)
        self.update_polish_button()

    def checked_book_ids(self):
        return list(dict.fromkeys(
            self.table.item(row, 1).data(Qt.ItemDataRole.DisplayRole)
            for row in range(self.table.rowCount())
            if not self.table.isRowHidden(row)
            and self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ))

    def request_polish(self):
        self.polish_ids = self.checked_book_ids()
        if self.polish_ids:
            self.accept()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar comparación', 'diferencias-calibre.csv', 'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(self.headers)
                writer.writerows(self.report)
        except OSError as error:
            QMessageBox.warning(self, 'MetadataPUB', str(error))


class SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        role = Qt.ItemDataRole.UserRole
        return (self.data(role), self.text().casefold()) < (other.data(role), other.text().casefold())


class Editor(QDialog):
    first_identifier_col = 2

    def __init__(self, gui, ids):
        super().__init__(gui)
        self.gui = gui
        self.db = gui.current_db.new_api
        self.rows = []
        # Snapshot: changes to preferences apply when reopening this dialog.
        self.fields = configured_fields()
        self.show_all = bool(prefs['show_all'])
        self.library_col = self.first_identifier_col + len(self.fields)
        self.status_col = self.library_col + 1
        self.setWindowTitle('MetadataPUB — editar identificadores')
        self.resize(1150, 600)
        layout = QVBoxLayout(self)
        headers = ('ID', 'Título', *self.fields, 'Valores en Calibre', 'Estado')
        self.search = self.make_search('Buscar en todas las columnas…', 'Buscar en todas las columnas')
        search_row = QHBoxLayout()
        search_row.addWidget(self.search)
        clear_search = QPushButton('Limpiar')
        clear_search.setAccessibleName('Limpiar búsqueda general')
        clear_search.clicked.connect(self.search.clear)
        search_row.addWidget(clear_search)
        layout.addLayout(search_row)

        filter_row = QHBoxLayout()
        self.column_filters = []
        for name in headers:
            field = self.make_search(name, f'Filtrar por {name}')
            field.setToolTip(f'Filtrar por {name}')
            field.setMinimumWidth(55)
            filter_row.addWidget(field, 1)
            self.column_filters.append(field)
        clear_filters = QPushButton('Limpiar')
        clear_filters.setAccessibleName('Limpiar filtros por columna')
        clear_filters.clicked.connect(self.clear_column_filters)
        filter_row.addWidget(clear_filters)
        layout.addLayout(filter_row)
        self.visible_count = QLabel()
        layout.addWidget(self.visible_count)

        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        layout.addWidget(self.table)
        bar = QHBoxLayout()
        save = QPushButton('Revisar y guardar cambios')
        save.clicked.connect(self.save)
        diagnose = QPushButton('Ver lectura del archivo')
        diagnose.clicked.connect(self.show_diagnostics)
        bar.addWidget(diagnose)
        bar.addWidget(save)
        bar.addStretch()
        close = QPushButton('Cerrar')
        close.clicked.connect(self.reject)
        bar.addWidget(close)
        layout.addLayout(bar)
        progress = QProgressDialog('Leyendo archivos…', 'Cancelar', 0, len(ids), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        for index, book_id in enumerate(ids):
            progress.setValue(index)
            if progress.wasCanceled():
                break
            try:
                data = self.db.format(book_id, 'EPUB')
                if data is None:
                    continue
                info = inspect_epub(data, self.fields)
                library = dict(self.db.field_for('identifiers', book_id) or {})
                diff = {k: library.get(k, '') for k in self.fields if library.get(k, '') != info['values'].get(k, '')}
                missing = [k for k in self.fields if not info['values'].get(k)]
                if not self.show_all and not missing:
                    continue
                if missing:
                    status, priority = 'Faltan en el archivo: ' + ', '.join(missing), 1
                elif diff:
                    status, priority = 'Diferencias con Calibre', 2
                else:
                    status, priority = 'Completo', 3
                self.add_row(book_id, info, digest(data), library, diff, status, priority)
            except Exception as err:
                self.add_row(book_id, None, None, {}, {}, f'ERROR: {err}', 0)
        progress.setValue(len(ids))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.setSortingEnabled(True)
        for field in (self.search, *self.column_filters):
            field.textChanged.connect(self.apply_filters)
        self.table.itemChanged.connect(self.update_edited_cell)
        self.table.model().layoutChanged.connect(self.apply_filters)
        self.apply_filters()

    @staticmethod
    def make_search(placeholder, accessible_name):
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setAccessibleName(accessible_name)
        field.setClearButtonEnabled(True)
        return field

    def clear_column_filters(self):
        for field in self.column_filters:
            with QSignalBlocker(field):
                field.clear()
        self.apply_filters()

    def apply_filters(self):
        query = self.search.text().strip().casefold()
        terms = [field.text().strip().casefold() for field in self.column_filters]
        visible = 0
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, col).text().casefold() for col in range(len(terms))]
            matches = (not query or any(query in value for value in values)) and all(
                term in value for term, value in zip(terms, values)
            )
            self.table.setRowHidden(row, not matches)
            visible += int(matches)
        self.visible_count.setText(f'{visible} de {self.table.rowCount()} filas visibles')

    def update_edited_cell(self, item):
        tooltip = cell_tooltip(item.text())
        if item.toolTip() != tooltip:
            with QSignalBlocker(self.table):
                item.setToolTip(tooltip)
        self.apply_filters()

    def record_index(self, row):
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)

    def add_row(self, book_id, info, fingerprint, library, diff, status, priority):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.rows.append((book_id, info, fingerprint, library))
        title = info['title'] if info else self.db.field_for('title', book_id)
        texts = [str(book_id), title or '', *[info['values'].get(k, '') if info else '' for k in self.fields],
                 json.dumps(diff, ensure_ascii=False) if diff else '', status]
        for col, text in enumerate(texts):
            if col == 0:
                item = SortableItem(text)
                item.setData(Qt.ItemDataRole.UserRole, book_id)
                # Keep the original record index with the item when Qt moves rows.
                item.setData(Qt.ItemDataRole.UserRole + 1, row)
            elif col == 1:
                item = SortableItem(text)
                item.setData(Qt.ItemDataRole.UserRole, text.casefold())
            elif col == self.status_col:
                item = SortableItem(text)
                item.setData(Qt.ItemDataRole.UserRole, priority)
            else:
                item = QTableWidgetItem(text)
            item.setToolTip(cell_tooltip(text))
            if not self.first_identifier_col <= col < self.library_col or info is None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)

    def show_diagnostics(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, 'MetadataPUB', 'Selecciona una fila para ver qué archivo se ha leído.')
            return
        book_id, info, fingerprint, library = self.rows[self.record_index(row)]
        if self.gui.current_db.new_api is not self.db:
            QMessageBox.warning(self, 'MetadataPUB', 'La biblioteca ha cambiado. Vuelve a analizar.')
            return
        try:
            data = self.db.format(book_id, 'EPUB')
            current = inspect_epub(data, self.fields)
            report = {
                'plugin_version': '.'.join(map(str, MetadataPUBPlugin.version)),
                'biblioteca': self.db.backend.library_path,
                'book_id': book_id,
                'formato': 'EPUB',
                'archivo_en_biblioteca': self.db.format_metadata(book_id, 'EPUB', allow_cache=False),
                'sha256_analizado': fingerprint,
                'sha256_actual': digest(data),
                'opf_leido': current['opf'],
                'tipos_configurados': self.fields,
                'identificadores_XML_actuales': current['identifiers'],
                'valores_leidos_al_analizar': info['values'] if info else None,
                'valores_leidos_ahora': current['values'],
                'valores_en_Calibre': dict(self.db.field_for('identifiers', book_id) or {}),
            }
            dialog = QDialog(self)
            dialog.setWindowTitle('MetadataPUB — diagnóstico de lectura')
            dialog.resize(850, 600)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel('Archivo e identificadores leídos. Este informe no modifica el libro.'))
            text = QPlainTextEdit(dialog)
            text.setReadOnly(True)
            text.setPlainText(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            layout.addWidget(text)
            buttons = QHBoxLayout()
            copy = QPushButton('Copiar informe')
            copy.clicked.connect(lambda: QApplication.clipboard().setText(text.toPlainText()))
            close = QPushButton('Cerrar')
            close.clicked.connect(dialog.accept)
            buttons.addWidget(copy)
            buttons.addWidget(close)
            layout.addLayout(buttons)
            dialog.exec()
        except Exception as err:
            QMessageBox.warning(self, 'MetadataPUB', str(err))

    def save(self):
        if self.gui.current_db.new_api is not self.db:
            QMessageBox.warning(self, 'MetadataPUB', 'La biblioteca ha cambiado. Cierra y vuelve a analizar.')
            return
        plans = []
        # Filters only affect visibility; edits on hidden rows remain in the review.
        for row in range(self.table.rowCount()):
            record = self.record_index(row)
            book_id, info, fingerprint, library = self.rows[record]
            if info is None:
                continue
            changes = {k: self.table.item(row, col).text().strip() for col, k in enumerate(self.fields, self.first_identifier_col)}
            changes = {k: v for k, v in changes.items() if v and (v != info['values'].get(k, '') or v != library.get(k, ''))}
            if changes:
                plans.append((record, book_id, fingerprint, library, changes,
                              self.table.item(row, self.status_col),
                              self.table.item(row, self.library_col)))
        if not plans:
            QMessageBox.information(self, 'MetadataPUB', 'No hay cambios para guardar.')
            return
        summary = '\n'.join(f'{book_id}: ' + ', '.join(f'{k} → {v}' for k, v in changes.items())
                            for _, book_id, _, _, changes, _, _ in plans)
        review = QMessageBox(self)
        review.setWindowTitle('Revisar cambios')
        review.setText(f'Se modificarán {len(plans)} libros. Se creará un respaldo por libro. Ver detalles para revisar los valores.')
        review.setDetailedText(summary)
        review.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
        if review.exec() != QMessageBox.StandardButton.Save:
            return
        backup_dir = os.path.join(self.db.backend.library_path, 'metadatapub-backups', datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
        try:
            os.makedirs(backup_dir)
        except Exception as err:
            QMessageBox.critical(self, 'MetadataPUB', str(err))
            return
        for record, book_id, fingerprint, library, changes, status_item, library_item in plans:
            written = False
            original = None
            try:
                original = self.db.format(book_id, 'EPUB')
                current_ids = dict(self.db.field_for('identifiers', book_id) or {})
                if original is None or digest(original) != fingerprint or current_ids != library:
                    raise ValueError('El libro cambió desde el análisis. Vuelve a analizar.')
                result = prepare(original, changes, self.fields)
                with open(os.path.join(backup_dir, f'{book_id}.epub'), 'xb') as f:
                    f.write(original)
                    f.flush()
                    os.fsync(f.fileno())
                with open(os.path.join(backup_dir, f'{book_id}.json'), 'x', encoding='utf-8') as f:
                    json.dump({'book_id': book_id, 'identifiers': library, 'changes': changes}, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                written = True
                if not self.db.add_format(book_id, 'EPUB', io.BytesIO(result), run_hooks=False):
                    raise ValueError('No se pudo sustituir el archivo.')
                if digest(self.db.format(book_id, 'EPUB')) != digest(result):
                    raise ValueError('La copia guardada no coincide.')
                self.db.set_field('identifiers', {book_id: {**library, **changes}})
                if dict(self.db.field_for('identifiers', book_id)) != {**library, **changes}:
                    raise ValueError('No se guardaron los identificadores de biblioteca.')
                new_info = inspect_epub(result, self.fields)
                self.rows[record] = (book_id, new_info, digest(result), {**library, **changes})
                status_item.setData(Qt.ItemDataRole.UserRole, 4)
                status_item.setText('Guardado y verificado')
                library_item.setText('')
            except Exception as err:
                message = str(err)
                if written:
                    try:
                        if not self.db.add_format(book_id, 'EPUB', io.BytesIO(original), run_hooks=False):
                            raise ValueError('No se restauró el archivo')
                        self.db.set_field('identifiers', {book_id: library})
                        if digest(self.db.format(book_id, 'EPUB')) != digest(original):
                            raise ValueError('Restauración no verificada')
                        message += ' — restaurado'
                    except Exception as rollback:
                        message += ' — restauración fallida: ' + str(rollback)
                status_item.setData(Qt.ItemDataRole.UserRole, 0)
                status_item.setText('ERROR: ' + message)
        self.gui.library_view.model().refresh_ids([p[1] for p in plans])
        QMessageBox.information(self, 'MetadataPUB', 'Proceso terminado. Revisa la columna Estado.\nRespaldos: ' + backup_dir)
