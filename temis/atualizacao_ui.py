"""
Tela de atualização.

A verificação corre em segundo plano e só aparece quando há o que dizer:
ao abrir o sistema, uma versão nova apresenta-se numa janela com as
novidades e três saídas — atualizar agora, depois, ou dispensar esta
versão. Nada é baixado antes do "sim".
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import __appname__, __version__, atualizacao as core
from .theme import PALETTE
from .widgets import fit_to_screen, hsep, output_button, subtext


# ─────────────────────────────────────────
#  TRABALHO EM SEGUNDO PLANO
# ─────────────────────────────────────────

class ConsultaThread(QThread):
    """Pergunta ao servidor se há versão nova."""

    achou = pyqtSignal(object)      # Atualizacao
    nada = pyqtSignal()
    falhou = pyqtSignal(str)

    def __init__(self, url: str = core.URL_MANIFESTO, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            nova = core.consultar(self._url)
        except core.ErroAtualizacao as e:
            self.falhou.emit(str(e))
            return
        if nova is None:
            self.nada.emit()
        else:
            self.achou.emit(nova)


class DownloadThread(QThread):
    """Baixa e confere o instalador."""

    progresso = pyqtSignal(int, int)
    pronto = pyqtSignal(str)
    falhou = pyqtSignal(str)

    def __init__(self, info: core.Atualizacao, parent=None):
        super().__init__(parent)
        self._info = info
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def run(self):
        try:
            caminho = core.baixar(
                self._info,
                progresso=lambda b, t: self.progresso.emit(b, t),
                cancelado=lambda: self._cancelar)
        except core.ErroAtualizacao as e:
            self.falhou.emit(str(e))
            return
        self.pronto.emit(str(caminho))


# ─────────────────────────────────────────
#  JANELA
# ─────────────────────────────────────────

class AtualizacaoDialog(QDialog):
    """Apresenta a versão nova e conduz o download."""

    def __init__(self, info: core.Atualizacao, parent=None):
        super().__init__(parent)
        self._info = info
        self._download: DownloadThread | None = None
        self._caminho = ""

        self.setWindowTitle("Atualização disponível")
        fit_to_screen(self, 560, 480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)

        titulo = QLabel(f"{__appname__} {info.versao}")
        titulo.setObjectName("heading")
        lay.addWidget(titulo)

        linha = f"Você está na versão {__version__}."
        if info.publicado:
            linha += f"  Publicada em {info.publicado}."
        if info.tamanho:
            linha += f"  Download de {info.tamanho_legivel}."
        lay.addWidget(subtext(linha, wrap=True))
        lay.addWidget(hsep())

        self._notas = QTextEdit()
        self._notas.setReadOnly(True)
        self._notas.setPlainText(info.notas or "Sem notas para esta versão.")
        self._notas.setStyleSheet(
            f"QTextEdit {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 12px; }")
        lay.addWidget(self._notas, 1)

        self._barra = QProgressBar()
        self._barra.setTextVisible(True)
        self._barra.setVisible(False)
        lay.addWidget(self._barra)

        self._estado = subtext("", wrap=True)
        lay.addWidget(self._estado)

        self._chk_dispensar = QCheckBox("Não avisar mais sobre esta versão")
        lay.addWidget(self._chk_dispensar)

        lay.addWidget(hsep())
        acoes = QHBoxLayout()
        acoes.setSpacing(8)

        self._btn_atualizar = output_button("Atualizar agora")
        self._btn_atualizar.clicked.connect(self._comecar)
        acoes.addWidget(self._btn_atualizar)

        acoes.addStretch()
        self._btn_depois = QPushButton("Agora não")
        self._btn_depois.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_depois.clicked.connect(self.reject)
        acoes.addWidget(self._btn_depois)
        lay.addLayout(acoes)

        if not core.instalado_como_programa():
            # Rodando a partir do código não há o que o instalador
            # substituir; dizer isso é melhor que falhar no meio.
            self._btn_atualizar.setEnabled(False)
            self._estado.setText(
                "Esta cópia está rodando a partir do código-fonte, e não da "
                "instalação — a atualização automática não se aplica.")

    # ── download ─────────────────────────────────
    def _comecar(self):
        self._btn_atualizar.setEnabled(False)
        self._chk_dispensar.setEnabled(False)
        self._barra.setVisible(True)
        self._barra.setRange(0, 100)
        self._barra.setValue(0)
        self._estado.setText("Baixando a atualização…")

        self._download = DownloadThread(self._info, self)
        self._download.progresso.connect(self._ao_progredir)
        self._download.pronto.connect(self._ao_baixar)
        self._download.falhou.connect(self._ao_falhar)
        self._download.start()

    def _ao_progredir(self, baixado: int, total: int):
        if total:
            self._barra.setValue(int(baixado * 100 / total))
            self._barra.setFormat(
                f"%p%  ({baixado / (1 << 20):.1f} de "
                f"{total / (1 << 20):.1f} MB)".replace(".", ","))
        else:
            self._barra.setRange(0, 0)

    def _ao_baixar(self, caminho: str):
        self._caminho = caminho
        self._barra.setValue(100)
        self._estado.setText(
            "Arquivo conferido pelo resumo SHA-256. O instalador vai abrir e "
            "o sistema será fechado para a troca dos arquivos.")
        try:
            core.instalar(Path(caminho))
        except core.ErroAtualizacao as e:
            self._ao_falhar(str(e))
            return
        # Encerra por completo: o instalador precisa substituir arquivos
        # que estão em uso enquanto a janela existir.
        QTimer.singleShot(1200, self._encerrar)

    def _encerrar(self):
        from PyQt6.QtWidgets import QApplication
        self.accept()
        QApplication.quit()

    def _ao_falhar(self, erro: str):
        self._barra.setVisible(False)
        self._estado.setText(erro)
        self._estado.setStyleSheet(f"color: {PALETTE['danger']};")
        self._btn_atualizar.setEnabled(True)
        self._chk_dispensar.setEnabled(True)

    # ── saída ────────────────────────────────────
    def reject(self):
        if self._download is not None and self._download.isRunning():
            self._download.cancelar()
            self._download.wait(3000)
        if self._chk_dispensar.isChecked():
            p = core.ler_preferencias()
            p.versao_dispensada = self._info.versao
            core.gravar_preferencias(p)
        super().reject()


# ─────────────────────────────────────────
#  ENTRADA
# ─────────────────────────────────────────

def verificar_ao_abrir(janela: QWidget, atraso_ms: int = 2500):
    """Consulta discreta, alguns segundos depois de a janela aparecer.

    Silenciosa quando não há nada ou quando a rede falha: quem abriu o
    sistema quer trabalhar, e um aviso de rede a cada abertura viraria
    ruído. Falhas só aparecem na verificação pedida pelo usuário.
    """
    prefs = core.ler_preferencias()
    if not prefs.verificar:
        return

    def consultar():
        thread = ConsultaThread(parent=janela)
        janela._thread_atualizacao = thread          # evita coleta precoce

        def ao_achar(info):
            if prefs.dispensou(info.versao):
                return
            AtualizacaoDialog(info, janela).exec()

        thread.achou.connect(ao_achar)
        thread.start()

    QTimer.singleShot(atraso_ms, consultar)


def verificar_agora(janela: QWidget, ao_terminar=None):
    """Verificação pedida pelo usuário — esta fala mesmo quando não há nada."""
    thread = ConsultaThread(parent=janela)
    janela._thread_atualizacao = thread

    def responder(mensagem: str, info=None):
        if info is not None:
            AtualizacaoDialog(info, janela).exec()
        if ao_terminar is not None:
            ao_terminar(mensagem)

    thread.achou.connect(
        lambda info: responder(f"Versão {info.versao} disponível.", info))
    thread.nada.connect(
        lambda: responder(f"O sistema está atualizado (versão {__version__})."))
    thread.falhou.connect(lambda erro: responder(erro))
    thread.start()
