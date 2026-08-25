"""
Análise avançada: o que o arquivo esconde de si mesmo.

A leitura comum de metadados responde *quem fez, quando e com quê*. Este
módulo vai atrás do que não aparece nem no programa que criou o arquivo:
fluxos de dados alternativos do NTFS, revisões anteriores guardadas
dentro do próprio PDF, propriedades de escritório que o Word não mostra,
miniatura desatualizada que denuncia edição, e bytes anexados depois do
fim do formato.

O que se procura aqui costuma valer mais que o conteúdo. Um documento
com duas revisões internas guarda a versão anterior à correção. Um
arquivo com `Zone.Identifier` guarda o endereço de onde foi baixado. Uma
fotografia cuja miniatura embutida não corresponde à imagem visível foi
editada depois de fotografada.

Sobre os fluxos alternativos
----------------------------

O NTFS permite prender a um arquivo outros fluxos de dados, invisíveis
ao Explorador e ao Prompt: `documento.pdf:oculto` ocupa espaço em disco,
não aparece na listagem e não entra no tamanho do arquivo. Medido: um
arquivo de 26 bytes carregando 640 bytes escondidos continua sendo
exibido como de 26 bytes.

O fluxo mais útil à apuração é o `Zone.Identifier`, que o Windows grava
ao receber um arquivo da internet — e nas versões recentes ele guarda o
**endereço de origem** e a página que levou até ele.

Nada aqui altera o arquivo: todos os fluxos são abertos somente para
leitura.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

#: Quanto o achado pesa na leitura da peça.
INFORMATIVO = "informativo"
ATENCAO = "atencao"
ALERTA = "alerta"

ORDEM_RELEVANCIA = {ALERTA: 0, ATENCAO: 1, INFORMATIVO: 2}

ROTULO_RELEVANCIA = {
    INFORMATIVO: "informação",
    ATENCAO: "merece atenção",
    ALERTA: "achado relevante",
}


@dataclass
class Achado:
    """Algo encontrado no arquivo que a leitura comum não mostra."""

    titulo: str
    detalhe: str = ""
    relevancia: str = INFORMATIVO
    #: Origem da análise, para o termo dizer de onde veio cada achado.
    origem: str = ""


@dataclass
class Analise:
    """O resultado do exame avançado de um arquivo."""

    caminho: str = ""
    achados: list[Achado] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    def anotar(self, titulo: str, detalhe: str = "",
               relevancia: str = INFORMATIVO, origem: str = ""):
        self.achados.append(Achado(titulo, detalhe, relevancia, origem))

    @property
    def ordenados(self) -> list[Achado]:
        return sorted(self.achados,
                      key=lambda a: ORDEM_RELEVANCIA.get(a.relevancia, 9))

    def quantos(self, relevancia: str) -> int:
        return sum(1 for a in self.achados if a.relevancia == relevancia)

    @property
    def vazio(self) -> bool:
        return not self.achados


# ─────────────────────────────────────────
#  FLUXOS ALTERNATIVOS (NTFS)
# ─────────────────────────────────────────

class _DADOS_DE_FLUXO(ctypes.Structure):
    _fields_ = [("StreamSize", ctypes.c_longlong),
                ("cStreamName", ctypes.c_wchar * 296)]


_MANIPULADOR_INVALIDO = wintypes.HANDLE(-1).value

#: O fluxo principal do arquivo — o conteúdo que todo mundo vê.
FLUXO_PRINCIPAL = "::$DATA"

#: Fluxos que o próprio Windows cria, e que não são achado por si sós.
FLUXOS_CONHECIDOS = {
    "Zone.Identifier": "marca de origem gravada pelo Windows",
    "SmartScreen": "avaliação do filtro do Windows",
    "Afp_AfpInfo": "resíduo de compartilhamento com macOS",
    "com.dropbox.attrs": "atributo do Dropbox",
    "com.apple.quarantine": "marca de quarentena do macOS",
}


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.FindFirstStreamW.restype = wintypes.HANDLE
    k.FindFirstStreamW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                   ctypes.c_void_p, wintypes.DWORD]
    k.FindNextStreamW.restype = wintypes.BOOL
    k.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    k.FindClose.argtypes = [wintypes.HANDLE]
    return k


def listar_fluxos(caminho: str | Path) -> list[tuple[str, int]]:
    """Fluxos de dados presos ao arquivo, além do principal.

    Devolve pares (nome, tamanho). O fluxo principal fica de fora — ele
    é o conteúdo comum do arquivo.
    """
    achados: list[tuple[str, int]] = []
    try:
        k = _kernel32()
        dados = _DADOS_DE_FLUXO()
        h = k.FindFirstStreamW(str(caminho), 0, ctypes.byref(dados), 0)
        if h == _MANIPULADOR_INVALIDO:
            return []
        try:
            while True:
                bruto = dados.cStreamName or ""
                if bruto != FLUXO_PRINCIPAL:
                    # vem como ":nome:$DATA"
                    nome = bruto.strip(":")
                    if nome.endswith(":$DATA"):
                        nome = nome[:-6]
                    achados.append((nome, int(dados.StreamSize)))
                if not k.FindNextStreamW(h, ctypes.byref(dados)):
                    break
        finally:
            k.FindClose(wintypes.HANDLE(h))
    except Exception:                                    # noqa: BLE001
        return []
    return achados


def ler_fluxo(caminho: str | Path, nome: str, limite: int = 8192) -> bytes:
    """Lê um fluxo alternativo, somente para leitura."""
    try:
        with open(f"{caminho}:{nome}", "rb") as f:
            return f.read(limite)
    except OSError:
        return b""


def _origem_do_download(bruto: bytes) -> dict:
    """Interpreta o `Zone.Identifier`.

    É onde o Windows guarda de onde o arquivo veio. `ZoneId=3` significa
    internet; `HostUrl` é o endereço do próprio arquivo e `ReferrerUrl`,
    a página que levou até ele.
    """
    texto = bruto.decode("utf-8", "replace")
    campos = {}
    for linha in texto.splitlines():
        if "=" in linha:
            chave, _, valor = linha.partition("=")
            campos[chave.strip()] = valor.strip()
    return campos


ZONAS = {
    "0": "computador local",
    "1": "rede local (intranet)",
    "2": "sítio confiável",
    "3": "internet",
    "4": "sítio restrito",
}


def analisar_fluxos(caminho: Path, a: Analise):
    for nome, tamanho in listar_fluxos(caminho):
        if nome == "Zone.Identifier":
            campos = _origem_do_download(ler_fluxo(caminho, nome))
            zona = ZONAS.get(campos.get("ZoneId", ""), campos.get("ZoneId", "—"))
            partes = [f"Zona de origem: {zona}"]
            if campos.get("HostUrl"):
                partes.append(f"Endereço do arquivo: {campos['HostUrl']}")
            if campos.get("ReferrerUrl"):
                partes.append(f"Página de origem: {campos['ReferrerUrl']}")
            if campos.get("LastWriterPackageFamilyName"):
                partes.append(f"Aplicativo que gravou: "
                              f"{campos['LastWriterPackageFamilyName']}")
            a.anotar(
                "Marca de origem: o arquivo foi recebido de fora da máquina",
                "\n".join(partes),
                ALERTA if campos.get("HostUrl") else ATENCAO,
                "fluxo alternativo Zone.Identifier")
            continue

        conhecido = FLUXOS_CONHECIDOS.get(nome)
        if conhecido:
            a.anotar(f"Fluxo alternativo “{nome}”",
                     f"{conhecido}. Ocupa {tamanho} bytes.",
                     INFORMATIVO, "fluxo alternativo")
            continue

        # Fluxo que não é do Windows: conteúdo preso ao arquivo, que não
        # aparece na listagem nem entra no tamanho exibido.
        amostra = ler_fluxo(caminho, nome, 64)
        a.anotar(
            f"Fluxo alternativo não identificado: “{nome}”",
            f"Contém {tamanho} bytes de dados que não aparecem na "
            f"listagem do Windows nem no tamanho exibido do arquivo."
            + (f"\nPrimeiros bytes: {amostra[:40]!r}" if amostra else ""),
            ALERTA, "fluxo alternativo")


# ─────────────────────────────────────────
#  PDF
# ─────────────────────────────────────────

def analisar_pdf(caminho: Path, a: Analise):
    import fitz

    #: PDF acima disto não é lido por inteiro para a contagem de
    #: revisões — a memória não compensa, e documento assim é raríssimo.
    TETO = 256 << 20
    try:
        if caminho.stat().st_size > TETO:
            a.erros.append(
                "arquivo grande demais para a contagem de revisões")
            bruto = b""
        else:
            bruto = caminho.read_bytes()
    except OSError as e:
        a.erros.append(f"leitura: {e}")
        return

    # Cada gravação incremental deixa o seu próprio fim de arquivo. Mais
    # de um significa que o documento foi alterado depois de criado — e
    # que a versão anterior continua ali dentro.
    fins = bruto.count(b"%%EOF")
    if fins > 1:
        a.anotar(
            f"O documento foi salvo {fins} vezes, de forma incremental",
            f"Cada gravação incremental preserva a versão anterior dentro "
            f"do próprio arquivo. Há {fins - 1} revisão(ões) anterior(es) "
            f"recuperável(is), com o conteúdo como estava antes das "
            f"alterações.",
            ALERTA, "estrutura do PDF")

    try:
        with fitz.open(caminho) as doc:
            xmp = doc.xref_xml_metadata() or ""
            if xmp.strip():
                a.anotar(
                    "Metadados XMP presentes",
                    f"{len(xmp)} caracteres de metadados em formato XMP, "
                    f"que costumam guardar histórico de edição e "
                    f"identificação de ferramentas."
                    + _resumo_xmp(xmp),
                    ATENCAO, "metadados XMP")

            if doc.embfile_count():
                nomes = []
                for i in range(doc.embfile_count()):
                    try:
                        info = doc.embfile_info(i)
                        nomes.append(f"{info.get('filename', '?')} "
                                     f"({info.get('size', 0)} bytes)")
                    except Exception:                    # noqa: BLE001
                        pass
                a.anotar(
                    f"{doc.embfile_count()} arquivo(s) embutido(s) no PDF",
                    "Arquivos anexados dentro do documento, que não "
                    "aparecem ao lê-lo:\n" + "\n".join(nomes),
                    ALERTA, "anexos do PDF")

            if doc.is_encrypted or doc.metadata.get("encryption"):
                a.anotar("Documento cifrado",
                         f"Método: {doc.metadata.get('encryption') or '—'}",
                         INFORMATIVO, "estrutura do PDF")

            if doc.has_annots():
                a.anotar("O documento tem anotações",
                         "Comentários, marcações ou carimbos acrescentados "
                         "após a criação.", ATENCAO, "estrutura do PDF")
            if doc.is_form_pdf:
                a.anotar("O documento é um formulário",
                         "Campos preenchíveis podem guardar valores que não "
                         "aparecem impressos.", ATENCAO, "estrutura do PDF")
    except Exception as e:                               # noqa: BLE001
        a.erros.append(f"PDF: {type(e).__name__}: {e}")

    # JavaScript embutido: legítimo em formulário, suspeito no resto.
    if re.search(rb"/JavaScript|/JS\b", bruto):
        a.anotar(
            "O documento contém JavaScript",
            "Código que roda ao abrir o documento. É comum em formulários; "
            "em documento comum, merece exame.",
            ALERTA, "estrutura do PDF")

    if re.search(rb"/Launch|/EmbeddedFile\b", bruto):
        a.anotar(
            "O documento tem ação de abrir programa ou arquivo externo",
            "Presença de /Launch ou /EmbeddedFile na estrutura.",
            ALERTA, "estrutura do PDF")


_XMP_ALVOS = (
    (rb"<xmp:CreatorTool>(.*?)</xmp:CreatorTool>", "Ferramenta de criação"),
    (rb"<xmp:CreateDate>(.*?)</xmp:CreateDate>", "Criado em"),
    (rb"<xmp:ModifyDate>(.*?)</xmp:ModifyDate>", "Alterado em"),
    (rb"<xmp:MetadataDate>(.*?)</xmp:MetadataDate>", "Metadado alterado em"),
    (rb"<xmpMM:DocumentID>(.*?)</xmpMM:DocumentID>", "Identificador do documento"),
    (rb"<xmpMM:InstanceID>(.*?)</xmpMM:InstanceID>", "Identificador da versão"),
)


def _resumo_xmp(xmp: str) -> str:
    bruto = xmp.encode("utf-8", "replace")
    linhas = []
    for padrao, rotulo in _XMP_ALVOS:
        m = re.search(padrao, bruto, re.S)
        if m:
            linhas.append(f"{rotulo}: "
                          f"{m.group(1).decode('utf-8', 'replace').strip()}")
    # O histórico do XMP guarda cada salvamento, com programa e data.
    historico = len(re.findall(rb"<stEvt:action>", bruto))
    if historico:
        linhas.append(f"Histórico de edição: {historico} evento(s) "
                      f"registrado(s) no próprio documento")
    return ("\n" + "\n".join(linhas)) if linhas else ""


# ─────────────────────────────────────────
#  DOCUMENTOS DE ESCRITÓRIO
# ─────────────────────────────────────────

_APP_XML = (
    ("Company", "Empresa ou órgão", ATENCAO),
    ("Manager", "Gerente", INFORMATIVO),
    ("Template", "Modelo utilizado", INFORMATIVO),
    ("Application", "Programa", INFORMATIVO),
    ("AppVersion", "Versão do programa", INFORMATIVO),
)


def analisar_office(caminho: Path, a: Analise):
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()

            if "docProps/app.xml" in nomes:
                app = z.read("docProps/app.xml").decode("utf-8", "replace")
                for campo, rotulo, peso in _APP_XML:
                    m = re.search(rf"<{campo}>(.*?)</{campo}>", app, re.S)
                    if m and m.group(1).strip():
                        a.anotar(f"{rotulo}: {m.group(1).strip()}", "",
                                 peso, "propriedades do documento")
                m = re.search(r"<TotalTime>(\d+)</TotalTime>", app)
                if m and int(m.group(1)) > 0:
                    minutos = int(m.group(1))
                    horas, resto = divmod(minutos, 60)
                    a.anotar(
                        f"Tempo total de edição: {horas}h{resto:02d}min",
                        "Somatório do tempo em que o documento esteve "
                        "aberto para edição, contado pelo próprio programa.",
                        ATENCAO, "propriedades do documento")

            if "docProps/core.xml" in nomes:
                core = z.read("docProps/core.xml").decode("utf-8", "replace")
                m = re.search(r"<cp:revision>(\d+)</cp:revision>", core)
                if m and int(m.group(1)) > 1:
                    a.anotar(
                        f"O documento passou por {m.group(1)} revisões",
                        "Contador de gravações mantido pelo próprio "
                        "programa de edição.",
                        ATENCAO, "propriedades do documento")

            comentarios = [n for n in nomes if n.endswith("comments.xml")]
            if comentarios:
                autores = set()
                for n in comentarios:
                    texto = z.read(n).decode("utf-8", "replace")
                    # XML admite aspas simples e duplas; arquivo de
                    # Office usa duplas, mas exigi-las deixava passar
                    # pacote gerado por outra ferramenta.
                    autores.update(re.findall(
                        r"""w:author=["']([^"']+)["']""", texto))
                a.anotar(
                    "O documento tem comentários de revisão",
                    ("Autores: " + ", ".join(sorted(autores))) if autores
                    else "Comentários presentes no pacote.",
                    ALERTA, "revisão do documento")

            # Marcas de alteração: o texto original permanece no arquivo.
            corpo = ""
            for n in ("word/document.xml", "ppt/presentation.xml"):
                if n in nomes:
                    corpo = z.read(n).decode("utf-8", "replace")
                    break
            if corpo and ("<w:del " in corpo or "<w:ins " in corpo):
                excluidos = corpo.count("<w:del ")
                inseridos = corpo.count("<w:ins ")
                a.anotar(
                    "O documento tem alterações controladas não aceitas",
                    f"{excluidos} exclusão(ões) e {inseridos} inserção(ões) "
                    f"registradas. O texto excluído continua no arquivo e "
                    f"pode ser recuperado.",
                    ALERTA, "revisão do documento")

            ocultas = [n for n in nomes
                       if n.startswith(("word/embeddings/", "xl/embeddings/",
                                        "ppt/embeddings/"))]
            if ocultas:
                a.anotar(
                    f"{len(ocultas)} objeto(s) embutido(s) no documento",
                    "\n".join(Path(n).name for n in ocultas[:8]),
                    ATENCAO, "estrutura do pacote")

            macros = [n for n in nomes if n.endswith(("vbaProject.bin",))]
            if macros:
                a.anotar("O documento contém macros",
                         "Código que pode ser executado ao abrir.",
                         ALERTA, "estrutura do pacote")
    except (zipfile.BadZipFile, OSError) as e:
        a.erros.append(f"pacote: {e}")


# ─────────────────────────────────────────
#  IMAGENS
# ─────────────────────────────────────────

def miniatura_embutida(bruto: bytes) -> bytes:
    """A miniatura que a câmera gravou dentro do EXIF.

    Ela é um JPEG completo dentro do segmento APP1. Procurá-la assim, em
    vez de percorrer a estrutura EXIF, resiste a arquivo com metadados
    malformados — que é justamente o caso interessante.
    """
    inicio = bruto.find(b"\xff\xe1")
    if inicio < 0 or inicio > 65536:
        return b""
    tamanho = int.from_bytes(bruto[inicio + 2:inicio + 4], "big")
    app1 = bruto[inicio + 4:inicio + 2 + tamanho]
    soi = app1.find(b"\xff\xd8\xff")
    if soi < 0:
        return b""
    eoi = app1.find(b"\xff\xd9", soi)
    return app1[soi:eoi + 2] if eoi > soi else b""


def analisar_imagem(caminho: Path, a: Analise):
    # Basta o começo: EXIF, XMP e miniatura ficam no cabeçalho.
    try:
        with open(caminho, "rb") as f:
            bruto = f.read(2 << 20)
    except OSError as e:
        a.erros.append(f"leitura: {e}")
        return

    mini = miniatura_embutida(bruto)
    if mini:
        try:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(mini)) as m, Image.open(caminho) as g:
                proporcao_mini = m.width / max(m.height, 1)
                proporcao_grande = g.width / max(g.height, 1)
                detalhe = (f"Miniatura de {m.width}×{m.height} guardada "
                           f"dentro do arquivo, ao lado da imagem de "
                           f"{g.width}×{g.height}.")
                # Proporção diferente indica recorte posterior: a
                # miniatura é a da foto como saiu da câmera.
                divergente = abs(proporcao_mini - proporcao_grande) > 0.06
                if divergente:
                    detalhe += (
                        "\nAs proporções não coincidem, o que ocorre quando "
                        "a imagem é recortada e a miniatura original não é "
                        "regravada. A miniatura pode mostrar a cena antes "
                        "do recorte.")
                a.anotar("Miniatura embutida na imagem", detalhe,
                         ALERTA if divergente else INFORMATIVO,
                         "EXIF — miniatura")
        except Exception:                                # noqa: BLE001
            a.anotar("Miniatura embutida na imagem",
                     f"{len(mini)} bytes de imagem guardados no EXIF.",
                     INFORMATIVO, "EXIF — miniatura")

    if b"http://ns.adobe.com/xap/1.0/" in bruto[:200_000]:
        a.anotar(
            "Metadados XMP presentes na imagem",
            "Costumam guardar histórico de edição e identificação do "
            "programa que tratou a imagem.",
            ATENCAO, "metadados XMP")

    if re.search(rb"Photoshop 3\.0|8BIM", bruto[:200_000]):
        a.anotar(
            "Marcas de edição por programa de imagem",
            "O arquivo traz blocos gravados por editor de imagem, o que "
            "indica que ele não saiu diretamente da câmera.",
            ALERTA, "resíduo de edição")

    # Nota do fabricante: guarda número de série da câmera, contagem de
    # disparos e ajustes que não aparecem no EXIF comum.
    if b"MakerNote" in bruto[:200_000] or b"Nikon" in bruto[:8000] \
            or b"Canon" in bruto[:8000]:
        a.anotar(
            "Nota do fabricante presente no EXIF",
            "Bloco proprietário que costuma guardar número de série do "
            "equipamento e contagem de disparos.",
            ATENCAO, "EXIF — nota do fabricante")


# ─────────────────────────────────────────
#  DADOS APÓS O FIM DO FORMATO
# ─────────────────────────────────────────

#: Marca que encerra cada formato, e a partir da qual tudo é sobra.
FIM_DO_FORMATO = {
    ".jpg": b"\xff\xd9", ".jpeg": b"\xff\xd9",
    ".png": b"IEND\xaeB`\x82",
    ".gif": b"\x00;",
    ".pdf": b"%%EOF",
}

#: Assinaturas reconhecíveis no começo da sobra.
ASSINATURAS = (
    (b"PK\x03\x04", "arquivo compactado (ZIP, DOCX, XLSX ou semelhante)"),
    (b"Rar!\x1a\x07", "arquivo RAR"),
    (b"7z\xbc\xaf\x27\x1c", "arquivo 7-Zip"),
    (b"MZ", "programa executável do Windows"),
    (b"\x1f\x8b", "arquivo comprimido com gzip"),
    (b"%PDF", "documento PDF"),
    (b"\xff\xd8\xff", "imagem JPEG"),
)


def analisar_cauda(caminho: Path, a: Analise):
    """Bytes depois do fim lógico do formato.

    É onde se esconde arquivo dentro de arquivo: a imagem abre
    normalmente, e o que vem depois passa despercebido.
    """
    marca = FIM_DO_FORMATO.get(caminho.suffix.lower())
    if marca is None:
        return
    # Lê só o fim do arquivo. Ler tudo custaria a memória inteira num
    # vídeo de dois gigabytes, para procurar uma marca que está nos
    # últimos bytes — e sobra anexada é sempre pequena perto do todo.
    JANELA = 4 << 20
    try:
        total = caminho.stat().st_size
        with open(caminho, "rb") as f:
            deslocamento = max(0, total - JANELA)
            f.seek(deslocamento)
            bruto = f.read()
    except OSError:
        return
    fim = bruto.rfind(marca)
    if fim < 0:
        a.anotar(
            "O arquivo não termina como o formato exige",
            "A marca de fim do formato não foi encontrada. O arquivo pode "
            "estar truncado ou ter sido alterado.",
            ATENCAO, "estrutura do arquivo")
        return
    sobra = len(bruto) - (fim + len(marca))
    if sobra <= 2:
        return
    amostra = bruto[fim + len(marca):fim + len(marca) + 16]
    reconhecida = next(
        (nome for assinatura, nome in ASSINATURAS
         if amostra.startswith(assinatura)), "")
    detalhe = (f"Há {sobra} bytes depois do fim do formato. O arquivo abre "
               f"normalmente e essa parte não é exibida.")
    if reconhecida:
        detalhe += f"\nO início desses dados corresponde a {reconhecida}."
    detalhe += f"\nPrimeiros bytes: {amostra!r}"
    a.anotar("Dados anexados após o fim do arquivo", detalhe,
             ALERTA if reconhecida else ATENCAO, "estrutura do arquivo")


# ─────────────────────────────────────────
#  ENTRADA
# ─────────────────────────────────────────

EXT_PDF = {".pdf"}
EXT_OFFICE = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm",
              ".odt", ".ods", ".odp"}
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic",
              ".gif", ".bmp"}


def analisar(caminho: str | Path) -> Analise:
    """Examina o arquivo em todas as frentes que se aplicam a ele."""
    caminho = Path(caminho)
    a = Analise(caminho=str(caminho))
    if not caminho.is_file():
        a.erros.append("arquivo não encontrado")
        return a

    for etapa in (analisar_fluxos, analisar_cauda):
        try:
            etapa(caminho, a)
        except Exception as e:                           # noqa: BLE001
            a.erros.append(f"{etapa.__name__}: {type(e).__name__}: {e}")

    ext = caminho.suffix.lower()
    especifica = None
    if ext in EXT_PDF:
        especifica = analisar_pdf
    elif ext in EXT_OFFICE:
        especifica = analisar_office
    elif ext in EXT_IMAGEM:
        especifica = analisar_imagem
    if especifica is not None:
        try:
            especifica(caminho, a)
        except Exception as e:                           # noqa: BLE001
            a.erros.append(f"{especifica.__name__}: {type(e).__name__}: {e}")
    return a
