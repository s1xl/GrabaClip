# GrabaClip

Grabador de pantalla y **clips instantáneos** para Windows, ligero y open source.
Guarda los últimos segundos de tu partida con una tecla, como el "Instant Replay" de NVIDIA.

<p align="center">
  <a href="docs/GrabaClip-anuncio.mp4"><img src="docs/anuncio.webp" alt="Anuncio de GrabaClip" width="100%"></a>
</p>

<p align="center"><a href="https://github.com/s1xl/GrabaClip/releases/latest"><b>⬇ Descargar GrabaClip</b></a> · <a href="docs/GrabaClip-anuncio.mp4">Ver el anuncio con sonido</a> (<a href="docs/GrabaClip-anuncio-vertical.mp4">vertical</a>) · <a href="#code-signing-policy">Code signing policy</a> · <a href="PRIVACIDAD.md">Privacidad</a></p>

## Funciones

- **Clips instantáneos:** GrabaClip graba en segundo plano y, al pulsar **F9**, guarda los últimos 10–300 segundos.
- **Grabación normal:** **F10** empieza y termina una grabación larga. **F8** activa o desactiva los clips desde el juego.
- **Capturas y marcas:** **F7** guarda una captura de pantalla del juego en la biblioteca; **F6** pone una marca durante una grabación, que luego aparece en el editor y como capítulo del video.
- **Codificación por GPU:** usa NVIDIA NVENC, AMD AMF o Intel QuickSync. Si la tarjeta lo permite, la captura va directo de la pantalla a la GPU, casi sin usar el procesador.
- **Graba solo el juego:** captura únicamente la ventana del juego (aunque haya otras ventanas encima), sigue automáticamente al juego que uses y, si quieres, graba la pantalla cuando no hay ningún juego abierto. También se puede grabar una pantalla completa a elegir.
- **Audio a tu gusto:** todo junto en una sola pista (lo más simple) o **pistas separadas**: una mezcla con todo, micrófono aparte y una pista por cada app que elijas (Discord, Spotify, el juego…), en el orden que quieras, para silenciarlas al editar. Las apps cerradas aparecen como inactivas y no ocupan lugar en el orden. Las pistas que quedan sin sonido (por ejemplo, si Discord estaba cerrado) se quitan al guardar.
- **Comandos de voz:** "Jarvis, sácale clip" y las frases que tú quieras para guardar clips, grabar o activar los clips. Usa el reconocimiento de voz de Windows, sin internet.
- **Overlay en el juego:** indicador de clips activos / REC y aviso al guardar un clip, con sonidos suaves. No recibe clics y no aparece en las grabaciones (se puede desactivar).
- **Organización por juego:** cada clip se guarda en una carpeta con el nombre del juego o la app que estaba en primer plano.
- **Carpeta a elegir:** por defecto en `Videos\GrabaClip`, o en la carpeta o disco que quieras (*Ajustes → General → Carpeta de videos*).
- **Biblioteca:** miniaturas, duración, filtros por tipo y juego, buscador, ordenar por fecha, tamaño o duración, **favoritos** ⭐ (el límite de espacio nunca los borra), renombrar con un clic y seleccionar varios para mandarlos a la Papelera.
- **Discord Rich Presence** (opcional): "Clipeando con GrabaClip" en tu perfil, con el juego y un botón para descargarlo.
- **Espacio en disco:** muestra cuánto ocupan tus videos y, si pones un límite (20–500 GB), manda los clips más viejos a la Papelera automáticamente.
- **Compartir:** copia el clip para pegarlo con Ctrl+V en Discord o WhatsApp, o crea una **versión para Discord** de menos de 10 MB que se copia sola.
- **Recortar clips:** editor dentro de la app con vista previa; elige inicio y fin con la barra o con las teclas I y O. Guarda una copia (o reemplaza el original) conservando todas las pistas de audio.
- **Ajustes:** FPS (30–240), calidad, resolución, duración del clip, teclas personalizables, 13 temas de color.
- **Iniciar con Windows** (opcional) y activar los clips automáticamente.
- **Ligero:** al quedar junto al reloj, la interfaz se descarga y libera su memoria. El **modo rendimiento** deja solo lo necesario (clips, grabación y teclas).
- **Junto al reloj:** al cerrar la ventana, GrabaClip sigue funcionando en los íconos ocultos de la barra de tareas, con un menú para guardar clips, grabar o salir.
- **Actualizaciones con un botón:** *Ajustes → General → Buscar actualizaciones* descarga la última versión de GitHub y la instala sola, sin perder ajustes ni clips.

## Descarga

Descarga `GrabaClip-vX.Y.Z-portable.zip` desde [Releases](https://github.com/s1xl/GrabaClip/releases/latest), descomprímelo en el Escritorio o en Documentos y abre `GrabaClip.exe`. No necesita instalación: Python, FFmpeg y todo lo demás vienen incluidos.

Requisitos: Windows 10 (versión 2004 o más nueva) u 11 de 64 bits, y el runtime WebView2 (incluido en Windows 11 y en Windows 10 actualizado).

## Problemas comunes

- **"Windows protegió su PC" (SmartScreen):** pulsa *Más información → Ejecutar de todas formas*. Sale porque GrabaClip todavía no está firmado.
- **Todas las opciones de "Codificar con" dicen "No funcionó":** casi siempre es el **Control inteligente de aplicaciones** de Windows 11 bloqueando FFmpeg, que no viene firmado. Se puede apagar en *Seguridad de Windows → Control de aplicaciones y navegador → Control inteligente de aplicaciones*. Con Windows 11 actualizado (abril de 2026 o más nuevo) se puede volver a encender después; en versiones anteriores, apagarlo es permanente hasta reinstalar Windows.
- **Si la ventana deja de responder:** cierra GrabaClip desde el Administrador de tareas y manda la carpeta `logs` al crear un *issue*.

## Desinstalar

1. Si activaste **Iniciar con Windows**, desactívalo en *Ajustes → General* (o borra el valor `GrabaClip` en `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
2. Cierra GrabaClip (clic derecho en su ícono junto al reloj → *Salir*) y borra su carpeta.
3. Tus videos están en `Videos\GrabaClip` (o en la carpeta que elegiste); bórralos solo si ya no los quieres.

GrabaClip no instala servicios, controladores ni nada fuera de su carpeta, salvo esa entrada opcional de inicio.

## Compilar

El paquete se compila en Linux (o en GitHub Actions) con [llvm-mingw](https://github.com/mstorsjo/llvm-mingw):

```bash
./build/build.sh   # -> dist/GrabaClip-vX.Y.Z-portable.zip
```

Las versiones publicadas se compilan automáticamente con GitHub Actions a partir de este repositorio (ver `.github/workflows/build.yml`).

## Code signing policy

*(Política de firma de código)*


Firma de código gratuita proporcionada por [SignPath.io](https://about.signpath.io), certificado de [SignPath Foundation](https://signpath.org).

- **Autores y revisores (committers and reviewers):** [@s1xl](https://github.com/s1xl)
- **Aprobadores (approvers):** [@s1xl](https://github.com/s1xl)

Free code signing provided by SignPath.io, certificate by SignPath Foundation. Only binaries built by GitHub Actions from this repository are signed.

Solo se firman los binarios compilados por GitHub Actions a partir del código de este repositorio (`GrabaClip.exe` y `audiocap.exe`). Python y FFmpeg se incluyen tal como los publican sus proyectos.

## Privacidad

Consulta [PRIVACIDAD.md](PRIVACIDAD.md). En resumen: este programa no transfiere ninguna información a otros sistemas de la red, a menos que el usuario lo pida expresamente.

## Conducta

Consulta [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Licencia

[MIT](LICENSE). Componentes de terceros en [docs/TERCEROS.txt](docs/TERCEROS.txt).
