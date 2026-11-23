"""Provas do fechamento do programa com atividade em curso.

Duas garantias. A primeira: perguntar não é encerrar. A janela consulta
cada ferramenta antes de fechar, e qualquer uma pode recusar; a atividade
de quem já respondeu "sim" só termina depois que todas concordaram —
senão o programa seguia aberto com a gravação já encerrada.

A segunda: fechar com o Espelhamento de Celular em curso **conclui** a
sessão e deixa o arquivo na pasta. Chamava-se o cancelamento, que apaga
a gravação da diligência.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from temis.tools import espelhamento as esp            # noqa: E402
from temis.tools import espelhamento_core as esp_core  # noqa: E402
from temis.tools import extracao as ext                # noqa: E402
from temis.tools import gravacao as grav               # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Espelhador:
    def __init__(self):
        self.encerrado = self.cancelado = False

    def encerrar(self, progresso=None, **_):
        self.encerrado = True
        return esp_core.Resultado(arquivo="/pasta/sessao.mp4")

    def cancelar(self):
        self.cancelado = True


class _Gravador:
    gravando = True
    destino = "/pasta/gravacao.mp4"

    def __init__(self):
        self.encerrado = False

    def encerrar(self):
        self.encerrado = True
        from temis.tools import gravacao_core
        return gravacao_core.Resultado(arquivo=self.destino)


class Base(unittest.TestCase):

    def setUp(self):
        self.resposta = QMessageBox.StandardButton.Yes
        self.avisos = []
        for nome in ("question",):
            original = QMessageBox.__dict__.get(nome,
                                                getattr(QMessageBox, nome))
            setattr(QMessageBox, nome,
                    staticmethod(lambda *a, **k: self.resposta))
            self.addCleanup(setattr, QMessageBox, nome, original)
        for nome in ("critical", "warning", "information"):
            original = getattr(QMessageBox, nome)
            setattr(QMessageBox, nome,
                    staticmethod(lambda *a, **k: self.avisos.append(a[2])))
            self.addCleanup(setattr, QMessageBox, nome, original)
        original = esp_core.encerrar_servidor
        esp_core.encerrar_servidor = lambda: None
        self.addCleanup(setattr, esp_core, "encerrar_servidor", original)


class OEspelhamentoEConcluidoENaoApagado(Base):

    def setUp(self):
        super().setUp()
        self.f = esp.EspelhamentoTool()
        self.addCleanup(self.f.deleteLater)
        self.sessao = _Espelhador()
        self.f._espelhador = self.sessao

    def test_fechar_conclui_a_sessao_sem_cancelar(self):
        self.assertTrue(self.f.can_close())
        self.f.shutdown()
        self.assertTrue(self.sessao.encerrado)
        self.assertFalse(self.sessao.cancelado,
                         "o fechamento apagou a gravação")
        self.assertIsNone(self.f._espelhador)

    def test_perguntar_nao_encerra(self):
        self.assertTrue(self.f.can_close())
        self.assertFalse(self.sessao.encerrado)
        self.assertIs(self.f._espelhador, self.sessao)

    def test_recusar_mantem_a_sessao(self):
        self.resposta = QMessageBox.StandardButton.No
        self.assertFalse(self.f.can_close())
        self.assertFalse(self.sessao.encerrado)
        self.assertFalse(self.sessao.cancelado)

    def test_encerramento_ja_em_curso_e_aguardado(self):
        self.f._encerrar()                  # o operador clicou em encerrar
        self.f.shutdown()                   # e fechou a janela em seguida
        self.assertTrue(self.sessao.encerrado)
        self.assertFalse(self.sessao.cancelado)


class PerguntarNaoEncerra(Base):

    def test_gravacao_de_tela(self):
        f = grav.GravacaoTool()
        self.addCleanup(f.deleteLater)
        gravador = _Gravador()
        f._gravador = gravador
        self.assertTrue(f.can_close())
        self.assertFalse(gravador.encerrado)
        f.shutdown()
        self.assertTrue(gravador.encerrado)

    def test_extracao_registrada(self):
        # Sem montar a tela, que traz o navegador embutido: bastam os
        # dois métodos reais sobre o estado de que dependem.
        from types import SimpleNamespace
        from temis.tools import extracao_core
        gravador = _Gravador()
        f = SimpleNamespace(
            _sessao=extracao_core.Sessao(), _gravador=gravador,
            _pulso=SimpleNamespace(stop=lambda: None), _perfil=None,
            _pagina=None, _view=None)
        f._sessao.comecar("x")
        self.assertTrue(ext.ExtracaoTool.can_close(f))
        self.assertTrue(f._sessao.ativa)
        self.assertFalse(gravador.encerrado)
        try:
            ext.ExtracaoTool.shutdown(f)
        except AttributeError:
            pass          # o desmonte do navegador, que aqui não existe
        self.assertFalse(f._sessao.ativa)
        self.assertTrue(gravador.encerrado)
        self.assertEqual(f._sessao.video.arquivo, gravador.destino)


class AAtualizacaoFechaAntesDeInstalar(unittest.TestCase):
    """O instalador só é iniciado depois de o programa aceitar fechar."""

    def janela(self, aceita):
        from types import SimpleNamespace
        from temis import shell
        ordem = []
        ferramenta = SimpleNamespace(
            can_close=lambda: (ordem.append("consulta"), aceita)[1],
            shutdown=lambda: ordem.append("encerra"))
        j = SimpleNamespace(
            _tools={"x": ferramenta}, _registrador=None,
            _depositar_na_sessao=lambda: None)
        for nome in ("_pode_fechar", "_encerrar_tudo",
                     "fechar_para_atualizar"):
            setattr(j, nome, getattr(shell.TemisWindow, nome).__get__(j))
        return j, ordem

    def dialogo(self, janela, ordem):
        from types import SimpleNamespace
        from temis import atualizacao as core
        from temis import atualizacao_ui as ui
        original = core.instalar
        core.instalar = lambda caminho, resumo: ordem.append("instala")
        self.addCleanup(setattr, core, "instalar", original)
        falhas = []
        d = SimpleNamespace(
            parent=lambda: janela, _info=SimpleNamespace(sha256="a" * 64),
            _barra=SimpleNamespace(setValue=lambda v: None),
            _estado=SimpleNamespace(setText=lambda t: None),
            _btn_atualizar=SimpleNamespace(setEnabled=lambda v: None),
            _ao_falhar=falhas.append, _encerrar=lambda: None)
        original_timer = ui.QTimer.singleShot
        ui.QTimer.singleShot = staticmethod(lambda *a: ordem.append("sai"))
        self.addCleanup(setattr, ui.QTimer, "singleShot", original_timer)
        ui.AtualizacaoDialog._ao_baixar(d, "/tmp/setup.exe")
        return falhas

    def test_recusado_o_fechamento_o_instalador_nao_roda(self):
        janela, ordem = self.janela(aceita=False)
        falhas = self.dialogo(janela, ordem)
        self.assertEqual(ordem, ["consulta"])
        self.assertEqual(len(falhas), 1)
        self.assertIn("não foi instalada", falhas[0])

    def test_aceito_o_programa_encerra_e_so_entao_instala(self):
        janela, ordem = self.janela(aceita=True)
        falhas = self.dialogo(janela, ordem)
        self.assertEqual(ordem, ["consulta", "encerra", "instala", "sai"])
        self.assertEqual(falhas, [])

    def test_o_fechamento_seguinte_nao_encerra_duas_vezes(self):
        janela, ordem = self.janela(aceita=True)
        janela.fechar_para_atualizar()
        janela._encerrar_tudo()
        self.assertEqual(ordem.count("encerra"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
