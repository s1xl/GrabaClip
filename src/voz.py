"""
Comandos de voz de GrabaClip ("Jarvis, sacale clip").

Usa el reconocimiento de voz de Windows (System.Speech, a traves de pythonnet), que
funciona sin internet: el audio del microfono se procesa en la PC y no se envia a
ningun lado. Solo se reconocen las frases que el usuario configuro (una gramatica
cerrada), lo que lo hace preciso y muy ligero.
"""
import os
import re
import glob
import time
import threading
import traceback
import unicodedata

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "voz.txt")
NOMBRE_COMPLETO = "System.Speech, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35"


def _log(texto):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + texto.rstrip() + "\n")
    except Exception:
        pass


def cargar_speech():
    """Carga System.Speech de .NET Framework. pythonnet 3 ya no encuentra las DLL del
    sistema solo por su nombre corto, asi que se prueba con el nombre completo y,
    si hace falta, con la ruta del archivo en el GAC de Windows."""
    import clr
    errores = []
    for intento in ("System.Speech", NOMBRE_COMPLETO):
        try:
            clr.AddReference(intento)
            import System.Speech.Recognition  # noqa: F401
            return True
        except Exception as ex:
            errores.append(f"AddReference({intento!r}): {ex}")
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidatos = glob.glob(os.path.join(windir, "Microsoft.NET", "assembly", "GAC_MSIL", "System.Speech", "*", "System.Speech.dll"))
    candidatos += glob.glob(os.path.join(windir, "Microsoft.NET", "Framework64", "v4.0.30319", "WPF", "System.Speech.dll"))
    candidatos += glob.glob(os.path.join(windir, "Microsoft.NET", "Framework", "v4.0.30319", "WPF", "System.Speech.dll"))
    for ruta in candidatos:
        try:
            from System.Reflection import Assembly
            Assembly.LoadFrom(ruta)
            clr.AddReference(ruta)
            import System.Speech.Recognition  # noqa: F401
            return True
        except Exception as ex:
            errores.append(f"LoadFrom({ruta}): {ex}")
    _log("No se pudo cargar System.Speech:\n  " + "\n  ".join(errores or ["no se encontro System.Speech.dll"]))
    return False

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
            if not cargar_speech():
                return []
            from System.Speech.Recognition import SpeechRecognitionEngine
            return [{"id": r.Culture.Name, "nombre": r.Culture.NativeName.capitalize()}
                    for r in SpeechRecognitionEngine.InstalledRecognizers()]
        except Exception:
            _log("idiomas: " + traceback.format_exc())
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
                if not cargar_speech():
                    raise RuntimeError("System.Speech no disponible")
                from System import Array, String
                from System.Speech.Recognition import (SpeechRecognitionEngine, Grammar, GrammarBuilder,
                                                       Choices, RecognizeMode)
            except Exception:
                _log("configurar: " + traceback.format_exc())
                self._cambiar(activo=False, error="No pude cargar el reconocimiento de voz de Windows (detalles en logs\\voz.txt).")
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
                _log("motor: " + traceback.format_exc())
                self._cambiar(activo=False, error=f"No se pudo preparar el reconocimiento de voz: {ex}")
                return
            try:
                motor.SetInputToDefaultAudioDevice()
            except Exception:
                _log("microfono: " + traceback.format_exc())
                self._cambiar(activo=False, error="No encontré un micrófono. Conéctalo o elígelo como predeterminado en Windows.")
                return
            motor.SpeechRecognized += self._reconocido
            motor.RecognizeAsync(RecognizeMode.Multiple)
            self._motor = motor
            self._cambiar(activo=True, error=None, idioma=elegido.Culture.NativeName.capitalize())
            _log(f"Escuchando en {elegido.Culture.Name} ({elegido.Description}) con {len(frases)} frases")

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
