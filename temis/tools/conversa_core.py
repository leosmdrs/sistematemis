"""
Reconstrução de conversa exportada, em peça conferível.

A corregedoria costuma receber a conversa já exportada — o arquivo que o
próprio aplicativo gera, "Exportar conversa". Trabalhá-la no Bloco de
Notas resolve o prático e destrói o jurídico: ao fim existe um texto, e
não existe como demonstrar que ele corresponde ao arquivo recebido.

O que esta ferramenta faz é estreito, e é justamente por ser estreito que
se sustenta. Ela **reconstrói a conversa a partir do arquivo de
exportação e a identifica pelo resumo criptográfico desse arquivo**. A
peça atesta uma coisa só: que esta reprodução corresponde àquele arquivo,
com aquele resumo. Não atesta a autenticidade nem a completude da
conversa original — o arquivo de exportação é gerado no aparelho e pode
ser editado como qualquer texto antes de chegar aqui, e a peça diz isso
com todas as letras.

Formatos
--------
Lê a exportação do WhatsApp em texto (`.txt`) e o pacote (`.zip`) que
inclui as mídias. As duas variações de formato — a do iOS, com a data
entre colchetes, e a do Android, com hífen — são reconhecidas. Quando o
pacote traz as mídias, cada arquivo é resumido em SHA-256 e relacionado à
mensagem que o referencia.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .hash_core import sha256_file

#: Formatos de arquivo que a ferramenta abre.
FORMATOS = (".txt", ".zip")

#: Marcas de direção que o iOS insere no começo das linhas e antes de
#: anexos. Não são conteúdo; atrapalham o reconhecimento e a leitura.
_MARCAS = "‎‏‪‫‬⁨⁩"

#: A data e a hora no começo de uma mensagem, nas duas variações:
#: iOS  ->  [25/12/2024 14:30:45] Autor: texto
#: Android -> 25/12/2024 14:30 - Autor: texto
_LINHA = re.compile(
    r"^\[?"
    r"(?P<data>\d{1,2}[/.]\d{1,2}[/.]\d{2,4})"
    r"[,\s]+"
    r"(?P<hora>\d{1,2}:\d{2}(?::\d{2})?)"
    r"\s?(?P<ampm>[APap]\.?[Mm]\.?)?"
    r"\]?"
    r"(?:\s-\s|\]\s?|\s)"
    r"(?P<resto>.*)$"
)

#: Trechos que denunciam mensagem de sistema, não de pessoa. Reconhecidos
#: por padrão, e a peça declara que o reconhecimento é por padrão — em
#: formato incomum, uma pode escapar.
_SISTEMA = (
    "as mensagens e as chamadas são", "as mensagens são protegidas",
    "criptografia de ponta a ponta", "messages and calls are end-to-end",
    "you created group", "você criou o grupo", "criou o grupo",
    "adicionou", "added", "saiu", "left", "removeu", "removed",
    "mudou o assunto", "changed the subject", "mudou a descrição",
    "mudou o número", "changed their phone number",
    "mudou a imagem do grupo", "changed this group's icon",
    "esta mensagem foi apagada", "this message was deleted",
    "você apagou esta mensagem", "you deleted this message",
    "código de segurança", "security code changed",
)

#: Como as mídias aparecem no texto quando o export não as inclui, e
#: quando inclui (iOS: "<anexado: arquivo>"; Android: "arquivo (arquivo
#: anexado)").
_MIDIA_OMITIDA = re.compile(
    r"(?:<\s*mídia\s+oculta\s*>|<\s*media\s+omitted\s*>|"
    r"imagem\s+ocultada|áudio\s+ocultado|vídeo\s+ocultado|"
    r"figurinha\s+omitida|gif\s+omitido|documento\s+omitido|"
    r"contato\s+não\s+incluído)", re.I)
_MIDIA_ANEXA = re.compile(
    r"<\s*anexad[oa]:\s*(?P<arq>[^>]+?)\s*>"
    r"|(?P<arq2>[\w\-.]+\.\w{2,4})\s*\((?:arquivo\s+anexado|file\s+attached)\)",
    re.I)


def _limpar(texto: str) -> str:
    return texto.translate({ord(c): None for c in _MARCAS}).strip()


@dataclass
class Mensagem:
    """Uma linha da conversa, já separada em quem, quando e o quê."""

    quando: str = ""            # como estava no arquivo
    quando_iso: str = ""        # normalizado, quando deu para ler
    autor: str = ""
    texto: str = ""
    sistema: bool = False
    #: Referência a mídia: o nome do arquivo, ou o rótulo de omissão.
    midia: str = ""
    midia_sha256: str = ""
    midia_caminho: str = ""

    @property
    def tem_midia(self) -> bool:
        return bool(self.midia)


@dataclass
class Conversa:
    """A conversa reconstruída, e o arquivo de que veio."""

    origem: str = ""
    resumo_origem: str = ""
    tamanho_origem: int = 0
    formato: str = ""            # "texto" ou "pacote"
    mensagens: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    @property
    def participantes(self) -> list:
        vistos = []
        for m in self.mensagens:
            if m.autor and not m.sistema and m.autor not in vistos:
                vistos.append(m.autor)
        return vistos

    @property
    def periodo(self) -> tuple:
        datas = [m.quando_iso for m in self.mensagens if m.quando_iso]
        return (datas[0], datas[-1]) if datas else ("", "")

    @property
    def n_mensagens(self) -> int:
        return sum(1 for m in self.mensagens if not m.sistema)

    @property
    def n_midias(self) -> int:
        return sum(1 for m in self.mensagens if m.midia_sha256)

    def resumo_conteudo(self) -> str:
        """Resumo do conteúdo reconstruído, para conferir a reprodução.

        Sobre o que a ferramenta produziu — autor, instante, texto e o
        resumo de cada mídia —, e não sobre os bytes do arquivo, que já
        têm o seu próprio resumo. Permite conferir que esta reprodução é a
        mesma que qualquer um obteria relendo o arquivo.
        """
        h = hashlib.sha256()
        for m in self.mensagens:
            for parte in (m.quando, m.autor, m.texto,
                          "S" if m.sistema else "M", m.midia, m.midia_sha256):
                h.update(parte.encode("utf-8"))
                h.update(b"\x1f")
            h.update(b"\x1e")
        return h.hexdigest()


def _quando_iso(data: str, hora: str, ampm: str) -> str:
    """A data/hora normalizada em ISO, ou vazio se não deu para ler."""
    sep = "/" if "/" in data else "."
    try:
        d, mes, a = (int(x) for x in data.split(sep))
    except ValueError:
        return ""
    if a < 100:
        a += 2000 if a < 70 else 1900
    partes = hora.split(":")
    hh = int(partes[0])
    mm = int(partes[1]) if len(partes) > 1 else 0
    ss = int(partes[2]) if len(partes) > 2 else 0
    if ampm:
        marca = ampm.lower().replace(".", "")
        if marca == "pm" and hh < 12:
            hh += 12
        elif marca == "am" and hh == 12:
            hh = 0
    # A data vem como dia/mês na exportação em português. Se o segundo
    # campo passou de 12, ele não pode ser mês: veio mês/dia (formato
    # americano), e se corrige. O caso comum — 25/12 — não é tocado.
    if mes > 12 and d <= 12:
        d, mes = mes, d
    try:
        return datetime.datetime(a, mes, d, hh, mm, ss).isoformat(
            timespec="seconds")
    except ValueError:
        return ""


def _classificar(resto: str) -> tuple:
    """(autor, texto, é_sistema) a partir do que vem depois da data."""
    baixo = resto.lower()
    if any(marca in baixo for marca in _SISTEMA):
        return "", resto, True
    # Autor e mensagem se separam no primeiro ": ". Nome de contato não
    # costuma ter mais que poucas palavras; texto longo antes do primeiro
    # dois-pontos é frase, não nome — e aí é mensagem de sistema.
    corte = resto.find(": ")
    if corte < 0:
        return "", resto, True
    autor = resto[:corte].strip()
    if len(autor) > 60 or "\n" in autor:
        return "", resto, True
    return autor, resto[corte + 2:], False


def parse_texto(texto: str) -> tuple:
    """Lê o texto exportado e devolve (mensagens, avisos)."""
    mensagens: list = []
    avisos: list = []
    atual: Mensagem | None = None

    for linha_bruta in texto.replace("\r\n", "\n").split("\n"):
        linha = _limpar(linha_bruta)
        m = _LINHA.match(linha)
        if not m:
            # Continuação da mensagem anterior — mensagem de várias linhas.
            if atual is not None and linha_bruta.strip("\r\n"):
                atual.texto += "\n" + _limpar(linha_bruta)
            continue
        autor, corpo, sistema = _classificar(m.group("resto"))
        atual = Mensagem(
            quando=f"{m.group('data')} {m.group('hora')}"
                   + (f" {m.group('ampm')}" if m.group("ampm") else ""),
            quando_iso=_quando_iso(m.group("data"), m.group("hora"),
                                   m.group("ampm") or ""),
            autor=autor, texto=corpo, sistema=sistema)
        mensagens.append(atual)

    for m in mensagens:
        anexo = _MIDIA_ANEXA.search(m.texto)
        if anexo:
            m.midia = (anexo.group("arq") or anexo.group("arq2") or "").strip()
        elif _MIDIA_OMITIDA.search(m.texto):
            m.midia = "(mídia não incluída na exportação)"

    if not mensagens:
        avisos.append("Nenhuma mensagem foi reconhecida. O arquivo pode não "
                      "ser uma exportação de conversa, ou estar num formato "
                      "que esta ferramenta ainda não lê.")
    return mensagens, avisos


def abrir(caminho) -> Conversa:
    """Abre a exportação (.txt ou .zip) e reconstrói a conversa.

    O resumo do arquivo é tomado aqui, no primeiro contato — é o marco a
    partir do qual a peça responde pelo material.
    """
    caminho = Path(caminho)
    conversa = Conversa(origem=str(caminho))
    try:
        conversa.tamanho_origem = caminho.stat().st_size
        conversa.resumo_origem = sha256_file(str(caminho))
    except OSError as e:
        conversa.avisos.append(f"não foi possível ler o arquivo: {e}")
        return conversa

    if caminho.suffix.lower() == ".zip":
        conversa.formato = "pacote"
        _abrir_pacote(caminho, conversa)
    else:
        conversa.formato = "texto"
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        conversa.mensagens, conversa.avisos = parse_texto(texto)
    return conversa


def _abrir_pacote(caminho: Path, conversa: Conversa) -> None:
    """Lê o .zip: o texto da conversa e as mídias, cada uma resumida."""
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            alvo = next((n for n in nomes if n.lower().endswith("_chat.txt")),
                        None)
            if alvo is None:
                alvo = next((n for n in nomes if n.lower().endswith(".txt")),
                            None)
            if alvo is None:
                conversa.avisos.append(
                    "O pacote não contém o arquivo de texto da conversa.")
                return
            texto = z.read(alvo).decode("utf-8", errors="replace")
            conversa.mensagens, conversa.avisos = parse_texto(texto)

            # Resumo de cada mídia presente, ligado à mensagem que a cita.
            presentes = {Path(n).name: n for n in nomes if n != alvo}
            for m in conversa.mensagens:
                if m.midia and m.midia in presentes:
                    dados = z.read(presentes[m.midia])
                    m.midia_sha256 = hashlib.sha256(dados).hexdigest()
                    m.midia_caminho = presentes[m.midia]
    except zipfile.BadZipFile:
        conversa.avisos.append("O arquivo não é um pacote .zip válido.")


def midia_bytes(caminho_zip, interno: str) -> bytes:
    """Os bytes de uma mídia dentro do pacote, para exibição."""
    try:
        with zipfile.ZipFile(caminho_zip) as z:
            return z.read(interno)
    except Exception:                                       # noqa: BLE001
        return b""


# ─────────────────────────────────────────
#  O TERMO
# ─────────────────────────────────────────

INK = "#16233A"
CINZA = "#5A6B85"


@dataclass
class Declarante:
    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = ""
    orgao: str = ""

    def __post_init__(self):
        from .derivado_core import cargo_padrao, orgao_padrao
        if not self.cargo:
            self.cargo = cargo_padrao()
        if not self.orgao:
            self.orgao = orgao_padrao()


@dataclass
class Procedimento:
    tipo: str = "IPS"
    numero: str = ""


#: O que a peça atesta, e — com igual clareza — o que ela não atesta. É a
#: honestidade destes limites que dá peso ao que ela de fato afirma.
RESSALVAS = (
    "Esta peça é a reprodução do arquivo de exportação identificado acima, "
    "cujo resumo criptográfico SHA-256 consta desta peça. Atesta que a "
    "reconstrução corresponde àquele arquivo — e não a autenticidade nem a "
    "completude da conversa original.",
    "O arquivo de exportação é gerado pelo próprio aplicativo, no aparelho, "
    "e é, na origem, um arquivo de texto: pode ter sido editado antes de "
    "chegar a esta ferramenta. A peça nada afirma sobre o que houve antes "
    "da abertura do arquivo por este sistema.",
    "As datas e horas são as registradas no arquivo, no fuso do aparelho "
    "que exportou — que o arquivo, em geral, não declara. Devem ser lidas "
    "com essa ressalva.",
    "As mensagens de sistema — avisos de criptografia, entradas e saídas, "
    "mudanças de grupo, mensagens apagadas — são reconhecidas por padrão e "
    "assinaladas como tais. Em formato incomum, alguma pode ser classificada "
    "como mensagem comum, ou o contrário.",
    "Quando a exportação inclui as mídias, cada arquivo é resumido em "
    "SHA-256 e relacionado à mensagem que o cita; os arquivos de mídia "
    "acompanham esta peça. Quando a exportação é apenas texto, a mídia não "
    "a acompanha, e a mensagem correspondente consta como referência.",
)


def _linha_tabela(rotulo, valor, mono=False):
    import html as _h
    face = " face='Courier New' size='1'" if mono else ""
    return ('<tr><td width="30%"><font color="' + CINZA + '">'
            + _h.escape(rotulo) + '</font></td><td><font color="' + INK + '"'
            + face + ">" + (_h.escape(valor) or "\u2014") + "</font></td></tr>")


def _bloco_mensagens(conversa):
    import html as _h
    e = _h.escape
    linhas = []
    for m in conversa.mensagens:
        quando = m.quando_iso.replace("T", " ") if m.quando_iso else m.quando
        if m.sistema:
            linhas.append(
                '<p align="center" style="font-size:8.5pt;margin:6px 0;">'
                '<font color="' + CINZA + '"><i>' + e(m.texto.strip())
                + "</i>  \u00b7  " + e(quando) + "</font></p>")
            continue
        if m.midia:
            if m.midia_sha256:
                corpo = ('<font color="' + CINZA + '" size="1">[m\u00eddia: '
                         + e(m.midia) + " \u00b7 SHA-256 " + m.midia_sha256
                         + "]</font>")
            elif m.midia.startswith("("):
                corpo = ('<font color="' + CINZA + '" size="1">['
                         + e(m.midia) + "]</font>")
            else:
                corpo = ('<font color="' + CINZA + '" size="1">[m\u00eddia '
                         "referida, n\u00e3o inclu\u00edda na exporta\u00e7\u00e3o: "
                         + e(m.midia) + "]</font>")
        else:
            corpo = e(m.texto.strip())
        linhas.append(
            '<p style="font-size:10pt;line-height:135%;margin:8px 0 2px;">'
            '<b><font color="' + INK + '">' + e(m.autor) + "</font></b>"
            '  <font color="' + CINZA + '" size="1">' + e(quando)
            + "</font><br/>" + corpo + "</p>")
    return "".join(linhas)


def intro(conversa, decl, proc):
    import html as _h
    from .hash_core import ARTIGO_PROCESSO
    e = _h.escape
    artigo = ARTIGO_PROCESSO.get(proc.tipo, "da")
    quem = ""
    if decl.nome.strip():
        qualif = " ".join(x for x in (decl.cargo.strip(), decl.nome.strip()) if x)
        quem = ("eu, " + e(qualif)
                + (", matr\u00edcula " + e(decl.matricula) if decl.matricula.strip() else "")
                + (", lotado(a) no(a) " + e(decl.lotacao) if decl.lotacao.strip() else "")
                + ", ")
    vinculo = ""
    if proc.numero.strip():
        vinculo = ("visando instruir os autos " + artigo + " " + e(proc.tipo)
                   + " n\u00ba " + e(proc.numero) + ", ")
    nome = Path(conversa.origem).name
    corpo = ("procedi \u00e0 reconstru\u00e7\u00e3o da conversa contida no arquivo de "
             "exporta\u00e7\u00e3o <b>" + e(nome) + "</b>, cujo teor segue reproduzido "
             "abaixo.")
    if quem or vinculo:
        frase = quem + vinculo + corpo
        return frase[0].upper() + frase[1:]
    return ("Segue a reconstru\u00e7\u00e3o da conversa contida no arquivo <b>"
            + e(nome) + "</b>.")


def build_html(conversa, decl=None, proc=None):
    """Termo de reconstrução de conversa, para exibir e exportar."""
    from ..impressao import cabecalho_html, rodape_html
    import html as _h
    e = _h.escape
    decl = decl or Declarante()
    proc = proc or Procedimento()

    ini, fim = conversa.periodo
    periodo = ((ini.replace("T", " ") + " a " + fim.replace("T", " "))
               if ini else "n\u00e3o identificado")
    ident = "".join([
        _linha_tabela("Arquivo de exporta\u00e7\u00e3o", Path(conversa.origem).name),
        _linha_tabela("Formato", "pacote com m\u00eddias (.zip)"
                      if conversa.formato == "pacote" else "texto (.txt)"),
        _linha_tabela("Resumo do arquivo (SHA-256)", conversa.resumo_origem, True),
        _linha_tabela("Participantes", ", ".join(conversa.participantes)),
        _linha_tabela("Per\u00edodo das mensagens", periodo),
        _linha_tabela("Mensagens reconstru\u00eddas", str(conversa.n_mensagens)),
        _linha_tabela("M\u00eddias resumidas", str(conversa.n_midias))
        if conversa.formato == "pacote" else "",
        _linha_tabela("Resumo do conte\u00fado (SHA-256)",
                      conversa.resumo_conteudo(), True),
    ])

    assinatura = ""
    if decl.nome.strip():
        v = " \u00b7 ".join(x for x in (
            "matr\u00edcula " + e(decl.matricula) if decl.matricula.strip() else "",
            e(decl.lotacao) if decl.lotacao.strip() else "") if x)
        assinatura = (
            '<div align="center" style="margin-top:40px;">'
            "______________________________________<br/>"
            '<b><font color="' + INK + '">' + e(decl.nome) + "</font></b><br/>"
            '<font color="' + INK + '" size="2">' + e(decl.cargo) + "</font>"
            + ('<br/><font color="' + CINZA + '" size="1">' + v + "</font>" if v else "")
            + "</div>")

    ressalvas = "".join(
        '<p align="justify" style="font-size:10pt;line-height:150%;">'
        '<font color="' + INK + '">' + e(x) + "</font></p>" for x in RESSALVAS)

    avisos = ""
    if conversa.avisos:
        avisos = ('<p style="font-size:10pt;margin-top:10px;"><font color="'
                  + CINZA + '">Observa\u00e7\u00f5es da leitura: '
                  + "; ".join(e(a) for a in conversa.avisos) + "</font></p>")

    partes = [
        '<html><body style="font-family:\'Segoe UI\',Arial,sans-serif; color:'
        + INK + ';">',
        cabecalho_html(),
        '<div align="center" style="margin-bottom:16px;"><b style="font-size:'
        '14pt; letter-spacing:0.5px;">Termo de Reconstru\u00e7\u00e3o de '
        "Conversa</b></div><hr/>",
        '<p align="justify" style="font-size:11pt; line-height:160%;">'
        + intro(conversa, decl, proc) + "</p>",
        '<table width="100%" cellspacing="0" cellpadding="4" border="1" '
        'style="border-collapse:collapse; font-size:9pt;">' + ident + "</table>",
        avisos,
        '<p style="margin-top:18px; margin-bottom:6px;"><b>Conversa '
        "reconstru\u00edda</b></p>",
        _bloco_mensagens(conversa)
        or ('<p><font color="' + CINZA + '">Nenhuma mensagem '
            "reconhecida.</font></p>"),
        '<p style="font-size:11pt; margin-top:18px;"><b><font color="' + INK
        + '">Alcance e limites</font></b></p>',
        ressalvas,
        '<p align="justify" style="font-size:11pt; margin-top:14px;">Sem mais '
        "a relatar, encerro o presente termo.</p>",
        assinatura,
        rodape_html(),
        "</body></html>",
    ]
    return "".join(partes)
