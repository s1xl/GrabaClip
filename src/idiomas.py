"""Traducciones de GrabaClip.

La app está escrita en español. Este archivo traduce lo que se ve al inglés y al portugués:
- T(...): textos exactos  ->  (español, inglés, portugués)
- P(...): textos con partes variables, marcadas con {0}, {1}...  (ej. "Clip guardado en {0}")
La interfaz (ui.html) recibe este catálogo y traduce todo lo que aparece en pantalla, incluidos
los avisos que manda Python. El overlay, el menú del ícono y Discord usan t() de aquí.

Francés, árabe y ruso están en lang/<código>.json: {"exacto": {español: traducción},
"patrones": [[español con {0}, traducción con {0}], ...]}. Para agregar un idioma basta con
otro archivo así y su nombre en IDIOMAS (si falta una traducción, se muestra en español).
"""
import json
import os
import re

IDIOMAS = {"es": "Español", "en": "English", "pt": "Português (Brasil)", "fr": "Français",
           "ar": "العربية", "ru": "Русский"}
RTL = {"ar"}  # idiomas que se escriben de derecha a izquierda
ACTUAL = "es"
_EXACTO = {}
_PATRONES = {}


def T(es, en, pt):
    _EXACTO.setdefault("en", {})[es] = en
    _EXACTO.setdefault("pt", {})[es] = pt


def P(es, en, pt):
    _PATRONES.setdefault("en", []).append((es, en))
    _PATRONES.setdefault("pt", []).append((es, pt))


# ======================= interfaz: pestañas, botones y títulos =======================
T("Grabaciones", "Recordings", "Gravações")
T("Estadísticas", "Statistics", "Estatísticas")
T("Ajustes", "Settings", "Configurações")
T("Ayuda", "Help", "Ajuda")
T("Buscar grabaciones", "Search recordings", "Buscar gravações")
T("Cambiar tema", "Change theme", "Mudar tema")
T("Detectando GPU…", "Detecting GPU…", "Detectando GPU…")
T("No se puede grabar", "Can't record", "Não é possível gravar")
T("GrabaClip no puede grabar en esta PC", "GrabaClip can't record on this PC", "O GrabaClip não consegue gravar neste PC")
T("El video va directo de la pantalla a la tarjeta gráfica, casi sin usar el procesador",
  "Video goes straight from the screen to the graphics card, barely using the CPU",
  "O vídeo vai direto da tela para a placa de vídeo, quase sem usar o processador")
T("Todos", "All", "Todos")
T("Clips", "Clips", "Clipes")
T("Capturas", "Screenshots", "Capturas")
T("Favoritos", "Favorites", "Favoritos")
T("Favorito", "Favorite", "Favorito")
T("Todos los juegos", "All games", "Todos os jogos")
T("Filtrar por juego o app", "Filter by game or app", "Filtrar por jogo ou app")
T("Ordenar", "Sort", "Ordenar")
T("Más nuevos", "Newest", "Mais recentes")
T("Más viejos", "Oldest", "Mais antigos")
T("Más pesados", "Largest", "Maiores")
T("Más largos", "Longest", "Mais longos")
T("Nombre", "Name", "Nome")
T("Seleccionar", "Select", "Selecionar")
T("Seleccionar todos", "Select all", "Selecionar todos")
T("Unir", "Join", "Juntar")
T("Une los videos elegidos en uno, en el orden en que se grabaron",
  "Joins the selected videos into one, in the order they were recorded",
  "Junta os vídeos escolhidos em um só, na ordem em que foram gravados")
T("Enviar a la Papelera", "Move to Recycle Bin", "Mover para a Lixeira")
T("Cancelar", "Cancel", "Cancelar")
T("Sin clasificar", "Unsorted", "Sem categoria")
T("CLIP", "CLIP", "CLIPE")
T("CAPTURA", "SCREENSHOT", "CAPTURA")
T("GRABACIÓN", "RECORDING", "GRAVAÇÃO")
T("Reproducir", "Play", "Reproduzir")
T("Abrir", "Open", "Abrir")
T("Pausa", "Pause", "Pausar")
T("Compartir", "Share", "Compartilhar")
T("Recortar", "Trim", "Cortar")
T("Mostrar en la carpeta", "Show in folder", "Mostrar na pasta")
T("Clic para renombrar", "Click to rename", "Clique para renomear")
T("Quitar de favoritos", "Remove from favorites", "Remover dos favoritos")
T("Marcar como favorito (el límite de espacio nunca lo borra)", "Mark as favorite (the space limit never deletes it)",
  "Marcar como favorito (o limite de espaço nunca o apaga)")
T("Sin resultados", "No results", "Sem resultados")
T("Prueba con otra búsqueda o filtro.", "Try another search or filter.", "Tente outra busca ou filtro.")
T("Aún no tienes grabaciones", "No recordings yet", "Você ainda não tem gravações")
T("Activa los clips instantáneos abajo y pulsa", "Turn on instant clips below and press", "Ative os clipes instantâneos abaixo e pressione")
T(", o pulsa REC para grabar.", ", or press REC to record.", ", ou pressione REC para gravar.")
T("Clips instantáneos", "Instant clips", "Clipes instantâneos")
T("Desactivados", "Off", "Desativados")
T("Esperando a que abras un juego…", "Waiting for you to open a game…", "Esperando você abrir um jogo…")
T("Abrir carpeta", "Open folder", "Abrir pasta")
T("REC", "REC", "REC")
T("Detener grabación", "Stop recording", "Parar gravação")
T("Empezar a grabar", "Start recording", "Começar a gravar")
T("Pantalla", "Screen", "Tela")
T("Pantalla 1", "Screen 1", "Tela 1")
T("Algo falla", "Something's wrong", "Algo deu errado")
T("Eliminar", "Delete", "Excluir")
T("Aplicar", "Apply", "Aplicar")
T("Reemplazar", "Replace", "Substituir")
T("Listo", "Done", "Pronto")
T("Guardar", "Save", "Salvar")
T("Renombrar", "Rename", "Renomear")
T("Mostrar más", "Show more", "Mostrar mais")
T("Subir", "Move up", "Subir")
T("Bajar", "Move down", "Descer")
T("Quitar", "Remove", "Remover")
T("Cerrar (Esc)", "Close (Esc)", "Fechar (Esc)")

# ---------- ajustes: secciones ----------
T("Video", "Video", "Vídeo")
T("Audio", "Audio", "Áudio")
T("Teclas", "Hotkeys", "Atalhos")
T("Voz", "Voice", "Voz")
T("General", "General", "Geral")
T("Apariencia", "Appearance", "Aparência")
T("Desactiva los clips y detén la grabación para cambiar estos ajustes.",
  "Turn off clips and stop recording to change these settings.",
  "Desative os clipes e pare a gravação para mudar estas configurações.")

# ---------- video ----------
T("Qué grabar", "What to record", "O que gravar")
T("Solo el juego", "Game only", "Só o jogo")
T("Pantalla completa", "Full screen", "Tela inteira")
T("Ventana a grabar", "Window to record", "Janela para gravar")
T("Automático: el juego que estés usando", "Automatic: the game you're playing", "Automático: o jogo que você estiver usando")
T("Buscar ventanas abiertas", "Find open windows", "Buscar janelas abertas")
T("Actualizar", "Refresh", "Atualizar")
T("En automático graba el juego que estés usando y cambia solo si cambias de juego. Discord, los navegadores y el escritorio no cuentan como juego.",
  "In automatic mode it records the game you're playing and switches by itself if you change games. Discord, browsers and the desktop don't count as games.",
  "No modo automático grava o jogo que você estiver usando e troca sozinho se você mudar de jogo. Discord, navegadores e a área de trabalho não contam como jogo.")
T("Grabar la pantalla cuando no haya un juego", "Record the screen when there's no game", "Gravar a tela quando não houver jogo")
T("Si está apagado, los clips esperan a que abras un juego.", "If off, clips wait until you open a game.", "Se estiver desligado, os clipes esperam você abrir um jogo.")
T("Codificar con", "Encode with", "Codificar com")
T("Cuadros por segundo", "Frames per second", "Quadros por segundo")
T("Calidad", "Quality", "Qualidade")
T("Resolución", "Resolution", "Resolução")
T("Baja", "Low", "Baixa")
T("Media", "Medium", "Média")
T("Alta", "High", "Alta")
T("Muy alta", "Very high", "Muito alta")
T("Máxima", "Maximum", "Máxima")
T("Original", "Original", "Original")
T("Duración de cada clip", "Length of each clip", "Duração de cada clipe")
T("Duración del clip largo", "Long clip length", "Duração do clipe longo")
T("Para cuando la jugada viene de lejos. El búfer guarda el más largo de los dos, así que más tiempo ocupa más espacio temporal en el disco.",
  "For when the play started a while back. The buffer keeps the longer of the two, so more time uses more temporary disk space.",
  "Para quando a jogada vem de longe. O buffer guarda o mais longo dos dois, então mais tempo ocupa mais espaço temporário no disco.")
T("Ajustes por juego", "Per-game settings", "Configurações por jogo")
T("Cada juego puede tener sus propios FPS, calidad y resolución. Los que no estén aquí usan los ajustes de arriba.",
  "Each game can have its own FPS, quality and resolution. Games not listed here use the settings above.",
  "Cada jogo pode ter seus próprios FPS, qualidade e resolução. Os que não estiverem aqui usam as configurações acima.")
T("Elige un juego o programa abierto…", "Pick an open game or program…", "Escolha um jogo ou programa aberto…")
T("Agregar", "Add", "Adicionar")
T("Todavía no hay juegos con ajustes propios.", "No games with their own settings yet.", "Ainda não há jogos com configurações próprias.")
T("FPS general", "Default FPS", "FPS geral")
T("Calidad general", "Default quality", "Qualidade geral")
T("Resolución general", "Default resolution", "Resolução geral")
T("Abre el juego y elígelo de la lista", "Open the game and pick it from the list", "Abra o jogo e escolha-o na lista")
T("Clip automático al cerrar el juego", "Automatic clip when the game closes", "Clipe automático ao fechar o jogo")
T("Cuando cierras el juego, GrabaClip guarda solo los últimos segundos (la pantalla final, el resultado de la partida). Ocupa espacio con cada partida.",
  "When you close the game, GrabaClip saves just the last few seconds (the final screen, the match result). It uses space with every match.",
  "Quando você fecha o jogo, o GrabaClip salva só os últimos segundos (a tela final, o resultado da partida). Ocupa espaço a cada partida.")
T("Más FPS y calidad dan videos más fluidos y nítidos, pero archivos más grandes. Si tu monitor es de 60 Hz, grabar a más de 60 FPS no aporta nada.",
  "More FPS and quality give smoother, sharper videos but bigger files. If your monitor is 60 Hz, recording above 60 FPS adds nothing.",
  "Mais FPS e qualidade deixam os vídeos mais fluidos e nítidos, mas com arquivos maiores. Se o seu monitor é de 60 Hz, gravar acima de 60 FPS não acrescenta nada.")
T("Modo automático: se graba el juego que uses", "Automatic mode: the game you play is recorded", "Modo automático: grava o jogo que você usar")
T("Se grabará solo esa ventana", "Only that window will be recorded", "Só essa janela será gravada")
T(" (cerrado ahora)", " (closed now)", " (fechado agora)")
T("Lista de ventanas actualizada", "Window list refreshed", "Lista de janelas atualizada")
T(" · captura directa", " · direct capture", " · captura direta")
T(" Se grabará la pantalla completa.", " The full screen will be recorded.", " A tela inteira será gravada.")
T("Procesador (CPU)", "Processor (CPU)", "Processador (CPU)")
T("Automático", "Automatic", "Automático")
T("GPU NVIDIA (NVENC)", "NVIDIA GPU (NVENC)", "GPU NVIDIA (NVENC)")
T("GPU AMD (AMF)", "AMD GPU (AMF)", "GPU AMD (AMF)")
T("Procesador (CPU, mas lento)", "Processor (CPU, slower)", "Processador (CPU, mais lento)")
T("No funciono en esta PC.", "Didn't work on this PC.", "Não funcionou neste PC.")
T("Tu driver de NVIDIA es muy antiguo. Actualizalo desde la app de NVIDIA o nvidia.com.",
  "Your NVIDIA driver is too old. Update it from the NVIDIA app or nvidia.com.",
  "Seu driver da NVIDIA é muito antigo. Atualize pelo app da NVIDIA ou em nvidia.com.")
T("No se encontro una tarjeta NVIDIA compatible.", "No compatible NVIDIA card was found.", "Nenhuma placa NVIDIA compatível foi encontrada.")
T("No se encontro una tarjeta AMD compatible (o falta su driver).", "No compatible AMD card was found (or its driver is missing).",
  "Nenhuma placa AMD compatível foi encontrada (ou falta o driver).")
T("Intel QuickSync no esta disponible (sin grafica Intel o desactivada).", "Intel QuickSync isn't available (no Intel graphics, or it's disabled).",
  "O Intel QuickSync não está disponível (sem gráfico Intel ou desativado).")
T("Tu Windows o tu FFmpeg no permiten capturar una sola ventana (necesita Windows 10 1903+ y FFmpeg 8).",
  "Your Windows or FFmpeg can't capture a single window (needs Windows 10 1903+ and FFmpeg 8).",
  "Seu Windows ou FFmpeg não permite capturar uma só janela (precisa do Windows 10 1903+ e FFmpeg 8).")
T("Windows bloqueo FFmpeg (Control inteligente de aplicaciones). Desactivalo en Seguridad de Windows > Control de aplicaciones y navegador.",
  "Windows blocked FFmpeg (Smart App Control). Turn it off in Windows Security > App & browser control.",
  "O Windows bloqueou o FFmpeg (Controle Inteligente de Aplicativos). Desative em Segurança do Windows > Controle de aplicativos e do navegador.")
T("Faltan archivos de FFmpeg. Vuelve a descomprimir GrabaClip completo.", "FFmpeg files are missing. Extract the whole GrabaClip again.",
  "Faltam arquivos do FFmpeg. Descompacte o GrabaClip completo de novo.")
T("Los archivos de FFmpeg estan danados o bloqueados. Vuelve a descomprimir GrabaClip (desbloquea el zip antes).",
  "FFmpeg files are damaged or blocked. Extract GrabaClip again (unblock the zip first).",
  "Os arquivos do FFmpeg estão danificados ou bloqueados. Descompacte o GrabaClip de novo (desbloqueie o zip antes).")
T("Windows o el antivirus no dejan ejecutar FFmpeg (acceso denegado).", "Windows or the antivirus won't let FFmpeg run (access denied).",
  "O Windows ou o antivírus não deixam o FFmpeg rodar (acesso negado).")
T("FFmpeg se cerro de golpe al arrancar.", "FFmpeg crashed on startup.", "O FFmpeg fechou de repente ao iniciar.")
T("No se encontro FFmpeg. Vuelve a descomprimir GrabaClip completo.", "FFmpeg wasn't found. Extract the whole GrabaClip again.",
  "O FFmpeg não foi encontrado. Descompacte o GrabaClip completo de novo.")

# ---------- audio ----------
T("Cómo guardar el audio", "How to save audio", "Como salvar o áudio")
T("Todo en una pista", "All in one track", "Tudo em uma faixa")
T("Pistas separadas", "Separate tracks", "Faixas separadas")
T("Juego, Discord, música y micrófono juntos en una sola pista. Lo más simple para subir o compartir.",
  "Game, Discord, music and mic together in a single track. The simplest for uploading or sharing.",
  "Jogo, Discord, música e microfone juntos em uma só faixa. O mais simples para postar ou compartilhar.")
T("Una pista \"Mezcla\" con todo y otra por cada app que marques, para silenciarlas al editar.",
  "A \"Mix\" track with everything plus one per app you check, so you can mute them when editing.",
  "Uma faixa \"Mix\" com tudo e outra para cada app que você marcar, para silenciá-las ao editar.")
T("Micrófono", "Microphone", "Microfone")
T("Se graba en su propia pista y también en la mezcla.", "Recorded on its own track and in the mix too.", "Gravado em sua própria faixa e também no mix.")
T("Se mezcla con el resto del sonido.", "Mixed with the rest of the sound.", "Misturado com o resto do som.")
T("Apps en pista propia", "Apps on their own track", "Apps em faixa própria")
T("Para poder quitarlas al editar (Discord, Spotify…).", "So you can remove them when editing (Discord, Spotify…).",
  "Para poder tirá-las ao editar (Discord, Spotify…).")
T("con sonido ahora", "playing sound now", "com som agora")
T("· con sonido ahora", "· playing sound now", "· com som agora")
T("· cerradas; su pista se agrega cuando las abras", "· closed; their track is added when you open them", "· fechados; a faixa é adicionada quando você abri-los")
T("cerradas; su pista se agrega cuando las abras", "closed; their track is added when you open them", "fechados; a faixa é adicionada quando você abri-los")
T("● Abierta", "● Open", "● Aberto")
T("Cerrada", "Closed", "Fechado")
T("Lista de apps actualizada", "App list refreshed", "Lista de apps atualizada")
T("Quitar pistas sin sonido al guardar", "Remove silent tracks when saving", "Remover faixas sem som ao salvar")
T("Si una app estaba cerrada o callada, su pista no aparece en el clip. La pista Mezcla siempre se queda.",
  "If an app was closed or silent, its track isn't included in the clip. The Mix track always stays.",
  "Se um app estava fechado ou em silêncio, a faixa dele não aparece no clipe. A faixa Mix sempre fica.")
T("Orden de las pistas", "Track order", "Ordem das faixas")
T("Así aparecen en DaVinci y en tu editor. Arrastra una pista o usa las flechas.",
  "This is how they appear in DaVinci and your editor. Drag a track or use the arrows.",
  "É assim que aparecem no DaVinci e no seu editor. Arraste uma faixa ou use as setas.")
T("Activas", "Active", "Ativas")
T("Inactivas", "Inactive", "Inativas")
T("· la app está cerrada; no ocupa lugar en el orden y se agrega al final cuando la abras",
  "· the app is closed; it takes no place in the order and is added at the end when you open it",
  "· o app está fechado; não ocupa lugar na ordem e é adicionado no fim quando você abri-lo")
T("Mezcla", "Mix", "Mix")
T("Todo el sonido junto", "All sound together", "Todo o som junto")
T("Tu voz", "Your voice", "Sua voz")
T("App", "App", "App")
T("Activa el micrófono o marca apps para ordenar sus pistas.", "Turn on the mic or check apps to order their tracks.",
  "Ative o microfone ou marque apps para ordenar as faixas.")
T("No hay apps con sonido. Abre Discord, Spotify o tu juego y pulsa Actualizar.",
  "No apps with sound. Open Discord, Spotify or your game and press Refresh.",
  "Nenhum app com som. Abra o Discord, o Spotify ou seu jogo e clique em Atualizar.")
T("Sincronía del audio", "Audio sync", "Sincronia do áudio")
T("Úsalo solo si el sonido va adelantado o atrasado respecto a la imagen.", "Use it only if the sound is ahead of or behind the picture.",
  "Use só se o som estiver adiantado ou atrasado em relação à imagem.")
T("La pista \"Mezcla\" lleva todo el sonido junto y nunca se quita.", "The \"Mix\" track carries all the sound together and is never removed.",
  "A faixa \"Mix\" leva todo o som junto e nunca é removida.")

# ---------- teclas ----------
T("Teclas rápidas", "Hotkeys", "Atalhos")
T("Activar / desactivar clips", "Turn clips on / off", "Ativar / desativar clipes")
T("Enciende o apaga los clips instantáneos sin abrir la ventana (suena un aviso).",
  "Turns instant clips on or off without opening the window (a sound plays).",
  "Liga ou desliga os clipes instantâneos sem abrir a janela (toca um aviso).")
T("Guardar clip", "Save clip", "Salvar clipe")
T("Guarda los últimos segundos.", "Saves the last few seconds.", "Salva os últimos segundos.")
T("Guardar clip largo", "Save long clip", "Salvar clipe longo")
T("Guarda más tiempo que el clip normal (se elige en Ajustes → Video).", "Saves more time than a normal clip (set in Settings → Video).",
  "Salva mais tempo que o clipe normal (escolhido em Configurações → Vídeo).")
T("Grabar / detener", "Record / stop", "Gravar / parar")
T("Empieza o termina una grabación.", "Starts or ends a recording.", "Começa ou termina uma gravação.")
T("Mostrar / ocultar GrabaClip", "Show / hide GrabaClip", "Mostrar / ocultar o GrabaClip")
T("Abre la ventana o la vuelve a esconder junto al reloj.", "Opens the window or hides it again next to the clock.",
  "Abre a janela ou esconde de novo ao lado do relógio.")
T("Captura de pantalla", "Screenshot", "Captura de tela")
T("Guarda una imagen del juego en la biblioteca.", "Saves a picture of the game to the library.", "Salva uma imagem do jogo na biblioteca.")
T("Poner una marca", "Add a marker", "Marcar um momento")
T("Mientras grabas, marca el momento para encontrarlo fácil después (en el editor y como capítulo del video).",
  "While recording, marks the moment so you can find it easily later (in the editor and as a video chapter).",
  "Enquanto grava, marca o momento para achar fácil depois (no editor e como capítulo do vídeo).")
T("Haz clic en una tecla y presiona la nueva tecla o combinación (por ejemplo Ctrl + Shift + F9). Esc cancela.",
  "Click a key and press the new key or combination (for example Ctrl + Shift + F9). Esc cancels.",
  "Clique numa tecla e pressione a nova tecla ou combinação (por exemplo Ctrl + Shift + F9). Esc cancela.")
T("Presiona…", "Press…", "Pressione…")
T("Cambio cancelado", "Change cancelled", "Mudança cancelada")

# ---------- voz ----------
T("Comandos de voz", "Voice commands", "Comandos de voz")
T("Escuchar comandos de voz", "Listen for voice commands", "Ouvir comandos de voz")
T("Di una de tus frases y GrabaClip lo hace, como \"Jarvis, sácale clip\". Todo se procesa en tu PC con el reconocimiento de voz de Windows, sin internet.",
  "Say one of your phrases and GrabaClip does it, like \"Jarvis, clip that\". Everything is processed on your PC with Windows speech recognition, no internet.",
  "Diga uma das suas frases e o GrabaClip faz, como \"Jarvis, clipa isso\". Tudo é processado no seu PC com o reconhecimento de voz do Windows, sem internet.")
T("Apagado", "Off", "Desligado")
T("Preparando…", "Getting ready…", "Preparando…")
T("Idioma", "Language", "Idioma")
T("Automático (español si está instalado)", "Automatic (Windows language)", "Automático (idioma do Windows)")
T("Exigencia", "Strictness", "Exigência")
T("Más alto = solo reacciona si está muy seguro de lo que dijiste. Si no te entiende, bájalo; si se activa solo, súbelo.",
  "Higher = it only reacts if it's very sure of what you said. If it doesn't understand you, lower it; if it triggers by itself, raise it.",
  "Mais alto = só reage se tiver muita certeza do que você disse. Se não te entender, abaixe; se ativar sozinho, aumente.")
T("Lo último que entendí", "The last thing I heard", "A última coisa que entendi")
T("Todavía nada. Prueba diciendo una de tus frases.", "Nothing yet. Try saying one of your phrases.", "Nada ainda. Tente dizer uma das suas frases.")
T("Consejo: usa frases de 2 a 4 palabras que empiecen con una palabra poco común, como \"Jarvis\", para que no se active mientras hablas con tus amigos.",
  "Tip: use 2 to 4 word phrases that start with an uncommon word, like \"Jarvis\", so it doesn't trigger while you talk to your friends.",
  "Dica: use frases de 2 a 4 palavras que comecem com uma palavra incomum, como \"Jarvis\", para não ativar enquanto você fala com os amigos.")
T("Agregar otra frase y pulsar Enter", "Add another phrase and press Enter", "Adicione outra frase e pressione Enter")
T("Frase agregada", "Phrase added", "Frase adicionada")
T("Usa al menos 2 palabras para que no se active por error", "Use at least 2 words so it doesn't trigger by mistake",
  "Use pelo menos 2 palavras para não ativar por engano")
T("el idioma de Windows", "the Windows language", "o idioma do Windows")
T("Agrega al menos una frase.", "Add at least one phrase.", "Adicione pelo menos uma frase.")
T("System.Speech no disponible", "System.Speech not available", "System.Speech não disponível")
T("No pude cargar el reconocimiento de voz de Windows (detalles en logs\\voz.txt).",
  "Couldn't load Windows speech recognition (details in logs\\voz.txt).",
  "Não consegui carregar o reconhecimento de voz do Windows (detalhes em logs\\voz.txt).")
T("No encontré un micrófono. Conéctalo o elígelo como predeterminado en Windows.",
  "No microphone found. Plug it in or set it as default in Windows.",
  "Não encontrei um microfone. Conecte ou escolha como padrão no Windows.")
T("✓ hecho", "✓ done", "✓ feito")
T("no alcanzó la exigencia (o fue muy seguido)", "below the strictness (or too soon)", "não atingiu a exigência (ou foi muito seguido)")

# ---------- general ----------
T("Modo rendimiento", "Performance mode", "Modo desempenho")
T("Solo lo necesario: clips, grabación y teclas. Apaga el overlay, los comandos de voz, las miniaturas y las animaciones, para que GrabaClip use lo mínimo mientras juegas.",
  "Only the essentials: clips, recording and hotkeys. Turns off the overlay, voice commands, thumbnails and animations so GrabaClip uses as little as possible while you play.",
  "Só o essencial: clipes, gravação e atalhos. Desliga o overlay, os comandos de voz, as miniaturas e as animações para o GrabaClip usar o mínimo enquanto você joga.")
T("Vista previa al pasar el mouse", "Preview on hover", "Prévia ao passar o mouse")
T("En la biblioteca, el clip se reproduce sin sonido sobre su miniatura.", "In the library, the clip plays muted over its thumbnail.",
  "Na biblioteca, o clipe toca sem som sobre a miniatura.")
T("Sin importar este ajuste, cuando cierras la ventana y GrabaClip queda junto al reloj, la interfaz se descarga y libera casi toda su memoria.",
  "Regardless of this setting, when you close the window and GrabaClip stays next to the clock, the interface unloads and frees almost all its memory.",
  "Independentemente desta opção, quando você fecha a janela e o GrabaClip fica ao lado do relógio, a interface é descarregada e libera quase toda a memória.")
T("Iniciar con Windows", "Start with Windows", "Iniciar com o Windows")
T("GrabaClip se abre junto al reloj al encender la PC.", "GrabaClip opens next to the clock when the PC starts.",
  "O GrabaClip abre ao lado do relógio quando o PC liga.")
T("GrabaClip se abrirá al iniciar Windows", "GrabaClip will open when Windows starts", "O GrabaClip vai abrir ao iniciar o Windows")
T("Inicio con Windows desactivado", "Start with Windows turned off", "Iniciar com o Windows desativado")
T("Al cerrar, seguir junto al reloj", "When closed, keep running by the clock", "Ao fechar, continuar ao lado do relógio")
T("La X esconde la ventana y GrabaClip sigue funcionando en los íconos ocultos. Para salir: clic derecho en su ícono → Salir.",
  "The X hides the window and GrabaClip keeps running in the hidden icons. To quit: right-click its icon → Exit.",
  "O X esconde a janela e o GrabaClip continua rodando nos ícones ocultos. Para sair: clique direito no ícone → Sair.")
T("Activar clips al abrir", "Turn on clips when opened", "Ativar clipes ao abrir")
T("Empieza a guardar el búfer de clips automáticamente.", "Starts filling the clip buffer automatically.", "Começa a encher o buffer de clipes automaticamente.")
T("Organizar por juego", "Organize by game", "Organizar por jogo")
T("Guarda cada clip en una carpeta con el nombre del juego o app que tenías abierto.",
  "Saves each clip in a folder named after the game or app you had open.",
  "Salva cada clipe numa pasta com o nome do jogo ou app que estava aberto.")
T("Sonidos de aviso", "Notification sounds", "Sons de aviso")
T("Al guardar un clip y al activar o desactivar los clips con la tecla.", "When saving a clip and when turning clips on or off with the hotkey.",
  "Ao salvar um clipe e ao ativar ou desativar os clipes pelo atalho.")
T("Overlay en el juego", "In-game overlay", "Overlay no jogo")
T("Avisos pequeños encima del juego. No reciben clics y no salen en tus clips.",
  "Small notices over the game. They don't take clicks and don't show up in your clips.",
  "Avisos pequenos sobre o jogo. Não recebem cliques e não aparecem nos seus clipes.")
T("Indicador de clips activos", "Active clips indicator", "Indicador de clipes ativos")
T("Una pastilla en la esquina: \"Clips\" mientras se guarda el búfer, o \"REC\" con el tiempo al grabar.",
  "A pill in the corner: \"Clips\" while the buffer is running, or \"REC\" with the time while recording.",
  "Uma pílula no canto: \"Clipes\" enquanto o buffer grava, ou \"REC\" com o tempo ao gravar.")
T("Aviso al guardar un clip", "Notice when a clip is saved", "Aviso ao salvar um clipe")
T("Aparece unos segundos con el juego y la duración.", "Shows for a few seconds with the game and length.", "Aparece por alguns segundos com o jogo e a duração.")
T("Esquina", "Corner", "Canto")
T("Arriba a la izquierda", "Top left", "Em cima à esquerda")
T("Arriba a la derecha", "Top right", "Em cima à direita")
T("Probar", "Test", "Testar")
T("Probando…", "Testing…", "Testando…")
T("Se ve en juegos en modo ventana o \"pantalla completa sin bordes\". En pantalla completa exclusiva, Windows no deja dibujar encima (el sonido sí se escucha).",
  "Shows in windowed or \"borderless fullscreen\" games. In exclusive fullscreen Windows doesn't allow drawing on top (you'll still hear the sound).",
  "Aparece em jogos em janela ou \"tela cheia sem bordas\". Em tela cheia exclusiva, o Windows não deixa desenhar por cima (o som ainda toca).")
T("El overlay está desactivado, solo sonó el aviso", "The overlay is off, only the sound played", "O overlay está desligado, só tocou o aviso")
T("Mostrar en Discord", "Show on Discord", "Mostrar no Discord")
T("Tus amigos ven \"Clipeando con GrabaClip\" en tu perfil, con un botón para descargarlo. Solo mientras los clips o una grabación están activos.",
  "Your friends see \"Clipping with GrabaClip\" on your profile, with a button to download it. Only while clips or a recording are active.",
  "Seus amigos veem \"Clipando com o GrabaClip\" no seu perfil, com um botão para baixar. Só enquanto os clipes ou uma gravação estão ativos.")
T("Mostrar el nombre del juego", "Show the game name", "Mostrar o nome do jogo")
T("Por ejemplo \"En Overwatch\".", "For example \"In Overwatch\".", "Por exemplo \"Em Overwatch\".")
T("Carpeta de videos", "Videos folder", "Pasta de vídeos")
T("Restablecer", "Reset", "Restaurar")
T("Cambiar…", "Change…", "Mudar…")
T("Los videos que ya tenías se quedan donde estaban; puedes moverlos a la carpeta nueva con el Explorador.",
  "Videos you already had stay where they were; you can move them to the new folder with File Explorer.",
  "Os vídeos que você já tinha ficam onde estavam; você pode movê-los para a pasta nova com o Explorador.")
T("Espacio en disco", "Disk space", "Espaço em disco")
T("Calculando…", "Calculating…", "Calculando…")
T("Límite de espacio", "Space limit", "Limite de espaço")
T("Sin límite", "No limit", "Sem limite")
T("Los videos se acumulan sin límite.", "Videos pile up with no limit.", "Os vídeos se acumulam sem limite.")
T("Incluir las grabaciones largas", "Include long recordings", "Incluir as gravações longas")
T("Si está apagado, solo se mandan a la Papelera los clips; tus grabaciones (F10) nunca se tocan.",
  "If off, only clips go to the Recycle Bin; your recordings (F10) are never touched.",
  "Se estiver desligado, só os clipes vão para a Lixeira; suas gravações (F10) nunca são tocadas.")
T("Actualizaciones", "Updates", "Atualizações")
T("Buscar actualizaciones", "Check for updates", "Procurar atualizações")
T("Buscando…", "Checking…", "Procurando…")
T("Actualizar ahora", "Update now", "Atualizar agora")
T("Avisar al abrir si hay versión nueva", "Notify on startup if there's a new version", "Avisar ao abrir se houver versão nova")
T("Revisa GitHub una vez al abrir GrabaClip. Es la única conexión a internet que hace.",
  "Checks GitHub once when GrabaClip opens. It's the only internet connection it makes.",
  "Verifica o GitHub uma vez ao abrir o GrabaClip. É a única conexão com a internet que ele faz.")
T("Al actualizar, GrabaClip se cierra unos segundos y se vuelve a abrir solo. Tus ajustes, clips y miniaturas se mantienen.",
  "When updating, GrabaClip closes for a few seconds and reopens by itself. Your settings, clips and thumbnails are kept.",
  "Ao atualizar, o GrabaClip fecha por alguns segundos e abre sozinho de novo. Suas configurações, clipes e miniaturas são mantidos.")
T("Instalando… GrabaClip se cerrará y se abrirá solo en unos segundos.", "Installing… GrabaClip will close and reopen by itself in a few seconds.",
  "Instalando… O GrabaClip vai fechar e abrir sozinho em alguns segundos.")
T("Tienes la versión …", "You have version …", "Você tem a versão …")
T("Idioma de la app", "App language", "Idioma do app")
T("Automático (el de Windows)", "Automatic (Windows language)", "Automático (o do Windows)")

# ---------- ayuda ----------
T("Cómo usar GrabaClip", "How to use GrabaClip", "Como usar o GrabaClip")
T("Activa los clips", "Turn on clips", "Ative os clipes")
T("Enciende \"Clips instantáneos\" abajo a la izquierda o pulsa", "Turn on \"Instant clips\" at the bottom left or press",
  "Ligue \"Clipes instantâneos\" embaixo à esquerda ou pressione")
T("desde el juego. GrabaClip guarda en segundo plano los últimos segundos.", "from the game. GrabaClip keeps the last few seconds in the background.",
  "no jogo. O GrabaClip guarda os últimos segundos em segundo plano.")
T("Guarda el momento", "Save the moment", "Salve o momento")
T("Cuando pase algo bueno pulsa", "When something good happens press", "Quando acontecer algo bom pressione")
T(". El clip aparece en Grabaciones.", ". The clip shows up in Recordings.", ". O clipe aparece em Gravações.")
T("Graba sesiones largas", "Record long sessions", "Grave sessões longas")
T("Pulsa el botón REC o", "Press the REC button or", "Pressione o botão REC ou")
T("para empezar y otra vez para terminar.", "to start and again to stop.", "para começar e de novo para terminar.")
T("Edita sin Discord ni música", "Edit without Discord or music", "Edite sem Discord nem música")
T("En Ajustes → Audio marca tus apps. En DaVinci cada una sale en su propia pista y puedes silenciarla.",
  "In Settings → Audio check your apps. In DaVinci each one gets its own track and you can mute it.",
  "Em Configurações → Áudio marque seus apps. No DaVinci cada um sai na sua própria faixa e você pode silenciá-lo.")
T("Siempre listo", "Always ready", "Sempre pronto")
T("En Ajustes → General activa \"Iniciar con Windows\" y \"Activar clips al abrir\".",
  "In Settings → General turn on \"Start with Windows\" and \"Turn on clips when opened\".",
  "Em Configurações → Geral ative \"Iniciar com o Windows\" e \"Ativar clipes ao abrir\".")
T("Revisa la carpeta \"logs\" junto a GrabaClip. Si el audio va desfasado, ajusta la sincronía en Audio.",
  "Check the \"logs\" folder next to GrabaClip. If the audio is out of sync, adjust the sync in Audio.",
  "Veja a pasta \"logs\" junto ao GrabaClip. Se o áudio estiver dessincronizado, ajuste a sincronia em Áudio.")
T("Grabar", "Record", "Gravar")
T("Empezar / detener grabación", "Start / stop recording", "Começar / parar gravação")
T("Duración", "Length", "Duração")

# ---------- estadísticas ----------
T("Tus estadísticas", "Your statistics", "Suas estatísticas")
T("Clips por semana", "Clips per week", "Clipes por semana")
T("Por juego", "By game", "Por jogo")
T("clip", "clip", "clipe")
T("clips", "clips", "clipes")
T("grabaciones", "recordings", "gravações")
T("capturas", "screenshots", "capturas")
T("de video", "of video", "de vídeo")
T("en disco", "on disk", "em disco")
T("de racha clipeando", "clipping streak", "de sequência clipando")
T("Todavía no hay clips.", "No clips yet.", "Ainda não há clipes.")
T("Cuando guardes clips, aquí verás tus juegos más clipeados.", "When you save clips, your most-clipped games will show here.",
  "Quando você salvar clipes, verá aqui seus jogos mais clipados.")

# ---------- editor, compartir, renombrar ----------
T("Cargando video…", "Loading video…", "Carregando vídeo…")
T("Inicio", "Start", "Início")
T("Fin", "End", "Fim")
T("Inicio aquí", "Start here", "Início aqui")
T("Fin aquí", "End here", "Fim aqui")
T("Tecla I", "Key I", "Tecla I")
T("Tecla O", "Key O", "Tecla O")
T("◀ Marca", "◀ Marker", "◀ Marca")
T("Marca ▶", "Marker ▶", "Marca ▶")
T("Marca anterior ([)", "Previous marker ([)", "Marca anterior ([)")
T("Marca siguiente (])", "Next marker (])", "Próxima marca (])")
T("Formato", "Format", "Formato")
T("Vertical 9:16", "Vertical 9:16", "Vertical 9:16")
T("Pistas de audio", "Audio tracks", "Faixas de áudio")
T("Clic para quitar o volver a poner esta pista", "Click to remove or add back this track", "Clique para remover ou colocar de volta esta faixa")
T("Deja al menos una pista de audio", "Keep at least one audio track", "Deixe pelo menos uma faixa de áudio")
T("Reemplazar el original", "Replace the original", "Substituir o original")
T("Guardar recorte", "Save trim", "Salvar corte")
T("Arrastra los extremos de la barra o usa I y O mientras se reproduce. Espacio: reproducir o pausar. Se guarda como una copia nueva junto al original.",
  "Drag the ends of the bar or use I and O while it plays. Space: play or pause. It's saved as a new copy next to the original.",
  "Arraste as pontas da barra ou use I e O enquanto toca. Espaço: tocar ou pausar. É salvo como uma cópia nova ao lado do original.")
T("Recortando…", "Trimming…", "Cortando…")
T("No se pudo abrir el video en la app. Prueba con Reproducir en la biblioteca.",
  "Couldn't open the video in the app. Try Play in the library.", "Não foi possível abrir o vídeo no app. Tente Reproduzir na biblioteca.")
T("¿Reemplazar el original?", "Replace the original?", "Substituir o original?")
T("El video original se enviará a la Papelera y su lugar lo ocupará el recorte.",
  "The original video will go to the Recycle Bin and the trim will take its place.",
  "O vídeo original irá para a Lixeira e o corte ocupará o lugar dele.")
T("Copiar el clip", "Copy the clip", "Copiar o clipe")
T("Pégalo con Ctrl+V en Discord, WhatsApp o una carpeta.", "Paste it with Ctrl+V in Discord, WhatsApp or a folder.",
  "Cole com Ctrl+V no Discord, WhatsApp ou numa pasta.")
T("Pégala con Ctrl+V en Discord, WhatsApp o una carpeta.", "Paste it with Ctrl+V in Discord, WhatsApp or a folder.",
  "Cole com Ctrl+V no Discord, WhatsApp ou numa pasta.")
T("Versión para Discord", "Discord version", "Versão para o Discord")
T("Una copia de menos de 10 MB, con una sola pista de audio. Se copia sola al terminar.",
  "A copy under 10 MB with a single audio track. It's copied automatically when done.",
  "Uma cópia com menos de 10 MB e uma só faixa de áudio. É copiada sozinha ao terminar.")
T("Preparando la versión para Discord…", "Preparing the Discord version…", "Preparando a versão para o Discord…")
T(" Ya está copiada, pégala en Discord con Ctrl+V.", " It's already copied, paste it in Discord with Ctrl+V.", " Já está copiada, cole no Discord com Ctrl+V.")
T(" (Discord gratis solo acepta hasta 10 MB: usa la versión para Discord).", " (free Discord only accepts up to 10 MB: use the Discord version).",
  " (o Discord grátis só aceita até 10 MB: use a versão para o Discord).")
T("Escribe un nombre", "Type a name", "Digite um nome")
T("¿Enviar a la Papelera?", "Move to Recycle Bin?", "Mover para a Lixeira?")
T("Añadido a favoritos", "Added to favorites", "Adicionado aos favoritos")
T("Quitado de favoritos", "Removed from favorites", "Removido dos favoritos")
T("Añadidos a favoritos", "Added to favorites", "Adicionados aos favoritos")
T("Quitados de favoritos", "Removed from favorites", "Removidos dos favoritos")
T("Uniendo videos… te aviso al terminar", "Joining videos… I'll let you know when it's done", "Juntando vídeos… aviso quando terminar")
T("1 seleccionado", "1 selected", "1 selecionado")
T("Elige al menos dos videos para unir", "Pick at least two videos to join", "Escolha pelo menos dois vídeos para juntar")

# ---------- avisos que manda GrabaClip (Python) ----------
T("Clips desactivados", "Clips off", "Clipes desativados")
T("Clips activos", "Clips on", "Clipes ativos")
T("Clips apagados", "Clips off", "Clipes desligados")
T("Esperando un juego", "Waiting for a game", "Esperando um jogo")
T("Espera un momento, todavía estoy detectando tu GPU", "Hang on, I'm still detecting your GPU", "Espere um momento, ainda estou detectando sua GPU")
T("Clips listos: empezarán a grabar cuando abras un juego", "Clips ready: they'll start recording when you open a game",
  "Clipes prontos: vão começar a gravar quando você abrir um jogo")
T("No hay ningún juego abierto para guardar un clip", "No game is open to save a clip from", "Nenhum jogo aberto para salvar um clipe")
T("Activa los clips primero", "Turn on clips first", "Ative os clipes primeiro")
T("Aún no hay suficiente video, espera unos segundos", "Not enough video yet, wait a few seconds", "Ainda não há vídeo suficiente, espere alguns segundos")
T("No se pudo guardar el clip", "Couldn't save the clip", "Não foi possível salvar o clipe")
T("Clip guardado", "Clip saved", "Clipe salvo")
T("Clip largo", "Long clip", "Clipe longo")
T("Clip del final de la partida", "End-of-match clip", "Clipe do fim da partida")
T("Grabación guardada", "Recording saved", "Gravação salva")
T("Captura guardada", "Screenshot saved", "Captura salva")
T("Escritorio", "Desktop", "Área de trabalho")
T("Se cerró el juego: los clips esperan a que abras otro", "The game closed: clips are waiting for you to open another",
  "O jogo fechou: os clipes esperam você abrir outro")
T("Los clips se detuvieron por un error (revisa la carpeta logs)", "Clips stopped because of an error (check the logs folder)",
  "Os clipes pararam por um erro (veja a pasta logs)")
T("La grabación terminó porque se cerró la ventana del juego", "The recording ended because the game window closed",
  "A gravação terminou porque a janela do jogo fechou")
T("La grabación se detuvo por un error (revisa la carpeta logs)", "The recording stopped because of an error (check the logs folder)",
  "A gravação parou por um erro (veja a pasta logs)")
T("Desactiva los clips y deten la grabación para cambiarlo", "Turn off clips and stop recording to change it",
  "Desative os clipes e pare a gravação para mudar")
T("Termina la grabación antes de cambiar la carpeta.", "Finish recording before changing the folder.", "Termine a gravação antes de mudar a pasta.")
T("Se usará otra vez Videos\\GrabaClip", "Videos\\GrabaClip will be used again", "Videos\\GrabaClip será usada de novo")
T("La actualización ya está en marcha", "The update is already running", "A atualização já está em andamento")
T("Termina la grabación antes de actualizar", "Finish recording before updating", "Termine a gravação antes de atualizar")
T("Primero busca actualizaciones", "Check for updates first", "Procure atualizações primeiro")
T("No pude revisar GitHub. ¿Tienes internet?", "Couldn't check GitHub. Are you online?", "Não consegui verificar o GitHub. Você está conectado?")
T("Empezó una grabación; termínala y vuelve a pulsar Actualizar", "A recording started; finish it and press Update again",
  "Uma gravação começou; termine e clique em Atualizar de novo")
T("Acción desconocida", "Unknown action", "Ação desconhecida")
T("No reconocí esa tecla", "I didn't recognize that key", "Não reconheci essa tecla")
T("Esa tecla no se puede usar, prueba otra", "That key can't be used, try another", "Essa tecla não pode ser usada, tente outra")
T("No encuentro ese video", "I can't find that video", "Não encontro esse vídeo")
T("Ya hay un recorte en marcha", "A trim is already running", "Já há um corte em andamento")
T("Espera a que termine lo que se está preparando", "Wait for the current job to finish", "Espere terminar o que está sendo preparado")
T("Video enviado a la Papelera", "Video moved to the Recycle Bin", "Vídeo movido para a Lixeira")
T("No se pudo eliminar el video", "Couldn't delete the video", "Não foi possível excluir o vídeo")
T("No se pudo eliminar", "Couldn't delete", "Não foi possível excluir")
T("Clip copiado: pégalo con Ctrl+V en Discord, WhatsApp o una carpeta", "Clip copied: paste it with Ctrl+V in Discord, WhatsApp or a folder",
  "Clipe copiado: cole com Ctrl+V no Discord, WhatsApp ou numa pasta")
T("No se pudo copiar al portapapeles", "Couldn't copy to the clipboard", "Não foi possível copiar para a área de transferência")
T("No se puede renombrar la grabación en curso", "The current recording can't be renamed", "A gravação em andamento não pode ser renomeada")
T("Ya hay un video con ese nombre en la misma carpeta", "There's already a video with that name in the same folder",
  "Já existe um vídeo com esse nome na mesma pasta")
T("No se pudo renombrar (¿está abierto en otro programa?)", "Couldn't rename (is it open in another program?)",
  "Não foi possível renomear (está aberto em outro programa?)")
T("El nombre no puede tener < > : \" / \\ | ? * ni ser tan largo", "The name can't contain < > : \" / \\ | ? * or be that long",
  "O nome não pode ter < > : \" / \\ | ? * nem ser tão longo")
T("No se pudo tomar la captura (revisa logs\\captura.log)", "Couldn't take the screenshot (check logs\\captura.log)",
  "Não foi possível tirar a captura (veja logs\\captura.log)")
T("Falta GrabaClip.exe para configurar el inicio con Windows", "GrabaClip.exe is missing to set up starting with Windows",
  "Falta o GrabaClip.exe para configurar o início com o Windows")
T("Tus videos pasan del límite de espacio, pero no queda nada que se pueda mandar a la Papelera",
  "Your videos are over the space limit, but there's nothing left that can go to the Recycle Bin",
  "Seus vídeos passaram do limite de espaço, mas não há nada que possa ir para a Lixeira")
T("Tus videos pasan del límite de espacio, pero no queda nada que se pueda mandar a la Papelera (las grabaciones no se tocan)",
  "Your videos are over the space limit, but there's nothing left that can go to the Recycle Bin (recordings aren't touched)",
  "Seus vídeos passaram do limite de espaço, mas não há nada que possa ir para a Lixeira (as gravações não são tocadas)")
T("El recorte tiene que durar al menos medio segundo", "The trim must be at least half a second long", "O corte precisa durar pelo menos meio segundo")
T("FFmpeg no pudo crear el video (revisa logs\\recorte.log)", "FFmpeg couldn't create the video (check logs\\recorte.log)",
  "O FFmpeg não conseguiu criar o vídeo (veja logs\\recorte.log)")
T("FFmpeg no pudo unir los videos (revisa logs\\unir.log)", "FFmpeg couldn't join the videos (check logs\\unir.log)",
  "O FFmpeg não conseguiu juntar os vídeos (veja logs\\unir.log)")
T("FFmpeg no pudo crear la versión para Discord (revisa logs\\discord.log)", "FFmpeg couldn't create the Discord version (check logs\\discord.log)",
  "O FFmpeg não conseguiu criar a versão para o Discord (veja logs\\discord.log)")
T("No pude leer uno de los videos", "Couldn't read one of the videos", "Não consegui ler um dos vídeos")
T("No pude leer la duración del video", "Couldn't read the video length", "Não consegui ler a duração do vídeo")
T("El archivo descargado está dañado (la huella no coincide). Prueba otra vez.", "The download is damaged (the checksum doesn't match). Try again.",
  "O arquivo baixado está danificado (a verificação não bate). Tente de novo.")
T("La versión publicada no trae el archivo portable", "The published version doesn't include the portable file",
  "A versão publicada não traz o arquivo portátil")
T("GrabaClip sigue funcionando", "GrabaClip is still running", "O GrabaClip continua rodando")
T("Está junto al reloj (en los íconos ocultos). Clic derecho para salir.", "It's next to the clock (in the hidden icons). Right-click to quit.",
  "Está ao lado do relógio (nos ícones ocultos). Clique direito para sair.")
T("Clips · esperando juego", "Clips · waiting for game", "Clipes · esperando jogo")

# ---------- menú del ícono junto al reloj ----------
T("Abrir GrabaClip", "Open GrabaClip", "Abrir o GrabaClip")
T("Activar clips", "Turn on clips", "Ativar clipes")
T("Desactivar clips", "Turn off clips", "Desativar clipes")
T("Salir de GrabaClip", "Exit GrabaClip", "Sair do GrabaClip")

# ---------- Discord ----------
T("Clipeando con GrabaClip", "Clipping with GrabaClip", "Clipando com o GrabaClip")
T("Grabando con GrabaClip", "Recording with GrabaClip", "Gravando com o GrabaClip")
T("Clips instantáneos activos", "Instant clips on", "Clipes instantâneos ativos")
T("Grabando la pantalla", "Recording the screen", "Gravando a tela")
T("Descargar GrabaClip", "Download GrabaClip", "Baixar o GrabaClip")
T("GrabaClip · clips instantáneos gratis y open source", "GrabaClip · free, open-source instant clips",
  "GrabaClip · clipes instantâneos grátis e open source")

# ---------- temas ----------
T("Carmesí", "Crimson", "Carmesim")
T("Oscuro", "Dark", "Escuro")
T("Medianoche", "Midnight", "Meia-noite")
T("Bosque", "Forest", "Floresta")
T("Atardecer", "Sunset", "Pôr do sol")
T("Rojo", "Red", "Vermelho")
T("Claro", "Light", "Claro")
T("Arena", "Sand", "Areia")
T("Rosa", "Pink", "Rosa")
T("Menta", "Mint", "Menta")
T("Alto contraste", "High contrast", "Alto contraste")

# ======================= textos con partes variables =======================
P("Clip guardado en {0}", "Clip saved in {0}", "Clipe salvo em {0}")
P("Clip guardado en {0} (sin {1} pista vacía)", "Clip saved in {0} (without {1} empty track)", "Clipe salvo em {0} (sem {1} faixa vazia)")
P("Clip guardado en {0} (sin {1} pistas vacías)", "Clip saved in {0} (without {1} empty tracks)", "Clipe salvo em {0} (sem {1} faixas vazias)")
P("Clip largo en {0}", "Long clip in {0}", "Clipe longo em {0}")
P("Clip largo en {0} (sin {1} pista vacía)", "Long clip in {0} (without {1} empty track)", "Clipe longo em {0} (sem {1} faixa vazia)")
P("Clip largo en {0} (sin {1} pistas vacías)", "Long clip in {0} (without {1} empty tracks)", "Clipe longo em {0} (sem {1} faixas vazias)")
P("Clip del final de la partida en {0}", "End-of-match clip in {0}", "Clipe do fim da partida em {0}")
P("Clips activos en {0}: {1} guarda los últimos {2} s", "Clips on in {0}: {1} saves the last {2} s", "Clipes ativos em {0}: {1} salva os últimos {2} s")
P("Clips activos en la pantalla: {0} guarda los últimos {1} s", "Clips on for the screen: {0} saves the last {1} s",
  "Clipes ativos na tela: {0} salva os últimos {1} s")
P("Grabando {0}", "Recording {0}", "Gravando {0}")
P("Grabando: {0}", "Recording: {0}", "Gravando: {0}")
P("Grabación guardada: {0}", "Recording saved: {0}", "Gravação salva: {0}")
P("Captura guardada en {0}", "Screenshot saved in {0}", "Captura salva em {0}")
P("Marca {0} en {1}", "Marker {0} at {1}", "Marca {0} em {1}")
P("Marca {0}", "Marker {0}", "Marca {0}")
P("Las marcas son para grabaciones: pulsa {0} para grabar", "Markers are for recordings: press {0} to record",
  "As marcas são para gravações: pressione {0} para gravar")
P("Los nuevos videos se guardarán en {0}", "New videos will be saved in {0}", "Os vídeos novos serão salvos em {0}")
P("No se pudo abrir el selector: {0}", "Couldn't open the folder picker: {0}", "Não foi possível abrir o seletor: {0}")
P("No se puede guardar en esa carpeta ({0}).", "Can't save to that folder ({0}).", "Não é possível salvar nessa pasta ({0}).")
P("Ya tienes la versión más reciente ({0})", "You already have the latest version ({0})", "Você já tem a versão mais recente ({0})")
P("Hay una versión nueva de GrabaClip ({0}). Actualízala en Ajustes → General", "There's a new version of GrabaClip ({0}). Update it in Settings → General",
  "Há uma versão nova do GrabaClip ({0}). Atualize em Configurações → Geral")
P("Hay una versión nueva: {0} (tienes la {1}). Descarga de {2}.", "There's a new version: {0} (you have {1}). {2} download.",
  "Há uma versão nova: {0} (você tem a {1}). Download de {2}.")
P("Tienes la versión {0}.", "You have version {0}.", "Você tem a versão {0}.")
P("Descargando… {0} de {1} ({2}%)", "Downloading… {0} of {1} ({2}%)", "Baixando… {0} de {1} ({2}%)")
P("Descargando… {0} ({1}%)", "Downloading… {0} ({1}%)", "Baixando… {0} ({1}%)")
P("No se pudo actualizar: {0}", "Couldn't update: {0}", "Não foi possível atualizar: {0}")
P("Nueva tecla: {0}", "New hotkey: {0}", "Novo atalho: {0}")
P("{0} ya se usa en otra tecla rápida", "{0} is already used by another hotkey", "{0} já é usado em outro atalho")
P("Así se verá · {0} s", "This is how it'll look · {0} s", "Assim vai ficar · {0} s")
P("Recorte guardado: {0}", "Trim saved: {0}", "Corte salvo: {0}")
P("Recorte guardado: {0} (el original está en la Papelera)", "Trim saved: {0} (the original is in the Recycle Bin)",
  "Corte salvo: {0} (o original está na Lixeira)")
P("Recortando… {0}%", "Trimming… {0}%", "Cortando… {0}%")
P("Clips unidos: {0}", "Clips joined: {0}", "Clipes juntados: {0}")
P("Uniendo… {0}%", "Joining… {0}%", "Juntando… {0}%")
P("Versión para Discord lista ({0} MB)", "Discord version ready ({0} MB)", "Versão para o Discord pronta ({0} MB)")
P("Versión para Discord lista ({0} MB): ya está copiada, pégala con Ctrl+V", "Discord version ready ({0} MB): it's already copied, paste it with Ctrl+V",
  "Versão para o Discord pronta ({0} MB): já está copiada, cole com Ctrl+V")
P("Preparando la versión para Discord… {0}%", "Preparing the Discord version… {0}%", "Preparando a versão para o Discord… {0}%")
P("Lista: {0} MB.", "Ready: {0} MB.", "Pronta: {0} MB.")
P("Lista: {0} MB. Ya está copiada, pégala en Discord con Ctrl+V.", "Ready: {0} MB. It's already copied, paste it in Discord with Ctrl+V.",
  "Pronta: {0} MB. Já está copiada, cole no Discord com Ctrl+V.")
P("Pégalo con Ctrl+V en Discord, WhatsApp o una carpeta. Pesa {0}.", "Paste it with Ctrl+V in Discord, WhatsApp or a folder. Size: {0}.",
  "Cole com Ctrl+V no Discord, WhatsApp ou numa pasta. Tamanho: {0}.")
P("Pégalo con Ctrl+V en Discord, WhatsApp o una carpeta. Pesa {0} (Discord gratis solo acepta hasta 10 MB: usa la versión para Discord).",
  "Paste it with Ctrl+V in Discord, WhatsApp or a folder. Size: {0} (free Discord only accepts up to 10 MB: use the Discord version).",
  "Cole com Ctrl+V no Discord, WhatsApp ou numa pasta. Tamanho: {0} (o Discord grátis só aceita até 10 MB: use a versão para o Discord).")
P("El video dura {0} s: es demasiado largo para que quepa en 10 MB. Recórtalo primero (unos 2 minutos como máximo).",
  "The video is {0} s long: too long to fit in 10 MB. Trim it first (about 2 minutes max).",
  "O vídeo tem {0} s: é longo demais para caber em 10 MB. Corte primeiro (uns 2 minutos no máximo).")
P("Queda poco espacio en el disco ({0} GB). Borra videos o pon un límite en Ajustes → General",
  "Low disk space ({0} GB). Delete videos or set a limit in Settings → General",
  "Pouco espaço em disco ({0} GB). Apague vídeos ou defina um limite em Configurações → Geral")
P("Se enviaron {0} video viejo a la Papelera ({1} GB) para no pasar de {2} GB", "{0} old video moved to the Recycle Bin ({1} GB) to stay under {2} GB",
  "{0} vídeo antigo foi para a Lixeira ({1} GB) para não passar de {2} GB")
P("Se enviaron {0} videos viejos a la Papelera ({1} GB) para no pasar de {2} GB", "{0} old videos moved to the Recycle Bin ({1} GB) to stay under {2} GB",
  "{0} vídeos antigos foram para a Lixeira ({1} GB) para não passar de {2} GB")
P("{0} video enviado a la Papelera", "{0} video moved to the Recycle Bin", "{0} vídeo movido para a Lixeira")
P("{0} videos enviados a la Papelera", "{0} videos moved to the Recycle Bin", "{0} vídeos movidos para a Lixeira")
P("Windows cortó la captura un momento; la grabación sigue en la parte {0}", "Windows interrupted the capture for a moment; recording continues in part {0}",
  "O Windows cortou a captura por um momento; a gravação continua na parte {0}")
P("Renombrado: {0}", "Renamed: {0}", "Renomeado: {0}")
P("{0} seleccionados", "{0} selected", "{0} selecionados")
P("{0} video · {1}", "{0} video · {1}", "{0} vídeo · {1}")
P("{0} videos · {1}", "{0} videos · {1}", "{0} vídeos · {1}")
P("Mostrar más ({0} restantes)", "Show more ({0} left)", "Mostrar mais ({0} restantes)")
P("Todos los juegos ({0})", "All games ({0})", "Todos os jogos ({0})")
P("Sin clasificar ({0})", "Unsorted ({0})", "Sem categoria ({0})")
P("Activas ({0})", "Active ({0})", "Ativos ({0})")
P("Inactivas ({0})", "Inactive ({0})", "Inativos ({0})")
P("{0} · {1} guarda {2} s", "{0} · {1} saves {2} s", "{0} · {1} salva {2} s")
P("Desactivados · {0} para activar", "Off · {0} to turn on", "Desativados · {0} para ativar")
P("Escuchando en {0}", "Listening in {0}", "Ouvindo em {0}")
P("Escuchando en {0} ({1}) con {2} frases", "Listening in {0} ({1}) with {2} phrases", "Ouvindo em {0} ({1}) com {2} frases")
P("No se pudo preparar el reconocimiento de voz: {0}", "Couldn't set up speech recognition: {0}", "Não foi possível preparar o reconhecimento de voz: {0}")
P("“{0}” · {1} % de seguridad · {2}", "“{0}” · {1}% confidence · {2}", "“{0}” · {1}% de certeza · {2}")
P("Escribe una frase y pulsa Enter (ej. \"{0}\")", "Type a phrase and press Enter (e.g. \"{0}\")", "Digite uma frase e pressione Enter (ex. \"{0}\")")
P("{0} clips · {1} grab. · {2}", "{0} clips · {1} rec. · {2}", "{0} clipes · {1} grav. · {2}")
P("Tu mejor semana: la del {0}, con {1} clips.", "Your best week: the week of {0}, with {1} clips.", "Sua melhor semana: a de {0}, com {1} clipes.")
P("Semana del {0}: {1} clips", "Week of {0}: {1} clips", "Semana de {0}: {1} clipes")
P("{0} día", "{0} day", "{0} dia")
P("{0} días", "{0} days", "{0} dias")
P("{0} h {1} min", "{0} h {1} min", "{0} h {1} min")
P("{0} videos ({1} clips: {2})", "{0} videos ({1} clips: {2})", "{0} vídeos ({1} clipes: {2})")
P("{0} videos ({1} clips: {2}) · {3} % de tu límite", "{0} videos ({1} clips: {2}) · {3}% of your limit", "{0} vídeos ({1} clipes: {2}) · {3}% do seu limite")
P("{0} videos ({1} clips: {2}) · Libre en el disco: {3}", "{0} videos ({1} clips: {2}) · Free on disk: {3}", "{0} vídeos ({1} clipes: {2}) · Livre no disco: {3}")
P("{0} videos ({1} clips: {2}) · {3} % de tu límite · Libre en el disco: {4}", "{0} videos ({1} clips: {2}) · {3}% of your limit · Free on disk: {4}",
  "{0} vídeos ({1} clipes: {2}) · {3}% do seu limite · Livre no disco: {4}")
P("Al pasar de {0} GB, los clips más viejos se mandan solos a la Papelera (puedes recuperarlos de ahí). Ojo: la Papelera también ocupa espacio hasta que la vacías.",
  "Above {0} GB, the oldest clips go to the Recycle Bin automatically (you can restore them from there). Note: the Recycle Bin also uses space until you empty it.",
  "Acima de {0} GB, os clipes mais antigos vão sozinhos para a Lixeira (dá para recuperar de lá). Atenção: a Lixeira também ocupa espaço até você esvaziá-la.")
P("Al pasar de {0} GB, los videos más viejos se mandan solos a la Papelera (puedes recuperarlos de ahí). Ojo: la Papelera también ocupa espacio hasta que la vacías.",
  "Above {0} GB, the oldest videos go to the Recycle Bin automatically (you can restore them from there). Note: the Recycle Bin also uses space until you empty it.",
  "Acima de {0} GB, os vídeos mais antigos vão sozinhos para a Lixeira (dá para recuperar de lá). Atenção: a Lixeira também ocupa espaço até você esvaziá-la.")
P("¿Poner el límite en {0} GB?", "Set the limit to {0} GB?", "Definir o limite em {0} GB?")
P("Ahora tus videos ocupan {0}. Los clips más viejos se mandarán a la Papelera hasta bajar de {1} GB.",
  "Your videos now take up {0}. The oldest clips will go to the Recycle Bin until under {1} GB.",
  "Seus vídeos ocupam {0} agora. Os clipes mais antigos irão para a Lixeira até ficar abaixo de {1} GB.")
P("Ahora tus videos ocupan {0}. Los videos más viejos se mandarán a la Papelera hasta bajar de {1} GB.",
  "Your videos now take up {0}. The oldest videos will go to the Recycle Bin until under {1} GB.",
  "Seus vídeos ocupam {0} agora. Os vídeos mais antigos irão para a Lixeira até ficar abaixo de {1} GB.")
P("¿Enviar {0} video a la Papelera?", "Move {0} video to the Recycle Bin?", "Mover {0} vídeo para a Lixeira?")
P("¿Enviar {0} videos a la Papelera?", "Move {0} videos to the Recycle Bin?", "Mover {0} vídeos para a Lixeira?")
P("{0} en total. Puedes recuperarlos desde la Papelera.", "{0} in total. You can restore them from the Recycle Bin.", "{0} no total. Dá para recuperá-los da Lixeira.")
P("{0} en total, incluye {1} favorito. Puedes recuperarlos desde la Papelera.", "{0} in total, includes {1} favorite. You can restore them from the Recycle Bin.",
  "{0} no total, inclui {1} favorito. Dá para recuperá-los da Lixeira.")
P("{0} en total, incluye {1} favoritos. Puedes recuperarlos desde la Papelera.", "{0} in total, includes {1} favorites. You can restore them from the Recycle Bin.",
  "{0} no total, inclui {1} favoritos. Dá para recuperá-los da Lixeira.")
P("{0} (es un favorito)", "{0} (it's a favorite)", "{0} (é um favorito)")
P("¿Unir {0} videos?", "Join {0} videos?", "Juntar {0} vídeos?")
P("Se crea un video nuevo de unos {0} con un fundido corto entre cada uno y una sola pista de audio (la mezcla). Los originales no se tocan.",
  "A new video of about {0} is created, with a short fade between each one and a single audio track (the mix). The originals aren't touched.",
  "Um vídeo novo de uns {0} é criado, com um fade curto entre cada um e uma só faixa de áudio (o mix). Os originais não são tocados.")
P("En {0}", "In {0}", "Em {0}")
P("{0} (clic para renombrar)", "{0} (click to rename)", "{0} (clique para renomear)")
P("{0} pista de audio", "{0} audio track", "{0} faixa de áudio")
P("{0} pistas de audio", "{0} audio tracks", "{0} faixas de áudio")
P("{0} pista de audio · {1} marca", "{0} audio track · {1} marker", "{0} faixa de áudio · {1} marca")
P("{0} pistas de audio · {1} marcas", "{0} audio tracks · {1} markers", "{0} faixas de áudio · {1} marcas")
P("FFmpeg no pudo arrancar (codigo 0x{0}).", "FFmpeg couldn't start (code 0x{0}).", "O FFmpeg não conseguiu iniciar (código 0x{0}).")
P("FFmpeg termino con el codigo 0x{0} sin dar detalles.", "FFmpeg ended with code 0x{0} without details.", "O FFmpeg terminou com o código 0x{0} sem detalhes.")
P("No se pudo ejecutar FFmpeg: {0}", "Couldn't run FFmpeg: {0}", "Não foi possível executar o FFmpeg: {0}")
P("Pantalla {0}", "Screen {0}", "Tela {0}")
P("No tienes el reconocimiento de voz en {0}. Para agregarlo: Configuración de Windows > Hora e idioma > Idioma y región > Agregar un idioma, y marca \"Reconocimiento de voz\". Mientras tanto se usa {1}.",
  "You don't have {0} speech recognition. To add it: Windows Settings > Time & language > Language & region > Add a language, and check \"Speech recognition\". Meanwhile {1} is used.",
  "Você não tem o reconhecimento de voz em {0}. Para adicionar: Configurações do Windows > Hora e idioma > Idioma e região > Adicionar um idioma, e marque \"Reconhecimento de fala\". Enquanto isso é usado {1}.")
T("español", "Spanish", "espanhol")
T("inglés", "English", "inglês")
T("portugués", "Portuguese", "português")
T("francés", "French", "francês")
T("árabe", "Arabic", "árabe")
T("ruso", "Russian", "russo")

# ---------- perfiles ----------
T("Perfil", "Profile", "Perfil")
T("Elige qué partes de GrabaClip quieres usar. Lo que apagues no se carga ni escucha teclas, así gasta menos.", "Choose which parts of GrabaClip you want to use. Whatever you turn off isn't loaded and doesn't listen for keys, so it uses less.", "Escolha quais partes do GrabaClip você quer usar. O que você desligar não é carregado nem escuta teclas, então gasta menos.")
T("Completo", "Full", "Completo")
T("Todo incluido: clips, grabación, capturas, voz, overlay, Discord y estadísticas.", "Everything included: clips, recording, screenshots, voice, overlay, Discord and statistics.", "Tudo incluído: clipes, gravação, capturas, voz, overlay, Discord e estatísticas.")
T("Esencial", "Essential", "Essencial")
T("Clips, grabación y capturas. Sin voz, overlay, Discord ni estadísticas.", "Clips, recording and screenshots. No voice, overlay, Discord or statistics.", "Clipes, gravação e capturas. Sem voz, overlay, Discord nem estatísticas.")
T("Solo clips", "Clips only", "Só clipes")
T("Solo los clips instantáneos y su aviso en el juego. Lo más ligero.", "Just instant clips and their in-game notice. The lightest option.", "Só os clipes instantâneos e o aviso no jogo. O mais leve.")
T("Solo grabación", "Recording only", "Só gravação")
T("Grabaciones largas con marcas, sin el búfer de clips.", "Long recordings with markers, without the clip buffer.", "Gravações longas com marcas, sem o buffer de clipes.")
T("Personalizar…", "Customize…", "Personalizar…")
T("Personalizado", "Custom", "Personalizado")
T("¿Cómo vas a usar GrabaClip?", "How will you use GrabaClip?", "Como você vai usar o GrabaClip?")
T("Puedes cambiarlo cuando quieras en Ajustes → General → Perfil.", "You can change it anytime in Settings → General → Profile.", "Você pode mudar quando quiser em Configurações → Geral → Perfil.")
T("El búfer que guarda los últimos segundos (F8, F9).", "The buffer that keeps the last few seconds (F8, F9).", "O buffer que guarda os últimos segundos (F8, F9).")
T("Grabación", "Recording", "Gravação")
T("Grabaciones largas con REC o F10, y marcas.", "Long recordings with REC or F10, and markers.", "Gravações longas com REC ou F10, e marcas.")
T("Capturas de pantalla", "Screenshots", "Capturas de tela")
T("Imágenes del juego con F7.", "Pictures of the game with F7.", "Imagens do jogo com F7.")
T("\"Jarvis, sácale clip\".", "\"Jarvis, clip that\".", "\"Jarvis, clipa isso\".")
T("Avisos encima del juego.", "Notices on top of the game.", "Avisos sobre o jogo.")
T("Estado en Discord", "Discord status", "Status no Discord")
T("\"Clipeando con GrabaClip\" en tu perfil.", "\"Clipping with GrabaClip\" on your profile.", "\"Clipando com o GrabaClip\" no seu perfil.")
T("La pestaña de estadísticas.", "The statistics tab.", "A aba de estatísticas.")
T("Los clips están apagados en tu perfil (Ajustes → General → Perfil)", "Clips are off in your profile (Settings → General → Profile)", "Os clipes estão desligados no seu perfil (Configurações → Geral → Perfil)")
T("La grabación está apagada en tu perfil (Ajustes → General → Perfil)", "Recording is off in your profile (Settings → General → Profile)", "A gravação está desligada no seu perfil (Configurações → Geral → Perfil)")
T("Termina la grabación antes de cambiar de perfil", "Finish recording before changing profile", "Termine a gravação antes de mudar de perfil")
T("Perfil desconocido", "Unknown profile", "Perfil desconhecido")
P("Perfil: {0}", "Profile: {0}", "Perfil: {0}")
# ---------- temas propios y tutorial ----------
T("Esquinas", "Corners", "Cantos")
T("Rectas", "Square", "Retos")
T("Normales", "Normal", "Normais")
T("Redondas", "Rounded", "Redondos")
T("Tamaño del texto", "Text size", "Tamanho do texto")
T("Pequeño", "Small", "Pequeno")
T("Normal", "Normal", "Normal")
T("Grande", "Large", "Grande")
T("Temas", "Themes", "Temas")
T("Crear tema", "Create theme", "Criar tema")
T("Editar tema", "Edit theme", "Editar tema")
T("Nombre de tu tema", "Your theme's name", "Nome do seu tema")
T("Empieza desde el tema que tengas puesto. Los cambios se ven al instante.", "It starts from your current theme. Changes show instantly.", "Começa a partir do tema atual. As mudanças aparecem na hora.")
T("Guardar tema", "Save theme", "Salvar tema")
T("Acento", "Accent", "Destaque")
T("Fondo", "Background", "Fundo")
T("Paneles", "Panels", "Painéis")
T("Campos", "Fields", "Campos")
T("Texto", "Text", "Texto")
T("Texto secundario", "Secondary text", "Texto secundário")
T("Bordes", "Borders", "Bordas")
T("Editar", "Edit", "Editar")
T("¿Eliminar este tema?", "Delete this theme?", "Excluir este tema?")
T("Tema guardado", "Theme saved", "Tema salvo")
T("Ponle un nombre a tu tema", "Give your theme a name", "Dê um nome ao seu tema")
T("Ese nombre ya lo usa un tema de fábrica", "A built-in theme already uses that name", "Um tema de fábrica já usa esse nome")
T("Algún color no es válido", "One of the colors isn't valid", "Alguma cor não é válida")
T("Ese tema no se puede borrar", "That theme can't be deleted", "Esse tema não pode ser excluído")
T("Saltar", "Skip", "Pular")
T("Siguiente", "Next", "Próximo")
T("Empezar", "Start", "Começar")
T("Terminar", "Finish", "Concluir")
T("Ver el tutorial otra vez", "Watch the tutorial again", "Ver o tutorial de novo")
T("¡Bienvenido a GrabaClip!", "Welcome to GrabaClip!", "Bem-vindo ao GrabaClip!")
T("Te muestro lo básico en menos de un minuto.", "Let me show you the basics in under a minute.", "Vou te mostrar o básico em menos de um minuto.")
T("Guarda la jugada", "Save the play", "Salve a jogada")
T("Graba partidas completas", "Record full matches", "Grave partidas inteiras")
T("Tu biblioteca", "Your library", "Sua biblioteca")
T("Aquí aparecen tus clips. Puedes verlos, recortarlos, compartirlos o marcarlos como favoritos.", "Your clips show up here. You can watch, trim, share or favorite them.", "Seus clipes aparecem aqui. Você pode ver, cortar, compartilhar ou favoritar.")
T("Hazlo a tu manera", "Make it yours", "Do seu jeito")
T("En Ajustes cambias las teclas, la calidad, el audio, tu perfil y los colores.", "In Settings you change hotkeys, quality, audio, your profile and colors.", "Em Configurações você muda atalhos, qualidade, áudio, seu perfil e as cores.")
T("¡Listo!", "All set!", "Pronto!")
T("Ya puedes empezar a clipear. Si quieres ver esto otra vez, está en Ayuda.", "You're ready to start clipping. To see this again, it's in Help.", "Você já pode começar a clipar. Para ver isso de novo, está em Ajuda.")
P("Con esto GrabaClip guarda en segundo plano los últimos segundos de tu partida. También puedes usar {0} desde el juego.", "This makes GrabaClip keep the last few seconds of your match in the background. You can also use {0} from the game.", "Com isso o GrabaClip guarda em segundo plano os últimos segundos da partida. Você também pode usar {0} no jogo.")
P("Cuando pase algo bueno, pulsa {0}. El clip se guarda sin pausar el juego.", "When something good happens, press {0}. The clip is saved without pausing the game.", "Quando acontecer algo bom, pressione {0}. O clipe é salvo sem pausar o jogo.")
P("REC o {0} empieza y termina una grabación larga. Con {1} marcas los mejores momentos.", "REC or {0} starts and ends a long recording. With {1} you mark the best moments.", "REC ou {0} começa e termina uma gravação longa. Com {1} você marca os melhores momentos.")
# ---------- accesos directos ----------
T("Acceso directo en el escritorio", "Desktop shortcut", "Atalho na área de trabalho")
T("Abre GrabaClip con doble clic, sin entrar a su carpeta.", "Open GrabaClip with a double-click, without going into its folder.", "Abra o GrabaClip com dois cliques, sem entrar na pasta.")
T("En el menú Inicio", "In the Start menu", "No menu Iniciar")
T("Para encontrarlo escribiendo \"GrabaClip\" en Inicio. Desde ahí también puedes anclarlo a la barra de tareas.", "So you can find it by typing \"GrabaClip\" in Start. From there you can also pin it to the taskbar.", "Para encontrá-lo digitando \"GrabaClip\" no Iniciar. Dali você também pode fixá-lo na barra de tarefas.")
T("Crear", "Create", "Criar")
T("Quitar", "Remove", "Remover")
T("Crear acceso directo", "Create shortcut", "Criar atalho")
T("Acceso directo creado en el escritorio", "Desktop shortcut created", "Atalho criado na área de trabalho")
T("GrabaClip ya aparece en el menú Inicio", "GrabaClip now shows up in the Start menu", "O GrabaClip já aparece no menu Iniciar")
T("Acceso directo quitado", "Shortcut removed", "Atalho removido")
T("No se pudo crear el acceso directo", "Couldn't create the shortcut", "Não foi possível criar o atalho")
T("No se pudo quitar el acceso directo", "Couldn't remove the shortcut", "Não foi possível remover o atalho")
T("No encontré esa carpeta de Windows", "I couldn't find that Windows folder", "Não encontrei essa pasta do Windows")
T("Falta GrabaClip.exe en la carpeta de la app", "GrabaClip.exe is missing from the app folder", "Falta o GrabaClip.exe na pasta do app")
# ---------- avisos de cada acción ----------
T("Avisos de cada acción", "Notifications for each action", "Avisos de cada ação")
T("Elige qué hace cada una: mostrar el overlay, tocar su sonido, las dos cosas o nada.", "Choose what each one does: show the overlay, play its sound, both, or nothing.", "Escolha o que cada uma faz: mostrar o overlay, tocar o som, as duas coisas ou nada.")
T("También los clips largos y el del final de la partida", "Also long clips and the end-of-match clip", "Também os clipes longos e o do fim da partida")
T("Terminar una grabación", "Finish a recording", "Terminar uma gravação")
T("Al detenerla y guardarla", "When you stop and save it", "Ao parar e salvar")
T("Al tomarla", "When you take it", "Ao tirar")
T("Mientras grabas", "While recording", "Enquanto grava")
T("Activar o desactivar los clips", "Turn clips on or off", "Ativar ou desativar os clipes")
T("Con la tecla o con la voz", "With the key or by voice", "Com a tecla ou com a voz")
T("Overlay", "Overlay", "Overlay")
T("Sonido", "Sound", "Som")
T("El overlay está apagado arriba", "The overlay is turned off above", "O overlay está desligado acima")
T("Los sonidos de aviso están apagados", "Notification sounds are turned off", "Os sons de aviso estão desligados")
T("Interruptor general. Abajo, en \"Avisos de cada acción\", eliges cuáles suenan.", "Master switch. Below, in \"Notifications for each action\", you choose which ones play.", "Interruptor geral. Abaixo, em \"Avisos de cada ação\", você escolhe quais tocam.")
T("Clips activados", "Clips on", "Clipes ativados")
T("captura directa", "direct capture", "captura direta")
T("cerrado ahora", "closed now", "fechado agora")
T("Usando:", "Using:", "Usando:")
T("Formato del video", "Video format", "Formato do vídeo")
T("H.264 · compatible con todo", "H.264 · works everywhere", "H.264 · compatível com tudo")
T("AV1 · más ligero", "AV1 · smaller files", "AV1 · mais leve")
T("Archivos ~35 % más ligeros con la misma calidad. Discord, YouTube, Chrome y DaVinci Resolve lo abren; algunos programas viejos no. \"Versión para Discord\" siempre lo convierte a H.264.", "Files ~35% smaller at the same quality. Discord, YouTube, Chrome and DaVinci Resolve open it; some old programs don't. \"Discord version\" always converts it to H.264.", "Arquivos ~35% mais leves com a mesma qualidade. Discord, YouTube, Chrome e DaVinci Resolve abrem; alguns programas antigos não. \"Versão para Discord\" sempre converte para H.264.")
T("El formato de siempre: se abre en cualquier programa y celular.", "The usual format: opens in any program and phone.", "O formato de sempre: abre em qualquer programa e celular.")
T("Detectando si tu tarjeta puede usar AV1…", "Checking whether your card can use AV1…", "Verificando se sua placa pode usar AV1…")
T("Ahora usa", "Now using", "Usando agora")
T("Con AV1 este FFmpeg no permite el búfer en RAM: se usa el disco.", "With AV1 this FFmpeg can't keep the buffer in RAM: the disk is used.", "Com AV1 este FFmpeg não permite o buffer na RAM: usa-se o disco.")
T("Guardar el búfer en la memoria RAM", "Keep the buffer in RAM", "Guardar o buffer na memória RAM")
T("Los últimos segundos se guardan en la memoria en vez de escribirse al disco todo el tiempo: menos desgaste del SSD. Usa más RAM (unos 150 a 800 MB según la calidad y la duración del clip largo).", "The last seconds are kept in memory instead of being written to disk all the time: less SSD wear. Uses more RAM (about 150 to 800 MB depending on quality and the long clip length).", "Os últimos segundos ficam na memória em vez de serem gravados no disco o tempo todo: menos desgaste do SSD. Usa mais RAM (uns 150 a 800 MB conforme a qualidade e a duração do clipe longo).")
T("Silenciar el micrófono", "Mute the microphone", "Silenciar o microfone")
T("Apaga o vuelve a encender tu micrófono en los clips y grabaciones, sin cortar nada.", "Turns your microphone off or back on in clips and recordings, without cutting anything.", "Desliga ou religa seu microfone nos clipes e gravações, sem cortar nada.")
T("Micrófono apagado: clic para encenderlo", "Microphone off: click to turn it on", "Microfone desligado: clique para ligar")
T("Con su tecla o el botón de abajo", "With its key or the button below", "Com a tecla ou o botão abaixo")
T("AV1 no está disponible", "AV1 isn't available", "AV1 não está disponível")
T("Micrófono apagado", "Mic off", "Microfone desligado")
T("Micrófono encendido", "Mic on", "Microfone ligado")
T("El micrófono no se está grabando (Ajustes → Audio)", "The microphone isn't being recorded (Settings → Audio)", "O microfone não está sendo gravado (Ajustes → Áudio)")
T("Micrófono apagado: no se graba tu voz", "Microphone off: your voice isn't recorded", "Microfone desligado: sua voz não é gravada")
T("AV1 por ahora solo funciona con tarjetas NVIDIA RTX 40 o más nuevas.", "For now AV1 only works with NVIDIA RTX 40 cards or newer.", "Por enquanto AV1 só funciona com placas NVIDIA RTX 40 ou mais novas.")
T("Tu tarjeta no puede comprimir en AV1 (hace falta una NVIDIA RTX 40 o más nueva).", "Your card can't encode AV1 (it needs an NVIDIA RTX 40 or newer).", "Sua placa não consegue comprimir em AV1 (precisa de uma NVIDIA RTX 40 ou mais nova).")
T("Tu FFmpeg no puede guardar AV1 en el búfer.", "Your FFmpeg can't store AV1 in the buffer.", "Seu FFmpeg não consegue guardar AV1 no buffer.")
T("Velocidad", "Speed", "Velocidade")
T("Lenta 0.5x", "Slow 0.5x", "Lenta 0.5x")
T("Muy lenta 0.25x", "Very slow 0.25x", "Muito lenta 0.25x")
T("Marca de agua", "Watermark", "Marca d'água")
T("@tu_nombre (vacío = sin marca)", "@your_name (empty = no watermark)", "@seu_nome (vazio = sem marca)")
T("clic para usarla", "click to use it", "clique para usar")
T("Exportar GIF", "Export GIF", "Exportar GIF")
T("GIF del tramo elegido (hasta 20 s), queda copiado para pegarlo en Discord", "GIF of the selected part (up to 20 s), copied so you can paste it in Discord", "GIF do trecho escolhido (até 20 s), fica copiado para colar no Discord")
T("Para un GIF elige 20 segundos o menos (pesan mucho)", "For a GIF pick 20 seconds or less (they're heavy)", "Para um GIF escolha 20 segundos ou menos (pesam muito)")
T("Creando el GIF…", "Creating the GIF…", "Criando o GIF…")
T("Crear resumen de la semana", "Make this week's recap", "Criar resumo da semana")
T("Un video con tus favoritos de los últimos 7 días (o tus clips más nuevos), 8 segundos de cada uno", "A video with your favorites from the last 7 days (or your newest clips), 8 seconds of each", "Um vídeo com seus favoritos dos últimos 7 dias (ou seus clipes mais novos), 8 segundos de cada")
T("Mi semana en GrabaClip", "My week in GrabaClip", "Minha semana no GrabaClip")
T("Necesitas al menos 2 clips de esta semana para el resumen", "You need at least 2 clips from this week for the recap", "Você precisa de pelo menos 2 clipes desta semana para o resumo")
T("El GIF tiene que durar al menos medio segundo", "The GIF must be at least half a second long", "O GIF precisa durar pelo menos meio segundo")
T("No encontré una fuente de Windows para escribir el texto", "I couldn't find a Windows font to write the text", "Não encontrei uma fonte do Windows para escrever o texto")
P("GIF listo ({0} MB): ya está copiado, pégalo con Ctrl+V", "GIF ready ({0} MB): it's copied, paste it with Ctrl+V", "GIF pronto ({0} MB): já está copiado, cole com Ctrl+V")
P("GIF listo ({0} MB)", "GIF ready ({0} MB)", "GIF pronto ({0} MB)")
P("Resumen listo: {0} clips en {1}", "Recap ready: {0} clips in {1}", "Resumo pronto: {0} clipes em {1}")
P("Armando tu resumen con {0} favoritos…", "Building your recap with {0} favorites…", "Montando seu resumo com {0} favoritos…")
P("Armando tu resumen con tus {0} clips más nuevos (marca favoritos para elegir tú)…", "Building your recap with your {0} newest clips (mark favorites to choose yourself)…", "Montando seu resumo com seus {0} clipes mais novos (marque favoritos para escolher)…")

def _por_especificidad(patrones):
    # los patrones con más texto fijo van primero ("Grabando: {0}" antes que "Grabando {0}")
    return sorted(patrones, key=lambda p: -len(re.sub(r"\{\d+\}", "", p[0])))


def _cargar_archivos():
    carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")
    for codigo in IDIOMAS:
        ruta = os.path.join(carpeta, codigo + ".json")
        if codigo in ("es", "en", "pt") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
            _EXACTO[codigo] = dict(datos.get("exacto", {}))
            _PATRONES[codigo] = [tuple(p) for p in datos.get("patrones", [])]
        except Exception:
            pass


_cargar_archivos()

# frases de voz por defecto en cada idioma (se cambian solas si el usuario no las tocó)
FRASES_VOZ = {"es": ["jarvis sácale clip", "jarvis clipea eso"],
              "en": ["jarvis clip that", "jarvis save the clip"],
              "pt": ["jarvis clipa isso", "jarvis salva o clipe"],
              "fr": ["jarvis clippe ça", "jarvis sauvegarde le clip"]}
# Windows no trae reconocimiento de voz en árabe ni en ruso: ahí se usan las frases en inglés
FRASES_VOZ["ar"] = FRASES_VOZ["ru"] = FRASES_VOZ["en"]


def ajustar_frases(cfg):
    """Si las frases para guardar clip son las de fábrica de otro idioma, usa las del idioma actual."""
    actuales = [f.lower() for f in cfg.get("voz_clip") or []]
    for lista in FRASES_VOZ.values():
        if actuales == lista and lista != FRASES_VOZ.get(ACTUAL, lista):
            cfg["voz_clip"] = list(FRASES_VOZ.get(ACTUAL, lista))
            return True
    return False


def catalogo(idioma):
    """Lo que necesita la interfaz para traducir: textos exactos y patrones (con {0}, {1}...)."""
    return {"exacto": _EXACTO.get(idioma, {}), "patrones": _por_especificidad(_PATRONES.get(idioma, []))}


_COMPILADOS = {}


def _regex(origen):
    partes = re.split(r"(\{\d+\})", origen)
    rx = "".join("(.+?)" if re.fullmatch(r"\{\d+\}", p) else re.escape(p) for p in partes)
    orden = [int(p[1:-1]) for p in partes if re.fullmatch(r"\{\d+\}", p)]
    return re.compile("^" + rx + "$", re.S), orden


def t(texto, idioma=None):
    """Traduce un texto en español al idioma actual (si no hay traducción, lo deja igual)."""
    idioma = idioma or ACTUAL
    if idioma == "es" or not texto:
        return texto
    exacto = _EXACTO.get(idioma, {})
    if texto in exacto:
        return exacto[texto]
    if idioma not in _COMPILADOS:
        _COMPILADOS[idioma] = [(_regex(o), d) for o, d in _por_especificidad(_PATRONES.get(idioma, []))]
    for (rx, orden), destino in _COMPILADOS[idioma]:
        m = rx.match(texto)
        if m:
            valores = {n: exacto.get(m.group(i + 1), m.group(i + 1)) for i, n in enumerate(orden)}
            return re.sub(r"\{(\d+)\}", lambda x: valores.get(int(x.group(1)), x.group(0)), destino)
    return texto


def idioma_de_windows():
    """'es', 'en' o 'pt' según el idioma de la interfaz de Windows (inglés si es otro)."""
    try:
        import ctypes
        primario = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x0A: "es", 0x09: "en", 0x16: "pt", 0x0C: "fr", 0x01: "ar", 0x19: "ru"}.get(primario, "en")
    except Exception:
        return "es"


def t_overlay(texto):
    """El overlay (Tk) no dibuja bien el árabe (sin unir letras ni derecha a izquierda): ahí va en inglés."""
    return t(texto, "en" if ACTUAL in RTL else None)


def elegir(preferido):
    global ACTUAL
    ACTUAL = preferido if preferido in IDIOMAS else idioma_de_windows()
    return ACTUAL
