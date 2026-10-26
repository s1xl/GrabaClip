# Política de privacidad de GrabaClip

**This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.**

Este programa no transfiere ninguna información a otros sistemas de la red, a menos que el usuario o quien lo instala u opera lo pida expresamente.

## Qué hace GrabaClip con tus datos

- Los videos, las miniaturas y la configuración se guardan **solo en tu computadora**: en `Videos\GrabaClip` y en la carpeta del programa.
- Para organizar los clips por juego, GrabaClip lee el **nombre del programa en primer plano** en el momento de guardar. Ese nombre solo se usa como nombre de carpeta y no sale de tu PC.
- Las teclas rápidas se detectan en tu equipo. GrabaClip solo reacciona a las combinaciones que configuraste y **no registra ni guarda lo que escribes**.
- **Comandos de voz** (apagados por defecto): si los activas, el micrófono se escucha con el reconocimiento de voz que trae Windows, **en tu PC y sin internet**. GrabaClip solo compara lo que oye con tus frases (por ejemplo "Jarvis, sácale clip"); no graba, no guarda y no envía tu voz. Lo único que muestra es la última frase reconocida, para que puedas ajustar la exigencia.
- **Discord** (apagado por defecto): si activas *Mostrar en Discord*, GrabaClip le dice a la app de Discord abierta en tu PC (por su conexión local, no por internet) que estás usando GrabaClip y, si lo permites, el nombre del juego. Discord muestra esa actividad en tu perfil a quienes pueden verlo, según tus ajustes de privacidad de Discord.
- No hay telemetría, estadísticas, anuncios ni cuentas.

## Conexiones a internet

La versión publicada ya trae todos sus componentes y no se conecta a internet por su cuenta.

- **Actualizaciones:** solo cuando pulsas *Buscar actualizaciones* (o si activas *Avisar al abrir si hay versión nueva*, apagado por defecto), GrabaClip consulta la última versión publicada en GitHub (`api.github.com/repos/s1xl/GrabaClip`) y, si pulsas *Actualizar ahora*, descarga el `.zip` de esa versión desde GitHub y comprueba su huella SHA-256. No se envía ningún dato personal; GitHub solo recibe la petición normal de cualquier navegador (dirección IP y el nombre "GrabaClip-actualizador").

 Solo si faltan los componentes de la interfaz (por ejemplo, en una copia incompleta), el lanzador los descarga una vez desde el índice oficial de paquetes de Python (pypi.org), avisando con una ventana visible. No se envía ningún dato personal.
