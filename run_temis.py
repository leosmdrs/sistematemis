"""
Ponto de entrada do executável empacotado.

O PyInstaller roda o arquivo de entrada como um script solto, sem pacote
pai — então apontá-lo direto para `temis/__main__.py` quebra todos os
imports relativos ("attempted relative import with no known parent
package"). Este arquivo fica fora do pacote e o importa de forma
absoluta, preservando `python -m temis` para execução a partir do código.
"""

import sys

from temis.__main__ import main


def autoteste() -> int:
    """Confere se o que foi empacotado funciona nesta máquina.

    Existe porque erro de empacotamento — uma biblioteca nativa que ficou
    de fora, um binário que não veio junto — só aparece na estação de quem
    instalou, e na forma de uma janela que não abre. Rodando
    `SistemaTemis.exe --autoteste` num terminal, o problema se identifica
    em segundos, e sem precisar da interface.
    """
    import os
    from pathlib import Path

    from temis import __version__

    # O executável é gráfico, sem console próprio. Chamado de um terminal,
    # ele se prende ao console de quem o chamou; e o relatório vai também
    # para arquivo, que é o que se pede a quem estiver do outro lado do
    # telefone quando nem terminal há.
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        try:
            from ctypes import windll
            if windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8",
                                  errors="replace")
                sys.stderr = sys.stdout
        except Exception:                               # noqa: BLE001
            pass

    linhas = []
    falhas = []

    def anotar(texto):
        linhas.append(texto)
        try:
            print(texto, flush=True)
        except Exception:                               # noqa: BLE001
            pass

    anotar(f"Sistema Têmis {__version__} — autoteste")

    def conferir(rotulo, funcao):
        try:
            detalhe = funcao()
        except Exception as e:                          # noqa: BLE001
            falhas.append(rotulo)
            anotar(f"  FALHA   {rotulo}: {type(e).__name__}: {e}")
        else:
            anotar(f"  ok      {rotulo}"
                   + (f" — {detalhe}" if detalhe else ""))

    def qt():
        from PyQt6.QtWidgets import QApplication             # noqa: F401
        return "Qt disponível"

    def navegador():
        from PyQt6.QtWebEngineCore import QWebEngineProfile  # noqa: F401
        return "QtWebEngine presente (Constatação Web)"

    def ffmpeg():
        from temis.tools.video_core import ffmpeg_path, ffprobe_path
        if ffmpeg_path() is None or ffprobe_path() is None:
            raise RuntimeError("ffmpeg ou ffprobe não encontrados")
        return f"FFmpeg em {ffmpeg_path().parent}"

    def whisper():
        import os

        import ctranslate2
        from faster_whisper import WhisperModel              # noqa: F401
        from faster_whisper.utils import get_assets_path

        # Não basta importar. O detector de voz é um arquivo de modelo
        # que a biblioteca carrega de dentro do próprio pacote, e ele
        # ficou de fora do empacotamento na 1.3.0 — a Degravação
        # importava sem queixa e morria ao transcrever. Conferir o
        # arquivo aqui é o que faz esse erro aparecer no autoteste, e não
        # na mão de quem instalou.
        modelo = os.path.join(get_assets_path(), "silero_vad_v6.onnx")
        if not os.path.isfile(modelo):
            raise RuntimeError(
                f"detector de voz ausente do pacote: {modelo}")
        tamanho = os.path.getsize(modelo) // 1024
        return (f"faster-whisper pronto (CTranslate2 "
                f"{ctranslate2.__version__}), detector de voz {tamanho} KB")

    def diarizacao():
        import sherpa_onnx
        sherpa_onnx.OfflineSpeakerDiarizationConfig          # noqa: B018
        return f"sherpa-onnx {sherpa_onnx.__version__} carregado"

    def documentos():
        import fitz                                          # noqa: F401
        from PIL import Image                                # noqa: F401
        return "PyMuPDF e Pillow presentes"

    def busca():
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
        con.close()
        return f"FTS5 disponível (SQLite {sqlite3.sqlite_version})"

    def ocr():
        from temis.tools import ocr_windows
        if not ocr_windows.disponivel():
            raise RuntimeError(ocr_windows.diagnostico())
        return ocr_windows.diagnostico()

    def espelhamento():
        from temis.tools import espelhamento_core
        if not espelhamento_core.disponivel():
            raise RuntimeError(espelhamento_core.diagnostico())
        return (f"scrcpy e adb em "
                f"{espelhamento_core.adb_path().parent}")

    def ferramentas():
        from temis.tools import REGISTRY
        return f"{len(REGISTRY)} ferramentas registradas"

    def som_do_sistema():
        # Capacidade que depende da placa de som da estação, e não do
        # pacote: numa máquina sem captura de retorno o botão existe e
        # não funciona. O autoteste diz qual é o caso antes de alguém
        # descobrir no meio de uma diligência.
        from temis.tools.audio_sistema import disponivel
        pode, detalhe = disponivel()
        if not pode:
            raise RuntimeError(
                f"esta estação não grava o som do computador: {detalhe}")
        return f"captura de retorno em “{detalhe}”"

    def planilhas():
        # A Análise de Planilha depende de duas bibliotecas que o
        # empacotador não descobre sozinho, porque só entram em cena
        # quando a ferramenta abre ou grava um arquivo. Faltando uma
        # delas, o programa abre normalmente e a falha só apareceria na
        # hora de ler a planilha — no meio do trabalho.
        import pathlib
        from tempfile import TemporaryDirectory

        from temis.tools import planilha_core as pc

        with TemporaryDirectory() as pasta:
            arquivo = pathlib.Path(pasta) / "conferencia.xlsx"
            antes = pc.Tabela(colunas=["a", "b"],
                              linhas=[("01", 2.0), ("03", 4.0)])
            pc.gravar(antes, arquivo)
            depois = pc.carregar(arquivo)
        if depois.resumo() != antes.resumo():
            raise RuntimeError("a planilha gravada não releu igual")
        # O zero à esquerda é o estrago clássico: se a leitura o perdeu,
        # todo CPF e toda placa da análise saem errados.
        if depois.linhas[0][0] != "01":
            raise RuntimeError("o zero à esquerda se perdeu na leitura")
        return "leitura e gravação conferem, com o zero à esquerda intacto"

    def identificacao():
        # O perfil chega às ferramentas por convenção de nome: os campos
        # se chamam `_in_nome`/`_e_nome` e afins, e cada diálogo de termo
        # chama `perfil.aplicar(self)` no fim do construtor. Convenção
        # que ninguém confere é convenção que se perde na ferramenta
        # seguinte — e o sintoma seria mudo: o campo simplesmente não
        # viria preenchido, e ninguém saberia que deveria vir.
        import ast
        import pathlib

        from temis import perfil

        raiz = pathlib.Path(__file__).resolve().parent / "temis" / "tools"
        conhecidos = {p + c for p in perfil.PREFIXOS for c in perfil.CAMPOS}
        faltando, fora_do_padrao = [], []

        def chama_aplicar(classe) -> bool:
            return any(
                isinstance(no, ast.Attribute) and no.attr == "aplicar"
                and isinstance(no.value, ast.Name) and no.value.id == "perfil"
                for no in ast.walk(classe))

        def e_pagina(classe) -> bool:
            # Páginas de ferramenta são atendidas pelo casco, que aplica o
            # perfil a cada abertura; só os diálogos precisam se servir.
            return any(getattr(b, "id", getattr(b, "attr", "")) == "ToolPage"
                       for b in classe.bases)

        for arquivo in sorted(raiz.glob("*.py")):
            if arquivo.name.endswith("_core.py"):
                continue
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if not isinstance(no, ast.ClassDef):
                    continue
                campos = {
                    alvo.attr
                    for atrib in ast.walk(no)
                    if isinstance(atrib, ast.Assign)
                    for alvo in atrib.targets
                    if isinstance(alvo, ast.Attribute)
                    and any(alvo.attr.endswith("_" + c)
                            for c in perfil.CAMPOS)
                }
                if not campos:
                    continue
                estranhos = campos - conhecidos
                if estranhos:
                    fora_do_padrao.append(
                        f"{arquivo.name}:{no.name} {sorted(estranhos)}")
                if not chama_aplicar(no) and not e_pagina(no):
                    faltando.append(f"{arquivo.name}:{no.name}")
        if fora_do_padrao or faltando:
            raise RuntimeError(
                "campos fora da convenção do perfil: "
                f"{fora_do_padrao or 'nenhum'}; sem aplicar o perfil: "
                f"{faltando or 'nenhum'}")
        return "todas as ferramentas aproveitam a identificação guardada"

    def timbre():
        # Toda peça que o sistema emite abre com o mesmo cabeçalho: a
        # marca do Têmis à esquerda, o órgão ao centro e o brasão dele à
        # direita. Ferramenta nova que monte o documento à mão sairia sem
        # ele, e o defeito só apareceria quando alguém comparasse duas
        # peças do mesmo processo lado a lado. Aqui se confere no código.
        import ast
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parent / "temis" / "tools"
        sem_timbre = []
        for arquivo in sorted(raiz.glob("*_core.py")):
            fonte = arquivo.read_text(encoding="utf-8")
            arvore = ast.parse(fonte)
            for no in arvore.body:
                if not isinstance(no, ast.FunctionDef):
                    continue
                if no.name not in ("build_html", "relatorio_html"):
                    continue
                chama = any(
                    isinstance(x, ast.Name) and x.id == "cabecalho_html"
                    for x in ast.walk(no))
                if not chama:
                    sem_timbre.append(f"{arquivo.name}:{no.name}")
        if sem_timbre:
            raise RuntimeError(
                f"peça(s) sem o cabeçalho do sistema: {sem_timbre}")
        return "todas as peças abrem com o mesmo cabeçalho"

    def procedencia():
        # E toda peça fecha declarando com o que foi produzida: versão do
        # sistema, sistema operacional e os motores de que a operação
        # dependeu. Não é enfeite de rodapé — o STJ deixou de presumir a
        # idoneidade da prova digital pela fé pública, e método cuja
        # ferramenta e cuja versão não constam não se reexecuta nem se
        # contesta. Ferramenta nova que monte a peça à mão sairia sem a
        # linha, e ninguém repararia até alguém precisar dela.
        import ast
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parent / "temis" / "tools"
        sem_procedencia = []
        for arquivo in sorted(raiz.glob("*_core.py")):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in arvore.body:
                if not isinstance(no, ast.FunctionDef):
                    continue
                if no.name not in ("build_html", "relatorio_html"):
                    continue
                chama = any(
                    isinstance(x, ast.Name) and x.id == "rodape_html"
                    for x in ast.walk(no))
                if not chama:
                    sem_procedencia.append(f"{arquivo.name}:{no.name}")
        if sem_procedencia:
            raise RuntimeError(
                f"peça(s) sem a linha de procedência: {sem_procedencia}")
        from temis import procedencia as proc
        return ("todas as peças declaram com o que foram produzidas — "
                + proc.sistema())

    def portal():
        # A grade do portal reparte os ladrilhos em fileiras de cinco, e
        # o que cabe ali depende do tamanho do ladrilho, do tamanho da
        # letra e de quantas ferramentas existem. Acrescentar uma
        # ferramenta pode fazer o nome quebrar em mais uma linha e
        # transbordar do ladrilho sem que nada mais quebre — e ninguém
        # repara olhando o código. Aqui se mede: monta-se o portal na
        # menor área prevista e conferem-se os retângulos.
        import os as _os
        _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QLabel

        from temis import theme
        from temis.shell import GradePortal

        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(theme.stylesheet())
        c = GradePortal()
        c.resize(*GradePortal.MINIMO)
        c.show()
        app.processEvents()
        c._reposicionar()
        app.processEvents()
        colisoes = c.sobreposicoes()
        fora = c.transbordo()
        # Nome e frase quebram em linhas, e quantas linhas cada um pede
        # depende da fonte que o Windows entrega. `sizeHint` mente para
        # rótulo que quebra — quem responde é `heightForWidth`.
        cortados = [
            t._meta.name
            for t in c._ladrilhos
            for lb in t.findChildren(QLabel)
            if lb.wordWrap() and lb.heightForWidth(lb.width()) > lb.height()
        ]
        c.close()
        if colisoes or fora or cortados:
            raise RuntimeError(
                f"{len(colisoes)} sobreposição(ões), {len(fora)} ladrilho(s) "
                f"fora da área e {len(cortados)} rótulo(s) cortado(s) na "
                f"menor tela prevista")
        return (f"{len(c._ladrilhos)} ladrilhos em {c._FILEIRAS} fileira(s) de "
                f"{c.COLUNAS}, sem sobreposição nem texto cortado em "
                f"{c.MINIMO[0]}×{c.MINIMO[1]}")

    for rotulo, funcao in (
        ("interface", qt),
        ("navegador embutido", navegador),
        ("ffmpeg empacotado", ffmpeg),
        ("reconhecimento de fala", whisper),
        ("separação de locutores", diarizacao),
        ("leitura de documentos", documentos),
        ("índice de busca", busca),
        ("reconhecimento óptico", ocr),
        ("espelhamento de celular", espelhamento),
        ("registro de ferramentas", ferramentas),
        ("som do computador", som_do_sistema),
        ("leitura de planilhas", planilhas),
        ("identificação do operador", identificacao),
        ("cabeçalho das peças", timbre),
        ("procedência das peças", procedencia),
        ("geometria do portal", portal),
    ):
        conferir(rotulo, funcao)

    anotar("")
    anotar(f"{len(falhas)} verificação(ões) falharam: {', '.join(falhas)}"
           if falhas else "Instalação íntegra.")

    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    destino = Path(base) / "SistemaTemis" / "autoteste.txt"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(chr(10).join(linhas) + chr(10), encoding="utf-8")
        anotar(f"(relatório também gravado em {destino})")
    except OSError:
        pass
    return 1 if falhas else 0


def registrar_quedas():
    """Faz o Python anotar em disco antes de o processo morrer.

    Programa gráfico não tem console: quando ele fecha sozinho, quem
    estava usando vê a janela sumir e mais nada — e o que se perde junto
    é justamente a informação que diria por quê.

    Isto não impede queda alguma; apenas deixa rastro. Cobre também a
    morte por dentro do Qt, que é o caso mais difícil de diagnosticar:
    exceção de Python levantada dentro de um método chamado pelo C++ não
    vira erro, encerra o processo.
    """
    import faulthandler
    import os
    from pathlib import Path

    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        destino = Path(base) / "SistemaTemis" / "quedas.txt"
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Mantido aberto de propósito, pelo tempo do processo: o
        # `faulthandler` escreve nele no instante da queda, quando já não
        # há mais Python para abrir arquivo nenhum.
        registro = open(destino, "a", encoding="utf-8", buffering=1)
        registro.write(f"\n=== sessão iniciada — {__version_para_queda()} ===\n")
        faulthandler.enable(file=registro)
    except Exception:                                       # noqa: BLE001
        pass


def __version_para_queda() -> str:
    import datetime

    from temis import __version__
    return (f"{__version__} — "
            f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(autoteste())
    registrar_quedas()
    sys.exit(main())
