"""
Ponto de entrada do executável empacotado.

O PyInstaller roda o arquivo de entrada como um script solto, sem pacote
pai — então apontá-lo direto para `temis/__main__.py` quebra todos os
imports relativos ("attempted relative import with no known parent
package"). Este arquivo fica fora do pacote e o importa de forma
absoluta, preservando `python -m temis` para execução a partir do código.
"""

import sys

from temis.__main__ import main


def autoteste() -> int:
    """Confere se o que foi empacotado funciona nesta máquina.

    Existe porque erro de empacotamento — uma biblioteca nativa que ficou
    de fora, um binário que não veio junto — só aparece na estação de quem
    instalou, e na forma de uma janela que não abre. Rodando
    `SistemaTemis.exe --autoteste` num terminal, o problema se identifica
    em segundos, e sem precisar da interface.
    """
    import os
    from pathlib import Path

    from temis import __version__

    # O executável é gráfico, sem console próprio. Chamado de um terminal,
    # ele se prende ao console de quem o chamou; e o relatório vai também
    # para arquivo, que é o que se pede a quem estiver do outro lado do
    # telefone quando nem terminal há.
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        try:
            from ctypes import windll
            if windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8",
                                  errors="replace")
                sys.stderr = sys.stdout
        except Exception:                               # noqa: BLE001
            pass

    linhas = []
    falhas = []

    def anotar(texto):
        linhas.append(texto)
        try:
            print(texto, flush=True)
        except Exception:                               # noqa: BLE001
            pass

    anotar(f"Sistema Têmis {__version__} — autoteste")

    def conferir(rotulo, funcao):
        try:
            detalhe = funcao()
        except Exception as e:                          # noqa: BLE001
            falhas.append(rotulo)
            anotar(f"  FALHA   {rotulo}: {type(e).__name__}: {e}")
        else:
            anotar(f"  ok      {rotulo}"
                   + (f" — {detalhe}" if detalhe else ""))

    def qt():
        from PyQt6.QtWidgets import QApplication             # noqa: F401
        return "Qt disponível"

    def navegador():
        from PyQt6.QtWebEngineCore import QWebEngineProfile  # noqa: F401
        return "QtWebEngine presente (Constatação Web)"

    def ffmpeg():
        from temis.tools.video_core import ffmpeg_path, ffprobe_path
        if ffmpeg_path() is None or ffprobe_path() is None:
            raise RuntimeError("ffmpeg ou ffprobe não encontrados")
        return f"FFmpeg em {ffmpeg_path().parent}"

    def whisper():
        import os

        import ctranslate2
        from faster_whisper import WhisperModel              # noqa: F401
        from faster_whisper.utils import get_assets_path

        # Não basta importar. O detector de voz é um arquivo de modelo
        # que a biblioteca carrega de dentro do próprio pacote, e ele
        # ficou de fora do empacotamento na 1.3.0 — a Degravação
        # importava sem queixa e morria ao transcrever. Conferir o
        # arquivo aqui é o que faz esse erro aparecer no autoteste, e não
        # na mão de quem instalou.
        modelo = os.path.join(get_assets_path(), "silero_vad_v6.onnx")
        if not os.path.isfile(modelo):
            raise RuntimeError(
                f"detector de voz ausente do pacote: {modelo}")
        tamanho = os.path.getsize(modelo) // 1024
        return (f"faster-whisper pronto (CTranslate2 "
                f"{ctranslate2.__version__}), detector de voz {tamanho} KB")

    def diarizacao():
        import sherpa_onnx
        sherpa_onnx.OfflineSpeakerDiarizationConfig          # noqa: B018
        return f"sherpa-onnx {sherpa_onnx.__version__} carregado"

    def documentos():
        import fitz                                          # noqa: F401
        from PIL import Image                                # noqa: F401
        return "PyMuPDF e Pillow presentes"

    def busca():
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
        con.close()
        return f"FTS5 disponível (SQLite {sqlite3.sqlite_version})"

    def ocr():
        from temis.tools import ocr_windows
        if not ocr_windows.disponivel():
            raise RuntimeError(ocr_windows.diagnostico())
        return ocr_windows.diagnostico()

    def ferramentas():
        from temis.tools import REGISTRY
        return f"{len(REGISTRY)} ferramentas registradas"

    for rotulo, funcao in (
        ("interface", qt),
        ("navegador embutido", navegador),
        ("ffmpeg empacotado", ffmpeg),
        ("reconhecimento de fala", whisper),
        ("separação de locutores", diarizacao),
        ("leitura de documentos", documentos),
        ("índice de busca", busca),
        ("reconhecimento óptico", ocr),
        ("registro de ferramentas", ferramentas),
    ):
        conferir(rotulo, funcao)

    anotar("")
    anotar(f"{len(falhas)} verificação(ões) falharam: {', '.join(falhas)}"
           if falhas else "Instalação íntegra.")

    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    destino = Path(base) / "SistemaTemis" / "autoteste.txt"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(chr(10).join(linhas) + chr(10), encoding="utf-8")
        anotar(f"(relatório também gravado em {destino})")
    except OSError:
        pass
    return 1 if falhas else 0


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(autoteste())
    sys.exit(main())
