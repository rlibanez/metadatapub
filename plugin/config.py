from qt.core import QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QMessageBox, QCheckBox, QDialogButtonBox, Qt
from calibre_plugins.metadatapub.settings import DEFAULT_FIELDS, configured_fields, parse_fields, prefs


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel('Escribe un tipo de identificador por línea (p. ej., isbn), sin valor.\n'
                       'El orden de la lista determina el de las columnas.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText('\n'.join(configured_fields()))
        self.editor.setMinimumSize(500, 220)
        layout.addWidget(self.editor)
        self.show_all = QCheckBox('Mostrar todos los EPUB seleccionados')
        self.show_all.setChecked(bool(prefs['show_all']))
        self.show_all.setToolTip('Desmarcada: solo se muestran los EPUB con algún identificador configurado vacío o ausente. Los errores de lectura siempre se muestran.')
        layout.addWidget(self.show_all)
        count = len(DEFAULT_FIELDS)
        self.reset_button = QPushButton(f'Restablecer valores de defaults.txt ({count} identificadores)')
        self.reset_button.clicked.connect(lambda: self.editor.setPlainText('\n'.join(DEFAULT_FIELDS)))
        layout.addWidget(self.reset_button, alignment=Qt.AlignmentFlag.AlignLeft)

    def showEvent(self, event):
        super().showEvent(event)
        # Calibre creates the standard footer after asking for our widget.
        footer = self.window().findChild(QDialogButtonBox)
        if footer is None:
            return
        save = footer.button(QDialogButtonBox.StandardButton.Ok)
        cancel = footer.button(QDialogButtonBox.StandardButton.Cancel)
        if save is None or cancel is None:
            return
        self.window().setWindowTitle('Configurar MetadataPUB')
        save.setText('Guardar')
        cancel.setText('Cancelar')
        if footer.buttonRole(self.reset_button) == QDialogButtonBox.ButtonRole.InvalidRole:
            self.layout().removeWidget(self.reset_button)
            footer.addButton(self.reset_button, QDialogButtonBox.ButtonRole.ResetRole)
            self.reset_button.show()

    def validate(self):
        try:
            parse_fields(self.editor.toPlainText())
            return True
        except ValueError as err:
            QMessageBox.warning(self, 'MetadataPUB', str(err))
            return False

    def save_settings(self):
        prefs['identifiers'] = list(parse_fields(self.editor.toPlainText()))
        prefs['show_all'] = self.show_all.isChecked()
