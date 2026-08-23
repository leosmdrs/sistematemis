# -*- mode: python ; coding: utf-8 -*-
"""
Especificação do PyInstaller para o Sistema Têmis.

Uso (a partir da raiz do projeto):
    python build/make_icon.py
    pyinstaller build/temis.spec --noconfirm
"""

import os

ROOT = os.path.abspath(os.getcwd())
ICON = os.path.join(ROOT, "build", "temis.ico")

# FFmpeg vai junto, na pasta "ffmpeg": a Edição de Vídeo depende dele e as
# estações onde o Têmis roda não têm como instalar pré-requisitos.
# video_core.localizar() procura exatamente aqui antes de tentar o PATH.
FFMPEG = [
    (os.path.join(ROOT, "vendor", "ffmpeg", "bin", exe), "ffmpeg")
    for exe in ("ffmpeg.exe", "ffprobe.exe")
    if os.path.isfile(os.path.join(ROOT, "vendor", "ffmpeg", "bin", exe))
]
if not FFMPEG:
    print("AVISO: vendor/ffmpeg/bin não encontrado — a Edição de Vídeo "
          "ficará indisponível no pacote gerado.")

a = Analysis(
    # Precisa ser o run_temis.py da raiz, e não temis/__main__.py: o
    # PyInstaller executa a entrada como script sem pacote pai, o que
    # quebraria todos os imports relativos do pacote.
    [os.path.join(ROOT, "run_temis.py")],
    pathex=[ROOT],
    binaries=[],
    datas=FFMPEG,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Módulos Qt que não usamos. O QtWebEngine é o que mais pesa: um
    # Chromium inteiro, cerca de 350 MB entre a DLL, os recursos e o
    # QtQuick/QtQml de que depende. Entrou no sistema por causa da
    # Calculadora ePAD e saiu com ela — o instalador inteiro passou a
    # caber em menos que aquela única biblioteca.
    excludes=[
        "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineQuick", "PyQt6.QtWebChannel",
        "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQml",
        "PyQt6.QtMultimedia", "PyQt6.QtBluetooth", "PyQt6.QtPositioning",
        "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtCharts",
        "tkinter", "unittest", "pydoc", "doctest",
        "matplotlib", "numpy", "scipy", "pandas",
    ],
    noarchive=False,
    optimize=0,
)

# ── enxugamento ──────────────────────────────────────────
#: O Qt traz a tradução da própria interface em todos os idiomas que
#: suporta — 53 MB para um programa que só fala português.
IDIOMAS = ("pt_br", "pt")


def _traducao_alheia(destino: str) -> bool:
    d = destino.replace("\\", "/").lower()
    if "/translations/" not in d or not d.endswith(".qm"):
        return False
    return not any(f"_{i}.qm" in d for i in IDIOMAS)


#: Restos do QtWebEngine que o PyInstaller recolhe como dados, e que a
#: lista `excludes` não alcança por não serem módulos Python.
def _resto_do_navegador(destino: str) -> bool:
    d = destino.replace("\\", "/").lower()
    return ("webengine" in d or "/qtwebengine" in d
            or d.endswith("qtwebengineprocess.exe"))


def _dispensavel(destino: str) -> bool:
    return _traducao_alheia(destino) or _resto_do_navegador(destino)


a.datas = TOC([(d, o, k) for d, o, k in a.datas if not _dispensavel(d)])
a.binaries = TOC([(d, o, k) for d, o, k in a.binaries
                  if not _resto_do_navegador(d)])

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SistemaTemis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # aplicação gráfica: sem janela de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    version=os.path.join(ROOT, "build", "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SistemaTemis",
)
