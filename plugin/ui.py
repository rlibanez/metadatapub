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


class MetadataPUBAction(InterfaceAction):
    name = 'MetadataPUB'
    action_add_menu = True
    action_menu_clone_qaction = 'Editar identificadores EPUB'
    action_spec = ('MetadataPUB', None, 'Completar identificadores de los EPUB seleccionados', None)

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
        for column, width in enumerate((90, 60, 165, 130, 75, 145, 175, 175)):
            self.table.setColumnWidth(column, width)
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
                    item.setToolTip('<qt>' + escape(value).replace('\n', '<br>') + '</qt>')
                self.table.setItem(row, column, item)
        row_header = self.table.verticalHeader()
        row_header.setMinimumSectionSize(row_header.defaultSectionSize())
        self.table.resizeRowsToContents()
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


class Editor(QDialog):
    def __init__(self, gui, ids):
        super().__init__(gui)
        self.gui = gui
        self.db = gui.current_db.new_api
        self.rows = []
        # Snapshot: changes to preferences apply when reopening this dialog.
        self.fields = configured_fields()
        self.show_all = bool(prefs['show_all'])
        self.library_col = len(self.fields) + 1
        self.status_col = len(self.fields) + 2
        self.setWindowTitle('MetadataPUB — identificadores EPUB')
        self.resize(1150, 600)
        layout = QVBoxLayout(self)
        mode_text = ('Se muestran todos los EPUB seleccionados.' if self.show_all else
                     'Se muestran los EPUB a los que les falta algún identificador configurado.')
        layout.addWidget(QLabel(mode_text + '\n'
                                'Los valores son los del EPUB. Un campo vacío no borra datos.\n'
                                'La columna Valores en Calibre muestra las diferencias; copia el valor que quieras conservar.'))
        self.table = QTableWidget(0, len(self.fields) + 3)
        self.table.setHorizontalHeaderLabels(['ID / título', *self.fields, 'Valores en Calibre', 'Estado'])
        layout.addWidget(self.table)
        bar = QHBoxLayout()
        save = QPushButton('Revisar y guardar cambios')
        save.clicked.connect(self.save)
        diagnose = QPushButton('Ver lectura EPUB')
        diagnose.clicked.connect(self.show_diagnostics)
        bar.addWidget(diagnose)
        close = QPushButton('Cerrar')
        close.clicked.connect(self.reject)
        bar.addWidget(save)
        bar.addWidget(close)
        layout.addLayout(bar)
        progress = QProgressDialog('Leyendo EPUB…', 'Cancelar', 0, len(ids), self)
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
                self.add_row(book_id, info, digest(data), library, diff, ('Faltan en el EPUB: ' + ', '.join(missing)) if missing else ('Diferencias con Calibre' if diff else 'Completo'))
            except Exception as err:
                self.add_row(book_id, None, None, {}, {}, str(err))
        progress.setValue(len(ids))
        self.table.resizeColumnsToContents()

    def add_row(self, book_id, info, fingerprint, library, diff, status):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.rows.append((book_id, info, fingerprint, library))
        title = info['title'] if info else self.db.field_for('title', book_id)
        texts = [f'{book_id}: {title}', *[info['values'].get(k, '') if info else '' for k in self.fields],
                 json.dumps(diff, ensure_ascii=False) if diff else '', status]
        for col, text in enumerate(texts):
            item = QTableWidgetItem(text)
            if col not in range(1, len(self.fields) + 1) or info is None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)

    def show_diagnostics(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, 'MetadataPUB', 'Selecciona una fila para ver qué archivo se ha leído.')
            return
        book_id, info, fingerprint, library = self.rows[row]
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
            layout.addWidget(QLabel('Archivo EPUB e identificadores leídos. Este informe no modifica el libro.'))
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
        for row, (book_id, info, fingerprint, library) in enumerate(self.rows):
            if info is None:
                continue
            changes = {k: self.table.item(row, col).text().strip() for col, k in enumerate(self.fields, 1)}
            changes = {k: v for k, v in changes.items() if v and (v != info['values'].get(k, '') or v != library.get(k, ''))}
            if changes:
                plans.append((row, book_id, info, fingerprint, library, changes))
        if not plans:
            QMessageBox.information(self, 'MetadataPUB', 'No hay cambios para guardar.')
            return
        summary = '\n'.join(f'{book_id}: ' + ', '.join(f'{k} → {v}' for k, v in changes.items())
                            for _, book_id, _, _, _, changes in plans)
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
        for row, book_id, info, fingerprint, library, changes in plans:
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
                    raise ValueError('No se pudo sustituir el EPUB.')
                if digest(self.db.format(book_id, 'EPUB')) != digest(result):
                    raise ValueError('La copia guardada no coincide.')
                self.db.set_field('identifiers', {book_id: {**library, **changes}})
                if dict(self.db.field_for('identifiers', book_id)) != {**library, **changes}:
                    raise ValueError('No se guardaron los identificadores de biblioteca.')
                new_info = inspect_epub(result, self.fields)
                self.rows[row] = (book_id, new_info, digest(result), {**library, **changes})
                self.table.item(row, self.status_col).setText('Guardado y verificado')
                self.table.item(row, self.library_col).setText('')
            except Exception as err:
                message = str(err)
                if written:
                    try:
                        if not self.db.add_format(book_id, 'EPUB', io.BytesIO(original), run_hooks=False):
                            raise ValueError('No se restauró el EPUB')
                        self.db.set_field('identifiers', {book_id: library})
                        if digest(self.db.format(book_id, 'EPUB')) != digest(original):
                            raise ValueError('Restauración no verificada')
                        message += ' — restaurado'
                    except Exception as rollback:
                        message += ' — restauración fallida: ' + str(rollback)
                self.table.item(row, self.status_col).setText('ERROR: ' + message)
        self.gui.library_view.model().refresh_ids([p[1] for p in plans])
        QMessageBox.information(self, 'MetadataPUB', 'Proceso terminado. Revisa la columna Estado.\nRespaldos: ' + backup_dir)
