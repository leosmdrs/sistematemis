# -*- mode: python ; coding: utf-8 -*-
"""
Especificação do PyInstaller para o Sistema Têmis.

Uso (a partir da raiz do projeto):
    python build/make_icon.py
    pyinstaller build/temis.spec --noconfirm
"""

import os

from PyInstaller.utils.hooks import (collect_data_files,
                                     collect_dynamic_libs,
                                     collect_submodules)

ROOT = os.path.abspath(os.getcwd())
ICON = os.path.join(ROOT, "build", "temis.ico")

# O reconhecimento óptico usa o motor do próprio Windows, alcançado pelos
# pacotes `winrt`. São *namespace packages* com extensões compiladas, e o
# PyInstaller não os enxerga por inteiro sozinho — sem esta lista, a
# Varredura e o PDF Pesquisável sairiam do forno anunciando "OCR
# indisponível", e só na máquina de quem instalou, que é o pior lugar
# para se descobrir uma coisa dessas.
WINRT = [
    "winrt.runtime",
    "winrt.system",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.globalization",
    "winrt.windows.graphics.imaging",
    "winrt.windows.media.ocr",
    "winrt.windows.storage.streams",
] + collect_submodules("winrt")

#: O pacote traz o runtime do Visual C++ de que suas extensões dependem.
WINRT_BINARIOS = collect_dynamic_libs("winrt")

# O PyInstaller coleta **código**, não dados. Uma biblioteca que carrega
# um modelo de dentro do próprio pacote sai do forno sem ele, e o erro só
# aparece na hora de usar, na máquina de quem instalou.
#
# Foi o que aconteceu com a Degravação na 1.3.0: o faster-whisper guarda
# o detector de voz em `faster_whisper/assets/silero_vad_v6.onnx` e o
# procura por `os.path.dirname(__file__)`. Sem ele, a transcrição morria
# com "NO_SUCHFILE: Load model ... failed. File doesn't exist".
#
# Varreram-se todas as dependências atrás do mesmo problema. Só esta
# tinha dado de verdade faltando: o resto era stub de tipo, cabeçalho C e
# licença, que não pesam na execução. As DLLs do sherpa-onnx pareciam
# faltar, mas escondê-las do interpretador não impediu o import — estão
# ligadas estaticamente ao módulo compilado.
DADOS_DE_PACOTE = collect_data_files("faster_whisper")

# O scrcpy e o adb vão junto, na pasta "scrcpy": o Espelhamento de
# Celular depende deles e a premissa do sistema é que a estação não tenha
# como instalar pré-requisito.
#
# São redistribuíveis, e isso foi apurado antes de embutir: o adb é do
# AOSP sob Apache-2.0; a licença do SDK do Android proíbe redistribuir o
# conjunto (§3.4) mas ressalva expressamente os componentes de código
# aberto, regidos pela própria licença (§3.5); o Debian empacota
# `android-platform-tools` na área `main`, que exige licença livre e
# redistribuível; e o próprio scrcpy distribui o adb.exe em suas versões
# oficiais. O FFmpeg que acompanha o scrcpy foi conferido no binário e é
# LGPL — sem --enable-gpl —, distinto do nosso.
_PASTA_SCRCPY = os.path.join(ROOT, "vendor", "scrcpy")
SCRCPY = [
    (os.path.join(_PASTA_SCRCPY, nome), "scrcpy")
    for nome in (sorted(os.listdir(_PASTA_SCRCPY))
                 if os.path.isdir(_PASTA_SCRCPY) else [])
    if os.path.isfile(os.path.join(_PASTA_SCRCPY, nome))
]
if not SCRCPY:
    print("AVISO: vendor/scrcpy não encontrado — o Espelhamento de Celular "
          "ficará indisponível no pacote gerado.")

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
    binaries=WINRT_BINARIOS,
    datas=FFMPEG + SCRCPY + DADOS_DE_PACOTE,
    hiddenimports=WINRT,
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
    # `numpy` esteve nesta lista e não podia estar. A exclusão vinha de
    # quando o sistema não transcrevia nada; com a Degravação, tanto o
    # faster-whisper quanto o sherpa-onnx dependem dele. O resultado é que
    # a ferramenta funcionava ao rodar pelo código-fonte — onde o numpy
    # está instalado — e falhava no programa instalado, com
    # "ModuleNotFoundError: No module named 'numpy'". Descoberto rodando
    # `SistemaTemis.exe --autoteste` no pacote gerado, que é o único lugar
    # onde esse tipo de erro aparece.
    excludes=[
        "PyQt6.QtQuick3D", "PyQt6.QtMultimedia", "PyQt6.QtBluetooth",
        "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtCharts",
        "tkinter", "unittest", "pydoc", "doctest",
        "matplotlib", "scipy", "pandas",
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
