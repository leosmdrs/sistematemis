"""
Calculadora ePAD — calculadora oficial da CGU, com o manual de uso.

Duas páginas numa ferramenta só:

* **Calculadora** — a página do ePAD/CGU exibida dentro do programa. Exige
  internet e é a única parte do Têmis que sai da máquina.
* **Manual** — o Guia Teórico e Prático da Dosimetria da Sanção
  Disciplinar, baixado uma vez da Base de Conhecimento da CGU e guardado
  na estação. Depois disso abre offline.

A navegação da calculadora é restrita ao domínio da CGU: sem essa trava,
um redirecionamento transformaria o painel num navegador aberto dentro de
um sistema institucional.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import (
    QDesktopServices, QImage, QKeySequence, QPixmap, QShortcut,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
    QLineEdit, QSizePolicy, QButtonGroup, QStackedWidget, QScrollArea,
)

from ..icons import draw_icon
from ..pdfview import VisorPDFContinuo
from ..theme import PALETTE
from ..widgets import (
    SidebarPanel, TOOLBAR_HEIGHT, ViewerToolbar, field_label, group_title,
    output_button, primary_button, subtext, vsep,
)
from .base import ToolPage, ToolMeta

#: Endereço da calculadora, no ePAD/CGU.
URL = "https://epad.cgu.gov.br/publico/calculadora/calc.html?tipo=pad"

#: Manual, na Base de Conhecimento da CGU.
URL_MANUAL = ("https://basedeconhecimento.cgu.gov.br/server/api/core/"
              "bitstreams/1efbd75d-cde7-4b41-9932-91e013d58128/content")
NOME_MANUAL = "Guia_Dosimetria_Sancao_Disciplinar.pdf"

#: Domínio em que a navegação de página inteira é permitida. Fora dele, o
#: endereço vai para o navegador do sistema, onde há barra de endereços.
#: Manter um único domínio reduz a chance de um redirecionamento levar o
#: servidor a uma página que não é oficial.
DOMINIOS = ("cgu.gov.br",)

#: Zoom inicial da calculadora. A página é larga e, em 100%, os
#: enquadramentos ficam cortados na largura útil da janela.
ZOOM_WEB_PADRAO = 0.80
ZOOM_WEB_MIN, ZOOM_WEB_MAX = 0.25, 3.0


META = ToolMeta(
    key="calculadora",
    name="Calculadora ePAD",
    icon="tool_calc",
    tagline="Calculadora oficial da CGU",
    description=(
        "Abre a calculadora do sistema ePAD, da Controladoria-Geral da "
        "União, usada no cálculo de penalidades do processo administrativo "
        "disciplinar, junto com o guia oficial de dosimetria. A calculadora "
        "requer conexão com a internet; o manual, depois de baixado uma "
        "vez, abre offline."
    ),
    online=True,
)


# O motor web é grande e pode não estar presente. Sem ele a calculadora
# passa a abrir no navegador do sistema — o manual continua funcionando,
# porque é renderizado pelo PyMuPDF.
try:
    from PyQt6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineSettings, QWebEngineProfile,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBVIEW_DISPONIVEL = True
except ImportError:  # pragma: no cover
    WEBVIEW_DISPONIVEL = False
    QWebEnginePage = object  # type: ignore


if WEBVIEW_DISPONIVEL:

    class _PaginaRestrita(QWebEnginePage):
        """Página que só navega dentro do domínio da CGU."""

        bloqueou = pyqtSignal(str)

        def acceptNavigationRequest(self, url: QUrl, tipo, is_main_frame: bool):
            if not is_main_frame:
                return True
            host = url.host().lower()
            if host == "" or any(host == d or host.endswith("." + d)
                                 for d in DOMINIOS):
                return True
            self.bloqueou.emit(url.toString())
            QDesktopServices.openUrl(url)
            return False


def pasta_manuais() -> Path:
    import os
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    raiz = Path(base) if base else Path.home() / ".local" / "share"
    destino = raiz / "SistemaTemis" / "manuais"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


# ─────────────────────────────────────────
#  DOWNLOAD DO MANUAL
# ─────────────────────────────────────────

class BaixarThread(QThread):
    """Busca o manual sem travar a interface."""

    concluido = pyqtSignal(str, str)     # caminho, erro

    def __init__(self, url: str, destino: Path):
        super().__init__()
        self._url = url
        self._destino = destino

    def run(self):
        try:
            req = urllib.request.Request(
                self._url, headers={"User-Agent": "SistemaTemis"})
            with urllib.request.urlopen(req, timeout=90) as r:
                dados = r.read()
            if not dados.startswith(b"%PDF"):
                self.concluido.emit("", "o endereço não devolveu um PDF")
                return
            # Grava num temporário e só então renomeia: uma queda no meio
            # do download deixaria um PDF truncado em cache, que passaria a
            # falhar em toda abertura seguinte.
            tmp = self._destino.with_suffix(".parcial")
            tmp.write_bytes(dados)
            tmp.replace(self._destino)
            self.concluido.emit(str(self._destino), "")
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            self.concluido.emit("", str(e))


# ─────────────────────────────────────────
#  VISUALIZADOR DE PDF
# ─────────────────────────────────────────

# ─────────────────────────────────────────
#  FERRAMENTA
# ─────────────────────────────────────────

class CalculadoraTool(ToolPage):

    meta = META

    PAGINAS = [
        ("calculadora", "Calculadora", "tool_calc"),
        ("manual", "Manual", "manual"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = None
        self._pagina = "calculadora"
        self._thread: BaixarThread | None = None
        self._doc_manual: fitz.Document | None = None
        self._zoom_web = ZOOM_WEB_PADRAO
        self._caminho_manual = pasta_manuais() / NOME_MANUAL

        self._build_ui()
        if WEBVIEW_DISPONIVEL:
            self._view.setZoomFactor(self._zoom_web)
            self._view.setUrl(QUrl(URL))

        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        QShortcut(QKeySequence("F5"), self, self._recarregar, context=ctx)
        QShortcut(QKeySequence("+"), self, self._mais_zoom, context=ctx)
        QShortcut(QKeySequence("-"), self, self._menos_zoom, context=ctx)

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
        ml.addWidget(self._build_toolbar())
        ml.addWidget(self._build_aviso())
        ml.addWidget(self._build_conteudo(), 1)
        root.addWidget(main, 1)

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar_frame")
        frame.setFixedHeight(TOOLBAR_HEIGHT)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(6)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._botoes: dict[str, QPushButton] = {}
        for i, (chave, rotulo, icone) in enumerate(self.PAGINAS):
            btn = QPushButton(f"  {rotulo}")
            btn.setIcon(draw_icon(icone, 16, PALETTE["text"]))
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setMinimumWidth(118)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(
                "Calculadora de penalidade administrativa da CGU"
                if chave == "calculadora"
                else "Guia Teórico e Prático da Dosimetria da Sanção Disciplinar")
            btn.clicked.connect(lambda _c, k=chave: self.mostrar(k))
            self._grupo.addButton(btn)
            self._botoes[chave] = btn
            lay.addWidget(btn)

        lay.addWidget(vsep())

        # Cada página tem os seus controles; a faixa troca junto.
        self._controles = QStackedWidget()
        self._controles.setFixedHeight(36)
        self._controles.addWidget(self._controles_web())
        self._controles.addWidget(self._controles_pdf())
        lay.addWidget(self._controles, 1)
        return frame

    def _controles_web(self) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        btn_reload = QPushButton()
        btn_reload.setIcon(draw_icon("reload"))
        btn_reload.setToolTip("Recarregar a calculadora  (F5)")
        btn_reload.setFixedSize(32, 32)
        btn_reload.clicked.connect(self._recarregar)
        lay.addWidget(btn_reload)

        lay.addWidget(vsep())

        rot = QLabel("Zoom:")
        rot.setObjectName("subtext")
        lay.addWidget(rot)

        btn_menos = QPushButton()
        btn_menos.setIcon(draw_icon("minus"))
        btn_menos.setToolTip("Diminuir zoom da calculadora  (−)")
        btn_menos.setFixedSize(32, 32)
        btn_menos.clicked.connect(self._menos_zoom)
        lay.addWidget(btn_menos)

        self._lbl_zoom_web = QLabel(f"{int(ZOOM_WEB_PADRAO * 100)}%")
        self._lbl_zoom_web.setFixedWidth(48)
        self._lbl_zoom_web.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._lbl_zoom_web)

        btn_mais = QPushButton()
        btn_mais.setIcon(draw_icon("plus"))
        btn_mais.setToolTip("Aumentar zoom da calculadora  (+)")
        btn_mais.setFixedSize(32, 32)
        btn_mais.clicked.connect(self._mais_zoom)
        lay.addWidget(btn_mais)

        btn_reset = QPushButton("80%")
        btn_reset.setToolTip("Voltar ao zoom padrão")
        btn_reset.clicked.connect(lambda: self._definir_zoom_web(ZOOM_WEB_PADRAO))
        lay.addWidget(btn_reset)

        lay.addWidget(vsep())

        btn_print = QPushButton("  Recortar tela")
        btn_print.setIcon(draw_icon("camera"))
        btn_print.setToolTip(
            "Abre a Captura e Esboço do Windows (Win+Shift+S) para recortar "
            "um trecho da tela")
        btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_print.clicked.connect(self._capturar_tela)
        lay.addWidget(btn_print)

        # Endereço à vista e somente leitura: numa ferramenta institucional
        # o usuário precisa poder conferir de onde vem o que está usando.
        self._endereco = QLineEdit(URL)
        self._endereco.setReadOnly(True)
        self._endereco.setCursorPosition(0)
        self._endereco.setToolTip("Endereço da página exibida (somente leitura)")
        self._endereco.setStyleSheet(f"QLineEdit {{ color: {PALETTE['text2']}; }}")
        lay.addWidget(self._endereco, 1)

        self._lbl_carregando = subtext("")
        self._lbl_carregando.setFixedWidth(92)
        lay.addWidget(self._lbl_carregando)
        return box

    def _controles_pdf(self) -> QWidget:
        bar = ViewerToolbar()
        # Só a faixa de controles interessa aqui: a moldura de barra já é
        # a da própria ferramenta.
        bar.setObjectName("")
        bar.setStyleSheet("background: transparent;")
        bar.setFixedHeight(36)
        bar.ir_para_pagina.connect(lambda i: self._pdf.ir_para(i))
        bar.zoom_in.connect(lambda: self._pdf.aplicar_zoom(1.25))
        bar.zoom_out.connect(lambda: self._pdf.aplicar_zoom(1 / 1.25))
        bar.ajustar_largura.connect(lambda: self._pdf.ajustar_a_largura())
        bar.add_stretch()
        self._barra_pdf = bar
        return bar

    def _build_aviso(self) -> QFrame:
        self._aviso = QFrame()
        self._aviso.setFixedHeight(32)
        self._aviso.setStyleSheet(
            f"background: {PALETTE['surface2']}; "
            f"border-bottom: 1px solid {PALETTE['border']};")
        lay = QHBoxLayout(self._aviso)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        self._icone_aviso = QLabel()
        lay.addWidget(self._icone_aviso)
        self._texto_aviso = QLabel("")
        self._texto_aviso.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._texto_aviso)
        lay.addStretch()
        self._atualizar_aviso()
        return self._aviso

    def _atualizar_aviso(self):
        if self._pagina == "calculadora":
            cor, icone = PALETTE["info"], "globe"
            texto = ("<b>Página externa</b> — conteúdo hospedado pela "
                     "Controladoria-Geral da União. Requer internet; as "
                     "demais ferramentas do Têmis funcionam offline.")
        else:
            cor, icone = PALETTE["success"], "manual"
            texto = ("<b>Guia oficial da CGU</b> — baixado uma vez e "
                     "guardado nesta estação. A partir daí abre sem internet.")
        self._icone_aviso.setPixmap(draw_icon(icone, 14, cor).pixmap(14, 14))
        self._texto_aviso.setText(
            f"<span style='color:{cor}'>{texto.split('—')[0]}</span>"
            f"<span style='color:{PALETTE['text2']}'>—"
            f"{texto.split('—', 1)[1]}</span>")

    def _build_conteudo(self) -> QWidget:
        self._pilha = QStackedWidget()

        if WEBVIEW_DISPONIVEL:
            self._view = QWebEngineView()
            # Perfil anônimo (sem nome): existe só em memória e some ao
            # fechar. Um perfil *nomeado* grava um diretório de estado na
            # estação — justamente o rastro de navegação que não se quer
            # deixar — e ainda derrubava o programa ao ser construído.
            # A referência fica no objeto porque, no QtWebEngine, o perfil
            # precisa sobreviver à página que o usa.
            self._perfil = QWebEngineProfile(self._view)
            self._perfil.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self._perfil.setHttpCacheType(
                QWebEngineProfile.HttpCacheType.MemoryHttpCache)

            pagina = _PaginaRestrita(self._perfil, self._view)
            pagina.bloqueou.connect(self._ao_bloquear)
            self._view.setPage(pagina)

            cfg = self._view.settings()
            for chave in (
                QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
                QWebEngineSettings.WebAttribute.ScreenCaptureEnabled,
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            ):
                cfg.setAttribute(chave, False)

            self._view.loadStarted.connect(
                lambda: self._lbl_carregando.setText("carregando…"))
            self._view.loadFinished.connect(self._ao_terminar)
            self._view.urlChanged.connect(self._ao_mudar_url)
            self._pilha.addWidget(self._view)
        else:
            self._pilha.addWidget(self._painel_sem_web())

        self._pdf = VisorPDFContinuo()
        self._pdf.pagina_mudou.connect(
            lambda i: self._barra_pdf.set_page(i, self._pdf.total()))
        self._pdf.zoom_mudou.connect(self._barra_pdf.set_zoom)
        self._pdf.mensagem("Abra a aba Manual para baixar o guia.")
        self._pilha.addWidget(self._pdf)
        return self._pilha

    def _painel_sem_web(self) -> QWidget:
        painel = QWidget()
        painel.setStyleSheet(f"background: {PALETTE['bg']};")
        lay = QVBoxLayout(painel)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(12)

        icone = QLabel()
        icone.setPixmap(draw_icon("tool_calc", 56, PALETTE["text3"], 2.2)
                        .pixmap(56, 56))
        icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icone)

        titulo = QLabel("Visualizador web indisponível")
        titulo.setObjectName("heading")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(titulo)

        msg = QLabel(
            "Este pacote foi gerado sem o componente de exibição de páginas. "
            "A calculadora continua acessível pelo navegador; o manual, na "
            "aba ao lado, funciona normalmente.")
        msg.setObjectName("subtext")
        msg.setWordWrap(True)
        msg.setMaximumWidth(520)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(msg, 0, Qt.AlignmentFlag.AlignCenter)

        btn = output_button("Abrir no navegador", "globe")
        btn.setMaximumWidth(260)
        btn.clicked.connect(self._abrir_no_navegador)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        return painel

    def _build_sidebar(self) -> SidebarPanel:
        panel = SidebarPanel()

        self._btn_recarregar = primary_button("Recarregar calculadora", "reload")
        self._btn_recarregar.clicked.connect(self._recarregar)
        panel.header.addWidget(self._btn_recarregar)
        panel.header.addWidget(subtext("Conteúdo oficial do ePAD/CGU", wrap=True))

        panel.body.addWidget(group_title("Sobre esta ferramenta"))
        panel.body.addWidget(subtext(
            "A calculadora do sistema ePAD, da Controladoria-Geral da União, "
            "apoia o cálculo de penalidades no processo administrativo "
            "disciplinar. O botão “Manual”, na barra acima, abre o Guia "
            "Teórico e Prático da Dosimetria da Sanção Disciplinar.",
            wrap=True))

        panel.body.addWidget(group_title("Origem do conteúdo"))
        for rotulo, endereco in (("Calculadora — ePAD/CGU", URL),
                                 ("Manual — Base de Conhecimento/CGU",
                                  URL_MANUAL)):
            panel.body.addWidget(field_label(rotulo))
            lbl = QLabel(endereco)
            lbl.setObjectName("muted")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            panel.body.addWidget(lbl)

        panel.body.addWidget(subtext(
            "As páginas são da CGU, não do Sistema Têmis. O resultado do "
            "cálculo deve ser conferido contra a norma aplicável ao caso.",
            wrap=True))

        panel.body.addWidget(group_title("Privacidade"))
        panel.body.addWidget(subtext(
            "Esta é a única ferramenta do Têmis que acessa a internet. Nada "
            "do que você digita na calculadora passa pelo Sistema Têmis, e a "
            "navegação não deixa cookies nem cache gravados na estação.",
            wrap=True))

        panel.body.addStretch()

        btn = output_button("Abrir no navegador", "globe")
        btn.setToolTip("Abre a página atual no navegador padrão do computador")
        btn.clicked.connect(self._abrir_no_navegador)
        panel.footer.addWidget(btn)
        panel.add_note("Conteúdo oficial da Controladoria-Geral da União.")
        return panel

    # ─────────────────────────────────────
    #  TROCA DE PÁGINA
    # ─────────────────────────────────────

    def mostrar(self, chave: str):
        self._pagina = chave
        for k, btn in self._botoes.items():
            btn.setChecked(k == chave)
        indice = 0 if chave == "calculadora" else 1
        self._pilha.setCurrentIndex(indice)
        self._controles.setCurrentIndex(indice)
        self._atualizar_aviso()

        if chave == "calculadora":
            self._btn_recarregar.setText("  Recarregar calculadora")
            self.status_msg.emit("Calculadora ePAD — página oficial da CGU")
        else:
            self._btn_recarregar.setText("  Baixar manual de novo")
            self._garantir_manual()

    # ─────────────────────────────────────
    #  MANUAL
    # ─────────────────────────────────────

    def _abrir_manual(self, caminho: str) -> bool:
        """Abre o PDF no visor. Devolve False se o arquivo não presta."""
        try:
            doc = fitz.open(caminho)
        except Exception:
            return False
        if self._doc_manual is not None:
            self._doc_manual.close()
        self._doc_manual = doc
        self._pdf.carregar(doc)
        self._barra_pdf.set_page(0, len(doc))
        self._barra_pdf.set_zoom(self._pdf.zoom())
        return True

    def _garantir_manual(self, forcar: bool = False):
        if self._doc_manual is not None and not forcar:
            return
        if self._caminho_manual.exists() and not forcar:
            if self._abrir_manual(str(self._caminho_manual)):
                self.status_msg.emit(
                    f"Manual — {self._pdf.total()} páginas (arquivo local)")
                return
            # Cache ilegível: apaga e baixa de novo.
            self._caminho_manual.unlink(missing_ok=True)
        self._baixar_manual()

    def _baixar_manual(self):
        if self._thread is not None and self._thread.isRunning():
            return
        self._pdf.mensagem("Baixando o manual da Base de Conhecimento da CGU…")
        self.status_msg.emit("Baixando o manual (1,8 MB)…")

        self._thread = BaixarThread(URL_MANUAL, self._caminho_manual)
        self._thread.concluido.connect(self._ao_baixar)
        self._thread.start()

    def _ao_baixar(self, caminho: str, erro: str):
        if erro or not caminho:
            self._pdf.mensagem(
                "Não foi possível baixar o manual.<br><br>"
                "Verifique a conexão com a internet e o acesso a "
                "basedeconhecimento.cgu.gov.br,<br>ou use “Abrir no "
                "navegador”, no painel à esquerda.")
            self.status_msg.emit(f"Falha ao baixar o manual: {erro[:80]}")
            return
        if not self._abrir_manual(caminho):
            self._pdf.mensagem("O manual baixado não pôde ser aberto.")
            self.status_msg.emit("O arquivo baixado não é um PDF válido")
            return
        self.status_msg.emit(
            f"Manual baixado — {self._pdf.total()} páginas, disponível offline")

    # ─────────────────────────────────────
    #  CALCULADORA
    # ─────────────────────────────────────

    def _recarregar(self):
        if self._pagina == "manual":
            self._garantir_manual(forcar=True)
            return
        if self._view is None:
            self._abrir_no_navegador()
            return
        # Volta ao endereço inicial: recarregar só faz sentido se devolver a
        # calculadora, e não uma página qualquer a que se tenha chegado.
        self._view.setUrl(QUrl(URL))
        self.status_msg.emit("Recarregando a calculadora…")

    # ── zoom da calculadora ──────────────────────
    def _definir_zoom_web(self, fator: float):
        fator = round(max(ZOOM_WEB_MIN, min(ZOOM_WEB_MAX, fator)), 2)
        self._zoom_web = fator
        if self._view is not None:
            self._view.setZoomFactor(fator)
        self._lbl_zoom_web.setText(f"{int(round(fator * 100))}%")

    def _mais_zoom(self):
        if self._pagina == "manual":
            self._pdf.aplicar_zoom(1.25)
        else:
            self._definir_zoom_web(self._zoom_web * 1.1)

    def _menos_zoom(self):
        if self._pagina == "manual":
            self._pdf.aplicar_zoom(1 / 1.25)
        else:
            self._definir_zoom_web(self._zoom_web / 1.1)

    # ── captura de tela ──────────────────────────
    def _capturar_tela(self):
        """Abre o recorte de tela do Windows.

        Duas vias, nesta ordem:

        1. O protocolo ``ms-screenclip:``, que abre a sobreposição de
           recorte diretamente. É o caminho oficial e não depende de
           sintetizar teclas.
        2. O atalho Win+Shift+S, para instalações em que o protocolo não
           esteja registrado.

        A primeira versão usava só o atalho, com uma estrutura ``INPUT``
        de 32 bytes — o Windows x64 exige 40, porque a união precisa
        comportar o maior membro (``MOUSEINPUT``). Com o tamanho errado o
        ``SendInput`` recusa a chamada sem qualquer efeito visível.
        """
        if sys.platform != "win32":
            self.status_msg.emit(
                "O recorte de tela do Windows não existe neste sistema")
            return

        if QDesktopServices.openUrl(QUrl("ms-screenclip:")):
            self.status_msg.emit(
                "Recorte de tela aberto — selecione a área desejada")
            return

        if self._enviar_win_shift_s():
            self.status_msg.emit(
                "Recorte de tela acionado — selecione a área desejada")
        else:
            self.status_msg.emit(
                "Não foi possível abrir o recorte de tela. Use Win+Shift+S.")

    @staticmethod
    def _enviar_win_shift_s() -> bool:
        """Envia Win+Shift+S ao sistema. Devolve False se não conseguir."""
        try:
            import ctypes
            from ctypes import wintypes

            VK_LWIN, VK_SHIFT, VK_S = 0x5B, 0x10, 0x53
            KEYEVENTF_KEYUP = 0x0002

            class _MOUSE(ctypes.Structure):
                _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                            ("mouseData", wintypes.DWORD),
                            ("dwFlags", wintypes.DWORD),
                            ("time", wintypes.DWORD),
                            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

            class _KEYBD(ctypes.Structure):
                _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                            ("dwFlags", wintypes.DWORD),
                            ("time", wintypes.DWORD),
                            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

            class _HARDWARE(ctypes.Structure):
                _fields_ = [("uMsg", wintypes.DWORD),
                            ("wParamL", wintypes.WORD),
                            ("wParamH", wintypes.WORD)]

            class _INPUT(ctypes.Structure):
                class _U(ctypes.Union):
                    # Os três membros precisam estar declarados: o tamanho
                    # da união é o do maior deles, e é esse tamanho que o
                    # SendInput confere.
                    _fields_ = [("mi", _MOUSE), ("ki", _KEYBD),
                                ("hi", _HARDWARE)]
                _anonymous_ = ("u",)
                _fields_ = [("type", wintypes.DWORD), ("u", _U)]

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SendInput.argtypes = (wintypes.UINT,
                                         ctypes.POINTER(_INPUT), ctypes.c_int)
            user32.SendInput.restype = wintypes.UINT

            def tecla(codigo, solta=False):
                return _INPUT(type=1, ki=_KEYBD(
                    wVk=codigo, wScan=0,
                    dwFlags=KEYEVENTF_KEYUP if solta else 0,
                    time=0, dwExtraInfo=None))

            seq = (tecla(VK_LWIN), tecla(VK_SHIFT), tecla(VK_S),
                   tecla(VK_S, True), tecla(VK_SHIFT, True),
                   tecla(VK_LWIN, True))
            vetor = (_INPUT * len(seq))(*seq)
            return user32.SendInput(len(seq), vetor,
                                    ctypes.sizeof(_INPUT)) == len(seq)
        except Exception:
            return False

    def _abrir_no_navegador(self):
        endereco = URL if self._pagina == "calculadora" else URL_MANUAL
        QDesktopServices.openUrl(QUrl(endereco))
        self.status_msg.emit("Página aberta no navegador do computador")

    def _ao_terminar(self, ok: bool):
        self._lbl_carregando.setText("" if ok else "falhou")
        if ok:
            self.status_msg.emit("Calculadora ePAD carregada")
        else:
            self.status_msg.emit(
                "Não foi possível carregar a calculadora — verifique a "
                "conexão e o acesso a epad.cgu.gov.br")

    def _ao_mudar_url(self, url: QUrl):
        self._endereco.setText(url.toString())
        self._endereco.setCursorPosition(0)

    def _ao_bloquear(self, url: str):
        self.status_msg.emit(f"Link externo aberto no navegador: {url[:70]}")

    # ─────────────────────────────────────
    #  CICLO DE VIDA
    # ─────────────────────────────────────

    def on_activated(self):
        if self._pagina == "manual":
            self._garantir_manual()
        elif self._view is None:
            self.status_msg.emit(
                "Visualizador web indisponível — use “Abrir no navegador”")
        else:
            self.status_msg.emit("Calculadora ePAD — página oficial da CGU")

    def shutdown(self):
        if self._thread is not None and self._thread.isRunning():
            self._thread.wait(3000)
        if self._doc_manual is not None:
            self._doc_manual.close()
            self._doc_manual = None
        if self._view is not None:
            # Sem parar o carregamento, o processo do motor web pode
            # segurar o encerramento do programa.
            self._view.stop()
            self._view.setPage(None)
            self._view = None
