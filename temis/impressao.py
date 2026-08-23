"""
Impressão de documentos em PDF.

Existe porque `QTextDocument.print` não serve para o que o sistema
precisa. Medindo os PDFs que ele gerava, constatou-se que:

* com o tamanho de página definido antes, o Qt trata o documento como já
  paginado e pula o ajuste de resolução — um texto diagramado a 96 dpi
  ia para uma página de 300 dpi e saía com cerca de um terço do tamanho,
  a ponto de ser preciso ampliar muito para ler;
* sem definir o tamanho, a letra sai certa, mas a mancha de texto fica
  aquém das margens dos dois lados, desperdiçando a folha.

Aqui a largura da página do documento é imposta em unidades dele próprio
— a área útil convertida pela resolução que o Qt usa para diagramar — e o
pincel é escalado dessa resolução para a da impressão. Assim 12 pt no
documento saem 12 pt no papel e a linha termina na margem.
"""

from __future__ import annotations

import html as _html
import re

from PyQt6.QtCore import QMarginsF, QRectF, QSizeF
from PyQt6.QtGui import (
    QAbstractTextDocumentLayout, QColor, QGuiApplication, QPageLayout,
    QPageSize, QPainter, QPalette, QPdfWriter, QTextDocument,
)

#: Cor da letra no papel. O tema da tela é escuro; o documento, não.
TINTA = "#16233A"

#: Margens em milímetros (esquerda, topo, direita, base). Estreitas de
#: propósito: peças com quadros largos ficam apertadas com as margens
#: generosas que o Qt usa por padrão.
MARGENS = (15, 18, 15, 15)


def preparar_escritor(caminho: str, titulo: str = "",
                      resolucao: int = 300) -> QPdfWriter:
    """QPdfWriter em A4 com as margens do sistema."""
    escritor = QPdfWriter(caminho)
    escritor.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    escritor.setPageMargins(QMarginsF(*MARGENS), QPageLayout.Unit.Millimeter)
    escritor.setResolution(resolucao)
    if titulo:
        escritor.setTitle(titulo)
    return escritor


def imprimir_documento(doc: QTextDocument, escritor: QPdfWriter,
                       tinta: str = TINTA):
    """Desenha o documento na folha, ocupando toda a área útil."""
    dpi_doc = QGuiApplication.primaryScreen().logicalDotsPerInch() or 96.0
    area = escritor.pageLayout().paintRect(QPageLayout.Unit.Point)
    largura = area.width() * dpi_doc / 72.0
    altura = area.height() * dpi_doc / 72.0
    doc.setPageSize(QSizeF(largura, altura))

    # A cor do texto vem de uma paleta explícita: sem isso o desenho usa a
    # paleta da aplicação, que é clara por ser um tema escuro, e o PDF sai
    # com a letra branca sobre o papel branco.
    paleta = QPalette()
    paleta.setColor(QPalette.ColorRole.Text, QColor(tinta))
    contexto = QAbstractTextDocumentLayout.PaintContext()
    contexto.palette = paleta

    pintor = QPainter(escritor)
    try:
        escala = escritor.resolution() / dpi_doc
        pintor.scale(escala, escala)
        for i in range(max(1, doc.pageCount())):
            if i:
                escritor.newPage()
            pintor.save()
            pintor.translate(0, -i * altura)
            contexto.clip = QRectF(0, i * altura, largura, altura)
            doc.documentLayout().draw(pintor, contexto)
            pintor.restore()
    finally:
        pintor.end()


# ─────────────────────────────────────────
#  EXPORTAÇÃO EM HTML
# ─────────────────────────────────────────

def limpar_para_sei(fragmento: str) -> str:
    """Remove do HTML o que o importador do SEI descarta ou estraga.

    O Qt exporta o texto com um cabeçalho completo, folha de estilo e
    atributos próprios. Levar isso para o SEI produz um documento com
    formatação imprevisível — o importador ignora a folha e mantém
    resíduos no corpo.
    """
    if not fragmento:
        return ""

    # Fica só o conteúdo do <body>, sem <head>, <style> ou <meta>.
    corpo = re.search(r"<body[^>]*>(.*)</body>", fragmento, re.S | re.I)
    texto = corpo.group(1) if corpo else fragmento

    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", texto,
                   flags=re.S | re.I)
    # Atributos que só fazem sentido dentro do Qt.
    texto = re.sub(r"\s+(class|id)=\"[^\"]*\"", "", texto, flags=re.I)
    texto = re.sub(r"-qt-[a-z-]+\s*:\s*[^;\"]*;?", "", texto, flags=re.I)
    texto = re.sub(r'\s+style="\s*"', "", texto)
    return texto.strip()


#: Estilo mínimo do arquivo exportado. O SEI descarta a folha na
#: importação; ela serve para quem abrir o arquivo no navegador.
_ESTILO_HTML = ("font-family:'Segoe UI',Arial,sans-serif; color:#16233A; "
                "max-width:820px; margin:32px auto; padding:0 16px;")


def documento_html(corpo: str, titulo: str = "") -> str:
    """Envolve o corpo já limpo num arquivo HTML completo."""
    return (
        '<!DOCTYPE html>\n<html lang="pt-br"><head><meta charset="utf-8">'
        f"<title>{_html.escape(titulo)}</title></head>\n"
        f'<body style="{_ESTILO_HTML}">\n{corpo}\n</body></html>\n'
    )
