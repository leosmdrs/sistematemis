"""Com o que cada peça foi produzida.

O Superior Tribunal de Justiça deixou de presumir a idoneidade da prova
digital pela fé pública de quem a colheu: confiabilidade e integridade
passaram a ser matéria de demonstração, por documentação técnica
objetiva, e o ônus é de quem produziu a prova — não da defesa, a quem
não se pode exigir que aponte a adulteração quando a própria deficiência
técnica impede a verificação.

Uma peça que diz **o que** foi feito e não diz **com o quê** deixa
metade dessa demonstração de fora. Perito da defesa não reexecuta nem
contesta método cuja ferramenta e cuja versão não sabe quais são.

Daí este módulo. Cada ferramenta declara os motores de que dependeu, o
termo os imprime junto da versão do sistema e do sistema operacional, e
o leitor da peça fica sabendo o que precisaria reunir para refazer o
caminho.

As versões são lidas na hora, e não gravadas em constante: constante
mente na primeira atualização de biblioteca, e mentiria justamente na
linha que existe para ser conferida.
"""

from __future__ import annotations

import platform
import sys

from . import __appname__, __version__

#: Rótulo impresso -> como se obtém a versão. Cada função devolve texto
#: vazio quando o motor não está presente, e a linha simplesmente não sai
#: na peça: declarar motor ausente seria afirmar dependência que não
#: houve.
MOTORES: dict[str, str] = {
    "pdf": "PyMuPDF",
    "imagem": "Pillow",
    "video": "FFmpeg",
    "fala": "faster-whisper",
    "locutores": "sherpa-onnx",
    "ocr": "OCR do Windows",
    "planilha": "python-calamine",
    "navegador": "QtWebEngine",
    "espelhamento": "scrcpy",
}


def _do_pacote(nome: str) -> str:
    """A versão que o próprio pacote instalado declara.

    Pela metadata da instalação, e não pelo `__version__` do módulo:
    nem todo pacote expõe o atributo — o python-calamine não expõe — e a
    metadata é a mesma fonte que o pip mostra, que é a que alguém vai
    conferir do outro lado.
    """
    from importlib.metadata import version
    return version(nome)


def _versao_pdf() -> str:
    return _do_pacote("PyMuPDF")


def _versao_imagem() -> str:
    return _do_pacote("Pillow")


def _versao_video() -> str:
    """Só o número, e não a faixa inteira que o FFmpeg imprime.

    A faixa traz compilador, data e a lista de opções de compilação —
    dezenas de linhas numa peça de duas páginas.
    """
    import re

    from .tools import video_core
    achado = re.search(r"ffmpeg version (\S+)", video_core.versao() or "")
    return achado.group(1) if achado else ""


def _versao_fala() -> str:
    return (_do_pacote("faster-whisper")
            + " (CTranslate2 " + _do_pacote("ctranslate2") + ")")


def _versao_locutores() -> str:
    return _do_pacote("sherpa-onnx")


def _versao_ocr() -> str:
    """O idioma, que é o que muda o resultado do reconhecimento.

    O motor é o do próprio Windows e não tem versão própria a informar;
    o idioma tem, e é ele que decide o que a leitura acerta.
    """
    from .tools import ocr_windows
    if not ocr_windows.disponivel():
        return ""
    return ocr_windows.idioma_preferido() or "instalado"


def _versao_planilha() -> str:
    return (_do_pacote("python-calamine")
            + " (openpyxl " + _do_pacote("openpyxl") + ")")


def _versao_navegador() -> str:
    from PyQt6.QtCore import QT_VERSION_STR
    return _do_pacote("PyQt6-WebEngine") + " (Qt " + QT_VERSION_STR + ")"


#: O scrcpy é binário, não pacote: a versão só se obtém perguntando a
#: ele. Guardada na primeira vez — a peça pode ser gerada várias vezes
#: numa sessão, e abrir processo a cada uma é gasto sem retorno.
_SCRCPY: list = []


def _versao_espelhamento() -> str:
    import re
    import subprocess

    if _SCRCPY:
        return _SCRCPY[0]
    from .tools import espelhamento_core
    caminho = espelhamento_core.scrcpy_path()
    if caminho is None:
        return ""
    try:
        r = subprocess.run([str(caminho), "--version"], capture_output=True,
                           text=True, timeout=10,
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
        achado = re.search(r"scrcpy (\S+)", (r.stdout or "") + (r.stderr or ""))
    except Exception:                                   # noqa: BLE001
        achado = None
    _SCRCPY.append(achado.group(1) if achado else "")
    return _SCRCPY[0]


_COMO: dict = {
    "pdf": _versao_pdf,
    "imagem": _versao_imagem,
    "video": _versao_video,
    "fala": _versao_fala,
    "locutores": _versao_locutores,
    "ocr": _versao_ocr,
    "planilha": _versao_planilha,
    "navegador": _versao_navegador,
    "espelhamento": _versao_espelhamento,
}


def sistema() -> str:
    """Nome e versão do próprio programa."""
    return f"{__appname__} {__version__}"


#: O resumo do executável, apurado uma vez. Ler doze megabytes por peça
#: emitida seria gasto sem retorno: o arquivo não muda enquanto o
#: programa está aberto.
_RESUMO_PROGRAMA: list = []


def resumo_do_programa() -> str:
    """O resumo criptográfico do executável que está rodando.

    Declarar a versão diz **qual** programa produziu a peça; declarar o
    resumo diz que é **aquele mesmo** programa, e não uma cópia alterada
    com o mesmo nome e o mesmo número. O Superior Tribunal de Justiça, ao
    tratar da mesmidade pelo hash, exigiu que ela venha acompanhada de
    software confiável e auditável — e software cujo binário não se possa
    conferir não se audita.

    Só existe no programa empacotado. Rodando a partir do código, o
    executável é o interpretador Python, e resumi-lo não diria nada sobre
    o Têmis: nesse caso a peça declara que rodou do código-fonte, que é a
    informação verdadeira disponível.
    """
    if _RESUMO_PROGRAMA:
        return _RESUMO_PROGRAMA[0]
    resumo = ""
    if getattr(sys, "frozen", False):
        try:
            from .tools.hash_core import sha256_file
            resumo = sha256_file(sys.executable)
        except Exception:                               # noqa: BLE001
            resumo = ""
    _RESUMO_PROGRAMA.append(resumo)
    return resumo


def plataforma() -> str:
    """O sistema operacional, como ele se identifica."""
    try:
        if sys.platform == "win32":
            return f"Windows {platform.release()} (build {platform.version()})"
        return f"{platform.system()} {platform.release()}"
    except Exception:                                   # noqa: BLE001
        return ""


def motores(*chaves: str) -> list:
    """[(rótulo, versão)] dos motores pedidos, na ordem em que vieram.

    Motor que não responde fica de fora em silêncio. A peça não deve
    afirmar dependência que não houve, nem deixar de ser emitida porque
    uma biblioteca não soube dizer a própria versão.
    """
    saida = []
    for chave in chaves:
        rotulo = MOTORES.get(chave)
        funcao = _COMO.get(chave)
        if rotulo is None or funcao is None:
            continue
        try:
            versao = (funcao() or "").strip()
        except Exception:                               # noqa: BLE001
            versao = ""
        if versao:
            saida.append((rotulo, versao))
    return saida


def frase(lista: list) -> str:
    """Como a procedência se lê na peça, em uma frase.

    Sai como texto corrido, e não como quadro: é informação de rodapé,
    que precisa estar na peça e não deve competir com o que a peça
    afirma sobre os arquivos.
    """
    partes = [f"{rotulo} {versao}" for rotulo, versao in lista]
    texto = "Peça produzida pelo " + sistema()
    onde = plataforma()
    if onde:
        texto += ", em " + onde
    if len(partes) == 1:
        texto += ", com " + partes[0]
    elif partes:
        # A vírgula do meio e o "e" do fim. Com um motor só, a montagem
        # por fatia deixava um "com ." solto na peça.
        texto += ", com " + ", ".join(partes[:-1]) + " e " + partes[-1]
    texto += (". As versões constam para que o método possa ser "
              "reexecutado e conferido por terceiro.")
    resumo = resumo_do_programa()
    if resumo:
        texto += (" O executável que produziu esta peça tem resumo SHA-256 "
                  + resumo + ".")
    elif getattr(sys, "frozen", False) is False:
        texto += (" Esta peça foi produzida a partir do código-fonte, e não "
                  "de executável empacotado.")
    return texto
