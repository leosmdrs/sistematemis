"""
Visor de PDF com rolagem vertical contínua.

Todas as páginas ficam empilhadas numa única área rolável: descer o
documento é rolar, e não clicar em "próxima". Trocar de página a cada
clique quebrava o fluxo de leitura, que é justamente o que se faz ao
examinar autos.

As páginas são desenhadas sob demanda — só as visíveis e as vizinhas
imediatas guardam imagem. Um processo com centenas de páginas em 150% de
zoom consumiria alguns gigabytes se todas fossem mantidas renderizadas.

Cada ferramenta fornece a sua própria classe de página (`fabrica`), o que
lhe permite desenhar por cima: as tarjas na Tarja Preta, os achados no
Anti-Injection. A conversão entre a tela e o papel fica em `PaginaPDF`,
uma vez só, em vez de repetida em cada ferramenta.
"""

from __future__ import annotations

import fitz

from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QLabel, QScrollArea, QVBoxLayout, QWidget, QFrame, QSizePolicy,
)

from .theme import PALETTE

#: Quantas páginas antes e depois da faixa visível ficam prontas.
MARGEM_RENDER = 1

#: Espaço entre as folhas.
ESPACO = 18


class PaginaPDF(QLabel):
    """Uma página do documento, base para as sobreposições das ferramentas."""

    def __init__(self, indice: int, parent=None):
        super().__init__(parent)
        self.indice = indice
        self.escala = 1.0
        self.largura_pt = 0.0
        self.altura_pt = 0.0
        self._pronta = False

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: #FFFFFF;")

    # ── geometria ────────────────────────────────
    def definir_medidas(self, largura_pt: float, altura_pt: float, escala: float):
        """Fixa o tamanho do widget mesmo antes de haver imagem.

        Reservar o espaço desde o início mantém a barra de rolagem estável:
        sem isso, o documento "pularia" conforme as páginas fossem sendo
        desenhadas.
        """
        self.largura_pt = largura_pt
        self.altura_pt = altura_pt
        self.escala = escala
        self.setFixedSize(QSize(max(1, round(largura_pt * escala)),
                                max(1, round(altura_pt * escala))))

    def pronta(self) -> bool:
        return self._pronta

    def definir_imagem(self, pm: QPixmap):
        self._pronta = True
        self.setPixmap(pm)
        self.update()

    def liberar(self):
        """Descarta a imagem, preservando o espaço reservado."""
        if not self._pronta:
            return
        self._pronta = False
        self.setPixmap(QPixmap())
        self.update()

    # ── conversão tela ↔ papel ───────────────────
    def para_pdf(self, r: QRect) -> fitz.Rect:
        e = self.escala
        return fitz.Rect(r.left() / e, r.top() / e,
                         r.right() / e, r.bottom() / e)

    def para_tela(self, r: fitz.Rect) -> QRect:
        e = self.escala
        return QRect(QPoint(round(r.x0 * e), round(r.y0 * e)),
                     QPoint(round(r.x1 * e), round(r.y1 * e)))

    # ── pintura ──────────────────────────────────
    def paintEvent(self, ev):
        super().paintEvent(ev)
        if not self._pronta:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor("#FFFFFF"))
            p.setPen(QColor(PALETTE["text3"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       f"página {self.indice + 1}")
            p.end()
            return
        self.desenhar_sobreposicao()

    def desenhar_sobreposicao(self):
        """Ponto de extensão das ferramentas."""


class VisorPDFContinuo(QScrollArea):
    """Empilha as páginas de um PDF numa rolagem única."""

    pagina_mudou = pyqtSignal(int)      # índice 0-based
    zoom_mudou = pyqtSignal(float)

    ZOOM_MIN, ZOOM_MAX = 0.25, 4.0

    def __init__(self, fabrica=PaginaPDF, parent=None):
        super().__init__(parent)
        self._fabrica = fabrica
        self._doc: fitz.Document | None = None
        self._paginas: list[PaginaPDF] = []
        self._zoom = 1.0
        self._atual = 0

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._suporte = QWidget()
        self._suporte.setStyleSheet(f"background: {PALETTE['bg']};")
        self._pilha = QVBoxLayout(self._suporte)
        self._pilha.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._pilha.setContentsMargins(24, 24, 24, 24)
        self._pilha.setSpacing(ESPACO)
        self.setWidget(self._suporte)

        self._vazio = QLabel("")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pilha.addWidget(self._vazio)

        # Redesenhar a cada pixel de rolagem seria desperdício; o disparo
        # é adiado para quando a rolagem se acalma.
        self._agenda = QTimer(self)
        self._agenda.setSingleShot(True)
        self._agenda.setInterval(60)
        self._agenda.timeout.connect(self._atualizar_visiveis)
        self.verticalScrollBar().valueChanged.connect(self._ao_rolar)

    # ─────────────────────────────────────
    #  DOCUMENTO
    # ─────────────────────────────────────

    def carregar(self, doc: fitz.Document | None):
        self._limpar()
        self._doc = doc
        if doc is None or len(doc) == 0:
            return
        for i in range(len(doc)):
            pagina = self._fabrica(i)
            r = doc[i].rect
            pagina.definir_medidas(r.width, r.height, self._zoom)
            self._pilha.addWidget(pagina, 0, Qt.AlignmentFlag.AlignHCenter)
            self._paginas.append(pagina)
        self._vazio.setVisible(False)
        self._atual = 0

        # Força o cálculo do layout agora. Sem isto, todas as páginas ficam
        # em y=0 até o próximo ciclo de eventos: a barra de rolagem nasce
        # sem curso e a renderização sob demanda considera o documento
        # inteiro visível, desenhando todas as páginas de uma vez.
        self._pilha.activate()
        self._suporte.adjustSize()

        self.verticalScrollBar().setValue(0)
        self._atualizar_visiveis()
        QTimer.singleShot(0, self._atualizar_visiveis)
        self.pagina_mudou.emit(0)

    def _limpar(self):
        for p in self._paginas:
            self._pilha.removeWidget(p)
            p.deleteLater()
        self._paginas = []
        self._doc = None
        self._vazio.setVisible(True)

    def mensagem(self, texto: str):
        self._limpar()
        self._vazio.setText(
            f"<div style='color:{PALETTE['text3']};font-size:15px;'>"
            f"{texto}</div>")
        self._vazio.setVisible(True)

    # ─────────────────────────────────────
    #  ACESSO
    # ─────────────────────────────────────

    def documento(self) -> fitz.Document | None:
        return self._doc

    def total(self) -> int:
        return len(self._paginas)

    def paginas(self) -> list[PaginaPDF]:
        return list(self._paginas)

    def pagina(self, indice: int) -> PaginaPDF | None:
        if 0 <= indice < len(self._paginas):
            return self._paginas[indice]
        return None

    def pagina_atual(self) -> int:
        return self._atual

    def zoom(self) -> float:
        return self._zoom

    # ─────────────────────────────────────
    #  NAVEGAÇÃO
    # ─────────────────────────────────────

    def ir_para(self, indice: int):
        if not self._paginas:
            return
        indice = max(0, min(len(self._paginas) - 1, indice))
        alvo = self._paginas[indice]
        # Encosta o topo da página no topo da área visível, descontando a
        # margem, para a folha não ficar "meio cortada" ao chegar.
        y = alvo.pos().y() - self._pilha.contentsMargins().top()
        self.verticalScrollBar().setValue(max(0, y))
        self._definir_atual(indice)

    def definir_zoom(self, z: float):
        z = round(max(self.ZOOM_MIN, min(self.ZOOM_MAX, z)), 2)
        if abs(z - self._zoom) < 1e-4 or not self._paginas:
            self._zoom = z
            self.zoom_mudou.emit(z)
            return

        # Preserva a posição relativa dentro da página em que se está, para
        # o zoom não jogar o leitor para outro ponto do documento.
        atual = self._atual
        pagina = self._paginas[atual]
        barra = self.verticalScrollBar()
        desloc = barra.value() - pagina.pos().y()
        fracao = desloc / max(1, pagina.height())

        self._zoom = z
        for p in self._paginas:
            p.definir_medidas(p.largura_pt, p.altura_pt, z)
            p.liberar()

        self._suporte.adjustSize()
        QTimer.singleShot(0, lambda: self._restaurar(atual, fracao))
        self.zoom_mudou.emit(z)

    def _restaurar(self, indice: int, fracao: float):
        pagina = self._paginas[indice] if indice < len(self._paginas) else None
        if pagina is not None:
            self.verticalScrollBar().setValue(
                max(0, pagina.pos().y() + int(fracao * pagina.height())))
        self._atualizar_visiveis()

    def aplicar_zoom(self, fator: float):
        self.definir_zoom(self._zoom * fator)

    def ajustar_a_largura(self):
        """Zoom que faz a página caber na largura da área visível."""
        if not self._paginas:
            return
        margens = self._pilha.contentsMargins()
        util = (self.viewport().width() - margens.left() - margens.right()
                - self.verticalScrollBar().sizeHint().width() - 4)
        largura = self._paginas[self._atual].largura_pt
        if largura > 0 and util > 0:
            self.definir_zoom(util / largura)

    # ─────────────────────────────────────
    #  RENDERIZAÇÃO SOB DEMANDA
    # ─────────────────────────────────────

    def _ao_rolar(self):
        self._agenda.start()
        self._detectar_pagina()

    def wheelEvent(self, ev):
        # Ctrl + roda dá zoom, como em qualquer leitor de PDF.
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.aplicar_zoom(1.1 if ev.angleDelta().y() > 0 else 1 / 1.1)
            ev.accept()
            return
        super().wheelEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._agenda.start()

    def _faixa_visivel(self) -> tuple[int, int]:
        if not self._paginas:
            return (0, -1)
        topo = self.verticalScrollBar().value()
        base = topo + self.viewport().height()
        primeiro, ultimo = None, None
        for i, p in enumerate(self._paginas):
            y0, y1 = p.pos().y(), p.pos().y() + p.height()
            if y1 >= topo and y0 <= base:
                if primeiro is None:
                    primeiro = i
                ultimo = i
        if primeiro is None:
            return (self._atual, self._atual)
        return (primeiro, ultimo)

    def _detectar_pagina(self):
        """A página corrente é a que ocupa mais área da janela."""
        if not self._paginas:
            return
        topo = self.verticalScrollBar().value()
        base = topo + self.viewport().height()
        melhor, area_melhor = self._atual, -1
        for i, p in enumerate(self._paginas):
            y0, y1 = p.pos().y(), p.pos().y() + p.height()
            area = max(0, min(y1, base) - max(y0, topo))
            if area > area_melhor:
                melhor, area_melhor = i, area
        self._definir_atual(melhor)

    def _definir_atual(self, indice: int):
        if indice != self._atual:
            self._atual = indice
            self.pagina_mudou.emit(indice)

    def _atualizar_visiveis(self):
        if not self._paginas or self._doc is None:
            return
        primeiro, ultimo = self._faixa_visivel()
        de = max(0, primeiro - MARGEM_RENDER)
        ate = min(len(self._paginas) - 1, ultimo + MARGEM_RENDER)

        for i, pagina in enumerate(self._paginas):
            if de <= i <= ate:
                if not pagina.pronta():
                    self._render(i)
            elif pagina.pronta():
                pagina.liberar()

    def _render(self, indice: int):
        pagina = self._paginas[indice]
        try:
            pix = self._doc[indice].get_pixmap(
                matrix=fitz.Matrix(self._zoom, self._zoom), alpha=False)
        except Exception:
            return
        pagina.definir_imagem(
            QPixmap.fromImage(QImage.fromData(pix.tobytes("ppm"))))

    def redesenhar(self):
        """Força o redesenho das páginas já prontas (sobreposições mudaram)."""
        for p in self._paginas:
            p.update()
