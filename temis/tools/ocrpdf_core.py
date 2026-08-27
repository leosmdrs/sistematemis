"""
Reconhecimento óptico em documentos digitalizados.

Um PDF escaneado é uma pilha de fotografias de papel. Ele abre, imprime
e é juntado aos autos como qualquer outro — mas não se pode procurar
nada dentro dele, copiar um trecho para a peça, nem deixá-lo achável
pela Varredura. Para o computador não há texto ali, só pontos.

Esta ferramenta acrescenta a esse arquivo uma **camada de texto
invisível**, encaixada palavra por palavra sobre a imagem. A aparência
do documento não muda em nada: a página continua sendo exatamente a
mesma imagem, no mesmo lugar, com a mesma qualidade. O que muda é que
agora existe texto por trás dela, na posição certa — e o documento passa
a ser pesquisável, selecionável e copiável.

Duas escolhas de fundo.

**A imagem original não é tocada.** Não há rasterização nem redesenho:
abre-se o PDF recebido, escreve-se o texto por cima e salva-se. Mediu-se
o que isso significa na prática, renderizando as duas versões e
comparando: a página sai **pixel a pixel idêntica** e a imagem embutida
sai **byte a byte igual**. Os fluxos do arquivo podem ser recomprimidos
com Flate, que é sem perda — num PDF que guardava a imagem crua isso
levou 11 MB a 47 KB sem tirar um ponto sequer; num documento de escâner,
que já traz JPEG, o arquivo cresce uns 4%. Uma peça reprocessada que
ficasse visivelmente pior seria motivo para se questionar tudo o que
veio dela.

**O texto reconhecido pode estar errado.** Nenhum OCR acerta sempre —
algarismo em fonte serifada, manuscrito e carimbo são onde ele mais
falha. Por isso a camada é invisível e fica *atrás* da imagem: quem lê o
documento continua lendo o original digitalizado, e não a interpretação
da máquina. O termo diz isso expressamente.

Sobre coordenadas, que é onde este tipo de ferramenta costuma errar. O
PyMuPDF trabalha em **dois** sistemas, e confundi-los estraga o
resultado justamente nas páginas tortas, que são as mais comuns num
lote digitalizado:

* `get_pixmap` desenha a página **como ela é exibida** — com /Rotate já
  aplicado. É essa a imagem que vai ao reconhecedor, e é nela que as
  palavras vêm posicionadas;
* `insert_text` e `get_text`, ao contrário, falam o sistema da página
  **sem rotação**.

Numa página com /Rotate 90 a diferença não é sutil: o ponto calculado
sobre a imagem cai fora do papel e o texto é simplesmente cortado. A
conversão de um sistema para o outro é `page.derotation_matrix`, e a
letra precisa ser escrita com `rotate=page.rotation` para sair
horizontal aos olhos de quem lê. Em página sem rotação a matriz é a
identidade e nada disso pesa.

Não se tomou isso da documentação: gerou-se a página nas quatro
rotações, desenhou-se a palavra visível, renderizou-se a vista exibida e
mediu-se onde a tinta caiu. CropBox deslocado, esse sim, o PyMuPDF
resolve sozinho.
"""

from __future__ import annotations

import datetime
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import ocr_windows

#: Formatos aceitos na entrada.
EXT_PDF = {".pdf"}
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
EXT_ACEITAS = EXT_PDF | EXT_IMAGEM

#: Resoluções oferecidas. Abaixo de 200 dpi o motor começa a perder
#: acento; acima de 400 o ganho não paga o tempo.
RESOLUCOES = (200, 300, 400)

#: Quanto de texto uma página precisa ter para ser considerada já
#: digital. Um número de página solto no rodapé de um escaneado não pode
#: fazer a página inteira passar por documento de texto.
MINIMO_TEXTO = 24

#: Situação de cada página no resultado.
RECONHECIDA = "reconhecida"
JA_TINHA = "ja_tinha_texto"
NADA_ACHADO = "nada_achado"
FALHOU = "falhou"

ROTULO_SITUACAO = {
    RECONHECIDA: "reconhecida",
    JA_TINHA: "já possuía texto",
    NADA_ACHADO: "nenhum texto encontrado",
    FALHOU: "falha",
}


# ─────────────────────────────────────────
#  MODELO
# ─────────────────────────────────────────

#: Cargo e órgão de quem assina.
#:
#: Vinham escritos no código, como "Policial Rodoviário Federal": o
#: sistema nasceu na PRF, mas não é dela. Agora saem da Identificação
#: guardada na estação, e continuam editáveis no próprio termo — o campo
#: da tela vale mais que a configuração, sempre.
def _do_perfil(campo: str) -> str:
    from .. import perfil
    try:
        return getattr(perfil.ler(), campo, "") or ""
    except Exception:                                       # noqa: BLE001
        return ""


def cargo_padrao() -> str:
    return _do_perfil("cargo")


def orgao_padrao() -> str:
    return _do_perfil("orgao")


def _com_cargo(t) -> str:
    """"Cargo Nome", ou só o nome quando não há cargo informado.

    Sem isto, quem não preenchesse o cargo teria termos abrindo com "eu,
    ,  Fulano" — dois espaços e uma vírgula órfã numa peça que vai ao
    processo.
    """
    cargo = (getattr(t, "cargo", "") or "").strip()
    nome = (getattr(t, "nome", "") or "").strip()
    return " ".join(x for x in (cargo, nome) if x)


@dataclass
class Opcoes:
    """Ajustes do reconhecimento."""

    dpi: int = 300
    #: Só reconhece as páginas que não têm camada de texto. Desligado,
    #: reconhece todas — o que duplicaria o texto de uma página já
    #: digital, e por isso não é o padrão.
    so_sem_texto: bool = True
    idioma: str = ""
    #: Sufixo do arquivo gerado. O original nunca é sobrescrito.
    sufixo: str = "-pesquisavel"

    def resumo(self) -> list[str]:
        L = [f"Reconhecimento óptico pelo motor do Windows, idioma "
             f"{self.idioma or ocr_windows.idioma_preferido() or '—'}, "
             f"com as páginas rasterizadas a {self.dpi} pontos por polegada "
             f"apenas para leitura."]
        L.append(
            "Foram submetidas ao reconhecimento somente as páginas sem "
            "camada de texto." if self.so_sem_texto
            else "Todas as páginas foram submetidas ao reconhecimento, "
                 "inclusive as que já possuíam camada de texto.")
        L.append(
            "A imagem de cada página foi preservada sem alteração de "
            "conteúdo; o texto reconhecido foi acrescentado em camada "
            "invisível, posicionada sobre as palavras correspondentes.")
        return L


@dataclass
class Pagina:
    """O que aconteceu com uma página."""

    numero: int
    situacao: str = RECONHECIDA
    palavras: int = 0
    caracteres: int = 0
    inclinacao: float = 0.0
    erro: str = ""


@dataclass
class Documento:
    """O resultado de um arquivo."""

    entrada: str = ""
    saida: str = ""
    paginas: list[Pagina] = field(default_factory=list)
    hash_entrada: str = ""
    hash_saida: str = ""
    tamanho_entrada: int = 0
    tamanho_saida: int = 0
    segundos: float = 0.0
    erro: str = ""

    @property
    def nome(self) -> str:
        return Path(self.entrada).name

    @property
    def nome_saida(self) -> str:
        return Path(self.saida).name if self.saida else ""

    @property
    def reconhecidas(self) -> int:
        return sum(1 for p in self.paginas if p.situacao == RECONHECIDA)

    @property
    def ja_tinham(self) -> int:
        return sum(1 for p in self.paginas if p.situacao == JA_TINHA)

    @property
    def vazias(self) -> int:
        return sum(1 for p in self.paginas if p.situacao == NADA_ACHADO)

    @property
    def caracteres(self) -> int:
        return sum(p.caracteres for p in self.paginas)

    @property
    def palavras(self) -> int:
        return sum(p.palavras for p in self.paginas)

    @property
    def ok(self) -> bool:
        """Processado sem erro — ainda que nada tenha sido acrescentado."""
        return not self.erro

    @property
    def gerou(self) -> bool:
        """Produziu arquivo novo."""
        return self.ok and bool(self.saida)

    @property
    def dispensado(self) -> bool:
        """Nada a acrescentar: o documento já era pesquisável, ou não há
        texto reconhecível nele. Não se gera cópia nesse caso."""
        return self.ok and not self.saida

    @property
    def motivo_dispensa(self) -> str:
        if not self.dispensado:
            return ""
        if self.ja_tinham and not self.vazias:
            return "já possuía camada de texto"
        if self.vazias and not self.ja_tinham:
            return "nenhum texto reconhecido"
        return "nada a acrescentar"


@dataclass
class Progresso:
    """Estado corrente, para a barra de andamento."""

    arquivo: str = ""
    indice_arquivo: int = 0
    total_arquivos: int = 0
    pagina: int = 0
    total_paginas: int = 0


# ─────────────────────────────────────────
#  APOIO
# ─────────────────────────────────────────

def formatar_tamanho(n: int) -> str:
    for unidade, limite in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= limite:
            return f"{n / limite:.2f} {unidade}".replace(".", ",")
    return f"{n} bytes"


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def caminho_de_saida(entrada: Path, pasta: Path | None, sufixo: str) -> Path:
    """Nome do arquivo gerado, sem nunca colidir com o original."""
    destino = (pasta or entrada.parent) / f"{entrada.stem}{sufixo}.pdf"
    n = 2
    while destino.exists() and destino.resolve() != entrada.resolve():
        destino = (pasta or entrada.parent) / f"{entrada.stem}{sufixo}-{n}.pdf"
        n += 1
    return destino


# ─────────────────────────────────────────
#  CAMADA DE TEXTO
# ─────────────────────────────────────────

def _mediana(valores: list[float]) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    meio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[meio]
    return (ordenados[meio - 1] + ordenados[meio]) / 2


def aplicar_camada(pagina, leitura: "ocr_windows.Leitura", zoom: float) -> tuple[int, int]:
    """Escreve o texto reconhecido, invisível, sobre a página.

    Devolve (palavras escritas, caracteres escritos).

    A linha de base sai da **mediana** do pé das palavras da linha, e não
    do pé de cada uma: palavra com perna descendente — *q*, *g*, *ç* —
    desce abaixo da linha, e usar o pé de cada palavra faria o texto
    invisível subir e descer ao longo da mesma linha. A mediana é
    dominada pelas palavras sem descendente, que é onde a linha de base
    de fato está.

    O corpo da letra é calculado para que a largura do texto invisível
    coincida com a largura da palavra na imagem. É o que faz a seleção,
    no leitor de PDF, cobrir exatamente a palavra que se vê.
    """
    import fitz

    # A imagem lida foi a da página exibida; a escrita se dá no sistema
    # da página sem rotação. Em página não rotacionada isto é a
    # identidade e não custa nada.
    derodar = pagina.derotation_matrix
    giro = pagina.rotation

    escritas = caracteres = 0
    for linha in leitura.linhas:
        if not linha.palavras:
            continue
        base_px = _mediana([p.base for p in linha.palavras])
        altura_px = _mediana([p.altura for p in linha.palavras]) or 1.0
        corpo_linha = (altura_px / zoom) * 1.25

        for palavra in linha.palavras:
            texto = palavra.texto.strip()
            if not texto:
                continue
            largura = palavra.largura / zoom
            if largura <= 0:
                continue
            try:
                unidade = fitz.get_text_length(texto, fontname="helv",
                                               fontsize=1.0)
            except Exception:                               # noqa: BLE001
                unidade = 0.0
            if unidade > 0:
                corpo = largura / unidade
            else:
                corpo = corpo_linha
            # Trava contra palavra reconhecida com caixa absurda, que
            # produziria uma letra de duzentos pontos no arquivo.
            corpo = max(1.0, min(corpo, corpo_linha * 2.5, 96.0))

            ponto = fitz.Point(palavra.x / zoom, base_px / zoom) * derodar
            try:
                pagina.insert_text(
                    ponto, texto, fontsize=corpo, fontname="helv",
                    # 3 = invisível: entra no arquivo, não se vê na tela.
                    render_mode=3,
                    rotate=giro)
            except Exception:                               # noqa: BLE001
                # Caractere fora do repertório da fonte não pode
                # interromper a página inteira.
                continue
            escritas += 1
            caracteres += len(texto)
    return escritas, caracteres


# ─────────────────────────────────────────
#  CONVERSÃO
# ─────────────────────────────────────────

def _abrir_como_pdf(entrada: Path):
    """Devolve um documento do PyMuPDF, convertendo imagem em PDF."""
    import fitz

    if entrada.suffix.lower() in EXT_PDF:
        return fitz.open(entrada)

    # Imagem: vira PDF de uma página do tamanho natural dela. TIFF com
    # várias páginas é desdobrado, que é o formato em que muitos
    # escâneres de mesa entregam o lote.
    from PIL import Image, ImageSequence

    saida = fitz.open()
    with Image.open(entrada) as imagem:
        for quadro in ImageSequence.Iterator(imagem):
            quadro = quadro.convert("RGB")
            import io
            buf = io.BytesIO()
            quadro.save(buf, "PNG")
            dados = buf.getvalue()
            with fitz.open("png", dados) as folha:
                pdf = folha.convert_to_pdf()
            with fitz.open("pdf", pdf) as folha_pdf:
                saida.insert_pdf(folha_pdf)
    return saida


def converter(entrada: str | Path, saida: str | Path,
              opcoes: Opcoes | None = None, motor=None,
              progresso=None, cancelar=None) -> Documento:
    """Gera a versão pesquisável de um documento."""
    import fitz

    opcoes = opcoes or Opcoes()
    entrada, saida = Path(entrada), Path(saida)
    doc = Documento(entrada=str(entrada))
    comeco = time.time()

    try:
        doc.tamanho_entrada = entrada.stat().st_size
        doc.hash_entrada = sha256(entrada)
    except OSError as e:
        doc.erro = f"Não foi possível ler o arquivo: {e}"
        return doc

    proprio = motor is None
    if proprio:
        motor = ocr_windows.Motor(opcoes.idioma)
    if not motor.pronto:
        doc.erro = ocr_windows.diagnostico()
        return doc

    zoom = opcoes.dpi / 72.0
    try:
        pdf = _abrir_como_pdf(entrada)
    except Exception as e:                                  # noqa: BLE001
        doc.erro = f"{type(e).__name__}: {e}"
        return doc

    try:
        total = pdf.page_count
        for numero in range(total):
            if cancelar and cancelar():
                doc.erro = "Interrompido pelo usuário."
                return doc
            if progresso:
                progresso(Progresso(arquivo=entrada.name, pagina=numero + 1,
                                    total_paginas=total))
            pagina = pdf[numero]
            registro = Pagina(numero=numero + 1)
            try:
                nativo = pagina.get_text("text") or ""
                if opcoes.so_sem_texto and len(nativo.strip()) >= MINIMO_TEXTO:
                    registro.situacao = JA_TINHA
                    registro.caracteres = len(nativo.strip())
                    doc.paginas.append(registro)
                    continue

                imagem = pagina.get_pixmap(
                    matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
                leitura = motor.ler(imagem)
                registro.inclinacao = leitura.inclinacao
                if not leitura.linhas:
                    registro.situacao = NADA_ACHADO
                    doc.paginas.append(registro)
                    continue

                escritas, caracteres = aplicar_camada(pagina, leitura, zoom)
                registro.palavras = escritas
                registro.caracteres = caracteres
                registro.situacao = RECONHECIDA if escritas else NADA_ACHADO
            except Exception as e:                          # noqa: BLE001
                registro.situacao = FALHOU
                registro.erro = f"{type(e).__name__}: {e}"
            doc.paginas.append(registro)

        if not any(p.situacao == RECONHECIDA for p in doc.paginas):
            # Nenhuma página ganhou texto. Gravar um arquivo novo, com
            # resumo criptográfico novo, que não acrescenta nada, só
            # enche a pasta e atrapalha a conferência depois.
            doc.segundos = time.time() - comeco
            return doc

        saida.parent.mkdir(parents=True, exist_ok=True)
        # `garbage` limpa objetos órfãos e `deflate` comprime fluxos que
        # estejam sem compressão. Flate é sem perda: a imagem embutida
        # sai byte a byte igual e a página renderiza pixel a pixel igual
        # — conferido nas duas pontas.
        pdf.save(str(saida), garbage=3, deflate=True)
    except Exception as e:                                  # noqa: BLE001
        doc.erro = f"{type(e).__name__}: {e}"
        return doc
    finally:
        pdf.close()

    doc.saida = str(saida)
    try:
        doc.tamanho_saida = saida.stat().st_size
        doc.hash_saida = sha256(saida)
    except OSError:
        pass
    doc.segundos = time.time() - comeco
    return doc


def converter_varios(entradas, pasta_saida, opcoes: Opcoes | None = None,
                     progresso=None, cancelar=None) -> list[Documento]:
    """Processa uma fila de arquivos, um documento de saída para cada."""
    opcoes = opcoes or Opcoes()
    motor = ocr_windows.Motor(opcoes.idioma)
    saidas: list[Documento] = []
    total = len(entradas)
    for i, bruto in enumerate(entradas, 1):
        if cancelar and cancelar():
            break
        entrada = Path(bruto)

        def repassar(p: Progresso, _i=i, _n=entrada.name):
            if progresso:
                p.indice_arquivo, p.total_arquivos = _i, total
                p.arquivo = _n
                progresso(p)

        destino = caminho_de_saida(entrada, Path(pasta_saida) if pasta_saida
                                   else None, opcoes.sufixo)
        saidas.append(converter(entrada, destino, opcoes, motor,
                                repassar, cancelar))
    return saidas


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

#: Tinta do corpo do documento, repetida célula a célula porque o motor
#: de texto do Qt não propaga a cor do <body> para dentro da tabela.
INK = "#16233A"
CINZA = "#5B6B82"

ENCERRAMENTO = "Sem mais a relatar, encerro o presente termo."

#: O que o reconhecimento não garante. Vai impresso: uma peça que se cala
#: sobre os próprios limites convida a que se lhe atribua alcance que ela
#: não tem.
RESSALVAS = (
    "A imagem de cada página foi preservada exatamente como recebida, sem "
    "rasterização nem redesenho: o documento gerado renderiza conteúdo "
    "visual idêntico ao do original, e a imagem nele embutida é a mesma. "
    "A eventual diferença de tamanho entre os arquivos decorre apenas da "
    "compressão dos fluxos do PDF, que se dá sem perda.",
    "O texto acrescentado é invisível e situa-se atrás da imagem: a "
    "leitura do documento continua sendo a do original digitalizado. A "
    "camada de texto serve à pesquisa, à seleção e à cópia, e não "
    "substitui o que está escrito na imagem.",
    "O reconhecimento óptico é automático e sujeito a erro, sobretudo em "
    "manuscritos, carimbos, documentos de baixa qualidade e algarismos. "
    "Divergência entre o texto pesquisável e a imagem resolve-se sempre "
    "em favor da imagem.",
    "A ausência de resultado numa pesquisa feita sobre o documento gerado "
    "não permite concluir pela inexistência do termo procurado no "
    "original.",
)


@dataclass
class TermoOCR:
    """Dados da peça."""

    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = field(default_factory=cargo_padrao)
    orgao: str = field(default_factory=orgao_padrao)
    tipo_processo: str = "IPS"
    numero_processo: str = ""
    dia: int = 1
    mes: int = 1
    ano: int = 2026
    opcoes: Opcoes = field(default_factory=Opcoes)
    documentos: list[Documento] = field(default_factory=list)

    @property
    def convertidos(self) -> list[Documento]:
        return [d for d in self.documentos if d.gerou]

    @property
    def dispensados(self) -> list[Documento]:
        return [d for d in self.documentos if d.dispensado]

    @property
    def falhos(self) -> list[Documento]:
        return [d for d in self.documentos if d.erro]


def intro_ocr(t: TermoOCR) -> str:
    """Parágrafo de abertura, na redação já consagrada no sistema."""
    from .hash_core import ARTIGO_PROCESSO, MESES
    artigo = ARTIGO_PROCESSO.get(t.tipo_processo, "da")
    mes = MESES[t.mes - 1]
    quando = (f"Ao 1º dia do mês de {mes} de {t.ano}" if t.dia == 1
              else f"Aos {t.dia} dias do mês de {mes} de {t.ano}")
    quantos = len(t.convertidos)
    plural = "documento" if quantos == 1 else "documentos"
    return (
        f"{quando}, eu, {_com_cargo(t)}, matrícula {t.matricula}, "
        f"lotado(a) no(a) {t.lotacao}, visando instruir os autos "
        f"{artigo} {t.tipo_processo} nº {t.numero_processo}, declaro que "
        f"submeti a reconhecimento óptico de caracteres {quantos} "
        f"{plural} digitalizado(s), gerando as versões pesquisáveis "
        f"adiante identificadas, sem alteração da imagem original."
    )


def validar_termo(t: TermoOCR) -> list[str]:
    faltando = []
    for valor, rotulo in ((t.nome, "Nome completo"),
                          (t.matricula, "Matrícula"),
                          (t.lotacao, "Lotação"),
                          (t.numero_processo, "Número do processo")):
        if not str(valor).strip():
            faltando.append(rotulo)
    return faltando


def _cel(texto, alinhar: str = "left", fonte: str = "",
         tamanho: str = "") -> str:
    import html as _html
    abre = f'<font color="{INK}"'
    if fonte:
        abre += f' face="{fonte}"'
    if tamanho:
        abre += f' size="{tamanho}"'
    return (f'<td align="{alinhar}">{abre}>'
            f"{_html.escape(str(texto))}</font></td>")


def _quadro_documentos(t: TermoOCR) -> str:
    linhas = []
    for i, d in enumerate(t.convertidos, 1):
        paginas = (f"{len(d.paginas)} — {d.reconhecidas} reconhecida(s)"
                   + (f", {d.ja_tinham} já com texto" if d.ja_tinham else "")
                   + (f", {d.vazias} sem texto" if d.vazias else ""))
        linhas.append(
            "<tr>"
            + _cel(i, "center")
            + _cel(f"{d.nome}\n→ {d.nome_saida}")
            + _cel(paginas, "center")
            + _cel(f"{d.hash_entrada}\n{d.hash_saida}", "left",
                   "Courier New", "1")
            + "</tr>")
    return (
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th>'
        '<th width="34%">Arquivo original<br/>e arquivo gerado</th>'
        '<th width="20%">Páginas</th>'
        '<th width="42%">SHA-256 do original<br/>e SHA-256 do gerado</th>'
        f"</tr>{''.join(linhas)}</table>")


def build_html(t: TermoOCR) -> str:
    """Termo em HTML, para exibir e exportar."""
    from ..impressao import cabecalho_html, rodape_html
    import html as _html
    e = _html.escape

    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        cabecalho_html(),
        '<div align="center" style="margin-bottom:18px;">'
        '<b style="font-size:14pt; letter-spacing:0.5px;">'
        "Termo de Reconhecimento Óptico de Documento Digitalizado</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(intro_ocr(t))}</p>",
        '<p style="font-size:11pt;"><b>1. Documentos processados</b></p>',
        _quadro_documentos(t),
    ]

    total_paginas = sum(len(d.paginas) for d in t.convertidos)
    total_reconhecidas = sum(d.reconhecidas for d in t.convertidos)
    total_palavras = sum(d.palavras for d in t.convertidos)
    partes.append(
        f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
        f"Foram examinadas {total_paginas} página(s), das quais "
        f"{total_reconhecidas} receberam camada de texto, com "
        f"{total_palavras} palavra(s) reconhecida(s) ao todo.</p>")

    if t.dispensados:
        nomes = ", ".join(f"{d.nome} ({d.motivo_dispensa})"
                          for d in t.dispensados)
        partes.append(
            f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
            f"Dispensaram reconhecimento, não tendo sido gerado arquivo "
            f"novo: {e(nomes)}.</p>")

    if t.falhos:
        nomes = ", ".join(d.nome for d in t.falhos)
        partes.append(
            f'<p align="justify" style="font-size:10.5pt; line-height:150%;">'
            f"Não foi possível processar: {e(nomes)}.</p>")

    partes.append('<p style="font-size:11pt;"><b>2. Método</b></p>')
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>'
               for linha in t.opcoes.resumo()]
    partes.append(
        '<p align="justify" style="font-size:10.5pt; line-height:150%;">'
        "O quadro acima registra o resumo criptográfico SHA-256 do arquivo "
        "recebido e o do arquivo gerado, o que permite conferir, a qualquer "
        "tempo, a identidade de um e de outro.</p>")

    partes.append('<p style="font-size:11pt;"><b>3. Ressalvas</b></p>')
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>' for linha in RESSALVAS]

    partes.append(f'<p align="justify" style="font-size:11pt; '
                  f'margin-top:18px;">{ENCERRAMENTO}</p>')
    partes.append(
        '<br/><br/><div align="center" style="margin-top:36px;">'
        "______________________________________<br/>"
        f"<b>{e(t.nome)}</b><br/>"
        f'<span style="font-size:10pt;">{e(t.cargo)}</span>'
        "</div>" + rodape_html("pdf", "ocr") + "</body></html>")
    return "\n".join(partes)


def build_text(t: TermoOCR) -> str:
    """Termo em texto puro, para onde não se aceita formatação."""
    L = ["TERMO DE RECONHECIMENTO ÓPTICO DE DOCUMENTO DIGITALIZADO", "",
         intro_ocr(t), "", "1. DOCUMENTOS PROCESSADOS", ""]
    for i, d in enumerate(t.convertidos, 1):
        L.append(f"{i}. {d.nome}")
        L.append(f"   Arquivo gerado: {d.nome_saida}")
        L.append(f"   Páginas: {len(d.paginas)} "
                 f"({d.reconhecidas} reconhecida(s), "
                 f"{d.ja_tinham} já com texto, {d.vazias} sem texto)")
        L.append(f"   SHA-256 do original: {d.hash_entrada}")
        L.append(f"   SHA-256 do gerado:   {d.hash_saida}")
        L.append("")
    if t.dispensados:
        L.append("Dispensaram reconhecimento (sem arquivo novo): "
                 + ", ".join(f"{d.nome} ({d.motivo_dispensa})"
                             for d in t.dispensados))
        L.append("")
    if t.falhos:
        L.append("Não foi possível processar: "
                 + ", ".join(d.nome for d in t.falhos))
        L.append("")
    L += ["2. MÉTODO", ""] + [f"  - {linha}" for linha in t.opcoes.resumo()]
    L += ["", "3. RESSALVAS", ""] + [f"  - {linha}" for linha in RESSALVAS]
    L += ["", ENCERRAMENTO, "", "_" * 40, t.nome,
          t.cargo]
    return "\n".join(L)
