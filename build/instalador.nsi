; Instalador de GrabaClip (NSIS). Se compila en GitHub Actions desde build/build.sh:
;   makensis -DVERSION=x.y.z -DORIGEN=<carpeta GrabaClip armada> -DSALIDA=<setup.exe> build/instalador.nsi
; Se instala por usuario (sin permisos de administrador) en %LOCALAPPDATA%\Programs\GrabaClip,
; con acceso directo en el menú Inicio y desinstalador en Configuración > Aplicaciones.
; Los videos (Videos\GrabaClip) nunca se tocan.

Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user
ManifestDPIAware true

!define APP "GrabaClip"
!define CLAVE_DESINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\GrabaClip"
!define WEB "https://github.com/s1xl/GrabaClip"

Name "${APP}"
OutFile "${SALIDA}"
InstallDir "$LOCALAPPDATA\Programs\${APP}"
InstallDirRegKey HKCU "${CLAVE_DESINST}" "InstallLocation"
BrandingText "${APP} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1034 "ProductName" "${APP}"
VIAddVersionKey /LANG=1034 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1034 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1034 "FileDescription" "Instalador de ${APP}"
VIAddVersionKey /LANG=1034 "CompanyName" "s1xl"
VIAddVersionKey /LANG=1034 "LegalCopyright" "Copyright (c) 2026 s1xl - MIT License"

!include "MUI2.nsh"
!define MUI_ICON "${ORIGEN}\grabaclip.ico"
!define MUI_UNICON "${ORIGEN}\grabaclip.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Este asistente instalará ${APP} ${VERSION}, el grabador de clips instantáneos gratis y open source.$\r$\n$\r$\nNo necesita permisos de administrador. Tus videos se guardan en la carpeta Videos\GrabaClip."
!define MUI_FINISHPAGE_RUN "$INSTDIR\GrabaClip.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir ${APP} ahora"
!define MUI_FINISHPAGE_LINK "Código fuente y ayuda en GitHub"
!define MUI_FINISHPAGE_LINK_LOCATION "${WEB}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"

; GrabaClip deja abierto ".abierto" mientras funciona: si no se puede borrar, está abierto.
!macro ESPERAR_CERRADO ID
  reintentar_${ID}:
  IfFileExists "$INSTDIR\.abierto" 0 libre_${ID}
  ClearErrors
  Delete "$INSTDIR\.abierto"
  IfErrors 0 libre_${ID}
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "GrabaClip está abierto.$\r$\nCiérralo (clic derecho en su ícono junto al reloj > Salir) y pulsa Reintentar." IDRETRY reintentar_${ID}
  Abort
  libre_${ID}:
!macroend

Section "GrabaClip (necesario)" SecApp
  SectionIn RO
  !insertmacro ESPERAR_CERRADO inst
  SetOutPath "$INSTDIR"
  File /r "${ORIGEN}\*.*"
  WriteUninstaller "$INSTDIR\Desinstalar GrabaClip.exe"
  CreateShortcut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\GrabaClip.exe" "" "$INSTDIR\grabaclip.ico"
  WriteRegStr HKCU "${CLAVE_DESINST}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${CLAVE_DESINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${CLAVE_DESINST}" "Publisher" "s1xl"
  WriteRegStr HKCU "${CLAVE_DESINST}" "DisplayIcon" "$INSTDIR\grabaclip.ico"
  WriteRegStr HKCU "${CLAVE_DESINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CLAVE_DESINST}" "UninstallString" '"$INSTDIR\Desinstalar GrabaClip.exe"'
  WriteRegStr HKCU "${CLAVE_DESINST}" "QuietUninstallString" '"$INSTDIR\Desinstalar GrabaClip.exe" /S'
  WriteRegStr HKCU "${CLAVE_DESINST}" "URLInfoAbout" "${WEB}"
  WriteRegDWORD HKCU "${CLAVE_DESINST}" "NoModify" 1
  WriteRegDWORD HKCU "${CLAVE_DESINST}" "NoRepair" 1
  WriteRegDWORD HKCU "${CLAVE_DESINST}" "EstimatedSize" 260000
SectionEnd

Section "Acceso directo en el escritorio" SecEscritorio
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\GrabaClip.exe" "" "$INSTDIR\grabaclip.ico"
SectionEnd

LangString DESC_App ${LANG_SPANISH} "El programa, con Python y FFmpeg incluidos."
LangString DESC_Escritorio ${LANG_SPANISH} "Un ícono de GrabaClip en el escritorio."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp} $(DESC_App)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecEscritorio} $(DESC_Escritorio)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  !insertmacro ESPERAR_CERRADO desinst
  ; Se borra solo lo que pertenece a GrabaClip, por nombre (nunca la carpeta entera con /r:
  ; si alguien lo instaló en una carpeta con otras cosas, esas cosas se quedan). Los videos no se tocan.
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\miniaturas"
  RMDir /r "$INSTDIR\logs"
  RMDir /r "$INSTDIR\sonidos"
  RMDir /r "$INSTDIR\__pycache__"
  RMDir /r "$INSTDIR\_actualizacion"
  RMDir /r "$INSTDIR\bufer"
  Delete "$INSTDIR\GrabaClip.exe"
  Delete "$INSTDIR\audiocap.exe"
  Delete "$INSTDIR\grabaclip.ico"
  Delete "$INSTDIR\ui.html"
  Delete "$INSTDIR\VERSION"
  Delete "$INSTDIR\LEEME.txt"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\TERCEROS.txt"
  Delete "$INSTDIR\config.json"
  Delete "$INSTDIR\favoritos.json"
  Delete "$INSTDIR\marcas.json"
  Delete "$INSTDIR\.abierto"
  Delete "$INSTDIR\grabaclip.py"
  Delete "$INSTDIR\grabaclip_clasico.py"
  Delete "$INSTDIR\nucleo.py"
  Delete "$INSTDIR\ventana_activa.py"
  Delete "$INSTDIR\overlay.py"
  Delete "$INSTDIR\sonidos.py"
  Delete "$INSTDIR\voz.py"
  Delete "$INSTDIR\actualizador.py"
  Delete "$INSTDIR\bandeja.py"
  Delete "$INSTDIR\recortes.py"
  Delete "$INSTDIR\discord_rpc.py"
  Delete "$INSTDIR\Desinstalar GrabaClip.exe"
  RMDir "$INSTDIR"  ; solo si quedó vacía
  Delete "$SMPROGRAMS\${APP}.lnk"
  Delete "$DESKTOP\${APP}.lnk"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "GrabaClip"
  DeleteRegKey HKCU "${CLAVE_DESINST}"
SectionEnd
