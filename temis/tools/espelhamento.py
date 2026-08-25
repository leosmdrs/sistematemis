"""
Espelhamento de Celular — a tela do aparelho, registrada.

A tela responde à sequência da diligência: ligar o cabo, reconhecer o
aparelho, identificar o processo, espelhar e gravar. O celular aparece
em janela própria do espelhador, ao lado; aqui ficam a identificação do
aparelho, o tempo decorrido e o encerramento.

O padrão é **somente observação**: o computador não repassa toque nem
digitação ao aparelho. Ligar o controle é ato do operador, e o termo
registra que foi ligado.
"""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (
    NoScrollComboBox, SidebarPanel, danger_button, field_label, fit_to_screen, hsep,
    output_button, primary_button, subtext,
)
from . import espelhamento_core as core
from .base import ToolMeta, ToolPage

META = ToolMeta(
    key="espelhamento",
    name="Espelhamento de Celular",
    icon="tool_espelhamento",
    tagline="Registra a tela de um aparelho Android",
    description=(
        "Liga um celular Android por cabo USB, espelha a tela no "
        "computador e grava a sessão em resolução nativa, com a "
        "identificação do aparelho — fabricante, modelo, versão do "
        "Android e número de série — lida do próprio dispositivo. Por "
        "padrão não repassa toque nem digitação: observa. Emite termo "
        "com o resumo criptográfico do vídeo e a declaração das "
        "alterações que o método provoca no aparelho."
    ),
)

PASTA_PADRAO = Path.home() / "Documents" / "Sistema Têmis" / "Espelhamentos"


# ─────────────────────────────────────────
#  PROCURA DE APARELHOS
# ─────────────────────────────────────────

class ProcurarThread(QThread):
    """Consulta o adb fora da interface.

    A primeira chamada sobe o processo de fundo do adb e pode levar
    segundos; feita na thread da janela, ela congela a tela.
    """

    pronto = pyqtSignal(list)

    def run(self):
        try:
            self.pronto.emit(core.listar())
        except Exception:                               # noqa: BLE001
            self.pronto.emit([])


class EncerrarThread(QThread):
    """Encerra a sessão e aplica a faixa, que exige recodificar.

    Numa diligência de vinte minutos essa etapa leva o seu tempo; a
    janela precisa continuar respondendo e dizendo o que está fazendo.
    """

    andamento = pyqtSignal(str)
    concluido = pyqtSignal(object)

    def __init__(self, espelhador: core.Espelhador):
        super().__init__()
        self._espelhador = espelhador

    def run(self):
        try:
            self.concluido.emit(
                self._espelhador.encerrar(progresso=self.andamento.emit))
        except Exception as e:                          # noqa: BLE001
            r = core.Resultado(erro=f"{type(e).__name__}: {e}")
            self.concluido.emit(r)


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """A peça pronta para os autos, editável antes de salvar."""

    def __init__(self, termo: core.TermoEspelhamento, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Espelhamento de Aparelho Móvel")
        self._termo = termo
        fit_to_screen(self, 960, 830)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel("Termo de Espelhamento")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        layout.addWidget(subtext(
            "O documento já traz a identificação do aparelho, a estação, o "
            "período e o resumo criptográfico do vídeo — e declara as "
            "alterações que o método provoca no dispositivo.", wrap=True))
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
        self._e_lotacao.setPlaceholderText("Ex.: CGCOR - PRF/DF")
        for coluna, (rotulo, campo) in enumerate((
                ("Nome do servidor", self._e_nome),
                ("Matrícula", self._e_matricula),
                ("Lotação", self._e_lotacao))):
            grade.addWidget(field_label(rotulo), 0, coluna)
            grade.addWidget(campo, 1, coluna)
            campo.textChanged.connect(self._remontar)

        self._e_tipo = NoScrollComboBox()
        for x in ("IPS", "PAD"):
            self._e_tipo.addItem(x)
        self._e_tipo.currentIndexChanged.connect(self._remontar)
        self._e_processo = QLineEdit(t.numero_processo)
        self._e_processo.setPlaceholderText("Ex.: 08650.000123/2026-11")
        self._e_processo.textChanged.connect(self._remontar)
        self._e_data = QDateEdit()
        self._e_data.setCalendarPopup(True)
        self._e_data.setDisplayFormat("dd/MM/yyyy")
        self._e_data.setDate(QDate.currentDate())
        self._e_data.dateChanged.connect(self._remontar)
        for coluna, (rotulo, campo) in enumerate((
                ("Procedimento", self._e_tipo),
                ("Número do processo", self._e_processo),
                ("Data do termo", self._e_data))):
            grade.addWidget(field_label(rotulo), 2, coluna)
            grade.addWidget(campo, 3, coluna)

        # Quem apresentou o aparelho, e a que título: é o que sustenta a
        # licitude do acesso, e sem isso a peça fica no ar.
        self._e_detentor = QLineEdit(t.detentor)
        self._e_detentor.setPlaceholderText(
            "Ex.: Fulano de Tal, denunciante, que o apresentou "
            "espontaneamente")
        self._e_detentor.textChanged.connect(self._remontar)
        grade.addWidget(field_label("Quem apresentou o aparelho"), 4, 0, 1, 3)
        grade.addWidget(self._e_detentor, 5, 0, 1, 3)

        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 1)
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

    def _atualizado(self) -> core.TermoEspelhamento:
        t = self._termo
        d = self._e_data.date()
        t.nome = self._e_nome.text().strip()
        t.matricula = self._e_matricula.text().strip()
        t.lotacao = self._e_lotacao.text().strip()
        t.tipo_processo = self._e_tipo.currentText()
        t.numero_processo = self._e_processo.text().strip()
        t.detentor = self._e_detentor.text().strip()
        t.dia, t.mes, t.ano = d.day(), d.month(), d.year()
        return t

    def _remontar(self):
        self._vista.setHtml(core.build_html(self._atualizado()))

    def _copiar(self):
        QGuiApplication.clipboard().setText(core.build_text(self._atualizado()))
        self._aviso.setText("✓ Texto copiado")

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML", "termo-espelhamento.html",
            "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            corpo = limpar_para_sei(self._vista.toHtml())
            Path(caminho).write_text(
                documento_html(corpo, "Termo de Espelhamento e Registro de "
                                      "Tela de Aparelho Móvel"),
                encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar o arquivo:\n{e}")

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo", "termo-espelhamento.pdf",
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            escritor = preparar_escritor(
                caminho, "Termo de Espelhamento e Registro de Tela de "
                         "Aparelho Móvel")
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

class EspelhamentoTool(ToolPage):
    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aparelhos: list[core.Aparelho] = []
        self._espelhador: core.Espelhador | None = None
        self._resultados: list[core.Resultado] = []
        self._procura: ProcurarThread | None = None
        self._encerramento: EncerrarThread | None = None

        self._pulso = QTimer(self)
        self._pulso.setInterval(1000)
        self._pulso.timeout.connect(self._tique)

        self._montar()
        self._atualizar_estado()
        QTimer.singleShot(400, self._procurar)

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
        coluna.addWidget(self._montar_aparelho())
        coluna.addWidget(self._montar_lista(), 1)
        raiz.addWidget(principal, 1)

    def _montar_lateral(self) -> QWidget:
        painel = SidebarPanel()
        titulo = QLabel("Diligência")
        titulo.setObjectName("heading")
        painel.header.addWidget(titulo)

        b_procurar = primary_button("Procurar aparelho", "reload")
        b_procurar.clicked.connect(self._procurar)
        painel.header.addWidget(b_procurar)
        self._b_procurar = b_procurar

        painel.body.addWidget(field_label("APARELHO"))
        self._cb_aparelho = NoScrollComboBox()
        self._cb_aparelho.currentIndexChanged.connect(self._mostrar_aparelho)
        painel.body.addWidget(self._cb_aparelho)

        painel.body.addWidget(hsep())
        painel.body.addWidget(field_label("IDENTIFICAÇÃO"))
        self._e_processo = QLineEdit()
        self._e_processo.setPlaceholderText("08650.000123/2026-11")
        painel.body.addWidget(field_label("Processo"))
        painel.body.addWidget(self._e_processo)

        self._e_operador = QLineEdit()
        self._e_operador.setPlaceholderText("Quem realiza a diligência")
        painel.body.addWidget(field_label("Operador"))
        painel.body.addWidget(self._e_operador)

        self._e_objeto = QPlainTextEdit()
        self._e_objeto.setPlaceholderText(
            "O que será registrado. Ex.: exibição, pelo denunciante, das "
            "conversas mantidas com o servidor apurado.")
        self._e_objeto.setFixedHeight(74)
        painel.body.addWidget(field_label("Objeto da diligência"))
        painel.body.addWidget(self._e_objeto)

        painel.body.addWidget(hsep())
        painel.body.addWidget(field_label("MODO"))
        self._op_observar = QCheckBox("Somente observar")
        self._op_observar.setChecked(True)
        self._op_observar.setToolTip(
            "Marcado, o computador não repassa toque nem digitação ao "
            "aparelho. Desmarcar permite operá-lo daqui, e o termo "
            "registra que o controle esteve habilitado.")
        painel.body.addWidget(self._op_observar)

        self._op_audio = QCheckBox("Captar o áudio do aparelho")
        self._op_audio.setChecked(True)
        self._op_audio.setToolTip("Exige Android 11 ou mais recente.")
        painel.body.addWidget(self._op_audio)
        painel.body.addStretch()

        self._b_sessao = primary_button("Iniciar espelhamento", "camera")
        self._b_sessao.clicked.connect(self._alternar)
        painel.footer.addWidget(self._b_sessao)

        self._b_termo = output_button("Gerar termo")
        self._b_termo.clicked.connect(self._gerar_termo)
        painel.footer.addWidget(self._b_termo)
        painel.add_note("Exige o aparelho destravado e com depuração USB "
                        "habilitada por quem o detém.")
        return painel

    def _montar_aparelho(self) -> QWidget:
        caixa = QFrame()
        caixa.setStyleSheet(
            f"background: {PALETTE['surface']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        coluna = QVBoxLayout(caixa)
        coluna.setContentsMargins(20, 16, 20, 16)
        coluna.setSpacing(6)

        self._rot_estado = QLabel("Procurando aparelhos…")
        self._rot_estado.setObjectName("heading")
        coluna.addWidget(self._rot_estado)

        self._rot_aparelho = QLabel()
        self._rot_aparelho.setObjectName("subtext")
        self._rot_aparelho.setWordWrap(True)
        coluna.addWidget(self._rot_aparelho)
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
        self._arvore.setColumnWidth(0, 250)
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

    # ── procura ──────────────────────────────────
    def _procurar(self):
        if not core.disponivel():
            self._rot_estado.setText("Espelhamento indisponível")
            self._rot_aparelho.setText(core.diagnostico())
            return
        if self._procura is not None and self._procura.isRunning():
            return
        self._b_procurar.setEnabled(False)
        self._rot_estado.setText("Procurando aparelhos…")
        self._rot_aparelho.setText(
            "Ligue o celular pelo cabo USB, destrave a tela e mantenha a "
            "depuração USB habilitada.")
        self._procura = ProcurarThread()
        self._procura.pronto.connect(self._achou)
        self._procura.start()

    def _achou(self, aparelhos: list):
        self._b_procurar.setEnabled(True)
        self._aparelhos = aparelhos
        self._cb_aparelho.blockSignals(True)
        self._cb_aparelho.clear()
        for a in aparelhos:
            self._cb_aparelho.addItem(a.rotulo, a.serie)
        self._cb_aparelho.blockSignals(False)

        if not aparelhos:
            self._rot_estado.setText("Nenhum aparelho encontrado")
            self._rot_aparelho.setText(
                "Confira: o cabo permite transferência de dados (há cabos "
                "que só carregam); a tela está destravada; e a depuração "
                "USB está habilitada em Opções do desenvolvedor.")
        else:
            self._mostrar_aparelho()
        self._atualizar_estado()

    def _aparelho(self) -> core.Aparelho | None:
        serie = self._cb_aparelho.currentData()
        return next((a for a in self._aparelhos if a.serie == serie), None)

    def _mostrar_aparelho(self):
        a = self._aparelho()
        if a is None:
            return
        if not a.pronto:
            self._rot_estado.setText("Aparelho aguardando autorização")
            self._rot_aparelho.setText(
                core.EXPLICACAO_ESTADO.get(a.estado, a.estado)
                + ".  Depois de autorizar, clique em Procurar aparelho.")
        else:
            self._rot_estado.setText(a.rotulo)
            self._rot_aparelho.setText("  ·  ".join(
                f"{r}: {v}" for r, v in a.linhas()))
        self._atualizar_estado()

    # ── sessão ───────────────────────────────────
    def _alternar(self):
        if self._espelhador is not None:
            self._encerrar()
        else:
            self._iniciar()

    def _identificacao(self) -> str:
        a = self._aparelho()
        partes = []
        if self._e_processo.text().strip():
            partes.append(self._e_processo.text().strip())
        if self._e_operador.text().strip():
            partes.append(f"Operador {self._e_operador.text().strip()}")
        if a is not None:
            nome = " ".join(x for x in (a.fabricante, a.modelo) if x)
            partes.append(f"Aparelho {nome or a.serie}")
        partes.append("Somente observação" if self._op_observar.isChecked()
                      else "COM CONTROLE DO APARELHO")
        return "  •  ".join(partes)

    def _iniciar(self):
        a = self._aparelho()
        if a is None or not a.pronto:
            return
        if not self._e_objeto.toPlainText().strip():
            QMessageBox.information(
                self, "Falta o objeto da diligência",
                "Descreva o que será registrado. É esse campo que diz, no "
                "termo, o que se foi verificar.")
            return
        if not self._op_observar.isChecked():
            resposta = QMessageBox.question(
                self, "Controle do aparelho habilitado",
                "Sem a opção “Somente observar”, o computador poderá operar "
                "o aparelho — tocar, digitar, abrir aplicativos.\n\n"
                "Operar o telefone de outra pessoa é ato diverso de "
                "observar o que ela exibe, e o termo registrará que o "
                "controle esteve habilitado.\n\nProsseguir assim?")
            if resposta != QMessageBox.StandardButton.Yes:
                return

        PASTA_PADRAO.mkdir(parents=True, exist_ok=True)
        agora = datetime.datetime.now()
        sugestao = PASTA_PADRAO / f"espelhamento-{agora:%Y-%m-%d-%H%M%S}.mp4"
        destino, _ = QFileDialog.getSaveFileName(
            self, "Onde gravar a sessão", str(sugestao), "Vídeo MP4 (*.mp4)")
        if not destino:
            return
        if not destino.lower().endswith(".mp4"):
            destino += ".mp4"

        opcoes = core.Opcoes(
            somente_observar=self._op_observar.isChecked(),
            com_audio=self._op_audio.isChecked(),
            identificacao=self._identificacao())
        self._espelhador = core.Espelhador(a, destino, opcoes)
        try:
            self._espelhador.iniciar()
        except Exception as e:                          # noqa: BLE001
            self._espelhador = None
            QMessageBox.critical(self, "Não foi possível espelhar", str(e))
            return
        self._pulso.start()
        self._atualizar_estado()
        self.status_msg.emit("Espelhamento iniciado.")

    def _tique(self):
        if self._espelhador is None:
            return
        s = int(self._espelhador.decorrido)
        self._rot_estado.setText(
            f"Espelhando — {s // 3600:02d}:{(s % 3600) // 60:02d}:"
            f"{s % 60:02d}")
        if not self._espelhador.espelhando:
            # O espelhador caiu sozinho — cabo solto, aparelho desligado.
            self.status_msg.emit(
                "O espelhamento terminou por conta própria; encerrando.")
            self._encerrar()

    def _encerrar(self):
        if self._espelhador is None or self._encerramento is not None:
            return
        self._pulso.stop()
        self._rot_estado.setText("Encerrando a sessão…")
        self._rot_aparelho.setText("Aplicando a faixa de identificação.")
        self._atualizar_estado(ocupado=True)
        self._encerramento = EncerrarThread(self._espelhador)
        self._encerramento.andamento.connect(self._rot_aparelho.setText)
        self._encerramento.concluido.connect(self._terminou)
        self._encerramento.start()

    def _terminou(self, r: core.Resultado):
        self._encerramento = None
        self._espelhador = None
        self._atualizar_estado()
        self._mostrar_aparelho()
        if r.erro:
            QMessageBox.critical(self, "A sessão falhou", r.erro)
            return
        self._resultados.append(r)
        item = QTreeWidgetItem([
            Path(r.arquivo).name, core.data_br(r.inicio), r.duracao,
            core.formatar_tamanho(r.tamanho), r.sha256])
        item.setData(0, Qt.ItemDataRole.UserRole, r.arquivo)
        item.setForeground(4, QColor(PALETTE["text3"]))
        item.setFont(4, QFont("Consolas", 8))
        self._arvore.addTopLevelItem(item)
        self._arvore.setCurrentItem(item)
        self.status_msg.emit(
            f"Sessão encerrada: {r.duracao}, "
            f"{core.formatar_tamanho(r.tamanho)}.")
        if r.avisos:
            QMessageBox.warning(self, "Avisos da sessão",
                                "\n\n".join(r.avisos[:4]))

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
        if not self._resultados:
            return
        termo = core.TermoEspelhamento(
            nome=self._e_operador.text().strip(),
            numero_processo=self._e_processo.text().strip(),
            objeto=self._e_objeto.toPlainText().strip(),
            registros=list(self._resultados))
        TermoDialog(termo, self).exec()

    # ── estado ───────────────────────────────────
    def _atualizar_estado(self, ocupado: bool = False):
        a = self._aparelho()
        espelhando = self._espelhador is not None
        pode = (a is not None and a.pronto and not ocupado
                and core.disponivel())
        self._b_sessao.setEnabled((pode or espelhando) and not ocupado)
        self._b_sessao.setText(
            "Encerrar espelhamento" if espelhando else "Iniciar espelhamento")
        self._b_termo.setEnabled(bool(self._resultados) and not espelhando
                                 and not ocupado)
        self._b_nova.setEnabled(bool(self._resultados) and not espelhando
                                and not ocupado)
        self._b_remover.setEnabled(
            self._arvore.currentItem() is not None and not espelhando
            and not ocupado)
        self._b_procurar.setEnabled(not espelhando and not ocupado)
        for w in (self._cb_aparelho, self._e_processo, self._e_operador,
                  self._e_objeto, self._op_observar, self._op_audio):
            w.setEnabled(not espelhando and not ocupado)

    # ── ciclo de vida ────────────────────────────
    def can_close(self) -> bool:
        if self._espelhador is not None:
            resposta = QMessageBox.question(
                self, "Espelhamento em andamento",
                "Há uma sessão em curso. Sair agora a encerra.\n\n"
                "Deseja encerrar e sair?")
            if resposta != QMessageBox.StandardButton.Yes:
                return False
            self._encerrar()
        return True

    def shutdown(self):
        self._pulso.stop()
        if self._espelhador is not None:
            self._espelhador.cancelar()
            self._espelhador = None
        for t in (self._procura, self._encerramento):
            if t is not None and t.isRunning():
                t.wait(6000)
        # O adb deixa um processo de fundo residente; encerrá-lo evita
        # deixar no computador um serviço que ninguém pediu.
        core.encerrar_servidor()
