"""Provas do monitoramento de downloads na Gravação de Tela.

A Gravação de Tela filma a área de trabalho inteira e não é dona de
navegador algum — ao contrário da Extração Registrada, que instrumenta o
seu próprio navegador. Por isso o que ela pode afirmar sobre um arquivo é
mais estreito, e verdadeiro: **este arquivo apareceu nesta pasta durante
a gravação, e tem este resumo**. Não a origem, não o clique.

Estas provas exercem o monitor de pasta sem gravar tela nem tocar em
FFmpeg: o monitor recebe o instante de fora, e por isso se prova sozinho.
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis.tools import gravacao_core as gc           # noqa: E402


class OMonitorDePasta(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.dir = Path(self.pasta.name)

    def arquivo(self, nome, conteudo=b"conteudo"):
        (self.dir / nome).write_bytes(conteudo)
        return self.dir / nome

    def estabilizar(self, m, decorrido=1.0, base=100.0):
        """Duas passadas com o mesmo tamanho, afastadas além de ESTAVEL."""
        m.varrer(decorrido, base)
        m.varrer(decorrido, base + gc.MonitorDownloads.ESTAVEL + 0.1)

    def test_o_que_ja_existia_nao_e_registrado(self):
        # Não foi esta diligência que o trouxe.
        self.arquivo("antigo.pdf")
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        self.estabilizar(m)
        self.assertEqual(m.baixados, [])

    def test_arquivo_novo_e_resumido_com_sha256(self):
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        self.arquivo("recebido.pdf", b"os bytes recebidos")
        self.estabilizar(m)
        self.assertEqual(len(m.baixados), 1)
        b = m.baixados[0]
        self.assertEqual(b.nome, "recebido.pdf")
        self.assertEqual(len(b.sha256), 64)
        self.assertEqual(b.tamanho, len(b"os bytes recebidos"))
        self.assertFalse(b.erro)

    def test_o_resumo_confere_com_o_conteudo(self):
        import hashlib
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        dados = b"material da diligencia"
        self.arquivo("prova.bin", dados)
        self.estabilizar(m)
        self.assertEqual(m.baixados[0].sha256, hashlib.sha256(dados).hexdigest())

    def test_arquivo_em_transito_nao_entra_ate_terminar(self):
        # O navegador baixa para .crdownload e renomeia ao terminar.
        # Resumir no meio pegaria bytes incompletos.
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        self.arquivo("baixando.crdownload", b"incompleto")
        self.estabilizar(m)
        self.assertEqual(m.baixados, [])

    def test_arquivo_que_cresce_so_e_resumido_quando_estabiliza(self):
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        alvo = self.dir / "crescendo.zip"
        alvo.write_bytes(b"parte 1")
        m.varrer(1.0, 100.0)                       # mede o primeiro tamanho
        alvo.write_bytes(b"parte 1 e parte 2")     # cresceu
        m.varrer(1.5, 100.6)                        # tamanho novo, reinicia
        self.assertEqual(m.baixados, [])
        m.varrer(2.0, 102.0)                        # agora estável
        self.assertEqual(len(m.baixados), 1)
        self.assertEqual(m.baixados[0].tamanho, len(b"parte 1 e parte 2"))

    def test_cada_arquivo_e_resumido_uma_vez_so(self):
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        self.arquivo("uma-vez.pdf")
        self.estabilizar(m)
        for k in range(4):
            m.varrer(3.0, 110.0 + k)
        self.assertEqual(len(m.baixados), 1)

    def test_concluir_da_por_completo_o_que_faltou(self):
        # No fim não se espera mais estabilização: a gravação acabou.
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        self.arquivo("no-fim.pdf", b"chegou perto do fim")
        m.varrer(5.0, 100.0)                       # só mediu, não estabilizou
        self.assertEqual(m.baixados, [])
        m.concluir(6.0, 100.2)
        self.assertEqual(len(m.baixados), 1)

    def test_registra_o_tempo_decorrido_da_gravacao(self):
        m = gc.MonitorDownloads(self.dir)
        m.iniciar()
        self.arquivo("com-tempo.pdf")
        self.estabilizar(m, decorrido=42.0)
        self.assertEqual(m.baixados[0].decorrido, 42.0)


class OTermoRelacionaOsArquivos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def termo_com(self, baixados):
        import re
        r = gc.Resultado(arquivo="video.mp4", inicio="2026-08-27T15:00:00-03:00",
                         fim="2026-08-27T15:10:00-03:00", segundos=600.0,
                         tamanho=1000, sha256="a" * 64, largura=1920,
                         altura=1080, quadros=10, contexto=gc.ler_contexto(),
                         opcoes=gc.Opcoes(), baixados=baixados)
        t = gc.TermoGravacao(nome="Fulano", matricula="1", lotacao="X",
                             numero_processo="123", objeto="teste",
                             registros=[r])
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", gc.build_html(t)))

    def test_sem_downloads_a_secao_nao_aparece(self):
        texto = self.termo_com([])
        self.assertNotIn("Arquivos recebidos durante a diligência", texto)
        # E o método segue numerado como 4, não 5.
        self.assertIn("4. Método", texto)

    def test_com_downloads_a_secao_e_a_ressalva_aparecem(self):
        b = gc.Baixado(nome="relatorio.pdf", sha256="b" * 64, tamanho=2048,
                       quando="2026-08-27T15:03:00-03:00", decorrido=180.0)
        texto = self.termo_com([b])
        self.assertIn("Arquivos recebidos durante a diligência", texto)
        self.assertIn("relatorio.pdf", texto)
        self.assertIn("b" * 64, texto)
        self.assertIn("5. Método", texto)      # empurrou o método para 5
        # A ressalva que separa observar de capturar na origem.
        self.assertIn("monitoramento é de pasta, e não do navegador", texto)
        self.assertIn("Extração Registrada", texto)


class ORegistroDeJanelas(unittest.TestCase):
    """Índice do vídeo, sem capturar conteúdo."""

    def monitor(self, sequencia):
        i = [0]
        def leitor():
            v = sequencia[min(i[0], len(sequencia) - 1)]
            i[0] += 1
            return v
        return gc.MonitorJanelas(leitor=leitor)

    def test_registra_a_troca_de_janela(self):
        m = self.monitor([("chrome.exe", "Portal"), ("notepad.exe", "Notas")])
        m.varrer(1.0)
        m.varrer(2.0)
        self.assertEqual([(j.aplicativo, j.titulo) for j in m.registros],
                         [("chrome.exe", "Portal"), ("notepad.exe", "Notas")])

    def test_janela_repetida_nao_duplica(self):
        m = self.monitor([("chrome.exe", "Portal")])
        for d in (1.0, 2.0, 3.0):
            m.varrer(d)
        self.assertEqual(len(m.registros), 1)

    def test_foco_vazio_e_ignorado(self):
        m = self.monitor([("", "")])
        m.varrer(1.0)
        self.assertEqual(m.registros, [])

    def test_nao_captura_conteudo_so_titulo_e_app(self):
        # O modelo tem exatamente estes campos: quando, decorrido,
        # aplicativo, título. Nada de tecla nem clique.
        campos = set(gc.Janela().__dataclass_fields__)
        self.assertEqual(campos, {"quando", "decorrido", "aplicativo",
                                  "titulo"})

    def test_o_termo_lista_as_janelas_e_a_ressalva(self):
        import os, re
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        j = gc.Janela(quando="2026-08-27T15:01:00-03:00", decorrido=60.0,
                      aplicativo="chrome.exe", titulo="Portal X")
        r = gc.Resultado(arquivo="v.mp4", inicio="2026-08-27T15:00:00-03:00",
                         fim="2026-08-27T15:10:00-03:00", segundos=600,
                         tamanho=1, sha256="a" * 64, largura=1920, altura=1080,
                         quadros=10, contexto=gc.ler_contexto(),
                         opcoes=gc.Opcoes(), janelas=[j])
        termo = gc.TermoGravacao(nome="F", matricula="1", lotacao="X",
                                 numero_processo="1", objeto="t", registros=[r])
        texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                                            gc.build_html(termo)))
        self.assertIn("Janelas em primeiro plano", texto)
        self.assertIn("chrome.exe", texto)
        self.assertIn("Portal X", texto)
        self.assertIn("não captura o que foi digitado", texto)


class AEscolhaDeMonitor(unittest.TestCase):
    """Gravar um monitor, e não os dois — o que se pediu na Extração."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        if gc.ffmpeg_path() is None:
            raise unittest.SkipTest("FFmpeg não está disponível")

    def test_monitor_unico_recorta_a_regiao_dele(self):
        cmd = gc.Gravador("x.mp4", gc.Opcoes(monitor="monitor:0")).comando()
        self.assertIn("-offset_x", cmd)
        self.assertIn("-video_size", cmd)

    def test_todos_os_monitores_nao_recorta(self):
        # "desktop" grava a área inteira; sem região, sem offset.
        cmd = gc.Gravador("x.mp4", gc.Opcoes(monitor="desktop")).comando()
        self.assertNotIn("-offset_x", cmd)
        self.assertNotIn("-video_size", cmd)

    def test_a_lista_de_monitores_traz_a_area_inteira_e_cada_tela(self):
        chaves = [m.chave for m in gc.monitores()]
        self.assertEqual(chaves[0], "desktop")
        self.assertTrue(any(c.startswith("monitor:") for c in chaves))


if __name__ == "__main__":
    unittest.main(verbosity=2)
