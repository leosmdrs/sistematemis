"""Executa o código injetado da Extração Registrada num navegador real.

Roda em processo à parte, chamado por `prova_extracao_sigilo.py`: o motor
do navegador embutido precisa ser o primeiro a iniciar a aplicação Qt, e
numa rodada com as demais provas outra já a teria iniciado.

Entrada (JSON, pela entrada padrão): a página, o código a injetar e a
lista de gestos, cada um um trecho de JavaScript. Saída (JSON): para cada
gesto, as mensagens que ele fez aparecer no console.
"""

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                      "--no-sandbox --disable-gpu")


def main() -> int:
    pedido = json.load(sys.stdin)

    from PyQt6.QtCore import QEventLoop, QTimer, QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWidgets import QApplication

    app = QApplication(["prova"])
    mensagens = []

    class Pagina(QWebEnginePage):
        def javaScriptConsoleMessage(self, nivel, mensagem, linha, fonte):
            mensagens.append(mensagem)

    pagina = Pagina()

    def esperar(ms):
        laco = QEventLoop()
        QTimer.singleShot(ms, laco.quit)
        laco.exec()

    def rodar(codigo):
        laco = QEventLoop()
        pagina.runJavaScript(codigo + "; 0", lambda _r: laco.quit())
        QTimer.singleShot(5000, laco.quit)
        laco.exec()
        esperar(150)

    laco = QEventLoop()
    carregou = []
    pagina.loadFinished.connect(lambda ok: (carregou.append(ok), laco.quit()))
    QTimer.singleShot(30000, laco.quit)
    pagina.setHtml(pedido["pagina"], QUrl("https://exemplo.test/"))
    laco.exec()
    if not carregou:
        return 3

    rodar(pedido["codigo"])
    saida = []
    for gesto in pedido["gestos"]:
        mensagens.clear()
        rodar(gesto)
        saida.append(list(mensagens))

    sys.stdout.write("\nRESULTADO " + json.dumps(saida) + "\n")
    sys.stdout.flush()
    del pagina
    return 0


if __name__ == "__main__":
    # Sai sem desmontar a aplicação: o encerramento do motor trava em
    # máquina sem tela, e o resultado já foi entregue.
    codigo = main()
    os._exit(codigo)
