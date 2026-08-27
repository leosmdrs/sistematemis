"""Provas dos avisos de registro da sessão, na abertura e no fecho.

São modais — não se pode clicar neles numa prova sem tela. O que se prova
aqui é o que importa e o que quebraria calado: que eles se montam sem
erro, e que o aviso de encerramento **não impede a janela de fechar**,
mesmo se algo nele falhar. Um aviso que travasse o fechamento seria pior
do que aviso nenhum.

O `exec` é neutralizado: o que se exercita é a montagem e o fluxo do
closeEvent, não a espera pelo clique.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox      # noqa: E402
from PyQt6.QtGui import QCloseEvent                        # noqa: E402


class OsAvisosDaSessao(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Nenhum modal espera clique durante a prova.
        self._exec_original = QMessageBox.exec
        QMessageBox.exec = lambda self: 0
        self.addCleanup(lambda: setattr(QMessageBox, "exec",
                                        self._exec_original))
        from temis.shell import TemisWindow
        self.win = TemisWindow()
        self.addCleanup(self.win.deleteLater)

    def test_o_aviso_de_abertura_se_monta_sem_erro(self):
        # Se o registrador subiu, o aviso existe e não estoura.
        self.win._avisar_registro_abertura()

    def test_o_aviso_dispara_uma_vez_ao_exibir(self):
        # Antes de exibir, não disparou; exibindo, marca; e não remarca.
        self.assertFalse(self.win._avisou_abertura)
        self.win.show()
        self.assertTrue(self.win._avisou_abertura)
        self.win.hide()
        self.win.show()
        self.assertTrue(self.win._avisou_abertura)

    def test_o_flag_existe_mesmo_sem_registrador(self):
        # O bug que a prova achou: sem registrador, showEvent não pode
        # encontrar o flag indefinido.
        self.assertTrue(hasattr(self.win, "_avisou_abertura"))

    def test_a_recomendacao_de_fecho_se_monta_com_e_sem_caminho(self):
        self.win._recomendar_juntar_registro(None)
        self.win._recomendar_juntar_registro(
            Path.home() / "relatorio.pdf")

    def test_fechar_a_janela_nao_e_impedido_pelo_aviso(self):
        # O caso que não pode falhar: o closeEvent tem de aceitar o
        # fechamento mesmo com o aviso no caminho.
        ev = QCloseEvent()
        self.win.closeEvent(ev)
        self.assertTrue(ev.isAccepted())

    def test_fechar_nao_quebra_se_o_aviso_falhar(self):
        # Aviso é acessório; falha nele não pode segurar o sistema aberto.
        def estoura(*_a, **_k):
            raise RuntimeError("falha simulada no aviso")
        self.win._recomendar_juntar_registro = estoura
        ev = QCloseEvent()
        try:
            self.win.closeEvent(ev)
        except RuntimeError:
            self.fail("o aviso derrubou o fechamento")


if __name__ == "__main__":
    unittest.main(verbosity=2)
