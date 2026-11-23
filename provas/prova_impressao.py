"""Provas de que "PDF salvo" só é dito quando há PDF.

O Qt não levanta erro quando não consegue abrir o arquivo de saída: o
desenho acontece no vazio e a chamada volta normalmente. As telas
anunciavam o sucesso, e a peça era dada por juntável sem existir.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QTextDocument                  # noqa: E402
from PyQt6.QtWidgets import QApplication               # noqa: E402

from temis import impressao                            # noqa: E402

_app = QApplication.instance() or QApplication([])


def documento():
    doc = QTextDocument()
    doc.setHtml("<p>Termo de teste</p>")
    return doc


class SoHaSucessoComArquivo(unittest.TestCase):

    def test_gravacao_normal_produz_arquivo_e_nao_reclama(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = str(Path(pasta) / "termo.pdf")
            impressao.imprimir_documento(
                documento(), impressao.preparar_escritor(alvo, "Termo"))
            self.assertGreater(os.path.getsize(alvo), 500)
            self.assertEqual(Path(alvo).read_bytes()[:5], b"%PDF-")

    def test_destino_que_nao_se_abre_vira_erro(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = str(Path(pasta) / "pasta-que-nao-existe" / "termo.pdf")
            with self.assertRaises(OSError):
                impressao.imprimir_documento(
                    documento(), impressao.preparar_escritor(alvo, "Termo"))
            self.assertFalse(Path(alvo).exists())

    def test_a_conferencia_acusa_arquivo_ausente_e_arquivo_vazio(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(OSError):
                impressao.conferir_gravado(Path(pasta) / "nao-ha.pdf")
            vazio = Path(pasta) / "vazio.pdf"
            vazio.write_bytes(b"")
            with self.assertRaises(OSError):
                impressao.conferir_gravado(vazio)
            cheio = Path(pasta) / "cheio.pdf"
            cheio.write_bytes(b"%PDF-1.7")
            impressao.conferir_gravado(cheio)


if __name__ == "__main__":
    unittest.main(verbosity=2)
