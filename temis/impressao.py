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

#: Azul-marinho da marca, para o nome do sistema e o do órgão no timbre.
#: É o mesmo da identidade visual — o cabeçalho é o único lugar do
#: documento em que a cor da instituição aparece.
MARINHO = "#0A2442"

#: Margens em milímetros (esquerda, topo, direita, base). Estreitas de
#: propósito: peças com quadros largos ficam apertadas com as margens
#: generosas que o Qt usa por padrão.
MARGENS = (15, 18, 15, 15)


# ─────────────────────────────────────────
#  CABEÇALHO DAS PEÇAS
# ─────────────────────────────────────────

#: Lado da marca do Têmis no cabeçalho, em pixels de documento.
ALTURA_CABECALHO = 58

#: Caixa em que qualquer brasão é encaixado: largura e altura máximas.
#:
#: Existe porque brasão não tem formato: o da PRF é um círculo, o de uma
#: procuradoria costuma ser uma faixa larga e baixa, e o de um tribunal
#: um escudo alto. Fixando só a altura, como se fazia aqui, o redondo
#: saía miúdo ao lado do nome do órgão. Encaixando na caixa e preservando
#: a proporção, qualquer um dos três chega ao documento no mesmo peso
#: visual — que é o que se quer de um timbre.
CAIXA_BRASAO = (150, 72)


def _medida_do_brasao() -> tuple[int, int]:
    """Quanto o brasão vai medir no documento, encaixado na caixa.

    Devolve (0, 0) quando não há brasão ou quando o arquivo não informa
    as próprias dimensões — e aí ele sai sem medida declarada, no
    tamanho natural, que é melhor do que sair esticado.
    """
    from . import perfil

    largura, altura = perfil.dimensoes_brasao()
    if largura <= 0 or altura <= 0:
        return (0, 0)
    caixa_l, caixa_a = CAIXA_BRASAO
    escala = min(caixa_l / largura, caixa_a / altura)
    return (max(1, round(largura * escala)), max(1, round(altura * escala)))


def _marca_em_dados(altura: int = ALTURA_CABECALHO) -> str:
    """A balança do Têmis como URI de dados.

    Desenhada na hora e embutida no documento. Se o desenho falhar — sem
    ambiente gráfico, por exemplo —, devolve vazio e o cabeçalho sai só
    com o nome: peça sem marca é peça feia, peça que não abre é peça
    perdida.
    """
    try:
        import base64

        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice

        from .icons import temis_pixmap

        pixmap = temis_pixmap(altura * 2)
        # O QByteArray precisa sobreviver ao QBuffer: um temporário aqui
        # deixa o buffer com um ponteiro solto, e o processo morre na
        # gravação. Já custou uma vez, no Quadro de Evidências.
        bytes_ = QByteArray()
        buffer = QBuffer(bytes_)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        return ("data:image/png;base64,"
                + base64.b64encode(bytes(bytes_.data())).decode("ascii"))
    except Exception:                                       # noqa: BLE001
        return ""


def cabecalho_html() -> str:
    """O timbre que abre toda peça do sistema.

    Três colunas: à esquerda o sistema, que assina sempre — foi ele quem
    produziu a peça, e isso não depende de configuração; ao centro o
    órgão; à direita o brasão dele. Órgão e brasão só aparecem se tiverem
    sido informados em Identificação, e a ausência de um não desarruma o
    outro: sem brasão, o nome do órgão fica centrado no espaço que sobra;
    sem nenhum dos dois, resta o bloco do sistema, à esquerda, como
    sempre foi.

    Vai em tabela, e não em `flex`: o destino destas peças é o editor do
    SEI e o QTextDocument do Qt, e nenhum dos dois entende folha de
    estilo moderna. Tabela de três células os dois entendem desde
    sempre.
    """
    from . import perfil

    p = perfil.ler()
    orgao = p.orgao.strip()
    brasao = perfil.brasao_em_dados()
    marca = _marca_em_dados()

    # O nome fica ao lado da balança, em duas linhas, e não embaixo:
    # embaixo ele alargava a coluna da esquerda e empurrava o nome do
    # órgão para fora do centro da folha.
    nome_sistema = (
        f'<span style="font-size:13pt; font-weight:bold; color:{MARINHO}; '
        f'line-height:110%;">Sistema<br/>Têmis</span>')
    esquerda = (
        '<table cellspacing="0" cellpadding="0"><tr>'
        + (f'<td valign="middle"><img src="{marca}" '
           f'width="{ALTURA_CABECALHO}" height="{ALTURA_CABECALHO}"/></td>'
           f'<td width="8"></td>' if marca else "")
        + f'<td valign="middle">{nome_sistema}</td>'
        "</tr></table>")

    if not orgao and not brasao:
        return (f'<table width="100%" cellspacing="0" cellpadding="0">'
                f'<tr><td align="left" valign="middle">{esquerda}</td>'
                f"</tr></table><hr/>")

    centro = (f'<span style="font-size:15pt; font-weight:bold; '
              f'color:{MARINHO};">{_html.escape(orgao)}</span>'
              if orgao else "")
    largura_brasao, altura_brasao = _medida_do_brasao()
    if brasao and largura_brasao:
        direita = (f'<img src="{brasao}" width="{largura_brasao}" '
                   f'height="{altura_brasao}"/>')
    elif brasao:
        direita = f'<img src="{brasao}"/>'
    else:
        direita = ""

    return (
        '<table width="100%" cellspacing="0" cellpadding="0">'
        '<tr>'
        f'<td width="27%" align="left" valign="middle">{esquerda}</td>'
        f'<td width="46%" align="center" valign="middle">{centro}</td>'
        f'<td width="27%" align="right" valign="middle">{direita}</td>'
        "</tr></table><hr/>"
    )


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
