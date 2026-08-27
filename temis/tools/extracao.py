"""
Extração Registrada — a diligência em sistema interno, documentada.

Quem extrai abre o sistema aqui dentro, e a ferramenta anota cada passo:
o endereço visitado, o que se clicou, o formulário submetido com seus
parâmetros e o arquivo recebido, resumido criptograficamente no instante
em que chega. A gravação de tela corre junto, de modo que o termo traz o
registro estruturado e o audiovisual, cruzados pelo tempo decorrido.

A tela é a diligência: navegador ao centro, linha do tempo à direita,
crescendo enquanto se trabalha. Quem opera vê o que está sendo
registrado a seu respeito — não há anotação que ele não possa conferir
na hora.
"""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
)

try:
    from PyQt6.QtWebEngineCore import (
        QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile,
        QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestInterceptor,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBVIEW_DISPONIVEL = True
except ImportError:                                     # pragma: no cover
    WEBVIEW_DISPONIVEL = False
    QWebEnginePage = object                             # type: ignore
    QWebEngineUrlRequestInterceptor = object            # type: ignore

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (preparar_procedimento, ler_procedimento,
    
    NoScrollComboBox, SidebarPanel, field_label, fit_to_screen, hsep,
    output_button, primary_button, subtext,
)
from . import extracao_core as core
from . import gravacao_core as grav
from .base import ToolMeta, ToolPage

META = ToolMeta(
    key="extracao",
    name="Extração Registrada",
    icon="tool_extracao",
    tagline="Documenta a extração de dados em sistema",
    description=(
        "Abre o sistema interno num navegador instrumentado e registra "
        "cada passo da extração: endereços visitados, cliques, consultas "
        "submetidas com seus parâmetros e arquivos recebidos — cada um "
        "resumido criptograficamente no instante em que chega, antes de "
        "tocar qualquer pasta de trabalho. Grava a tela ao mesmo tempo e "
        "emite termo com a relação dos atos praticados. Feita para quem "
        "atende ao pedido de auditoria, não para quem o formula."
    ),
    online=True,
)

PAGINA_INICIAL = "about:blank"


# ─────────────────────────────────────────
#  INSTRUMENTAÇÃO
# ─────────────────────────────────────────

class _Espiao(QWebEngineUrlRequestInterceptor):
    """Anota os endereços que a página pediu.

    Roda na thread de rede: uma exceção aqui derruba o processo inteiro,
    sem mensagem nenhuma. Nada pode escapar deste método — e nada pode
    sumir em silêncio, por isso a lista de erros.
    """

    def __init__(self):
        super().__init__()
        self.pedidos: list[tuple[str, str]] = []
        self.erros: list[str] = []

    def interceptRequest(self, info):                   # noqa: N802
        try:
            # `.value` e não `int()`: neste PyQt o enum de tipo de recurso
            # não converte para inteiro, e a exceção — engolida — deixava
            # o registro sair vazio sem ninguém notar.
            if info.resourceType().value == 0:          # documento principal
                self.pedidos.append((
                    str(info.requestMethod(), "ascii", "ignore"),
                    info.requestUrl().toString()))
        except Exception as e:                          # noqa: BLE001
            self.erros.append(f"{type(e).__name__}: {e}")


class _Pagina(QWebEnginePage):
    """Página que repassa as mensagens do código injetado.

    Não há como saber, de fora, no que a pessoa clicou dentro da página.
    O código injetado anuncia pelo console; aqui se lê o que vier com a
    marca e se descarta o resto — inclusive os erros da própria página,
    que são muitos e não interessam ao registro.
    """

    ato = pyqtSignal(str, str, str)      # tipo, descrição, detalhe

    def javaScriptConsoleMessage(self, _nivel, mensagem,  # noqa: N802
                                 _linha, _origem):
        lido = core.ler_console(mensagem or "")
        if lido is not None:
            self.ato.emit(*lido)


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """A peça pronta para os autos, editável antes de salvar."""

    def __init__(self, termo: core.TermoExtracao, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Extração de Dados")
        self._termo = termo
        fit_to_screen(self, 980, 830)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        titulo = QLabel("Termo de Extração de Dados")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        layout.addWidget(subtext(
            "O documento já traz a estação, a relação dos atos praticados e "
            "o resumo criptográfico de cada arquivo recebido. Complete a "
            "qualificação de quem assina.", wrap=True))
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
        self._e_nome.setPlaceholderText("Ex.: Maria Silva")
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

        # Quem extrai costuma ser da área de tecnologia, não da
        # corregedoria: o cargo não pode vir fixo.
        self._e_cargo = QLineEdit(t.cargo)
        self._e_tipo = NoScrollComboBox()
        preparar_procedimento(self._e_tipo)
        self._e_tipo.currentIndexChanged.connect(self._remontar)
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

        self._e_processo = QLineEdit(t.numero_processo)
        self._e_processo.setPlaceholderText("Ex.: 08650.000123/2026-11")
        self._e_processo.textChanged.connect(self._remontar)
        self._e_solicitacao = QLineEdit(t.solicitacao)
        self._e_solicitacao.setPlaceholderText(
            "Ex.: Ofício nº 45/2026-CGCOR")
        self._e_solicitacao.textChanged.connect(self._remontar)
        grade.addWidget(field_label("Número do processo"), 4, 0)
        grade.addWidget(self._e_processo, 5, 0)
        grade.addWidget(field_label("Solicitação atendida"), 4, 1, 1, 2)
        grade.addWidget(self._e_solicitacao, 5, 1, 1, 2)

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

    def _atualizado(self) -> core.TermoExtracao:
        t = self._termo
        d = self._e_data.date()
        t.nome = self._e_nome.text().strip()
        t.matricula = self._e_matricula.text().strip()
        t.lotacao = self._e_lotacao.text().strip()
        t.cargo = self._e_cargo.text().strip() or "Servidor"
        t.tipo_processo = ler_procedimento(self._e_tipo)
        t.numero_processo = self._e_processo.text().strip()
        t.solicitacao = self._e_solicitacao.text().strip()
        t.dia, t.mes, t.ano = d.day(), d.month(), d.year()
        return t

    def _remontar(self):
        self._vista.setHtml(core.build_html(self._atualizado()))

    def _copiar(self):
        QGuiApplication.clipboard().setText(core.build_text(self._atualizado()))
        self._aviso.setText("✓ Texto copiado")

    def _salvar_html(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML", "termo-extracao.html",
            "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            corpo = limpar_para_sei(self._vista.toHtml())
            Path(caminho).write_text(
                documento_html(corpo, "Termo de Extração de Dados em "
                                      "Sistema Informatizado"),
                encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar o arquivo:\n{e}")

    def _salvar_pdf(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo", "termo-extracao.pdf",
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            escritor = preparar_escritor(
                caminho, "Termo de Extração de Dados em Sistema "
                         "Informatizado")
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

class ExtracaoTool(ToolPage):
    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessao: core.Sessao | None = None
        self._gravador: grav.Gravador | None = None
        self._video: grav.Resultado | None = None
        self._pulso = QTimer(self)
        self._pulso.setInterval(1000)
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
        coluna.addWidget(self._montar_barra())
        coluna.addWidget(self._montar_navegador(), 1)
        raiz.addWidget(principal, 1)
        raiz.addWidget(self._montar_linha_do_tempo())

    def _montar_lateral(self) -> QWidget:
        painel = SidebarPanel()
        titulo = QLabel("Diligência")
        titulo.setObjectName("heading")
        painel.header.addWidget(titulo)

        painel.body.addWidget(field_label("IDENTIFICAÇÃO"))
        self._e_processo = QLineEdit()
        self._e_processo.setPlaceholderText("08650.000123/2026-11")
        painel.body.addWidget(field_label("Processo"))
        painel.body.addWidget(self._e_processo)

        self._e_solicitacao = QLineEdit()
        self._e_solicitacao.setPlaceholderText("Ofício nº 45/2026-CGCOR")
        painel.body.addWidget(field_label("Solicitação atendida"))
        painel.body.addWidget(self._e_solicitacao)

        self._e_operador = QLineEdit()
        self._e_operador.setPlaceholderText("Quem realiza a extração")
        painel.body.addWidget(field_label("Operador"))
        painel.body.addWidget(self._e_operador)

        self._e_sistema = QLineEdit()
        self._e_sistema.setPlaceholderText("Nome do sistema consultado")
        painel.body.addWidget(field_label("Sistema"))
        painel.body.addWidget(self._e_sistema)

        self._e_objeto = QPlainTextEdit()
        self._e_objeto.setPlaceholderText(
            "O que será extraído. Ex.: registros de acesso do servidor de "
            "matrícula 1234567, entre 01/01/2026 e 31/03/2026.")
        self._e_objeto.setFixedHeight(74)
        painel.body.addWidget(field_label("Objeto da extração"))
        painel.body.addWidget(self._e_objeto)

        painel.body.addWidget(hsep())
        self._op_gravar = QCheckBox("Gravar a tela junto")
        self._op_gravar.setChecked(True)
        self._op_gravar.setToolTip(
            "Registra em vídeo a diligência inteira, em paralelo ao "
            "registro dos atos. O termo cruza os dois pelo tempo decorrido.")
        painel.body.addWidget(self._op_gravar)

        # As duas fontes de som ficam recuadas sob a gravação, porque só
        # fazem sentido com ela ligada — e se apagam junto quando ela é
        # desmarcada, em vez de ficarem oferecendo o que não vai
        # acontecer.
        from .audio_sistema import disponivel as _retorno_disponivel
        pode_sistema, detalhe_sistema = _retorno_disponivel()

        self._op_som_sistema = QCheckBox("      com o som do computador")
        self._op_som_sistema.setEnabled(pode_sistema)
        self._op_som_sistema.setToolTip(
            "Grava o que o computador reproduz durante a extração"
            if pode_sistema else f"Indisponível: {detalhe_sistema}")
        painel.body.addWidget(self._op_som_sistema)

        self._op_som_ambiente = QCheckBox("      com o som do ambiente")
        vozes = grav.microfones()
        self._op_som_ambiente.setEnabled(bool(vozes))
        self._op_som_ambiente.setToolTip(
            f"Grava pelo microfone: {vozes[0]}" if vozes
            else "Nenhum microfone disponível nesta estação")
        painel.body.addWidget(self._op_som_ambiente)

        def _seguir_gravacao(ligado: bool):
            self._op_som_sistema.setEnabled(ligado and pode_sistema)
            self._op_som_ambiente.setEnabled(ligado and bool(vozes))

        self._op_gravar.toggled.connect(_seguir_gravacao)
        _seguir_gravacao(self._op_gravar.isChecked())

        self._rot_estado = QLabel("Sessão não iniciada.")
        self._rot_estado.setObjectName("muted")
        self._rot_estado.setWordWrap(True)
        painel.body.addWidget(self._rot_estado)
        painel.body.addStretch()

        self._b_sessao = primary_button("Iniciar diligência", "camera")
        self._b_sessao.clicked.connect(self._alternar_sessao)
        painel.footer.addWidget(self._b_sessao)

        self._b_termo = output_button("Gerar termo")
        self._b_termo.clicked.connect(self._gerar_termo)
        painel.footer.addWidget(self._b_termo)
        painel.add_note("Arquivos recebidos são resumidos ao chegar, na "
                        "pasta da diligência.")
        return painel

    def _montar_barra(self) -> QFrame:
        barra = QFrame()
        barra.setStyleSheet(
            f"background: {PALETTE['surface']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        linha = QHBoxLayout(barra)
        linha.setContentsMargins(12, 8, 12, 8)
        linha.setSpacing(8)

        for rotulo, icone, alvo in (
                ("", "arrow_left", self._voltar),
                ("", "reload", self._recarregar)):
            b = QPushButton(rotulo)
            b.setIcon(draw_icon(icone, 15, PALETTE["text2"]))
            b.setFixedWidth(38)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(alvo)
            linha.addWidget(b)

        self._e_url = QLineEdit()
        self._e_url.setPlaceholderText(
            "Endereço do sistema — ex.: https://sistema.prf.gov.br/auditoria")
        self._e_url.returnPressed.connect(self._ir)
        linha.addWidget(self._e_url, 1)

        b_ir = QPushButton("Abrir")
        b_ir.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ir.clicked.connect(self._ir)
        linha.addWidget(b_ir)

        self._b_anotar = QPushButton("  Anotar")
        self._b_anotar.setIcon(draw_icon("note", 15, PALETTE["text"]))
        self._b_anotar.setToolTip(
            "Acrescenta uma observação do operador à linha do tempo")
        self._b_anotar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_anotar.clicked.connect(self._anotar)
        linha.addWidget(self._b_anotar)
        return barra

    def _montar_navegador(self) -> QWidget:
        if not WEBVIEW_DISPONIVEL:
            aviso = QLabel("O componente de navegação não está disponível "
                           "nesta instalação.")
            aviso.setObjectName("subtext")
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return aviso

        # Perfil próprio, sem estado anterior: a sessão começa limpa, o
        # que evita a alegação de que o resultado veio de cache ou de
        # credencial de outra pessoa.
        self._perfil = QWebEngineProfile(self)
        self._perfil.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self._perfil.setHttpCacheType(
            QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self._espiao = _Espiao()
        self._perfil.setUrlRequestInterceptor(self._espiao)
        self._perfil.downloadRequested.connect(self._ao_baixar)

        script = QWebEngineScript()
        script.setName("temis_espia")
        script.setSourceCode(core.ESPIA_JS)
        script.setInjectionPoint(
            QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        self._perfil.scripts().insert(script)

        self._view = QWebEngineView()
        self._pagina = _Pagina(self._perfil, self._view)
        self._view.setPage(self._pagina)
        self._pagina.settings().setAttribute(
            QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, False)
        self._pagina.ato.connect(self._ao_ato)
        self._pagina.urlChanged.connect(self._ao_navegar)
        self._pagina.loadFinished.connect(self._ao_carregar)
        self._pagina.load(QUrl(PAGINA_INICIAL))
        return self._view

    def _montar_linha_do_tempo(self) -> QWidget:
        painel = QFrame()
        painel.setFixedWidth(360)
        painel.setStyleSheet(
            f"background: {PALETTE['surface']}; "
            f"border-left: 1px solid {PALETTE['border']};")
        coluna = QVBoxLayout(painel)
        coluna.setContentsMargins(12, 12, 12, 12)
        coluna.setSpacing(8)

        topo = QLabel("Linha do tempo")
        topo.setObjectName("heading")
        coluna.addWidget(topo)
        coluna.addWidget(subtext(
            "Tudo o que for registrado aparece aqui, na hora.", wrap=True))

        self._lista_atos = QListWidget()
        self._lista_atos.setWordWrap(True)
        # Nada de reticências nem de rolagem lateral: o que este painel
        # mostra é o que a gravação de vídeo registra, e um dado cortado
        # ali é um dado que não foi filmado. Se algo não couber, que
        # desça de linha — nunca que suma para o lado.
        self._lista_atos.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._lista_atos.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        coluna.addWidget(self._lista_atos, 1)

        self._rot_resumo = QLabel("")
        self._rot_resumo.setObjectName("muted")
        self._rot_resumo.setWordWrap(True)
        coluna.addWidget(self._rot_resumo)

        acoes = QHBoxLayout()
        acoes.setSpacing(6)
        for rotulo, alvo in (("Abrir pasta", self._abrir_pasta),
                             ("Copiar hash", self._copiar_hash)):
            b = QPushButton(rotulo)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(alvo)
            acoes.addWidget(b)
        coluna.addLayout(acoes)
        return painel

    # ── sessão ───────────────────────────────────
    def _alternar_sessao(self):
        if self._sessao is not None and self._sessao.ativa:
            self._encerrar_sessao()
        else:
            self._iniciar_sessao()

    def _iniciar_sessao(self):
        faltando = [r for r, v in (("Sistema", self._e_sistema.text()),
                                   ("Objeto", self._e_objeto.toPlainText()))
                    if not v.strip()]
        if faltando:
            QMessageBox.information(
                self, "Falta identificar a diligência",
                "Preencha: " + ", ".join(faltando) + ".\n\nSão esses campos "
                "que dizem, no termo, o que se foi buscar e onde.")
            return

        resposta = QMessageBox.question(
            self, "Registro de ações nesta diligência",
            "A Extração Registrada documenta cada passo desta diligência: "
            "os endereços visitados, os cliques, os formulários submetidos "
            "com seus parâmetros e os arquivos recebidos, cada um resumido "
            "em SHA-256.\n\nCampo de senha nunca é registrado. Tudo fica "
            "apenas nesta máquina, e a relação sai no termo. Iniciar a "
            "diligência assim?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if resposta != QMessageBox.StandardButton.Yes:
            return

        base = core.pasta_padrao() / core.nome_de_sessao(
            self._e_processo.text().strip())
        self._sessao = core.Sessao()
        self._sessao.comecar(base)
        self._lista_atos.clear()
        self._video = None

        if self._op_gravar.isChecked():
            identificacao = "  •  ".join(x for x in (
                self._e_processo.text().strip(),
                (f"Operador {self._e_operador.text().strip()}"
                 if self._e_operador.text().strip() else ""),
                f"Sistema {self._e_sistema.text().strip()}",
                f"Estação {self._sessao.contexto.estacao}",
            ) if x)
            self._gravador = grav.Gravador(
                base / "gravacao-da-diligencia.mp4",
                grav.Opcoes(identificacao=identificacao,
                            microfone=((grav.microfones() or [""])[0]
                                       if self._op_som_ambiente.isChecked()
                                       else ""),
                            audio_sistema=self._op_som_sistema.isChecked(),
                            rodape="SISTEMA TÊMIS — EXTRAÇÃO REGISTRADA"))
            try:
                self._gravador.iniciar()
                self._sessao.anotar(
                    core.ABERTURA, "Gravação de tela iniciada",
                    detalhe=Path(self._gravador.destino).name)
            except Exception as e:                      # noqa: BLE001
                self._gravador = None
                self._sessao.erros.append(f"gravação: {e}")
                QMessageBox.warning(
                    self, "A gravação não começou",
                    f"O registro dos atos continua, mas sem vídeo.\n\n{e}")

        self._pulso.start()
        self._refletir()
        self._atualizar_estado()
        self.status_msg.emit(f"Diligência iniciada em {base}")

    def _encerrar_sessao(self):
        if self._sessao is None:
            return
        self._pulso.stop()
        if self._gravador is not None:
            self._video = self._gravador.encerrar()
            self._gravador = None
            if self._video.erro:
                self._sessao.erros.append(f"gravação: {self._video.erro}")
            else:
                self._sessao.video = self._video
        self._sessao.encerrar()
        self._refletir()
        self._atualizar_estado()
        self.status_msg.emit(
            f"Diligência encerrada: {len(self._sessao.eventos)} atos, "
            f"{len(self._sessao.bons)} arquivo(s) recebido(s).")

    def _tique(self):
        if self._sessao is None or not self._sessao.ativa:
            return
        s = int(self._sessao.decorrido)
        self._rot_estado.setText(
            f"<b>Em diligência</b><br/>{s // 3600:02d}:"
            f"{(s % 3600) // 60:02d}:{s % 60:02d} decorridos<br/>"
            f"{len(self._sessao.eventos)} atos registrados"
            + ("<br/>gravando a tela" if self._gravador is not None else ""))
        if self._gravador is not None and not self._gravador.gravando:
            self._sessao.erros.append(
                "a gravação de tela parou antes do encerramento")
            self._video = self._gravador.encerrar()
            self._gravador = None
            if not self._video.erro:
                self._sessao.video = self._video

    # ── eventos do navegador ─────────────────────
    def _registrar(self, tipo: str, descricao: str, url: str = "",
                   detalhe: str = ""):
        if self._sessao is None or not self._sessao.ativa:
            return
        self._sessao.anotar(tipo, descricao, url, detalhe)
        self._refletir_ultimo()

    def _ao_navegar(self, url: QUrl):
        endereco = url.toString()
        self._e_url.setText(endereco)
        if endereco and endereco != PAGINA_INICIAL:
            self._registrar(core.NAVEGACAO, "Acesso a endereço", endereco)

    def _ao_carregar(self, ok: bool):
        titulo = self._pagina.title() if WEBVIEW_DISPONIVEL else ""
        endereco = self._pagina.url().toString() if WEBVIEW_DISPONIVEL else ""
        if endereco in ("", PAGINA_INICIAL):
            return
        if ok:
            self._registrar(core.CARREGADA,
                            f"Página carregada: {titulo or 'sem título'}",
                            endereco)
        else:
            self._registrar(core.FALHA, "A página não carregou", endereco)

    def _ao_ato(self, tipo: str, descricao: str, detalhe: str):
        self._registrar(tipo, descricao, detalhe=detalhe)

    def _ao_baixar(self, pedido):
        """Guarda o arquivo na pasta da diligência e o resume ao chegar."""
        if self._sessao is None or not self._sessao.ativa:
            pedido.cancel()
            QMessageBox.information(
                self, "Diligência não iniciada",
                "Inicie a diligência antes de baixar arquivos — é o que "
                "permite registrar de onde cada um veio.")
            return
        pasta = Path(self._sessao.pasta) / "recebidos"
        pasta.mkdir(parents=True, exist_ok=True)
        pedido.setDownloadDirectory(str(pasta))
        nome = pedido.downloadFileName() or pedido.suggestedFileName()
        pedido.setDownloadFileName(nome)
        url = pedido.url().toString()
        mime = pedido.mimeType()

        def concluiu():
            if not pedido.isFinished():
                return
            destino = Path(pedido.downloadDirectory()) / \
                Path(pedido.downloadFileName()).name
            b = core.registrar_baixado(self._sessao, destino, url, mime)
            self._refletir_ultimo()
            self.status_msg.emit(
                f"Arquivo recebido e resumido: {b.nome}"
                if b.ok else f"Falha ao resumir {b.nome}: {b.erro}")

        pedido.isFinishedChanged.connect(concluiu)
        pedido.accept()
        self._registrar(core.NAVEGACAO, f"Download iniciado: {nome}", url)

    # ── navegação ────────────────────────────────
    def _ir(self):
        if not WEBVIEW_DISPONIVEL:
            return
        texto = self._e_url.text().strip()
        if not texto:
            return
        if "://" not in texto:
            texto = "https://" + texto
        self._pagina.load(QUrl(texto))

    def _voltar(self):
        if WEBVIEW_DISPONIVEL:
            self._pagina.triggerAction(QWebEnginePage.WebAction.Back)

    def _recarregar(self):
        if WEBVIEW_DISPONIVEL:
            self._pagina.triggerAction(QWebEnginePage.WebAction.Reload)

    def _anotar(self):
        if self._sessao is None or not self._sessao.ativa:
            return
        texto, ok = QInputDialog.getText(
            self, "Anotação do operador",
            "O que registrar neste momento da diligência?")
        if ok and texto.strip():
            self._registrar(core.ANOTACAO, texto.strip())

    # ── linha do tempo na tela ───────────────────
    #: Maior sequência sem espaço que cabe na largura do painel.
    #:
    #: Medido: a linha do SHA-256 pedia 484 pixels num painel de 334
    #: úteis, e saía cortada com reticências. Trinta e dois divide o
    #: hash exatamente ao meio, e cada metade sobra folga.
    LARGURA_EM_CARACTERES = 32

    @classmethod
    def _dobrar(cls, texto: str) -> str:
        """Quebra sequências longas demais para caberem no painel.

        A quebra automática do Qt só corta em espaço, e nem hash nem
        endereço têm um. O resultado era o pior possível para o que esta
        ferramenta existe: o hash **estava** registrado, ia inteiro para
        o termo, e mesmo assim a tela mostrava só o começo dele — de modo
        que a gravação de vídeo, que é o ponto da ferramenta, filmava um
        hash pela metade.

        A emenda é um espaço de largura zero, e não um espaço comum. Com
        espaço comum o endereço aparecia na tela como
        `logs-audi toria.csv`: quem lesse a filmagem veria um caractere
        que o endereço não tem. Num registro que existe para provar
        autenticidade, exibir o dado alterado é pior do que exibi-lo
        cortado. O de largura zero é ponto de quebra para o Qt e não
        imprime nada.
        """
        EMENDA = "​"
        pedacos = []
        for palavra in texto.split(" "):
            while len(palavra) > cls.LARGURA_EM_CARACTERES:
                pedacos.append(palavra[:cls.LARGURA_EM_CARACTERES] + EMENDA)
                palavra = palavra[cls.LARGURA_EM_CARACTERES:]
            pedacos.append(palavra)
        return " ".join(pedacos).replace(EMENDA + " ", EMENDA)

    def _item(self, e: core.Evento) -> QListWidgetItem:
        linhas = [f"[{e.relogio}]  {e.rotulo}", e.descricao]
        if e.url:
            linhas.append(e.url)
        if e.detalhe:
            linhas.append(e.detalhe)
        item = QListWidgetItem("\n".join(self._dobrar(x) for x in linhas))
        cores = {core.DOWNLOAD: PALETTE["gold"],
                 core.FORMULARIO: PALETTE["info"],
                 core.FALHA: PALETTE["danger"],
                 core.ANOTACAO: PALETTE["success"]}
        item.setForeground(QColor(cores.get(e.tipo, PALETTE["text2"])))
        return item

    def _refletir_ultimo(self):
        if self._sessao is None or not self._sessao.eventos:
            return
        self._lista_atos.addItem(self._item(self._sessao.eventos[-1]))
        self._lista_atos.scrollToBottom()
        self._atualizar_resumo()

    def _refletir(self):
        self._lista_atos.clear()
        if self._sessao is None:
            return
        for e in self._sessao.eventos:
            self._lista_atos.addItem(self._item(e))
        self._lista_atos.scrollToBottom()
        self._atualizar_resumo()

    def _atualizar_resumo(self):
        if self._sessao is None:
            self._rot_resumo.setText("")
            return
        s = self._sessao
        self._rot_resumo.setText(
            f"{len(s.eventos)} atos · {s.quantos(core.CLIQUE)} cliques · "
            f"{s.quantos(core.FORMULARIO)} consultas · "
            f"{len(s.bons)} arquivo(s) recebido(s)")

    # ── ações ────────────────────────────────────
    def _abrir_pasta(self):
        if self._sessao is None or not self._sessao.pasta:
            return
        try:
            os.startfile(self._sessao.pasta)            # noqa: S606
        except OSError as e:
            QMessageBox.warning(self, "Não foi possível abrir", str(e))

    def _copiar_hash(self):
        if self._sessao is None or not self._sessao.bons:
            return
        texto = "\n".join(f"{b.sha256}  {b.nome}" for b in self._sessao.bons)
        QGuiApplication.clipboard().setText(texto)
        self.status_msg.emit("Resumos criptográficos copiados.")

    # ── termo ────────────────────────────────────
    def _gerar_termo(self):
        if self._sessao is None:
            return
        termo = core.TermoExtracao(
            nome=self._e_operador.text().strip(),
            numero_processo=self._e_processo.text().strip(),
            solicitacao=self._e_solicitacao.text().strip(),
            objeto=self._e_objeto.toPlainText().strip(),
            sistema=self._e_sistema.text().strip(),
            sessao=self._sessao)
        TermoDialog(termo, self).exec()

    # ── estado ───────────────────────────────────
    def _atualizar_estado(self):
        ativa = self._sessao is not None and self._sessao.ativa
        self._b_sessao.setText(
            "Encerrar diligência" if ativa else "Iniciar diligência")
        self._b_anotar.setEnabled(ativa)
        self._b_termo.setEnabled(
            self._sessao is not None and not ativa and
            bool(self._sessao.eventos))
        for w in (self._e_processo, self._e_solicitacao, self._e_operador,
                  self._e_sistema, self._e_objeto, self._op_gravar):
            w.setEnabled(not ativa)
        if not ativa and self._sessao is None:
            self._rot_estado.setText("Sessão não iniciada.")
        elif not ativa and self._sessao is not None:
            self._rot_estado.setText(
                f"<b>Diligência encerrada</b><br/>"
                f"{len(self._sessao.eventos)} atos registrados<br/>"
                f"{len(self._sessao.bons)} arquivo(s) recebido(s)")

    # ── ciclo de vida ────────────────────────────
    def can_close(self) -> bool:
        if self._sessao is not None and self._sessao.ativa:
            resposta = QMessageBox.question(
                self, "Diligência em andamento",
                "Há uma diligência em curso. Sair agora a encerra.\n\n"
                "Deseja encerrar e sair?")
            if resposta != QMessageBox.StandardButton.Yes:
                return False
            self._encerrar_sessao()
        return True

    def shutdown(self):
        self._pulso.stop()
        if self._gravador is not None:
            self._gravador.encerrar()
            self._gravador = None
        if self._sessao is not None and self._sessao.ativa:
            self._sessao.encerrar()
