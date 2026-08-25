"""
Ícones e marca do Sistema Têmis, desenhados vetorialmente.

Nada aqui depende de arquivos de imagem, de emoji ou de glifos especiais:
caracteres como '＋', '⬛' ou '🗑' viram um quadrado vazio quando a fonte do
sistema não os possui. Desenhar com QPainter garante que o ícone apareça
em qualquer máquina e em qualquer DPI.
"""

from functools import lru_cache

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QIcon, QPainterPath, QFont,
)

from .theme import PALETTE


# ─────────────────────────────────────────
#  MARCA — a balança de Têmis
# ─────────────────────────────────────────

def draw_temis_mark(painter: QPainter, size: float, color: str, weight: float = 0.055):
    """Desenha a balança de Têmis num quadrado size×size.

    O mastro vertical com o travessão horizontal forma naturalmente um **T**
    — a inicial de Têmis é a própria estrutura da balança, e não um
    ornamento acrescentado por cima dela.
    """
    s = size
    pen = QPen(QColor(color), max(1.0, s * weight))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    cx = s * 0.50
    beam_y = s * 0.30
    left_x, right_x = s * 0.17, s * 0.83

    # Mastro e travessão (o "T")
    painter.drawLine(QPointF(cx, s * 0.17), QPointF(cx, s * 0.79))
    painter.drawLine(QPointF(left_x, beam_y), QPointF(right_x, beam_y))

    # Base
    painter.drawLine(QPointF(s * 0.30, s * 0.83), QPointF(s * 0.70, s * 0.83))

    # Tirantes e pratos
    pan_y = s * 0.45
    pan_w = s * 0.30
    for x in (left_x, right_x):
        painter.drawLine(QPointF(x, beam_y), QPointF(x, pan_y))
        bowl = QRectF(x - pan_w / 2, pan_y - pan_w * 0.42, pan_w, pan_w * 0.84)
        painter.drawArc(bowl, 180 * 16, 180 * 16)   # semicírculo inferior

    # Pino superior
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.PenStyle.NoPen)
    r = s * 0.055
    painter.drawEllipse(QPointF(cx, s * 0.155), r, r)


def temis_pixmap(size: int = 128, plate: bool = True,
                 fg: str = None, bg: str = None) -> QPixmap:
    """Marca do Têmis como QPixmap. Com `plate`, sobre a placa azul-marinho."""
    fg = fg or PALETTE["gold"]
    bg = bg or PALETTE["surface"]

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    if plate:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        p.fillPath(path, QColor(bg))

        # Abaixo de ~32px a borda interna e a marca disputam os mesmos
        # pixels e o ícone vira um borrão: nesses tamanhos a borda sai e
        # a balança cresce, ganhando o espaço inteiro da placa.
        small = size < 32
        if not small:
            inset = size * 0.02
            p.setPen(QPen(QColor(fg), max(1.0, size * 0.02)))
            p.drawRoundedRect(
                QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
                size * 0.20, size * 0.20,
            )

        pad, weight = (0.08, 0.085) if small else (0.16, 0.055)
        p.translate(size * pad, size * pad)
        draw_temis_mark(p, size * (1 - 2 * pad), fg, weight)
    else:
        draw_temis_mark(p, size, fg)

    p.end()
    return pm


def app_icon() -> QIcon:
    """Ícone da aplicação em vários tamanhos (janela, barra de tarefas)."""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(temis_pixmap(s))
    return icon


# ─────────────────────────────────────────
#  ÍCONES DE INTERFACE
# ─────────────────────────────────────────

@lru_cache(maxsize=512)
def draw_icon(kind: str, size: int = 16, color: str = None, width: float = 1.8) -> QIcon:
    """Ícone de interface desenhado vetorialmente."""
    color = color or PALETTE["text"]
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    s = float(size)
    c = s / 2.0
    m = s * 0.24

    def poly(*pts):
        path = QPainterPath(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        p.drawPath(path)

    # ── genéricos ────────────────────────────────
    if kind == "plus":
        p.drawLine(QPointF(m, c), QPointF(s - m, c))
        p.drawLine(QPointF(c, m), QPointF(c, s - m))
    elif kind == "minus":
        p.drawLine(QPointF(m, c), QPointF(s - m, c))
    elif kind == "chevron_left":
        poly((c + s * 0.13, m), (c - s * 0.15, c), (c + s * 0.13, s - m))
    elif kind == "arrow_left":
        p.drawLine(QPointF(m, c), QPointF(s - m, c))
        poly((m + s * 0.20, c - s * 0.18), (m, c), (m + s * 0.20, c + s * 0.18))
    elif kind == "chevron_right":
        poly((c - s * 0.13, m), (c + s * 0.15, c), (c - s * 0.13, s - m))
    elif kind == "undo":
        p.drawArc(QRectF(m, m * 1.15, s - 2 * m, s - 2 * m), 20 * 16, 300 * 16)
        poly((m + s * 0.02, c - s * 0.20), (m - s * 0.02, c + s * 0.06),
             (m + s * 0.24, c + s * 0.02))
    elif kind == "trash":
        p.drawLine(QPointF(m - 1, m + s * 0.10), QPointF(s - m + 1, m + s * 0.10))
        p.drawLine(QPointF(c - s * 0.10, m - s * 0.02), QPointF(c + s * 0.10, m - s * 0.02))
        poly((m + s * 0.06, m + s * 0.10), (m + s * 0.13, s - m),
             (s - m - s * 0.13, s - m), (s - m - s * 0.06, m + s * 0.10))
    elif kind == "save":
        poly((m, s - m), (m, m), (s - m * 1.4, m), (s - m, m * 1.4),
             (s - m, s - m), (m, s - m))
        p.drawLine(QPointF(c - s * 0.15, m), QPointF(c - s * 0.15, c - s * 0.06))
        p.drawLine(QPointF(c + s * 0.15, m), QPointF(c + s * 0.15, c - s * 0.06))
    elif kind == "open":
        poly((m, s - m * 1.1), (m, m * 1.1), (c - s * 0.06, m * 1.1),
             (c + s * 0.02, m * 1.6), (s - m, m * 1.6), (s - m, s - m * 1.1), (m, s - m * 1.1))
    elif kind == "info":
        p.drawEllipse(QPointF(c, c), c - m * 0.5, c - m * 0.5)
        p.drawLine(QPointF(c, c - s * 0.04), QPointF(c, c + s * 0.16))
        p.drawPoint(QPointF(c, c - s * 0.17))
    elif kind == "cracha":
        # cartão de identificação: a moldura, o retrato à esquerda e duas
        # linhas de dados à direita
        p.drawRoundedRect(QRectF(m * 0.7, m, s - m * 1.4, s - m * 2),
                          s * 0.06, s * 0.06)
        p.drawEllipse(QPointF(c - s * 0.14, c - s * 0.06), s * 0.06, s * 0.06)
        p.drawArc(QRectF(c - s * 0.24, c + s * 0.01, s * 0.2, s * 0.16),
                  0, 180 * 16)
        p.drawLine(QPointF(c + s * 0.03, c - s * 0.06),
                   QPointF(s - m * 1.2, c - s * 0.06))
        p.drawLine(QPointF(c + s * 0.03, c + s * 0.06),
                   QPointF(s - m * 1.7, c + s * 0.06))
    elif kind == "home":
        poly((m, c), (c, m * 0.8), (s - m, c))
        poly((m + s * 0.06, c), (m + s * 0.06, s - m), (s - m - s * 0.06, s - m),
             (s - m - s * 0.06, c))

    # ── ferramentas ──────────────────────────────
    elif kind == "tool_tarja":
        # linhas de texto com uma tarja preta cobrindo a do meio
        p.drawLine(QPointF(m, m + s * 0.04), QPointF(s - m, m + s * 0.04))
        p.drawLine(QPointF(m, s - m - s * 0.04), QPointF(s - m * 1.6, s - m - s * 0.04))
        p.fillRect(QRectF(m, c - s * 0.10, s - 2 * m, s * 0.20), QColor(color))
    elif kind == "tool_hash":
        p.drawLine(QPointF(m + s * 0.10, m), QPointF(m + s * 0.02, s - m))
        p.drawLine(QPointF(s - m - s * 0.02, m), QPointF(s - m - s * 0.10, s - m))
        p.drawLine(QPointF(m - s * 0.02, c - s * 0.13), QPointF(s - m + s * 0.02, c - s * 0.13))
        p.drawLine(QPointF(m - s * 0.02, c + s * 0.13), QPointF(s - m + s * 0.02, c + s * 0.13))
    elif kind == "tool_antiinj":
        # documento com lupa — "revela o invisível"
        poly((m, s - m), (m, m), (c + s * 0.10, m), (c + s * 0.10, c - s * 0.02))
        p.drawLine(QPointF(m + s * 0.08, m + s * 0.12), QPointF(c, m + s * 0.12))
        p.drawEllipse(QPointF(c + s * 0.10, c + s * 0.10), s * 0.19, s * 0.19)
        p.drawLine(QPointF(c + s * 0.24, c + s * 0.24), QPointF(s - m * 0.55, s - m * 0.55))
    elif kind == "tool_transcricao":
        # onda sonora virando linhas de texto
        for i, alt in enumerate((0.16, 0.30, 0.22, 0.34, 0.18)):
            x = m + s * 0.04 + i * s * 0.075
            p.drawLine(QPointF(x, c - s * alt), QPointF(x, c + s * alt))
        for i in range(3):
            y = c - s * 0.16 + i * s * 0.16
            p.drawLine(QPointF(c + s * 0.10, y),
                       QPointF(s - m - (s * 0.10 if i == 2 else 0), y))
    elif kind == "tool_constatacao":
        # janela de navegador com um selo — a página registrada
        p.drawRect(QRectF(m, m + s * 0.06, s - 2 * m, s - 2 * m - s * 0.06))
        p.drawLine(QPointF(m, m + s * 0.24), QPointF(s - m, m + s * 0.24))
        p.setBrush(QBrush(QColor(color)))
        for i in range(3):
            p.drawEllipse(QPointF(m + s * 0.09 + i * s * 0.09, m + s * 0.15),
                          s * 0.022, s * 0.022)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(c + s * 0.16, c + s * 0.20), s * 0.17, s * 0.17)
        poly((c + s * 0.09, c + s * 0.20),
             (c + s * 0.14, c + s * 0.26),
             (c + s * 0.24, c + s * 0.13))
    elif kind == "tool_metadados":
        # etiqueta presa ao documento — o que o arquivo diz sobre si
        poly((m, s - m), (m, m), (c + s * 0.06, m), (c + s * 0.06, s - m),
             (m, s - m))
        p.drawLine(QPointF(m + s * 0.09, m + s * 0.14),
                   QPointF(c - s * 0.02, m + s * 0.14))
        p.drawLine(QPointF(m + s * 0.09, m + s * 0.30),
                   QPointF(c - s * 0.02, m + s * 0.30))
        etiqueta = [(c + s * 0.14, c + s * 0.30), (c + s * 0.14, c - s * 0.06),
                    (s - m * 0.6, c - s * 0.22), (s - m * 0.6, c + s * 0.14)]
        poly(*etiqueta, etiqueta[0])
        p.setBrush(QBrush(QColor(color)))
        p.drawEllipse(QPointF(c + s * 0.24, c - s * 0.02), s * 0.04, s * 0.04)
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == "tool_extracao":
        # janela de navegador com o carimbo de registro — a diligência
        # feita dentro do sistema, e anotada
        p.drawRoundedRect(QRectF(m, m + s * 0.06, s - 2 * m, s - 2 * m - s * 0.12),
                          s * 0.06, s * 0.06)
        p.drawLine(QPointF(m, m + s * 0.24), QPointF(s - m, m + s * 0.24))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            p.drawEllipse(QPointF(m + s * (0.09 + i * 0.08), m + s * 0.15),
                          s * 0.025, s * 0.025)
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(color), max(1.0, s * 0.075))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        poly((c - s * 0.16, c + s * 0.08), (c - s * 0.04, c + s * 0.19),
             (c + s * 0.19, c - s * 0.08))
    elif kind == "tool_espelhamento":
        # celular com a tela espelhada para fora — o que o aparelho
        # mostra, aparecendo no computador
        p.drawRoundedRect(QRectF(m * 0.8, m * 0.6, s * 0.30, s - 2 * m * 0.6),
                          s * 0.05, s * 0.05)
        p.drawLine(QPointF(m * 0.8 + s * 0.10, m * 0.6 + s * 0.04),
                   QPointF(m * 0.8 + s * 0.20, m * 0.6 + s * 0.04))
        p.drawRoundedRect(QRectF(c + s * 0.02, m, s - m - c - s * 0.02 + s * 0.20,
                                 s * 0.44), s * 0.04, s * 0.04)
        p.drawLine(QPointF(c + s * 0.24, m + s * 0.44),
                   QPointF(c + s * 0.24, m + s * 0.56))
        p.drawLine(QPointF(c + s * 0.10, m + s * 0.56),
                   QPointF(c + s * 0.38, m + s * 0.56))
        poly((c - s * 0.04, c + s * 0.20), (c + s * 0.06, c + s * 0.20))
        poly((c + s * 0.01, c + s * 0.15), (c + s * 0.06, c + s * 0.20),
             (c + s * 0.01, c + s * 0.25))
    elif kind == "tool_gravacao":
        # monitor com o ponto de gravação — registrar o que está na tela
        p.drawRoundedRect(QRectF(m, m + s * 0.04, s - 2 * m,
                                 s - 2 * m - s * 0.18),
                          s * 0.07, s * 0.07)
        p.drawLine(QPointF(c - s * 0.15, s - m), QPointF(c + s * 0.15, s - m))
        p.drawLine(QPointF(c, s - m - s * 0.14), QPointF(c, s - m))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(c, c - s * 0.04), s * 0.11, s * 0.11)
    elif kind == "tool_ocrpdf":
        # letra dentro da moldura de leitura — a imagem virando texto
        canto = s * 0.16
        for (ax, ay), (bx, by), (cx2, cy2) in (
                ((m, m + canto), (m, m), (m + canto, m)),
                ((s - m - canto, m), (s - m, m), (s - m, m + canto)),
                ((m, s - m - canto), (m, s - m), (m + canto, s - m)),
                ((s - m - canto, s - m), (s - m, s - m), (s - m, s - m - canto))):
            p.drawLine(QPointF(ax, ay), QPointF(bx, by))
            p.drawLine(QPointF(bx, by), QPointF(cx2, cy2))
        alto, baixo = s * 0.30, s * 0.70
        p.drawLine(QPointF(c - s * 0.15, baixo), QPointF(c, alto))
        p.drawLine(QPointF(c, alto), QPointF(c + s * 0.15, baixo))
        p.drawLine(QPointF(c - s * 0.08, c + s * 0.06),
                   QPointF(c + s * 0.08, c + s * 0.06))
    elif kind == "tool_varredura":
        # lupa sobre uma pilha de arquivos — procurar dentro do acervo
        for i, dy in enumerate((s * 0.30, s * 0.15, s * 0.00)):
            p.drawRoundedRect(
                QRectF(m * 0.8 + i * s * 0.035, m * 0.8 + dy,
                       s * (0.44 - i * 0.035), s * 0.12),
                s * 0.03, s * 0.03)
        raio = s * 0.19
        centro = QPointF(s * 0.63, s * 0.63)
        p.drawEllipse(centro, raio, raio)
        p.drawLine(QPointF(centro.x() + raio * 0.72, centro.y() + raio * 0.72),
                   QPointF(s - m * 0.7, s - m * 0.7))
    elif kind == "tool_atividades":
        # folha de relatório com um relógio no canto: o que se fez, e quando
        poly((m * 0.8, s - m * 0.7), (m * 0.8, m * 0.7), (s - m * 1.4, m * 0.7),
             (s - m * 1.4, c + s * 0.02))
        p.drawLine(QPointF(m * 1.5, m * 1.5), QPointF(s - m * 2.1, m * 1.5))
        p.drawLine(QPointF(m * 1.5, c - s * 0.04), QPointF(s - m * 2.1, c - s * 0.04))
        p.drawLine(QPointF(m * 1.5, c + s * 0.08), QPointF(c - s * 0.02, c + s * 0.08))
        p.drawEllipse(QPointF(s - m * 0.9, s - m * 0.9), s * 0.17, s * 0.17)
        p.drawLine(QPointF(s - m * 0.9, s - m * 0.9),
                   QPointF(s - m * 0.9, s - m * 0.9 - s * 0.1))
        p.drawLine(QPointF(s - m * 0.9, s - m * 0.9),
                   QPointF(s - m * 0.9 + s * 0.08, s - m * 0.9))
    elif kind == "tool_quadro":
        # alfinetes ligados por barbante — o mural de investigação
        a = (s * 0.24, s * 0.26)
        b = (s * 0.76, s * 0.36)
        d = (s * 0.40, s * 0.76)
        p.drawLine(QPointF(*a), QPointF(*b))
        p.drawLine(QPointF(*b), QPointF(*d))
        p.drawLine(QPointF(*d), QPointF(*a))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        for pt in (a, b, d):
            p.drawEllipse(QPointF(*pt), s * 0.12, s * 0.12)
    elif kind == "tool_video":
        p.drawRoundedRect(QRectF(m, m + s * 0.06, s - 2 * m, s - 2 * m - s * 0.12),
                          s * 0.08, s * 0.08)
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath(QPointF(c - s * 0.07, c - s * 0.11))
        path.lineTo(QPointF(c + s * 0.13, c))
        path.lineTo(QPointF(c - s * 0.07, c + s * 0.11))
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "redact":
        p.fillRect(QRectF(m, c - s * 0.16, s - 2 * m, s * 0.32), QColor(color))

    # ── ferramentas do quadro ────────────────────
    elif kind == "cursor":
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        seta = QPainterPath(QPointF(m, m * 0.8))
        for pt in ((m, s - m * 1.1), (m + s * 0.16, s - m * 1.7),
                   (m + s * 0.30, s - m * 0.5), (m + s * 0.40, s - m * 0.85),
                   (m + s * 0.26, s - m * 2.0), (s - m * 1.1, s - m * 2.2)):
            seta.lineTo(QPointF(*pt))
        seta.closeSubpath()
        p.drawPath(seta)
    elif kind == "hand":
        p.drawRoundedRect(QRectF(m + s * 0.06, c - s * 0.06,
                                 s - 2 * m - s * 0.12, s - m - c + s * 0.06),
                          s * 0.10, s * 0.10)
        for dx in (-0.16, 0.0, 0.16):
            p.drawLine(QPointF(c + s * dx, c - s * 0.04),
                       QPointF(c + s * dx, m + s * 0.02))
    elif kind == "note":
        poly((m, m), (s - m, m), (s - m, s - m * 1.5),
             (s - m * 1.5, s - m), (m, s - m), (m, m))
        p.drawLine(QPointF(s - m * 1.5, s - m), QPointF(s - m * 1.5, s - m * 1.5))
        p.drawLine(QPointF(s - m * 1.5, s - m * 1.5), QPointF(s - m, s - m * 1.5))
    elif kind == "image":
        p.drawRoundedRect(QRectF(m, m + s * 0.04, s - 2 * m, s - 2 * m - s * 0.08),
                          s * 0.07, s * 0.07)
        poly((m + s * 0.04, s - m - s * 0.06), (c - s * 0.06, c),
             (c + s * 0.06, c + s * 0.12), (c + s * 0.16, c + s * 0.02),
             (s - m - s * 0.04, s - m - s * 0.06))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(c + s * 0.13, m + s * 0.20), s * 0.055, s * 0.055)
    elif kind == "highlight":
        cor = QColor(color)
        cor.setAlpha(90)
        p.fillRect(QRectF(m, c - s * 0.20, s - 2 * m, s * 0.40), cor)
        p.drawRect(QRectF(m, c - s * 0.20, s - 2 * m, s * 0.40))
    elif kind == "tool_calc":
        p.drawRoundedRect(QRectF(m, m - s * 0.02, s - 2 * m, s - 2 * m + s * 0.04),
                          s * 0.08, s * 0.08)
        p.drawLine(QPointF(m + s * 0.06, c - s * 0.14),
                   QPointF(s - m - s * 0.06, c - s * 0.14))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        for ly in (c + s * 0.02, c + s * 0.18):
            for lx in (c - s * 0.16, c, c + s * 0.16):
                p.drawEllipse(QPointF(lx, ly), s * 0.035, s * 0.035)
    # ── formatação de texto ──────────────────────
    elif kind in ("negrito", "italico", "sublinhado"):
        f = QFont("Georgia", int(s * 0.62))
        f.setStyleHint(QFont.StyleHint.Serif)
        if kind == "negrito":
            f.setBold(True)
            letra = "N"
        elif kind == "italico":
            f.setItalic(True)
            letra = "I"
        else:
            f.setUnderline(True)
            letra = "S"
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(0, 0, s, s), int(Qt.AlignmentFlag.AlignCenter), letra)
    elif kind == "cor":
        f = QFont("Georgia", int(s * 0.55))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(0, -s * 0.10, s, s), int(Qt.AlignmentFlag.AlignCenter), "A")
        p.fillRect(QRectF(m * 0.7, s - m * 0.75, s - m * 1.4, s * 0.13),
                   QColor("#E5484D"))
    elif kind == "cor_limpar":
        f = QFont("Georgia", int(s * 0.55))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(0, -s * 0.10, s, s), int(Qt.AlignmentFlag.AlignCenter), "A")
        p.setPen(QPen(QColor(color), width))
        p.drawLine(QPointF(m * 0.7, s - m * 0.6), QPointF(s - m * 0.7, s - m * 0.6))
    elif kind in ("lista_marcador", "lista_numero"):
        p.setPen(QPen(QColor(color), width))
        for i, y in enumerate((m, c, s - m)):
            p.drawLine(QPointF(c - s * 0.02, y), QPointF(s - m * 0.7, y))
            if kind == "lista_marcador":
                p.setBrush(QBrush(QColor(color)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(m * 0.85, y), s * 0.055, s * 0.055)
                p.setPen(QPen(QColor(color), width))
            else:
                f = QFont("Segoe UI", int(s * 0.30))
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRectF(0, y - s * 0.22, m * 1.5, s * 0.44),
                           int(Qt.AlignmentFlag.AlignCenter), str(i + 1))
    elif kind in ("alinhar_esq", "alinhar_centro", "alinhar_just"):
        curtas = {"alinhar_esq": (0.0, 0.62), "alinhar_centro": (0.19, 0.62),
                  "alinhar_just": (0.0, 1.0)}[kind]
        for i, y in enumerate((m, m + (s - 2 * m) / 3,
                               m + 2 * (s - 2 * m) / 3, s - m)):
            larga = i % 2 == 0
            x0 = m if larga else m + (s - 2 * m) * curtas[0]
            x1 = (s - m if larga
                  else m + (s - 2 * m) * (curtas[0] + curtas[1]))
            p.drawLine(QPointF(x0, y), QPointF(x1, y))
    elif kind in ("seta_cima", "seta_baixo"):
        sinal = 1 if kind == "seta_cima" else -1
        p.drawLine(QPointF(c, c - sinal * (c - m)), QPointF(c, c + sinal * (c - m)))
        poly((c - s * 0.17, c - sinal * (c - m) + sinal * s * 0.20),
             (c, c - sinal * (c - m)),
             (c + s * 0.17, c - sinal * (c - m) + sinal * s * 0.20))
    elif kind in ("linha_mais", "linha_menos", "coluna_mais", "coluna_menos"):
        p.drawRect(QRectF(m, m, s - 2 * m, s - 2 * m))
        if kind.startswith("linha"):
            p.drawLine(QPointF(m, c), QPointF(s - m, c))
        else:
            p.drawLine(QPointF(c, m), QPointF(c, s - m))
        cx, cy = s - m * 0.30, s - m * 0.30
        p.drawLine(QPointF(cx - s * 0.11, cy), QPointF(cx + s * 0.11, cy))
        if kind.endswith("mais"):
            p.drawLine(QPointF(cx, cy - s * 0.11), QPointF(cx, cy + s * 0.11))
    elif kind == "paragrafo":
        f = QFont("Georgia", int(s * 0.60))
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(0, 0, s, s), int(Qt.AlignmentFlag.AlignCenter),
                   "\u00b6")
    elif kind == "tabela":
        p.drawRect(QRectF(m, m, s - 2 * m, s - 2 * m))
        p.drawLine(QPointF(m, m + (s - 2 * m) / 3),
                   QPointF(s - m, m + (s - 2 * m) / 3))
        p.drawLine(QPointF(m, m + 2 * (s - 2 * m) / 3),
                   QPointF(s - m, m + 2 * (s - 2 * m) / 3))
        p.drawLine(QPointF(c, m), QPointF(c, s - m))
    elif kind == "check":
        poly((m, c), (c - s * 0.06, s - m - s * 0.04), (s - m, m + s * 0.04))
    elif kind == "tool_ips":
        # documento com uma pena
        poly((m, s - m), (m, m), (c + s * 0.08, m),
             (c + s * 0.08, m + s * 0.18), (s - m * 1.2, m + s * 0.18))
        p.drawLine(QPointF(m + s * 0.08, c - s * 0.04),
                   QPointF(c + s * 0.02, c - s * 0.04))
        p.drawLine(QPointF(m + s * 0.08, c + s * 0.14),
                   QPointF(c - s * 0.04, c + s * 0.14))
        p.drawLine(QPointF(c + s * 0.06, s - m - s * 0.02),
                   QPointF(s - m, c - s * 0.10))
    elif kind == "camera":
        # recorte de tela: cantos de enquadramento com uma objetiva
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            x = m + dx * (s - 2 * m)
            y = m + dy * (s - 2 * m)
            sx = 1 if dx == 0 else -1
            sy = 1 if dy == 0 else -1
            p.drawLine(QPointF(x, y), QPointF(x + sx * s * 0.16, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + sy * s * 0.16))
        p.drawEllipse(QPointF(c, c), s * 0.15, s * 0.15)
    elif kind == "manual":
        # livro aberto
        p.drawLine(QPointF(c, m + s * 0.10), QPointF(c, s - m))
        poly((c, m + s * 0.10), (m + s * 0.04, m + s * 0.02),
             (m, m + s * 0.06), (m, s - m + s * 0.02),
             (m + s * 0.04, s - m - s * 0.04), (c, s - m))
        poly((c, m + s * 0.10), (s - m - s * 0.04, m + s * 0.02),
             (s - m, m + s * 0.06), (s - m, s - m + s * 0.02),
             (s - m - s * 0.04, s - m - s * 0.04), (c, s - m))
    elif kind == "globe":
        p.drawEllipse(QPointF(c, c), c - m * 0.6, c - m * 0.6)
        p.drawLine(QPointF(m * 0.6, c), QPointF(s - m * 0.6, c))
        rx = (c - m * 0.6) * 0.45
        p.drawArc(QRectF(c - rx, m * 0.6, rx * 2, s - m * 1.2), 0, 360 * 16)
    elif kind == "reload":
        rect = QRectF(m, m, s - 2 * m, s - 2 * m)
        p.drawArc(rect, 60 * 16, 280 * 16)
        poly((c + s * 0.06, m - s * 0.03), (c + s * 0.26, m + s * 0.08),
             (c + s * 0.08, m + s * 0.22))
    elif kind == "compress":
        # setas convergindo para o centro
        p.drawLine(QPointF(m, m), QPointF(c - s * 0.05, c - s * 0.05))
        p.drawLine(QPointF(s - m, s - m), QPointF(c + s * 0.05, c + s * 0.05))
        poly((c - s * 0.22, c - s * 0.05), (c - s * 0.05, c - s * 0.05),
             (c - s * 0.05, c - s * 0.22))
        poly((c + s * 0.22, c + s * 0.05), (c + s * 0.05, c + s * 0.05),
             (c + s * 0.05, c + s * 0.22))
    elif kind == "scissors":
        p.drawLine(QPointF(m + s * 0.04, m), QPointF(s - m - s * 0.10, s - m - s * 0.14))
        p.drawLine(QPointF(s - m - s * 0.04, m), QPointF(m + s * 0.10, s - m - s * 0.14))
        p.drawEllipse(QPointF(m + s * 0.10, s - m - s * 0.06), s * 0.10, s * 0.10)
        p.drawEllipse(QPointF(s - m - s * 0.10, s - m - s * 0.06), s * 0.10, s * 0.10)
    elif kind == "merge":
        # dois fluxos que se juntam num só
        p.drawLine(QPointF(m, m + s * 0.04), QPointF(c, c))
        p.drawLine(QPointF(m, s - m - s * 0.04), QPointF(c, c))
        p.drawLine(QPointF(c, c), QPointF(s - m, c))
        poly((s - m - s * 0.16, c - s * 0.12), (s - m, c),
             (s - m - s * 0.16, c + s * 0.12))
    elif kind == "link":
        p.drawLine(QPointF(m + s * 0.14, s - m - s * 0.10),
                   QPointF(s - m - s * 0.14, m + s * 0.10))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(m + s * 0.10, s - m - s * 0.06), s * 0.11, s * 0.11)
        p.drawEllipse(QPointF(s - m - s * 0.10, m + s * 0.06), s * 0.11, s * 0.11)

    p.end()
    return QIcon(pm)
