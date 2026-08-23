"""
Indexação e busca em massa de acervos digitais.

O caso que esta ferramenta atende é o do dispositivo apreendido: um
pendrive, um cartão de memória, uma pasta copiada de um computador. O
encarregado não sabe o que procura até encontrar, e abrir arquivo por
arquivo é inviável quando são milhares.

A varredura percorre tudo uma vez, calcula o resumo criptográfico de
cada arquivo, extrai o texto que houver — inclusive de páginas
digitalizadas, por OCR — e guarda o resultado num índice de busca. A
partir daí a procura é instantânea e não toca mais no dispositivo, que
pode ser devolvido ou lacrado.

Duas escolhas merecem explicação.

**A leitura é passiva.** Todo arquivo é aberto somente para leitura e
nunca reescrito. Ainda assim, montar um dispositivo no Windows não é
operação inócua: o sistema pode criar pastas próprias e a indexação do
Explorer pode escrever nele. Para material que é objeto de apuração, o
correto é usar bloqueador de escrita ou trabalhar sobre cópia — e o
termo registra em qual das duas condições se trabalhou, porque isso é o
que se discute depois.

**O índice é autossuficiente.** As miniaturas das imagens e todo o texto
extraído ficam guardados nele. Terminada a varredura, o índice continua
consultável com o dispositivo já lacrado, sem precisar acessá-lo de
novo.

O que esta ferramenta **não** faz: recuperar arquivo apagado, ler espaço
não alocado, esculpir dados de setores brutos ou abrir contêiner
cifrado. Isso é perícia e pede ferramenta de perícia — o IPED, da
Polícia Federal, faz tudo isso e é gratuito. Aqui o propósito é triagem,
e o termo gerado diz exatamente isso.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import os
import re
import sqlite3
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import ocr_windows

#: Versão do formato do índice. Índice de versão diferente é recusado em
#: vez de lido torto.
FORMATO = 1

#: Extensão dos arquivos de índice.
SUFIXO = ".tvi"


# ─────────────────────────────────────────
#  CATEGORIAS
# ─────────────────────────────────────────

#: Agrupamento por natureza do arquivo, que é como se filtra numa
#: apuração — ninguém procura "por .xlsx", procura "nas planilhas".
CATEGORIAS: dict[str, set[str]] = {
    "Documento": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md",
                  ".pages", ".wpd", ".tex"},
    "Planilha": {".xls", ".xlsx", ".ods", ".csv", ".tsv", ".numbers"},
    "Apresentação": {".ppt", ".pptx", ".odp", ".key"},
    "Imagem": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff",
               ".webp", ".heic", ".heif", ".svg", ".ico"},
    "Vídeo": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".webm",
              ".mpg", ".mpeg", ".3gp", ".flv"},
    "Áudio": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma",
              ".opus", ".amr"},
    "Mensagem": {".eml", ".msg", ".mbox", ".pst", ".ost", ".vcf"},
    "Compactado": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
                   ".iso", ".cab"},
    "Programa": {".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".sh",
                 ".vbs", ".jar", ".apk", ".scr", ".com"},
    "Banco de dados": {".db", ".sqlite", ".sqlite3", ".mdb", ".accdb",
                       ".sql", ".dbf"},
    "Página web": {".html", ".htm", ".mhtml", ".mht", ".xml", ".json"},
}

OUTROS = "Outro"

#: Índice invertido, montado uma vez.
_POR_EXTENSAO = {e: c for c, exts in CATEGORIAS.items() for e in exts}

#: Ordem de exibição das categorias.
ORDEM_CATEGORIAS = list(CATEGORIAS) + [OUTROS]


def categoria_de(caminho) -> str:
    return _POR_EXTENSAO.get(Path(caminho).suffix.lower(), OUTROS)


#: Extensões de texto puro, lidas diretamente.
EXT_TEXTO = {".txt", ".md", ".csv", ".tsv", ".log", ".json", ".xml",
             ".ini", ".cfg", ".yml", ".yaml", ".sql", ".srt", ".vtt",
             ".py", ".js", ".css", ".bat", ".cmd", ".ps1", ".sh", ".vcf"}
EXT_HTML = {".html", ".htm", ".mht", ".mhtml"}
EXT_OFFICE = {".docx", ".xlsx", ".pptx"}
EXT_ODF = {".odt", ".ods", ".odp"}
EXT_EMAIL = {".eml"}
EXT_IMAGEM = CATEGORIAS["Imagem"] - {".svg", ".ico"}

#: Como o texto do arquivo foi obtido. Vai para o termo, porque texto
#: reconhecido por OCR não tem a mesma fidelidade de texto nativo.
NATIVO = "nativo"
OCR = "ocr"
MISTO = "misto"          # PDF com páginas nativas e páginas reconhecidas
SEM_TEXTO = "sem_texto"
NAO_SUPORTADO = "nao_suportado"
FALHA = "falha"

ROTULO_ORIGEM = {
    NATIVO: "texto nativo",
    OCR: "reconhecido por OCR",
    MISTO: "nativo + OCR",
    SEM_TEXTO: "sem texto",
    NAO_SUPORTADO: "formato não lido",
    FALHA: "falha na leitura",
}


# ─────────────────────────────────────────
#  OPÇÕES DA VARREDURA
# ─────────────────────────────────────────

@dataclass
class Opcoes:
    """Ajustes da indexação."""

    #: Reconhecer texto em imagens e em páginas de PDF sem camada de texto.
    ocr: bool = True
    #: Páginas de PDF submetidas a OCR, no máximo, por arquivo. Um PDF
    #: digitalizado de 400 páginas levaria horas; 40 já cobrem o que
    #: interessa na triagem e o termo registra que houve corte.
    paginas_ocr: int = 40
    #: Arquivos acima disto não têm o texto extraído (mas continuam
    #: indexados por nome, tamanho e resumo).
    tamanho_max_texto: int = 96 << 20        # 96 MB
    #: Teto do texto guardado por arquivo, para o índice não explodir.
    texto_max: int = 4 << 20                 # 4 MB
    #: Imagens menores que isto não vão a OCR — são ícones e miniaturas.
    imagem_min_lado: int = 240
    #: Guardar miniatura das imagens, para a galeria funcionar depois de
    #: o dispositivo ser lacrado.
    miniaturas: bool = True
    miniatura_lado: int = 200
    #: Incluir arquivos e pastas ocultos.
    ocultos: bool = True
    #: A origem foi lida através de bloqueador de escrita ou é cópia?
    #: Não muda o processamento; vai para o termo.
    somente_leitura: bool = False

    def resumo(self) -> list[str]:
        """Linhas descrevendo os ajustes, para o termo."""
        L = []
        if self.ocr:
            L.append(f"Reconhecimento óptico de caracteres ativado "
                     f"({ocr_windows.idioma_preferido() or 'indisponível'}), "
                     f"limitado a {self.paginas_ocr} páginas por documento.")
        else:
            L.append("Reconhecimento óptico de caracteres desativado.")
        L.append(f"Extração de texto dispensada em arquivos maiores que "
                 f"{formatar_tamanho(self.tamanho_max_texto)}.")
        L.append("Arquivos ocultos incluídos." if self.ocultos
                 else "Arquivos ocultos ignorados.")
        return L


@dataclass
class Progresso:
    """Estado corrente da varredura, para a barra de progresso."""

    fase: str = ""
    atual: int = 0
    total: int = 0
    arquivo: str = ""


# ─────────────────────────────────────────
#  APOIO
# ─────────────────────────────────────────

def formatar_tamanho(n: int) -> str:
    for unidade, limite in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= limite:
            return f"{n / limite:.2f} {unidade}".replace(".", ",")
    return f"{n} bytes"


def data_br(quando: float | None) -> str:
    if not quando:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(quando).strftime("%d/%m/%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return "—"


def _sha256(caminho: Path, cancelar=None) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            if cancelar and cancelar():
                return ""
            h.update(bloco)
    return h.hexdigest()


def _limpar(texto: str, teto: int) -> str:
    """Normaliza o texto extraído antes de indexar."""
    if not texto:
        return ""
    texto = texto.replace("\x00", " ")
    texto = unicodedata.normalize("NFC", texto)
    texto = re.sub(r"[ \t\u00a0]+", " ", texto)
    # Extratores de planilha e de XML deixam a linha com espa\u00e7os de sobra
    # dos dois lados; sem apar\u00e1-los o trecho de contexto do resultado sai
    # cheio de buracos, que \u00e9 justamente o que o usu\u00e1rio l\u00ea na busca.
    texto = re.sub(r" *\r?\n *", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = texto.strip()
    return texto[:teto]


def _oculto(caminho: Path) -> bool:
    if caminho.name.startswith("."):
        return True
    try:
        return bool(caminho.stat().st_file_attributes & 2)   # FILE_ATTRIBUTE_HIDDEN
    except (OSError, AttributeError):
        return False


#: Pastas que o Windows mantém para si e às quais nem o administrador tem
#: acesso normal. A lixeira **não** entra aqui de propósito: o que foi
#: apagado é justamente o que costuma interessar.
IGNORAR_PASTAS = {"system volume information", "$recycle.bin.trash"}


# ─────────────────────────────────────────
#  EXTRAÇÃO DE TEXTO
# ─────────────────────────────────────────

def _ler_bytes_texto(bruto: bytes) -> str:
    """Decodifica um arquivo de texto sem saber a codificação de antemão."""
    for bom, cod in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"),
                     (b"\xfe\xff", "utf-16")):
        if bruto.startswith(bom):
            try:
                return bruto.decode(cod)
            except UnicodeDecodeError:
                break
    for cod in ("utf-8", "cp1252", "latin-1"):
        try:
            return bruto.decode(cod)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", "replace")


_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


def _de_html(bruto: bytes) -> str:
    import html as _html
    texto = _ler_bytes_texto(bruto)
    texto = _SCRIPT.sub(" ", texto)
    texto = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", texto, flags=re.I)
    return _html.unescape(_TAG.sub(" ", texto))


def _de_office(caminho: Path) -> str:
    """Texto de .docx/.xlsx/.pptx — que são pacotes ZIP de XML."""
    def interessa(n: str) -> bool:
        if not n.endswith(".xml"):
            return False
        if n.endswith("comments.xml"):      # revisão: quem anotou o quê
            return True
        return (
            n in ("word/document.xml", "word/footnotes.xml",
                  "word/endnotes.xml", "xl/sharedStrings.xml")
            or n.startswith("word/header") or n.startswith("word/footer")
            or n.startswith("ppt/slides/slide")
            or n.startswith("ppt/notesSlides/")
            or n.startswith("xl/worksheets/sheet")
        )

    partes: list[str] = []
    with zipfile.ZipFile(caminho) as z:
        for nome in sorted(n for n in z.namelist() if interessa(n)):
            try:
                bruto = z.read(nome)
            except (KeyError, zipfile.BadZipFile, OSError):
                continue
            texto = bruto.decode("utf-8", "replace")
            # Preserva a separação entre parágrafos e células.
            texto = re.sub(r"</(w:p|a:p|c|si|t)>", " \n", texto)
            partes.append(_TAG.sub(" ", texto))
    import html as _html
    return _html.unescape("\n".join(partes))


def _de_odf(caminho: Path) -> str:
    """Texto de .odt/.ods/.odp."""
    import html as _html
    with zipfile.ZipFile(caminho) as z:
        try:
            bruto = z.read("content.xml")
        except KeyError:
            return ""
    texto = bruto.decode("utf-8", "replace")
    texto = re.sub(r"</(text:p|text:h|table:table-cell)>", " \n", texto)
    return _html.unescape(_TAG.sub(" ", texto))


def _de_email(caminho: Path) -> str:
    """Cabeçalhos e corpo de uma mensagem .eml.

    Os cabeçalhos vão no texto indexado de propósito: numa apuração,
    quem enviou e para quem vale tanto quanto o que foi escrito.
    """
    import email
    from email import policy
    with open(caminho, "rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)
    L = []
    for campo in ("From", "To", "Cc", "Bcc", "Subject", "Date", "Reply-To"):
        valor = msg.get(campo)
        if valor:
            L.append(f"{campo}: {valor}")
    try:
        corpo = msg.get_body(preferencelist=("plain", "html"))
        if corpo is not None:
            conteudo = corpo.get_content()
            if corpo.get_content_subtype() == "html":
                conteudo = _de_html(conteudo.encode("utf-8", "replace"))
            L.append("")
            L.append(conteudo)
    except (KeyError, LookupError, ValueError):
        pass
    anexos = [p.get_filename() for p in msg.iter_attachments()
              if p.get_filename()]
    if anexos:
        L.append("")
        L.append("Anexos: " + ", ".join(anexos))
    return "\n".join(L)


_RTF_CONTROLE = re.compile(r"\\[a-z]+-?\d* ?|[{}]|\\\n")


def _de_rtf(caminho: Path) -> str:
    bruto = caminho.read_bytes()
    texto = _ler_bytes_texto(bruto)
    texto = re.sub(r"\\'([0-9a-fA-F]{2})",
                   lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"),
                   texto)
    return _RTF_CONTROLE.sub(" ", texto)


def _de_pdf(caminho: Path, motor, opcoes: Opcoes) -> tuple[str, str, int]:
    """Texto de um PDF. Devolve (texto, origem, páginas reconhecidas).

    Página a página: se a camada de texto tem conteúdo, usa-a; se está
    vazia — página digitalizada —, rasteriza e reconhece. É comum o
    mesmo arquivo ter as duas coisas, um ofício digitado com um anexo
    escaneado no fim.
    """
    import fitz

    partes: list[str] = []
    reconhecidas = 0
    teve_nativo = False
    with fitz.open(caminho) as doc:
        for pagina in doc:
            try:
                nativo = pagina.get_text("text") or ""
            except Exception:                               # noqa: BLE001
                nativo = ""
            if len(nativo.strip()) >= 24:
                partes.append(nativo)
                teve_nativo = True
                continue
            if not (motor and motor.pronto) or reconhecidas >= opcoes.paginas_ocr:
                if nativo.strip():
                    partes.append(nativo)
                    teve_nativo = True
                continue
            try:
                pix = pagina.get_pixmap(dpi=ocr_windows.DPI)
                lido = motor.texto(pix.tobytes("png"))
            except Exception:                               # noqa: BLE001
                lido = ""
            if lido.strip():
                partes.append(lido)
                reconhecidas += 1
            elif nativo.strip():
                partes.append(nativo)
                teve_nativo = True

    texto = "\n\n".join(partes)
    if reconhecidas and teve_nativo:
        origem = MISTO
    elif reconhecidas:
        origem = OCR
    elif texto.strip():
        origem = NATIVO
    else:
        origem = SEM_TEXTO
    return texto, origem, reconhecidas


def _miniatura(caminho: Path, lado: int) -> bytes:
    """Miniatura JPEG, para a galeria seguir funcionando sem a origem."""
    from PIL import Image
    with Image.open(caminho) as im:
        im.draft("RGB", (lado * 2, lado * 2))
        im = im.convert("RGB")
        im.thumbnail((lado, lado), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72, optimize=True)
        return buf.getvalue()


def _dimensoes(caminho: Path) -> tuple[int, int]:
    from PIL import Image
    try:
        with Image.open(caminho) as im:
            return im.size
    except Exception:                                       # noqa: BLE001
        return (0, 0)


def extrair_texto(caminho: Path, motor, opcoes: Opcoes) -> tuple[str, str, int]:
    """Texto do arquivo. Devolve (texto, origem, páginas reconhecidas)."""
    ext = caminho.suffix.lower()
    try:
        if ext == ".pdf":
            return _de_pdf(caminho, motor, opcoes)
        if ext in EXT_OFFICE:
            return _de_office(caminho), NATIVO, 0
        if ext in EXT_ODF:
            return _de_odf(caminho), NATIVO, 0
        if ext in EXT_EMAIL:
            return _de_email(caminho), NATIVO, 0
        if ext == ".rtf":
            return _de_rtf(caminho), NATIVO, 0
        if ext in EXT_HTML:
            return _de_html(caminho.read_bytes()), NATIVO, 0
        if ext in EXT_TEXTO:
            return _ler_bytes_texto(caminho.read_bytes()), NATIVO, 0
        if ext in EXT_IMAGEM:
            if not (opcoes.ocr and motor and motor.pronto):
                return "", NAO_SUPORTADO, 0
            largura, altura = _dimensoes(caminho)
            if max(largura, altura) < opcoes.imagem_min_lado:
                return "", SEM_TEXTO, 0
            lido = motor.texto(caminho.read_bytes())
            return (lido, OCR, 1) if lido.strip() else ("", SEM_TEXTO, 0)
    except Exception as e:                                  # noqa: BLE001
        raise _ErroLeitura(f"{type(e).__name__}: {e}") from e
    return "", NAO_SUPORTADO, 0


class _ErroLeitura(Exception):
    pass


#: Grupos de metadado que descrevem o arquivo em si (nome, tamanho,
#: datas). Já estão nas colunas da tabela; repeti-los só encheria o
#: quadro.
GRUPO_REDUNDANTE = "Arquivo"


def ler_metadados(caminho: Path) -> tuple[list, str]:
    """Metadados do arquivo e as coordenadas, se houver.

    Reaproveita o extrator da ferramenta de Metadados e Hash, que já sabe
    ler EXIF de fotografia, propriedades de documento de escritório e
    marcas de mídia. Aqui o resumo criptográfico é dispensado porque a
    varredura já o calculou.
    """
    from .metadados_core import extrair
    try:
        lido = extrair(caminho, com_hash=False)
    except Exception:                                       # noqa: BLE001
        return [], ""
    campos = [c for c in lido.campos if c.grupo != GRUPO_REDUNDANTE]
    gps = ""
    for c in campos:
        if c.rotulo == "Coordenadas":
            gps = c.valor
            break
    return campos, gps


# ─────────────────────────────────────────
#  ÍNDICE
# ─────────────────────────────────────────

ESQUEMA = """
CREATE TABLE IF NOT EXISTS caso (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS arquivo (
    id          INTEGER PRIMARY KEY,
    caminho     TEXT UNIQUE,      -- relativo à raiz varrida
    nome        TEXT,
    ext         TEXT,
    categoria   TEXT,
    tamanho     INTEGER,
    criado      REAL,
    modificado  REAL,
    sha256      TEXT,
    origem      TEXT,             -- como o texto foi obtido
    ocr_paginas INTEGER DEFAULT 0,
    caracteres  INTEGER DEFAULT 0,
    largura     INTEGER DEFAULT 0,
    altura      INTEGER DEFAULT 0,
    gps         TEXT DEFAULT '',   -- coordenadas, quando o arquivo as traz
    miniatura   BLOB,
    erro        TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS i_arq_cat  ON arquivo(categoria);
CREATE INDEX IF NOT EXISTS i_arq_ext  ON arquivo(ext);
CREATE INDEX IF NOT EXISTS i_arq_hash ON arquivo(sha256);
CREATE INDEX IF NOT EXISTS i_arq_mod  ON arquivo(modificado);

-- O texto vai numa tabela FTS5 comum (não "contentless") porque é dela
-- que sai o trecho de contexto do resultado: sem guardar o conteúdo,
-- snippet() não teria o que recortar.
--
-- Duas colunas porque são duas naturezas de acerto. `conteudo` é o que
-- está escrito dentro do arquivo; `contexto` é o nome, o caminho e os
-- metadados — procurar "relatorio" tem de achar `relatorio_servico.pdf`
-- mesmo que a palavra não apareça no texto, e procurar pelo nome de
-- quem editou tem de achar o documento. O ranqueamento pesa mais o
-- conteúdo, e o trecho exibido prefere-o.
CREATE VIRTUAL TABLE IF NOT EXISTS texto USING fts5(
    conteudo,
    contexto,
    tokenize = "unicode61 remove_diacritics 2"
);

CREATE TABLE IF NOT EXISTS metadado (
    arquivo   INTEGER,
    rotulo    TEXT,
    valor     TEXT,
    grupo     TEXT,
    relevante INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS i_meta_arq ON metadado(arquivo);
"""


@dataclass
class Achado:
    """Uma linha de resultado."""

    id: int
    caminho: str
    nome: str
    ext: str
    categoria: str
    tamanho: int
    modificado: float
    sha256: str
    origem: str
    trecho: str = ""
    caracteres: int = 0
    gps: str = ""
    erro: str = ""

    @property
    def pasta(self) -> str:
        return str(Path(self.caminho).parent).replace("\\", "/").lstrip(".").lstrip("/")


@dataclass
class Filtros:
    """Recorte aplicado sobre o acervo."""

    categorias: set[str] = field(default_factory=set)
    extensoes: set[str] = field(default_factory=set)
    tamanho_min: int = 0
    tamanho_max: int = 0                 # 0 = sem teto
    depois_de: float = 0.0
    antes_de: float = 0.0
    so_com_texto: bool = False
    so_ocr: bool = False
    so_com_gps: bool = False
    pasta: str = ""

    def vazio(self) -> bool:
        return not (self.categorias or self.extensoes or self.tamanho_min
                    or self.tamanho_max or self.depois_de or self.antes_de
                    or self.so_com_texto or self.so_ocr or self.so_com_gps
                    or self.pasta)

    def clausulas(self) -> tuple[list[str], list]:
        onde: list[str] = []
        args: list = []
        if self.categorias:
            onde.append("a.categoria IN (%s)"
                        % ",".join("?" * len(self.categorias)))
            args += sorted(self.categorias)
        if self.extensoes:
            onde.append("a.ext IN (%s)" % ",".join("?" * len(self.extensoes)))
            args += sorted(self.extensoes)
        if self.tamanho_min:
            onde.append("a.tamanho >= ?"); args.append(self.tamanho_min)
        if self.tamanho_max:
            onde.append("a.tamanho <= ?"); args.append(self.tamanho_max)
        if self.depois_de:
            onde.append("a.modificado >= ?"); args.append(self.depois_de)
        if self.antes_de:
            onde.append("a.modificado <= ?"); args.append(self.antes_de)
        if self.so_com_texto:
            onde.append("a.caracteres > 0")
        if self.so_ocr:
            onde.append("a.origem IN ('ocr','misto')")
        if self.so_com_gps:
            onde.append("a.gps <> ''")
        if self.pasta:
            onde.append("a.caminho LIKE ?"); args.append(self.pasta + "%")
        return onde, args


#: Operadores que o usuário pode digitar, em português e em inglês.
_OPERADORES = {
    "E": "AND", "AND": "AND",
    "OU": "OR", "OR": "OR",
    "NAO": "NOT", "NÃO": "NOT", "NOT": "NOT", "-": "NOT",
}


def preparar_consulta(texto: str) -> str:
    """Traduz o que o usuário digitou para a sintaxe do FTS5.

    Cada palavra vai entre aspas para que pontuação, hífen e acento não
    sejam lidos como operador — `BR-101` quebraria a consulta inteira se
    fosse passado cru. Aspas digitadas pelo usuário viram busca por
    expressão exata, e o asterisco final continua valendo como prefixo.
    """
    if not texto or not texto.strip():
        return ""
    pecas: list[str] = []
    for bruto in re.findall(r'"[^"]*"?|\S+', texto.strip()):
        if bruto.startswith('"'):
            frase = bruto.strip('"').replace('"', " ").strip()
            if frase:
                pecas.append(f'"{frase}"')
            continue
        chave = bruto.upper()
        if chave in _OPERADORES:
            if pecas and pecas[-1] in ("AND", "OR", "NOT"):
                pecas[-1] = _OPERADORES[chave]
            elif pecas:
                pecas.append(_OPERADORES[chave])
            continue
        prefixo = bruto.endswith("*")
        palavra = bruto.rstrip("*").replace('"', "")
        # Pontuação de borda não é token para o FTS5; tirá-la evita
        # consulta vazia em termos como "abordagem," ou "(placa)".
        palavra = palavra.strip(".,;:!?()[]{}<>«»'")
        if not palavra:
            continue
        pecas.append(f'"{palavra}"*' if prefixo else f'"{palavra}"')
    # Uma consulta não pode terminar em operador.
    while pecas and pecas[-1] in ("AND", "OR", "NOT"):
        pecas.pop()
    return " ".join(pecas)


class Indice:
    """O índice de uma varredura, gravado em arquivo."""

    def __init__(self, banco: str | Path):
        self.banco = Path(banco)
        self.con = sqlite3.connect(str(self.banco), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self.con.commit()

    # ── caso ──────────────────────────────
    def anotar(self, chave: str, valor) -> None:
        self.con.execute(
            "INSERT INTO caso(chave,valor) VALUES(?,?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, str(valor)))
        self.con.commit()

    def anotacao(self, chave: str, padrao: str = "") -> str:
        linha = self.con.execute(
            "SELECT valor FROM caso WHERE chave=?", (chave,)).fetchone()
        return linha["valor"] if linha else padrao

    @property
    def raiz(self) -> str:
        return self.anotacao("raiz")

    def fechar(self):
        try:
            self.con.close()
        except sqlite3.Error:
            pass

    # ── indexação ─────────────────────────
    def indexar(self, raiz: str | Path, opcoes: Opcoes | None = None,
                progresso=None, cancelar=None) -> dict:
        """Percorre a origem e monta o índice. Devolve o resumo."""
        opcoes = opcoes or Opcoes()
        raiz = Path(raiz)
        aviso = lambda p: progresso(p) if progresso else None    # noqa: E731
        parar = lambda: bool(cancelar and cancelar())            # noqa: E731

        self.con.execute("DELETE FROM arquivo")
        self.con.execute("DELETE FROM texto")
        self.con.execute("DELETE FROM metadado")
        self.con.commit()

        # ── 1ª passagem: quantos são ───────
        aviso(Progresso("Percorrendo a origem", 0, 0, str(raiz)))
        caminhos: list[Path] = []
        for pasta, subpastas, arquivos in os.walk(raiz, onerror=None):
            if parar():
                break
            subpastas[:] = [d for d in subpastas
                            if d.lower() not in IGNORAR_PASTAS
                            and (opcoes.ocultos or not d.startswith("."))]
            base = Path(pasta)
            for nome in arquivos:
                alvo = base / nome
                if not opcoes.ocultos and _oculto(alvo):
                    continue
                caminhos.append(alvo)
            if len(caminhos) % 500 == 0:
                aviso(Progresso("Percorrendo a origem", len(caminhos), 0, pasta))

        total = len(caminhos)
        motor = ocr_windows.Motor() if opcoes.ocr else None
        if motor is not None and not motor.pronto:
            motor = None

        resumo = {"total": total, "lidos": 0, "com_texto": 0, "ocr": 0,
                  "falhas": 0, "bytes": 0, "cancelado": False,
                  "ocr_paginas": 0, "com_gps": 0}
        manifesto: list[str] = []

        for i, alvo in enumerate(caminhos, 1):
            if parar():
                resumo["cancelado"] = True
                break
            relativo = str(alvo.relative_to(raiz)).replace("\\", "/")
            aviso(Progresso("Indexando", i, total, relativo))

            try:
                info = alvo.stat()
            except OSError as e:
                self._gravar_falha(relativo, alvo, f"{type(e).__name__}: {e}")
                resumo["falhas"] += 1
                continue

            try:
                resumo_hash = _sha256(alvo, cancelar)
            except OSError as e:
                self._gravar_falha(relativo, alvo, f"{type(e).__name__}: {e}",
                                   info.st_size)
                resumo["falhas"] += 1
                continue
            if not resumo_hash:                 # cancelado no meio do arquivo
                resumo["cancelado"] = True
                break

            texto, origem, paginas, erro = "", NAO_SUPORTADO, 0, ""
            if info.st_size <= opcoes.tamanho_max_texto:
                try:
                    texto, origem, paginas = extrair_texto(alvo, motor, opcoes)
                except _ErroLeitura as e:
                    origem, erro = FALHA, str(e)
                    resumo["falhas"] += 1
            else:
                origem = SEM_TEXTO

            texto = _limpar(texto, opcoes.texto_max)
            if texto and origem == SEM_TEXTO:
                origem = NATIVO
            if not texto and origem in (NATIVO, OCR, MISTO):
                origem = SEM_TEXTO

            try:
                campos, gps = ler_metadados(alvo)
            except Exception:                               # noqa: BLE001
                campos, gps = [], ""

            largura = altura = 0
            mini = None
            if alvo.suffix.lower() in EXT_IMAGEM:
                largura, altura = _dimensoes(alvo)
                if opcoes.miniaturas and largura:
                    try:
                        mini = _miniatura(alvo, opcoes.miniatura_lado)
                    except Exception:                       # noqa: BLE001
                        mini = None

            cur = self.con.execute(
                "INSERT INTO arquivo(caminho,nome,ext,categoria,tamanho,"
                "criado,modificado,sha256,origem,ocr_paginas,caracteres,"
                "largura,altura,gps,miniatura,erro) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (relativo, alvo.name, alvo.suffix.lower(), categoria_de(alvo),
                 info.st_size, info.st_ctime, info.st_mtime, resumo_hash,
                 origem, paginas, len(texto), largura, altura, gps, mini, erro))
            ident = cur.lastrowid

            if campos:
                self.con.executemany(
                    "INSERT INTO metadado(arquivo,rotulo,valor,grupo,relevante)"
                    " VALUES(?,?,?,?,?)",
                    [(ident, c.rotulo, c.valor, c.grupo, int(c.relevante))
                     for c in campos])

            # O caminho entra separado por barra e por sublinhado para que
            # `relatorio_servico.pdf` seja achado por "relatorio".
            contexto = "\n".join([
                relativo.replace("/", " ").replace("_", " ").replace("-", " "),
                relativo,
                "\n".join(f"{c.rotulo}: {c.valor}" for c in campos),
            ])
            self.con.execute(
                "INSERT INTO texto(rowid,conteudo,contexto) VALUES(?,?,?)",
                (ident, texto, contexto))
            if texto:
                resumo["com_texto"] += 1
            if gps:
                resumo["com_gps"] = resumo.get("com_gps", 0) + 1
            if paginas:
                resumo["ocr"] += 1
                resumo["ocr_paginas"] += paginas

            manifesto.append(f"{resumo_hash}  {relativo}")
            resumo["lidos"] += 1
            resumo["bytes"] += info.st_size
            if i % 200 == 0:
                self.con.commit()

        self.con.commit()

        # Resumo do conjunto: SHA-256 do manifesto ordenado. Reproduzível
        # — quem repetir a varredura sobre o mesmo material chega ao mesmo
        # valor, e é isso que permite afirmar que nada mudou.
        manifesto.sort()
        conjunto = hashlib.sha256(
            ("\n".join(manifesto) + "\n").encode("utf-8")).hexdigest() \
            if manifesto else ""

        self.anotar("formato", FORMATO)
        self.anotar("raiz", str(raiz))
        self.anotar("quando", datetime.datetime.now().isoformat(timespec="seconds"))
        self.anotar("hash_conjunto", conjunto)
        self.anotar("ocr_idioma", ocr_windows.idioma_preferido() if opcoes.ocr else "")
        self.anotar("somente_leitura", int(opcoes.somente_leitura))
        for chave, valor in resumo.items():
            self.anotar(f"r_{chave}", valor)
        for i, linha in enumerate(opcoes.resumo()):
            self.anotar(f"ajuste_{i}", linha)

        try:
            self.con.execute("INSERT INTO texto(texto) VALUES('optimize')")
            self.con.commit()
        except sqlite3.Error:
            pass
        resumo["hash_conjunto"] = conjunto
        return resumo

    def _gravar_falha(self, relativo: str, alvo: Path, erro: str,
                      tamanho: int = 0):
        self.con.execute(
            "INSERT OR REPLACE INTO arquivo(caminho,nome,ext,categoria,"
            "tamanho,origem,erro) VALUES(?,?,?,?,?,?,?)",
            (relativo, alvo.name, alvo.suffix.lower(), categoria_de(alvo),
             tamanho, FALHA, erro))

    # ── consulta ──────────────────────────
    COLUNAS = ("a.id,a.caminho,a.nome,a.ext,a.categoria,a.tamanho,"
               "a.modificado,a.sha256,a.origem,a.caracteres,a.gps,a.erro")

    def _achado(self, linha, trecho: str = "") -> Achado:
        return Achado(id=linha["id"], caminho=linha["caminho"],
                      nome=linha["nome"], ext=linha["ext"],
                      categoria=linha["categoria"], tamanho=linha["tamanho"],
                      modificado=linha["modificado"], sha256=linha["sha256"],
                      origem=linha["origem"], caracteres=linha["caracteres"],
                      gps=linha["gps"], erro=linha["erro"], trecho=trecho)

    def buscar(self, consulta: str, filtros: Filtros | None = None,
               limite: int = 500) -> list[Achado]:
        """Procura no texto dos arquivos.

        Consulta vazia devolve o acervo filtrado — é o modo "navegar",
        que serve para ver tudo que é imagem, ou tudo que mudou num dia.
        """
        filtros = filtros or Filtros()
        onde, args = filtros.clausulas()
        expr = preparar_consulta(consulta)

        if not expr:
            sql = (f"SELECT {self.COLUNAS} FROM arquivo a"
                   + (" WHERE " + " AND ".join(onde) if onde else "")
                   + " ORDER BY a.modificado DESC LIMIT ?")
            return [self._achado(l) for l in
                    self.con.execute(sql, (*args, limite))]

        sql = (f"SELECT {self.COLUNAS}, "
               "snippet(texto, 0, '\x02', '\x03', ' … ', 24) AS trecho, "
               "snippet(texto, 1, '\x02', '\x03', ' … ', 12) AS onde_mais "
               "FROM texto JOIN arquivo a ON a.id = texto.rowid "
               "WHERE texto MATCH ?"
               + ("".join(" AND " + c for c in onde))
               # O conteúdo pesa mais que o nome e os metadados: um
               # acerto dentro do documento vale mais do que um acerto no
               # caminho da pasta.
               + " ORDER BY bm25(texto, 1.0, 0.4) LIMIT ?")
        try:
            linhas = self.con.execute(sql, (expr, *args, limite)).fetchall()
        except sqlite3.OperationalError as e:
            raise ValueError(f"Consulta inválida: {e}") from e
        saida = []
        for l in linhas:
            # O trecho preferido é o do conteúdo; quando o acerto foi só
            # no nome ou nos metadados, mostra-se esse.
            trecho = l["trecho"] or ""
            if "\x02" not in trecho:
                trecho = l["onde_mais"] or trecho
            saida.append(self._achado(l, trecho))
        return saida

    def contar(self, consulta: str, filtros: Filtros | None = None) -> int:
        filtros = filtros or Filtros()
        onde, args = filtros.clausulas()
        expr = preparar_consulta(consulta)
        if not expr:
            sql = ("SELECT COUNT(*) FROM arquivo a"
                   + (" WHERE " + " AND ".join(onde) if onde else ""))
            return self.con.execute(sql, args).fetchone()[0]
        sql = ("SELECT COUNT(*) FROM texto JOIN arquivo a ON a.id = texto.rowid "
               "WHERE texto MATCH ?" + "".join(" AND " + c for c in onde))
        try:
            return self.con.execute(sql, (expr, *args)).fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    def texto_de(self, ident: int) -> str:
        linha = self.con.execute(
            "SELECT conteudo FROM texto WHERE rowid=?", (ident,)).fetchone()
        return linha["conteudo"] if linha else ""

    def arquivo(self, ident: int) -> Achado | None:
        linha = self.con.execute(
            f"SELECT {self.COLUNAS} FROM arquivo a WHERE a.id=?",
            (ident,)).fetchone()
        return self._achado(linha) if linha else None

    def metadados(self, ident: int) -> list[tuple[str, str, str, bool]]:
        """(rótulo, valor, grupo, relevante) de um arquivo."""
        return [(l["rotulo"], l["valor"], l["grupo"], bool(l["relevante"]))
                for l in self.con.execute(
                    "SELECT rotulo,valor,grupo,relevante FROM metadado "
                    "WHERE arquivo=?", (ident,))]

    def com_localizacao(self, limite: int = 500) -> list[Achado]:
        """Arquivos que trazem coordenadas — costuma ser o filtro mais
        revelador de um acervo de fotografias."""
        return [self._achado(l) for l in self.con.execute(
            f"SELECT {self.COLUNAS} FROM arquivo a WHERE a.gps <> '' "
            "ORDER BY a.modificado DESC LIMIT ?", (limite,))]

    def miniatura(self, ident: int) -> bytes:
        linha = self.con.execute(
            "SELECT miniatura FROM arquivo WHERE id=?", (ident,)).fetchone()
        return bytes(linha["miniatura"]) if linha and linha["miniatura"] else b""

    def imagens(self, filtros: Filtros | None = None,
                limite: int = 2000) -> list[Achado]:
        filtros = filtros or Filtros()
        onde, args = filtros.clausulas()
        onde = ["a.categoria = 'Imagem'", "a.miniatura IS NOT NULL"] + onde
        sql = (f"SELECT {self.COLUNAS} FROM arquivo a WHERE "
               + " AND ".join(onde) + " ORDER BY a.modificado DESC LIMIT ?")
        return [self._achado(l) for l in self.con.execute(sql, (*args, limite))]

    def duplicatas(self) -> list[list[Achado]]:
        """Grupos de arquivos idênticos, pelo resumo criptográfico."""
        sql = (f"SELECT {self.COLUNAS} FROM arquivo a WHERE a.sha256 <> '' "
               "AND a.sha256 IN (SELECT sha256 FROM arquivo WHERE sha256 <> '' "
               "GROUP BY sha256 HAVING COUNT(*) > 1) "
               "ORDER BY a.tamanho DESC, a.sha256, a.caminho")
        grupos: dict[str, list[Achado]] = {}
        for linha in self.con.execute(sql):
            grupos.setdefault(linha["sha256"], []).append(self._achado(linha))
        return sorted(grupos.values(),
                      key=lambda g: -(g[0].tamanho * (len(g) - 1)))

    def extensoes(self) -> list[tuple[str, int]]:
        return [(l[0] or "(sem extensão)", l[1]) for l in self.con.execute(
            "SELECT ext, COUNT(*) FROM arquivo GROUP BY ext "
            "ORDER BY COUNT(*) DESC")]

    def panorama(self) -> dict:
        """Números do acervo, para a aba de visão geral e para o termo."""
        c = self.con
        por_categoria = [(l[0], l[1], l[2] or 0) for l in c.execute(
            "SELECT categoria, COUNT(*), SUM(tamanho) FROM arquivo "
            "GROUP BY categoria")]
        ordem = {n: i for i, n in enumerate(ORDEM_CATEGORIAS)}
        por_categoria.sort(key=lambda t: ordem.get(t[0], 99))

        def um(sql, *args):
            return c.execute(sql, args).fetchone()[0] or 0

        maiores = [self._achado(l) for l in c.execute(
            f"SELECT {self.COLUNAS} FROM arquivo a ORDER BY a.tamanho DESC LIMIT 15")]
        faixa = c.execute("SELECT MIN(modificado), MAX(modificado) FROM arquivo "
                          "WHERE modificado > 0").fetchone()
        return {
            "total": um("SELECT COUNT(*) FROM arquivo"),
            "bytes": um("SELECT SUM(tamanho) FROM arquivo"),
            "com_texto": um("SELECT COUNT(*) FROM arquivo WHERE caracteres > 0"),
            "ocr": um("SELECT COUNT(*) FROM arquivo WHERE origem IN ('ocr','misto')"),
            "ocr_paginas": um("SELECT SUM(ocr_paginas) FROM arquivo"),
            "falhas": um("SELECT COUNT(*) FROM arquivo WHERE origem='falha'"),
            "com_gps": um("SELECT COUNT(*) FROM arquivo WHERE gps <> ''"),
            "duplicados": um("SELECT COUNT(*) FROM arquivo WHERE sha256 IN "
                             "(SELECT sha256 FROM arquivo WHERE sha256 <> '' "
                             "GROUP BY sha256 HAVING COUNT(*) > 1)"),
            "por_categoria": por_categoria,
            "extensoes": self.extensoes()[:20],
            "maiores": maiores,
            "primeiro": faixa[0] or 0,
            "ultimo": faixa[1] or 0,
        }


def abrir(banco: str | Path) -> Indice:
    """Abre um índice já gravado, recusando formato de outra versão."""
    ind = Indice(banco)
    marca = ind.anotacao("formato")
    if marca and int(marca) != FORMATO:
        ind.fechar()
        raise ValueError(
            f"Índice gravado no formato {marca}; este programa lê o "
            f"formato {FORMATO}. Refaça a varredura.")
    return ind


def destacar(trecho: str) -> str:
    """Converte as marcas do snippet() em HTML, com o resto escapado."""
    import html as _html
    return (_html.escape(trecho)
            .replace("\x02", '<span class="hit">')
            .replace("\x03", "</span>"))


# ─────────────────────────────────────────
#  IDENTIFICAÇÃO DO VOLUME
# ─────────────────────────────────────────

def informacao_volume(caminho: str | Path) -> dict:
    """Rótulo, número de série e sistema de arquivos da unidade.

    É o que identifica o dispositivo no termo. Dois pendrives da mesma
    marca e capacidade se distinguem pelo número de série do volume, e
    esse número acompanha a mídia — não a pasta que se escolheu varrer.
    """
    import ctypes

    vazio = {"unidade": "", "rotulo": "", "serie": "", "sistema": ""}
    try:
        raiz = Path(caminho).resolve().anchor
        if not raiz:
            return vazio
        rotulo = ctypes.create_unicode_buffer(261)
        sistema = ctypes.create_unicode_buffer(261)
        serie = ctypes.c_ulong(0)
        comp = ctypes.c_ulong(0)
        bandeiras = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(raiz), rotulo, ctypes.sizeof(rotulo),
            ctypes.byref(serie), ctypes.byref(comp), ctypes.byref(bandeiras),
            sistema, ctypes.sizeof(sistema))
        if not ok:
            return vazio
        bruto = serie.value
        return {
            "unidade": raiz.rstrip("\\"),
            "rotulo": rotulo.value,
            "serie": f"{bruto >> 16:04X}-{bruto & 0xFFFF:04X}",
            "sistema": sistema.value,
        }
    except Exception:                                       # noqa: BLE001
        return vazio


# ─────────────────────────────────────────
#  TERMO DE VARREDURA
# ─────────────────────────────────────────

#: Tinta do corpo do documento, repetida célula a célula porque o motor
#: de texto do Qt não propaga a cor do <body> para dentro da tabela.
INK = "#16233A"
CINZA = "#5B6B82"

ENCERRAMENTO = "Sem mais a relatar, encerro o presente termo."

#: O que a ferramenta não faz. Vai impresso no termo de propósito: uma
#: peça que se cala sobre os próprios limites convida a que se lhe
#: atribua alcance que ela não tem.
RESSALVAS = (
    "A varredura alcança apenas os arquivos existentes e acessíveis no "
    "sistema de arquivos da origem. Não abrange arquivos excluídos, "
    "espaço não alocado, resíduos de setores, partições ocultas nem o "
    "conteúdo de contêineres cifrados ou protegidos por senha.",
    "O conteúdo de arquivos compactados não foi examinado; cada pacote "
    "consta como um único arquivo.",
    "Trechos obtidos por reconhecimento óptico de caracteres reproduzem "
    "a leitura automática da imagem e podem divergir do original, "
    "especialmente em manuscritos, documentos de baixa qualidade e "
    "algarismos. Prevalece sempre o documento examinado.",
    "O presente exame tem natureza de triagem e não substitui perícia em "
    "mídia de armazenamento.",
)


@dataclass
class Registro:
    """Uma busca feita e o que ela devolveu.

    O termo não registra o acervo, registra a diligência: o que se
    procurou, com que recorte e o que apareceu. É isso que permite a
    quem lê refazer o caminho.
    """

    consulta: str
    recorte: str = ""
    total: int = 0
    achados: list[Achado] = field(default_factory=list)


@dataclass
class TermoVarredura:
    """Dados da peça."""

    # quem assina
    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    # a que autos
    tipo_processo: str = "IPS"
    numero_processo: str = ""
    dia: int = 1
    mes: int = 1
    ano: int = 2026
    # o que foi examinado
    origem: str = ""
    descricao_origem: str = ""
    volume: dict = field(default_factory=dict)
    somente_leitura: bool = False
    quando_varreu: str = ""
    hash_conjunto: str = ""
    ajustes: list[str] = field(default_factory=list)
    panorama: dict = field(default_factory=dict)
    # o que se procurou e o que se destacou
    registros: list[Registro] = field(default_factory=list)
    marcados: list[Achado] = field(default_factory=list)


def intro_varredura(t: TermoVarredura) -> str:
    """Parágrafo de abertura, na redação já consagrada no sistema."""
    from .hash_core import ARTIGO_PROCESSO, MESES
    artigo = ARTIGO_PROCESSO.get(t.tipo_processo, "da")
    mes = MESES[t.mes - 1]
    quando = (f"Ao 1º dia do mês de {mes} de {t.ano}" if t.dia == 1
              else f"Aos {t.dia} dias do mês de {mes} de {t.ano}")
    condicao = ("por meio de acesso somente para leitura"
                if t.somente_leitura
                else "mediante acesso direto ao dispositivo")
    return (
        f"{quando}, eu, PRF {t.nome}, matrícula {t.matricula}, "
        f"lotado(a) no(a) {t.lotacao}, visando instruir os autos "
        f"{artigo} {t.tipo_processo} nº {t.numero_processo}, declaro que "
        f"procedi à varredura e à indexação do acervo digital adiante "
        f"identificado, {condicao}, para fins de pesquisa de conteúdo."
    )


def validar_termo(t: TermoVarredura) -> list[str]:
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
            f'{_html.escape(str(texto))}</font></td>')


def _quadro_identificacao(t: TermoVarredura) -> str:
    v = t.volume or {}
    p = t.panorama or {}
    linhas = [("Origem examinada", t.origem)]
    if t.descricao_origem:
        linhas.append(("Descrição do dispositivo", t.descricao_origem))
    if v.get("unidade"):
        linhas.append(("Unidade", v["unidade"]))
    if v.get("rotulo"):
        linhas.append(("Rótulo do volume", v["rotulo"]))
    if v.get("serie"):
        linhas.append(("Número de série do volume", v["serie"]))
    if v.get("sistema"):
        linhas.append(("Sistema de arquivos", v["sistema"]))
    linhas += [
        ("Condição de acesso",
         "Somente leitura / cópia de trabalho" if t.somente_leitura
         else "Acesso direto ao dispositivo"),
        ("Data e hora da varredura", t.quando_varreu),
        ("Arquivos indexados", f"{p.get('total', 0)}"),
        ("Volume de dados", formatar_tamanho(p.get("bytes", 0) or 0)),
    ]
    corpo = "".join(f"<tr>{_cel(r)}{_cel(val)}</tr>"
                    for r, val in linhas if val)
    return (
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse; font-size:9.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="34%">Item</th><th width="66%">Conteúdo</th></tr>'
        f"{corpo}</table>")


def _quadro_panorama(t: TermoVarredura) -> str:
    p = t.panorama or {}
    if not p.get("por_categoria"):
        return ""
    linhas = "".join(
        f"<tr>{_cel(cat)}{_cel(n, 'center')}"
        f"{_cel(formatar_tamanho(b or 0), 'right')}</tr>"
        for cat, n, b in p["por_categoria"])
    return (
        '<table width="100%" cellspacing="0" cellpadding="5" border="1" '
        'style="border-collapse:collapse; font-size:9.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="50%">Natureza</th><th width="22%">Arquivos</th>'
        '<th width="28%">Volume</th></tr>'
        f"{linhas}</table>")


def _quadro_achados(achados: list[Achado], com_trecho: bool) -> str:
    import html as _html
    linhas = []
    for i, a in enumerate(achados, 1):
        trecho = ""
        if com_trecho and a.trecho:
            limpo = a.trecho.replace("\x02", "").replace("\x03", "")
            trecho = " ".join(limpo.split())
        linhas.append(
            "<tr>"
            + _cel(i, "center")
            + _cel(a.caminho)
            + _cel(formatar_tamanho(a.tamanho), "center")
            + _cel(ROTULO_ORIGEM.get(a.origem, a.origem), "center")
            + (f'<td><font color="{CINZA}" size="1">'
               f"{_html.escape(trecho)}</font></td>" if com_trecho else "")
            + "</tr>")
    cabeca = ('<th width="4%">Nº</th><th width="46%">Arquivo</th>'
              '<th width="12%">Tamanho</th><th width="16%">Texto</th>'
              + ('<th width="22%">Trecho</th>' if com_trecho else ""))
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        f'<tr style="background-color:#0a2442; color:#ffd633;">{cabeca}</tr>'
        f"{''.join(linhas)}</table>")


def _quadro_marcados(marcados: list[Achado]) -> str:
    linhas = "".join(
        "<tr>"
        + _cel(i, "center")
        + _cel(a.caminho)
        + _cel(formatar_tamanho(a.tamanho), "center")
        + _cel(a.sha256, "left", "Courier New", "1")
        + "</tr>"
        for i, a in enumerate(marcados, 1))
    return (
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:8.5pt;">'
        '<tr style="background-color:#0a2442; color:#ffd633;">'
        '<th width="4%">Nº</th><th width="40%">Arquivo</th>'
        '<th width="11%">Tamanho</th><th width="45%">Hash SHA-256</th></tr>'
        f"{linhas}</table>")


def _secoes(t: TermoVarredura) -> dict:
    """Numeração das seções, que depende do que existe na peça."""
    n = 5
    ordem = {}
    if t.registros:
        ordem["pesquisas"] = n
        n += 1
    if t.marcados:
        ordem["marcados"] = n
        n += 1
    ordem["ressalvas"] = n
    return ordem


def build_html(t: TermoVarredura) -> str:
    """Termo em HTML, para exibir e exportar."""
    import html as _html
    e = _html.escape
    p = t.panorama or {}
    sec = _secoes(t)

    partes = [
        "<html><body style=\"font-family:'Segoe UI',Arial,sans-serif; "
        'color:#16233a;">',
        '<div align="center" style="margin-bottom:18px;">'
        '<b style="font-size:14pt; letter-spacing:0.5px;">'
        "Termo de Varredura e Indexação de Acervo Digital</b></div>",
        "<hr/>",
        f'<p align="justify" style="font-size:11pt; line-height:160%;">'
        f"{e(intro_varredura(t))}</p>",
        '<p style="font-size:11pt;"><b>1. Identificação da origem</b></p>',
        _quadro_identificacao(t),
    ]

    # ── método ────────────────────────────
    metodo = [
        "A totalidade dos arquivos acessíveis na origem foi percorrida uma "
        "única vez. De cada arquivo foram registrados o caminho, o tamanho, "
        "as datas do sistema e o resumo criptográfico SHA-256; quando o "
        "formato permitia, o conteúdo textual foi extraído e indexado, "
        "assim como os metadados que o arquivo carrega sobre si mesmo.",
    ]
    metodo += list(t.ajustes)
    if p.get("ocr"):
        metodo.append(
            f"Foram submetidos a reconhecimento óptico de caracteres "
            f"{p['ocr']} arquivos, totalizando {p.get('ocr_paginas', 0)} "
            f"páginas ou imagens.")
    if p.get("falhas"):
        metodo.append(
            f"{p['falhas']} arquivo(s) não puderam ser lidos, por corrupção, "
            f"restrição de acesso ou formato inválido; permanecem no índice "
            f"com o respectivo registro de falha.")
    partes.append('<p style="font-size:11pt;"><b>2. Método</b></p>')
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>' for linha in metodo]

    # ── integridade ───────────────────────
    if t.hash_conjunto:
        partes.append(
            '<p style="font-size:11pt;"><b>3. Integridade do conjunto</b></p>')
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%;">'
            "O resumo criptográfico do conjunto é o SHA-256 calculado sobre "
            "a relação, ordenada por caminho, dos resumos individuais de "
            "todos os arquivos indexados. Repetida a varredura sobre o mesmo "
            "material, o valor abaixo há de se repetir; valor diverso indica "
            "que o conteúdo do acervo não é mais o mesmo.</p>")
        partes.append(
            f'<p align="center" style="font-size:10pt;">'
            f'<font face="Courier New" color="{INK}">'
            f"{e(t.hash_conjunto)}</font></p>")

    # ── panorama ──────────────────────────
    quadro = _quadro_panorama(t)
    if quadro:
        partes.append(
            '<p style="font-size:11pt;"><b>4. Composição do acervo</b></p>')
        partes.append(quadro)
        resumo = (f"Do total, {p.get('com_texto', 0)} arquivo(s) tiveram "
                  f"conteúdo textual indexado")
        if p.get("com_gps"):
            resumo += (f" e {p['com_gps']} trazem coordenadas geográficas "
                       f"registradas pelo equipamento de origem")
        if p.get("duplicados"):
            resumo += (f". Identificaram-se {p['duplicados']} arquivo(s) com "
                       f"conteúdo idêntico ao de outro, aferido pelo resumo "
                       f"criptográfico")
        partes.append(f'<p align="justify" style="font-size:10.5pt; '
                      f'line-height:150%;">{e(resumo)}.</p>')

    # ── pesquisas ─────────────────────────
    if t.registros:
        n = sec["pesquisas"]
        partes.append(
            f'<p style="font-size:11pt;"><b>{n}. Pesquisas realizadas</b></p>')
        for i, r in enumerate(t.registros, 1):
            cabeca = f"{n}.{i}. Expressão pesquisada: “{e(r.consulta)}”"
            if r.recorte:
                cabeca += f" — recorte: {e(r.recorte)}"
            partes.append(f'<p align="justify" style="font-size:10.5pt; '
                          f'line-height:150%; margin-top:10px;">'
                          f"<b>{cabeca}</b></p>")
            achou = (f"Retornou {r.total} arquivo(s)."
                     if r.total else "Não retornou resultado.")
            if r.achados and len(r.achados) < r.total:
                achou += (f" Relacionam-se abaixo os {len(r.achados)} "
                          f"selecionados pelo encarregado.")
            partes.append(f'<p align="justify" style="font-size:10.5pt;">'
                          f"{e(achou)}</p>")
            if r.achados:
                partes.append(_quadro_achados(r.achados, com_trecho=True))

    # ── arquivos destacados ───────────────
    if t.marcados:
        n = sec["marcados"]
        partes.append(f'<p style="font-size:11pt;"><b>{n}. Arquivos '
                      f"destacados para juntada</b></p>")
        partes.append(
            '<p align="justify" style="font-size:10.5pt; line-height:150%;">'
            "Os arquivos adiante relacionados foram selecionados no curso da "
            "pesquisa e vão acompanhados do respectivo resumo criptográfico, "
            "que permite conferir, a qualquer tempo, a identidade entre a "
            "cópia juntada aos autos e o arquivo encontrado na origem.</p>")
        partes.append(_quadro_marcados(t.marcados))

    # ── ressalvas ─────────────────────────
    n = sec["ressalvas"]
    partes.append(f'<p style="font-size:11pt;"><b>{n}. Ressalvas</b></p>')
    partes += [f'<p align="justify" style="font-size:10.5pt; '
               f'line-height:150%;">{e(linha)}</p>' for linha in RESSALVAS]

    partes.append(f'<p align="justify" style="font-size:11pt; '
                  f'margin-top:18px;">{ENCERRAMENTO}</p>')
    partes.append(
        '<br/><br/><div align="center" style="margin-top:36px;">'
        "______________________________________<br/>"
        f"<b>{e(t.nome)}</b><br/>"
        '<span style="font-size:10pt;">Policial Rodoviário Federal</span>'
        "</div></body></html>")
    return "\n".join(partes)


def build_text(t: TermoVarredura) -> str:
    """Termo em texto puro, para onde não se aceita formatação."""
    p = t.panorama or {}
    v = t.volume or {}
    sec = _secoes(t)
    L = ["TERMO DE VARREDURA E INDEXAÇÃO DE ACERVO DIGITAL", "",
         intro_varredura(t), "", "1. IDENTIFICAÇÃO DA ORIGEM", ""]
    L.append(f"Origem examinada: {t.origem}")
    if t.descricao_origem:
        L.append(f"Descrição do dispositivo: {t.descricao_origem}")
    for rotulo, chave in (("Unidade", "unidade"),
                          ("Rótulo do volume", "rotulo"),
                          ("Número de série do volume", "serie"),
                          ("Sistema de arquivos", "sistema")):
        if v.get(chave):
            L.append(f"{rotulo}: {v[chave]}")
    L.append("Condição de acesso: "
             + ("Somente leitura / cópia de trabalho" if t.somente_leitura
                else "Acesso direto ao dispositivo"))
    L.append(f"Data e hora da varredura: {t.quando_varreu}")
    L.append(f"Arquivos indexados: {p.get('total', 0)}")
    L.append(f"Volume de dados: {formatar_tamanho(p.get('bytes', 0) or 0)}")

    L += ["", "2. MÉTODO", ""] + list(t.ajustes)
    if t.hash_conjunto:
        L += ["", "3. INTEGRIDADE DO CONJUNTO", "",
              f"SHA-256 do conjunto: {t.hash_conjunto}"]
    if p.get("por_categoria"):
        L += ["", "4. COMPOSIÇÃO DO ACERVO", ""]
        for cat, n, b in p["por_categoria"]:
            L.append(f"  {cat}: {n} arquivo(s), {formatar_tamanho(b or 0)}")
    if t.registros:
        n = sec["pesquisas"]
        L += ["", f"{n}. PESQUISAS REALIZADAS", ""]
        for i, r in enumerate(t.registros, 1):
            L.append(f'{n}.{i}. "{r.consulta}"'
                     + (f" — recorte: {r.recorte}" if r.recorte else ""))
            L.append(f"     {r.total} arquivo(s) retornados.")
            for a in r.achados:
                L.append(f"       - {a.caminho}")
            L.append("")
    if t.marcados:
        n = sec["marcados"]
        L += [f"{n}. ARQUIVOS DESTACADOS PARA JUNTADA", ""]
        for i, a in enumerate(t.marcados, 1):
            L.append(f"{i}. {a.caminho}  ({formatar_tamanho(a.tamanho)})")
            L.append(f"   SHA-256: {a.sha256}")
        L.append("")
    n = sec["ressalvas"]
    L += [f"{n}. RESSALVAS", ""] + [f"  - {linha}" for linha in RESSALVAS]
    L += ["", ENCERRAMENTO, "", "_" * 40, t.nome,
          "Policial Rodoviário Federal"]
    return "\n".join(L)
