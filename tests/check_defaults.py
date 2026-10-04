"""Installed ZIP checks; expected defaults are passed after --."""
import sys
from qt.core import QApplication, QPushButton, QWidget, QMessageBox
from calibre.customize.ui import interface_actions
from calibre_plugins.metadatapub.settings import DEFAULT_FIELDS, configured_fields, prefs
from calibre_plugins.metadatapub.ui import MetadataPUBAction

app = QApplication.instance() or QApplication([])
expected = tuple(sys.argv[1:])
assert DEFAULT_FIELDS == expected, (DEFAULT_FIELDS, expected)
assert configured_fields() == expected
plugin = next(p for p in interface_actions() if p.name == 'MetadataPUB')
config = plugin.config_widget()
assert config.validate()
assert config.findChildren(QPushButton)[0].text().endswith(f'({len(expected)} identificadores)')
config.editor.setPlainText('')
assert config.validate()
plugin.save_settings(config)
assert configured_fields() == ()
# An empty list must stop before accessing the library or selected books.
original = QMessageBox.information
messages = []
QMessageBox.information = lambda *args: messages.append(args[2])
try:
    action = MetadataPUBAction(QWidget(), '')
    action.open_dialog()
    assert len(messages) == 1 and 'No hay identificadores' in messages[0]
finally:
    QMessageBox.information = original
print(f'PASS: {len(expected)} valores desde defaults.txt, recuento y lista vacía')
