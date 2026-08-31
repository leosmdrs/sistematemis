"""
Vídeo da Internet — a tela.

Um caminho só: colar o endereço, consultar, capturar e emitir a peça.

A consulta vem antes da captura de propósito. Ela mostra o que se vai
obter — título, canal, duração, disponibilidade — e faz o erro de
endereço aparecer como recado, e não como diligência perdida no meio. É
também onde a pessoa vê, antes de baixar, que o material é público.

O botão da peça nasce desligado e só acende depois de o arquivo estar em
disco: o termo cita o resumo criptográfico do que foi obtido, e antes de
existir arquivo não há bytes a resumir.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from ..theme import PALETTE
from ..widgets import (NoScrollComboBox, SidebarPanel, field_label,
                       group_title, hsep, output_button, primary_button,
                       subtext)
from . import videoweb_core as vc
from .base import ToolMeta, ToolPage
from .derivado_dialogo import TermoDerivadoDialog


class Sondador(QThread):
    """Consulta o endereço sem baixar nada."""

    pronto = pyqtSignal(object)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        self.pronto.emit(vc.sondar(self._url))


class Capturador(QThread):
    """Baixa fora da linha da interface, informando o andamento."""

    andamento = pyqtSignal(int, int)
    pronto = pyqtSignal(object)

    def __init__(self, url: str, pasta: str, qualidade: str):
        super().__init__()
        self._args = (url, pasta, qualidade)

    def run(self):
        url, pasta, qualidade = self._args
        self.pronto.emit(
            vc.baixar(url, pasta, qualidade, progresso=self.andamento.emit))


class VideoWebTool(ToolPage):
    """Captura documentada de vídeo publicado na internet."""

    meta = ToolMeta(
        key="videoweb",
        name="Vídeo da Internet",
        icon="tool_videoweb",
        tagline="Captura e documenta vídeo publicado na rede",
        description=(
            "Obtém vídeo publicado em plataforma da internet e emite o "
            "termo que o identifica: o endereço, os dados que a "
            "plataforma publicava naquele instante, a hora qualificada da "
            "captura e o resumo criptográfico do arquivo. Serve ao "
            "material que some — apagado pelo autor, removido pela "
            "plataforma, perdido com a conta encerrada. Alcança somente "
            "o que está publicamente acessível."),
        online=True,
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._publicacao = None
        self._captura = None
        self._sondador = None
        self._capturador = None

        fora = QHBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)
        fora.addWidget(self._montar_painel())
        fora.addWidget(self._montar_vista(), 1)
        self._refletir()

    # ── painel ───────────────────────────
    def _montar_painel(self) -> SidebarPanel:
        p = SidebarPanel()

        p.header.addWidget(field_label("Endereço do vídeo"))
        self._e_url = QLineEdit()
        self._e_url.setPlaceholderText("Cole aqui o endereço da publicação")
        self._e_url.returnPressed.connect(self._consultar)
        self._e_url.textChanged.connect(self._ao_mudar_url)
        p.header.addWidget(self._e_url)

        self._b_consultar = primary_button("Consultar", "globe")
        self._b_consultar.clicked.connect(self._consultar)
        p.header.addWidget(self._b_consultar)

        p.body.addWidget(group_title("Qualidade"))
        self._cb_qualidade = NoScrollComboBox()
        for chave, rotulo, _s in vc.QUALIDADES:
            self._cb_qualidade.addItem(rotulo, chave)
        self._cb_qualidade.setCurrentIndex(0)
        p.body.addWidget(self._cb_qualidade)
        p.body.addWidget(subtext(
            "As plataformas servem imagem e som em fluxos separados. O "
            "arquivo entregue é a junção local dos dois, feita nesta "
            "estação — e a peça declara isso.", wrap=True))

        p.body.addWidget(hsep())
        self._lbl_estado = QLabel("")
        self._lbl_estado.setObjectName("subtext")
        self._lbl_estado.setWordWrap(True)
        p.body.addWidget(self._lbl_estado)

        self._barra = QProgressBar()
        self._barra.setVisible(False)
        p.body.addWidget(self._barra)
        p.body.addStretch()

        self._b_capturar = output_button("Capturar", "save")
        self._b_capturar.clicked.connect(self._capturar)
        p.footer.addWidget(self._b_capturar)

        self._b_termo = output_button("Gerar termo")
        self._b_termo.setEnabled(False)
        self._b_termo.setToolTip(
            "Disponível depois da captura — a peça cita o resumo "
            "criptográfico do arquivo obtido")
        self._b_termo.clicked.connect(self._gerar_termo)
        p.footer.addWidget(self._b_termo)

        pode, recado = vc.estado()
        p.add_note(("Biblioteca de captura: " + recado) if pode else recado)
        return p

    def _montar_vista(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        self._lbl_titulo = QLabel("Nenhum endereço consultado")
        self._lbl_titulo.setWordWrap(True)
        self._lbl_titulo.setStyleSheet(
            "font-size: 17px; font-weight: 800;")
        lay.addWidget(self._lbl_titulo)

        self._lbl_dados = QLabel("")
        self._lbl_dados.setWordWrap(True)
        self._lbl_dados.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_dados.setStyleSheet("font-size: 12px;")
        lay.addWidget(self._lbl_dados)

        lay.addWidget(hsep())
        self._lbl_descricao = QLabel("")
        self._lbl_descricao.setWordWrap(True)
        self._lbl_descricao.setObjectName("subtext")
        self._lbl_descricao.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._lbl_descricao, 1)
        return w

    # ── consulta ─────────────────────────
    def _ao_mudar_url(self):
        # Endereço novo invalida o que se sabia do anterior: manter os
        # dados na tela faria a pessoa capturar um e ler o outro.
        self._publicacao = None
        self._captura = None
        self._refletir()

    def _consultar(self):
        url = self._e_url.text().strip()
        if not url:
            return
        self._lbl_estado.setText("Consultando o endereço…")
        self._b_consultar.setEnabled(False)
        self._b_capturar.setEnabled(False)

        def pronto(publicacao):
            self._b_consultar.setEnabled(True)
            if publicacao.erro:
                self._lbl_estado.setText("")
                self._lbl_titulo.setText("Não foi possível consultar")
                self._lbl_dados.setText("")
                self._lbl_descricao.setText("")
                QMessageBox.warning(self, "Não foi possível consultar",
                                    publicacao.erro)
                self._refletir()
                return
            self._publicacao = publicacao
            self._lbl_estado.setText("")
            self._mostrar(publicacao)
            self._refletir()

        self._sondador = Sondador(url)
        self._sondador.pronto.connect(pronto)
        self._sondador.start()

    def _mostrar(self, p):
        self._lbl_titulo.setText(p.titulo or "(sem título)")
        disponibilidade = {
            "public": "pública",
            "unlisted": "não listada",
        }.get(p.disponibilidade, p.disponibilidade or "—")
        cor = (PALETTE["text3"] if p.publica else PALETTE["warning"])
        linhas = [
            f"<b>Canal:</b> {p.canal or '—'}",
            f"<b>Publicado em:</b> {p.publicado_em or '—'}",
            f"<b>Duração:</b> {vc.formatar_duracao(p.duracao)}",
            f"<b>Plataforma:</b> {p.extrator or '—'}",
            f"<b>Disponibilidade:</b> "
            f"<span style='color:{cor}'>{disponibilidade}</span>",
        ]
        if p.licenca:
            linhas.append(f"<b>Licença declarada:</b> {p.licenca}")
        if p.restricao_idade:
            linhas.append(f"<b>Restrição de idade:</b> {p.restricao_idade} anos")
        self._lbl_dados.setText("<br/>".join(linhas))
        self._lbl_descricao.setText(p.descricao or "")

    # ── captura ──────────────────────────
    def _capturar(self):
        if self._publicacao is None:
            return
        alvo = self.destino_na_sessao("Vídeos", "", str(Path.home()))
        pasta = QFileDialog.getExistingDirectory(
            self, "Onde gravar o vídeo", alvo)
        if not pasta:
            return

        self._barra.setVisible(True)
        self._barra.setRange(0, 0)
        self._b_capturar.setEnabled(False)
        self._b_consultar.setEnabled(False)
        self._lbl_estado.setText("Capturando…")

        def andou(feito, total):
            if total > 0:
                self._barra.setRange(0, total)
                self._barra.setValue(feito)
                self._lbl_estado.setText(
                    f"Capturando… {100 * feito // max(total, 1)}%")

        def pronto(captura):
            self._barra.setVisible(False)
            self._b_consultar.setEnabled(True)
            if captura.erro:
                self._lbl_estado.setText("")
                QMessageBox.warning(self, "A captura não se completou",
                                    captura.erro)
                self._refletir()
                return
            self._captura = captura
            self._lbl_estado.setText(
                f"Obtido: {captura.nome}\nSHA-256 {captura.sha256[:16]}…")
            self._refletir()
            QMessageBox.information(
                self, "Vídeo capturado",
                f"Arquivo gravado em:\n{captura.arquivo}\n\n"
                f"SHA-256: {captura.sha256}\n\n"
                "O termo já pode ser gerado — ele traz o endereço, os "
                "dados que a plataforma publicava, a hora da captura e "
                "este resumo criptográfico.")

        self._capturador = Capturador(
            self._e_url.text().strip(), pasta,
            self._cb_qualidade.currentData() or "melhor")
        self._capturador.andamento.connect(andou)
        self._capturador.pronto.connect(pronto)
        self._capturador.start()

    # ── estado ───────────────────────────
    def _refletir(self):
        pode, _recado = vc.estado()
        self._b_consultar.setEnabled(pode and bool(self._e_url.text().strip()))
        self._b_capturar.setEnabled(pode and self._publicacao is not None)
        self._b_termo.setEnabled(self._captura is not None)
        if self._publicacao is None:
            self._lbl_titulo.setText("Nenhum endereço consultado")
            self._lbl_dados.setText("")
            self._lbl_descricao.setText("")

    # ── a peça ───────────────────────────
    def _gerar_termo(self):
        if self._captura is None:
            return
        TermoDerivadoDialog(vc.montar_termo(self._captura), self,
                            modulo=vc).exec()

    # ── ciclo de vida ────────────────────
    def shutdown(self):
        for t in (self._sondador, self._capturador):
            if t is not None and t.isRunning():
                t.wait(5000)
