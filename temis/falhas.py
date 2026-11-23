"""
Erro que ninguém tratou não derruba o programa.

Uma exceção de Python levantada dentro de um método chamado pelo Qt — o
clique de um botão, o fim de uma tarefa — não vira erro: sem um tratador
instalado, o Qt encerra o processo na hora, sem mensagem. Um descuido em
qualquer tela fechava o sistema inteiro, com a gravação de tela em curso
noutra ferramenta e o registro da sessão por fechar.

O tratador daqui faz duas coisas: grava o erro, com a pilha, no arquivo
de falhas da estação; e mostra à pessoa uma mensagem dizendo que a ação
falhou e que o programa continua aberto. Não finge que nada houve — a
ação que falhou não foi feita, e a mensagem diz isso.

Não é licença para deixar exceção solta: é a rede sob o trapézio. Onde
se sabe que uma operação pode falhar — gravar em disco, abrir arquivo —
o tratamento continua sendo o da própria tela, com mensagem própria.
"""

from __future__ import annotations

import datetime
import os
import sys
import threading
import traceback
from pathlib import Path

_avisador = None
_mostrando = False


def arquivo_de_falhas() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "SistemaTemis" / "falhas.txt"


def registrar(tipo, valor, pilha) -> str:
    """Grava a falha em disco e devolve o texto gravado."""
    texto = "".join(traceback.format_exception(tipo, valor, pilha))
    try:
        destino = arquivo_de_falhas()
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            agora = datetime.datetime.now().astimezone().isoformat(
                timespec="seconds")
            f.write(f"\n=== {agora} ===\n{texto}")
    except OSError:
        pass
    return texto


def _mostrar(resumo: str):
    """Avisa a pessoa. Uma janela por vez: falha em cascata não empilha."""
    global _mostrando
    if _mostrando:
        return
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        return
    if QApplication.instance() is None:
        return
    _mostrando = True
    try:
        QMessageBox.critical(
            QApplication.activeWindow(), "A ação não foi concluída",
            "Ocorreu um erro que o sistema não esperava, e a ação que "
            "estava em andamento não foi concluída.\n\n"
            f"{resumo}\n\n"
            "O programa continua aberto e as demais ferramentas seguem "
            "funcionando. O detalhe técnico foi gravado em:\n"
            f"{arquivo_de_falhas()}")
    except Exception:                                       # noqa: BLE001
        pass
    finally:
        _mostrando = False


def tratar(tipo, valor, pilha):
    """O tratador instalado. Nunca levanta."""
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, pilha)
        return
    try:
        registrar(tipo, valor, pilha)
        resumo = f"{tipo.__name__}: {valor}"[:400]
        if _avisador is not None:
            # Por sinal: a falha pode vir de outra thread, e janela só se
            # abre na thread da interface.
            _avisador.pedir.emit(resumo)
        else:
            sys.__excepthook__(tipo, valor, pilha)
    except Exception:                                       # noqa: BLE001
        pass


def instalar():
    """Instala o tratador. Chamado uma vez, com a aplicação já criada."""
    global _avisador
    from PyQt6.QtCore import QObject, Qt, pyqtSignal

    class _Avisador(QObject):
        pedir = pyqtSignal(str)

    _avisador = _Avisador()
    _avisador.pedir.connect(_mostrar, Qt.ConnectionType.QueuedConnection)
    sys.excepthook = tratar
    threading.excepthook = lambda a: tratar(
        a.exc_type, a.exc_value, a.exc_traceback)
