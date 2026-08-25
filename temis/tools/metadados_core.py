"""
Extração de metadados de arquivos.

Sem dependência de interface, para poder ser testado isolado.

O que se procura aqui não é o conteúdo do arquivo, e sim o que ele carrega
**sobre si mesmo**: quem criou, com que programa, em que data, com que
equipamento e — em fotografias e vídeos de celular — em que coordenadas.
Num procedimento correcional isso costuma valer tanto quanto o conteúdo:
uma foto anexada aos autos pode dizer o modelo do aparelho e o instante da
captura; um documento de escritório guarda o nome de quem o editou por
último, mesmo depois de o texto ser reescrito.

A leitura é sempre passiva: o arquivo é aberto somente para leitura e
nunca é reescrito.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .video_core import _SEM_JANELA, ffprobe_path


# ─────────────────────────────────────────
#  MODELO
# ─────────────────────────────────────────

#: Grupos em que os campos aparecem, na ordem de exibição.
GRUPOS = ("Arquivo", "Documento", "Origem", "Localização", "Técnico")


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


@dataclass
class Campo:
    """Um dado extraído do arquivo."""

    rotulo: str
    valor: str
    grupo: str = "Documento"
    #: Campo que costuma interessar à apuração — identifica pessoa,
    #: equipamento, data de criação ou lugar. Sai destacado no termo.
    relevante: bool = False


#: Extensões reconhecidas por tipo de leitura.
EXT_PDF = {".pdf"}
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic",
              ".bmp", ".gif"}
EXT_OFFICE = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
EXT_MIDIA = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".mp3", ".wav",
             ".m4a", ".aac", ".ogg", ".flac", ".webm"}


@dataclass
class Arquivo:
    """Resultado da leitura de um arquivo."""

    caminho: str
    campos: list[Campo] = field(default_factory=list)
    erro: str = ""
    sha256: str = ""
    tamanho: int = 0
    #: Número do documento no SEI, digitado pelo encarregado. Vai para a
    #: coluna do termo de juntada, que é o que amarra o arquivo aos autos.
    sei: str = ""
    #: Resultado do exame avançado, quando pedido. Fica separado dos
    #: campos porque é de outra natureza: aquilo são dados declarados
    #: pelo arquivo, isto são achados sobre ele.
    analise: object = None

    @property
    def nome(self) -> str:
        return Path(self.caminho).name

    @property
    def extensao(self) -> str:
        return Path(self.caminho).suffix.lower()

    @property
    def tipo(self) -> str:
        e = self.extensao
        if e in EXT_PDF:
            return "PDF"
        if e in EXT_IMAGEM:
            return "Imagem"
        if e in EXT_OFFICE:
            return "Documento de escritório"
        if e in EXT_MIDIA:
            return "Mídia"
        return "Arquivo"

    def por_grupo(self, grupo: str) -> list[Campo]:
        return [c for c in self.campos if c.grupo == grupo]

    @property
    def relevantes(self) -> list[Campo]:
        return [c for c in self.campos if c.relevante]

    def valor(self, rotulo: str) -> str:
        for c in self.campos:
            if c.rotulo == rotulo:
                return c.valor
        return ""

    @property
    def tem_localizacao(self) -> bool:
        return any(c.grupo == "Localização" for c in self.campos)


# ─────────────────────────────────────────
#  APOIO
# ─────────────────────────────────────────

def formatar_tamanho(n: int) -> str:
    for unidade, limite in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= limite:
            return f"{n / limite:.2f} {unidade}".replace(".", ",")
    return f"{n} bytes"


def _data_br(quando) -> str:
    if isinstance(quando, (int, float)):
        quando = datetime.datetime.fromtimestamp(quando)
    if isinstance(quando, datetime.datetime):
        return quando.strftime("%d/%m/%Y às %H:%M:%S")
    return str(quando)


_DATA_PDF = re.compile(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?")


def _data_pdf(texto: str) -> str:
    """Converte a data no formato do PDF (D:AAAAMMDDHHMMSS)."""
    if not texto:
        return ""
    m = _DATA_PDF.match(texto.strip())
    if not m:
        return texto
    ano, mes, dia, hora, minuto, seg = (p or "00" for p in m.groups())
    fuso = texto[m.end():].strip().replace("'", ":").rstrip(":")
    base = f"{dia}/{mes}/{ano} às {hora}:{minuto}:{seg}"
    return f"{base} (UTC{fuso})" if fuso and fuso not in ("Z", "") else base


def _data_iso(texto: str) -> str:
    """Converte datas ISO-8601 usadas em Office e contêineres de mídia."""
    if not texto:
        return ""
    limpo = texto.strip().replace("Z", "+00:00")
    try:
        return _data_br(datetime.datetime.fromisoformat(limpo))
    except ValueError:
        return texto


# ─────────────────────────────────────────
#  SISTEMA DE ARQUIVOS
# ─────────────────────────────────────────

def _do_sistema(caminho: Path) -> list[Campo]:
    st = caminho.stat()
    campos = [
        Campo("Nome do arquivo", caminho.name, "Arquivo"),
        Campo("Pasta", str(caminho.parent), "Arquivo"),
        Campo("Tamanho", formatar_tamanho(st.st_size), "Arquivo"),
        Campo("Modificado em", _data_br(st.st_mtime), "Arquivo", True),
    ]
    # No Windows, st_ctime é a criação; nos demais, a mudança de inode —
    # rotular como "criação" fora do Windows seria afirmar o que não é.
    if sys.platform == "win32":
        campos.append(Campo("Criado em", _data_br(st.st_ctime),
                            "Arquivo", True))
    return campos


# ─────────────────────────────────────────
#  PDF
# ─────────────────────────────────────────

_ROTULOS_PDF = {
    "title": ("Título", False),
    "author": ("Autor", True),
    "subject": ("Assunto", False),
    "keywords": ("Palavras-chave", False),
    "creator": ("Criado com", True),
    "producer": ("Produzido por", True),
    "creationDate": ("Data de criação", True),
    "modDate": ("Data de modificação", True),
}


def _de_pdf(caminho: Path) -> list[Campo]:
    import fitz

    campos: list[Campo] = []
    with fitz.open(caminho) as doc:
        meta = doc.metadata or {}
        for chave, (rotulo, relevante) in _ROTULOS_PDF.items():
            valor = (meta.get(chave) or "").strip()
            if not valor:
                continue
            if chave.endswith("Date"):
                valor = _data_pdf(valor)
            campos.append(Campo(rotulo, valor, "Documento", relevante))

        campos.append(Campo("Páginas", str(doc.page_count), "Técnico"))
        if meta.get("format"):
            campos.append(Campo("Versão do formato", meta["format"], "Técnico"))
        campos.append(Campo("Criptografado",
                            "Sim" if doc.is_encrypted else "Não", "Técnico"))
        if doc.is_form_pdf:
            campos.append(Campo("Formulário preenchível", "Sim", "Técnico"))
        camadas = doc.layer_ui_configs() if hasattr(doc, "layer_ui_configs") else []
        if camadas:
            ocultas = sum(1 for c in camadas if not c.get("on", True))
            campos.append(Campo(
                "Camadas (OCG)",
                f"{len(camadas)}" + (f", {ocultas} desligada(s)"
                                     if ocultas else ""),
                "Técnico", bool(ocultas)))
        if doc.xref_xml_metadata():
            campos.append(Campo("Metadados XMP", "Presentes", "Técnico"))
    return campos


# ─────────────────────────────────────────
#  IMAGEM (EXIF)
# ─────────────────────────────────────────

#: Etiquetas EXIF que interessam, com o grupo e o destaque de cada uma.
_EXIF = {
    "Make": ("Fabricante do equipamento", "Origem", True),
    "Model": ("Modelo do equipamento", "Origem", True),
    "LensModel": ("Lente", "Origem", False),
    "BodySerialNumber": ("Número de série", "Origem", True),
    "Software": ("Programa", "Origem", True),
    "Artist": ("Autor", "Origem", True),
    "Copyright": ("Direitos", "Origem", False),
    "DateTimeOriginal": ("Data da captura", "Origem", True),
    "DateTimeDigitized": ("Data da digitalização", "Origem", True),
    "DateTime": ("Data da última alteração", "Origem", True),
    "ExposureTime": ("Tempo de exposição", "Técnico", False),
    "FNumber": ("Abertura", "Técnico", False),
    "ISOSpeedRatings": ("ISO", "Técnico", False),
    "FocalLength": ("Distância focal", "Técnico", False),
    "Flash": ("Flash", "Técnico", False),
    "Orientation": ("Orientação", "Técnico", False),
}


def _graus(valor, referencia: str) -> float | None:
    """Converte coordenada EXIF (grau, minuto, segundo) para decimal."""
    try:
        g, m, s = (float(x) for x in valor)
    except (TypeError, ValueError):
        return None
    decimal = g + m / 60 + s / 3600
    if str(referencia).upper() in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def _de_imagem(caminho: Path) -> list[Campo]:
    from PIL import ExifTags, Image

    campos: list[Campo] = []
    with Image.open(caminho) as img:
        campos.append(Campo("Dimensões", f"{img.width} × {img.height} px",
                            "Técnico"))
        campos.append(Campo("Formato", img.format or "—", "Técnico"))
        if img.mode:
            campos.append(Campo("Modo de cor", img.mode, "Técnico"))

        bruto = img.getexif()
        if not bruto:
            return campos

        nomes = {v: k for k, v in ExifTags.TAGS.items()}
        legivel = {ExifTags.TAGS.get(k, k): v for k, v in bruto.items()}
        # O bloco EXIF principal fica num IFD à parte; sem ele faltariam
        # justamente a data da captura e os dados da lente.
        try:
            legivel.update({
                ExifTags.TAGS.get(k, k): v
                for k, v in bruto.get_ifd(nomes["ExifOffset"]).items()})
        except (KeyError, AttributeError):
            pass

        for etiqueta, (rotulo, grupo, relevante) in _EXIF.items():
            valor = legivel.get(etiqueta)
            if valor in (None, "", b""):
                continue
            texto = str(valor).strip().rstrip("\x00")
            if not texto:
                continue
            if etiqueta.startswith("DateTime"):
                texto = re.sub(r"^(\d{4}):(\d{2}):(\d{2})",
                               r"\3/\2/\1 às", texto)
            campos.append(Campo(rotulo, texto, grupo, relevante))

        campos += _gps(bruto, nomes)
    return campos


def _gps(bruto, nomes: dict) -> list[Campo]:
    """Coordenadas da fotografia, quando o aparelho as gravou."""
    from PIL import ExifTags

    try:
        dados = bruto.get_ifd(nomes["GPSInfo"])
    except (KeyError, AttributeError):
        return []
    if not dados:
        return []

    gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in dados.items()}
    lat = _graus(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef", "N"))
    lon = _graus(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef", "E"))
    if lat is None or lon is None:
        return []

    campos = [
        Campo("Coordenadas", f"{lat}, {lon}", "Localização", True),
        # O endereço não é consultado em serviço nenhum: o sistema não
        # envia dado de arquivo para fora da máquina. O link fica à
        # disposição de quem quiser conferir por conta própria.
        Campo("Conferir em", f"https://www.google.com/maps?q={lat},{lon}",
              "Localização", False),
    ]
    if gps.get("GPSAltitude") is not None:
        try:
            campos.append(Campo("Altitude",
                                f"{float(gps['GPSAltitude']):.1f} m",
                                "Localização", False))
        except (TypeError, ValueError):
            pass
    if gps.get("GPSDateStamp"):
        campos.append(Campo("Data GPS (UTC)",
                            str(gps["GPSDateStamp"]).replace(":", "/"),
                            "Localização", True))
    return campos


# ─────────────────────────────────────────
#  DOCUMENTOS DE ESCRITÓRIO
# ─────────────────────────────────────────

_CORE_OFFICE = {
    "title": ("Título", False),
    "subject": ("Assunto", False),
    "creator": ("Autor", True),
    "lastModifiedBy": ("Última alteração por", True),
    "revision": ("Revisão", False),
    "created": ("Data de criação", True),
    "modified": ("Data de modificação", True),
    "lastPrinted": ("Última impressão", True),
    "keywords": ("Palavras-chave", False),
    "description": ("Descrição", False),
    "category": ("Categoria", False),
}

_APP_OFFICE = {
    "Application": ("Programa", True),
    "AppVersion": ("Versão do programa", False),
    "Company": ("Empresa", True),
    "Manager": ("Responsável", True),
    "TotalTime": ("Tempo total de edição (min)", True),
    "Pages": ("Páginas", False),
    "Words": ("Palavras", False),
    "Characters": ("Caracteres", False),
}


def _texto_xml(dados: bytes) -> dict[str, str]:
    """Pares etiqueta→texto de um XML simples, sem espaço de nomes."""
    achados: dict[str, str] = {}
    for m in re.finditer(rb"<(?:[\w-]+:)?([\w-]+)[^>]*>([^<]*)</", dados):
        etiqueta = m.group(1).decode("ascii", "ignore")
        valor = m.group(2).decode("utf-8", "ignore").strip()
        if valor and etiqueta not in achados:
            achados[etiqueta] = valor
    return achados


def _de_office(caminho: Path) -> list[Campo]:
    campos: list[Campo] = []
    with zipfile.ZipFile(caminho) as z:
        nomes = set(z.namelist())

        if "docProps/core.xml" in nomes:
            dados = _texto_xml(z.read("docProps/core.xml"))
            for chave, (rotulo, relevante) in _CORE_OFFICE.items():
                valor = dados.get(chave, "")
                if not valor:
                    continue
                if chave in ("created", "modified", "lastPrinted"):
                    valor = _data_iso(valor)
                campos.append(Campo(rotulo, valor, "Documento", relevante))

        if "docProps/app.xml" in nomes:
            dados = _texto_xml(z.read("docProps/app.xml"))
            for chave, (rotulo, relevante) in _APP_OFFICE.items():
                valor = dados.get(chave, "")
                if valor:
                    grupo = "Origem" if chave in ("Application", "Company",
                                                  "Manager") else "Técnico"
                    campos.append(Campo(rotulo, valor, grupo, relevante))

        # OpenDocument guarda o mesmo tipo de dado em outro arquivo.
        if "meta.xml" in nomes:
            dados = _texto_xml(z.read("meta.xml"))
            for chave, rotulo, grupo, relevante in (
                ("creator", "Última alteração por", "Documento", True),
                ("initial-creator", "Autor", "Documento", True),
                ("creation-date", "Data de criação", "Documento", True),
                ("date", "Data de modificação", "Documento", True),
                ("generator", "Programa", "Origem", True),
                ("editing-cycles", "Revisão", "Técnico", False),
            ):
                valor = dados.get(chave, "")
                if valor:
                    if "date" in chave:
                        valor = _data_iso(valor)
                    campos.append(Campo(rotulo, valor, grupo, relevante))

        ocultos = [n for n in nomes if "vbaProject" in n]
        if ocultos:
            campos.append(Campo("Macros (VBA)", "Presentes", "Técnico", True))
    return campos


# ─────────────────────────────────────────
#  MÍDIA (ffprobe)
# ─────────────────────────────────────────

_TAGS_MIDIA = {
    "creation_time": ("Data de criação", "Origem", True),
    "com.apple.quicktime.creationdate": ("Data de criação", "Origem", True),
    "com.apple.quicktime.make": ("Fabricante do equipamento", "Origem", True),
    "com.apple.quicktime.model": ("Modelo do equipamento", "Origem", True),
    "com.apple.quicktime.software": ("Sistema do aparelho", "Origem", True),
    "com.apple.quicktime.location.ISO6709": ("Coordenadas",
                                             "Localização", True),
    "location": ("Coordenadas", "Localização", True),
    "location-eng": ("Coordenadas", "Localização", True),
    "encoder": ("Codificador", "Técnico", True),
    "handler_name": ("Manipulador", "Técnico", False),
    "artist": ("Autor", "Origem", True),
    "album": ("Álbum", "Documento", False),
    "title": ("Título", "Documento", False),
    "comment": ("Comentário", "Documento", False),
    "make": ("Fabricante do equipamento", "Origem", True),
    "model": ("Modelo do equipamento", "Origem", True),
}


def _de_midia(caminho: Path) -> list[Campo]:
    exe = ffprobe_path()
    if exe is None:
        return [Campo("Leitura de mídia",
                      "ffprobe não encontrado nesta instalação", "Técnico")]

    saida = subprocess.run(
        [str(exe), "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(caminho)],
        capture_output=True, text=True, timeout=60,
        creationflags=_SEM_JANELA).stdout
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return [Campo("Leitura de mídia", "Não foi possível sondar o arquivo",
                      "Técnico")]

    campos: list[Campo] = []
    formato = dados.get("format", {})
    if formato.get("format_long_name"):
        campos.append(Campo("Contêiner", formato["format_long_name"],
                            "Técnico"))
    if formato.get("duration"):
        try:
            seg = float(formato["duration"])
            campos.append(Campo(
                "Duração",
                f"{int(seg // 3600):02d}:{int(seg % 3600 // 60):02d}:"
                f"{int(seg % 60):02d}", "Técnico"))
        except ValueError:
            pass
    if formato.get("bit_rate"):
        try:
            campos.append(Campo("Taxa de bits",
                                f"{int(formato['bit_rate']) // 1000} kbps",
                                "Técnico"))
        except ValueError:
            pass

    vistos: set[tuple[str, str]] = set()
    for origem in [formato.get("tags", {})] + [
            f.get("tags", {}) for f in dados.get("streams", [])]:
        for chave, valor in (origem or {}).items():
            achado = _TAGS_MIDIA.get(chave.lower())
            if not achado or not str(valor).strip():
                continue
            rotulo, grupo, relevante = achado
            texto = str(valor).strip()
            if "data" in rotulo.lower():
                texto = _data_iso(texto)
            if (rotulo, texto) in vistos:
                continue
            vistos.add((rotulo, texto))
            campos.append(Campo(rotulo, texto, grupo, relevante))

    for fluxo in dados.get("streams", []):
        if fluxo.get("codec_type") == "video":
            campos.append(Campo(
                "Vídeo",
                f"{fluxo.get('codec_name', '—')} "
                f"{fluxo.get('width', 0)}×{fluxo.get('height', 0)}",
                "Técnico"))
        elif fluxo.get("codec_type") == "audio":
            campos.append(Campo(
                "Áudio",
                f"{fluxo.get('codec_name', '—')} "
                f"{fluxo.get('sample_rate', '—')} Hz", "Técnico"))
    return campos


# ─────────────────────────────────────────
#  LEITURA
# ─────────────────────────────────────────

LEITORES = [
    (EXT_PDF, _de_pdf),
    (EXT_IMAGEM, _de_imagem),
    (EXT_OFFICE, _de_office),
    (EXT_MIDIA, _de_midia),
]


def extrair(caminho: str | Path, com_hash: bool = True,
            avancado: bool = False) -> Arquivo:
    """Lê um arquivo e devolve o que ele informa sobre si mesmo."""
    caminho = Path(caminho)
    saida = Arquivo(caminho=str(caminho))
    if not caminho.is_file():
        saida.erro = "Arquivo não encontrado"
        return saida

    try:
        saida.campos.extend(_do_sistema(caminho))
    except OSError as e:
        saida.erro = f"Não foi possível ler o arquivo: {e}"
        return saida

    extensao = caminho.suffix.lower()
    for extensoes, leitor in LEITORES:
        if extensao in extensoes:
            try:
                saida.campos.extend(leitor(caminho))
            except Exception as e:                      # noqa: BLE001
                # Arquivo corrompido ou formato inesperado não pode
                # derrubar a leitura do lote inteiro.
                saida.erro = f"{type(e).__name__}: {e}"
            break

    try:
        saida.tamanho = caminho.stat().st_size
    except OSError:
        pass

    if com_hash:
        from .hash_core import sha256_file
        try:
            saida.sha256 = sha256_file(caminho)
        except OSError:
            pass

    if avancado:
        from . import metadados_avancado
        try:
            saida.analise = metadados_avancado.analisar(caminho)
        except Exception as e:                          # noqa: BLE001
            saida.erro = (saida.erro + " | " if saida.erro else "") + \
                f"análise avançada: {type(e).__name__}: {e}"
    return saida


def extrair_varios(caminhos, com_hash: bool = True,
                   progresso=None, avancado: bool = False) -> list[Arquivo]:
    total = len(caminhos)
    saida = []
    for i, caminho in enumerate(caminhos, 1):
        saida.append(extrair(caminho, com_hash, avancado))
        if progresso:
            progresso(i, total)
    return saida


# ─────────────────────────────────────────
#  TERMO DE DILIGÊNCIA
# ─────────────────────────────────────────

#: Tinta do corpo do documento. Vai explícita em cada célula porque o
#: motor de texto do Qt não propaga a cor do <body> para dentro da tabela.
INK = "#16233A"
CINZA = "#5B6B82"
DESTAQUE = "#B3261E"


#: Quanto de metadado acompanha o termo.
SO_HASH = "so_hash"          # termo de juntada puro, sem metadados
RELEVANTES = "relevantes"    # só o que interessa à apuração
COMPLETO = "completo"        # tudo o que foi lido
AVANCADO = "avancado"        # o que o arquivo esconde de si mesmo

MODOS = {
    SO_HASH: "Só hash",
    RELEVANTES: "Relevantes",
    COMPLETO: "Completo",
    AVANCADO: "Avançado",
}


@dataclass
class Declarante:
    """Quem assina o termo."""

    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = field(default_factory=cargo_padrao)
    orgao: str = field(default_factory=orgao_padrao)


@dataclass
class Juntada:
    """O vínculo do termo aos autos.

    É o que distingue esta peça de um relatório técnico: sem o número do
    procedimento e a data por extenso, o documento não se presta à
    juntada.
    """

    tipo_processo: str = "IPS"
    numero_processo: str = ""
    dia: int = 1
    mes: int = 1
    ano: int = 2026

    def intro(self, decl: Declarante) -> str:
        """Parágrafo de abertura, na redação já consagrada no sistema."""
        from .hash_core import TermoData, build_intro
        return build_intro(TermoData(
            nome=decl.nome, matricula=decl.matricula, lotacao=decl.lotacao,
            tipo_processo=self.tipo_processo,
            numero_processo=self.numero_processo,
            dia=self.dia, mes=self.mes, ano=self.ano))


def _linha(rotulo: str, valor: str, campo: "Campo | None" = None) -> str:
    """Uma linha do quadro.

    O realce é sóbrio de propósito: negrito para o que interessa à
    apuração e vermelho só para a localização geográfica. Pintar de
    vermelho todo campo relevante — data de modificação, autor — faria o
    quadro inteiro parecer alarme e nada se destacaria de fato.
    """
    import html as _html

    e = _html.escape
    localizacao = campo is not None and campo.grupo == "Localização"
    relevante = campo is not None and campo.relevante
    cor = DESTAQUE if localizacao else INK
    corpo = e(valor)
    if relevante:
        corpo = f"<b>{corpo}</b>"
    return (
        "<tr>"
        f'<td width="32%"><font color="{CINZA}">{e(rotulo)}</font></td>'
        f'<td><font color="{cor}">{corpo}</font></td>'
        "</tr>"
    )


def _bloco_arquivo(a: Arquivo, numero: int, so_relevantes: bool) -> str:
    import html as _html

    e = _html.escape
    campos = a.relevantes if so_relevantes else a.campos
    linhas = "".join(_linha(c.rotulo, c.valor, c) for c in campos)
    if not linhas:
        linhas = (f'<tr><td colspan="2"><font color="{CINZA}">'
                  "Nenhum metadado registrado no arquivo.</font></td></tr>")

    aviso = ""
    if a.erro:
        aviso = (f'<p style="font-size:9pt; margin:2px 0 6px 0;">'
                 f'<font color="{DESTAQUE}">Leitura parcial: {e(a.erro)}'
                 "</font></p>")

    return f"""
<p style="margin-top:14px; margin-bottom:2px; font-size:11pt;">
  <b><font color="{INK}">{numero}. {e(a.nome)}</font></b>
  <font color="{CINZA}" size="1"> — {e(a.tipo)}</font>
</p>
{aviso}
<table width="100%" cellspacing="0" cellpadding="4" border="1"
       style="border-collapse:collapse; font-size:9pt;">
  {linhas}
  {_linha("Resumo criptográfico (SHA-256)", a.sha256) if a.sha256 else ""}
</table>
"""


def _quadro_juntada(arquivos: list[Arquivo]) -> str:
    """A tabela do termo de juntada: o que se está juntando aos autos."""
    import html as _html

    e = _html.escape
    from .hash_core import format_size

    linhas = []
    for i, a in enumerate(arquivos, 1):
        linhas.append(
            "<tr>"
            f'<td align="center"><font color="{INK}">{i}</font></td>'
            f'<td><font color="{INK}">{e(a.nome)}</font></td>'
            f'<td align="center"><font color="{INK}">'
            f"{e(format_size(a.tamanho))}</font></td>"
            f'<td><font color="{INK}" face="Courier New" size="1">'
            f"{e(a.sha256)}</font></td>"
            f'<td><font color="{INK}">{e(a.sei)}</font></td>'
            "</tr>")

    return f"""
<table width="100%" cellspacing="0" cellpadding="5" border="1"
       style="border-collapse:collapse; font-size:9pt;">
  <tr style="background-color:#0A2442; color:#FFD633;">
    <th width="4%">Nº</th>
    <th width="30%">Nome do Arquivo</th>
    <th width="10%">Tamanho</th>
    <th width="40%">Hash SHA-256</th>
    <th width="16%">Nº SEI!</th>
  </tr>
  {''.join(linhas)}
</table>
"""


#: Cores de cada peso, no quadro de achados.
COR_RELEVANCIA = {"alerta": DESTAQUE, "atencao": "#8A6D00",
                  "informativo": CINZA}


def _bloco_achados(arquivos: list[Arquivo]) -> str:
    """Quadro dos achados do exame avançado.

    Sai separado dos metadados de propósito: aqueles são dados que o
    arquivo declara; estes são conclusões sobre ele, e misturá-los faria
    parecer que a ferramenta afirma o mesmo grau de certeza sobre as
    duas coisas.
    """
    import html as _html
    from . import metadados_avancado as av

    e = _html.escape
    blocos = []
    for i, a in enumerate(arquivos, 1):
        analise = a.analise
        if analise is None:
            continue
        blocos.append(
            f'<p style="font-size:11pt; margin-top:16px;">'
            f'<b><font color="{INK}">{i}. {e(a.nome)}</font></b></p>')
        if analise.vazio:
            blocos.append(
                f'<p style="font-size:10pt;"><font color="{CINZA}">'
                f"Nada foi encontrado além dos metadados já relacionados."
                f"</font></p>")
            continue
        linhas = []
        for ach in analise.ordenados:
            cor = COR_RELEVANCIA.get(ach.relevancia, CINZA)
            detalhe = e(ach.detalhe).replace(chr(10), "<br/>")
            linhas.append(
                f'<tr><td width="22%" valign="top">'
                f'<font color="{cor}" size="1">'
                f"{av.ROTULO_RELEVANCIA.get(ach.relevancia, '').upper()}"
                f"</font><br/>"
                f'<font color="{CINZA}" size="1">{e(ach.origem)}</font></td>'
                f'<td><font color="{INK}"><b>{e(ach.titulo)}</b></font>'
                + (f'<br/><font color="{CINZA}" size="1">{detalhe}</font>'
                   if detalhe else "")
                + "</td></tr>")
        blocos.append(
            '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
            'style="border-collapse:collapse; font-size:9.5pt;">'
            + "".join(linhas) + "</table>")
        if analise.erros:
            blocos.append(
                f'<p style="font-size:9pt;"><font color="{CINZA}">'
                f"Falhas durante o exame: {e('; '.join(analise.erros[:4]))}"
                f"</font></p>")
    return "".join(blocos)


#: O que o exame avançado alcança, e o que não alcança. Vai impresso
#: junto com os achados.
RESSALVAS_AVANCADO = (
    "O exame avançado percorre o próprio arquivo em busca do que a "
    "leitura comum de metadados não mostra: fluxos de dados alternativos "
    "do sistema de arquivos, revisões anteriores preservadas na estrutura "
    "do documento, propriedades não exibidas pelo programa que o criou e "
    "dados acrescentados após o fim do formato.",
    "A ausência de achados não significa que o arquivo não tenha sido "
    "alterado — significa apenas que não foram encontradas as marcas "
    "procuradas.",
    "Os achados são indícios e devem ser interpretados no contexto da "
    "apuração. Marca de origem, tempo de edição e contagem de revisões "
    "são registros mantidos por programas e sistemas, e como tais podem "
    "ser incorretos ou manipulados.",
    "Este exame não recupera o conteúdo das revisões anteriores nem "
    "extrai os dados ocultos encontrados; limita-se a constatar a sua "
    "existência. A extração, quando necessária, é objeto de perícia.",
)


def build_html(arquivos: list[Arquivo], quando: str,
               decl: Declarante | None = None,
               modo: str = RELEVANTES,
               juntada: "Juntada | None" = None) -> str:
    """Termo em HTML, para exibir e exportar em PDF.

    O documento é um só: abre como termo de juntada — que é o que lhe dá
    valor de peça — e, conforme o modo, traz em seguida os metadados de
    cada arquivo. Em `SO_HASH` sai o termo de juntada puro, sem os
    quadros; há juntada em que a lista de metadados só atrapalha a
    leitura.
    """
    from ..impressao import cabecalho_html
    import html as _html

    e = _html.escape
    decl = decl or Declarante()
    juntada = juntada or Juntada()
    com_metadados = modo != SO_HASH

    abertura = juntada.intro(decl) if decl.nome else (
        "Declaro que foi realizada a juntada dos arquivos abaixo.")

    corpo = [
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(abertura)}</p>",
        _quadro_juntada(arquivos),
    ]

    if com_metadados:
        com_local = [a for a in arquivos if a.tem_localizacao]
        total = sum(len(a.campos) for a in arquivos)
        frase = (
            f"Procedeu-se, ainda, à extração dos metadados dos "
            f"<b>{len(arquivos)}</b> arquivo(s) acima, dos quais foram "
            f"obtidos <b>{total}</b> registro(s), conforme os quadros a "
            "seguir."
        )
        if com_local:
            frase += (f" <b>{len(com_local)}</b> arquivo(s) contém "
                      "coordenadas geográficas registradas pelo equipamento "
                      "de origem.")
        corpo.append(
            f'<p align="justify" style="font-size:11pt; line-height:160%; '
            f'margin-top:18px;">{frase}</p>')
        corpo.append("".join(
            _bloco_arquivo(a, i, modo == RELEVANTES)
            for i, a in enumerate(arquivos, 1)))

    if modo == AVANCADO and any(a.analise is not None for a in arquivos):
        import html as _html2
        alertas = sum(a.analise.quantos("alerta")
                      for a in arquivos if a.analise is not None)
        corpo.append(
            f'<p align="justify" style="font-size:11pt; line-height:160%; '
            f'margin-top:22px;">Procedeu-se, por fim, ao exame avançado dos '
            f"arquivos, em busca do que não é exibido pela leitura comum de "
            f"metadados. "
            + (f"Foram identificados <b>{alertas}</b> achado(s) de maior "
               f"relevância, adiante relacionados."
               if alertas else
               "Os achados, quando houve, estão adiante relacionados.")
            + "</p>")
        corpo.append(_bloco_achados(arquivos))
        corpo.append(
            f'<p style="font-size:11pt; margin-top:16px;">'
            f'<b><font color="{INK}">Ressalvas quanto ao exame avançado'
            f"</font></b></p>")
        corpo += [
            f'<p align="justify" style="font-size:10pt; line-height:150%;">'
            f'<font color="{INK}">{_html2.escape(x)}</font></p>'
            for x in RESSALVAS_AVANCADO]

    blocos = "".join(corpo)

    assinatura = ""
    if decl.nome:
        vinculo = " · ".join(x for x in (
            f"matrícula {e(decl.matricula)}" if decl.matricula else "",
            e(decl.lotacao) if decl.lotacao else "",
        ) if x)
        assinatura = f"""
<div align="center" style="margin-top:40px;">
  ______________________________________<br/>
  <b><font color="{INK}">{e(decl.nome)}</font></b><br/>
  <font color="{INK}" size="2">{e(decl.cargo)}</font>
  {f'<br/><font color="{CINZA}" size="1">{vinculo}</font>' if vinculo else ''}
</div>
"""

    return f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif; color:{INK};">
{cabecalho_html()}
<div align="center" style="margin-bottom:16px;">
  <b style="font-size:14pt; letter-spacing:0.5px;">{
    "Termo de Juntada de Arquivo(s) Digital(is)" if not com_metadados
    else "Termo de Juntada e Extração de Metadados"}</b>
</div>
<hr/>
{blocos}
<p align="justify" style="font-size:10pt; line-height:150%; margin-top:16px;">
{"O resumo criptográfico SHA-256 de cada arquivo permite verificar, a "
 "qualquer tempo, que o arquivo juntado é o mesmo aqui identificado."
 if not com_metadados else
 "Os metadados acima foram lidos diretamente da estrutura interna de cada "
 "arquivo, sem qualquer alteração do original. O resumo criptográfico "
 "SHA-256 permite verificar, a qualquer tempo, que o arquivo examinado é o "
 "mesmo juntado aos autos."}
{"" if not quando else
 f'<br/>Diligência realizada em {e(quando)}, com processamento local, sem '
 "envio dos arquivos a terceiros."}
</p>
<p align="justify" style="font-size:11pt; margin-top:14px;">
Sem mais a relatar, encerro o presente termo.
</p>
{assinatura}
</body></html>
"""
