"""
Verificação e instalação de atualizações.

Sem dependência de interface, para poder ser testado isolado.

Como funciona: ao abrir, o sistema busca um arquivo `versao.json` num
endereço fixo e compara com a versão instalada. Havendo versão mais nova,
**pergunta ao usuário** — nada é baixado ou instalado sem autorização. Se
ele aceitar, o instalador é baixado, conferido pelo SHA-256 declarado no
manifesto e só então executado.

O manifesto não escolhe de onde vem o instalador: o endereço tem de ser
o da release daquela versão, neste repositório, e a versão tem de ser um
número. O resumo é conferido de novo no instante de executar. A estação
pode desligar a atualização ou fixar uma versão por política (`politica`).

E o manifesto é assinado. Quem publica guarda uma chave privada fora do
repositório; a pública vai embutida aqui (`CHAVES_PUBLICAS`). Versão,
resumo e tamanho do instalador só são aceitos com a assinatura dessa
chave — de modo que escrever no repositório deixa de bastar para fazer
chegar um instalador às estações.

Sobre confiança, com franqueza: quem tiver poder de escrita no endereço
de publicação pode fazer chegar código a todas as estações que usam o
sistema. O hash protege contra um download corrompido ou adulterado no
caminho, e o HTTPS contra interceptação — mas nenhum dos dois protege
contra o próprio repositório comprometido. A defesa para isso é assinar o
instalador com certificado de código, o que também faria o Windows parar
de bloquear a instalação. Enquanto não houver certificado, o acesso de
escrita ao repositório precisa ser tão restrito quanto o dos autos.

Nada é enviado da máquina: a verificação é uma requisição de leitura de um
arquivo estático, sem identificação do usuário nem da estação.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

#: Onde o sistema é publicado: o GitLab da PRF. Até a 1.15.2 era o GitHub
#: (`leosmdrs/sistematemis`); a 1.15.3 é a versão que muda o endereço, e
#: por isso ela ainda precisa sair também lá — é de lá que as estações
#: antigas a recebem.
SERVIDOR = "https://git.prf.gov.br"
REPOSITORIO = "sistemas-nacionais/temis"

#: Endereço do manifesto. O formato `releases/permalink/latest/downloads/`
#: do GitLab sempre aponta para o anexo da versão mais recente publicada,
#: então o endereço nunca muda a cada lançamento. Só funciona se o anexo
#: tiver sido cadastrado na release com o caminho `/versao.json` — o
#: `build/publicar_gitlab.py` faz isso.
#: A consulta vai sem credencial: enquanto o projeto exigir login, ela
#: falha em silêncio e o sistema abre normalmente.
URL_MANIFESTO = (f"{SERVIDOR}/{REPOSITORIO}"
                 "/-/releases/permalink/latest/downloads/versao.json")

#: Segundos de espera. Curto de propósito: se a rede não responder, o
#: sistema abre normalmente — atualizar é acessório, trabalhar não é.
TEMPO_LIMITE = 6

#: Identificação enviada ao servidor. Sem versão, sem máquina, sem usuário.
AGENTE = "SistemaTemis-atualizador"

#: Tamanho máximo aceito para o manifesto, para não ler um arquivo enorme
#: caso o endereço passe a servir outra coisa.
LIMITE_MANIFESTO = 64 * 1024

#: Teto do instalador quando o manifesto não declara o tamanho. O de hoje
#: tem perto de 300 MB.
LIMITE_INSTALADOR = 1024 * 1024 * 1024

#: Prazo total do download, em segundos. O limite por leitura não basta:
#: um servidor que entregue um byte a cada 29 segundos nunca o estoura.
PRAZO_DOWNLOAD = 30 * 60

#: A versão é um número, e só. Ela entra no nome do arquivo gravado em
#: disco e no título da janela; vinda do manifesto sem conferência, um
#: `..\..\x` escolheria onde gravar.
_VERSAO = re.compile(r"\d{1,4}\.\d{1,4}\.\d{1,4}(\.\d{1,4})?")
_HEX64 = re.compile(r"[0-9a-f]{64}")


#: Chaves públicas de quem publica, em hexadecimal — 64 caracteres cada.
#: Com ao menos uma aqui, o programa só aceita atualização cujo manifesto
#: traga a assinatura de uma delas. Vazia, a assinatura não é exigida:
#: é o estado de antes de a primeira chave ser gerada.
#:
#: Quem gera, registra e usa as chaves é o `build/assinatura.py`. Duas
#: chaves são melhor que uma: a de uso e uma de reserva, guardada em
#: outro lugar — perdida a única, nenhuma estação volta a se atualizar
#: sem reinstalação manual.
# <chaves-publicas>
CHAVES_PUBLICAS: tuple = ()
# </chaves-publicas>

#: O que precede o conteúdo assinado. Amarra a assinatura a este uso:
#: uma assinatura feita com a mesma chave para outra coisa não serve
#: aqui, nem a daqui serve lá.
_CONTEXTO_DA_ASSINATURA = "SistemaTemis atualizacao v1"


def conteudo_assinado(versao: str, sha256: str, tamanho: int) -> bytes:
    """O que a assinatura cobre: a versão, o resumo e o tamanho.

    São os três dados que decidem o que a estação instala. O endereço
    não entra porque não é escolha do manifesto — é função da versão. As
    notas e a marca de versão crítica ficam de fora: quem alterasse o
    manifesto poderia mudar o texto exibido, mas não o que é instalado.
    """
    return (f"{_CONTEXTO_DA_ASSINATURA}\n{versao}\n{sha256.lower()}\n"
            f"{int(tamanho)}\n").encode("utf-8")


def assinatura_confere(versao: str, sha256: str, tamanho: int,
                       assinatura: str, chaves=None) -> bool:
    """A assinatura é de uma das chaves de publicação? Nunca levanta."""
    import base64
    import binascii

    from . import ed25519

    chaves = CHAVES_PUBLICAS if chaves is None else chaves
    try:
        bruta = base64.b64decode((assinatura or "").strip(), validate=True)
    except (binascii.Error, ValueError):
        return False
    mensagem = conteudo_assinado(versao, sha256, tamanho)
    for chave in chaves:
        try:
            publica = bytes.fromhex(str(chave).strip())
        except ValueError:
            continue
        if ed25519.confere(publica, mensagem, bruta):
            return True
    return False


def versao_valida(versao: str) -> bool:
    return bool(_VERSAO.fullmatch(versao or ""))


def url_do_instalador(versao: str) -> str:
    """O único endereço de que o instalador de uma versão pode vir."""
    return (f"{SERVIDOR}/{REPOSITORIO}/-/releases/"
            f"v{versao}/downloads/SistemaTemis-{versao}-setup.exe")


# ─────────────────────────────────────────
#  VERSÃO
# ─────────────────────────────────────────

def _partes(versao: str) -> tuple[int, ...]:
    numeros = re.findall(r"\d+", versao or "")
    return tuple(int(n) for n in numeros[:4]) or (0,)


def comparar(a: str, b: str) -> int:
    """-1 se a < b, 0 se iguais, 1 se a > b."""
    pa, pb = _partes(a), _partes(b)
    tamanho = max(len(pa), len(pb))
    pa += (0,) * (tamanho - len(pa))
    pb += (0,) * (tamanho - len(pb))
    return (pa > pb) - (pa < pb)


def mais_nova(candidata: str, instalada: str = "") -> bool:
    return comparar(candidata, instalada or __version__) > 0


@dataclass
class Atualizacao:
    """O que o manifesto anuncia."""

    versao: str = ""
    url: str = ""
    sha256: str = ""
    tamanho: int = 0
    notas: str = ""
    publicado: str = ""
    #: Quando verdadeiro, a tela insiste; ainda assim não instala sozinha.
    critica: bool = False
    #: Assinatura de quem publica sobre a versão, o resumo e o tamanho.
    assinatura: str = ""

    @property
    def assinada(self) -> bool:
        """A assinatura confere — ou não há chave que a exija."""
        if not CHAVES_PUBLICAS:
            return True
        # Sem tamanho não há o que conferir: ele faz parte do assinado,
        # e é o teto do download.
        return self.tamanho > 0 and assinatura_confere(
            self.versao, self.sha256, self.tamanho, self.assinatura)

    @property
    def valida(self) -> bool:
        """Manifesto completo e apontando para a release oficial.

        O endereço não é aceito como vier: quem conseguisse trocar o
        manifesto apontaria o instalador para qualquer servidor. Aqui ele
        tem de ser o da release desta versão, neste repositório.
        """
        return (versao_valida(self.versao)
                and bool(_HEX64.fullmatch(self.sha256))
                and self.tamanho >= 0
                and self.url == url_do_instalador(self.versao))

    @property
    def tamanho_legivel(self) -> str:
        if self.tamanho >= 1 << 20:
            return f"{self.tamanho / (1 << 20):.1f} MB".replace(".", ",")
        if self.tamanho >= 1 << 10:
            return f"{self.tamanho / (1 << 10):.0f} KB"
        return f"{self.tamanho} bytes"


def _inteiro(valor) -> int:
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return -1                      # manifesto inválido, não exceção


def de_dict(dados: dict) -> Atualizacao:
    return Atualizacao(
        versao=str(dados.get("versao", "")).strip(),
        url=str(dados.get("url", "")).strip(),
        sha256=str(dados.get("sha256", "")).strip().lower(),
        tamanho=_inteiro(dados.get("tamanho", 0)),
        notas=str(dados.get("notas", "")).strip(),
        publicado=str(dados.get("publicado", "")).strip(),
        critica=bool(dados.get("critica", False)),
        assinatura=str(dados.get("assinatura", "")).strip(),
    )


# ─────────────────────────────────────────
#  CONSULTA
# ─────────────────────────────────────────

class ErroAtualizacao(Exception):
    """Falha ao consultar ou baixar — sempre com mensagem em português."""


ERRO_ASSINATURA = (
    "Há uma versão anunciada no endereço de atualização, mas o anúncio não "
    "traz a assinatura de quem publica o sistema. Nada foi baixado nem "
    "instalado. Se o aviso persistir, comunique o responsável pelo "
    "sistema.")


class _SoHTTPS(urllib.request.HTTPRedirectHandler):
    """Segue redirecionamento, desde que continue em HTTPS.

    O GitLab entrega os anexos de release por redirecionamento para o
    registro de pacotes, então proibir não é opção. O que não se aceita é o
    caminho descer para HTTP no meio: conferir o esquema só do primeiro
    endereço deixava essa porta aberta.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not str(newurl).lower().startswith("https://"):
            raise urllib.error.URLError(
                "redirecionamento para endereço sem HTTPS recusado")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ABRIDOR = urllib.request.build_opener(_SoHTTPS)


def _abrir(url: str, tempo: int = TEMPO_LIMITE):
    if not url.lower().startswith("https://"):
        # Sem HTTPS não há como saber de quem veio o arquivo.
        raise ErroAtualizacao("O endereço de atualização precisa ser HTTPS.")
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    return _ABRIDOR.open(pedido, timeout=tempo)


def consultar(url: str = URL_MANIFESTO) -> Atualizacao | None:
    """Lê o manifesto. Devolve None quando não há nada mais novo."""
    regra = politica()
    if not regra.atualizar:
        raise ErroAtualizacao(
            "A atualização por este canal está desligada nesta estação, "
            "por configuração do administrador.")
    try:
        with _abrir(url) as resposta:
            bruto = resposta.read(LIMITE_MANIFESTO + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ErroAtualizacao(
                "Nenhuma versão publicada ainda no endereço de atualização.")
        raise ErroAtualizacao(f"O servidor respondeu {e.code}.")
    except urllib.error.URLError as e:
        raise ErroAtualizacao(f"Sem acesso ao endereço de atualização: "
                              f"{e.reason}")
    except (TimeoutError, OSError) as e:
        raise ErroAtualizacao(f"Falha de rede: {e}")

    if len(bruto) > LIMITE_MANIFESTO:
        raise ErroAtualizacao("Resposta inesperada no endereço de atualização.")
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ErroAtualizacao("O manifesto de versão está ilegível.")

    nova = de_dict(dados if isinstance(dados, dict) else {})
    if not nova.valida:
        raise ErroAtualizacao(
            "O manifesto de versão está incompleto ou aponta para fora "
            "do endereço oficial de publicação.")
    if not mais_nova(nova.versao):
        return None
    if regra.versao_fixada and comparar(nova.versao, regra.versao_fixada) > 0:
        # A estação foi fixada numa versão: a mais nova não é oferecida.
        return None
    if not nova.assinada:
        raise ErroAtualizacao(ERRO_ASSINATURA)
    return nova


# ─────────────────────────────────────────
#  DOWNLOAD
# ─────────────────────────────────────────

BLOCO = 256 * 1024


def pasta_download() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMPDIR") or tempfile.gettempdir()
    destino = Path(base) / "SistemaTemis" / "atualizacoes"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def baixar(info: Atualizacao, progresso=None, cancelado=None) -> Path:
    """Baixa o instalador e confere o SHA-256 antes de devolvê-lo.

    O arquivo só recebe o nome definitivo depois de conferido: assim um
    download interrompido não deixa para trás algo que pareça instalável.
    """
    if not info.valida:
        raise ErroAtualizacao(
            "O manifesto de versão está incompleto ou aponta para fora "
            "do endereço oficial de publicação.")
    if not info.assinada:
        raise ErroAtualizacao(ERRO_ASSINATURA)
    destino = pasta_download() / f"SistemaTemis-{info.versao}-setup.exe"
    parcial = destino.with_suffix(".parcial")
    digestor = hashlib.sha256()
    baixado = 0
    teto = info.tamanho or LIMITE_INSTALADOR
    limite = time.monotonic() + PRAZO_DOWNLOAD

    try:
        with _abrir(info.url, tempo=30) as resposta, open(parcial, "wb") as saida:
            total = info.tamanho or int(
                resposta.headers.get("Content-Length") or 0)
            while True:
                if cancelado is not None and cancelado():
                    raise ErroAtualizacao("Download cancelado.")
                pedaco = resposta.read(BLOCO)
                if not pedaco:
                    break
                if baixado + len(pedaco) > teto:
                    raise ErroAtualizacao(
                        "O arquivo recebido é maior que o publicado e "
                        "foi descartado.")
                if time.monotonic() > limite:
                    raise ErroAtualizacao(
                        "O download excedeu o prazo e foi interrompido.")
                saida.write(pedaco)
                digestor.update(pedaco)
                baixado += len(pedaco)
                if progresso is not None:
                    progresso(baixado, total)
    except ErroAtualizacao:
        parcial.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        parcial.unlink(missing_ok=True)
        raise ErroAtualizacao(f"Falha ao baixar a atualização: {e}")

    obtido = digestor.hexdigest()
    if obtido != info.sha256:
        parcial.unlink(missing_ok=True)
        raise ErroAtualizacao(
            "O arquivo baixado não confere com o publicado e foi descartado.\n"
            f"Esperado: {info.sha256}\nObtido:   {obtido}")

    parcial.replace(destino)
    return destino


# ─────────────────────────────────────────
#  INSTALAÇÃO
# ─────────────────────────────────────────

#: `/SILENT` mostra a barra de progresso sem fazer perguntas — o usuário
#: já autorizou na tela do sistema. `/CLOSEAPPLICATIONS` deixa o
#: instalador encerrar o programa em execução para trocar os arquivos.
ARGUMENTOS_INSTALADOR = [
    "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS", "/NORESTART",
]


def resumo_do_arquivo(caminho: Path) -> str:
    digestor = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            digestor.update(bloco)
    return digestor.hexdigest()


def instalar(caminho: Path, sha256: str) -> None:
    """Executa o instalador. Quem chama deve encerrar o programa depois.

    O resumo é conferido de novo aqui, no instante de executar. O
    arquivo fica em pasta que o próprio usuário grava, e entre o fim do
    download e a execução outro processo dele poderia trocá-lo: conferir
    só ao baixar atestava um arquivo que já não era o executado. A
    conferência encurta essa janela a quase nada; fechá-la de vez é
    papel da assinatura de código.
    """
    if not Path(caminho).is_file():
        raise ErroAtualizacao("O instalador baixado não foi encontrado.")
    if sys.platform != "win32":
        raise ErroAtualizacao(
            "A instalação automática só está disponível no Windows.")
    try:
        obtido = resumo_do_arquivo(Path(caminho))
    except OSError as e:
        raise ErroAtualizacao(f"Não foi possível reler o instalador: {e}")
    if not sha256 or obtido != sha256.lower():
        raise ErroAtualizacao(
            "O instalador mudou depois de conferido e não foi executado.\n"
            f"Esperado: {sha256}\nObtido:   {obtido}")
    try:
        subprocess.Popen([str(caminho), *ARGUMENTOS_INSTALADOR],
                         close_fds=True)
    except OSError as e:
        raise ErroAtualizacao(f"Não foi possível iniciar o instalador: {e}")


def instalado_como_programa() -> bool:
    """Só faz sentido atualizar quem foi instalado pelo instalador."""
    return bool(getattr(sys, "frozen", False))


# ─────────────────────────────────────────
#  POLÍTICA DA ESTAÇÃO
# ─────────────────────────────────────────

#: Onde o administrador da estação desliga a atualização ou fixa a
#: versão. Fica em HKEY_LOCAL_MACHINE, que o usuário comum não grava, e
#: sob `Policies`, que é onde a política de grupo distribui valores.
#:
#:   Atualizar     (DWORD)  0 desliga a consulta e a instalação
#:   VersaoFixada  (texto)  ex.: 1.15.2 — nada acima disso é oferecido
CHAVE_POLITICA = r"SOFTWARE\Policies\SistemaTemis"


@dataclass
class Politica:
    atualizar: bool = True
    versao_fixada: str = ""


def _ler_registro() -> dict:
    """Os valores da chave de política; vazio fora do Windows."""
    if sys.platform != "win32":
        return {}
    try:
        import winreg
    except ImportError:
        return {}
    valores = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE_POLITICA) as k:
            for nome in ("Atualizar", "VersaoFixada"):
                try:
                    valores[nome] = winreg.QueryValueEx(k, nome)[0]
                except OSError:
                    pass
    except OSError:
        pass
    return valores


def politica() -> Politica:
    valores = _ler_registro()
    regra = Politica()
    if "Atualizar" in valores:
        regra.atualizar = str(valores["Atualizar"]).strip() not in ("0", "")
    fixada = str(valores.get("VersaoFixada", "")).strip()
    if versao_valida(fixada):
        regra.versao_fixada = fixada
    return regra


# ─────────────────────────────────────────
#  PREFERÊNCIAS
# ─────────────────────────────────────────

def arquivo_config() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME")
    raiz = Path(base) if base else Path.home() / ".config"
    pasta = raiz / "SistemaTemis"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / "config.json"


@dataclass
class Preferencias:
    verificar: bool = True
    versao_dispensada: str = ""

    def dispensou(self, versao: str) -> bool:
        return bool(versao) and versao == self.versao_dispensada


def ler_preferencias() -> Preferencias:
    try:
        dados = json.loads(arquivo_config().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Preferencias()
    return Preferencias(
        verificar=bool(dados.get("verificar_atualizacoes", True)),
        versao_dispensada=str(dados.get("versao_dispensada", "")),
    )


def gravar_preferencias(p: Preferencias) -> None:
    alvo = arquivo_config()
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "verificar_atualizacoes": p.verificar,
        "versao_dispensada": p.versao_dispensada,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(alvo)
