"""Provas do que o aviso de fechamento afirma sobre o registro.

Ao fechar, o programa dizia "A sessão foi registrada" e que a pasta da
sessão levava "o registro encadeado" — sem conferir nada. Com a pasta de
Documentos sem permissão de escrita nada era gravado e o aviso se
repetia; no caso normal, a pasta entregue para os autos não levava o
arquivo com os elos, de modo que a corrente não podia ser reconferida a
partir dela.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication               # noqa: E402

from temis import shell                                # noqa: E402
from temis.tools import atividades_core as ac          # noqa: E402

_app = QApplication.instance() or QApplication([])


class Base(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        raiz = Path(self._dir.name)
        self.registrador = ac.Registrador(raiz / "registro")
        self.registrador.iniciar()
        self.registrador.anotar("Tarja Preta", "Documento salvo")
        self.pasta = raiz / "sessao"
        self.janela = SimpleNamespace(
            _registrador=self.registrador,
            _sessao_trabalho=SimpleNamespace(
                usada=lambda: True, pasta=self.pasta,
                garantir=lambda: (self.pasta.mkdir(exist_ok=True),
                                  self.pasta)[1]))

    def depositar(self):
        return shell.TemisWindow._depositar_na_sessao(self.janela)

    def situacao(self, destino=None, pasta=None):
        return shell.TemisWindow._situacao_do_registro(
            self.janela, destino, pasta)


class APastaDaSessaoLevaACorrente(Base):

    def test_o_arquivo_encadeado_vai_para_a_pasta_e_confere(self):
        destino = self.registrador.encerrar()
        pasta = self.depositar()
        encadeados = list(pasta.glob("registro-da-sessao-*.json"))
        self.assertEqual(len(encadeados), 1)
        relida = ac.ler_sessao(encadeados[0])
        self.assertEqual(ac.conferir(relida)[0], "integro")
        self.assertEqual(len(list(pasta.glob("*.pdf"))), 1)
        gravado, titulo, corpo = self.situacao(destino, pasta)
        self.assertTrue(gravado)
        self.assertIn(encadeados[0].name, corpo)

    def test_o_que_nao_se_gravou_na_pasta_e_nomeado(self):
        self.registrador.encerrar()
        self.pasta.mkdir()
        # Um diretório no lugar do arquivo: gravar ali falha.
        nome = f"registro-da-sessao-{self.registrador.sessao.identificador}"
        (self.pasta / f"{nome}.html").mkdir()
        pasta = self.depositar()
        self.assertIn(f"{nome}.html", self.janela._nao_depositados)
        _g, _t, corpo = self.situacao(None, pasta)
        self.assertIn("Não foi possível gravar na pasta", corpo)
        self.assertIn(f"{nome}.html", corpo)


class SemGravacaoNaoSeAfirmaRegistro(Base):

    def test_registro_que_nao_foi_para_o_disco_e_dito_como_tal(self):
        self.registrador.encerrar()
        self.registrador.caminho_dados().unlink()
        self.registrador.sessao.erros.append(
            "gravação: PermissionError: acesso negado")
        gravado, titulo, corpo = self.situacao()
        self.assertFalse(gravado)
        self.assertIn("não foi gravado", titulo)
        self.assertNotIn("foi registrada", titulo)
        self.assertIn("acesso negado", corpo)

    def test_registro_gravado_segue_com_a_recomendacao(self):
        destino = self.registrador.encerrar()
        gravado, titulo, corpo = self.situacao(destino)
        self.assertTrue(gravado)
        self.assertIn("foi registrada", titulo)
        self.assertIn(str(destino), corpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
