import io
import json
import os
from datetime import datetime
from uuid import uuid4
from qt.core import (QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
                     QTableWidget, QTableWidgetItem, Qt, QMessageBox, QProgressDialog, QPlainTextEdit, QApplication)
from calibre.gui2.actions import InterfaceAction
from calibre_plugins.metadatapub.core import inspect_epub, prepare, digest
from calibre_plugins.metadatapub.settings import configured_fields, prefs


class MetadataPUBAction(InterfaceAction):
    name = 'MetadataPUB'
    action_spec = ('MetadataPUB', None, 'Completar identificadores de los EPUB seleccionados', None)

    def genesis(self):
        self.qaction.setIcon(get_icons('images/metadatapub.png', 'MetadataPUB'))
        self.qaction.triggered.connect(self.open_dialog)

    def open_dialog(self):
        if not configured_fields():
            QMessageBox.information(self.gui, 'MetadataPUB',
                                    'No hay identificadores configurados. Añádelos en Preferences → Plugins → MetadataPUB → Customize plugin.')
            return
        ids = self.gui.library_view.get_selected_ids()
        if not ids:
            QMessageBox.information(self.gui, 'MetadataPUB', 'Selecciona los libros que quieres revisar. Para toda la lista usa Ctrl+A.')
            return
        Editor(self.gui, ids).exec()


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
                'plugin_version': '1.0.0',
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
