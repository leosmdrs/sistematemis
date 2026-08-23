"""Ponto de entrada do Sistema Têmis."""

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from . import __appname__, __version__
from .icons import app_icon
from .shell import TemisWindow


#: Escala da interface inteira. 1.0 é o tamanho de projeto; 0.85 deixa
#: tudo — fontes, botões, painéis, ícones — 15% menor de uma vez, sem
#: precisar acertar medida por medida. O Qt aplica sobre a escala do
#: sistema e continua desenhando na resolução real do monitor, então o
#: texto não perde nitidez.
ESCALA_INTERFACE = "0.85"


def _preparar_escala():
    """Reduz a interface como um todo, respeitando ajuste do usuário."""
    os.environ.setdefault("QT_SCALE_FACTOR", ESCALA_INTERFACE)


def main() -> int:
    # No Windows, informar o AppUserModelID faz a barra de tarefas usar o
    # ícone do programa em vez do ícone genérico do interpretador Python.
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "PRF.Corregedoria.SistemaTemis")
        except Exception:
            pass

    _preparar_escala()

    app = QApplication(sys.argv)
    app.setApplicationName(__appname__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Polícia Rodoviária Federal")
    app.setWindowIcon(app_icon())

    win = TemisWindow()
    win.show()

    # Depois de a janela aparecer: a consulta é discreta e não atrasa a
    # abertura. Silenciosa quando não há novidade ou quando a rede falha.
    from .atualizacao_ui import verificar_ao_abrir
    verificar_ao_abrir(win)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
