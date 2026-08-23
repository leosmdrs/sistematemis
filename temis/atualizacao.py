"""
Verificação e instalação de atualizações.

Sem dependência de interface, para poder ser testado isolado.

Como funciona: ao abrir, o sistema busca um arquivo `versao.json` num
endereço fixo e compara com a versão instalada. Havendo versão mais nova,
**pergunta ao usuário** — nada é baixado ou instalado sem autorização. Se
ele aceitar, o instalador é baixado, conferido pelo SHA-256 declarado no
manifesto e só então executado.

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
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

#: Endereço do manifesto. O formato `releases/latest/download/` do GitHub
#: sempre aponta para o arquivo da versão mais recente publicada, então o
#: endereço nunca muda a cada lançamento.
#: AJUSTAR antes de publicar: troque `usuario/repositorio` pelo endereço
#: real. Enquanto apontar para um repositório inexistente, a consulta
#: falha em silêncio e o sistema abre normalmente.
REPOSITORIO = "leosmdrs/sistematemis"

URL_MANIFESTO = (f"https://github.com/{REPOSITORIO}"
                 "/releases/latest/download/versao.json")

#: Segundos de espera. Curto de propósito: se a rede não responder, o
#: sistema abre normalmente — atualizar é acessório, trabalhar não é.
TEMPO_LIMITE = 6

#: Identificação enviada ao servidor. Sem versão, sem máquina, sem usuário.
AGENTE = "SistemaTemis-atualizador"

#: Tamanho máximo aceito para o manifesto, para não ler um arquivo enorme
#: caso o endereço passe a servir outra coisa.
LIMITE_MANIFESTO = 64 * 1024


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

    @property
    def valida(self) -> bool:
        return bool(self.versao and self.url and len(self.sha256) == 64)

    @property
    def tamanho_legivel(self) -> str:
        if self.tamanho >= 1 << 20:
            return f"{self.tamanho / (1 << 20):.1f} MB".replace(".", ",")
        if self.tamanho >= 1 << 10:
            return f"{self.tamanho / (1 << 10):.0f} KB"
        return f"{self.tamanho} bytes"


def de_dict(dados: dict) -> Atualizacao:
    return Atualizacao(
        versao=str(dados.get("versao", "")).strip(),
        url=str(dados.get("url", "")).strip(),
        sha256=str(dados.get("sha256", "")).strip().lower(),
        tamanho=int(dados.get("tamanho", 0) or 0),
        notas=str(dados.get("notas", "")).strip(),
        publicado=str(dados.get("publicado", "")).strip(),
        critica=bool(dados.get("critica", False)),
    )


# ─────────────────────────────────────────
#  CONSULTA
# ─────────────────────────────────────────

class ErroAtualizacao(Exception):
    """Falha ao consultar ou baixar — sempre com mensagem em português."""


def _abrir(url: str, tempo: int = TEMPO_LIMITE):
    if not url.lower().startswith("https://"):
        # Sem HTTPS não há como saber de quem veio o arquivo.
        raise ErroAtualizacao("O endereço de atualização precisa ser HTTPS.")
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    return urllib.request.urlopen(pedido, timeout=tempo)


def consultar(url: str = URL_MANIFESTO) -> Atualizacao | None:
    """Lê o manifesto. Devolve None quando não há nada mais novo."""
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
        raise ErroAtualizacao("O manifesto de versão está incompleto.")
    return nova if mais_nova(nova.versao) else None


# ─────────────────────────────────────────
#  DOWNLOAD
# ─────────────────────────────────────────

BLOCO = 256 * 1024


def pasta_download() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMPDIR") or "/tmp"
    destino = Path(base) / "SistemaTemis" / "atualizacoes"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def baixar(info: Atualizacao, progresso=None, cancelado=None) -> Path:
    """Baixa o instalador e confere o SHA-256 antes de devolvê-lo.

    O arquivo só recebe o nome definitivo depois de conferido: assim um
    download interrompido não deixa para trás algo que pareça instalável.
    """
    destino = pasta_download() / f"SistemaTemis-{info.versao}-setup.exe"
    parcial = destino.with_suffix(".parcial")
    digestor = hashlib.sha256()
    baixado = 0

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


def instalar(caminho: Path) -> None:
    """Executa o instalador. Quem chama deve encerrar o programa depois."""
    if not Path(caminho).is_file():
        raise ErroAtualizacao("O instalador baixado não foi encontrado.")
    if sys.platform != "win32":
        raise ErroAtualizacao(
            "A instalação automática só está disponível no Windows.")
    try:
        subprocess.Popen([str(caminho), *ARGUMENTOS_INSTALADOR],
                         close_fds=True)
    except OSError as e:
        raise ErroAtualizacao(f"Não foi possível iniciar o instalador: {e}")


def instalado_como_programa() -> bool:
    """Só faz sentido atualizar quem foi instalado pelo instalador."""
    return bool(getattr(sys, "frozen", False))


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
