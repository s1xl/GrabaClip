"""
Comandos de voz de GrabaClip ("Jarvis, sacale clip").

Usa el reconocimiento de voz de Windows (System.Speech, a traves de pythonnet), que
funciona sin internet: el audio del microfono se procesa en la PC y no se envia a
ningun lado. Solo se reconocen las frases que el usuario configuro (una gramatica
cerrada), lo que lo hace preciso y muy ligero.
"""
import re
import time
import threading
import unicodedata

ACCIONES = ("clip", "grabar", "clips")


def normalizar(frase):
    """Minusculas, sin signos de puntuacion ni espacios de mas (los acentos se conservan)."""
    frase = unicodedata.normalize("NFC", (frase or "").lower())
    frase = re.sub(r"[^\w\sáéíóúüñ]", " ", frase)
    return re.sub(r"\s+", " ", frase).strip()


def _sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


class Voz:
    """Escucha el microfono y llama a al_reconocer(accion, frase, confianza)."""

    def __init__(self, al_reconocer, al_cambiar_estado):
        self._al_reconocer = al_reconocer
        self._al_cambiar = al_cambiar_estado
        self._motor = None
        self._acciones_por_frase = {}
        self._confianza = 0.6
        self._ultimo_disparo = 0
        self._lock = threading.Lock()
        self.estado = {"activo": False, "idioma": None, "error": None, "ultimo": None}

    # ---------- idiomas instalados ----------
    @staticmethod
    def idiomas():
        try:
            import clr  # noqa: F401  (lo carga pywebview)
            clr.AddReference("System.Speech")
            from System.Speech.Recognition import SpeechRecognitionEngine
            return [{"id": r.Culture.Name, "nombre": r.Culture.NativeName.capitalize()}
                    for r in SpeechRecognitionEngine.InstalledRecognizers()]
        except Exception:
            return []

    # ---------- encender / apagar ----------
    def configurar(self, cfg):
        """Arranca, reinicia o apaga segun la configuracion."""
        threading.Thread(target=self._configurar, args=(dict(cfg),), daemon=True).start()

    def _configurar(self, cfg):
        with self._lock:
            self._apagar()
            if not cfg.get("voz"):
                self._cambiar(activo=False, error=None)
                return
            frases = {}
            for accion in ACCIONES:
                for f in cfg.get(f"voz_{accion}", []) or []:
                    n = normalizar(f)
                    if n:
                        frases[n] = accion
            if not frases:
                self._cambiar(activo=False, error="Agrega al menos una frase.")
                return
            self._acciones_por_frase = frases
            self._confianza = float(cfg.get("voz_confianza", 0.6))
            try:
                import clr
                clr.AddReference("System.Speech")
                from System import Array, String
                from System.Speech.Recognition import (SpeechRecognitionEngine, Grammar, GrammarBuilder,
                                                       Choices, RecognizeMode)
            except Exception:
                self._cambiar(activo=False, error="Este Windows no tiene el componente de voz (System.Speech).")
                return
            instalados = list(SpeechRecognitionEngine.InstalledRecognizers())
            if not instalados:
                self._cambiar(activo=False, error=(
                    "Windows no tiene ningún reconocimiento de voz instalado. Ve a Configuración > Hora e idioma > "
                    "Idioma, abre Opciones de tu idioma y descarga \"Reconocimiento de voz\"."))
                return
            elegido = self._elegir_idioma(instalados, cfg.get("voz_idioma") or "")
            try:
                motor = SpeechRecognitionEngine(elegido)
                constructor = GrammarBuilder()
                constructor.Culture = elegido.Culture
                constructor.Append(Choices(Array[String](list(frases.keys()))))
                motor.LoadGrammar(Grammar(constructor))
            except Exception as ex:
                self._cambiar(activo=False, error=f"No se pudo preparar el reconocimiento de voz: {ex}")
                return
            try:
                motor.SetInputToDefaultAudioDevice()
            except Exception:
                self._cambiar(activo=False, error="No encontré un micrófono. Conéctalo o elígelo como predeterminado en Windows.")
                return
            motor.SpeechRecognized += self._reconocido
            motor.RecognizeAsync(RecognizeMode.Multiple)
            self._motor = motor
            self._cambiar(activo=True, error=None, idioma=elegido.Culture.NativeName.capitalize())

    def apagar(self):
        with self._lock:
            self._apagar()
            self._cambiar(activo=False)

    def _apagar(self):
        if self._motor is not None:
            try:
                self._motor.RecognizeAsyncCancel()
                self._motor.Dispose()
            except Exception:
                pass
        self._motor = None

    @staticmethod
    def _elegir_idioma(instalados, preferido):
        for r in instalados:
            if r.Culture.Name.lower() == preferido.lower():
                return r
        for r in instalados:  # automatico: primero espanol, despues el que haya
            if r.Culture.Name.lower().startswith("es"):
                return r
        return instalados[0]

    # ---------- reconocimiento ----------
    def _reconocido(self, emisor, evento):
        try:
            texto = normalizar(evento.Result.Text)
            confianza = float(evento.Result.Confidence)
        except Exception:
            return
        accion = self._acciones_por_frase.get(texto)
        if accion is None:  # por si Windows devuelve la frase sin acentos
            sin = _sin_acentos(texto)
            accion = next((a for f, a in self._acciones_por_frase.items() if _sin_acentos(f) == sin), None)
        aceptado = accion is not None and confianza >= self._confianza and time.time() - self._ultimo_disparo > 2.5
        self.estado["ultimo"] = {"frase": texto, "confianza": round(confianza * 100), "aceptado": aceptado}
        self._al_cambiar(self.estado)
        if aceptado:
            self._ultimo_disparo = time.time()
            try:
                self._al_reconocer(accion, texto, confianza)
            except Exception:
                pass

    def _cambiar(self, **cambios):
        self.estado.update(cambios)
        try:
            self._al_cambiar(self.estado)
        except Exception:
            pass
