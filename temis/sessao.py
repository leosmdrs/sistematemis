"""
A pasta desta sessão de trabalho.

Uma execução do programa é uma sessão, e uma sessão é uma pasta. Tudo o
que as ferramentas geram — vídeos, termos, capturas, arquivos recebidos —
cai aqui por padrão, para que a diligência inteira fique reunida num lugar
só, ao lado do registro encadeado e do relatório em PDF. Reunir assim não
é só arrumação: é o que amarra cada peça ao momento e à sessão em que se
produziu, e reforça a cadeia de custódia de tudo o que saiu dali.

A pasta nasce **tarde**, de propósito: só quando a primeira peça é
efetivamente gravada. Abrir o sistema para uma consulta rápida, ou por
engano, não deixa para trás uma pasta vazia nem um PDF de uma sessão em
que nada se fez. Quem decide que a pasta passou a existir é o primeiro
arquivo que cai nela, não o duplo-clique que abriu o programa.
"""

from __future__ import annotations

import datetime
from pathlib import Path


def raiz_das_sessoes() -> Path:
    """Onde moram as pastas de sessão. Uma subpasta por execução."""
    return Path.home() / "Documents" / "Sistema Têmis" / "Sessões"


def _sessao_de(widget):
    """Acha a sessão subindo pela árvore de widgets a partir de `widget`.

    A ferramenta guarda a sessão em `self.sessao`; os diálogos de termo que
    ela abre têm a ferramenta por ancestral. Subir a árvore acha a sessão a
    partir de qualquer um dos dois, sem precisar passá-la a cada diálogo.
    """
    w = widget
    while w is not None:
        s = getattr(w, "sessao", None)
        if s is not None:
            return s
        w = w.parent() if hasattr(w, "parent") else None
    return None


def destino_para_dialogo(widget, subpasta: str, nome: str,
                         fallback=None) -> str:
    """Caminho a propor num diálogo de salvar, na pasta da sessão.

    Dentro de `subpasta` da pasta da sessão, quando há uma; senão, na pasta
    de sempre da ferramenta (`fallback`), ou em Documentos. A subpasta chega
    a ser criada, para o diálogo abrir já nela — mas subpasta vazia não faz
    a sessão contar como usada: só o arquivo salvo, depois, conta. Cancelar
    o diálogo não deixa rastro.
    """
    sessao = _sessao_de(widget)
    if sessao is not None:
        return str(sessao.garantir(subpasta) / nome)
    base = Path(fallback) if fallback else Path.home() / "Documents"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = Path.home()
    return str(base / nome)


def _nome_legivel(quando: datetime.datetime) -> str:
    """Nome de pasta legível: data e hora por extenso, do próprio início.

    Deriva do mesmo instante que identifica a sessão no registro, para que
    a pasta e o log encadeado que ela guarda concordem na hora — quem
    confere um não precisa adivinhar a correspondência com o outro.
    """
    return quando.strftime("%Y-%m-%d %Hh%Mm%S")


class SessaoTrabalho:
    """A pasta de uma execução do sistema, criada sob demanda.

    O caminho é decidido na abertura, mas o disco só é tocado quando
    alguém pede para gravar de fato (`garantir`). Consultar o caminho para
    preencher um diálogo (`sugestao`) não cria nada — assim, cancelar o
    diálogo ou salvar noutro lugar não deixa pasta órfã.
    """

    def __init__(self, identificador: str = "",
                 quando: datetime.datetime | None = None):
        # Se veio um identificador do registro, a hora da pasta sai dele —
        # não do relógio de agora, que já andou alguns instantes desde a
        # abertura. Assim a pasta e o log encadeado marcam o mesmo minuto.
        if quando is None and identificador:
            try:
                quando = datetime.datetime.strptime(
                    identificador, "%Y-%m-%d-%H%M%S")
            except ValueError:
                quando = None
        quando = quando or datetime.datetime.now().astimezone()
        self.identificador = identificador or quando.strftime(
            "%Y-%m-%d-%H%M%S")
        self._pasta = raiz_das_sessoes() / _nome_legivel(quando)

    # ── caminhos ─────────────────────────────
    @property
    def pasta(self) -> Path:
        """O caminho da pasta da sessão, sem criá-la."""
        return self._pasta

    def sugestao(self, subpasta: str = "", arquivo: str = "") -> Path:
        """Um caminho para propor num diálogo de salvar. Não toca o disco.

        Devolve a pasta (ou um arquivo dentro dela) para preencher o
        diálogo. Nada é criado: se o operador cancelar, ou escolher outro
        lugar, a sessão continua sem pasta.
        """
        alvo = self._pasta / subpasta if subpasta else self._pasta
        return alvo / arquivo if arquivo else alvo

    def garantir(self, subpasta: str = "") -> Path:
        """A pasta (ou uma subpasta dela), criada agora, pronta para gravar.

        É a chamada de quem vai mesmo escrever um arquivo. A partir daqui a
        sessão passa a ter pasta em disco, e o fechamento vai reparar nela.
        """
        alvo = self._pasta / subpasta if subpasta else self._pasta
        alvo.mkdir(parents=True, exist_ok=True)
        return alvo

    # ── estado ───────────────────────────────
    def usada(self) -> bool:
        """Se a sessão produziu alguma peça — há ao menos um arquivo dentro.

        Medido no disco, não por contagem interna: qualquer ferramenta que
        grave na pasta conta, sem precisar avisar ninguém. Conta arquivo,
        não pasta: uma subpasta vazia — criada para propor um destino num
        diálogo que o operador acabou cancelando — não faz a sessão parecer
        usada. É o que decide, no fechamento, entre encerrar com PDF e
        abrir a pasta, ou fechar em silêncio.
        """
        try:
            if not self._pasta.is_dir():
                return False
            return any(p.is_file() for p in self._pasta.rglob("*"))
        except OSError:
            return False
