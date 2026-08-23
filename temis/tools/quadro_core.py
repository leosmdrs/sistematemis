"""
Modelo e persistência do Quadro de Evidências.

Sem dependência de interface, para poder ser testado isoladamente.

As imagens ficam como arquivos soltos numa pasta, e não embutidas no JSON.
A versão web guardava tudo em base64 dentro do `localStorage`, cujo limite
de ~5 MB estourava com poucas fotos — e o gravador apenas registrava um
aviso no console, de modo que o quadro era perdido em silêncio.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ─────────────────────────────────────────
#  CORES (herdadas da versão web)
# ─────────────────────────────────────────

#: Vermelho-escuro dos alfinetes e do barbante.
CORDAO = "#8B0000"

NOTA_PADRAO = "#E5C02E"
NOTA_CORES = ["#E5C02E", "#FECACA", "#BFDBFE", "#BBF7D0", "#E9D5FF"]

MARCACAO_PADRAO = "#EF4444"
MARCACAO_CORES = ["#EF4444", "#3B82F6", "#FDE047", "#22C55E"]

#: Opacidade das marcações, que servem para agrupar sem esconder.
MARCACAO_ALPHA = 0.35

FUNDO = "#F8F9FA"
GRADE = "#D1D5DB"
SELECAO = "#3B82F6"

TIPOS = ("nota", "imagem", "marcacao")

TAMANHO_MIN = 40
FONTE_MIN, FONTE_MAX = 10, 48

#: Redimensionamento das imagens ao entrar no quadro.
IMAGEM_LARGURA_MAX = 900


def _novo_id() -> str:
    return uuid.uuid4().hex


# ─────────────────────────────────────────
#  MODELO
# ─────────────────────────────────────────

@dataclass
class Node:
    id: str = field(default_factory=_novo_id)
    tipo: str = "nota"
    x: float = 0.0
    y: float = 0.0
    largura: float = 220.0
    altura: float = 180.0
    texto: str = ""
    cor: str = NOTA_PADRAO
    imagem: str = ""          # nome do arquivo em imagens/
    fonte: int = 14
    z: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Node":
        campos = {f: d[f] for f in Node.__dataclass_fields__ if f in d}
        return Node(**campos)


@dataclass
class Conexao:
    id: str = field(default_factory=_novo_id)
    de: str = ""
    para: str = ""
    cor: str = CORDAO

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Conexao":
        campos = {f: d[f] for f in Conexao.__dataclass_fields__ if f in d}
        return Conexao(**campos)


@dataclass
class Caso:
    id: str = field(default_factory=_novo_id)
    nome: str = "Novo caso"
    nodes: list[Node] = field(default_factory=list)
    conexoes: list[Conexao] = field(default_factory=list)
    atualizado: float = field(default_factory=time.time)

    # ── consultas ────────────────────────────────
    def node(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    # As marcações servem para agrupar áreas e vivem numa faixa de
    # profundidade negativa, sempre atrás do conteúdo. Sem faixas
    # separadas, uma marcação criada depois cobriria as anotações.
    def topo_z(self) -> int:
        return max((n.z for n in self.nodes if n.tipo != "marcacao"), default=0)

    def fundo_z(self) -> int:
        return min((n.z for n in self.nodes if n.tipo == "marcacao"), default=0)

    def conexoes_de(self, node_id: str) -> list[Conexao]:
        return [c for c in self.conexoes if node_id in (c.de, c.para)]

    # ── alterações ───────────────────────────────
    def adicionar(self, node: Node) -> Node:
        node.z = (self.fundo_z() - 1 if node.tipo == "marcacao"
                  else self.topo_z() + 1)
        self.nodes.append(node)
        return node

    def remover(self, node_id: str):
        """Remove o nó e, junto, os vínculos que dependiam dele.

        Deixar as conexões órfãs produziria barbantes ligados ao nada na
        próxima abertura do caso.
        """
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.conexoes = [c for c in self.conexoes
                         if node_id not in (c.de, c.para)]

    def conectar(self, de: str, para: str) -> Conexao | None:
        """Cria o vínculo, ignorando laços e duplicatas."""
        if de == para or not self.node(de) or not self.node(para):
            return None
        existe = any(
            {c.de, c.para} == {de, para} for c in self.conexoes
        )
        if existe:
            return None
        c = Conexao(de=de, para=para)
        self.conexoes.append(c)
        return c

    def desconectar(self, conexao_id: str):
        self.conexoes = [c for c in self.conexoes if c.id != conexao_id]

    # ── profundidade ─────────────────────────────
    def ordem(self) -> list[Node]:
        """Itens do fundo para a frente."""
        return sorted(self.nodes, key=lambda n: n.z)

    def _reindexar(self, ordenados: list[Node]):
        """Renumera z de 0..n-1, mantendo a ordem recebida.

        Sem renumerar, empurrões sucessivos afastariam os valores de z
        indefinidamente e a ordem viraria um emaranhado difícil de depurar.
        """
        for i, n in enumerate(ordenados):
            n.z = i

    def mover_profundidade(self, node_id: str, destino) -> bool:
        """Reordena o item. `destino`: -1, +1, "fundo" ou "topo".

        Opera sobre a pilha inteira, e não dentro de faixas por tipo: a
        hierarquia é escolha do usuário, e restringi-la impediria, por
        exemplo, deixar uma marcação por cima de uma anotação.
        """
        ordenados = self.ordem()
        alvo = self.node(node_id)
        if alvo is None or len(ordenados) < 2:
            return False

        i = ordenados.index(alvo)
        if destino == "topo":
            j = len(ordenados) - 1
        elif destino == "fundo":
            j = 0
        else:
            j = i + int(destino)
        j = max(0, min(len(ordenados) - 1, j))
        if j == i:
            return False

        ordenados.insert(j, ordenados.pop(i))
        self._reindexar(ordenados)
        return True

    def clonar(self) -> "Caso":
        """Cópia independente, para a pilha de desfazer."""
        return Caso.from_dict(self.to_dict())

    def limpar(self):
        self.nodes = []
        self.conexoes = []

    # ── serialização ─────────────────────────────
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "nodes": [n.to_dict() for n in self.nodes],
            "conexoes": [c.to_dict() for c in self.conexoes],
            "atualizado": self.atualizado,
        }

    @staticmethod
    def from_dict(d: dict) -> "Caso":
        return Caso(
            id=d.get("id") or _novo_id(),
            nome=d.get("nome", "Novo caso"),
            nodes=[Node.from_dict(n) for n in d.get("nodes", [])],
            conexoes=[Conexao.from_dict(c) for c in d.get("conexoes", [])],
            atualizado=d.get("atualizado", time.time()),
        )


# ─────────────────────────────────────────
#  ARMAZENAMENTO
# ─────────────────────────────────────────

def pasta_dados() -> Path:
    """Pasta de dados do usuário, por sistema operacional."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    raiz = Path(base) if base else Path.home() / ".local" / "share"
    return raiz / "SistemaTemis" / "quadro"


class Acervo:
    """Casos gravados em disco: um JSON de índice e uma pasta de imagens."""

    ARQUIVO = "casos.json"
    IMAGENS = "imagens"

    def __init__(self, raiz: Path | None = None):
        self.raiz = Path(raiz) if raiz else pasta_dados()
        self.raiz.mkdir(parents=True, exist_ok=True)
        (self.raiz / self.IMAGENS).mkdir(exist_ok=True)

    # ── casos ────────────────────────────────────
    def carregar(self) -> tuple[list[Caso], str]:
        arq = self.raiz / self.ARQUIVO
        if not arq.exists():
            caso = Caso(nome="Dê um nome ao caso")
            return [caso], caso.id
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
            casos = [Caso.from_dict(c) for c in dados.get("casos", [])]
        except (json.JSONDecodeError, OSError, TypeError):
            casos = []
        if not casos:
            caso = Caso(nome="Dê um nome ao caso")
            return [caso], caso.id
        atual = dados.get("atual") if isinstance(dados, dict) else None
        if atual not in [c.id for c in casos]:
            atual = casos[0].id
        return casos, atual

    def gravar(self, casos: list[Caso], atual: str):
        # Grava num temporário e só então substitui: um desligamento no
        # meio da escrita deixaria o arquivo truncado e perderia todos os
        # casos, não apenas o que estava sendo salvo.
        alvo = self.raiz / self.ARQUIVO
        tmp = alvo.with_suffix(".tmp")
        payload = {"casos": [c.to_dict() for c in casos], "atual": atual}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(alvo)

    # ── imagens ──────────────────────────────────
    def guardar_imagem(self, origem: str | Path) -> str:
        """Copia a imagem para o acervo e devolve o nome interno."""
        origem = Path(origem)
        nome = f"{_novo_id()}{origem.suffix.lower() or '.png'}"
        shutil.copy2(origem, self.raiz / self.IMAGENS / nome)
        return nome

    def guardar_bytes(self, dados: bytes, sufixo: str = ".png") -> str:
        nome = f"{_novo_id()}{sufixo}"
        (self.raiz / self.IMAGENS / nome).write_bytes(dados)
        return nome

    def caminho_imagem(self, nome: str) -> Path:
        return self.raiz / self.IMAGENS / nome

    def limpar_imagens_orfas(self, casos: list[Caso]) -> int:
        """Apaga imagens que nenhum caso referencia mais."""
        usadas = {n.imagem for c in casos for n in c.nodes if n.imagem}
        removidas = 0
        for arq in (self.raiz / self.IMAGENS).iterdir():
            if arq.is_file() and arq.name not in usadas:
                arq.unlink(missing_ok=True)
                removidas += 1
        return removidas
