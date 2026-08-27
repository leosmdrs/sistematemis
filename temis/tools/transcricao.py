"""
Degravação — transcreve oitivas e gravações, na própria máquina.

Disposição das demais: painel à esquerda com o arquivo e os controles,
barra no alto, transcrição à direita. Cada trecho é uma linha editável,
com a marca de tempo e o rótulo de quem fala.

O reconhecimento automático é meio de trabalho, não fonte de fé: o texto
sai para revisão, e o termo diz isso com todas as letras.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QFrame, QSizePolicy, QMessageBox, QDialog, QTextEdit, QLineEdit,
    QGridLayout, QProgressBar, QScrollArea, QCheckBox, QComboBox,
)

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (preparar_procedimento, ler_procedimento,
    
    Carregando, NoScrollComboBox, SidebarPanel, field_label, fit_to_screen,
    hsep, output_button, primary_button, subtext, TOOLBAR_HEIGHT,
)
from .base import ToolPage, ToolMeta
from . import transcricao_core as core


META = ToolMeta(
    key="transcricao",
    name="Degravação",
    icon="tool_transcricao",
    tagline="Transcreve oitivas e gravações",
    description=(
        "Transcreve áudio e vídeo com reconhecimento de fala executado na "
        "própria máquina — nenhum trecho é enviado a serviço externo. "
        "Separa automaticamente quem fala, na cronologia da gravação, e "
        "basta nomear cada voz uma vez. Emite termo de degravação com o "
        "resumo SHA-256 da mídia de origem."
    ),
)

FILTRO = (
    "Áudio e vídeo (*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.wma *.mp4 *.mov "
    "*.avi *.mkv *.wmv *.m4v *.webm);;Todos os arquivos (*)"
)


# ─────────────────────────────────────────
#  TRABALHO EM SEGUNDO PLANO
# ─────────────────────────────────────────

class BaixarModeloThread(QThread):
    """Traz o modelo na primeira vez que ele é usado."""

    pronto = pyqtSignal()
    falhou = pyqtSignal(str)

    def __init__(self, chave: str, parent=None):
        super().__init__(parent)
        self._chave = chave

    def run(self):
        try:
            core.baixar_modelo(self._chave)
        except Exception as e:                          # noqa: BLE001
            self.falhou.emit(
                f"Não foi possível baixar o modelo: {e}\n\n"
                "Se esta rede bloqueia o acesso, o modelo pode ser copiado "
                f"manualmente para:\n{core.pasta_do_modelo(self._chave)}")
            return
        self.pronto.emit()


class BaixarDiarizacaoThread(QThread):
    """Traz os modelos que separam quem fala."""

    pronto = pyqtSignal()
    falhou = pyqtSignal(str)

    def run(self):
        try:
            core.baixar_diarizacao()
        except Exception as e:                          # noqa: BLE001
            self.falhou.emit(
                f"Não foi possível baixar a separação de vozes: {e}\n\n"
                "A transcrição funciona sem ela; desmarque “Separar quem "
                "fala” para seguir.")
            return
        self.pronto.emit()


class TranscreverThread(QThread):
    """Reconhece a fala fora da interface — pode levar muitos minutos."""

    progresso = pyqtSignal(float, float)
    pronto = pyqtSignal(list)
    falhou = pyqtSignal(str)

    etapa = pyqtSignal(str)

    def __init__(self, audio, chave: str, idioma: str, vozes: bool = False,
                 pessoas: int = 0, parent=None):
        super().__init__(parent)
        self._audio = audio
        self._chave = chave
        self._idioma = idioma
        self._vozes = vozes
        self._pessoas = pessoas
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def run(self):
        try:
            self.etapa.emit("Transcrevendo… pode levar alguns minutos.")
            trechos = core.transcrever(
                self._audio, self._chave, self._idioma,
                progresso=lambda p, t: self.progresso.emit(p, t),
                cancelado=lambda: self._cancelar)
            if self._vozes and trechos and not self._cancelar:
                self.etapa.emit("Separando quem fala…")
                falas = core.separar_vozes(self._audio, self._pessoas)
                trechos = core.atribuir_vozes(trechos, falas)
        except core.ErroTranscricao as e:
            self.falhou.emit(str(e))
            return
        self.pronto.emit(trechos)


# ─────────────────────────────────────────
#  LINHA DE TRECHO
# ─────────────────────────────────────────

class TrechoWidget(QFrame):
    """Uma fala: marca de tempo, quem falou e o texto, editável."""

    alterado = pyqtSignal()

    def __init__(self, trecho: core.Trecho, parent=None):
        super().__init__(parent)
        self.trecho = trecho
        self.setStyleSheet("QFrame { background: transparent; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        marca = QLabel(trecho.marca)
        marca.setFixedWidth(64)
        marca.setAlignment(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignTop)
        marca.setStyleSheet(
            f"color: {PALETTE['text3']}; font-family: Consolas; "
            "padding-top: 9px;")
        lay.addWidget(marca)

        # O nome de quem fala é dado uma vez, no painel de vozes — repetir
        # um seletor em cada linha faria o encarregado responder a mesma
        # pergunta duzentas vezes numa oitiva de uma hora.
        self._cb = QLineEdit(trecho.locutor)
        self._cb.setFixedWidth(126)
        self._cb.setReadOnly(True)
        self._cb.setToolTip(
            "Quem fala neste trecho. O nome vem do painel de vozes, no alto.")
        self._cb.setStyleSheet(
            f"QLineEdit {{ background: {PALETTE['bg']}; "
            f"color: {PALETTE['gold']}; border: 1px solid "
            f"{PALETTE['border']}; border-radius: 5px; padding: 6px 8px; }}")
        lay.addWidget(self._cb, 0, Qt.AlignmentFlag.AlignTop)

        self.editor = QTextEdit()
        self.editor.setPlainText(trecho.texto)
        self.editor.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 5px; "
            "padding: 6px 9px; }"
            f"QTextEdit:focus {{ border: 1px solid {PALETTE['gold']}; }}")
        self.editor.setFont(QFont("Segoe UI", 10))
        self.editor.document().documentLayout().documentSizeChanged.connect(
            self._ajustar)
        self.editor.textChanged.connect(self._ao_editar)
        self.editor.setFixedHeight(40)
        lay.addWidget(self.editor, 1, Qt.AlignmentFlag.AlignTop)

    def _ajustar(self, *_a):
        alt = int(self.editor.document().size().height()) + 14
        self.editor.setFixedHeight(max(40, alt))

    def _ao_editar(self):
        self.trecho.texto = self.editor.toPlainText()
        self.alterado.emit()

    def aplicar_locutor(self, nome: str):
        self.trecho.locutor = nome
        self._cb.setText(nome)


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """O termo de degravação, editável antes de salvar."""

    def __init__(self, deg: core.Degravacao, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Degravação")
        self._deg = deg
        fit_to_screen(self, 940, 800)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        titulo = QLabel("Termo de Degravação")
        titulo.setObjectName("heading")
        lay.addWidget(titulo)
        lay.addWidget(subtext(
            "Confira o texto antes de salvar. A fidelidade da transcrição é "
            "sua, não do reconhecimento automático.", wrap=True))
        lay.addWidget(self._build_form())
        lay.addWidget(hsep())

        self._view = QTextEdit()
        self._view.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 26px; }")
        lay.addWidget(self._view, 1)
        lay.addWidget(hsep())

        acoes = QWidget()
        acoes.setSizePolicy(QSizePolicy.Policy.Preferred,
                            QSizePolicy.Policy.Fixed)
        linha = QHBoxLayout(acoes)
        linha.setContentsMargins(0, 8, 0, 0)
        linha.setSpacing(8)

        pdf = output_button("Salvar PDF")
        pdf.clicked.connect(self._salvar_pdf)
        linha.addWidget(pdf)

        htm = QPushButton("  Salvar HTML")
        htm.setIcon(draw_icon("save", 15, PALETTE["text"]))
        htm.setToolTip("Arquivo HTML, para importar no SEI")
        htm.setCursor(Qt.CursorShape.PointingHandCursor)
        htm.clicked.connect(self._salvar_html)
        linha.addWidget(htm)

        self._chk_marcas = QCheckBox("Marcas de tempo")
        self._chk_marcas.setChecked(True)
        self._chk_marcas.toggled.connect(self._remontar)
        linha.addWidget(self._chk_marcas)

        self._aviso = QLabel("")
        self._aviso.setObjectName("badge_ok")
        linha.addWidget(self._aviso)

        linha.addStretch()
        fechar = QPushButton("Fechar")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)

        lay.addWidget(acoes)
        self._remontar()
        # Por último, e não junto do formulário: preencher um campo
        # dispara `textChanged`, que remonta a prévia do termo — e a
        # prévia só existe depois. Chamado antes, isto derrubava o
        # programa inteiro, sem mensagem: exceção dentro de sinal do Qt
        # não vira erro em Python, vira encerramento do processo.
        #
        # Só os campos vazios são tocados. O que veio do termo anterior,
        # ou o que a pessoa escrever depois, vale mais que o perfil: ele
        # poupa digitação, não decide quem assina.
        perfil.aplicar(self)

    def _build_form(self) -> QWidget:
        caixa = QWidget()
        grade = QGridLayout(caixa)
        grade.setContentsMargins(0, 4, 0, 4)
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(4)

        self._in_nome = QLineEdit()
        self._in_nome.setPlaceholderText("Ex.: João da Silva")
        self._in_matricula = QLineEdit()
        self._in_matricula.setPlaceholderText("Ex.: 1234567")
        self._in_lotacao = QLineEdit()
        self._in_lotacao.setPlaceholderText("Ex.: CGCOR - PRF/DF")
        for coluna, (rotulo, campo) in enumerate((
            ("Nome do servidor", self._in_nome),
            ("Matrícula", self._in_matricula),
            ("Lotação", self._in_lotacao),
        )):
            grade.addWidget(field_label(rotulo), 0, coluna)
            grade.addWidget(campo, 1, coluna)
            campo.textChanged.connect(self._remontar)

        self._cb_tipo = NoScrollComboBox()

        preparar_procedimento(self._cb_tipo)
        self._cb_tipo.currentIndexChanged.connect(self._remontar)
        self._in_processo = QLineEdit()
        self._in_processo.setPlaceholderText("Ex.: 08650.000123/2026-11")
        self._in_processo.textChanged.connect(self._remontar)
        grade.addWidget(field_label("Procedimento"), 2, 0)
        grade.addWidget(self._cb_tipo, 3, 0)
        grade.addWidget(field_label("Número do processo"), 2, 1)
        grade.addWidget(self._in_processo, 3, 1)

        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 1)
        grade.setColumnStretch(2, 2)
        grade.setRowMinimumHeight(2, 12)
        return caixa

    def _remontar(self):
        self._view.setHtml(core.build_html(
            self._deg,
            core.Declarante(nome=self._in_nome.text().strip(),
                            matricula=self._in_matricula.text().strip(),
                            lotacao=self._in_lotacao.text().strip()),
            core.Procedimento(tipo=ler_procedimento(self._cb_tipo),
                              numero=self._in_processo.text().strip()),
            com_marcas=self._chk_marcas.isChecked()))

    def _base(self) -> str:
        return f"degravacao-{Path(self._deg.origem).stem or 'midia'}"

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo", f"{self._base()}.pdf",
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            doc = self._view.document().clone()
            doc.setDefaultFont(QFont("Segoe UI", 10))
            imprimir_documento(doc, preparar_escritor(
                caminho, "Termo de Degravação"))
            self._aviso.setText("✓ PDF salvo")
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gerar o PDF:\n{e}")

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML", f"{self._base()}.html",
            "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            Path(caminho).write_text(
                documento_html(limpar_para_sei(self._view.toHtml()),
                               "Termo de Degravação"),
                encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar:\n{e}")


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class TranscricaoTool(ToolPage):
    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._deg = core.Degravacao()
        self._audio = None
        self._tmp = Path(tempfile.mkdtemp(prefix="temis-degrav-"))
        self._thread = None
        self._baixando = None
        self._widgets: list[TrechoWidget] = []
        self._build_ui()

    # ── montagem ─────────────────────────────────
    def _build_ui(self):
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._build_sidebar())

        principal = QWidget()
        coluna = QVBoxLayout(principal)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self._build_barra())

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QFrame.Shape.NoFrame)
        corpo = QWidget()
        corpo.setStyleSheet(f"background: {PALETTE['bg']};")
        self._pilha = QVBoxLayout(corpo)
        self._pilha.setContentsMargins(16, 14, 18, 14)
        self._pilha.setSpacing(0)
        self._pilha.addStretch()
        self._area.setWidget(corpo)
        self._corpo = corpo

        self._vazio = QLabel(
            "Abra um áudio ou vídeo e clique em Transcrever.")
        self._vazio.setObjectName("subtext")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)

        coluna.addWidget(self._vazio, 1)
        coluna.addWidget(self._area, 1)
        self._area.setVisible(False)
        raiz.addWidget(principal, 1)

    def _build_barra(self) -> QFrame:
        barra = QFrame()
        barra.setObjectName("toolbar_frame")
        barra.setFixedHeight(TOOLBAR_HEIGHT)
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)

        self._lbl_vozes = QLabel("Vozes:")
        self._lbl_vozes.setObjectName("subtext")
        lay.addWidget(self._lbl_vozes)

        # Um campo por voz encontrada: nomear aqui vale para todas as falas
        # daquela pessoa, na gravação inteira.
        self._campos_voz: dict[int, QLineEdit] = {}
        self._caixa_vozes = QHBoxLayout()
        self._caixa_vozes.setSpacing(6)
        lay.addLayout(self._caixa_vozes)

        lay.addStretch()
        self._lbl_resumo = subtext("—")
        lay.addWidget(self._lbl_resumo)
        return barra

    def _build_sidebar(self) -> SidebarPanel:
        painel = SidebarPanel()

        self._btn_abrir = primary_button("Abrir mídia…", "open")
        self._btn_abrir.clicked.connect(self._abrir)
        painel.header.addWidget(self._btn_abrir)

        self._lbl_arquivo = subtext("Nenhum arquivo aberto", wrap=True)
        painel.header.addWidget(self._lbl_arquivo)

        painel.body.addWidget(field_label("Qualidade do reconhecimento"))
        self._cb_modelo = NoScrollComboBox()
        for m in core.MODELOS:
            self._cb_modelo.addItem(
                f"{m.rotulo} · {m.tamanho_mb} MB", m.chave)
        self._cb_modelo.setCurrentIndex(
            next(i for i, m in enumerate(core.MODELOS)
                 if m.chave == core.MODELO_PADRAO))
        self._cb_modelo.currentIndexChanged.connect(self._descrever_modelo)
        painel.body.addWidget(self._cb_modelo)

        self._lbl_modelo = subtext("", wrap=True)
        painel.body.addWidget(self._lbl_modelo)

        self._chk_vozes = QCheckBox("Separar quem fala")
        self._chk_vozes.setChecked(True)
        self._chk_vozes.setToolTip(
            "Divide a gravação por voz e marca cada fala. O resultado é um "
            "ponto de partida: confira antes de assinar.")
        self._chk_vozes.toggled.connect(
            lambda ligado: self._cb_pessoas.setEnabled(ligado))
        painel.body.addWidget(self._chk_vozes)

        self._cb_pessoas = NoScrollComboBox()
        self._cb_pessoas.addItem("Descobrir sozinho", 0)
        for n in range(2, 7):
            self._cb_pessoas.addItem(f"{n} pessoas", n)
        self._cb_pessoas.setToolTip(
            "Informar quantas pessoas falam melhora bastante o resultado")
        painel.body.addWidget(self._cb_pessoas)

        self._btn_transcrever = output_button("Transcrever")
        self._btn_transcrever.clicked.connect(self._transcrever)
        self._btn_transcrever.setEnabled(False)
        painel.body.addWidget(self._btn_transcrever)

        self._barra = QProgressBar()
        self._barra.setTextVisible(True)
        self._barra.setVisible(False)
        painel.body.addWidget(self._barra)

        self._lbl_estado = subtext("", wrap=True)
        painel.body.addWidget(self._lbl_estado)

        self._btn_cancelar = QPushButton("Cancelar")
        self._btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancelar.clicked.connect(self._cancelar)
        self._btn_cancelar.setVisible(False)
        painel.body.addWidget(self._btn_cancelar)

        painel.body.addStretch()

        self._btn_copiar = QPushButton("  Copiar transcrição")
        self._btn_copiar.setIcon(draw_icon("note", 15, PALETTE["text"]))
        self._btn_copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copiar.clicked.connect(self._copiar)
        self._btn_copiar.setEnabled(False)
        painel.body.addWidget(self._btn_copiar)

        self._btn_termo = output_button("Gerar termo")
        self._btn_termo.clicked.connect(self._gerar_termo)
        self._btn_termo.setEnabled(False)
        painel.footer.addWidget(self._btn_termo)
        painel.add_note(
            "O áudio não sai desta máquina. Só o modelo é baixado, uma vez.")

        self._descrever_modelo()
        return painel

    # ── modelo ───────────────────────────────────
    def _modelo_atual(self) -> str:
        return self._cb_modelo.currentData()

    def _descrever_modelo(self):
        m = core.modelo(self._modelo_atual())
        estado = ("já baixado" if core.baixado(m.chave)
                  else f"será baixado na primeira vez ({m.tamanho_mb} MB)")
        self._lbl_modelo.setText(f"{m.nota}  ({estado})")

    # ── abertura ─────────────────────────────────
    def _abrir(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir áudio ou vídeo", "", FILTRO)
        if not caminho:
            return
        self._lbl_estado.setText("Extraindo o áudio…")
        QGuiApplication.processEvents()
        try:
            wav = core.extrair_audio(caminho, self._tmp / "audio.wav")
            self._audio = core.carregar_audio(wav)
            duracao = core.duracao(wav)
        except core.ErroTranscricao as e:
            self._lbl_estado.setText("")
            QMessageBox.critical(self, "Não foi possível abrir", str(e))
            return

        from .hash_core import sha256_file
        self._deg = core.Degravacao(
            origem=caminho, duracao=duracao, modelo=self._modelo_atual())
        try:
            self._deg.sha256 = sha256_file(caminho)
        except OSError:
            pass

        self._limpar_trechos()
        self._lbl_arquivo.setText(
            f"{Path(caminho).name}\n{core.hms(duracao)}")
        self._lbl_estado.setText("")
        self._btn_transcrever.setEnabled(True)
        self._btn_termo.setEnabled(False)
        self._btn_copiar.setEnabled(False)
        self.status_msg.emit(
            f"{Path(caminho).name} · {core.hms(duracao)} de áudio")

    # ── transcrição ──────────────────────────────
    def _transcrever(self):
        if self._audio is None:
            return
        chave = self._modelo_atual()
        if not core.baixado(chave):
            self._baixar_modelo(chave)
            return
        if self._chk_vozes.isChecked() and not core.diarizacao_baixada():
            self._baixar_diarizacao(chave)
            return
        self._iniciar_reconhecimento(chave)

    def _baixar_modelo(self, chave: str):
        m = core.modelo(chave)
        if QMessageBox.question(
            self, "Baixar modelo",
            f"O modelo “{m.rotulo}” ainda não está nesta máquina e precisa "
            f"ser baixado ({m.tamanho_mb} MB). Isso acontece uma única vez.\n\n"
            "O áudio não é enviado a lugar nenhum — apenas o modelo é "
            "recebido.\n\nBaixar agora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) != QMessageBox.StandardButton.Yes:
            return

        self._btn_transcrever.setEnabled(False)
        self._barra.setVisible(True)
        self._barra.setRange(0, m.tamanho_mb)
        self._lbl_estado.setText("Baixando o modelo…")

        # O progresso vem de olhar a pasta crescer: é robusto e não depende
        # de espiar as entranhas da biblioteca de download.
        self._relogio = QTimer(self)
        self._relogio.timeout.connect(
            lambda: self._barra.setValue(
                min(m.tamanho_mb, core.tamanho_em_disco(chave) // (1 << 20))))
        self._relogio.start(500)

        self._baixando = BaixarModeloThread(chave, self)
        self._baixando.pronto.connect(
            lambda: self._modelo_pronto(chave))
        self._baixando.falhou.connect(self._falhou)
        self._baixando.start()

    def _modelo_pronto(self, chave: str):
        self._relogio.stop()
        self._descrever_modelo()
        if self._chk_vozes.isChecked() and not core.diarizacao_baixada():
            self._baixar_diarizacao(chave)
            return
        self._iniciar_reconhecimento(chave)

    def _baixar_diarizacao(self, chave: str):
        if QMessageBox.question(
            self, "Baixar separação de vozes",
            f"A separação de quem fala usa dois modelos que ainda não estão "
            f"nesta máquina ({core.DIARIZACAO_MB} MB). Isso acontece uma "
            "única vez.\n\nBaixar agora?\n\nRespondendo “Não”, a "
            "transcrição segue sem separar os interlocutores.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) != QMessageBox.StandardButton.Yes:
            self._chk_vozes.setChecked(False)
            self._iniciar_reconhecimento(chave)
            return

        self._btn_transcrever.setEnabled(False)
        self._barra.setVisible(True)
        self._barra.setRange(0, 0)
        self._lbl_estado.setText("Baixando os modelos de voz…")

        self._baixando = BaixarDiarizacaoThread(self)
        self._baixando.pronto.connect(
            lambda: self._iniciar_reconhecimento(chave))
        self._baixando.falhou.connect(self._falhou)
        self._baixando.start()

    def _iniciar_reconhecimento(self, chave: str):
        self._deg.modelo = chave
        self._btn_transcrever.setEnabled(False)
        self._btn_abrir.setEnabled(False)
        self._btn_cancelar.setVisible(True)
        self._barra.setVisible(True)
        self._barra.setRange(0, 100)
        self._barra.setValue(0)
        self._lbl_estado.setText("Transcrevendo… pode levar alguns minutos.")

        separar = self._chk_vozes.isChecked() and core.diarizacao_baixada()
        self._deg.separou_vozes = separar
        self._thread = TranscreverThread(
            self._audio, chave, self._deg.idioma, separar,
            self._cb_pessoas.currentData() or 0, self)
        self._thread.etapa.connect(self._lbl_estado.setText)
        self._thread.progresso.connect(self._ao_progredir)
        self._thread.pronto.connect(self._ao_transcrever)
        self._thread.falhou.connect(self._falhou)
        self._thread.start()

    def _ao_progredir(self, pronto: float, total: float):
        if total:
            self._barra.setValue(int(min(100, pronto * 100 / total)))
            self._barra.setFormat(
                f"%p%  ({core.hms(pronto)} de {core.hms(total)})")

    def _ao_transcrever(self, trechos: list):
        self._deg.trechos = trechos
        self._deg.nomes = {}
        # Cada trecho já nasce com "Locutor 1", "Locutor 2": o encarregado
        # troca pelo nome real no painel do alto, uma vez por voz.
        for t in trechos:
            if t.voz >= 0:
                t.locutor = self._deg.nome_da_voz(t.voz)
        self._encerrar_trabalho()
        self._montar_trechos()
        self._btn_termo.setEnabled(bool(trechos))
        self._btn_copiar.setEnabled(bool(trechos))
        vozes = len(self._deg.vozes)
        self.status_msg.emit(
            f"{len(trechos)} trecho(s) · {self._deg.palavras} palavra(s)"
            + (f" · {vozes} voz(es) separada(s)" if vozes else "")
            + ". Confira o texto antes de gerar o termo.")

    def _falhou(self, erro: str):
        self._encerrar_trabalho()
        QMessageBox.warning(self, "Não foi possível concluir", erro)

    def _encerrar_trabalho(self):
        if getattr(self, "_relogio", None) is not None:
            self._relogio.stop()
        self._barra.setVisible(False)
        self._btn_cancelar.setVisible(False)
        self._btn_transcrever.setEnabled(self._audio is not None)
        self._btn_abrir.setEnabled(True)
        self._lbl_estado.setText("")

    def _cancelar(self):
        if self._thread is not None and self._thread.isRunning():
            self._thread.cancelar()
            self._lbl_estado.setText("Encerrando…")

    # ── trechos na tela ──────────────────────────
    def _limpar_trechos(self):
        for w in self._widgets:
            self._pilha.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._widgets = []
        self._area.setVisible(False)
        self._vazio.setVisible(True)
        self._lbl_resumo.setText("—")

    def _montar_trechos(self):
        self._limpar_trechos()
        self._corpo.setUpdatesEnabled(False)
        self._corpo.hide()
        try:
            for i, t in enumerate(self._deg.trechos):
                w = TrechoWidget(t)
                w.alterado.connect(self._atualizar_resumo)
                self._pilha.insertWidget(i, w)
                self._widgets.append(w)
        finally:
            self._corpo.show()
            self._corpo.setUpdatesEnabled(True)
        self._vazio.setVisible(False)
        self._area.setVisible(True)
        self._montar_vozes()
        self._atualizar_resumo()

    def _montar_vozes(self):
        """Um campo de nome para cada voz que a separação encontrou."""
        while self._caixa_vozes.count():
            item = self._caixa_vozes.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._campos_voz = {}

        vozes = self._deg.vozes
        self._lbl_vozes.setVisible(bool(vozes))
        for voz in vozes:
            campo = QLineEdit()
            campo.setFixedWidth(132)
            campo.setPlaceholderText(self._deg.nome_da_voz(voz))
            campo.setText(self._deg.nomes.get(voz, ""))
            campo.setToolTip(
                f"Nome de quem fala nos trechos marcados como "
                f"“{self._deg.nome_da_voz(voz)}”")
            campo.textChanged.connect(
                lambda texto, v=voz: self._renomear_voz(v, texto))
            self._caixa_vozes.addWidget(campo)
            self._campos_voz[voz] = campo

    def _renomear_voz(self, voz: int, texto: str):
        self._deg.renomear(voz, texto)
        for w in self._widgets:
            if w.trecho.voz == voz:
                w.aplicar_locutor(w.trecho.locutor)
        self._atualizar_resumo()

    def _atualizar_resumo(self):
        vozes = len(self._deg.vozes)
        self._lbl_resumo.setText(
            f"{len(self._deg.trechos)} trechos · {self._deg.palavras} "
            f"palavras" + (f" · {vozes} voz(es)" if vozes else ""))

    def _copiar(self):
        linhas = []
        for t in self._deg.trechos:
            quem = f"{t.locutor}: " if t.locutor else ""
            linhas.append(f"[{t.marca}] {quem}{t.texto.strip()}")
        QGuiApplication.clipboard().setText("\n".join(linhas))
        self.status_msg.emit("Transcrição copiada.")

    def _gerar_termo(self):
        if self._deg.trechos:
            TermoDialog(self._deg, self).exec()

    # ── contrato do casco ────────────────────────
    def shutdown(self):
        for t in (self._thread, self._baixando):
            if t is not None and t.isRunning():
                if hasattr(t, "cancelar"):
                    t.cancelar()
                t.wait(4000)
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)
