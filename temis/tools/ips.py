"""
Encarregado de IPS — montagem da Informação.

O documento é escrito aqui, parte por parte, e sai como um HTML pronto
para a importação do SEI. A ideia é tirar a redação de dentro do SEI, que
não é um editor de texto, sem tirar dali o documento final.

O roteiro das partes vem de `ips_core.SECOES`. A ferramenta não conhece
nenhuma seção em particular: monta o roteiro, o progresso e o documento a
partir dessa lista.
"""

from __future__ import annotations

import datetime
import time
from pathlib import Path

from PyQt6.QtCore import (Qt, QTimer, QUrl, QSize, QMarginsF, QRectF,
                          QSizeF, pyqtSignal)
from PyQt6.QtGui import (
    QColor, QFont, QImage, QKeySequence, QShortcut, QTextCharFormat,
    QAbstractTextDocumentLayout, QGuiApplication, QPainter,
    QPalette, QTextCursor, QTextDocument,
    QPdfWriter, QPageSize,
    QPageLayout,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QFrame, QMessageBox, QTextEdit, QLineEdit, QListWidget, QListWidgetItem,
    QInputDialog, QDialog, QColorDialog, QSizePolicy, QProgressBar,
    QStackedWidget, QScrollArea, QPlainTextEdit, QApplication,
)

from ..icons import draw_icon
from ..impressao import imprimir_documento, preparar_escritor
from ..theme import PALETTE
from ..widgets import (
    Carregando, NoScrollComboBox, SidebarPanel, TOOLBAR_HEIGHT, danger_button,
    field_label, fit_to_screen, group_title, hsep, output_button,
    primary_button, subtext, vsep,
)
from .base import ToolPage, ToolMeta
from . import ips_core as core
from . import ips_blocos as blocos
from .ips_editor import EditorBlocos


META = ToolMeta(
    key="ips",
    name="Encarregado de IPS",
    icon="tool_ips",
    tagline="Montagem da Informação",
    description=(
        "Monta a Informação da Investigação Preliminar Sumária parte por "
        "parte, com o roteiro do que entra em cada uma e o respaldo "
        "normativo à mão. Ao final exporta um HTML pronto para a importação "
        "no SEI, já diagramado — tirando a redação de dentro do SEI sem "
        "tirar de lá o documento."
    ),
)

#: Tamanho máximo da imagem inserida, em pixels de largura.
IMAGEM_LARGURA_MAX = 1000


# ─────────────────────────────────────────
#  EDITOR
# ─────────────────────────────────────────

class EditorRico(QTextEdit):
    """Editor da parte, com imagens resolvidas a partir do disco."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pasta_imagens: Path | None = None
        self.setAcceptRichText(True)
        self.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 28px 34px; }")
        f = QFont("Times New Roman", 12)
        self.setFont(f)
        self.document().setDefaultFont(f)

    def loadResource(self, tipo: int, nome: QUrl):
        """Resolve `imagens/<arquivo>` na pasta do caso.

        As imagens ficam em disco e não embutidas no documento: assim o
        salvamento automático continua barato e o arquivo do caso não
        cresce a cada foto.
        """
        caminho = nome.toString()
        if (tipo == QTextDocument.ResourceType.ImageResource
                and caminho.startswith(core.PREFIXO_IMAGEM)
                and self.pasta_imagens is not None):
            arq = self.pasta_imagens / caminho[len(core.PREFIXO_IMAGEM):]
            if arq.exists():
                return QImage(str(arq))
        return super().loadResource(tipo, nome)


# ─────────────────────────────────────────
#  NORMA
# ─────────────────────────────────────────

class NormaDialog(QDialog):
    """O que a instrução normativa diz sobre esta parte."""

    def __init__(self, s: core.Secao, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Norma — {s.titulo}")
        fit_to_screen(self, 640, 480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        titulo = QLabel(s.titulo)
        titulo.setObjectName("heading")
        lay.addWidget(titulo)

        if s.norma:
            ref = QLabel(s.norma)
            ref.setStyleSheet(f"color: {PALETTE['gold']}; font-weight: 700;")
            lay.addWidget(ref)

        lay.addWidget(group_title("O que se espera desta parte"))
        orient = QLabel(s.orientacao or "—")
        orient.setObjectName("subtext")
        orient.setWordWrap(True)
        lay.addWidget(orient)

        lay.addWidget(group_title("Texto da norma"))
        texto = QTextEdit()
        texto.setReadOnly(True)
        texto.setPlainText(
            s.texto_norma
            or "O texto do dispositivo ainda não foi cadastrado nesta parte.")
        texto.setStyleSheet(
            f"QTextEdit {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 12px; }}")
        lay.addWidget(texto, 1)

        linha = QHBoxLayout()
        linha.addStretch()
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        lay.addLayout(linha)



# ─────────────────────────────────────────
#  CASOS SALVOS
# ─────────────────────────────────────────

class CasosDialog(QDialog):
    """Informações já iniciadas neste computador."""

    def __init__(self, casos: list[core.CasoIPS], atual: str,
                 acervo: core.AcervoIPS, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Informações salvas")
        fit_to_screen(self, 680, 540)
        self.escolhido: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        titulo = QLabel("Informações salvas neste computador")
        titulo.setObjectName("heading")
        lay.addWidget(titulo)

        caminho = QLabel(str(acervo.raiz))
        caminho.setObjectName("muted")
        caminho.setWordWrap(True)
        caminho.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(caminho)

        self._lista = QListWidget()
        self._lista.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 10px 12px; "
            f"border-bottom: 1px solid {PALETTE['surface2']}; }}")
        for c in sorted(casos, key=lambda x: -x.atualizado):
            feitas, total = c.progresso()
            quando = time.strftime("%d/%m/%Y às %H:%M",
                                   time.localtime(c.atualizado))
            marca = "●  " if c.id == atual else "    "
            processo = c.numero_processo or "sem número de processo"
            item = QListWidgetItem(
                f"{marca}{c.nome}\n"
                f"     {processo} · {feitas} de {total} partes"
                f" · alterado em {quando}")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            if c.id == atual:
                item.setForeground(QColor(PALETTE["gold"]))
            elif feitas == total and total:
                item.setForeground(QColor(PALETTE["success"]))
            self._lista.addItem(item)
        self._lista.itemDoubleClicked.connect(self._abrir)
        lay.addWidget(self._lista, 1)

        linha = QHBoxLayout()
        linha.setSpacing(8)
        abrir = output_button("Abrir Informação")
        abrir.clicked.connect(lambda: self._abrir(self._lista.currentItem()))
        linha.addWidget(abrir)
        linha.addStretch()
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.reject)
        linha.addWidget(fechar)
        lay.addLayout(linha)

        if self._lista.count():
            self._lista.setCurrentRow(0)

    def _abrir(self, item):
        if item is None:
            return
        self.escolhido = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


# ─────────────────────────────────────────
#  PRÉVIA
# ─────────────────────────────────────────

class PreviaDialog(QDialog):
    """Mostra a Informação montada e permite exportar."""

    def __init__(self, caso: core.CasoIPS, pasta_imagens: Path,
                 ao_exportar_html, ao_exportar_pdf, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Prévia — {caso.nome}")
        fit_to_screen(self, 940, 800)
        self._caso = caso

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        titulo = QLabel("Prévia da Informação")
        titulo.setObjectName("heading")
        lay.addWidget(titulo)

        feitas, total = caso.progresso()
        sub = QLabel(
            f"{feitas} de {total} partes concluídas. "
            "É assim que o documento entra no SEI.")
        sub.setObjectName("subtext")
        lay.addWidget(sub)

        self.visao = QTextEdit()
        self.visao.setReadOnly(True)
        self.visao.setHtml(core.build_html(caso, pasta_imagens=pasta_imagens))
        # Fundo branco: é a pré-visualização de um documento que vai para
        # os autos, não uma tela do sistema.
        self.visao.setStyleSheet(
            "QTextEdit { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
            "padding: 34px 44px; }")
        lay.addWidget(self.visao, 1)
        lay.addWidget(hsep())

        acoes = QWidget()
        acoes.setSizePolicy(QSizePolicy.Policy.Preferred,
                            QSizePolicy.Policy.Fixed)
        linha = QHBoxLayout(acoes)
        linha.setContentsMargins(0, 8, 0, 0)
        linha.setSpacing(8)

        b_html = output_button("Exportar HTML para o SEI")
        b_html.clicked.connect(lambda: ao_exportar_html())
        linha.addWidget(b_html)

        b_pdf = QPushButton("  Exportar PDF")
        b_pdf.setIcon(draw_icon("save", 16, PALETTE["text"]))
        b_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        b_pdf.clicked.connect(lambda: ao_exportar_pdf())
        linha.addWidget(b_pdf)

        self.aviso = QLabel("")
        self.aviso.setObjectName("badge_ok")
        linha.addWidget(self.aviso)

        linha.addStretch()
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        linha.addWidget(fechar)
        lay.addWidget(acoes)


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class IPSTool(ToolPage):

    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._acervo = core.AcervoIPS()
        self._casos, atual = self._acervo.carregar()
        self._caso = next(c for c in self._casos if c.id == atual)
        self._secao_atual = core.SECOES[0].id if core.SECOES else ""
        self._carregando = False

        # Salvamento automático: o encarregado não deve precisar lembrar
        # de salvar, e um travamento não pode custar o trabalho da tarde.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1200)
        self._save_timer.timeout.connect(self._gravar)

        self._build_ui()
        self._recarregar_casos()
        self._abrir_secao(self._secao_atual)
        self._atualizar_roteiro()

        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        QShortcut(QKeySequence("Ctrl+S"), self, self._gravar_agora, context=ctx)
        QShortcut(QKeySequence("Ctrl+B"), self, self._negrito, context=ctx)
        QShortcut(QKeySequence("Ctrl+I"), self, self._italico, context=ctx)
        QShortcut(QKeySequence("Ctrl+U"), self, self._sublinhado, context=ctx)

    # ─────────────────────────────────────
    #  UI
    # ─────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self._barra_formatacao = self._build_toolbar()
        ml.addWidget(self._barra_formatacao)
        ml.addWidget(self._build_cabecalho_secao())

        corpo = QWidget()
        corpo.setStyleSheet(f"background: {PALETTE['bg']};")
        cl = QVBoxLayout(corpo)
        cl.setContentsMargins(24, 16, 24, 20)
        cl.setSpacing(10)

        # Uma pilha: seções com formatação fixa viram formulário; as
        # demais, editor livre.
        self._pilha = QStackedWidget()

        self._editor = EditorRico()
        self._editor.textChanged.connect(self._ao_editar)
        self._editor.currentCharFormatChanged.connect(self._sincronizar_botoes)
        self._pilha.addWidget(self._editor)

        self._form_area = QScrollArea()
        self._form_area.setWidgetResizable(True)
        self._form_area.setFrameShape(QFrame.Shape.NoFrame)
        self._pilha.addWidget(self._form_area)
        self._campos: dict[str, QWidget] = {}

        # Corpo em parágrafos numerados — a forma padrão dos elementos.
        self._blocos = EditorBlocos()
        self._blocos.alterado.connect(self._ao_editar)
        self._pilha.addWidget(self._blocos)

        # Entra por último para não deslocar os índices das páginas
        # anteriores; a troca é sempre por widget. O nome não pode ser
        # `_carregando`: esse atributo é a trava do salvamento automático
        # durante a carga, e o widget ficava por baixo dela.
        self._sinal_carga = Carregando()
        self._pilha.addWidget(self._sinal_carga)

        cl.addWidget(self._pilha, 1)

        rodape = QHBoxLayout()
        self._chk_concluida = QPushButton("  Marcar parte como concluída")
        self._chk_concluida.setCheckable(True)
        self._chk_concluida.setIcon(draw_icon("check", color=PALETTE["success"]))
        self._chk_concluida.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chk_concluida.clicked.connect(self._alternar_concluida)
        rodape.addWidget(self._chk_concluida)
        rodape.addStretch()
        self._lbl_salvo = subtext("")
        rodape.addWidget(self._lbl_salvo)
        cl.addLayout(rodape)

        ml.addWidget(corpo, 1)
        root.addWidget(main, 1)

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar_frame")
        frame.setFixedHeight(TOOLBAR_HEIGHT)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(4)

        def botao(icone, dica, slot, alternavel=False):
            b = QPushButton()
            b.setIcon(draw_icon(icone, 16, PALETTE["text"]))
            b.setToolTip(dica)
            b.setFixedSize(34, 32)
            b.setCheckable(alternavel)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        self._btn_b = botao("negrito", "Negrito  (Ctrl+B)", self._negrito, True)
        self._btn_i = botao("italico", "Itálico  (Ctrl+I)", self._italico, True)
        self._btn_u = botao("sublinhado", "Sublinhado  (Ctrl+U)",
                            self._sublinhado, True)

        lay.addWidget(vsep())

        self._btn_cor = QPushButton()
        self._btn_cor.setIcon(draw_icon("cor", 16, PALETTE["text"]))
        self._btn_cor.setToolTip("Cor do texto")
        self._btn_cor.setFixedSize(34, 32)
        self._btn_cor.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cor.clicked.connect(self._escolher_cor)
        lay.addWidget(self._btn_cor)

        botao("cor_limpar", "Voltar à cor padrão",
              lambda: self._aplicar_cor(QColor("#16233A")))

        lay.addWidget(vsep())

        botao("alinhar_esq", "Alinhar à esquerda",
              lambda: self._alinhar(Qt.AlignmentFlag.AlignLeft))
        botao("alinhar_centro", "Centralizar",
              lambda: self._alinhar(Qt.AlignmentFlag.AlignCenter))
        botao("alinhar_just", "Justificar",
              lambda: self._alinhar(Qt.AlignmentFlag.AlignJustify))

        lay.addWidget(vsep())

        botao("image", "Inserir imagem", self._inserir_imagem)
        botao("undo", "Desfazer  (Ctrl+Z)", lambda: self._alvo().undo())

        lay.addWidget(vsep())

        self._btn_paragrafo = QPushButton("  Parágrafo")
        self._btn_paragrafo.setIcon(draw_icon("paragrafo", 15, PALETTE["text"]))
        self._btn_paragrafo.setToolTip(
            "Acrescenta um parágrafo ao final  (ou tecle Enter no último)")
        self._btn_paragrafo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_paragrafo.clicked.connect(self._novo_paragrafo)
        lay.addWidget(self._btn_paragrafo)

        self._btn_tabela = QPushButton("  Tabela")
        self._btn_tabela.setIcon(draw_icon("tabela", 15, PALETTE["text"]))
        self._btn_tabela.setToolTip("Acrescenta uma tabela 3x3 ao final")
        self._btn_tabela.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_tabela.clicked.connect(self._nova_tabela)
        lay.addWidget(self._btn_tabela)

        lay.addWidget(vsep())
        dica = QLabel("Tab aprofunda o nível · Shift+Tab volta")
        dica.setObjectName("muted")
        lay.addWidget(dica)
        lay.addStretch()
        return frame

    def _build_cabecalho_secao(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(46)
        frame.setStyleSheet(
            f"background: {PALETTE['surface2']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(24, 0, 16, 0)
        lay.setSpacing(10)

        self._lbl_secao = QLabel("—")
        self._lbl_secao.setStyleSheet(
            f"color: {PALETTE['gold']}; font-size: 15px; font-weight: 700;")
        lay.addWidget(self._lbl_secao)

        self._lbl_resumo = subtext("")
        lay.addWidget(self._lbl_resumo)
        lay.addStretch()

        self._btn_norma = QPushButton("  O que diz a norma")
        self._btn_norma.setIcon(draw_icon("manual", 16, PALETTE["text"]))
        self._btn_norma.setToolTip(
            "Mostra o dispositivo da instrução normativa sobre esta parte")
        self._btn_norma.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_norma.clicked.connect(self._mostrar_norma)
        lay.addWidget(self._btn_norma)

        btn_esq = QPushButton("Restaurar roteiro")
        btn_esq.setToolTip("Devolve o texto-guia original desta parte")
        btn_esq.clicked.connect(self._restaurar_esqueleto)
        lay.addWidget(btn_esq)
        return frame

    def _build_sidebar(self) -> SidebarPanel:
        panel = SidebarPanel()

        btn_novo = primary_button("Nova Informação", "plus")
        btn_novo.clicked.connect(self._novo_caso)
        panel.header.addWidget(btn_novo)

        self._cb_caso = NoScrollComboBox()
        self._cb_caso.currentIndexChanged.connect(self._trocar_caso)
        panel.header.addWidget(self._cb_caso)

        linha = QHBoxLayout()
        linha.setSpacing(6)
        b_ren = QPushButton("Renomear")
        b_ren.clicked.connect(self._renomear_caso)
        linha.addWidget(b_ren)
        self._btn_excluir = danger_button("Excluir")
        self._btn_excluir.clicked.connect(self._excluir_caso)
        linha.addWidget(self._btn_excluir)
        panel.header.addLayout(linha)

        btn_salvos = QPushButton("  Informações salvas…")
        btn_salvos.setIcon(draw_icon("open"))
        btn_salvos.setToolTip(
            "Ver todas as Informações já iniciadas neste computador")
        btn_salvos.clicked.connect(self._abrir_gerenciador)
        panel.header.addWidget(btn_salvos)

        # ── alternância: etapas ou identificação ──
        # As duas coisas não cabem juntas na lateral. Empilhadas, a lista
        # de partes virava uma caixinha com rolagem própria — rolar dentro
        # de um quadrado dentro de outro para achar a etapa. Separadas, a
        # lista ocupa a lateral inteira e rola com ela.
        self._abas = QHBoxLayout()
        self._abas.setSpacing(0)
        self._btn_etapas = self._aba("Etapas", 0)
        self._btn_dados = self._aba("Identificação", 1)
        panel.body.addLayout(self._abas)

        # O rótulo vai acima da barra, e não dentro: sobre o trecho
        # preenchido o texto ficava verde sobre verde, ilegível.
        self._lbl_progresso = subtext("—")
        panel.body.addWidget(self._lbl_progresso)

        self._barra = QProgressBar()
        self._barra.setTextVisible(False)
        self._barra.setFixedHeight(10)
        self._barra.setStyleSheet(
            f"QProgressBar {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 5px; }}"
            f"QProgressBar::chunk {{ background: {PALETTE['success']}; "
            "border-radius: 4px; }}")
        panel.body.addWidget(self._barra)

        self._lateral = QStackedWidget()
        panel.body.addWidget(self._lateral, 1)

        # ── página das etapas ────────────────────
        pag_etapas = QWidget()
        cx = QVBoxLayout(pag_etapas)
        cx.setContentsMargins(0, 0, 0, 0)
        self._lista = QListWidget()
        self._lista.setWordWrap(True)
        self._lista.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lista.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lista.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 9px 10px; "
            f"border-bottom: 1px solid {PALETTE['surface2']}; }}")
        self._lista.currentRowChanged.connect(self._ao_escolher_secao)
        cx.addWidget(self._lista)
        cx.addStretch()
        self._lateral.addWidget(pag_etapas)

        # ── página da identificação ──────────────
        pag_dados = QWidget()
        cd = QVBoxLayout(pag_dados)
        cd.setContentsMargins(0, 0, 0, 0)
        cd.setSpacing(14)
        self._in_processo = self._campo(cd, "Número do processo",
                                        "Ex.: 08650.000123/2026-11")
        self._in_encarregado = self._campo(cd, "Encarregado",
                                           "Ex.: João da Silva")
        self._in_matricula = self._campo(cd, "Matrícula", "Ex.: 1234567")
        self._in_unidade = self._campo(cd, "Unidade",
                                       "Ex.: DEL10 - PRF/UF")
        cd.addStretch()
        self._lateral.addWidget(pag_dados)
        self._mostrar_lateral(0)

        self._btn_previa = QPushButton("  Ver prévia da Informação")
        self._btn_previa.setIcon(draw_icon("manual", 16, PALETTE["text"]))
        self._btn_previa.setToolTip(
            "Mostra o documento montado, como entrará no SEI")
        self._btn_previa.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_previa.clicked.connect(self._ver_previa)
        panel.footer.addWidget(self._btn_previa)

        self._btn_export = output_button("Exportar HTML para o SEI")
        self._btn_export.clicked.connect(self._exportar)
        panel.footer.addWidget(self._btn_export)
        panel.add_note("Salvo automaticamente neste computador.")
        return panel

    def _aba(self, rotulo: str, indice: int) -> QPushButton:
        b = QPushButton(rotulo)
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(32)
        b.clicked.connect(lambda: self._mostrar_lateral(indice))
        self._abas.addWidget(b)
        return b

    def _mostrar_lateral(self, indice: int):
        """Troca entre a lista de etapas e os dados do procedimento."""
        self._lateral.setCurrentIndex(indice)
        for i, b in enumerate((self._btn_etapas, self._btn_dados)):
            b.setChecked(i == indice)
            b.setStyleSheet(
                (f"background: {PALETTE['gold']}; color: #0B1B2E; "
                 "font-weight: 700; border: none;"
                 if i == indice else
                 f"background: {PALETTE['bg']}; color: {PALETTE['text2']}; "
                 f"border: 1px solid {PALETTE['border']};")
                + ("border-top-left-radius:6px; border-bottom-left-radius:6px;"
                   if i == 0 else
                   "border-top-right-radius:6px; "
                   "border-bottom-right-radius:6px;"))
        if indice == 0:
            self._ajustar_altura_etapas()

    def _ajustar_altura_etapas(self):
        """A lista cresce com o conteúdo; quem rola é a lateral inteira.

        A altura sai da geometria já calculada, e não de
        `sizeHintForRow`: esta devolve a mesma altura para toda linha e
        ignora a quebra dos títulos longos, o que deixava as duas últimas
        etapas fora da caixa. Enquanto sobrar conteúdo, refaz a conta na
        volta do laço de eventos, quando a geometria está pronta.
        """
        n = self._lista.count()
        if not n:
            return
        fim = self._lista.visualItemRect(self._lista.item(n - 1)).bottom()
        if fim <= 0:
            fim = sum(self._lista.sizeHintForRow(i) for i in range(n))
        nova = fim + 2 * self._lista.frameWidth() + 3
        mudou = nova != self._lista.height()
        self._lista.setFixedHeight(nova)
        if mudou and self._lista.verticalScrollBar().maximum() > 0:
            QTimer.singleShot(0, self._ajustar_altura_etapas)

    def _campo(self, layout, rotulo: str, exemplo: str) -> QLineEdit:
        layout.addWidget(field_label(rotulo))
        campo = QLineEdit()
        campo.setPlaceholderText(exemplo)
        campo.textChanged.connect(self._ao_mudar_identificacao)
        layout.addWidget(campo)
        return campo

    # ─────────────────────────────────────
    #  FORMATAÇÃO
    # ─────────────────────────────────────

    def _alvo(self) -> QTextEdit:
        """Caixa em que a formatação deve agir.

        Nas seções de parágrafos numerados, é a do bloco em foco; o
        editor único só permanece para os casos antigos.
        """
        s = core.secao(self._secao_atual)
        if s is not None and not s.por_campos:
            alvo = self._blocos.editor_ativo()
            if alvo is not None:
                return alvo
        return self._editor

    def _novo_paragrafo(self):
        self._blocos.acrescentar(blocos.Bloco())

    def _nova_tabela(self):
        self._blocos.acrescentar(blocos.nova_tabela(3, 3))

    def _aplicar(self, fmt: QTextCharFormat):
        editor = self._alvo()
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        editor.mergeCurrentCharFormat(fmt)
        editor.setFocus()

    def _negrito(self):
        fmt = QTextCharFormat()
        editor = self._alvo()
        peso = (QFont.Weight.Normal
                if editor.fontWeight() > QFont.Weight.Normal
                else QFont.Weight.Bold)
        fmt.setFontWeight(peso)
        self._aplicar(fmt)

    def _italico(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._alvo().fontItalic())
        self._aplicar(fmt)

    def _sublinhado(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self._alvo().fontUnderline())
        self._aplicar(fmt)

    def _escolher_cor(self):
        cor = QColorDialog.getColor(self._alvo().textColor(), self,
                                    "Cor do texto")
        if cor.isValid():
            self._aplicar_cor(cor)

    def _aplicar_cor(self, cor: QColor):
        fmt = QTextCharFormat()
        fmt.setForeground(cor)
        self._aplicar(fmt)

    def _alinhar(self, alinhamento):
        alvo = self._alvo()
        alvo.setAlignment(alinhamento)
        alvo.setFocus()

    def _sincronizar_botoes(self, *_a):
        alvo = self._alvo()
        self._btn_b.setChecked(alvo.fontWeight() > QFont.Weight.Normal)
        self._btn_i.setChecked(alvo.fontItalic())
        self._btn_u.setChecked(alvo.fontUnderline())

    def _inserir_imagem(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Inserir imagem", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not caminho:
            return
        img = QImage(caminho)
        if img.isNull():
            QMessageBox.warning(self, "Imagem inválida",
                                "Não foi possível abrir esta imagem.")
            return
        try:
            nome = self._acervo.guardar_imagem(self._caso.id, caminho)
        except OSError as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível copiar:\n{e}")
            return

        editor = self._alvo()
        # Nos blocos a caixa é estreita e não tem rolagem horizontal: uma
        # imagem maior que ela sairia cortada na tela.
        cabe = max(200, editor.viewport().width() - 24)
        largura = min(img.width(), IMAGEM_LARGURA_MAX, cabe)
        cursor = editor.textCursor()
        # Recolhe a seleção antes de inserir: com texto selecionado,
        # `insertHtml` o substituiria pela imagem, e o encarregado perderia
        # o trecho sem perceber. A imagem entra depois do que estava
        # selecionado.
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionEnd())
        cursor.insertHtml(
            f'<p><img src="{core.PREFIXO_IMAGEM}{nome}" width="{largura}"></p>')
        editor.setTextCursor(cursor)
        editor.setFocus()
        self.status_msg.emit(f"Imagem inserida: {Path(caminho).name}")

    # ─────────────────────────────────────
    #  SEÇÕES
    # ─────────────────────────────────────

    def _atualizar_roteiro(self):
        self._lista.blockSignals(True)
        self._lista.clear()
        for s in core.SECOES:
            parte = self._caso.partes.get(s.id)
            if parte is not None and parte.concluida:
                marca, cor = "✓", PALETTE["success"]
            elif self._caso.iniciada(s.id):
                marca, cor = "•", PALETTE["warning"]
            else:
                marca, cor = "○", PALETTE["text3"]
            item = QListWidgetItem(f" {marca}  {s.nome_curto}")
            item.setForeground(QColor(cor))
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self._lista.addItem(item)
        idx = next((i for i, s in enumerate(core.SECOES)
                    if s.id == self._secao_atual), 0)
        self._lista.setCurrentRow(idx)
        self._lista.blockSignals(False)
        self._ajustar_altura_etapas()

        feitas, total = self._caso.progresso()
        self._barra.setMaximum(max(1, total))
        self._barra.setValue(feitas)
        self._lbl_progresso.setText(
            f"{feitas} de {total} partes concluídas"
            + ("  ·  pronto para exportar" if feitas == total and total else ""))
        self._btn_export.setEnabled(feitas > 0)

    def _ao_escolher_secao(self, linha: int):
        if linha < 0 or linha >= len(core.SECOES):
            return
        self._guardar_secao()
        self._abrir_secao(core.SECOES[linha].id)

    def _abrir_secao(self, secao_id: str):
        s = core.secao(secao_id)
        if s is None:
            return
        self._secao_atual = secao_id
        parte = self._caso.parte(secao_id)

        self._carregando = True
        if s.por_campos:
            self._montar_formulario(s, parte)
            self._pilha.setCurrentIndex(1)
        else:
            if not parte.blocos:
                # Casos abertos antes de a parte ganhar roteiro pronto.
                parte.blocos = core.blocos_do_roteiro(s)
            if len(parte.blocos) > 8:
                # Elemento longo: avisa que está montando, em vez de
                # deixar a página meia-feita à mostra.
                self._pilha.setCurrentWidget(self._sinal_carga)
                self._sinal_carga.comecar()
                # `repaint` e não `processEvents`: este trecho roda dentro
                # do tratador de seleção da lista, e processar eventos aqui
                # reentraria na troca de etapa.
                self._sinal_carga.repaint()
            self._blocos.definir_pasta_imagens(
                self._acervo.pasta_imagens(self._caso.id))
            self._blocos.carregar(parte.blocos, self._numero_da_secao(s.id))
            parte.blocos = self._blocos.blocos
            self._sinal_carga.parar()
            self._pilha.setCurrentWidget(self._blocos)
        self._carregando = False
        self._barra_formatacao.setVisible(not s.por_campos)
        self._btn_paragrafo.setVisible(not s.por_campos)
        self._btn_tabela.setVisible(not s.por_campos)

        self._lbl_secao.setText(s.titulo)
        self._lbl_resumo.setText(s.resumo)
        self._chk_concluida.setChecked(parte.concluida)
        self._btn_norma.setEnabled(bool(s.orientacao or s.texto_norma))
        self.status_msg.emit(f"{s.titulo} — {s.resumo}")

    def _numero_da_secao(self, secao_id: str) -> int:
        """Posição do elemento entre os numerados, para compor 1.1, 2.1…"""
        numero = 0
        for s in core.SECOES:
            if s.numerada:
                numero += 1
            if s.id == secao_id:
                return max(1, numero)
        return 1

    def _guardar_secao(self):
        if self._carregando or not self._secao_atual:
            return
        s = core.secao(self._secao_atual)
        parte = self._caso.parte(self._secao_atual)
        if s is not None and s.por_campos:
            for campo in s.campos:
                w = self._campos.get(campo.id)
                if w is None:
                    continue
                parte.valores[campo.id] = (
                    w.toPlainText() if isinstance(w, QPlainTextEdit)
                    else w.text()).strip()
        else:
            parte.blocos = self._blocos.blocos

    def _ao_editar(self):
        if self._carregando:
            return
        self._guardar_secao()
        self._lbl_salvo.setText("salvando…")
        self._save_timer.start()

    def _alternar_concluida(self):
        parte = self._caso.parte(self._secao_atual)
        parte.concluida = self._chk_concluida.isChecked()
        self._atualizar_roteiro()
        self._save_timer.start()
        s = core.secao(self._secao_atual)
        self.status_msg.emit(
            f"{s.titulo}: {'concluída' if parte.concluida else 'em aberto'}")

    def _restaurar_esqueleto(self):
        s = core.secao(self._secao_atual)
        if s is None:
            return
        if QMessageBox.question(
            self, "Restaurar roteiro",
            f"Substituir o texto de “{s.titulo}” pelo roteiro original?\n\n"
            "O que estiver escrito nesta parte será perdido.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        parte = self._caso.parte(s.id)
        if s.por_campos:
            parte.valores = {c.id: c.padrao for c in s.campos}
        else:
            parte.blocos = core.blocos_do_roteiro(s)
            parte.html = s.esqueleto
        self._abrir_secao(s.id)
        self._atualizar_roteiro()
        self._save_timer.start()

    def _mostrar_norma(self):
        s = core.secao(self._secao_atual)
        if s is not None:
            NormaDialog(s, self).exec()

    # ─────────────────────────────────────
    #  CASOS
    # ─────────────────────────────────────

    def _recarregar_casos(self):
        self._cb_caso.blockSignals(True)
        self._cb_caso.clear()
        for c in self._casos:
            self._cb_caso.addItem(c.nome, c.id)
        idx = next((i for i, c in enumerate(self._casos)
                    if c.id == self._caso.id), 0)
        self._cb_caso.setCurrentIndex(idx)
        self._cb_caso.blockSignals(False)
        self._btn_excluir.setEnabled(len(self._casos) > 1)
        self._preencher_identificacao()

    def _preencher_identificacao(self):
        self._carregando = True
        self._in_processo.setText(self._caso.numero_processo)
        self._in_encarregado.setText(self._caso.encarregado)
        self._in_matricula.setText(self._caso.matricula)
        self._in_unidade.setText(self._caso.unidade)
        self._carregando = False

    def _ao_mudar_identificacao(self):
        if self._carregando:
            return
        self._caso.numero_processo = self._in_processo.text().strip()
        self._caso.encarregado = self._in_encarregado.text().strip()
        self._caso.matricula = self._in_matricula.text().strip()
        self._caso.unidade = self._in_unidade.text().strip()
        self._save_timer.start()

    def _trocar_caso(self, idx: int):
        if idx < 0 or idx >= len(self._casos):
            return
        self._guardar_secao()
        self._gravar()
        self._caso = self._casos[idx]
        self._preencher_identificacao()
        self._secao_atual = core.SECOES[0].id if core.SECOES else ""
        self._abrir_secao(self._secao_atual)
        self._atualizar_roteiro()
        self.status_msg.emit(f"Informação: {self._caso.nome}")

    def _novo_caso(self):
        nome, ok = QInputDialog.getText(
            self, "Nova Informação", "Nome do caso:")
        if not ok:
            return
        self._guardar_secao()
        self._gravar()
        caso = core.CasoIPS(nome=nome.strip() or "Nova Informação")
        self._casos.append(caso)
        self._caso = caso
        self._recarregar_casos()
        self._secao_atual = core.SECOES[0].id if core.SECOES else ""
        self._abrir_secao(self._secao_atual)
        self._atualizar_roteiro()
        self._gravar()
        self.status_msg.emit(f"Informação criada: {caso.nome}")

    def _renomear_caso(self):
        nome, ok = QInputDialog.getText(self, "Renomear", "Nome do caso:",
                                        text=self._caso.nome)
        if not ok or not nome.strip():
            return
        self._caso.nome = nome.strip()
        self._recarregar_casos()
        self._gravar()

    def _excluir_caso(self):
        if len(self._casos) <= 1:
            return
        if QMessageBox.question(
            self, "Excluir Informação",
            f"Excluir “{self._caso.nome}” e tudo o que foi escrito nela?\n\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._casos.remove(self._caso)
        self._caso = self._casos[0]
        self._recarregar_casos()
        self._secao_atual = core.SECOES[0].id if core.SECOES else ""
        self._abrir_secao(self._secao_atual)
        self._atualizar_roteiro()
        self._gravar()


    # ─────────────────────────────────────
    #  FORMULÁRIO DAS SEÇÕES POR CAMPOS
    # ─────────────────────────────────────

    def _montar_formulario(self, s: core.Secao, parte: core.Parte):
        antigo = self._form_area.takeWidget()
        if antigo is not None:
            antigo.deleteLater()
        self._campos = {}

        corpo = QWidget()
        corpo.setStyleSheet(f"background: {PALETTE['bg']};")
        lay = QVBoxLayout(corpo)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(14)

        for campo in s.campos:
            bloco = QWidget()
            bl = QVBoxLayout(bloco)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(5)
            bl.addWidget(field_label(campo.rotulo))

            valor = parte.valores.get(campo.id, campo.padrao)
            if campo.tipo == "paragrafo":
                w = QPlainTextEdit()
                w.setPlainText(valor)
                w.setPlaceholderText(campo.exemplo)
                w.setFixedHeight(150)
                w.textChanged.connect(self._ao_editar)
            else:
                w = QLineEdit(valor)
                w.setPlaceholderText(campo.exemplo)
                w.textChanged.connect(self._ao_editar)
            w.setStyleSheet(
                "background: #FFFFFF; color: #16233A; "
                f"border: 1px solid {PALETTE['border']}; border-radius: 6px; "
                "padding: 8px 10px; font-family: 'Times New Roman'; "
                "font-size: 13px;")
            bl.addWidget(w)
            self._campos[campo.id] = w

            if campo.ajuda:
                bl.addWidget(subtext(campo.ajuda, wrap=True))
            lay.addWidget(bloco)

        lay.addStretch()
        self._form_area.setWidget(corpo)

    # ─────────────────────────────────────
    #  INFORMAÇÕES SALVAS
    # ─────────────────────────────────────

    def _abrir_gerenciador(self):
        self._guardar_secao()
        self._gravar()
        dlg = CasosDialog(self._casos, self._caso.id, self._acervo, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.escolhido:
            return
        idx = next((i for i, c in enumerate(self._casos)
                    if c.id == dlg.escolhido), None)
        if idx is not None and self._casos[idx] is not self._caso:
            self._cb_caso.setCurrentIndex(idx)   # dispara _trocar_caso

    # ─────────────────────────────────────
    #  PRÉVIA E PDF
    # ─────────────────────────────────────

    def _ver_previa(self):
        self._guardar_secao()
        pasta = self._acervo.pasta_imagens(self._caso.id)
        dlg = PreviaDialog(self._caso, pasta, self._exportar,
                           self._exportar_pdf, self)
        dlg.exec()

    def _documento_para_impressao(self) -> QTextDocument:
        """Documento montado, pronto para virar PDF."""
        pasta = self._acervo.pasta_imagens(self._caso.id)
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Times New Roman", 11))
        doc.setHtml(core.build_html(self._caso, pasta_imagens=pasta))
        return doc

    def _exportar_pdf(self):
        self._guardar_secao()
        base = "".join(ch for ch in self._caso.nome
                       if ch.isalnum() or ch in " -_").strip() or "informacao"
        from ..sessao import destino_para_dialogo
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar PDF",
            destino_para_dialogo(self, "Termos", f"{base}.pdf"),
            "Documento PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            escritor = preparar_escritor(
                caminho, f"Informação — {self._caso.nome}")

            imprimir_documento(self._documento_para_impressao(), escritor)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao exportar",
                                 f"Não foi possível gerar o PDF:\n{e}")
            return
        QMessageBox.information(
            self, "PDF gerado",
            f"Documento salvo em:\n{caminho}\n\n"
            "O PDF serve para conferência e arquivo. Para o SEI, use a "
            "exportação em HTML.")
        self.status_msg.emit(f"PDF exportado: {Path(caminho).name}")

    # ─────────────────────────────────────
    #  PERSISTÊNCIA
    # ─────────────────────────────────────

    def _gravar(self):
        self._guardar_secao()
        self._caso.atualizado = time.time()
        try:
            self._acervo.gravar(self._casos, self._caso.id)
            self._lbl_salvo.setText(
                "salvo " + datetime.datetime.now().strftime("%H:%M:%S"))
        except OSError as e:
            self._lbl_salvo.setText("não foi possível salvar")
            self.status_msg.emit(f"Falha ao salvar: {e}")
        self._atualizar_roteiro()

    def _gravar_agora(self):
        self._save_timer.stop()
        self._gravar()
        self.status_msg.emit("Informação salva")

    # ─────────────────────────────────────
    #  EXPORTAÇÃO
    # ─────────────────────────────────────

    def _exportar(self):
        self._guardar_secao()
        pendentes = self._caso.pendentes()
        if pendentes:
            nomes = "\n• ".join(s.titulo for s in pendentes[:8])
            if QMessageBox.question(
                self, "Partes em aberto",
                f"Ainda não foram concluídas:\n\n• {nomes}\n\n"
                "Exportar assim mesmo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return

        base = "".join(ch for ch in self._caso.nome
                       if ch.isalnum() or ch in " -_").strip() or "informacao"
        from ..sessao import destino_para_dialogo
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar HTML para o SEI",
            destino_para_dialogo(self, "Termos", f"{base}.html"),
            "Documento HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith(".html"):
            caminho += ".html"

        try:
            pasta_img = self._acervo.pasta_imagens(self._caso.id)
            documento = core.build_html(self._caso, pasta_imagens=pasta_img)
            Path(caminho).write_text(documento, encoding="utf-8")
            copiadas = self._copiar_imagens(Path(caminho), pasta_img)
        except OSError as e:
            QMessageBox.critical(self, "Erro ao exportar",
                                 f"Não foi possível gravar:\n{e}")
            return

        self._relatar_exportacao(Path(caminho), copiadas)

    def _copiar_imagens(self, destino_html: Path, pasta_img: Path) -> list[str]:
        """Salva as imagens também soltas, ao lado do HTML."""
        import shutil
        usadas: list[str] = []
        for s in core.SECOES:
            usadas += core.imagens_referenciadas(
                self._caso.partes.get(s.id, core.Parte(s.id)).html)
        if not usadas:
            return []
        pasta = destino_html.with_suffix("")
        pasta = pasta.parent / f"{pasta.name}-imagens"
        pasta.mkdir(exist_ok=True)
        saidas = []
        for i, nome in enumerate(dict.fromkeys(usadas), 1):
            origem = pasta_img / nome
            if not origem.exists():
                continue
            alvo = pasta / f"imagem-{i:02d}{origem.suffix}"
            shutil.copy2(origem, alvo)
            saidas.append(alvo.name)
        return saidas

    def _relatar_exportacao(self, caminho: Path, imagens: list[str]):
        linhas = ["Documento gerado em:", str(caminho), "",
                  "No SEI: Incluir Documento → Externo/Editor → "
                  "importar o arquivo HTML."]
        if imagens:
            # O importador do SEI costuma descartar imagens em base64.
            # Avisar aqui evita o servidor descobrir isso só depois de
            # subir o documento e vê-lo sem as figuras.
            linhas += [
                "",
                f"⚠ O documento tem {len(imagens)} imagem(ns) embutida(s).",
                "O importador do SEI pode descartá-las. Se isso acontecer, "
                "reinsira-as pelo editor do SEI — os arquivos foram salvos "
                "em:",
                str(caminho.parent / f"{caminho.stem}-imagens"),
            ]
        QMessageBox.information(self, "Exportado", "\n".join(linhas))
        self.status_msg.emit(f"HTML exportado: {caminho.name}")

    # ─────────────────────────────────────
    #  CICLO DE VIDA
    # ─────────────────────────────────────

    def on_activated(self):
        feitas, total = self._caso.progresso()
        self.status_msg.emit(
            f"{self._caso.nome} — {feitas} de {total} partes concluídas")

    def on_deactivated(self):
        self._gravar()

    def shutdown(self):
        self._gravar()
