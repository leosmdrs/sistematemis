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
    # Módulos Qt que não usamos.
    #
    # O QtWebEngine saiu do pacote quando a Calculadora ePAD foi retirada:
    # 350 MB de Chromium para exibir uma página que um favorito resolvia.
    # Voltou com a Constatação Web, e aí a conta é outra — ali o navegador
    # não é conveniência, é o instrumento da captura. Ambiente controlado,
    # sem extensão e sem sessão anterior, com a versão do motor viajando
    # junto com a versão do programa, é o que dá valor à peça.
    excludes=[
        "PyQt6.QtQuick3D", "PyQt6.QtMultimedia", "PyQt6.QtBluetooth",
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


a.datas = TOC([(d, o, k) for d, o, k in a.datas
               if not _traducao_alheia(d)])

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
