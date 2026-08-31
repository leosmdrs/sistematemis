"""Provas da pasta de sessão.

Uma execução do sistema é uma sessão, e uma sessão é uma pasta. O que dá
segurança a isso, e o que estas provas cuidam: a pasta nasce só quando
algo é gravado; propor um caminho num diálogo não cria nada; e o sistema
sabe, no fim, distinguir uma sessão que produziu peças de uma que não
produziu — que é o que decide entre encerrar com PDF e abrir a pasta, ou
fechar em silêncio.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis import sessao as ss                            # noqa: E402


class APastaNasceTarde(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name) / "Sessões"
        self._orig = ss.raiz_das_sessoes
        ss.raiz_das_sessoes = lambda: base
        self.addCleanup(setattr, ss, "raiz_das_sessoes", self._orig)
        self.s = ss.SessaoTrabalho("2026-08-29-143012")

    def test_construir_nao_cria_pasta(self):
        self.assertFalse(self.s.pasta.exists())
        self.assertFalse(self.s.usada())

    def test_sugestao_nao_toca_o_disco(self):
        p = self.s.sugestao("Vídeos", "captura.mp4")
        self.assertEqual(p.name, "captura.mp4")
        self.assertEqual(p.parent.name, "Vídeos")
        self.assertFalse(p.parent.exists())
        self.assertFalse(self.s.pasta.exists())
        self.assertFalse(self.s.usada())

    def test_garantir_cria_a_subpasta(self):
        p = self.s.garantir("Vídeos")
        self.assertTrue(p.is_dir())
        self.assertEqual(p.name, "Vídeos")

    def test_subpasta_vazia_nao_conta_como_usada(self):
        # pré-criar a subpasta para um diálogo, e o operador cancelar,
        # não pode fazer a sessão parecer usada
        self.s.garantir("Vídeos")
        self.assertFalse(self.s.usada())

    def test_um_arquivo_salvo_marca_a_sessao(self):
        pasta = self.s.garantir("Vídeos")
        (pasta / "diligencia.mp4").write_bytes(b"\x00\x00")
        self.assertTrue(self.s.usada())

    def test_a_pasta_fica_sob_sessoes(self):
        self.assertEqual(self.s.pasta.parent.name, "Sessões")

    def test_o_nome_da_pasta_vem_do_identificador(self):
        # a hora da pasta sai do identificador, não do relógio de agora
        self.assertEqual(self.s.pasta.name, "2026-08-29 14h30m12")
        self.assertEqual(self.s.identificador, "2026-08-29-143012")


class OIdentificadorProprioQuandoNaoVeioDoRegistro(unittest.TestCase):

    def test_sem_identificador_gera_um_e_a_pasta_combina(self):
        import datetime
        quando = datetime.datetime(2026, 1, 2, 9, 8, 7)
        s = ss.SessaoTrabalho(quando=quando)
        self.assertEqual(s.identificador, "2026-01-02-090807")
        self.assertEqual(s.pasta.name, "2026-01-02 09h08m07")


class ODestinoSobeAteAFerramenta(unittest.TestCase):
    """Um diálogo de termo acha a sessão da ferramenta que o abriu.

    Os termos são salvos em diálogos, não na própria ferramenta. Como o
    diálogo tem a ferramenta por ancestral, subir a árvore de widgets acha
    a sessão a partir de qualquer um dos dois — é o que faz o destino
    proposto cair na pasta da sessão sem precisar passá-la a cada diálogo.
    """

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name) / "Sessões"
        self._orig = ss.raiz_das_sessoes
        ss.raiz_das_sessoes = lambda: base
        self.addCleanup(setattr, ss, "raiz_das_sessoes", self._orig)

    def test_dialogo_filho_acha_a_sessao_e_cai_na_pasta(self):
        from PyQt6.QtWidgets import QWidget
        ferramenta = QWidget()
        ferramenta.sessao = ss.SessaoTrabalho("2026-08-29-101112")
        dialogo = QWidget(ferramenta)      # o termo, filho da ferramenta
        destino = ss.destino_para_dialogo(dialogo, "Termos", "termo.pdf")
        self.assertTrue(destino.startswith(str(ferramenta.sessao.pasta)))
        self.assertIn("Termos", destino)
        self.assertTrue(destino.endswith("termo.pdf"))

    def test_sem_sessao_cai_no_fallback(self):
        from PyQt6.QtWidgets import QWidget
        w = QWidget()                      # nenhuma sessão na árvore
        fb = Path(self.tmp.name) / "de-sempre"
        destino = ss.destino_para_dialogo(w, "Termos", "x.pdf", fallback=fb)
        self.assertTrue(destino.startswith(str(fb)))
        self.assertTrue(destino.endswith("x.pdf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
