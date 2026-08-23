"""
Constatação de conteúdo em meio eletrônico.

Sem dependência de interface, para poder ser testado isolado.

O que esta ferramenta produz **não é ata notarial**: ata notarial é ato
privativo de tabelião. É o termo de constatação que o servidor já lavra —
feito com método. A diferença entre um print colado no Word e uma peça que
sobrevive a contestação está em três coisas, e todas são responsabilidade
deste módulo:

* registrar **o que** se viu — a página inteira, o código que a produziu e
  a lista de recursos que ela carregou;
* registrar **de onde** veio — o endereço IP para o qual o domínio
  resolvia naquele instante e o certificado que o servidor apresentou;
* registrar **quando**, e provar que nada mudou depois — o resumo SHA-256
  de cada peça, encadeado num resumo da sessão.

A verificação de rede é feita aqui, e não perguntando ao navegador, de
propósito: são duas observações independentes do mesmo fato. Se o
navegador e a consulta direta concordam sobre para qual IP aquele domínio
apontava, a constatação fica bem mais difícil de contestar do que se tudo
viesse da mesma fonte.
"""

from __future__ import annotations

import hashlib
import os
import socket
import ssl
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

#: Tempo máximo de espera nas consultas de rede, em segundos.
TEMPO_LIMITE = 8


def _novo_id() -> str:
    return uuid.uuid4().hex[:12]


# ─────────────────────────────────────────
#  OBSERVAÇÃO DA REDE
# ─────────────────────────────────────────

@dataclass
class Certificado:
    """O que o servidor apresentou como identidade."""

    titular: str = ""
    emissor: str = ""
    valido_de: str = ""
    valido_ate: str = ""
    numero_serie: str = ""
    #: SHA-256 do certificado em DER — identifica o certificado exato.
    impressao: str = ""
    erro: str = ""

    @property
    def obtido(self) -> bool:
        return bool(self.impressao)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _nome(campos) -> str:
    """Achata o nome distinto do certificado numa linha legível."""
    partes = []
    for grupo in campos or ():
        for chave, valor in grupo:
            if chave in ("commonName", "organizationName", "countryName"):
                partes.append(str(valor))
    return ", ".join(dict.fromkeys(partes))


def certificado_tls(host: str, porta: int = 443) -> Certificado:
    """Certificado apresentado pelo servidor, lido em conexão própria."""
    try:
        contexto = ssl.create_default_context()
        with socket.create_connection((host, porta), TEMPO_LIMITE) as bruto:
            with contexto.wrap_socket(bruto, server_hostname=host) as seguro:
                dados = seguro.getpeercert()
                der = seguro.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError, ValueError) as e:
        return Certificado(erro=f"{type(e).__name__}: {e}")

    return Certificado(
        titular=_nome(dados.get("subject")),
        emissor=_nome(dados.get("issuer")),
        valido_de=str(dados.get("notBefore", "")),
        valido_ate=str(dados.get("notAfter", "")),
        numero_serie=str(dados.get("serialNumber", "")),
        impressao=hashlib.sha256(der).hexdigest(),
    )


def resolver(host: str) -> list[str]:
    """Endereços IP para os quais o domínio aponta neste instante."""
    try:
        achados = socket.getaddrinfo(host, None)
    except OSError:
        return []
    return sorted({str(a[4][0]) for a in achados})


# ─────────────────────────────────────────
#  PEÇAS
# ─────────────────────────────────────────

@dataclass
class Peca:
    """Um arquivo produzido pela captura, com o seu resumo."""

    nome: str = ""
    descricao: str = ""
    caminho: str = ""
    tamanho: int = 0
    sha256: str = ""

    def calcular(self):
        arq = Path(self.caminho)
        if not arq.is_file():
            return
        self.tamanho = arq.stat().st_size
        d = hashlib.sha256()
        with open(arq, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                d.update(bloco)
        self.sha256 = d.hexdigest()


@dataclass
class Recurso:
    """Um endereço que a página carregou durante a exibição."""

    url: str = ""
    tipo: str = ""
    metodo: str = "GET"

    @property
    def dominio(self) -> str:
        return urlparse(self.url).netloc


@dataclass
class Captura:
    """Tudo o que se observou de um endereço, num instante."""

    url: str = ""
    url_final: str = ""            # depois de eventuais redirecionamentos
    titulo: str = ""
    quando: datetime = field(default_factory=lambda: datetime.now().astimezone())
    ips: list[str] = field(default_factory=list)
    certificado: Certificado = field(default_factory=Certificado)
    pecas: list[Peca] = field(default_factory=list)
    recursos: list[Recurso] = field(default_factory=list)

    @property
    def host(self) -> str:
        return urlparse(self.url_final or self.url).netloc.split(":")[0]

    @property
    def quando_br(self) -> str:
        return self.quando.strftime("%d/%m/%Y às %H:%M:%S")

    @property
    def quando_utc(self) -> str:
        return self.quando.astimezone(timezone.utc).strftime(
            "%d/%m/%Y às %H:%M:%S UTC")

    @property
    def dominios_terceiros(self) -> list[str]:
        """Domínios distintos do principal que a página acionou."""
        principal = self.host.lower()
        return sorted({r.dominio for r in self.recursos
                       if r.dominio and not r.dominio.lower().endswith(principal)})

    @property
    def resumo(self) -> str:
        d = hashlib.sha256()
        d.update((self.url_final or self.url).encode("utf-8"))
        d.update(self.quando.isoformat().encode("utf-8"))
        for p in self.pecas:
            d.update(p.sha256.encode("ascii"))
        return d.hexdigest()


@dataclass
class Sessao:
    """Uma diligência: uma ou mais capturas, feitas na mesma ocasião."""

    id: str = field(default_factory=_novo_id)
    inicio: datetime = field(default_factory=lambda: datetime.now().astimezone())
    capturas: list[Captura] = field(default_factory=list)
    #: Declaração obrigatória quando o conteúdo só era visível a uma conta.
    #: Conteúdo restrito é fato distinto de conteúdo público, e o termo
    #: perde valor — e ganha uma brecha — se não disser em que condição foi
    #: visto.
    autenticada: bool = False
    conta: str = ""
    observacoes: str = ""

    @property
    def inicio_br(self) -> str:
        return self.inicio.strftime("%d/%m/%Y às %H:%M:%S")

    @property
    def resumo(self) -> str:
        """SHA-256 que amarra a diligência inteira.

        Encadeia os resumos de cada captura, que por sua vez encadeiam os
        das peças. Basta um byte diferente em qualquer arquivo para este
        código mudar — então um único número no termo cobre o conjunto.
        """
        d = hashlib.sha256()
        d.update(self.inicio.isoformat().encode("utf-8"))
        for c in self.capturas:
            d.update(c.resumo.encode("ascii"))
        return d.hexdigest()

    @property
    def pecas(self) -> list[Peca]:
        return [p for c in self.capturas for p in c.pecas]


def pasta_sessoes() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    raiz = Path(base) if base else Path.home() / ".local" / "share"
    destino = raiz / "SistemaTemis" / "constatacoes"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def empacotar(sessao: Sessao, destino: str | Path) -> Path:
    """Reúne as peças num ZIP, com um índice legível.

    O índice vai junto porque o ZIP pode ser aberto por quem não tem o
    termo à mão, e sem ele os arquivos não se explicam.
    """
    destino = Path(destino)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        indice = [
            "CONSTATAÇÃO DE CONTEÚDO EM MEIO ELETRÔNICO",
            f"Diligência {sessao.id} — iniciada em {sessao.inicio_br}",
            f"Resumo da sessão (SHA-256): {sessao.resumo}",
            "",
        ]
        if sessao.autenticada:
            indice += [f"SESSÃO AUTENTICADA na conta: {sessao.conta}", ""]

        for i, c in enumerate(sessao.capturas, 1):
            indice += [
                f"{i}. {c.url_final or c.url}",
                f"   título: {c.titulo}",
                f"   em: {c.quando_br}  ({c.quando_utc})",
                f"   IP: {', '.join(c.ips) or '—'}",
                f"   certificado SHA-256: {c.certificado.impressao or '—'}",
            ]
            for p in c.pecas:
                arq = Path(p.caminho)
                if arq.is_file():
                    z.write(arq, f"{i:02d}/{arq.name}")
                indice.append(f"   {arq.name}  SHA-256: {p.sha256}")
            indice.append("")

        z.writestr("INDICE.txt", "\n".join(indice))
    return destino


# ─────────────────────────────────────────
#  TERMO
# ─────────────────────────────────────────

INK = "#16233A"
CINZA = "#5B6B82"
DESTAQUE = "#B3261E"


@dataclass
class Declarante:
    nome: str = ""
    matricula: str = ""
    lotacao: str = ""
    cargo: str = "Policial Rodoviário Federal"


@dataclass
class Procedimento:
    tipo: str = "IPS"
    numero: str = ""


def _linha(rotulo: str, valor: str, mono: bool = False,
           alerta: bool = False) -> str:
    import html as _html

    e = _html.escape
    cor = DESTAQUE if alerta else INK
    face = ' face="Courier New" size="1"' if mono else ""
    return (
        "<tr>"
        f'<td width="30%"><font color="{CINZA}">{e(rotulo)}</font></td>'
        f'<td><font color="{cor}"{face}>{e(valor) or "—"}</font></td>'
        "</tr>"
    )


def _bloco_captura(c: Captura, numero: int, total: int) -> str:
    import html as _html

    from .metadados_core import formatar_tamanho

    e = _html.escape
    titulo = (f"{numero}. {e(c.titulo or c.url)}" if total > 1
              else e(c.titulo or c.url))

    identificacao = "".join([
        _linha("Endereço acessado", c.url),
        _linha("Endereço final", c.url_final)
        if c.url_final and c.url_final != c.url else "",
        _linha("Título da página", c.titulo),
        _linha("Data e hora (local)", c.quando_br),
        _linha("Data e hora (UTC)", c.quando_utc),
    ])

    if c.certificado.obtido:
        rede = "".join([
            _linha("Endereço IP do servidor", ", ".join(c.ips)),
            _linha("Certificado — titular", c.certificado.titular),
            _linha("Certificado — emissor", c.certificado.emissor),
            _linha("Certificado — validade",
                   f"{c.certificado.valido_de} a {c.certificado.valido_ate}"),
            _linha("Certificado — nº de série", c.certificado.numero_serie,
                   mono=True),
            _linha("Certificado — SHA-256", c.certificado.impressao,
                   mono=True),
        ])
    else:
        rede = _linha("Verificação de rede",
                      c.certificado.erro or "não realizada", alerta=True)

    pecas = "".join(
        "<tr>"
        f'<td><font color="{INK}">{e(p.nome)}</font></td>'
        f'<td><font color="{CINZA}" size="1">{e(p.descricao)}</font></td>'
        f'<td align="center"><font color="{INK}">'
        f"{e(formatar_tamanho(p.tamanho))}</font></td>"
        f'<td><font color="{INK}" face="Courier New" size="1">'
        f"{e(p.sha256)}</font></td>"
        "</tr>"
        for p in c.pecas)

    terceiros = c.dominios_terceiros
    bloco_terceiros = ""
    if terceiros:
        bloco_terceiros = (
            f'<p align="justify" style="font-size:9pt; line-height:150%;">'
            f'<font color="{CINZA}">Durante a exibição a página acionou '
            f"{len(c.recursos)} requisição(ões), alcançando "
            f"{len(terceiros)} domínio(s) além do principal: "
            f"{e(', '.join(terceiros[:20]))}"
            f"{'…' if len(terceiros) > 20 else ''}.</font></p>")

    return f"""
<p style="margin-top:18px; margin-bottom:4px; font-size:11pt;">
  <b><font color="{INK}">{titulo}</font></b>
</p>
<table width="100%" cellspacing="0" cellpadding="4" border="1"
       style="border-collapse:collapse; font-size:9pt;">{identificacao}</table>
<table width="100%" cellspacing="0" cellpadding="4" border="1"
       style="border-collapse:collapse; font-size:9pt; margin-top:6px;">
  {rede}</table>
<table width="100%" cellspacing="0" cellpadding="5" border="1"
       style="border-collapse:collapse; font-size:9pt; margin-top:6px;">
  <tr style="background-color:#0A2442; color:#FFD633;">
    <th width="20%">Arquivo</th><th width="26%">Conteúdo</th>
    <th width="10%">Tamanho</th><th width="44%">SHA-256</th>
  </tr>
  {pecas}
</table>
{bloco_terceiros}
"""


def build_html(sessao: Sessao, decl: Declarante | None = None,
               proc: Procedimento | None = None) -> str:
    """Termo de constatação em HTML, para exibir e exportar."""
    import html as _html

    e = _html.escape
    decl = decl or Declarante()
    proc = proc or Procedimento()
    total = len(sessao.capturas)

    quem = (f"eu, PRF {e(decl.nome)}, matrícula {e(decl.matricula)}, "
            f"lotado(a) no(a) {e(decl.lotacao)}, " if decl.nome else "")
    vinculo = (f"para instruir os autos {'da' if proc.tipo == 'IPS' else 'do'} "
               f"{e(proc.tipo)} nº {e(proc.numero)}, " if proc.numero else "")
    quantos = ("o endereço eletrônico abaixo" if total == 1
               else f"os {total} endereços eletrônicos abaixo")
    abertura = (
        f"Em {sessao.inicio_br}, {quem}{vinculo}acessei {quantos} e "
        "constatei o conteúdo neles publicado, na forma e pelos meios "
        "adiante descritos."
    )

    aviso_sessao = ""
    if sessao.autenticada:
        aviso_sessao = (
            f'<p align="justify" style="font-size:11pt; line-height:160%;">'
            f'<font color="{DESTAQUE}"><b>Sessão autenticada.</b></font> '
            "O conteúdo constatado <b>não era de acesso público</b>: sua "
            "exibição dependeu de autenticação na conta "
            f"<b>{e(sessao.conta) or '(não informada)'}</b>, realizada pelo "
            "signatário no ato da constatação. Registra-se que pessoa não "
            "autenticada, ou autenticada em outra conta, poderia não "
            "visualizar o mesmo conteúdo.</p>")

    blocos = "".join(_bloco_captura(c, i, total)
                     for i, c in enumerate(sessao.capturas, 1))

    observacoes = ""
    if sessao.observacoes.strip():
        observacoes = (
            f'<p align="justify" style="font-size:11pt; line-height:160%; '
            f'margin-top:14px;"><b>Observações do signatário:</b> '
            f"{e(sessao.observacoes.strip())}</p>")

    assinatura = ""
    if decl.nome:
        v = " · ".join(x for x in (
            f"matrícula {e(decl.matricula)}" if decl.matricula else "",
            e(decl.lotacao) if decl.lotacao else "") if x)
        assinatura = f"""
<div align="center" style="margin-top:40px;">
  ______________________________________<br/>
  <b><font color="{INK}">{e(decl.nome)}</font></b><br/>
  <font color="{INK}" size="2">{e(decl.cargo)}</font>
  {f'<br/><font color="{CINZA}" size="1">{v}</font>' if v else ''}
</div>"""

    return f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif; color:{INK};">
<div align="center" style="margin-bottom:16px;">
  <b style="font-size:14pt; letter-spacing:0.5px;">Termo de Constatação de Conteúdo em Meio Eletrônico</b>
</div>
<hr/>
<p align="justify" style="font-size:11pt; line-height:160%;">{abertura}</p>
{aviso_sessao}
{blocos}
<table width="100%" cellspacing="0" cellpadding="4" style="font-size:9pt;
       margin-top:10px;">
  {_linha("Resumo da diligência (SHA-256)", sessao.resumo, mono=True)}
</table>
{observacoes}
<p align="justify" style="font-size:10pt; line-height:150%; margin-top:16px;">
A constatação consistiu na exibição de cada endereço em navegador dedicado
a este fim, integrante deste sistema, sem extensões instaladas e sem sessão
de navegação anterior, e no registro do que foi exibido. A resolução do
domínio e a leitura do certificado do servidor foram feitas por conexão
própria, independente da que renderizou a página — são duas observações
distintas do mesmo fato. O resumo criptográfico SHA-256 de cada peça, e o
resumo da diligência que os encadeia, permitem verificar a qualquer tempo
que os arquivos apresentados são exatamente os produzidos neste ato.
</p>
<p align="justify" style="font-size:10pt; line-height:150%;">
O presente termo <b>não constitui ata notarial</b>, ato privativo de
tabelião, <b>nem atesta a veracidade do conteúdo constatado</b> — atesta
que o conteúdo estava acessível no endereço indicado, na data e hora
registradas, nas condições aqui descritas.
</p>
<p align="justify" style="font-size:11pt; margin-top:14px;">
Sem mais a relatar, encerro o presente termo.
</p>
{assinatura}
</body></html>
"""
