from qt.core import QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QMessageBox, QCheckBox
from calibre_plugins.metadatapub.settings import DEFAULT_FIELDS, configured_fields, parse_fields, prefs


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel('Identificadores que quieres comprobar y editar, uno por línea.\n'
                       'Escribe únicamente el tipo (por ejemplo: isbn), sin dos puntos ni valor.\n'
                       'El orden de las líneas será el de las columnas. Se guardan en minúsculas.\n'
                       'La configuración se aplica a todas las bibliotecas de este perfil de Calibre.\n'
                       'Quitar un tipo de esta lista no lo elimina de tus libros.\n'
                       'Puedes dejar la lista vacía para no comprobar ningún identificador.')
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
        reset = QPushButton(f'Restablecer valores de defaults.txt ({count} identificadores)')
        reset.clicked.connect(lambda: self.editor.setPlainText('\n'.join(DEFAULT_FIELDS)))
        layout.addWidget(reset)

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
