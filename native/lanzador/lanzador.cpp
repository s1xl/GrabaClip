// GrabaClip.exe - lanzador de GrabaClip
//
// - Registra o quita el inicio con Windows segun config.json ("iniciar_con_windows").
//   Lo hace este .exe porque el Python de la Microsoft Store no puede escribir
//   de verdad en el registro (usa una copia privada).
// - Si GrabaClip ya esta abierto, solo lo trae al frente.
// - Busca Python, instala lo que falte (pywebview, keyboard) y abre grabaclip.py.
//
// Uso: GrabaClip.exe [--minimizado]

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cwchar>
#include <string>
#include <vector>

static std::wstring g_dir;

static std::wstring dir_exe() {
    wchar_t buf[MAX_PATH * 2];
    DWORD n = GetModuleFileNameW(nullptr, buf, MAX_PATH * 2);
    std::wstring p(buf, n);
    return p.substr(0, p.find_last_of(L"\\/"));
}

static bool existe(const std::wstring& p) {
    return GetFileAttributesW(p.c_str()) != INVALID_FILE_ATTRIBUTES;
}

static std::string leer_archivo(const std::wstring& p) {
    HANDLE h = CreateFileW(p.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                           OPEN_EXISTING, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return {};
    std::string s;
    char b[4096];
    DWORD n;
    while (ReadFile(h, b, sizeof(b), &n, nullptr) && n) s.append(b, n);
    CloseHandle(h);
    return s;
}

static bool config_bool(const std::string& json, const char* clave) {
    std::string k = std::string("\"") + clave + "\"";
    size_t p = json.find(k);
    if (p == std::string::npos) return false;
    p = json.find(':', p + k.size());
    if (p == std::string::npos) return false;
    p++;
    while (p < json.size() && (json[p] == ' ' || json[p] == '\t' || json[p] == '\r' || json[p] == '\n')) p++;
    return json.compare(p, 4, "true") == 0;
}

static void sincronizar_inicio() {
    bool quiere = config_bool(leer_archivo(g_dir + L"\\config.json"), "iniciar_con_windows");
    HKEY k;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0,
                      KEY_SET_VALUE | KEY_QUERY_VALUE, &k) != ERROR_SUCCESS)
        return;
    if (quiere) {
        std::wstring cmd = L"\"" + g_dir + L"\\GrabaClip.exe\" --minimizado";
        RegSetValueExW(k, L"GrabaClip", 0, REG_SZ, (const BYTE*)cmd.c_str(),
                       (DWORD)((cmd.size() + 1) * sizeof(wchar_t)));
    } else {
        RegDeleteValueW(k, L"GrabaClip");
    }
    RegCloseKey(k);
}

static bool ya_abierto() {
    // grabaclip.py mantiene abierto este archivo mientras funciona
    std::wstring p = g_dir + L"\\.abierto";
    if (!existe(p)) return false;
    HANDLE h = CreateFileW(p.c_str(), GENERIC_READ, 0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return GetLastError() == ERROR_SHARING_VIOLATION;
    CloseHandle(h);
    return false;
}

static void traer_al_frente() {
    // GrabaClip puede estar escondido junto al reloj: se le pide que muestre su ventana
    HANDLE ev = OpenEventW(EVENT_MODIFY_STATE, FALSE, L"Local\\GrabaClip_mostrar");
    if (ev) {
        AllowSetForegroundWindow(ASFW_ANY);
        SetEvent(ev);
        CloseHandle(ev);
        return;
    }
    HWND w = nullptr;
    while ((w = FindWindowExW(nullptr, w, nullptr, L"GrabaClip")) != nullptr) {
        wchar_t clase[128];
        GetClassNameW(w, clase, 128);
        if (wcscmp(clase, L"CabinetWClass") == 0) continue;  // carpeta del Explorador
        if (IsIconic(w)) ShowWindow(w, SW_RESTORE);
        SetForegroundWindow(w);
        return;
    }
}

static std::wstring leer_reg(HKEY raiz, const wchar_t* sub, const wchar_t* valor) {
    wchar_t buf[32767];
    DWORD tam = sizeof(buf);
    if (RegGetValueW(raiz, sub, valor, RRF_RT_REG_SZ | RRF_RT_REG_EXPAND_SZ | RRF_NOEXPAND, nullptr,
                     buf, &tam) != ERROR_SUCCESS)
        return {};
    return buf;
}

static std::wstring expandir(const std::wstring& s) {
    wchar_t buf[32767];
    DWORD n = ExpandEnvironmentStringsW(s.c_str(), buf, 32767);
    return n ? std::wstring(buf) : s;
}

static void refrescar_path() {
    // por si Python o FFmpeg se instalaron despues de iniciar sesion
    std::wstring sys = leer_reg(HKEY_LOCAL_MACHINE,
                                L"SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment", L"Path");
    std::wstring usr = leer_reg(HKEY_CURRENT_USER, L"Environment", L"Path");
    wchar_t local[MAX_PATH];
    GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
    std::wstring path = expandir(sys) + L";" + expandir(usr) + L";" + local + L"\\Microsoft\\WinGet\\Links";
    // FFmpeg incluido en la version portable tiene prioridad
    if (existe(g_dir + L"\\runtime\\ffmpeg\\ffmpeg.exe")) path = g_dir + L"\\runtime\\ffmpeg;" + path;
    SetEnvironmentVariableW(L"PATH", path.c_str());
}

static bool g_portable = false;

static std::wstring buscar_python() {
    // Python incluido en la version portable
    std::wstring propio = g_dir + L"\\runtime\\python";
    if (existe(propio + L"\\pythonw.exe")) {
        g_portable = true;
        SetEnvironmentVariableW(L"PYTHONNOUSERSITE", L"1");
        return propio;
    }
    wchar_t local[MAX_PATH], pf[MAX_PATH];
    GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
    GetEnvironmentVariableW(L"ProgramFiles", pf, MAX_PATH);
    const wchar_t* versiones[] = {L"314", L"313", L"312", L"311", L"310"};
    for (auto v : versiones) {
        std::wstring a = std::wstring(local) + L"\\Programs\\Python\\Python" + v;
        if (existe(a + L"\\pythonw.exe")) return a;
        std::wstring b = std::wstring(pf) + L"\\Python" + v;
        if (existe(b + L"\\pythonw.exe")) return b;
    }
    std::wstring store = std::wstring(local) + L"\\Microsoft\\WindowsApps";
    if (existe(store + L"\\pythonw.exe")) return store;
    return {};
}

static DWORD ejecutar(const std::wstring& cmd, bool mostrar, bool esperar) {
    STARTUPINFOW si = {sizeof(si)};
    PROCESS_INFORMATION pi = {};
    std::vector<wchar_t> buf(cmd.begin(), cmd.end());
    buf.push_back(0);
    DWORD flags = mostrar ? CREATE_NEW_CONSOLE : CREATE_NO_WINDOW;
    if (!CreateProcessW(nullptr, buf.data(), nullptr, nullptr, FALSE, flags, nullptr, g_dir.c_str(), &si, &pi))
        return (DWORD)-1;
    DWORD code = 0;
    if (esperar) {
        WaitForSingleObject(pi.hProcess, INFINITE);
        GetExitCodeProcess(pi.hProcess, &code);
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return code;
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, LPWSTR, int) {
    g_dir = dir_exe();
    sincronizar_inicio();

    if (ya_abierto()) {
        traer_al_frente();
        return 0;
    }

    bool minimizado = wcsstr(GetCommandLineW(), L"--minimizado") != nullptr;
    refrescar_path();
    std::wstring py = buscar_python();
    if (py.empty()) {
        MessageBoxW(nullptr, L"No encontré los archivos de GrabaClip.\n\nVuelve a descomprimir el .zip completo y abre GrabaClip.exe.",
                    L"GrabaClip", MB_ICONERROR);
        return 1;
    }

    std::wstring python = L"\"" + py + L"\\python.exe\"";
    if (ejecutar(python + L" -c \"import webview, keyboard\"", false, true) != 0) {
        if (minimizado) {
            // al iniciar Windows no molestamos: abrimos la version clasica sin instalar nada
        } else {
            std::wstring usuario = g_portable ? L"" : L" --user";
            ejecutar(L"cmd.exe /c \"title GrabaClip && echo. && echo   Preparando GrabaClip (solo la primera vez, tarda unos segundos)... && echo. && " +
                         python + L" -m pip install" + usuario +
                         L" --upgrade --disable-pip-version-check --no-warn-script-location -q pywebview keyboard"
                         L" || (echo. && echo   No se pudo descargar. Revisa tu conexion a internet. && pause)\"",
                     true, true);
        }
    }

    std::wstring cmd = L"\"" + py + L"\\pythonw.exe\" \"" + g_dir + L"\\grabaclip.py\"";
    if (minimizado) cmd += L" --minimizado";
    if (ejecutar(cmd, false, false) == (DWORD)-1) {
        MessageBoxW(nullptr, L"No pude abrir GrabaClip.", L"GrabaClip", MB_ICONERROR);
        return 1;
    }
    return 0;
}
