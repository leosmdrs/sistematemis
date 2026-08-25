"""
Quem opera o sistema.

Nome, matrícula e lotação são pedidos por nove das treze ferramentas, e
até aqui tinham de ser digitados a cada termo. Guardá-los uma vez e
oferecê-los depois poupa a digitação sem tirar nada de ninguém.

A regra é uma só, e é o que separa uma conveniência de uma imposição:
**o perfil só preenche campo vazio.** O que a pessoa escreveu, escreveu;
o que ela apagou, fica apagado enquanto ela estiver ali. Nenhum termo é
assinado por quem o perfil disser — é assinado por quem estiver no campo
no momento de gerar, e esse campo aceita qualquer coisa.

O arquivo é separado do `config.json` das atualizações de propósito:
aquele é reescrito inteiro a cada gravação, e as duas coisas no mesmo
lugar fariam uma apagar a outra.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

#: Os campos de texto que o perfil conhece. A ordem é a da tela.
#:
#: O cargo entrou porque estava fixo em "Policial Rodoviário Federal" no
#: código de sete ferramentas, e o sistema não é só da PRF. O órgão
#: entrou junto: quem assina por outra instituição precisa que a peça
#: diga qual.
CAMPOS = ("nome", "cargo", "matricula", "lotacao", "orgao")

#: Como as ferramentas nomeiam esses campos. Duas convenções convivem no
#: código — `_in_` nas mais antigas, `_e_` nas mais novas —, e o perfil
#: atende às duas em vez de obrigar uma reescrita geral. A conformidade
#: é conferida pelo autoteste, que reprova ferramenta com campo de
#: identificação fora dessas convenções.
PREFIXOS = ("_in_", "_e_")


@dataclass
class Perfil:
    """A identificação guardada. Tudo opcional: nada aqui é obrigatório."""

    nome: str = ""
    cargo: str = ""
    matricula: str = ""
    lotacao: str = ""
    orgao: str = ""

    @property
    def vazio(self) -> bool:
        return not any(getattr(self, c).strip() for c in CAMPOS)

    def resumo(self) -> str:
        """Uma linha para mostrar no portal, ou vazio se não há nada."""
        partes = [" ".join(p for p in (self.cargo.strip(),
                                       self.nome.strip()) if p)]
        if self.matricula.strip():
            partes.append(f"matrícula {self.matricula.strip()}")
        if self.lotacao.strip():
            partes.append(self.lotacao.strip())
        if self.orgao.strip():
            partes.append(self.orgao.strip())
        return " — ".join(p for p in partes if p)


def pasta() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME")
    raiz = Path(base) if base else Path.home() / ".config"
    destino = raiz / "SistemaTemis"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def arquivo() -> Path:
    return pasta() / "perfil.json"


def caminho_brasao() -> Path:
    """Onde fica a cópia do brasão do órgão, se houver.

    Cópia, e não referência ao arquivo escolhido: o original pode ser
    movido, renomeado ou apagado, e um termo que sai sem o brasão porque
    alguém limpou a pasta de downloads seria um defeito difícil de
    entender. A cópia é convertida para PNG e reduzida na hora de
    escolher, de modo que o que está aqui já é o que vai ao documento.
    """
    return pasta() / "brasao.png"


def tem_brasao() -> bool:
    try:
        return caminho_brasao().is_file() and caminho_brasao().stat().st_size > 0
    except OSError:
        return False


def brasao_em_dados() -> str:
    """O brasão como URI de dados, pronto para entrar no HTML.

    Embutido, e não apontado por caminho: o termo é exportado, anexado
    ao processo e aberto noutra máquina. Uma imagem que apontasse para o
    disco desta estação viraria um quadrado vazio do outro lado.
    """
    if not tem_brasao():
        return ""
    try:
        import base64
        dados = caminho_brasao().read_bytes()
    except OSError:
        return ""
    return "data:image/png;base64," + base64.b64encode(dados).decode("ascii")


def dimensoes_brasao() -> tuple[int, int]:
    """Largura e altura do brasão guardado, em pixels. (0, 0) se não há.

    Lidas do cabeçalho do próprio PNG — doze bytes a partir do
    décimo sexto —, e não com a biblioteca gráfica. Quem precisa da
    medida é o montador do documento, que roda também na exportação e
    não deve depender de haver tela.
    """
    if not tem_brasao():
        return (0, 0)
    try:
        with open(caminho_brasao(), "rb") as f:
            cabeca = f.read(24)
    except OSError:
        return (0, 0)
    if len(cabeca) < 24 or cabeca[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    return (int.from_bytes(cabeca[16:20], "big"),
            int.from_bytes(cabeca[20:24], "big"))


def gravar_brasao(dados: bytes) -> None:
    alvo = caminho_brasao()
    tmp = alvo.with_suffix(".tmp")
    tmp.write_bytes(dados)
    tmp.replace(alvo)


def remover_brasao() -> None:
    try:
        caminho_brasao().unlink()
    except OSError:
        pass


def ler() -> Perfil:
    """Lê o perfil guardado. Qualquer defeito no arquivo devolve vazio.

    Perfil ilegível não pode impedir o sistema de abrir: é conveniência,
    não requisito.
    """
    try:
        dados = json.loads(arquivo().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Perfil()
    if not isinstance(dados, dict):
        return Perfil()
    return Perfil(**{c: str(dados.get(c, "") or "").strip() for c in CAMPOS})


def gravar(p: Perfil) -> None:
    """Grava por arquivo temporário: queda no meio não corrompe o antigo."""
    alvo = arquivo()
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({c: getattr(p, c).strip() for c in CAMPOS},
                   ensure_ascii=False, indent=1),
        encoding="utf-8")
    tmp.replace(alvo)


def aplicar(pagina, p: Perfil | None = None) -> list[str]:
    """Oferece o perfil aos campos vazios da ferramenta.

    Devolve os nomes dos campos que preencheu — não por elegância, mas
    para que o autoteste possa conferir que o perfil de fato chega às
    ferramentas, em vez de supor que chega.

    Campo com conteúdo nunca é tocado. É o que garante que a pessoa possa
    apagar e escrever outro nome sem que o sistema desfaça o que ela fez.
    """
    p = ler() if p is None else p
    if p.vazio:
        return []
    preenchidos = []
    for campo in CAMPOS:
        valor = getattr(p, campo).strip()
        if not valor:
            continue
        for prefixo in PREFIXOS:
            widget = getattr(pagina, prefixo + campo, None)
            if widget is None or not hasattr(widget, "setText"):
                continue
            try:
                if widget.text().strip():
                    continue
                widget.setText(valor)
            except (AttributeError, RuntimeError):
                continue
            preenchidos.append(prefixo + campo)
    return preenchidos
