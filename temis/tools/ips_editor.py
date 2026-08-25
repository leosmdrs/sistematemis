"""
Editor de blocos numerados do corpo da Informação.

Cada parágrafo é um bloco com nível e estilo próprios; o marcador (1.1,
1.1.1, a), I –) aparece à esquerda, calculado, e nunca é digitado. Inserir,
mover ou remover um parágrafo renumera o resto sozinho.

Teclas, seguindo o que se espera de um editor de listas:

* **Enter** cria o parágrafo seguinte no mesmo nível
* **Shift+Enter** quebra a linha dentro do mesmo parágrafo
* **Tab / Shift+Tab** aprofunda e recua o nível
* **Backspace** num parágrafo vazio funde com o anterior
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QImage, QStandardItem,
                         QStandardItemModel, QTextCharFormat, QTextCursor,
                         QTextDocument, QTextDocumentFragment)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QFrame,
    QTextEdit, QScrollArea, QComboBox, QTableWidget, QTableWidgetItem,
    QSizePolicy, QHeaderView,
)

from ..icons import draw_icon
from ..theme import PALETTE
from ..widgets import NoScrollComboBox
from . import ips_blocos as B
from . import ips_core as core

ALTURA_MIN = 46

_FONTE = None


def fonte_paragrafo() -> QFont:
    """Uma instância só, compartilhada por todos os parágrafos.

    Criada na primeira chamada, e não na importação do módulo: este
    módulo é carregado antes de existir QApplication, e construir um
    QFont antes disso não é suportado pelo Qt.
    """
    global _FONTE
    if _FONTE is None:
        _FONTE = QFont("Times New Roman", 12)
    return _FONTE

#: Largura da coluna de controles à direita de cada bloco. Fixa, para que
#: todos os blocos tenham as ações na mesma coluna, seja qual for o nível.
LARGURA_CONTROLES = 212
LADO_BOTAO = 26


_MODELO_ESTILOS = None


def _modelo_estilos() -> QStandardItemModel:
    global _MODELO_ESTILOS
    if _MODELO_ESTILOS is None:
        _MODELO_ESTILOS = QStandardItemModel()
        for chave, rotulo in B.ESTILOS.items():
            item = QStandardItem(rotulo)
            item.setData(chave, Qt.ItemDataRole.UserRole - 1)
            _MODELO_ESTILOS.appendRow(item)
    return _MODELO_ESTILOS


#: O que sobrevive de uma colagem, e nada mais.
#:
#: Texto colado de fora — de um ofício em Word, de uma página, de um
#: e-mail — chega carregado: fonte da origem, corpo maior ou menor, cor,
#: realce, recuo de lista. Colado cru, o parágrafo da Informação passa a
#: ter três tipografias e a peça denuncia de onde cada trecho veio.
#:
#: Do que vem de fora guarda-se só o que carrega sentido jurídico:
#: negrito, itálico e sublinhado. Um destaque desses foi posto por
#: alguém de propósito. Já o corpo 14 do documento de origem não quer
#: dizer nada aqui.
GRIFOS_QUE_FICAM = ("negrito", "itálico", "sublinhado")


def normalizar_colagem(doc: QTextDocument) -> None:
    """Põe o documento colado na tipografia da peça, no lugar.

    Três coisas acontecem em cada parágrafo:

    **A tipografia vira a do sistema.** Família e corpo do parágrafo,
    preservando apenas negrito, itálico e sublinhado. Cor de letra,
    realce de fundo e tachado caem.

    **O link some, o texto fica.** Colar de uma página traz o endereço
    embutido; numa peça que vai a processo isso vira texto azul
    sublinhado que ninguém pode clicar. O que interessa é o que está
    escrito.

    **Marcador e numeração são ignorados.** A Informação numera os
    próprios parágrafos, calculando o marcador a partir do nível — um
    `1.` vindo de fora concorreria com essa numeração e a peça sairia com
    duas contagens. O texto do item entra como parágrafo comum, e o
    recuo que a lista impunha vai junto.

    Tabela continua tabela: ali a estrutura carrega significado, e
    desmontá-la em parágrafos perderia a relação entre coluna e valor. O
    que se ajusta dentro dela é a tipografia, como no resto.
    """
    padrao = fonte_paragrafo()
    doc.setDefaultFont(padrao)

    # ── primeiro se lê tudo; só depois se altera ──
    #
    # Não é organização: é a correção de uma queda. A versão anterior
    # trocava o formato de cada trecho enquanto percorria os trechos, e
    # trocar formato é justamente o que faz o Qt **fundir** trechos
    # vizinhos que passaram a ser iguais — que é o efeito inevitável de
    # normalizar. O iterador seguia apontando para o que deixara de
    # existir, e o programa morria por violação de acesso, sem mensagem,
    # levando junto o texto ainda não gravado.
    #
    # Guardar posição e comprimento em vez do trecho é o que torna isso
    # seguro: mudar formato não muda o tamanho do texto, de modo que as
    # posições recolhidas continuam valendo depois de qualquer fusão.
    recolhidos = []      # (posição, comprimento, negrito, itálico, sublinhado)
    inicios_de_bloco = []

    bloco = doc.begin()
    while bloco.isValid():
        inicios_de_bloco.append(bloco.position())
        pedaco = bloco.begin()
        while not pedaco.atEnd():
            trecho = pedaco.fragment()
            if trecho.isValid() and trecho.length():
                formato = trecho.charFormat()
                recolhidos.append((
                    trecho.position(),
                    trecho.length(),
                    formato.fontWeight() >= QFont.Weight.Bold,
                    formato.fontItalic(),
                    formato.fontUnderline(),
                ))
            pedaco += 1
        bloco = bloco.next()

    # ── agora sim, as alterações ──
    for posicao in inicios_de_bloco:
        cursor = QTextCursor(doc)
        cursor.setPosition(posicao)
        alvo = cursor.block()
        if not alvo.isValid():
            continue
        lista = alvo.textList()
        if lista is not None:
            lista.remove(alvo)
        formato = alvo.blockFormat()
        formato.setIndent(0)
        formato.setLeftMargin(0)
        formato.setRightMargin(0)
        formato.setTextIndent(0)
        # Sem esta linha, texto vindo de origem com `<pre>` ou
        # `white-space:pre` chegava marcado como "não quebrar linha" e
        # continuava assim: o parágrafo corria numa linha só, saindo pela
        # direita da caixa, e no documento o marcador ficava sozinho na
        # linha de cima. Custou dois parágrafos de uma Informação real
        # para aparecer, porque a marca não se vê — só o efeito dela.
        formato.setNonBreakableLines(False)
        cursor.setBlockFormat(formato)

    for posicao, tamanho, negrito, italico, sublinhado in recolhidos:
        # Formato novo em folha, e não o antigo remendado: assim o que
        # não for explicitamente recolocado — cor, realce, tachado,
        # endereço do link — desaparece por construção, em vez de
        # depender de uma lista de coisas a limpar que alguém teria de
        # manter em dia.
        novo = QTextCharFormat()
        novo.setFont(padrao)
        novo.setFontWeight(QFont.Weight.Bold if negrito
                           else QFont.Weight.Normal)
        novo.setFontItalic(italico)
        novo.setFontUnderline(sublinhado)

        seleção = QTextCursor(doc)
        seleção.setPosition(posicao)
        seleção.setPosition(posicao + tamanho,
                            QTextCursor.MoveMode.KeepAnchor)
        seleção.setCharFormat(novo)


class _EditorParagrafo(QTextEdit):
    """Caixa de texto de um bloco, que cresce com o conteúdo."""

    novo_bloco = pyqtSignal()
    aprofundar = pyqtSignal()
    recuar = pyqtSignal()
    fundir_anterior = pyqtSignal()
    subir_foco = pyqtSignal()
    descer_foco = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pasta_imagens = None
        self.setAcceptRichText(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pintar(False)
        self.document().setDefaultFont(fonte_paragrafo())
        self.document().documentLayout().documentSizeChanged.connect(
            self._ajustar_altura)
        self.setFixedHeight(ALTURA_MIN)

    def pintar(self, exemplo: bool):
        """Exemplo do roteiro fica acinzentado; texto do caso, preto.

        A aparência vem da folha única do editor, e não de uma folha por
        caixa: com meia centena de parágrafos, um `setStyleSheet` em cada
        um custava caro o bastante para a troca de etapa piscar.
        """
        anterior = self.objectName()
        self.setObjectName("exemplo" if exemplo else "paragrafo")
        if anterior and anterior != self.objectName():
            # Repolir custa uma releitura inteira da folha de estilo. Só
            # vale quando a caixa muda de estado em uso; ao nascer, o
            # nome basta.
            self.style().unpolish(self)
            self.style().polish(self)

    def insertFromMimeData(self, fonte):
        """Tudo o que entra por colagem ou arrasto passa por aqui.

        Imagem segue pelo caminho de sempre — ela não tem tipografia a
        corrigir, e o editor já sabe guardá-la na pasta do caso.

        O `try` que envolve a normalização não é zelo excessivo, é o que
        separa um contratempo de um desastre. Este método é chamado pelo
        Qt, em C++; uma exceção de Python aqui não vira mensagem de erro
        — **encerra o processo**, e com ele o texto que o encarregado
        ainda não gravou. Se algo der errado ao normalizar, o texto entra
        sem formatação nenhuma, que é feio e recuperável.
        """
        if fonte.hasImage() or fonte.hasUrls():
            super().insertFromMimeData(fonte)
            return

        if fonte.hasHtml():
            try:
                doc = QTextDocument()
                doc.setHtml(fonte.html())
                normalizar_colagem(doc)
                # Fragmento, e não texto: é o que preserva a tabela e os
                # grifos que sobreviveram à normalização.
                self.textCursor().insertFragment(QTextDocumentFragment(doc))
                return
            except Exception as e:                          # noqa: BLE001
                self._anotar_falha_de_colagem(e)

        if fonte.hasText():
            self.textCursor().insertText(fonte.text())
            return

        try:
            super().insertFromMimeData(fonte)
        except Exception as e:                              # noqa: BLE001
            self._anotar_falha_de_colagem(e)

    def desfazer_linha_unica(self):
        """Tira a marca de "não quebrar linha" de todos os parágrafos.

        A marca não se vê — vê-se o efeito: o texto corre numa linha só,
        some pela direita da caixa e, no documento gerado, empurra o
        marcador para a linha de cima. Ela entra por colagem de origem
        que usa `<pre>` ou `white-space:pre`, e ficava gravada no caso.

        Silencioso quando não há nada a fazer, que é o caso comum: sem
        isso, abrir uma Informação marcaria todos os parágrafos como
        alterados e dispararia gravação à toa.
        """
        doc = self.document()
        alvos = []
        bloco = doc.begin()
        while bloco.isValid():
            if bloco.blockFormat().nonBreakableLines():
                alvos.append(bloco.position())
            bloco = bloco.next()
        if not alvos:
            return
        for posicao in alvos:
            cursor = QTextCursor(doc)
            cursor.setPosition(posicao)
            formato = cursor.block().blockFormat()
            formato.setNonBreakableLines(False)
            cursor.setBlockFormat(formato)

    @staticmethod
    def _anotar_falha_de_colagem(erro: Exception):
        """Guarda a falha em disco, já que a tela não pode mostrá-la.

        Ninguém vai reproduzir de propósito, e o defeito só aparece com o
        conteúdo que a pessoa tinha copiado naquele instante. O arquivo
        registra o tipo do erro e onde ele ocorreu — nunca o texto
        colado, que é material de apuração.
        """
        import datetime
        import os
        import traceback
        from pathlib import Path

        try:
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            destino = Path(base) / "SistemaTemis" / "falhas-colagem.txt"
            destino.parent.mkdir(parents=True, exist_ok=True)
            quando = datetime.datetime.now().astimezone().isoformat(
                timespec="seconds")
            with open(destino, "a", encoding="utf-8") as f:
                f.write(f"\n--- {quando} — {type(erro).__name__}: {erro}\n")
                f.write("".join(traceback.format_tb(erro.__traceback__)))
        except Exception:                                   # noqa: BLE001
            pass

    def loadResource(self, tipo: int, nome: QUrl):
        """Resolve `imagens/<arquivo>` na pasta do caso.

        Sem isto a imagem inserida aparece como um ícone de documento
        quebrado: ela não está embutida no HTML, está em disco, e o editor
        precisa saber onde procurar.
        """
        caminho = nome.toString()
        if (tipo == QTextDocument.ResourceType.ImageResource
                and caminho.startswith(core.PREFIXO_IMAGEM)
                and self.pasta_imagens is not None):
            arq = self.pasta_imagens / caminho[len(core.PREFIXO_IMAGEM):]
            if arq.exists():
                return QImage(str(arq))
        return super().loadResource(tipo, nome)

    def _ajustar_altura(self, *_a):
        # A caixa acompanha o texto: uma barra de rolagem por parágrafo
        # tornaria a leitura do conjunto impossível.
        alt = int(self.document().size().height()) + 16
        self.setFixedHeight(max(ALTURA_MIN, alt))

    def keyPressEvent(self, ev):
        tecla = ev.key()
        mod = ev.modifiers()

        if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if mod & Qt.KeyboardModifier.ShiftModifier:
                self.textCursor().insertText(" ")   # quebra de linha
                return
            self.novo_bloco.emit()
            return

        if tecla == Qt.Key.Key_Tab and not (mod & Qt.KeyboardModifier.ShiftModifier):
            self.aprofundar.emit()
            return
        if tecla == Qt.Key.Key_Backtab or (
                tecla == Qt.Key.Key_Tab and mod & Qt.KeyboardModifier.ShiftModifier):
            self.recuar.emit()
            return

        if (tecla == Qt.Key.Key_Backspace
                and not self.textCursor().hasSelection()
                and self.textCursor().position() == 0):
            self.fundir_anterior.emit()
            return

        cursor = self.textCursor()
        if tecla == Qt.Key.Key_Up and cursor.blockNumber() == 0:
            self.subir_foco.emit()
            return
        if (tecla == Qt.Key.Key_Down
                and cursor.blockNumber() == self.document().blockCount() - 1):
            self.descer_foco.emit()
            return

        super().keyPressEvent(ev)


class _TabelaWidget(QTableWidget):
    """Grade editável de um bloco de tabela."""

    alterada = pyqtSignal()

    def __init__(self, bloco: B.Bloco, parent=None):
        super().__init__(bloco.linhas(), bloco.colunas(), parent)
        self.bloco = bloco
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.setStyleSheet(
            "QTableWidget { background: #FFFFFF; color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 5px; "
            "gridline-color: #C8CEDA; }"
            "QTableWidget::item { padding: 4px; }")
        self.setFont(QFont("Times New Roman", 11))
        self._preencher()
        self.itemChanged.connect(self._ao_editar)
        self._ajustar_altura()

    def _preencher(self):
        self.blockSignals(True)
        self.setRowCount(self.bloco.linhas())
        self.setColumnCount(self.bloco.colunas())
        for i, linha in enumerate(self.bloco.celulas):
            for j, cel in enumerate(linha):
                item = QTableWidgetItem(B.texto_visivel(cel))
                if i == 0 and self.bloco.cabecalho:
                    fonte = item.font()
                    fonte.setBold(True)
                    item.setFont(fonte)
                    item.setBackground(QColor("#E8EAF0"))
                self.setItem(i, j, item)
        self.blockSignals(False)

    def _ao_editar(self, item: QTableWidgetItem):
        while len(self.bloco.celulas) <= item.row():
            self.bloco.inserir_linha()
        self.bloco.celulas[item.row()][item.column()] = item.text()
        self.alterada.emit()

    def _ajustar_altura(self):
        alt = sum(self.rowHeight(i) for i in range(self.rowCount())) + 6
        self.setFixedHeight(max(70, alt))

    def recarregar(self):
        self._preencher()
        self._ajustar_altura()


class BlocoWidget(QFrame):
    """Um bloco na tela: marcador, controles e conteúdo."""

    alterado = pyqtSignal()
    pediu_novo = pyqtSignal(object)
    pediu_remover = pyqtSignal(object)
    pediu_nivel = pyqtSignal(object, int)
    pediu_mover = pyqtSignal(object, int)
    pediu_fundir = pyqtSignal(object)
    pediu_foco = pyqtSignal(object, int)
    ganhou_foco = pyqtSignal(object)

    def __init__(self, bloco: B.Bloco, parent=None):
        super().__init__(parent)
        self.bloco = bloco
        self.editor: _EditorParagrafo | None = None
        self.tabela: _TabelaWidget | None = None
        self._btn_adotar: QPushButton | None = None

        # Sem folha de estilo própria: uma folha no quadro obriga o Qt a
        # reavaliar o estilo de toda a subárvore a cada filho acrescentado,
        # e são dez por parágrafo. O fundo vem da folha única do editor.
        self.setObjectName("bloco")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(8)
        # Tudo encostado no topo: sem isto o Qt centraliza verticalmente a
        # caixa de texto em relação aos controles, e a primeira linha do
        # parágrafo deixa de coincidir com o marcador.
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._recuo = QWidget()
        self._recuo.setFixedWidth(0)
        lay.addWidget(self._recuo)

        self._marcador = QLabel("")
        self._marcador.setFixedWidth(62)
        self._marcador.setAlignment(Qt.AlignmentFlag.AlignRight
                                    | Qt.AlignmentFlag.AlignTop)
        self._marcador.setStyleSheet(
            f"color: {PALETTE['gold']}; font-weight: 700; padding-top: 9px;")
        lay.addWidget(self._marcador)

        if bloco.tipo == B.TABELA:
            self.tabela = _TabelaWidget(bloco)
            self.tabela.alterada.connect(self.alterado)
            lay.addWidget(self.tabela, 1, Qt.AlignmentFlag.AlignTop)
        else:
            self.editor = _EditorParagrafo()
            self.editor.pintar(bloco.exemplo)
            self.editor.setHtml(bloco.html)
            # Conserta o que já está gravado, e não só o que se cola de
            # agora em diante: parágrafos colados antes da correção
            # ficaram marcados como "não quebrar linha" e continuariam
            # correndo para fora da caixa a cada abertura. Isto os
            # endireita ao abrir, sem que ninguém precise redigitar.
            self.editor.desfazer_linha_unica()
            self.editor.textChanged.connect(self._ao_editar)
            self.editor.novo_bloco.connect(lambda: self.pediu_novo.emit(self))
            self.editor.aprofundar.connect(
                lambda: self.pediu_nivel.emit(self, +1))
            self.editor.recuar.connect(lambda: self.pediu_nivel.emit(self, -1))
            self.editor.fundir_anterior.connect(
                lambda: self.pediu_fundir.emit(self))
            self.editor.subir_foco.connect(
                lambda: self.pediu_foco.emit(self, -1))
            self.editor.descer_foco.connect(
                lambda: self.pediu_foco.emit(self, +1))
            self.editor.installEventFilter(self)
            lay.addWidget(self.editor, 1, Qt.AlignmentFlag.AlignTop)

        lay.addWidget(self._controles(), 0, Qt.AlignmentFlag.AlignTop)
        self.atualizar_recuo()

    # ── controles ────────────────────────────────
    def _botao(self, icone: str, dica: str, slot, cor: str = "") -> QPushButton:
        b = QPushButton()
        b.setIcon(draw_icon(icone, 13, cor or PALETTE["text2"]))
        b.setToolTip(dica)
        b.setFixedSize(LADO_BOTAO, LADO_BOTAO)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def _controles(self) -> QWidget:
        """Coluna de ações, de largura fixa e encostada à direita.

        Uma grade só, e não fileiras aninhadas: cada layout acrescentado a
        outro reparenta os seus widgets, e o Qt reavalia o estilo de todos
        eles. Num elemento de meia centena de parágrafos isso respondia
        por boa parte do tempo de abertura.

        A coluna não acompanha o recuo do bloco: as ações de todos os
        parágrafos ficam alinhadas na mesma margem.
        """
        caixa = QWidget()
        caixa.setFixedWidth(LARGURA_CONTROLES)
        grade = QGridLayout(caixa)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(4)
        grade.setVerticalSpacing(4)

        acoes = [
            ("seta_cima", "Mover para cima",
             lambda: self.pediu_mover.emit(self, -1), ""),
            ("seta_baixo", "Mover para baixo",
             lambda: self.pediu_mover.emit(self, +1), ""),
            ("trash", "Remover este bloco",
             lambda: self.pediu_remover.emit(self), PALETTE["danger"]),
        ]

        if self.bloco.tipo == B.TEXTO:
            self._cb_estilo = NoScrollComboBox(ajustar_largura=False)
            for chave, rotulo in B.ESTILOS.items():
                self._cb_estilo.addItem(rotulo, chave)
            i = self._cb_estilo.findData(self.bloco.estilo)
            self._cb_estilo.setCurrentIndex(max(0, i))
            self._cb_estilo.setFixedHeight(LADO_BOTAO)
            self._cb_estilo.setToolTip("Tipo de marcador deste parágrafo")
            self._cb_estilo.currentIndexChanged.connect(self._trocar_estilo)
            grade.addWidget(self._cb_estilo, 0, 0, 1, 3)
            grade.addWidget(self._botao(
                "chevron_left", "Recuar nível  (Shift+Tab)",
                lambda: self.pediu_nivel.emit(self, -1)), 0, 3)
            grade.addWidget(self._botao(
                "chevron_right", "Aprofundar nível  (Tab)",
                lambda: self.pediu_nivel.emit(self, +1)), 0, 4)
            if self.bloco.exemplo:
                # Só nasce onde faz sentido: criar o botão em todo bloco e
                # escondê-lo custava mais que todo o resto da coluna.
                self._btn_adotar = self._botao(
                    "check", "Usar este texto como está  (ou escreva por "
                             "cima)", self.adotar, PALETTE["success"])
                grade.addWidget(self._btn_adotar, 1, 1)
        else:
            for coluna, (icone, dica, slot) in enumerate((
                ("linha_mais", "Inserir linha", self._add_linha),
                ("linha_menos", "Remover última linha", self._del_linha),
                ("coluna_mais", "Inserir coluna", self._add_coluna),
                ("coluna_menos", "Remover última coluna", self._del_coluna),
            )):
                grade.addWidget(self._botao(icone, dica, slot), 0, coluna + 1)

        for n, (icone, dica, slot, cor) in enumerate(acoes):
            grade.addWidget(self._botao(icone, dica, slot, cor), 1, n + 2)

        grade.setColumnStretch(0, 1)
        grade.setRowStretch(2, 1)
        return caixa

    # ── tabela ───────────────────────────────────
    def _add_linha(self):
        self.bloco.inserir_linha()
        self.tabela.recarregar()
        self.alterado.emit()

    def _add_coluna(self):
        self.bloco.inserir_coluna()
        self.tabela.recarregar()
        self.alterado.emit()

    def _del_linha(self):
        self.bloco.remover_linha(self.bloco.linhas() - 1)
        self.tabela.recarregar()
        self.alterado.emit()

    def _del_coluna(self):
        self.bloco.remover_coluna(self.bloco.colunas() - 1)
        self.tabela.recarregar()
        self.alterado.emit()

    # ── estado ───────────────────────────────────
    def _ao_editar(self):
        self.bloco.html = self.editor.toHtml()
        if self.bloco.exemplo:
            # Escrever por cima do exemplo é a forma natural de adotá-lo:
            # o parágrafo deixa de ser ilustração e passa a valer.
            self.adotar()
        self.alterado.emit()

    def adotar(self):
        """Deixa de ser exemplo e passa a integrar o documento."""
        if not self.bloco.exemplo:
            return
        self.bloco.exemplo = False
        if self.editor is not None:
            self.editor.pintar(False)
        if self._btn_adotar is not None:
            self._btn_adotar.deleteLater()
            self._btn_adotar = None
        self.alterado.emit()

    def _trocar_estilo(self):
        self.bloco.estilo = self._cb_estilo.currentData()
        self.alterado.emit()

    def eventFilter(self, obj, ev):
        if obj is self.editor and ev.type() == ev.Type.FocusIn:
            self.ganhou_foco.emit(self)
        return super().eventFilter(obj, ev)

    def definir_marcador(self, texto: str):
        self._marcador.setText(texto)

    def atualizar_recuo(self):
        self._recuo.setFixedWidth((self.bloco.nivel - 1) * 26)


class EditorBlocos(QWidget):
    """Lista de blocos de um elemento."""

    alterado = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.blocos: list[B.Bloco] = []
        self._widgets: list[BlocoWidget] = []
        self._numero_elemento = 1
        self._ativo: BlocoWidget | None = None
        self.pasta_imagens = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QFrame.Shape.NoFrame)
        corpo = QWidget()
        corpo.setStyleSheet(
            f"QWidget {{ background: {PALETTE['bg']}; }}"
            "QFrame#bloco { background: transparent; }"
            "QTextEdit#paragrafo, QTextEdit#exemplo {"
            " background: #FFFFFF; border-radius: 5px; padding: 7px 10px; }"
            f"QTextEdit#paragrafo {{ color: #16233A; "
            f"border: 1px solid {PALETTE['border']}; }}"
            f"QTextEdit#paragrafo:focus {{ border: 1px solid "
            f"{PALETTE['gold']}; }}"
            "QTextEdit#exemplo { color: #6B7280; "
            "border: 1px dashed #8A6D1F; }")
        self._corpo = corpo
        self._pilha = QVBoxLayout(corpo)
        self._pilha.setContentsMargins(4, 4, 14, 4)
        self._pilha.setSpacing(0)
        self._pilha.addStretch()
        self._area.setWidget(corpo)
        raiz.addWidget(self._area, 1)

    # ── carga ────────────────────────────────────
    def definir_pasta_imagens(self, pasta):
        self.pasta_imagens = pasta
        for w in self._widgets:
            if w.editor is not None:
                w.editor.pasta_imagens = pasta

    def carregar(self, blocos: list[B.Bloco], numero_elemento: int):
        # Monta com o corpo oculto: visível, cada parágrafo acrescentado
        # obrigava o Qt a refazer o arranjo de todos os anteriores, e um
        # elemento de meia centena de parágrafos levava segundos para
        # abrir — era isso que se via piscando.
        self._corpo.setUpdatesEnabled(False)
        self._corpo.hide()
        try:
            self._numero_elemento = numero_elemento
            self.blocos = blocos
            for w in self._widgets:
                self._pilha.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
            self._widgets = []
            self._ativo = None

            if not self.blocos:
                self.blocos.append(B.Bloco())
            for b in self.blocos:
                self._criar_widget(b)
            self.renumerar()
        finally:
            self._corpo.show()
            self._corpo.setUpdatesEnabled(True)

    def _criar_widget(self, bloco: B.Bloco, posicao: int | None = None) -> BlocoWidget:
        w = BlocoWidget(bloco)
        if w.editor is not None:
            w.editor.pasta_imagens = self.pasta_imagens
        w.alterado.connect(self._ao_alterar)
        w.pediu_novo.connect(self._novo_depois)
        w.pediu_remover.connect(self._remover)
        w.pediu_nivel.connect(self._mudar_nivel)
        w.pediu_mover.connect(self._mover)
        w.pediu_fundir.connect(self._fundir)
        w.pediu_foco.connect(self._mover_foco)
        w.ganhou_foco.connect(self._definir_ativo)
        idx = len(self._widgets) if posicao is None else posicao
        self._pilha.insertWidget(idx, w)
        self._widgets.insert(idx, w)
        return w

    # ── operações ────────────────────────────────
    def _ao_alterar(self):
        self.renumerar()
        self.alterado.emit()

    def _indice(self, w: BlocoWidget) -> int:
        return self._widgets.index(w)

    def acrescentar(self, bloco: B.Bloco):
        self.blocos.append(bloco)
        w = self._criar_widget(bloco)
        self.renumerar()
        self.alterado.emit()
        if w.editor is not None:
            w.editor.setFocus()

    def _novo_depois(self, w: BlocoWidget):
        i = self._indice(w)
        novo = B.Bloco(nivel=w.bloco.nivel,
                       estilo=w.bloco.estilo if w.bloco.estilo != B.SEM_MARCADOR
                       else B.NUMERO)
        self.blocos.insert(i + 1, novo)
        novo_w = self._criar_widget(novo, i + 1)
        self.renumerar()
        self.alterado.emit()
        if novo_w.editor is not None:
            novo_w.editor.setFocus()

    def _remover(self, w: BlocoWidget):
        if len(self._widgets) <= 1:
            # Sempre resta um bloco: uma seção sem nenhum não teria onde
            # o encarregado voltar a escrever.
            if w.editor is not None:
                w.editor.clear()
            return
        i = self._indice(w)
        self.blocos.pop(i)
        self._widgets.pop(i)
        self._pilha.removeWidget(w)
        w.deleteLater()
        self.renumerar()
        self.alterado.emit()
        alvo = self._widgets[min(i, len(self._widgets) - 1)]
        if alvo.editor is not None:
            alvo.editor.setFocus()

    def _mudar_nivel(self, w: BlocoWidget, delta: int):
        novo = max(1, min(B.NIVEL_MAX, w.bloco.nivel + delta))
        if novo == w.bloco.nivel:
            return
        w.bloco.nivel = novo
        w.atualizar_recuo()
        self.renumerar()
        self.alterado.emit()
        if w.editor is not None:
            w.editor.setFocus()

    def _mover(self, w: BlocoWidget, delta: int):
        i = self._indice(w)
        j = i + delta
        if not (0 <= j < len(self._widgets)):
            return
        self.blocos.insert(j, self.blocos.pop(i))
        self._widgets.insert(j, self._widgets.pop(i))
        self._pilha.removeWidget(w)
        self._pilha.insertWidget(j, w)
        self.renumerar()
        self.alterado.emit()
        if w.editor is not None:
            w.editor.setFocus()

    def _fundir(self, w: BlocoWidget):
        i = self._indice(w)
        if i == 0:
            return
        anterior = self._widgets[i - 1]
        if anterior.editor is None or w.editor is None:
            return
        resto = w.editor.toPlainText()
        cur = anterior.editor.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        anterior.editor.setTextCursor(cur)
        if resto:
            cur.insertText(resto)
        self._remover(w)
        anterior.editor.setFocus()

    def _mover_foco(self, w: BlocoWidget, delta: int):
        i = self._indice(w) + delta
        if 0 <= i < len(self._widgets):
            alvo = self._widgets[i]
            if alvo.editor is not None:
                alvo.editor.setFocus()

    def _definir_ativo(self, w: BlocoWidget):
        self._ativo = w

    # ── numeração ────────────────────────────────
    def renumerar(self):
        marcadores = B.numerar(self.blocos, self._numero_elemento)
        for w, m in zip(self._widgets, marcadores):
            if w.bloco.exemplo:
                w.definir_marcador("exemplo")
            else:
                w.definir_marcador(
                    m or ("tabela" if w.bloco.tipo == B.TABELA else ""))
            w.atualizar_recuo()

    def definir_numero_elemento(self, numero: int):
        self._numero_elemento = numero
        self.renumerar()

    # ── acesso do exterior ───────────────────────
    def editor_ativo(self) -> QTextEdit | None:
        """Caixa de texto em foco, para a barra de formatação agir nela."""
        if self._ativo is not None and self._ativo.editor is not None:
            return self._ativo.editor
        for w in self._widgets:
            if w.editor is not None:
                return w.editor
        return None
