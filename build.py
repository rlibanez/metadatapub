import ast
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent
module = ast.parse((root / 'plugin' / '__init__.py').read_text(encoding='utf-8'))
plugin_class = next(node for node in module.body
                    if isinstance(node, ast.ClassDef) and node.name == 'MetadataPUBPlugin')
version_value = next(node.value for node in plugin_class.body
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'version'
                             for target in node.targets))
version = ast.literal_eval(version_value)
if (not isinstance(version, tuple) or len(version) != 3
        or any(type(part) is not int or part < 0 for part in version)):
    raise ValueError('La versión del plugin debe contener tres enteros no negativos')
version_text = '.'.join(map(str, version))
out = root / 'dist' / f'MetadataPUB-{version_text}.zip'
out.parent.mkdir(exist_ok=True)
with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
    for path in sorted((root / 'plugin').rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.txt', '.svg', '.png'):
            archive.write(path, path.relative_to(root / 'plugin').as_posix())
    license_path = root / 'LICENSE'
    if license_path.is_file():
        archive.write(license_path, 'LICENSE')
print(out)
