# GrabaClip

Grabador de pantalla y **clips instantáneos** para Windows, ligero y open source.
Guarda los últimos segundos de tu partida con una tecla, como el "Instant Replay" de NVIDIA.

## Funciones

- **Clips instantáneos:** GrabaClip graba en segundo plano y, al pulsar **F9**, guarda los últimos 10–300 segundos.
- **Grabación normal:** **F10** empieza y termina una grabación larga.
- **Codificación por GPU:** usa NVIDIA NVENC, AMD AMF o Intel QuickSync. Si la tarjeta lo permite, la captura va directo de la pantalla a la GPU, casi sin usar el procesador.
- **Pistas de audio separadas:** pista 1 con todo mezclado, micrófono aparte y una pista por cada app que elijas (Discord, Spotify, el juego…), para silenciarlas al editar.
- **Organización por juego:** cada clip se guarda en una carpeta con el nombre del juego o la app que estaba en primer plano.
- **Biblioteca:** miniaturas, duración, filtros por tipo y juego, buscador, reproducir, mostrar en carpeta y enviar a la Papelera.
- **Ajustes:** FPS (30–240), calidad, resolución, duración del clip, teclas personalizables, 13 temas de color.
- **Iniciar con Windows** (opcional) y activar los clips automáticamente.

## Descarga

Descarga `GrabaClip-vX.Y.Z-portable.zip` desde [Releases](../../releases), descomprímelo en el Escritorio o en Documentos y abre `GrabaClip.exe`. No necesita instalación: Python, FFmpeg y todo lo demás vienen incluidos.

Requisitos: Windows 10 (versión 2004 o más nueva) u 11 de 64 bits, y el runtime WebView2 (incluido en Windows 11 y en Windows 10 actualizado).

## Desinstalar

1. Si activaste **Iniciar con Windows**, desactívalo en *Ajustes → General* (o borra el valor `GrabaClip` en `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
2. Cierra GrabaClip y borra su carpeta.
3. Tus videos están en `Videos\GrabaClip`; bórralos solo si ya no los quieres.

GrabaClip no instala servicios, controladores ni nada fuera de su carpeta, salvo esa entrada opcional de inicio.

## Compilar

El paquete se compila en Linux (o en GitHub Actions) con [llvm-mingw](https://github.com/mstorsjo/llvm-mingw):

```bash
./build/build.sh   # -> dist/GrabaClip-vX.Y.Z-portable.zip
```

Las versiones publicadas se compilan automáticamente con GitHub Actions a partir de este repositorio (ver `.github/workflows/build.yml`).

## Política de firma de código

Firma de código gratuita proporcionada por [SignPath.io](https://about.signpath.io), certificado de [SignPath Foundation](https://signpath.org).

- **Autores y revisores (committers and reviewers):** [@USUARIO](https://github.com/USUARIO)
- **Aprobadores (approvers):** [@USUARIO](https://github.com/USUARIO)

Solo se firman los binarios compilados por GitHub Actions a partir del código de este repositorio (`GrabaClip.exe` y `audiocap.exe`). Python y FFmpeg se incluyen tal como los publican sus proyectos.

## Privacidad

Consulta [PRIVACIDAD.md](PRIVACIDAD.md). En resumen: este programa no transfiere ninguna información a otros sistemas de la red, a menos que el usuario lo pida expresamente.

## Licencia

[MIT](LICENSE). Componentes de terceros en [docs/TERCEROS.txt](docs/TERCEROS.txt).
