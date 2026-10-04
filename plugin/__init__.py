from calibre.customize import InterfaceActionBase


class MetadataPUBPlugin(InterfaceActionBase):
    name = 'MetadataPUB'
    description = 'Completa identificadores configurables en EPUB y biblioteca con respaldo.'
    author = 'rlibanez'
    version = (1, 0, 0)
    supported_platforms = ['linux', 'windows', 'osx']
    minimum_calibre_version = (9, 14, 0)
    actual_plugin = 'calibre_plugins.metadatapub.ui:MetadataPUBAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.metadatapub.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
