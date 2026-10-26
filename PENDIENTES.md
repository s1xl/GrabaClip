# Pendientes de GrabaClip

Lista de trabajo acordada el 26 de octubre de 2026, en orden de prioridad.

## 1. Probar en Windows lo que aún no se ha visto funcionar (urgente)

- [ ] **Comandos de voz (Jarvis):** confirmar que la corrección de `voz.py` (carga de System.Speech por nombre completo / ruta del GAC) muestra "Escuchando…". Si falla, revisar `logs\voz.txt`.
- [x] **Publicar 0.10.1** con esa corrección y la opción de elegir la carpeta de videos.
- [ ] **Overlay:** botón "Probar" en Ajustes > General; revisar sobre un juego en pantalla completa sin bordes.
- [ ] **Grabar solo la ventana del juego** (gfxcapture): guardar un clip con Discord encima y comprobar que solo sale el juego. Revisar `logs\gpu.txt` ("Captura de ventana").
- [ ] **Sincronía del audio:** comprobar que voz y juego no van desfasados respecto al video.

## 2. Ícono junto al reloj (bandeja del sistema)

- [ ] Al cerrar la ventana, que GrabaClip siga funcionando junto al reloj en lugar de cerrarse.
- [ ] Menú con clic derecho: Abrir, Guardar clip, Activar/desactivar clips, Grabar, Salir.
- [ ] Con "Iniciar con Windows", arrancar directo en la bandeja.

## 3. Recortar y compartir clips

- [ ] Recortar un clip desde la biblioteca (inicio y fin) sin volver a comprimir.
- [ ] "Preparar para Discord": versión comprimida de menos de 10 MB.
- [ ] Copiar el clip al portapapeles para pegarlo con Ctrl+V.

## 4. Aviso de actualizaciones

- [ ] Revisar GitHub Releases al abrir y avisar si hay versión nueva.
- [ ] Interruptor para desactivarlo (sería la única conexión a internet; actualizar PRIVACIDAD.md).

## 5. Control del espacio en disco

- [ ] Mostrar cuánto ocupan todos los clips.
- [ ] Opción de enviar a la Papelera lo más viejo al pasar de un tamaño máximo.

## 6. Avisos de Windows (cuando haya más usuarios)

- [ ] Solicitar la firma gratuita en signpath.org/apply (el flujo de GitHub Actions ya está listo).
- [ ] Compatibilidad con Control inteligente de aplicaciones (FFmpeg sin firma): evaluar usar Media Foundation de Windows.

## Extras

- [ ] Versión vertical (9:16) del anuncio para TikTok y Reels.
