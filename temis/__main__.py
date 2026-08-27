"""Ponto de entrada do Sistema Têmis."""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from . import __appname__, __author__, __version__
from .icons import app_icon
from .shell import TemisWindow


# A interface **não** aplica fator de escala próprio, e isto é decisão
# medida, não esquecimento.
#
# Houve aqui um `QT_SCALE_FACTOR = "0.85"`, para deixar tudo 15% menor
# sem acertar medida por medida, e o comentário de então afirmava que o
# texto não perdia nitidez com isso. Perdia. O Qt calcula as métricas em
# pixels lógicos **inteiros** e só depois multiplica pelo fator, de modo
# que o resultado cai entre pixels e as hastes das letras são desenhadas
# em cima da fronteira. Medido nesta máquina:
#
#     fonte    px reais a 1,0    px reais a 0,85
#      9 pt         16,00             13,60
#     10 pt         17,00             14,45
#     11 pt         20,00             17,00
#     13 pt         22,00             18,70
#
# E a tipografia do tema, que é declarada em pixel: 13 px viravam 11,05;
# 12 px, 10,20; 11 px, 9,35; 10 px, 8,50.
#
# O 11 pt é o único que dá inteiro (20 × 0,85 = 17), e era o único que
# saía nítido — daí a impressão de que o defeito dependia do tamanho da
# fonte. Dependia de o produto dar inteiro, o que é outra coisa.
#
# **Não existe fator fracionário nítido**, porque a métrica de origem é
# sempre inteira. Para diminuir a interface, o caminho é baixar as
# medidas do tema, que são em pixel e chegam inteiras à tela.
#
# Quem quiser escalar assim mesmo continua podendo: o Qt lê
# QT_SCALE_FACTOR do ambiente, e nada aqui atrapalha.


def _preparar_webengine():
    """Liga o contexto de OpenGL compartilhado, exigido pelo QtWebEngine.

    Precisa valer **antes** de existir QApplication: ligado depois, o
    componente de navegação da Constatação Web não carrega.
    """
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


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

    _preparar_webengine()

    app = QApplication(sys.argv)
    app.setApplicationName(__appname__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__author__)
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
