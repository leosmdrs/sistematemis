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
        import ctranslate2
        from faster_whisper import WhisperModel              # noqa: F401
        return f"faster-whisper pronto (CTranslate2 {ctranslate2.__version__})"

    def documentos():
        import fitz                                          # noqa: F401
        from PIL import Image                                # noqa: F401
        return "PyMuPDF e Pillow presentes"

    def ferramentas():
        from temis.tools import REGISTRY
        return f"{len(REGISTRY)} ferramentas registradas"

    for rotulo, funcao in (
        ("interface", qt),
        ("navegador embutido", navegador),
        ("ffmpeg empacotado", ffmpeg),
        ("reconhecimento de fala", whisper),
        ("leitura de documentos", documentos),
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
