"""Provas da identificação de quem assina.

O perfil guardado na estação é conveniência: preenche os campos para a
pessoa não redigitar. Não pode decidir por ela quem assina — e decidia:
o campo que o operador apagava voltava preenchido na abertura seguinte
da ferramenta, e a Reconstruir Conversa assinava com o perfil sem
mostrá-lo na tela.
"""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit    # noqa: E402

from temis import perfil                               # noqa: E402

_app = QApplication.instance() or QApplication([])


class OCampoApagadoNaoERepreenchido(unittest.TestCase):

    def setUp(self):
        self.pagina = SimpleNamespace(_e_nome=QLineEdit(),
                                      _e_matricula=QLineEdit())
        self.perfil = perfil.Perfil(nome="Fulano de Tal", matricula="123")

    def test_a_primeira_abertura_preenche(self):
        perfil.aplicar(self.pagina, self.perfil)
        self.assertEqual(self.pagina._e_nome.text(), "Fulano de Tal")

    def test_apagado_pelo_operador_fica_apagado(self):
        perfil.aplicar(self.pagina, self.perfil)
        self.pagina._e_nome.clear()                # outra pessoa assina
        perfil.aplicar(self.pagina, self.perfil)   # a ferramenta reabre
        self.assertEqual(self.pagina._e_nome.text(), "")

    def test_guardar_identificacao_nova_alcanca_os_campos_vazios(self):
        perfil.aplicar(self.pagina, self.perfil)
        self.pagina._e_nome.clear()
        novo = perfil.Perfil(nome="Beltrana", matricula="456")
        perfil.aplicar(self.pagina, novo, repetir=True)
        self.assertEqual(self.pagina._e_nome.text(), "Beltrana")
        # e não toca no que tem conteúdo
        self.assertEqual(self.pagina._e_matricula.text(), "123")


class AConversaMostraQuemAssina(unittest.TestCase):

    def test_o_termo_sai_com_o_que_esta_na_tela(self):
        from temis.tools import conversa as tela
        f = tela.ConversaTool()
        self.addCleanup(f.deleteLater)
        for campo in ("_e_nome", "_e_matricula", "_e_lotacao"):
            self.assertTrue(hasattr(f, campo), campo)
        f._e_nome.setText("Quem Assina")
        f._e_matricula.setText("7654321")
        declarante = f._declarante()
        self.assertEqual(declarante.nome, "Quem Assina")
        self.assertEqual(declarante.matricula, "7654321")

    def test_campo_vazio_nao_e_trocado_pelo_perfil_as_escondidas(self):
        from temis.tools import conversa as tela
        original = perfil.ler
        perfil.ler = lambda: perfil.Perfil(nome="Do Perfil", matricula="1")
        self.addCleanup(setattr, perfil, "ler", original)
        f = tela.ConversaTool()
        self.addCleanup(f.deleteLater)
        f._e_nome.clear()
        self.assertEqual(f._declarante().nome, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
