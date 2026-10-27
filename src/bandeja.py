"""Ícono de GrabaClip junto al reloj (bandeja del sistema / íconos ocultos).

Usa System.Windows.Forms.NotifyIcon de .NET, que ya está cargado por pywebview, así que no
agrega dependencias. Todo lo de WinForms se hace en el hilo de la ventana (form.Invoke) y las
acciones del menú corren en hilos aparte para no congelar la interfaz.
"""
import ctypes
import threading

from idiomas import t

EVENTO_MOSTRAR = "Local\\GrabaClip_mostrar"  # el lanzador lo activa si GrabaClip ya estaba abierto


class Bandeja:
    def __init__(self, form, icono, acciones, estado):
        """acciones: dict con funciones 'abrir', 'clip', 'clips', 'grabar', 'salir'.
        estado(): dict {'clips': bool, 'grabando': bool}."""
        self._form = form
        self._icono = icono
        self._acc = acciones
        self._estado = estado
        self._ni = None
        self._items = {}

    def _en_ui(self, fn, esperar=True):
        from System import Action
        if not self._form.InvokeRequired:
            fn()
        elif esperar:
            self._form.Invoke(Action(fn))
        else:
            self._form.BeginInvoke(Action(fn))  # sin esperar: nunca traba a quien llama

    def crear(self):
        def hacer():
            import System.Windows.Forms as WF
            import System.Drawing as SD
            ni = WF.NotifyIcon()
            try:
                ni.Icon = SD.Icon(self._icono)
            except Exception:
                ni.Icon = self._form.Icon
            ni.Text = "GrabaClip"
            menu = WF.ContextMenuStrip()

            def item(clave, texto, negrita=False):
                it = WF.ToolStripMenuItem(texto)
                if negrita:
                    it.Font = SD.Font(it.Font, SD.FontStyle.Bold)
                it.Click += lambda s, e, c=clave: threading.Thread(target=self._acc[c], daemon=True).start()
                menu.Items.Add(it)
                self._items[clave] = it

            item("abrir", "Abrir GrabaClip", True)
            menu.Items.Add(WF.ToolStripSeparator())
            item("clip", "Guardar clip")
            item("clips", "Activar clips")
            item("grabar", "Empezar a grabar")
            menu.Items.Add(WF.ToolStripSeparator())
            item("salir", "Salir de GrabaClip")

            def al_abrir_menu(s, e):
                est = self._estado()
                self._items["abrir"].Text = t("Abrir GrabaClip")
                self._items["salir"].Text = t("Salir de GrabaClip")
                self._items["clips"].Text = t("Desactivar clips" if est.get("clips") else "Activar clips")
                self._items["grabar"].Text = t("Detener grabación" if est.get("grabando") else "Empezar a grabar")
                self._items["clip"].Text = t("Guardar clip")
                self._items["clip"].Enabled = bool(est.get("clips"))
            menu.Opening += al_abrir_menu

            def al_clic(s, e):
                if e.Button == WF.MouseButtons.Left:
                    threading.Thread(target=self._acc["abrir"], daemon=True).start()
            ni.MouseClick += al_clic
            ni.MouseDoubleClick += al_clic  # GrabaClip ignora la llamada repetida
            ni.ContextMenuStrip = menu
            ni.Visible = True
            self._ni = ni
            try:  # al apagar o cerrar sesión, dejar que la ventana se cierre de verdad
                from Microsoft.Win32 import SystemEvents
                SystemEvents.SessionEnding += lambda s, e: self._acc.get("apagando", lambda: None)()
            except Exception:
                pass
        self._en_ui(hacer)
        threading.Thread(target=self._esperar_lanzador, daemon=True).start()

    def texto(self, t):
        if not self._ni:
            return
        t = t[:63]

        def hacer():
            self._ni.Text = t
        try:
            self._en_ui(hacer, esperar=False)
        except Exception:
            pass

    def globo(self, titulo, texto):
        if not self._ni:
            return

        def hacer():
            import System.Windows.Forms as WF
            self._ni.ShowBalloonTip(4000, titulo, texto, WF.ToolTipIcon.Info)
        try:
            self._en_ui(hacer, esperar=False)
        except Exception:
            pass

    def quitar(self):
        if not self._ni:
            return

        def hacer():
            self._ni.Visible = False
            self._ni.Dispose()
        try:
            self._en_ui(hacer)
        except Exception:
            pass
        self._ni = None

    def _esperar_lanzador(self):
        """Si abren GrabaClip.exe otra vez mientras está en la bandeja, se muestra la ventana."""
        try:
            k = ctypes.windll.kernel32
            k.CreateEventW.restype = ctypes.c_void_p
            h = k.CreateEventW(None, False, False, EVENTO_MOSTRAR)
            if not h:
                return
            while self._ni is not None:
                if k.WaitForSingleObject(ctypes.c_void_p(h), 1000) == 0:
                    self._acc["abrir"]()
        except Exception:
            pass
