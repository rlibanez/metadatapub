<p align="center">
  <img src="plugin/images/metadatapub.png" alt="Icono de MetadataPUB: letrero de pub con el símbolo de código" width="160">
</p>

<h1 align="center">MetadataPUB</h1>

<p align="center">
  Tus identificadores EPUB, en orden 🍺
</p>

<p align="center">
  <strong>1.0.0</strong> · <strong>rlibanez</strong> · Calibre <strong>9.14.0+</strong>
</p>

Comprueba, añade y edita los identificadores de tus libros desde Calibre.
Elige los campos que necesitas, completa una tabla y guarda los cambios tanto
en el EPUB como en su ficha de biblioteca.

<p align="center">
  <a href="https://github.com/rlibanez/metadatapub/releases/latest">Descargar plugin</a> ·
  <a href="#instalación">Instalación</a> ·
  <a href="#configuración">Configuración</a> ·
  <a href="#uso">Uso</a>
</p>

---

## Instalación

1. Descarga el ZIP instalable `MetadataPUB-X.Y.Z.zip` desde
   [Releases](https://github.com/rlibanez/metadatapub/releases).
   También puedes generarlo siguiendo [Desarrollo](#desarrollo).
2. Opcionalmente, preconfigura los identificadores editando `defaults.txt` dentro
   del ZIP antes de importarlo. Consulta [Configuración → Valores iniciales:
   defaults.txt](#valores-iniciales-defaultstxt).
3. En Calibre, abre **Preferences → Plugins → Load plugin from file**
   (Preferencias → Complementos → Cargar complemento desde un archivo).
4. Selecciona el ZIP y reinicia Calibre cuando lo solicite.
5. Añade **MetadataPUB** a la barra desde **Preferences → Toolbars & menus →
   The main toolbar** si el botón no aparece.

Para actualizar, instala el nuevo ZIP mediante el mismo procedimiento y reinicia
Calibre. La configuración personalizada se conserva.

## Configuración

Abre **Preferences → Plugins**, selecciona **MetadataPUB** y pulsa
**Customize plugin** (Personalizar complemento).

### Identificadores

Escribe un tipo de identificador por línea, sin dos puntos ni valor. Por ejemplo:

```text
hardcover
hardcover_book
hardcover_edition
isbn
```

El orden de las líneas determina el orden de las columnas. Los tipos se guardan
en minúsculas y admiten letras, números, guiones y guiones bajos; no se admiten
nombres repetidos, espacios ni dos puntos. Las líneas vacías se ignoran.

Puedes dejar la lista vacía: el plugin indicará que debes configurar algún
identificador antes de analizar libros. Quitar un tipo de la configuración no
elimina ese identificador de los libros.

La configuración se guarda en el perfil de Calibre y se aplica a todas sus
bibliotecas. Los cambios se utilizan al volver a abrir MetadataPUB; una tabla
que ya esté abierta conserva su configuración original.

### Libros que aparecen en la tabla

La casilla **Mostrar todos los EPUB seleccionados** permite elegir:

- **Marcada:** muestra todos los EPUB seleccionados, completos e incompletos.
- **Desmarcada (valor inicial):** muestra solamente los EPUB con algún
  identificador configurado vacío o ausente dentro del archivo.

Una diferencia con la ficha de Calibre, por sí sola, no hace aparecer un EPUB
completo cuando la casilla está desmarcada. Los errores de lectura se muestran
en ambos modos para permitir su revisión. Los libros sin formato EPUB se omiten.

### Valores iniciales: defaults.txt

El ZIP contiene `defaults.txt` en su raíz. Puedes editarlo antes de instalar el
plugin: es texto UTF-8, con un tipo de identificador por línea. No hace falta
modificar archivos Python. El paquete incluye inicialmente:

```text
hardcover
hardcover_book
hardcover_edition
isbn
```

Si `defaults.txt` está vacío, no hay identificadores predeterminados. El botón
**Restablecer valores de defaults.txt** muestra automáticamente cuántos contiene
y carga esa lista en el editor; guarda la configuración para aplicarla.

La configuración personalizada guardada tiene prioridad sobre `defaults.txt`,
incluso si la lista guardada está vacía. Cambiar el archivo en un nuevo ZIP no
sobrescribe esa configuración: utiliza el botón de restablecer para adoptarla.

## Uso

1. Selecciona en Calibre los libros que quieres revisar y pulsa **MetadataPUB**.
   Para revisar toda la lista visible, selecciónala con **Ctrl+A**; la selección
   depende de la búsqueda o biblioteca virtual activa.
2. Completa o corrige los valores en la tabla.
3. Pulsa **Revisar y guardar cambios**. Abre los detalles del diálogo para
   comprobar los valores propuestos y confirma el guardado.
4. Revisa la columna **Estado** para conocer el resultado de cada libro.

El plugin trabaja sobre los EPUB de los libros seleccionados. No descarga
metadatos ni consulta servicios externos.

### Cómo interpretar la tabla

| Columna | Contenido |
| --- | --- |
| ID / título | Identificador del registro en Calibre y título leído del EPUB. |
| Columnas de identificadores | Valores encontrados dentro del EPUB; son editables. |
| Valores en Calibre | Valores de la ficha de Calibre que difieren de los encontrados en el EPUB. |
| Estado | Campos ausentes en el EPUB, diferencias con Calibre, errores o resultado del guardado. |

La ficha de Calibre y el archivo EPUB pueden contener valores diferentes.
Por ejemplo, `isbn` puede estar en la ficha y faltar dentro del archivo: aparecerá
en **Valores en Calibre** y como ausente en el EPUB. Puedes copiar su valor a la
columna correspondiente para incrustarlo mediante MetadataPUB.

Un campo que dejes vacío significa **no modificar**; no elimina un valor
existente. Los valores no vacíos que cambien el EPUB o la ficha se guardan en
ambos lugares. Los identificadores que no hayas cambiado se conservan en cada
fuente; el plugin no sincroniza automáticamente todos los metadatos del libro.

## Ver lectura EPUB

Selecciona una fila y pulsa **Ver lectura EPUB** para abrir un informe visible
con texto seleccionable y los botones **Copiar informe** y **Cerrar**.

El informe incluye la versión del plugin, biblioteca, ID del libro, información
del formato EPUB, ruta del OPF indicada por `META-INF/container.xml`, tipos
configurados, identificadores XML y valores de Calibre. También muestra los
hashes del EPUB al analizar y al consultar el informe, para detectar cambios
entre ambas lecturas. Esta operación no modifica el libro.

## Escritura y copias de seguridad

MetadataPUB utiliza la API EPUB de Calibre para preparar los cambios en una
copia en memoria. Antes de sustituir el formato comprueba:

- La integridad del ZIP y el empaquetado EPUB del resultado.
- La conservación del identificador principal del libro.
- Los valores previstos y los identificadores previos reconocidos por Calibre.
- Que los archivos internos distintos del OPF mantengan su contenido, mediante
  hashes de sus datos descomprimidos.

Calibre puede normalizar otros metadatos del OPF. No se convierte el libro ni se
ejecutan los hooks de otros plugins al reemplazar su formato. Después del
reemplazo se verifica el EPUB guardado y la actualización de los identificadores
correspondientes en la ficha.

Los originales se guardan antes de reemplazarlos en:

```text
<biblioteca>/metadatapub-backups/<fecha-hora-id>/<ID>.epub
<biblioteca>/metadatapub-backups/<fecha-hora-id>/<ID>.json
```

El JSON contiene el ID del libro, los identificadores originales de su ficha y
los cambios solicitados. La fecha y hora corresponden al entorno de Calibre.
Los respaldos no se eliminan automáticamente; necesitas espacio y permiso de
escritura en la carpeta de la biblioteca.

Si falla la aplicación de los cambios, se intenta restaurar el EPUB y sus
identificadores de biblioteca. La columna Estado informa de la restauración o
de sus errores. Cada libro se procesa por separado: no hay una transacción
atómica entre archivo y base de datos ni para toda la selección. Un cierre
abrupto puede requerir recuperación manual.

### Recuperación manual

1. Localiza el respaldo cuyo ID corresponde al libro que quieres restaurar.
2. Selecciona ese registro en Calibre y utiliza **Añadir archivos a los registros
   de libros seleccionados** para reemplazar su EPUB con el respaldo.
3. En **Editar metadatos**, restaura los identificadores de su ficha usando el
   apartado `identifiers` del JSON correspondiente.

No añadas el respaldo como un libro nuevo. Mantén también tu copia habitual de
la biblioteca.

## Límites y validación

Se rechazan EPUB con firmas digitales, varios OPF, estructura inválida o tipos
de identificador configurados que aparezcan duplicados. Si el EPUB o los
identificadores de su ficha cambian desde el análisis, vuelve a abrir la tabla
para analizarlos de nuevo. Los libros se procesan secuencialmente; selecciones
grandes pueden tardar.

## Desarrollo

El código del plugin está en `plugin/`; `build.py` genera el ZIP instalable en
`dist/`. Desde la raíz del proyecto:

```sh
calibre-debug -e tests/check_calibre.py
python3 build.py
```

Las pruebas de interfaz y configuración de `tests/` requieren instalar primero
el ZIP en un perfil de Calibre dedicado a pruebas. No las ejecutes con tu perfil
habitual: algunas pruebas cambian las preferencias del plugin.

Consulta el [historial de cambios](CHANGELOG.md).
