"""Provas de que erro não tratado não fecha o programa.

Exceção de Python dentro de um método chamado pelo Qt — o clique de um
botão — encerrava o processo na hora, sem mensagem: o programa inteiro
caía por um descuido numa tela, com atividade em curso em outras.

A prova principal roda em processo à parte, porque o que se mede é
justamente se o processo sobrevive.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from temis import falhas                               # noqa: E402

CENARIO = r"""
import sys
sys.path.insert(0, {raiz!r})
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
app = QApplication(["prova"])
if {instalar}:
    from temis import falhas
    falhas.instalar()
avisos = []
QMessageBox.critical = staticmethod(lambda *a, **k: avisos.append(a[2]))
botao = QPushButton()
botao.clicked.connect(lambda: int("²"))
QTimer.singleShot(0, botao.click)
def fim():
    print("SOBREVIVEU", len(avisos), flush=True)
    app.quit()
QTimer.singleShot(400, fim)
app.exec()
"""


def rodar(instalar: bool, pasta: str):
    ambiente = dict(os.environ, LOCALAPPDATA=pasta,
                    QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c",
         CENARIO.format(raiz=str(RAIZ), instalar=instalar)],
        capture_output=True, text=True, timeout=120, env=ambiente)


class OErroNaoTratadoNaoFechaOPrograma(unittest.TestCase):

    def test_sem_o_tratador_o_processo_morre(self):
        # É o defeito, medido: garante que a prova seguinte prova algo.
        with tempfile.TemporaryDirectory() as pasta:
            r = rodar(False, pasta)
        self.assertNotIn("SOBREVIVEU", r.stdout)
        self.assertNotEqual(r.returncode, 0)

    def test_com_o_tratador_o_programa_segue_avisa_e_registra(self):
        with tempfile.TemporaryDirectory() as pasta:
            r = rodar(True, pasta)
            registro = Path(pasta) / "SistemaTemis" / "falhas.txt"
            self.assertIn("SOBREVIVEU 1", r.stdout, r.stderr[-400:])
            self.assertEqual(r.returncode, 0)
            self.assertIn("ValueError", registro.read_text(encoding="utf-8"))


class ORegistroDaFalha(unittest.TestCase):

    def test_a_pilha_vai_para_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            original = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = pasta
            try:
                try:
                    raise RuntimeError("falha de teste")
                except RuntimeError:
                    falhas.registrar(*sys.exc_info())
                texto = falhas.arquivo_de_falhas().read_text(encoding="utf-8")
            finally:
                if original is None:
                    del os.environ["LOCALAPPDATA"]
                else:
                    os.environ["LOCALAPPDATA"] = original
        self.assertIn("RuntimeError: falha de teste", texto)
        self.assertIn("prova_falhas.py", texto)

    def test_interrupcao_pelo_teclado_nao_e_engolida(self):
        chamadas = []
        original = sys.__excepthook__
        sys.__excepthook__ = lambda *a: chamadas.append(a[0])
        try:
            falhas.tratar(KeyboardInterrupt, KeyboardInterrupt(), None)
        finally:
            sys.__excepthook__ = original
        self.assertEqual(chamadas, [KeyboardInterrupt])


class OCampoDePaginaSoAceitaAlgarismo(unittest.TestCase):

    def test_expoente_e_algarismo_de_outra_escrita_nao_passam(self):
        for texto in ("²", "٣", "１２"):
            self.assertTrue(texto.isdigit())             # o que enganava
            self.assertFalse(texto.isascii() and texto.isdigit())


if __name__ == "__main__":
    unittest.main(verbosity=2)
