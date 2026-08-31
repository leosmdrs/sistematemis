"""
Constatação Web — registro de conteúdo publicado na internet.

Disposição igual às demais: painel à esquerda com o que já foi capturado,
barra no alto, conteúdo à direita. A diferença é que o conteúdo é um
navegador.

Duas decisões de projeto que não são estéticas:

**A barra de endereços fica visível e mostra o endereço real.** Uma janela
de navegador sem barra de endereços, pedindo senha, é o desenho clássico
de phishing — e este programa vai pedir login em rede social. Quem usa
precisa poder conferir onde está.

**A sessão é anônima e recomeça a cada abertura.** Nada de cookie ou cache
em disco. O custo é ter de autenticar a cada diligência; o ganho é duplo:
não fica sessão de rede social guardada na estação, e a autenticação
acontece dentro da própria constatação, o que fortalece a peça.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QFrame, QSizePolicy, QMessageBox, QDialog, QTextEdit, QListWidget,
    QListWidgetItem, QLineEdit, QGridLayout, QCheckBox, QPlainTextEdit,
)

try:
    from PyQt6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
        QWebEngineUrlRequestInterceptor,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBVIEW_DISPONIVEL = True
except ImportError:                                     # pragma: no cover
    WEBVIEW_DISPONIVEL = False
    QWebEngineUrlRequestInterceptor = object             # type: ignore

from .. import perfil
from ..icons import draw_icon
from ..impressao import (documento_html, imprimir_documento,
                         limpar_para_sei, preparar_escritor)
from ..theme import PALETTE
from ..widgets import (preparar_procedimento, ler_procedimento,
    
    NoScrollComboBox, SidebarPanel, field_label, fit_to_screen, hsep,
    output_button, primary_button, subtext, TOOLBAR_HEIGHT,
)
from .base import ToolPage, ToolMeta
from . import constatacao_core as core


META = ToolMeta(
    key="constatacao",
    name="Constatação Web",
    icon="tool_constatacao",
    tagline="Registra conteúdo publicado na internet",
    description=(
        "Abre o endereço num navegador dedicado, sem extensões e sem sessão "
        "anterior, e registra o que foi exibido: a página inteira em PDF, o "
        "código-fonte, a tela, o IP do servidor e o certificado que ele "
        "apresentou — cada peça com o seu SHA-256. Emite termo de "
        "constatação pronto para os autos."
    ),
    online=True,
)

PAGINA_INICIAL = "https://www.gov.br/prf/pt-br"


# ─────────────────────────────────────────
#  REGISTRO DAS REQUISIÇÕES
# ─────────────────────────────────────────

class _Espiao(QWebEngineUrlRequestInterceptor):
    """Anota cada recurso que a página pediu.

    Roda na thread de rede: uma exceção aqui derruba o processo inteiro,
    sem mensagem nenhuma. Por isso nada pode escapar deste método — foi o
    que travou o protótipo duas vezes.
    """

    TIPOS = {0: "página", 1: "sub-quadro", 2: "folha de estilo",
             3: "script", 4: "imagem", 5: "fonte", 14: "XHR"}

    def __init__(self):
        super().__init__()
        self.recursos: list[core.Recurso] = []
        self.erros: list[str] = []

    def limpar(self):
        self.recursos = []
        self.erros = []

    def interceptRequest(self, info):                   # noqa: N802
        try:
            # `.value` e não `int()`: neste PyQt o enum de tipo de recurso
            # não converte para inteiro, e a exceção — engolida — deixava
            # o registro de requisições sair vazio sem ninguém notar.
            self.recursos.append(core.Recurso(
                url=info.requestUrl().toString(),
                tipo=self.TIPOS.get(info.resourceType().value, "outro"),
                metodo=str(info.requestMethod(), "ascii", "ignore")))
        except Exception as e:                          # noqa: BLE001
            # Não pode escapar, sob pena de derrubar o processo — mas
            # também não pode sumir, sob pena de falhar em silêncio.
            self.erros.append(f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

class TermoDialog(QDialog):
    """O termo montado, editável antes de salvar."""

    def __init__(self, sessao: core.Sessao, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Termo de Constatação")
        self._sessao = sessao
        fit_to_screen(self, 940, 800)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        titulo = QLabel("Termo de Constatação")
        titulo.setObjectName("heading")
        lay.addWidget(titulo)
        lay.addWidget(subtext(
            "Os campos abaixo montam a abertura. Confira e ajuste o texto "
            "antes de salvar.", wrap=True))
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

        zipe = QPushButton("  Salvar peças (ZIP)")
        zipe.setIcon(draw_icon("open", 15, PALETTE["text"]))
        zipe.setToolTip("Os arquivos capturados, com índice e hashes")
        zipe.setCursor(Qt.CursorShape.PointingHandCursor)
        zipe.clicked.connect(self._salvar_zip)
        linha.addWidget(zipe)

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
        vazio = QWidget()
        for coluna, (rotulo, campo) in enumerate((
            ("Procedimento", self._cb_tipo),
            ("Número do processo", self._in_processo),
            ("", vazio),
        )):
            if rotulo:
                grade.addWidget(field_label(rotulo), 2, coluna)
            grade.addWidget(campo, 3, coluna)

        grade.setColumnStretch(0, 3)
        grade.setColumnStretch(1, 1)
        grade.setColumnStretch(2, 2)
        grade.setRowMinimumHeight(2, 12)
        return caixa

    # ── documento ────────────────────────────────
    def _remontar(self):
        self._view.setHtml(core.build_html(
            self._sessao,
            core.Declarante(nome=self._in_nome.text().strip(),
                            matricula=self._in_matricula.text().strip(),
                            lotacao=self._in_lotacao.text().strip()),
            core.Procedimento(tipo=ler_procedimento(self._cb_tipo),
                              numero=self._in_processo.text().strip())))

    def _base(self) -> str:
        return f"constatacao-{self._sessao.id}"

    def _salvar_pdf(self):
        from ..sessao import destino_para_dialogo
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo",
            destino_para_dialogo(self, "Termos", f"{self._base()}.pdf"),
            "Arquivos PDF (*.pdf)")
        if not caminho:
            return
        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"
        try:
            doc = self._view.document().clone()
            doc.setDefaultFont(QFont("Segoe UI", 10))
            imprimir_documento(doc, preparar_escritor(
                caminho, "Termo de Constatação"))
            self._aviso.setText("✓ PDF salvo")
        except Exception as e:                          # noqa: BLE001
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gerar o PDF:\n{e}")

    def _salvar_html(self):
        from ..sessao import destino_para_dialogo
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar termo em HTML",
            destino_para_dialogo(self, "Termos", f"{self._base()}.html"),
            "Página HTML (*.html)")
        if not caminho:
            return
        if not caminho.lower().endswith((".html", ".htm")):
            caminho += ".html"
        try:
            Path(caminho).write_text(
                documento_html(limpar_para_sei(self._view.toHtml()),
                               "Termo de Constatação"),
                encoding="utf-8")
            self._aviso.setText("✓ HTML salvo")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar:\n{e}")

    def _salvar_zip(self):
        from ..sessao import destino_para_dialogo
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar peças",
            destino_para_dialogo(self, "Termos", f"{self._base()}.zip"),
            "Arquivo ZIP (*.zip)")
        if not caminho:
            return
        if not caminho.lower().endswith(".zip"):
            caminho += ".zip"
        try:
            core.empacotar(self._sessao, caminho)
            self._aviso.setText("✓ Peças salvas")
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar",
                                 f"Não foi possível gravar:\n{e}")


# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class ConstatacaoTool(ToolPage):
    meta = META

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessao = core.Sessao()
        self._pasta = core.pasta_sessoes() / self._sessao.id
        self._pasta.mkdir(parents=True, exist_ok=True)
        self._espiao = None
        self._capturando = False
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
        coluna.addWidget(self._build_aviso_video())

        if WEBVIEW_DISPONIVEL:
            # Perfil anônimo: nada em disco, sessão nova a cada abertura.
            self._perfil = QWebEngineProfile(self)
            # Apresenta-se como Chrome comum, retirando o rótulo "QtWebEngine"
            # da identificação do navegador. Sítios que barram navegador
            # desconhecido — o WhatsApp Web, entre eles — passam a carregar, e
            # o conteúdo servido é o mesmo que um Chrome veria. A versão do
            # Chromium é a real, embutida; nada de fingir versão que não há.
            import re as _re
            self._perfil.setHttpUserAgent(
                _re.sub(r"QtWebEngine/\S+\s*", "", self._perfil.httpUserAgent()))
            self._perfil.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self._perfil.setHttpCacheType(
                QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            self._espiao = _Espiao()
            self._perfil.setUrlRequestInterceptor(self._espiao)

            self._view = QWebEngineView()
            self._pagina = QWebEnginePage(self._perfil, self._view)
            self._view.setPage(self._pagina)
            ajustes = self._pagina.settings()
            ajustes.setAttribute(
                QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, False)
            self._pagina.urlChanged.connect(self._ao_navegar)
            self._pagina.loadFinished.connect(self._ao_carregar)
            self._pagina.titleChanged.connect(
                lambda t: self._lbl_titulo.setText(t[:80]))
            coluna.addWidget(self._view, 1)
            self._pagina.load(QUrl(PAGINA_INICIAL))
        else:
            aviso = QLabel(
                "O componente de navegação não está disponível nesta "
                "instalação.")
            aviso.setObjectName("subtext")
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            coluna.addWidget(aviso, 1)

        raiz.addWidget(principal, 1)

    def _build_barra(self) -> QFrame:
        barra = QFrame()
        barra.setObjectName("toolbar_frame")
        barra.setFixedHeight(TOOLBAR_HEIGHT)
        lay = QHBoxLayout(barra)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)

        for icone, dica, slot in (
            ("chevron_left", "Voltar", self._voltar),
            ("reload", "Recarregar", self._recarregar),
        ):
            b = QPushButton()
            b.setIcon(draw_icon(icone, 14, PALETTE["text2"]))
            b.setToolTip(dica)
            b.setFixedSize(30, 30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            lay.addWidget(b)

        # O endereço fica à vista e é o real. Sem isto, a janela vira uma
        # caixa sem procedência pedindo senha de rede social.
        self._lbl_cadeado = QLabel("")
        self._lbl_cadeado.setFixedWidth(20)
        self._lbl_cadeado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._lbl_cadeado)

        self._in_url = QLineEdit()
        self._in_url.setPlaceholderText("Endereço a constatar")
        self._in_url.returnPressed.connect(self._ir)
        lay.addWidget(self._in_url, 1)

        self._btn_capturar = primary_button("Capturar esta página", "camera")
        self._btn_capturar.setMinimumWidth(196)
        self._btn_capturar.clicked.connect(self._capturar)
        lay.addWidget(self._btn_capturar)
        return barra

    def _build_sidebar(self) -> SidebarPanel:
        painel = SidebarPanel()

        self._lbl_titulo = subtext("—", wrap=True)
        painel.header.addWidget(field_label("Página em exibição"))
        painel.header.addWidget(self._lbl_titulo)

        linha = QHBoxLayout()
        titulo = QLabel("Capturas")
        titulo.setObjectName("heading")
        linha.addWidget(titulo)
        linha.addStretch()
        self._lbl_contagem = subtext("—")
        linha.addWidget(self._lbl_contagem)
        painel.body.addLayout(linha)

        self._lista = QListWidget()
        self._lista.setWordWrap(True)
        self._lista.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg']}; "
            f"border: 1px solid {PALETTE['border']}; border-radius: 6px; }}"
            f"QListWidget::item {{ padding: 9px 10px; "
            f"border-bottom: 1px solid {PALETTE['surface2']}; }}")
        painel.body.addWidget(self._lista, 1)

        botoes = QHBoxLayout()
        self._btn_remover = QPushButton("  Remover")
        self._btn_remover.setIcon(draw_icon("trash", 14, PALETTE["danger"]))
        self._btn_remover.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_remover.clicked.connect(self._remover)
        botoes.addWidget(self._btn_remover)
        painel.body.addLayout(botoes)

        # Declaração da condição de acesso. Conteúdo restrito é fato
        # diferente de conteúdo público, e o termo precisa dizer qual foi.
        painel.body.addWidget(hsep())
        self._chk_auth = QCheckBox("Sessão autenticada")
        self._chk_auth.setToolTip(
            "Marque quando o conteúdo só era visível após login. O termo "
            "vai declarar isso em destaque.")
        self._chk_auth.toggled.connect(self._alternar_auth)
        painel.body.addWidget(self._chk_auth)

        self._in_conta = QLineEdit()
        self._in_conta.setPlaceholderText("Conta usada no acesso")
        self._in_conta.setEnabled(False)
        self._in_conta.textChanged.connect(
            lambda t: setattr(self._sessao, "conta", t.strip()))
        painel.body.addWidget(self._in_conta)

        painel.body.addWidget(field_label("Observações"))
        self._in_obs = QPlainTextEdit()
        self._in_obs.setFixedHeight(70)
        self._in_obs.setPlaceholderText("O que mais deva constar do termo")
        self._in_obs.textChanged.connect(
            lambda: setattr(self._sessao, "observacoes",
                            self._in_obs.toPlainText()))
        painel.body.addWidget(self._in_obs)

        self._btn_termo = output_button("Gerar termo")
        self._btn_termo.clicked.connect(self._gerar_termo)
        self._btn_termo.setEnabled(False)
        painel.footer.addWidget(self._btn_termo)
        painel.add_note(
            "Sessão anônima: nada fica gravado nesta máquina ao fechar.")
        return painel

    # ── navegação ────────────────────────────────
    def _ir(self):
        texto = self._in_url.text().strip()
        if not texto:
            return
        if not texto.lower().startswith(("http://", "https://")):
            texto = "https://" + texto
        if WEBVIEW_DISPONIVEL:
            self._pagina.load(QUrl(texto))

    def _voltar(self):
        if WEBVIEW_DISPONIVEL:
            self._pagina.triggerAction(QWebEnginePage.WebAction.Back)

    def _recarregar(self):
        if WEBVIEW_DISPONIVEL:
            self._pagina.triggerAction(QWebEnginePage.WebAction.Reload)

    def _ao_navegar(self, url: QUrl):
        endereco = url.toString()
        self._in_url.setText(endereco)
        seguro = endereco.lower().startswith("https://")
        self._lbl_cadeado.setPixmap(
            draw_icon("check" if seguro else "info", 14,
                      PALETTE["success"] if seguro
                      else PALETTE["warning"]).pixmap(14, 14))
        self._lbl_cadeado.setToolTip(
            "Conexão cifrada (HTTPS)" if seguro
            else "Conexão sem cifra — o conteúdo pode ter sido alterado no "
                 "caminho")

    def _build_aviso_video(self) -> QFrame:
        """Faixa que explica por que um vídeo pode não tocar aqui.

        Fica escondida e só aparece quando a página tem vídeo. O usuário
        não tem como adivinhar que o erro exibido pelo próprio site vem
        de um codec ausente no navegador embutido.
        """
        faixa = QFrame()
        faixa.setStyleSheet(
            f"background: {PALETTE['surface2']}; "
            f"border-bottom: 1px solid {PALETTE['warning']};")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(14, 8, 12, 8)
        linha.setSpacing(10)

        icone = QLabel()
        icone.setPixmap(draw_icon("info", 16, PALETTE["warning"]).pixmap(16, 16))
        icone.setFixedSize(16, 16)
        linha.addWidget(icone)

        texto = QLabel(
            "Esta página tem vídeo. O navegador embutido não reproduz os "
            "formatos H.264 e AAC, usados pela maior parte das redes "
            "sociais — a captura registra a página, o texto e a imagem, "
            "mas não o vídeo em movimento. Para registrar a reprodução, "
            "use a <b>Gravação de Tela</b> com o navegador do sistema.")
        texto.setObjectName("subtext")
        texto.setWordWrap(True)
        linha.addWidget(texto, 1)

        fechar = QPushButton("Entendi")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(lambda: faixa.setVisible(False))
        linha.addWidget(fechar)

        faixa.setVisible(False)
        self._faixa_video = faixa
        #: Uma vez dispensada, não volta a incomodar nesta sessão.
        self._aviso_video_dispensado = False
        fechar.clicked.connect(
            lambda: setattr(self, "_aviso_video_dispensado", True))
        return faixa

    #: Pergunta ao próprio navegador se há vídeo na página e se ele sabe
    #: tocar o formato mais comum. Perguntar é melhor que presumir: se um
    #: dia o componente vier com os codecs, o aviso deixa de aparecer
    #: sozinho, sem ninguém precisar lembrar de removê-lo.
    _SONDA_VIDEO = """
        (function () {
          var temVideo = document.getElementsByTagName('video').length > 0;
          var v = document.createElement('video');
          var toca = v.canPlayType('video/mp4; codecs="avc1.42E01E"') !== '';
          return (temVideo ? '1' : '0') + (toca ? '1' : '0');
        })();
    """

    def _ao_carregar(self, ok: bool):
        self._btn_capturar.setEnabled(bool(ok) and not self._capturando)
        if not ok:
            self.status_msg.emit("Não foi possível carregar o endereço.")
            return
        if self._aviso_video_dispensado or not WEBVIEW_DISPONIVEL:
            return
        try:
            self._pagina.runJavaScript(self._SONDA_VIDEO, self._ao_sondar_video)
        except Exception:                               # noqa: BLE001
            pass

    def _ao_sondar_video(self, resposta):
        """Mostra a faixa quando há vídeo e o formato não é suportado."""
        if not isinstance(resposta, str) or len(resposta) != 2:
            return
        tem_video, sabe_tocar = resposta[0] == "1", resposta[1] == "1"
        self._faixa_video.setVisible(tem_video and not sabe_tocar)

    # ── captura ──────────────────────────────────
    def _capturar(self):
        if not WEBVIEW_DISPONIVEL or self._capturando:
            return
        self._capturando = True
        self._btn_capturar.setEnabled(False)
        self.status_msg.emit("Capturando…")

        c = core.Captura(url=self._pagina.url().toString())
        c.url_final = c.url
        c.titulo = self._pagina.title()
        c.ips = core.resolver(c.host)
        c.certificado = core.certificado_tls(c.host)
        c.recursos = list(self._espiao.recursos)

        n = len(self._sessao.capturas) + 1
        destino = self._pasta / f"{n:02d}"
        destino.mkdir(parents=True, exist_ok=True)

        # O certificado diz quem o servidor afirma ser; o registro diz
        # quem respondeu pelo nome. A resposta bruta é guardada como peça
        # com resumo próprio: é ela que um terceiro confere, e não o que
        # esta ferramenta extraiu dela para exibir.
        c.registro, bruto_rdap = core.registro_do_dominio(c.host)
        if bruto_rdap:
            alvo = destino / "registro-dominio.json"
            try:
                alvo.write_bytes(bruto_rdap)
                c.pecas.append(core.Peca(
                    "registro-dominio.json",
                    "resposta do registro do domínio (RDAP), como recebida",
                    str(alvo)))
            except OSError:
                pass
        pendentes = {"pdf": False, "html": False}

        def concluir():
            if not all(pendentes.values()):
                return
            tela = destino / "tela.png"
            self._view.grab().save(str(tela))
            c.pecas.append(core.Peca("tela.png", "captura da tela exibida",
                                     str(tela)))
            for p in c.pecas:
                p.calcular()
            self._sessao.capturas.append(c)
            self._espiao.limpar()
            self._capturando = False
            self._btn_capturar.setEnabled(True)
            self._preencher_lista()
            self.status_msg.emit(
                f"Captura {n} registrada · resumo {c.resumo[:12]}…")

        def salvar_pdf(dados):
            alvo = destino / "pagina.pdf"
            try:
                alvo.write_bytes(dados)
                c.pecas.append(core.Peca(
                    "pagina.pdf", "página inteira, com texto selecionável",
                    str(alvo)))
            except OSError:
                pass
            pendentes["pdf"] = True
            concluir()

        def salvar_html(texto):
            alvo = destino / "pagina.html"
            try:
                alvo.write_text(texto, encoding="utf-8")
                c.pecas.append(core.Peca(
                    "pagina.html", "código-fonte como exibido (DOM)",
                    str(alvo)))
            except OSError:
                pass
            pendentes["html"] = True
            concluir()

        self._pagina.printToPdf(salvar_pdf)
        self._pagina.toHtml(salvar_html)
        # Rede lenta ou página que nunca assenta não pode travar a
        # ferramenta: passado o limite, encerra com o que houver.
        QTimer.singleShot(20000, lambda: (
            pendentes.update(pdf=True, html=True), concluir()))

    def _preencher_lista(self):
        self._lista.clear()
        for i, c in enumerate(self._sessao.capturas, 1):
            item = QListWidgetItem(
                f" {i}.  {c.titulo or c.url}\n      {c.quando_br} · "
                f"{len(c.pecas)} peça(s)")
            item.setForeground(QColor(PALETTE["text2"]))
            self._lista.addItem(item)
        self._lbl_contagem.setText(str(len(self._sessao.capturas)))
        self._btn_termo.setEnabled(bool(self._sessao.capturas))

    def _remover(self):
        i = self._lista.currentRow()
        if 0 <= i < len(self._sessao.capturas):
            self._sessao.capturas.pop(i)
            self._preencher_lista()

    def _alternar_auth(self, ligado: bool):
        self._sessao.autenticada = ligado
        self._in_conta.setEnabled(ligado)
        if ligado and not self._in_conta.text().strip():
            self.status_msg.emit(
                "Informe a conta usada — o termo precisa declará-la.")

    def _gerar_termo(self):
        if not self._sessao.capturas:
            return
        if self._sessao.autenticada and not self._sessao.conta.strip():
            QMessageBox.warning(
                self, "Conta não informada",
                "A sessão está marcada como autenticada. Informe a conta "
                "utilizada: o termo precisa declarar em que condição o "
                "conteúdo foi visto.")
            return
        TermoDialog(self._sessao, self).exec()

    # ── contrato do casco ────────────────────────
    def shutdown(self):
        if WEBVIEW_DISPONIVEL:
            self._pagina.setUrl(QUrl("about:blank"))
