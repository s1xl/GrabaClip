// audiocap.exe - ayudante de audio para GrabaClip
//
//   audiocap list
//       Lista las apps que tienen una sesion de audio: "exe<TAB>pid" por linea.
//
//   audiocap run <prefijo> <pista> [<pista> ...]
//       Crea una tuberia \\.\pipe\<prefijo>_<n> por pista y escribe en ella audio
//       PCM s16le, 48000 Hz, estereo, continuo (rellena con silencio).
//       Pistas:  sys          -> todo el audio del sistema (salida predeterminada)
//                mic          -> microfono predeterminado
//                app:<exe>    -> solo el audio de ese programa (y sus subprocesos)
//       Termina cuando se cierra stdin o cuando ffmpeg deja de leer.
//       Por stdin acepta lineas "mute 1" / "mute 0": silencia o reactiva el microfono
//       (la pista sigue sonando continua, solo que con silencio).

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <initguid.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audiopolicy.h>
#include <tlhelp32.h>
#include <propvarutil.h>
#include <atomic>
#include <cstdio>
#include <cstdint>
#include <cwctype>
#include <map>
#include <set>
#include <string>
#include <thread>
#include <vector>
#include <algorithm>

static const int RATE = 48000;
static const int CH = 2;
static const LONGLONG HEADROOM_MS = 60;   // margen para que no lleguen paquetes "tarde"
static const size_t FIFO_MAX = RATE * 150 / 1000;  // frames
static const size_t FIFO_TRIM = RATE * 60 / 1000;

// ---------- definiciones de process loopback (no vienen en mingw) ----------
typedef enum { AUDIOCLIENT_ACTIVATION_TYPE_DEFAULT_ = 0, AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK_ = 1 } ACT_TYPE;
typedef enum { PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE_ = 0, PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE_ = 1 } PL_MODE;
struct PL_PARAMS { DWORD TargetProcessId; PL_MODE ProcessLoopbackMode; };
struct ACT_PARAMS { ACT_TYPE ActivationType; PL_PARAMS ProcessLoopbackParams; };
DEFINE_GUID(IID_IAgileObject_, 0x94ea2b94, 0xe9cc, 0x49e0, 0xc0, 0xff, 0xee, 0x64, 0xca, 0x8f, 0x5b, 0x90);
typedef HRESULT(WINAPI* PFN_ActivateAsync)(LPCWSTR, REFIID, PROPVARIANT*, IActivateAudioInterfaceCompletionHandler*, IActivateAudioInterfaceAsyncOperation**);

class ActHandler : public IActivateAudioInterfaceCompletionHandler {
    LONG ref = 1;
public:
    HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    ~ActHandler() { CloseHandle(done); }
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (riid == IID_IUnknown || riid == IID_IActivateAudioInterfaceCompletionHandler || riid == IID_IAgileObject_) {
            *ppv = static_cast<IActivateAudioInterfaceCompletionHandler*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref); }
    STDMETHODIMP_(ULONG) Release() override {
        LONG r = InterlockedDecrement(&ref);
        if (!r) delete this;
        return r;
    }
    STDMETHODIMP ActivateCompleted(IActivateAudioInterfaceAsyncOperation*) override {
        SetEvent(done);
        return S_OK;
    }
};

static WAVEFORMATEX formato() {
    WAVEFORMATEX f = {};
    f.wFormatTag = WAVE_FORMAT_PCM;
    f.nChannels = CH;
    f.nSamplesPerSec = RATE;
    f.wBitsPerSample = 16;
    f.nBlockAlign = CH * 2;
    f.nAvgBytesPerSec = RATE * f.nBlockAlign;
    return f;
}

static std::wstring minus(std::wstring s) {
    for (auto& c : s) c = (wchar_t)towlower(c);
    return s;
}

static std::string utf8(const std::wstring& w) {
    if (w.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, 0);
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

static std::wstring nombre_exe(DWORD pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return L"";
    wchar_t buf[MAX_PATH * 2];
    DWORD n = MAX_PATH * 2;
    std::wstring r;
    if (QueryFullProcessImageNameW(h, 0, buf, &n)) {
        r.assign(buf, n);
        size_t p = r.find_last_of(L"\\/");
        if (p != std::wstring::npos) r = r.substr(p + 1);
    }
    CloseHandle(h);
    return r;
}

// Procesos "raiz" de un exe: los que tienen ese nombre y cuyo padre no lo tiene.
static std::set<DWORD> raices(const std::wstring& exe) {
    std::set<DWORD> out;
    std::map<DWORD, std::pair<std::wstring, DWORD>> procs;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return out;
    PROCESSENTRY32W pe = {sizeof(pe)};
    if (Process32FirstW(snap, &pe)) {
        do procs[pe.th32ProcessID] = {minus(pe.szExeFile), pe.th32ParentProcessID};
        while (Process32NextW(snap, &pe));
    }
    CloseHandle(snap);
    std::wstring obj = minus(exe);
    for (auto& kv : procs) {
        if (kv.second.first != obj) continue;
        auto padre = procs.find(kv.second.second);
        if (padre == procs.end() || padre->second.first != obj) out.insert(kv.first);
    }
    return out;
}

// ---------- una fuente de audio (un IAudioClient) ----------
struct Fuente {
    IAudioClient* cliente = nullptr;
    IAudioCaptureClient* captura = nullptr;
    HANDLE evento = nullptr;
    std::vector<int16_t> fifo;
    DWORD pid = 0;
    bool muerta = false;

    ~Fuente() {
        if (cliente) cliente->Stop();
        if (captura) captura->Release();
        if (cliente) cliente->Release();
        if (evento) CloseHandle(evento);
    }

    bool iniciar(IAudioClient* c, DWORD flags_extra, bool con_evento) {
        cliente = c;
        WAVEFORMATEX f = formato();
        DWORD flags = AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY | flags_extra;
        if (con_evento) flags |= AUDCLNT_STREAMFLAGS_EVENTCALLBACK;
        if (FAILED(cliente->Initialize(AUDCLNT_SHAREMODE_SHARED, flags, 2000000, 0, &f, nullptr))) return false;
        if (con_evento) {
            evento = CreateEventW(nullptr, FALSE, FALSE, nullptr);
            if (FAILED(cliente->SetEventHandle(evento))) return false;
        }
        if (FAILED(cliente->GetService(__uuidof(IAudioCaptureClient), (void**)&captura))) return false;
        return SUCCEEDED(cliente->Start());
    }

    void leer() {
        if (muerta) return;
        UINT32 paquete = 0;
        while (true) {
            HRESULT hr = captura->GetNextPacketSize(&paquete);
            if (FAILED(hr)) { muerta = true; return; }
            if (paquete == 0) return;
            BYTE* datos;
            UINT32 frames;
            DWORD flags;
            hr = captura->GetBuffer(&datos, &frames, &flags, nullptr, nullptr);
            if (FAILED(hr)) { muerta = true; return; }
            size_t n = (size_t)frames * CH;
            size_t ini = fifo.size();
            fifo.resize(ini + n);
            if (flags & AUDCLNT_BUFFERFLAGS_SILENT) std::fill(fifo.begin() + ini, fifo.end(), 0);
            else memcpy(&fifo[ini], datos, n * sizeof(int16_t));
            captura->ReleaseBuffer(frames);
        }
    }
};

static Fuente* abrir_dispositivo(EDataFlow flujo) {
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), (void**)&en))) return nullptr;
    IMMDevice* dev = nullptr;
    HRESULT hr = en->GetDefaultAudioEndpoint(flujo, eConsole, &dev);
    en->Release();
    if (FAILED(hr)) return nullptr;
    IAudioClient* c = nullptr;
    hr = dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, (void**)&c);
    dev->Release();
    if (FAILED(hr)) return nullptr;
    Fuente* f = new Fuente();
    if (!f->iniciar(c, flujo == eRender ? AUDCLNT_STREAMFLAGS_LOOPBACK : 0, false)) { delete f; return nullptr; }
    return f;
}

static Fuente* abrir_proceso(DWORD pid) {
    static PFN_ActivateAsync activar = (PFN_ActivateAsync)GetProcAddress(LoadLibraryW(L"Mmdevapi.dll"), "ActivateAudioInterfaceAsync");
    if (!activar) return nullptr;
    ACT_PARAMS p = {};
    p.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK_;
    p.ProcessLoopbackParams.TargetProcessId = pid;
    p.ProcessLoopbackParams.ProcessLoopbackMode = PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE_;
    PROPVARIANT pv = {};
    pv.vt = VT_BLOB;
    pv.blob.cbSize = sizeof(p);
    pv.blob.pBlobData = (BYTE*)&p;
    ActHandler* h = new ActHandler();
    IActivateAudioInterfaceAsyncOperation* op = nullptr;
    HRESULT hr = activar(L"VAD\\Process_Loopback", __uuidof(IAudioClient), &pv, h, &op);
    if (FAILED(hr)) { h->Release(); return nullptr; }
    DWORD w = WaitForSingleObject(h->done, 5000);
    IUnknown* unk = nullptr;
    HRESULT hr2 = E_FAIL;
    if (w == WAIT_OBJECT_0) op->GetActivateResult(&hr2, &unk);
    op->Release();
    h->Release();
    if (FAILED(hr2) || !unk) return nullptr;
    IAudioClient* c = nullptr;
    hr = unk->QueryInterface(__uuidof(IAudioClient), (void**)&c);
    unk->Release();
    if (FAILED(hr)) return nullptr;
    Fuente* f = new Fuente();
    f->pid = pid;
    if (!f->iniciar(c, AUDCLNT_STREAMFLAGS_LOOPBACK, true)) { delete f; return nullptr; }
    return f;
}

// ---------- pistas ----------
static std::atomic<LONGLONG> g_t0{0};
static std::atomic<int> g_vivas{0};
static std::atomic<bool> g_mic_mudo{false};
static LARGE_INTEGER g_freq;

static LONGLONG ahora_ms() {
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return c.QuadPart * 1000 / g_freq.QuadPart;
}

static void hilo_pista(std::wstring tipo, HANDLE tubo) {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    BOOL ok = ConnectNamedPipe(tubo, nullptr) || GetLastError() == ERROR_PIPE_CONNECTED;
    if (!ok) { g_vivas--; return; }
    LONGLONG esperado = 0;
    if (g_t0.compare_exchange_strong(esperado, ahora_ms())) {}
    const LONGLONG t0 = g_t0.load();

    std::vector<Fuente*> fuentes;
    std::wstring app;
    if (tipo.rfind(L"app:", 0) == 0) app = tipo.substr(4);
    LONGLONG ultimo_mant = -100000;
    unsigned long long emitidos = 0;
    std::vector<int32_t> mezcla;
    std::vector<int16_t> salida;

    while (true) {
        LONGLONG t = ahora_ms();
        // mantenimiento cada 3 s: abrir fuentes nuevas, quitar las muertas
        if (t - ultimo_mant >= 3000) {
            ultimo_mant = t;
            fuentes.erase(std::remove_if(fuentes.begin(), fuentes.end(), [](Fuente* f) {
                if (f->muerta) { delete f; return true; }
                return false;
            }), fuentes.end());
            if (!app.empty()) {
                std::set<DWORD> rs = raices(app);
                fuentes.erase(std::remove_if(fuentes.begin(), fuentes.end(), [&](Fuente* f) {
                    if (!rs.count(f->pid)) { delete f; return true; }
                    return false;
                }), fuentes.end());
                for (DWORD pid : rs) {
                    bool ya = false;
                    for (auto* f : fuentes) if (f->pid == pid) ya = true;
                    if (!ya) if (Fuente* f = abrir_proceso(pid)) fuentes.push_back(f);
                }
            } else if (fuentes.empty()) {
                if (Fuente* f = abrir_dispositivo(tipo == L"mic" ? eCapture : eRender)) fuentes.push_back(f);
            }
        }
        for (auto* f : fuentes) f->leer();

        LONGLONG obj_ms = ahora_ms() - t0 - HEADROOM_MS;
        unsigned long long objetivo = obj_ms > 0 ? (unsigned long long)obj_ms * RATE / 1000 : 0;
        if (objetivo > emitidos) {
            size_t n = (size_t)(objetivo - emitidos);
            mezcla.assign(n * CH, 0);
            for (auto* f : fuentes) {
                size_t disp = std::min(n, f->fifo.size() / CH);
                for (size_t i = 0; i < disp * CH; i++) mezcla[i] += f->fifo[i];
                f->fifo.erase(f->fifo.begin(), f->fifo.begin() + disp * CH);
                if (f->fifo.size() / CH > FIFO_MAX)  // evitar que se acumule retraso
                    f->fifo.erase(f->fifo.begin(), f->fifo.end() - FIFO_TRIM * CH);
            }
            if (tipo == L"mic" && g_mic_mudo) std::fill(mezcla.begin(), mezcla.end(), 0);
            salida.resize(n * CH);
            for (size_t i = 0; i < n * CH; i++)
                salida[i] = (int16_t)std::max(-32768, std::min(32767, mezcla[i]));
            DWORD escritos = 0;
            if (!WriteFile(tubo, salida.data(), (DWORD)(salida.size() * 2), &escritos, nullptr)) break;
            emitidos = objetivo;
        }
        Sleep(10);
    }
    for (auto* f : fuentes) delete f;
    CloseHandle(tubo);
    g_vivas--;
}

static int cmd_list() {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), (void**)&en))) return 1;
    IMMDeviceCollection* col = nullptr;
    en->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &col);
    UINT nd = 0;
    if (col) col->GetCount(&nd);
    std::map<std::wstring, DWORD> vistos;
    DWORD yo = GetCurrentProcessId();
    for (UINT d = 0; d < nd; d++) {
        IMMDevice* dev = nullptr;
        if (FAILED(col->Item(d, &dev))) continue;
        IAudioSessionManager2* mgr = nullptr;
        if (SUCCEEDED(dev->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, (void**)&mgr))) {
            IAudioSessionEnumerator* se = nullptr;
            if (SUCCEEDED(mgr->GetSessionEnumerator(&se))) {
                int ns = 0;
                se->GetCount(&ns);
                for (int i = 0; i < ns; i++) {
                    IAudioSessionControl* ctl = nullptr;
                    if (FAILED(se->GetSession(i, &ctl))) continue;
                    IAudioSessionControl2* ctl2 = nullptr;
                    if (SUCCEEDED(ctl->QueryInterface(__uuidof(IAudioSessionControl2), (void**)&ctl2))) {
                        DWORD pid = 0;
                        ctl2->GetProcessId(&pid);
                        if (pid && pid != yo) {
                            std::wstring exe = nombre_exe(pid);
                            if (!exe.empty() && !vistos.count(minus(exe))) {
                                vistos[minus(exe)] = pid;
                                printf("%s\t%lu\n", utf8(exe).c_str(), pid);
                            }
                        }
                        ctl2->Release();
                    }
                    ctl->Release();
                }
                se->Release();
            }
            mgr->Release();
        }
        dev->Release();
    }
    if (col) col->Release();
    en->Release();
    fflush(stdout);
    return 0;
}

int wmain(int argc, wchar_t** argv) {
    QueryPerformanceFrequency(&g_freq);
    if (argc >= 2 && std::wstring(argv[1]) == L"list") return cmd_list();
    if (argc < 4 || std::wstring(argv[1]) != L"run") {
        fprintf(stderr, "uso: audiocap list | audiocap run <prefijo> <pista>...\n");
        return 2;
    }
    std::wstring prefijo = argv[2];
    std::vector<std::thread> hilos;
    std::vector<std::pair<std::wstring, HANDLE>> pistas;
    for (int i = 3; i < argc; i++) {
        std::wstring nombre = L"\\\\.\\pipe\\" + prefijo + L"_" + std::to_wstring(i - 3);
        HANDLE t = CreateNamedPipeW(nombre.c_str(), PIPE_ACCESS_OUTBOUND, PIPE_TYPE_BYTE | PIPE_WAIT, 1,
                                    1 << 20, 0, 0, nullptr);
        if (t == INVALID_HANDLE_VALUE) {
            fprintf(stderr, "no se pudo crear la tuberia %d\n", i - 3);
            return 3;
        }
        pistas.push_back({argv[i], t});
    }
    g_vivas = (int)pistas.size();
    for (auto& p : pistas) hilos.emplace_back(hilo_pista, p.first, p.second);
    printf("READY\n");
    fflush(stdout);

    // terminar cuando se cierre stdin
    std::atomic<bool> fin{false};
    std::thread lector([&] {
        char b[64];
        DWORD n;
        std::string linea;
        HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
        while (ReadFile(in, b, sizeof(b), &n, nullptr) && n > 0) {
            for (DWORD i = 0; i < n; i++) {
                if (b[i] != '\n') { if (linea.size() < 64) linea += b[i]; continue; }
                if (linea.rfind("mute ", 0) == 0) g_mic_mudo = linea.size() > 5 && linea[5] == '1';
                linea.clear();
            }
        }
        fin = true;
    });
    lector.detach();
    while (!fin && g_vivas > 0) Sleep(200);
    ExitProcess(0);
}
