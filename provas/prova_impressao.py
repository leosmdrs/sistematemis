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


class OTermoEditadoTemOsResumosConferidos(unittest.TestCase):
    """O que se exporta é o que está na tela, e a tela aceita edição."""

    A = "ab12" * 16
    B = "cd34" * 16

    def html(self):
        return (f"<table><tr><td>a.pdf</td><td>{self.A}</td></tr>"
                f"<tr><td>b.pdf</td><td>{self.B}</td></tr></table>"
                f"<p>O arquivo a.pdf tem resumo {self.A}.</p>")

    def plano(self, html):
        doc = QTextDocument()
        doc.setHtml(html)
        return doc.toPlainText()

    def test_texto_como_gerado_nao_acusa(self):
        self.assertEqual(
            impressao.resumos_alterados(self.html(), self.plano(self.html())),
            [])

    def test_ajuste_de_redacao_nao_acusa(self):
        texto = self.plano(self.html()).replace("O arquivo", "O documento")
        self.assertEqual(impressao.resumos_alterados(self.html(), texto), [])

    def test_resumo_quebrado_em_linhas_pela_celula_nao_acusa(self):
        texto = self.plano(self.html()).replace(
            self.B, self.B[:32] + "\n" + self.B[32:])
        self.assertEqual(impressao.resumos_alterados(self.html(), texto), [])

    def test_um_caractere_trocado_e_acusado(self):
        texto = self.plano(self.html()).replace(self.B, "0" + self.B[1:])
        self.assertEqual(impressao.resumos_alterados(self.html(), texto),
                         [self.B])

    def test_trocado_em_so_uma_das_ocorrencias_tambem(self):
        plano = self.plano(self.html())
        onde = plano.index(self.A)
        texto = plano[:onde] + "0" + plano[onde + 1:]
        self.assertEqual(impressao.resumos_alterados(self.html(), texto),
                         [self.A])

    def test_resumo_apagado_e_acusado(self):
        texto = self.plano(self.html()).replace(self.A, "")
        self.assertEqual(impressao.resumos_alterados(self.html(), texto),
                         [self.A])


if __name__ == "__main__":
    unittest.main(verbosity=2)
