# Pendientes de GrabaClip

Lista de trabajo acordada el 26 de octubre de 2026, en orden de prioridad.

## 1. Probar en Windows lo que aún no se ha visto funcionar (urgente)

- [ ] **Comandos de voz (Jarvis):** confirmar que la corrección de `voz.py` (carga de System.Speech por nombre completo / ruta del GAC) muestra "Escuchando…". Si falla, revisar `logs\voz.txt`.
- [x] **Publicar 0.10.1** con esa corrección y la opción de elegir la carpeta de videos.
- [ ] **Overlay:** botón "Probar" en Ajustes > General; revisar sobre un juego en pantalla completa sin bordes.
- [ ] **Grabar solo la ventana del juego** (gfxcapture): guardar un clip con Discord encima y comprobar que solo sale el juego. Revisar `logs\gpu.txt` ("Captura de ventana").
- [ ] **Sincronía del audio:** comprobar que voz y juego no van desfasados respecto al video.

## 2. Ícono junto al reloj (bandeja del sistema)

- [x] Al cerrar la ventana, que GrabaClip siga funcionando junto al reloj en lugar de cerrarse.
- [x] Menú con clic derecho: Abrir, Guardar clip, Activar/desactivar clips, Grabar, Salir.
- [x] Con "Iniciar con Windows", arrancar directo en la bandeja.

## 3. Recortar y compartir clips

- [x] Recortar un clip desde la biblioteca (inicio y fin), exacto y con todas las pistas (0.14.0).
- [x] "Preparar para Discord": versión comprimida de menos de 10 MB.
- [x] Copiar el clip al portapapeles para pegarlo con Ctrl+V.

## 4. Aviso de actualizaciones

- [x] Botón "Buscar actualizaciones" que descarga e instala la versión nueva (0.11.0).
- [x] Interruptor "Avisar al abrir" (apagado por defecto) y PRIVACIDAD.md actualizado.
- [x] Probada en Windows la primera actualización real (0.11.0 -> 0.12.0).

## 5. Control del espacio en disco

- [x] Mostrar cuánto ocupan todos los clips. (0.18.0)
- [x] Opción de enviar a la Papelera lo más viejo al pasar de un tamaño máximo. (0.18.0)

## 6. Avisos de Windows (cuando haya más usuarios)

- [x] Repositorio listo para SignPath: sección "Code signing policy" en el README y en cada release, privacidad, desinstalación, código de conducta, roles.
- [ ] **(s1xl)** Activar la verificación en dos pasos (2FA) en GitHub: SignPath la exige a todo el equipo.
- [ ] **(s1xl)** Enviar el formulario en signpath.org/apply con los textos preparados.
- [ ] Riesgo a revisar con SignPath: `runtime\python\...\webview\lib` trae DLL de Microsoft (WebView2 SDK), que no son open source; preguntar si cuentan como bibliotecas del sistema.
- [x] Evaluado Control inteligente de aplicaciones: bloquea cualquier DLL/EXE sin firma ni reputación (FFmpeg, Python). La firma de SignPath solo cubre GrabaClip.exe y audiocap.exe; SignPath no permite firmar FFmpeg. La única solución completa es reemplazar FFmpeg por un capturador propio con Media Foundation (firmado por Microsoft) y Windows.Graphics.Capture: captura, H.264 por GPU y MP4 con varias pistas en C++. Es un trabajo grande; queda para cuando haya más usuarios. Mientras tanto, a quien le pase: desde la actualización de Windows 11 de abril de 2026 el Control inteligente se puede apagar y volver a encender sin reinstalar (explicado en el README, "Problemas comunes").

## Extras

- [x] Versión vertical (9:16) del anuncio para TikTok y Reels (`docs/GrabaClip-anuncio-vertical.mp4`).

## Hecho además de la lista (0.10.1 – 0.17.0)

- [x] Elegir la carpeta de los videos (0.10.1).
- [x] La captura se reanuda sola cuando Windows la corta (error 887a0026) (0.10.2).
- [x] Audio en una sola pista o separadas; pistas y apps divididas en activas e inactivas (0.13.0 – 0.14.0).
- [x] Menos memoria al quedar junto al reloj y modo rendimiento (0.15.0).
- [x] Arreglo del ícono junto al reloj que dejaba de responder con doble clic (0.16.0).
- [x] Discord Rich Presence "Clipeando con GrabaClip", probado en Discord (0.17.0).
