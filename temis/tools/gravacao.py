"""
Gravação de Tela — registro audiovisual de diligência em meio eletrônico.

Serve a qualquer tela do Windows: sistema legado, aplicativo de mesa,
página que não abre no navegador embutido. Registra o que se fez, com a
identificação do processo, do operador e da estação impressa no próprio
vídeo, e encerra calculando o resumo criptográfico.

A janela some enquanto grava
----------------------------

A primeira versão disto era inutilizável: a tela do Têmis aparecia no
vídeo e, minimizada, não havia como encerrar a gravação. Ao iniciar, a
janela principal é recolhida e fica um painel pequeno, acima de tudo,
com o tempo decorrido e o botão de encerrar — arrastável, para sair da
frente do que se está registrando.

Que ele apareça no vídeo é proposital: mostra que a gravação estava em
curso e por quanto tempo, e não esconde nada do que se registrou, porque
ocupa um canto e pode ser movido.
"""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QDate, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PyQt6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (preparar_procedimento, ler_procedimento,
    
    NoScrollComboBox, SidebarPanel, danger_button, field_label, fit_to_screen, hsep,
    output_button, primary_button, subtext,
)
from . import gravacao_core as core
from .base import ToolMeta, ToolPage

META = ToolMeta(
    key="gravacao",
    name="Gravação de Tela",
    icon="tool_gravacao",
    tagline="Registra a diligência feita no computador",
    description=(
        "Grava o que acontece na tela com a identificação do processo, do "
        "operador e da estação impressa no próprio vídeo, junto ao "
        "relógio e ao tempo decorrido. Lê da máquina o usuário do "
        "Windows, o nome e o número de série do equipamento e os "
        "endereços de rede. Ao encerrar, calcula o SHA-256 do arquivo e "
        "emite termo de registro audiovisual, com as ressalvas do que a "
        "gravação prova e do que não prova."
    ),
)

#: Onde as gravações são guardadas por padrão.
PASTA_PADRAO = Path.home() / "Documents" / "Sistema Têmis" / "Gravações"


def _pasta_downloads_padrao() -> Path:
    """A pasta de Downloads do usuário, ou a home se ela não existir."""
    candidata = Path.home() / "Downloads"
    return candidata if candidata.is_dir() else Path.home()


# ─────────────────────────────────────────
#  PAINEL FLUTUANTE
# ─────────────────────────────────────────

class PainelGravando(QWidget):
    """Controle mínimo que fica sobre tudo enquanto se grava."""

    encerrar_pedido = pyqtSignal()
    capturar_pedido = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(268, 56)
        self._arrastando: QPoint | None = None

        linha = QHBoxLayout(self)
        linha.setContentsMargins(14, 8, 10, 8)
        linha.setSpacing(10)

        self._ponto = QLabel("●")
        self._ponto.setStyleSheet(
            f"color: {PALETTE['danger']}; font-size: 17px;")
        linha.addWidget(self._ponto)

        self._tempo = QLabel("00:00:00")
        self._tempo.setStyleSheet(
            f"color: {PALETTE['text']}; font-size: 17px; font-weight: 700;"
            "font-family: Consolas, monospace;")
        linha.addWidget(self._tempo)
        linha.addStretch()

        capturar = QPushButton("Capturar tela")
        capturar.setCursor(Qt.CursorShape.PointingHandCursor)
        capturar.setStyleSheet(
            f"QPushButton {{ background: {PALETTE['surface3']}; "
            f"color: {PALETTE['text']}; border: none; border-radius: 6px; "
            f"padding: 7px 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {PALETTE['surface2']}; }}")
        capturar.clicked.connect(self.capturar_pedido)
        linha.addWidget(capturar)

        parar = QPushButton("Encerrar")
        parar.setCursor(Qt.CursorShape.PointingHandCursor)
        parar.setStyleSheet(
            f"QPushButton {{ background: {PALETTE['danger']}; color: white; "
            f"border: none; border-radius: 6px; padding: 7px 14px; "
            f"font-weight: 700; }}"
            f"QPushButton:hover {{ background: #FF7A88; }}")
        parar.clicked.connect(self.encerrar_pedido)
        linha.addWidget(parar)

        # O ponto pisca: numa gravação longa é o que diz, de relance, que
        # o registro continua correndo.
        self._pisca = QTimer(self)
        self._pisca.setInterval(700)
        self._pisca.timeout.connect(self._alternar)
        self._aceso = True

    def paintEvent(self, _ev):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setBrush(QColor(PALETTE["surface"]))
        pintor.setPen(QColor(PALETTE["border"]))
        pintor.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

    def _alternar(self):
        self._aceso = not self._aceso
        self._ponto.setStyleSheet(
            f"color: {PALETTE['danger'] if self._aceso else 'transparent'};"
            "font-size: 17px;")

    def mostrar(self):
        tela = QGuiApplication.primaryScreen().availableGeometry()
        self.move(tela.right() - self.width() - 28, tela.top() + 28)
        self.show()
        self._pisca.start()

    def esconder(self):
        self._pisca.stop()
        self.hide()

    def atualizar(self, segundos: float):
        s = int(segundos)
        self._tempo.setText(
            f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")

    # arrastável: precisa sair da frente do que está sendo registrado
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._arrastando = (ev.globalPosition().toPoint()
                                - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, ev):
        if self._arrastando is not None:
            self.move(ev.globalPosition().toPoint() - self._arrastando)

    def mouseReleaseEvent(self, _ev):
        self._arrastando = None


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """A peça pronta para os autos, editável antes de salvar."""

    def __init__(self, termo: core.TermoGravacao, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Registro Audiovisual")
        self._termo = termo
        fit_to_screen(self, 960, 820)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel("Termo de Registro Audiovisual")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        layout.addWidget(subtext(
            "O documento já traz a estação onde se gravou, o período, a "
            "duração e o resumo criptográfico de cada arquivo. Confira a "
            "abertura e o objeto antes de salvar.", wrap=True))
        layout.addWidget(self._montar_formulario())
        layout.addWidget(hsep())

        self._vista = QTextEdit()
        self._vista.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 26px; }")
        layout.addWidget(self._vista, 1)
        layout.addWidget(hsep())
        layout.addWidget(self._montar_acoes())
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

    def _montar_formulario(self) -> QWidget:
        caixa = QWidget()
        grade = QGridLayout(caixa)
        grade.setContentsMargins(0, 4, 0, 4)
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(4)

        t = self._termo
        self._e_nome = QLineEdit(t.nome)
        self._e_nome.setPlaceholderText("Ex.: João da Silva")
        self._e_matricula = QLineEdit(t.matricula)
        self._e_matricula.setPlaceholderText("Ex.: 1234567")
        self._e_lotacao = QLineEdit(t.lotacao)
        self._e_lotacao.setPlaceholderText("Ex.: DTIC — Divisão de Sistemas")
        for coluna, (rotulo, campo) in enumerate((
                ("Nome do servidor", self._e_nome),
                ("Matrícula", self._e_matricula),
                ("Lotação", self._e_lotacao))):
            grade.addWidget(field_label(rotulo), 0, coluna)
            grade.addWidget(campo, 1, coluna)
            campo.textChanged.connect(self._remontar)

        # O cargo é editável porque esta ferramenta não é só da
        # corregedoria: quem grava a extração costuma ser de outra área.
        self._e_cargo = QLineEdit(t.cargo)
        self._e_tipo = NoScrollComboBox()
        preparar_procedimento(self._e_tipo)
        self._e_tipo.currentIndexChanged.connect(self._remontar)
        self._e_processo = QLineEdit(t.numero_processo)
        self._e_processo.setPlaceholderText("Ex.: 08650.000123/2026-11")
        self._e_data = QDateEdit()
        self._e_data.setCalendarPopup(True)
        self._e_data.setDisplayFormat("dd/MM/yyyy")
        self._e_data.setDate(QDate.currentDate())
        self._e_data.dateChanged.connect(self._remontar)
        for coluna, (rotulo, campo) in enumerate((
                ("Cargo de quem assina", self._e_cargo),
                ("Procedimento", self._e_tipo),
                ("Data do termo", self._e_data))):
            grade.addWidget(field_label(rotulo), 2, coluna)
            grade.addWidget(campo, 3, coluna)
        self._e_cargo.textChanged.connect(self._remontar)
        self._e_processo.textChanged.connect(self._remontar)

        grade.addWidget(field_label("Número do processo"), 4, 0)
        grade.addWidget(self._e_processo, 5, 0)
        self._e_sistema = QLineEdit(t.sistema_consultado)
        self._e_sistema.setPlaceholderText(
            "Ex.: Sistema de Registro de Ocorrências — módulo de auditoria")
        self._e_sistema.textChanged.connect(self._remontar)
        grade.addWidget(field_label("Sistema consultado (opcional)"), 4, 1, 1, 2)
        grade.addWidget(self._e_sistema, 5, 1, 1, 2)

        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 2)
        grade.setColumnStretch(2, 2)
        grade.setRowMinimumHeight(2, 10)
        grade.setRowMinimumHeight(4, 10)
        return caixa

    def _montar_acoes(self) -> QWidget:
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

        copiar = QPushButton("Copiar texto")
        copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        copiar.clicked.connect(self._copiar)
        linha.addWidget(copiar)

        restaurar = QPushButton("  Restaurar original")
        restaurar.setIcon(draw_icon("undo"))
        restaurar.setCursor(Qt.CursorShape.PointingHandCursor)
        restaurar.clicked.connect(self._remontar)
        linha.addWidget(restaurar)

        self._aviso = QLabel("")
        self._aviso.setObjectName("badge_ok")
        linha.addWidget(self._aviso)
        linha.addStretch()

        fechar = QPushButton("Fechar")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        return acoes

    def _atualizado(self) -> core.TermoGravacao:
        t = self._termo
        d = self._e_data.date()
        t.nome = self._e_nome.text().strip()
        t.matricula = self._e_matricula.text().strip()
        t.lotacao = self._e_lotacao.text().strip()
        t.cargo = self._e_cargo.text().strip() or "Servidor"
        t.tipo_processo = ler_procedimento(self._e_tipo)
        t.numero_processo = self._e_processo.text().strip()
        t.sistema_consultado = self._e_sistema.text().strip()
        t.dia, t.mes, t.ano = d.day(), d.month(), d.year()
        return t

    def _remontar(self):
        self._vista.setHtml(core.build_html(self._atualizado()))

    def _copiar(self):
        QGuiApplication.clipboard().setText(core.build_text(self._atualizado()))
        self._aviso.setText("✓ Texto copiado")

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML", "termo-gravacao.html",
            "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            corpo = limpar_para_sei(self._vista.toHtml())
            Path(caminho).write_text(
                documento_html(corpo, "Termo de Registro Audiovisual de "
                                      "Diligência em Meio Eletrônico"),
                encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar o arquivo:\n{e}")

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo", "termo-gravacao.pdf",
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            escritor = preparar_escritor(
                caminho, "Termo de Registro Audiovisual de Diligência em "
                         "Meio Eletrônico")
            doc = self._vista.document().clone()
            doc.setDefaultFont(QFont("Segoe UI", 10))
            imprimir_documento(doc, escritor)
            self._aviso.setText("✓ PDF salvo")
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gerar o PDF:\n{e}")


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class GravacaoTool(ToolPage):
    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gravador: core.Gravador | None = None
        self._resultados: list[core.Resultado] = []
        self._capturas: list = []
        self._contexto = core.ler_contexto()
        self._painel = PainelGravando()
        self._painel.encerrar_pedido.connect(self._encerrar)
        self._painel.capturar_pedido.connect(self._capturar)

        self._pulso = QTimer(self)
        self._pulso.setInterval(500)
        self._pulso.timeout.connect(self._tique)

        self._montar()
        self._atualizar_estado()

    # ── montagem ─────────────────────────────────
    def _montar(self):
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._montar_lateral())

        principal = QWidget()
        coluna = QVBoxLayout(principal)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self._montar_estado())
        coluna.addWidget(self._montar_lista(), 1)
        raiz.addWidget(principal, 1)

    def _montar_lateral(self) -> QWidget:
        painel = SidebarPanel()

        titulo = QLabel("Diligência")
        titulo.setObjectName("heading")
        painel.header.addWidget(titulo)

        painel.body.addWidget(field_label("IDENTIFICAÇÃO"))
        self._e_processo = QLineEdit()
        self._e_processo.setPlaceholderText("08650.000123/2026-11")
        self._e_processo.textChanged.connect(self._atualizar_previa)
        painel.body.addWidget(field_label("Número do processo"))
        painel.body.addWidget(self._e_processo)

        self._e_operador = QLineEdit()
        self._e_operador.setPlaceholderText("Nome de quem realiza a diligência")
        self._e_operador.textChanged.connect(self._atualizar_previa)
        painel.body.addWidget(field_label("Operador"))
        painel.body.addWidget(self._e_operador)

        self._e_objeto = QPlainTextEdit()
        self._e_objeto.setPlaceholderText(
            "O que será registrado. Ex.: extração de registros de acesso do "
            "servidor X, no período de 01/01 a 31/03, no módulo de auditoria.")
        self._e_objeto.setFixedHeight(78)
        painel.body.addWidget(field_label("Objeto da diligência"))
        painel.body.addWidget(self._e_objeto)

        painel.body.addWidget(hsep())
        painel.body.addWidget(field_label("CAPTURA"))

        self._cb_area = NoScrollComboBox()
        for m in core.monitores():
            self._cb_area.addItem(m.rotulo, m.chave)
        painel.body.addWidget(field_label("Área"))
        painel.body.addWidget(self._cb_area)

        self._cb_qualidade = NoScrollComboBox()
        for chave, _q, _c, descricao in core.QUALIDADES:
            self._cb_qualidade.addItem(f"{chave.capitalize()} — {descricao}",
                                       chave)
        painel.body.addWidget(field_label("Qualidade"))
        painel.body.addWidget(self._cb_qualidade)

        # Duas fontes de som, escolhidas em separado, porque são coisas
        # diferentes: o que a máquina reproduz e o que se fala na sala.
        # Marcadas as duas, entram como faixas distintas no arquivo — e
        # não misturadas, para que a peça possa afirmar a origem de cada
        # uma.
        painel.body.addWidget(field_label("Áudio da gravação"))

        self._cb_microfone = NoScrollComboBox()
        self._cb_microfone.addItem("Sem microfone", "")
        for nome in core.microfones():
            self._cb_microfone.addItem(nome, nome)
        self._cb_microfone.setToolTip(
            "Som do ambiente: o que for falado na sala durante a diligência")
        painel.body.addWidget(self._cb_microfone)

        from .audio_sistema import disponivel as _retorno_disponivel
        pode_sistema, detalhe_sistema = _retorno_disponivel()
        self._chk_som_sistema = QCheckBox("Som do computador")
        self._chk_som_sistema.setEnabled(pode_sistema)
        self._chk_som_sistema.setToolTip(
            f"Grava o que o computador reproduz — vídeos, mensagens de "
            f"voz, chamadas. Saída: {detalhe_sistema}" if pode_sistema else
            f"Indisponível nesta estação: {detalhe_sistema}")
        painel.body.addWidget(self._chk_som_sistema)

        painel.body.addWidget(subtext(
            "Marcadas as duas, o vídeo sai com duas faixas de áudio "
            "separadas — o que o computador tocou e o que foi dito na "
            "sala." if pode_sistema else
            f"O som do computador não pode ser gravado nesta estação: "
            f"{detalhe_sistema}", wrap=True))

        self._op_resistente = QCheckBox("Resistir a interrupção")
        self._op_resistente.setChecked(True)
        self._op_resistente.setToolTip(
            "Grava de modo que uma queda de energia não leve o registro "
            "inteiro — perdem-se os últimos dez a quinze segundos em vez de "
            "tudo. O arquivo fica cerca de três vezes maior.")
        painel.body.addWidget(self._op_resistente)

        # Monitorar downloads é opção, e não padrão: filmar a tela é o que
        # a ferramenta sempre faz; resumir arquivos recebidos é um
        # acréscimo para a diligência que envolve baixar algo.
        self._chk_downloads = QCheckBox("Registrar arquivos recebidos")
        self._chk_downloads.setToolTip(
            "Vigia uma pasta durante a gravação e resume em SHA-256 cada "
            "arquivo que nela aparecer, relacionando-os no termo. Não "
            "captura o que se digita nem em que se clica — observa a "
            "pasta, e diz que o arquivo chegou ali, com aquele resumo.")
        self._chk_downloads.toggled.connect(self._alternar_downloads)
        painel.body.addWidget(self._chk_downloads)

        linha_pasta = QHBoxLayout()
        self._e_pasta = QLineEdit(str(_pasta_downloads_padrao()))
        self._e_pasta.setReadOnly(True)
        self._e_pasta.setEnabled(False)
        self._b_pasta = QPushButton("Escolher…")
        self._b_pasta.setEnabled(False)
        self._b_pasta.clicked.connect(self._escolher_pasta)
        linha_pasta.addWidget(self._e_pasta, 1)
        linha_pasta.addWidget(self._b_pasta)
        painel.body.addLayout(linha_pasta)

        self._chk_janelas = QCheckBox("Registrar janelas em primeiro plano")
        self._chk_janelas.setToolTip(
            "Anota quais aplicativos e janelas estiveram à frente durante "
            "a gravação, e quando — o índice navegável do vídeo. Não "
            "captura o que se digita nem em que se clica.")
        painel.body.addWidget(self._chk_janelas)

        painel.body.addWidget(hsep())
        painel.body.addWidget(field_label("ESTAÇÃO"))
        self._rot_contexto = QLabel()
        self._rot_contexto.setObjectName("muted")
        self._rot_contexto.setWordWrap(True)
        self._rot_contexto.setText("<br/>".join(
            f"{r}: {v}" for r, v in self._contexto.linhas()[:5]))
        painel.body.addWidget(self._rot_contexto)
        painel.body.addStretch()

        self._b_gravar = primary_button("Iniciar gravação", "camera")
        self._b_gravar.clicked.connect(self._iniciar)
        painel.footer.addWidget(self._b_gravar)

        self._b_capturar = output_button("Capturar tela", "camera")
        self._b_capturar.setToolTip(
            "Fotografa a tela agora, resume em SHA-256 e documenta a "
            "captura. Durante a gravação, use o botão da janela flutuante.")
        self._b_capturar.clicked.connect(self._capturar)
        painel.footer.addWidget(self._b_capturar)

        self._b_termo = output_button("Gerar termo")
        self._b_termo.clicked.connect(self._gerar_termo)
        painel.footer.addWidget(self._b_termo)
        painel.add_note("A janela do sistema é recolhida durante a gravação.")
        return painel

    def _alternar_downloads(self, ligado: bool):
        self._e_pasta.setEnabled(ligado)
        self._b_pasta.setEnabled(ligado)

    def _escolher_pasta(self):
        atual = self._e_pasta.text() or str(Path.home())
        escolha = QFileDialog.getExistingDirectory(
            self, "Pasta a vigiar durante a gravação", atual)
        if escolha:
            self._e_pasta.setText(escolha)

    def _montar_estado(self) -> QWidget:
        caixa = QFrame()
        caixa.setStyleSheet(
            f"background: {PALETTE['surface']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        coluna = QVBoxLayout(caixa)
        coluna.setContentsMargins(20, 16, 20, 16)
        coluna.setSpacing(6)

        self._rot_estado = QLabel("Pronto para gravar")
        self._rot_estado.setObjectName("heading")
        coluna.addWidget(self._rot_estado)

        self._rot_previa = QLabel()
        self._rot_previa.setObjectName("subtext")
        self._rot_previa.setWordWrap(True)
        coluna.addWidget(self._rot_previa)
        self._atualizar_previa()
        return caixa

    def _montar_lista(self) -> QWidget:
        envelope = QWidget()
        coluna = QVBoxLayout(envelope)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)

        self._arvore = QTreeWidget()
        self._arvore.setColumnCount(5)
        self._arvore.setHeaderLabels(
            ["Arquivo", "Início", "Duração", "Tamanho", "SHA-256"])
        self._arvore.setRootIsDecorated(False)
        self._arvore.setAlternatingRowColors(True)
        cabeca = self._arvore.header()
        cabeca.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        cabeca.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            cabeca.setSectionResizeMode(
                c, QHeaderView.ResizeMode.ResizeToContents)
        self._arvore.setColumnWidth(0, 260)
        self._arvore.itemDoubleClicked.connect(lambda *_: self._abrir())
        self._arvore.currentItemChanged.connect(
            lambda *_: self._atualizar_estado())
        coluna.addWidget(self._arvore, 1)

        acoes = QFrame()
        acoes.setStyleSheet(
            f"background: {PALETTE['surface']}; "
            f"border-top: 1px solid {PALETTE['border']};")
        linha = QHBoxLayout(acoes)
        linha.setContentsMargins(14, 10, 14, 10)
        linha.setSpacing(8)
        for rotulo, alvo in (("Abrir vídeo", self._abrir),
                             ("Abrir pasta", self._abrir_pasta),
                             ("Copiar hash", self._copiar_hash)):
            b = QPushButton(rotulo)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(alvo)
            linha.addWidget(b)
        linha.addStretch()

        # Sem estas duas, a lista acumulava tudo o que se gravou desde
        # que o programa abriu, e o termo seguinte repetia a diligência
        # anterior — erro grave numa peça que vai aos autos.
        self._b_remover = QPushButton("Remover da lista")
        self._b_remover.setToolTip(
            "Tira este registro da lista e do termo. O arquivo de vídeo "
            "não é apagado.")
        self._b_remover.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_remover.clicked.connect(self._remover_da_lista)
        linha.addWidget(self._b_remover)

        self._b_nova = danger_button("Nova diligência")
        self._b_nova.setToolTip(
            "Esvazia a lista para começar outro registro. Os vídeos "
            "gravados permanecem onde estão.")
        self._b_nova.clicked.connect(self._nova_diligencia)
        linha.addWidget(self._b_nova)
        coluna.addWidget(acoes)
        return envelope

    # ── prévia da faixa ──────────────────────────
    def _identificacao(self) -> str:
        partes = []
        if self._e_processo.text().strip():
            partes.append(self._e_processo.text().strip())
        if self._e_operador.text().strip():
            partes.append(f"Operador {self._e_operador.text().strip()}")
        partes.append(f"Estação {self._contexto.estacao}")
        if self._contexto.usuario:
            partes.append(f"Usuário {self._contexto.usuario}")
        partes.append(f"Início {datetime.datetime.now():%d/%m/%Y}")
        return "  •  ".join(partes)

    def _atualizar_previa(self):
        self._rot_previa.setText(
            "A faixa impressa no vídeo mostrará:  "
            f"<b>{self._identificacao()}</b>  —  mais o relógio da estação e "
            "o tempo decorrido.")

    # ── gravação ─────────────────────────────────
    def _iniciar(self):
        if self._gravador is not None:
            return
        if self._chk_janelas.isChecked():
            resposta = QMessageBox.question(
                self, "Registro de ações nesta gravação",
                "Esta gravação vai registrar, além da imagem, as janelas "
                "que passarem ao primeiro plano — qual aplicativo e qual "
                "janela estiveram à frente, e quando.\n\nO registro não "
                "captura o que se digita nem em que se clica, e a relação "
                "sai no termo. Iniciar assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes)
            if resposta != QMessageBox.StandardButton.Yes:
                return
        if not self._e_processo.text().strip():
            resposta = QMessageBox.question(
                self, "Sem número de processo",
                "A faixa do vídeo sairá sem o número do processo, que é o "
                "que liga o registro aos autos.\n\nGravar assim mesmo?")
            if resposta != QMessageBox.StandardButton.Yes:
                return

        PASTA_PADRAO.mkdir(parents=True, exist_ok=True)
        agora = datetime.datetime.now()
        sugestao = PASTA_PADRAO / f"diligencia-{agora:%Y-%m-%d-%H%M%S}.mp4"
        destino, _ = QFileDialog.getSaveFileName(
            self, "Onde gravar o vídeo", str(sugestao),
            "Vídeo MP4 (*.mp4)")
        if not destino:
            return
        if not destino.lower().endswith(".mp4"):
            destino += ".mp4"

        opcoes = core.Opcoes(
            monitor=self._cb_area.currentData() or "desktop",
            qualidade=self._cb_qualidade.currentData() or "normal",
            microfone=self._cb_microfone.currentData() or "",
            audio_sistema=self._chk_som_sistema.isChecked(),
            identificacao=self._identificacao(),
            resistente=self._op_resistente.isChecked(),
            pasta_monitorada=(self._e_pasta.text().strip()
                              if self._chk_downloads.isChecked() else ""),
            registrar_janelas=self._chk_janelas.isChecked())

        self._gravador = core.Gravador(destino, opcoes)
        try:
            self._gravador.iniciar()
        except Exception as e:                          # noqa: BLE001
            self._gravador = None
            QMessageBox.critical(self, "Não foi possível gravar", str(e))
            return

        self._rot_estado.setText("Gravando…")
        self._atualizar_estado()
        self._painel.mostrar()
        self._pulso.start()
        self.status_msg.emit("Gravação iniciada.")

        # A janela sai da frente: se ficasse, apareceria no registro e
        # cobriria o que se quer mostrar.
        janela = self.window()
        if janela is not None:
            janela.showMinimized()

    def _pasta_capturas(self) -> Path:
        """Onde as capturas ficam.

        Junto do vídeo, quando há gravação em curso — assim a imagem e o
        vídeo da mesma diligência moram no mesmo lugar. Fora de uma
        gravação, numa pasta de capturas por dia.
        """
        if self._gravador is not None:
            return Path(self._gravador.destino).parent / "capturas"
        agora = datetime.datetime.now()
        return PASTA_PADRAO / "Capturas" / f"{agora:%Y-%m-%d}"

    def _capturar(self):
        monitor = (self._gravador.opcoes.monitor
                   if self._gravador is not None
                   else self._cb_area.currentData() or "desktop")
        decorrido = (self._gravador.decorrido
                     if self._gravador is not None else None)
        captura = core.capturar_tela(
            self._pasta_capturas(), len(self._capturas) + 1, monitor,
            decorrido)
        self._capturas.append(captura)
        if captura.erro:
            self.status_msg.emit(f"Falha na captura: {captura.erro}")
        else:
            self.status_msg.emit(
                f"Captura {len(self._capturas)} salva "
                f"({captura.nome}) — SHA-256 {captura.sha256[:12]}…")
        self._atualizar_estado()

    def _tique(self):
        if self._gravador is None:
            return
        self._painel.atualizar(self._gravador.decorrido)
        self._gravador.varrer_downloads()
        if not self._gravador.gravando:
            # O codificador morreu sozinho — melhor encerrar e dizer isso
            # do que deixar o painel piscando sobre uma gravação parada.
            self._encerrar(inesperado=True)

    def _encerrar(self, inesperado: bool = False):
        if self._gravador is None:
            return
        self._pulso.stop()
        self._painel.esconder()
        janela = self.window()
        if janela is not None:
            janela.showNormal()
            janela.raise_()
            janela.activateWindow()

        resultado = self._gravador.encerrar()
        self._gravador = None
        self._rot_estado.setText("Pronto para gravar")

        if resultado.erro:
            self._atualizar_estado()
            QMessageBox.critical(self, "A gravação falhou", resultado.erro)
            return
        self._resultados.append(resultado)
        self._acrescentar(resultado)
        # Depois de guardar o resultado, e não antes: o botão do termo
        # depende de haver gravação na lista, e a ordem invertida o
        # deixava desligado justamente quando passava a fazer sentido.
        self._atualizar_estado()
        self.status_msg.emit(
            f"Gravação encerrada: {resultado.duracao}, "
            f"{core.formatar_tamanho(resultado.tamanho)}.")
        if inesperado:
            QMessageBox.warning(
                self, "A gravação parou sozinha",
                "O codificador encerrou antes do comando. O arquivo "
                "gravado até ali foi mantido e consta da lista, mas o "
                "registro está incompleto.")

    def _acrescentar(self, r: core.Resultado):
        item = QTreeWidgetItem([
            Path(r.arquivo).name, core.data_br(r.inicio), r.duracao,
            core.formatar_tamanho(r.tamanho), r.sha256])
        item.setData(0, Qt.ItemDataRole.UserRole, r.arquivo)
        item.setToolTip(0, r.arquivo)
        item.setForeground(4, QColor(PALETTE["text3"]))
        item.setFont(4, QFont("Consolas", 8))
        self._arvore.addTopLevelItem(item)
        self._arvore.setCurrentItem(item)

    # ── ações ────────────────────────────────────
    def _selecionado(self) -> core.Resultado | None:
        item = self._arvore.currentItem()
        if item is None:
            return None
        caminho = item.data(0, Qt.ItemDataRole.UserRole)
        return next((r for r in self._resultados if r.arquivo == caminho), None)

    def _abrir(self):
        r = self._selecionado()
        if r is None:
            return
        try:
            os.startfile(r.arquivo)                     # noqa: S606
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir", str(e))

    def _abrir_pasta(self):
        r = self._selecionado()
        if r is None:
            return
        try:
            subprocess.Popen(["explorer", "/select,", str(Path(r.arquivo))])
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir", str(e))

    def _copiar_hash(self):
        r = self._selecionado()
        if r is None:
            return
        QGuiApplication.clipboard().setText(r.sha256)
        self.status_msg.emit("SHA-256 copiado.")


    # ── limpar ───────────────────────────────────
    def _remover_da_lista(self):
        """Tira um registro da lista, sem apagar o arquivo."""
        item = self._arvore.currentItem()
        r = self._selecionado()
        if item is None or r is None:
            return
        resposta = QMessageBox.question(
            self, "Remover da lista",
            f"Retirar “{Path(r.arquivo).name}” da lista e do termo?\n\n"
            f"O arquivo de vídeo continuará onde está; apenas deixa de "
            f"constar do próximo termo.")
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self._arvore.takeTopLevelItem(self._arvore.indexOfTopLevelItem(item))
        self._resultados = [x for x in self._resultados
                            if x.arquivo != r.arquivo]
        self._atualizar_estado()
        self.status_msg.emit("Registro retirado da lista.")

    def _nova_diligencia(self):
        """Esvazia a lista para começar outro registro."""
        if not self._resultados:
            return
        resposta = QMessageBox.question(
            self, "Nova diligência",
            f"Esvaziar a lista para começar outro registro?\n\n"
            f"Os {len(self._resultados)} vídeo(s) já gravado(s) permanecem "
            f"onde estão, e o termo que você já tenha salvo continua "
            f"valendo. O que se limpa aqui é apenas o que entraria no "
            f"próximo termo.")
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self._resultados.clear()
        self._arvore.clear()
        # O número do processo e o objeto mudam a cada diligência; o nome
        # de quem opera, não — é o mesmo o dia inteiro.
        self._e_processo.clear()
        self._e_objeto.clear()
        self._atualizar_estado()
        self.status_msg.emit("Lista esvaziada. Os arquivos foram mantidos.")

    # ── termo ────────────────────────────────────
    def _gerar_termo(self):
        if not self._resultados and not self._capturas:
            return
        termo = core.TermoGravacao(
            nome=self._e_operador.text().strip(),
            numero_processo=self._e_processo.text().strip(),
            objeto=self._e_objeto.toPlainText().strip(),
            registros=list(self._resultados),
            capturas=list(self._capturas))
        TermoDialog(termo, self).exec()

    # ── estado ───────────────────────────────────
    def _atualizar_estado(self):
        gravando = self._gravador is not None
        self._b_gravar.setEnabled(not gravando)
        # Capturar vale sempre: durante a gravação (pelo painel flutuante
        # e por este botão) e fora dela.
        self._b_capturar.setEnabled(True)
        tem_peca = bool(self._resultados or self._capturas)
        self._b_termo.setEnabled(tem_peca and not gravando)
        self._b_nova.setEnabled(bool(self._resultados) and not gravando)
        self._b_remover.setEnabled(
            self._arvore.currentItem() is not None and not gravando)
        for w in (self._e_processo, self._e_operador, self._e_objeto,
                  self._cb_area, self._cb_qualidade, self._cb_microfone,
                  self._chk_som_sistema,
                  self._op_resistente):
            w.setEnabled(not gravando)

    # ── ciclo de vida ────────────────────────────
    def can_close(self) -> bool:
        if self._gravador is not None:
            resposta = QMessageBox.question(
                self, "Gravação em andamento",
                "Há uma gravação em curso. Sair agora a encerra.\n\n"
                "Deseja encerrar a gravação e sair?")
            if resposta != QMessageBox.StandardButton.Yes:
                return False
            self._encerrar()
        return True

    def shutdown(self):
        # Encerrar pelo comando, e não matando o processo: só assim o
        # arquivo é fechado com a duração correta.
        if self._gravador is not None:
            self._pulso.stop()
            self._gravador.encerrar()
            self._gravador = None
        self._painel.esconder()
        self._painel.deleteLater()
