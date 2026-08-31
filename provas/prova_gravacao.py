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

    def test_a_leitura_real_do_foco_nao_estoura(self):
        # A prova que faltava: as demais injetam um leitor de mentira, e
        # por isso não pegaram que a função real referenciava um "sys" não
        # importado — o que abortava o processo pela mão do PyQt no timer.
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        r = gc.janela_em_foco()
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 2)

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


class ACapturaDeTela(unittest.TestCase):
    """Captura documentada — o botão de printscreen com hash e hora."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_a_captura_carrega_hora_e_um_lugar_para_o_resumo(self):
        # O modelo tem os campos que documentam a prova.
        campos = set(gc.Captura().__dataclass_fields__)
        for c in ("nome", "caminho", "sha256", "quando", "tamanho",
                  "monitor", "decorrido"):
            self.assertIn(c, campos)

    def test_falha_ao_capturar_vira_erro_e_nao_queda(self):
        # No motor offscreen não há tela a fotografar: a captura devolve
        # erro em vez de derrubar a diligência.
        import tempfile
        c = gc.capturar_tela(tempfile.mkdtemp(), 1, "monitor:0", 12.0)
        self.assertTrue(c.erro or c.sha256)   # ou capturou, ou registrou o erro
        self.assertEqual(c.nome, "captura-001.png")

    def test_o_termo_relaciona_as_capturas_com_hash(self):
        import re
        cap = gc.Captura(nome="captura-002.png", sha256="d" * 64,
                         tamanho=1024, quando="27/08/2026 às 15:00:00",
                         decorrido=90.0)
        r = gc.Resultado(arquivo="v.mp4", inicio="2026-08-27T15:00:00-03:00",
                         fim="2026-08-27T15:10:00-03:00", segundos=600,
                         tamanho=1, sha256="e" * 64, largura=1920, altura=1080,
                         quadros=10, contexto=gc.ler_contexto(),
                         opcoes=gc.Opcoes())
        termo = gc.TermoGravacao(nome="F", matricula="1", lotacao="X",
                                 numero_processo="1", objeto="t",
                                 registros=[r], capturas=[cap])
        texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                                            gc.build_html(termo)))
        self.assertIn("Capturas de tela", texto)
        self.assertIn("captura-002.png", texto)
        self.assertIn("d" * 64, texto)
        self.assertIn("decorrido 00:01:30", texto)

    def test_sem_captura_a_secao_nao_aparece(self):
        import re
        r = gc.Resultado(arquivo="v.mp4", inicio="2026-08-27T15:00:00-03:00",
                         fim="2026-08-27T15:10:00-03:00", segundos=600,
                         tamanho=1, sha256="e" * 64, largura=1920, altura=1080,
                         quadros=10, contexto=gc.ler_contexto(),
                         opcoes=gc.Opcoes())
        termo = gc.TermoGravacao(nome="F", matricula="1", lotacao="X",
                                 numero_processo="1", objeto="t",
                                 registros=[r])
        texto = re.sub(r"<[^>]+>", " ", gc.build_html(termo))
        self.assertNotIn("Capturas de tela", texto)


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


class OPainelFlutuanteCabeTodosOsBotoes(unittest.TestCase):
    """A janelinha que fica sobre tudo não pode cortar botão.

    O painel tinha largura fixa; quando ganhou o botão de captura, o
    rótulo saiu cortado. Agora a largura acompanha o conteúdo — esta
    prova trava isso, para o corte não voltar sem ninguém perceber.
    """

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_a_largura_comporta_capturar_e_encerrar_inteiros(self):
        from PyQt6.QtWidgets import QPushButton
        from temis.tools.gravacao import PainelGravando
        painel = PainelGravando()
        try:
            painel.mostrar()          # é aqui que a largura se ajusta
            botoes = painel.findChildren(QPushButton)
            self.assertEqual(len(botoes), 2)
            # nenhum botão fica menor do que pede para caber inteiro
            preciso = sum(b.sizeHint().width() for b in botoes)
            self.assertGreaterEqual(painel.width(), preciso)
            # e a largura cobre tudo o que o layout pede
            self.assertGreaterEqual(
                painel.width(), painel.layout().sizeHint().width())
        finally:
            painel.esconder()

    def test_a_altura_continua_travada(self):
        from temis.tools.gravacao import PainelGravando
        painel = PainelGravando()
        try:
            painel.mostrar()
            self.assertEqual(painel.height(), 56)
        finally:
            painel.esconder()


class OFilhoNaoSobreviveAoPai(unittest.TestCase):
    """O FFmpeg (e o scrcpy) não podem seguir vivos se o Têmis cai.

    O `shutdown` encerra tudo num fechamento limpo. A rede de segurança,
    para quando o programa cai de repente, é o Job Object: o sistema
    operacional mata os filhos atados quando o processo-pai deixa de
    existir. Sem isto, o FFmpeg seguia capturando a tela sozinho — o
    cursor piscava como se ainda houvesse gravação, e o disco enchia.
    """

    @unittest.skipUnless(sys.platform == "win32", "Job Object é do Windows")
    def test_o_job_object_se_cria(self):
        # Se a estrutura ou as flags estivessem erradas (o handle de 64
        # bits truncado, um campo fora de tamanho), isto devolveria None.
        from temis.tools import video_core as vc
        self.assertTrue(vc._garantir_job())

    @unittest.skipUnless(sys.platform == "win32", "Job Object é do Windows")
    def test_filho_atado_morre_quando_o_pai_e_morto(self):
        import os
        import subprocess
        raiz = str(Path(__file__).resolve().parents[1])
        # Carrega o video_core isolado, por caminho: importar o pacote
        # temis.tools puxaria as 16 ferramentas (Qt, whisper…) e o processo
        # levaria muito para subir. O que se quer aqui é só o Job Object.
        codigo = (
            "import importlib.util, os, subprocess, sys, time\n"
            "alvo = os.path.join(os.environ['TEMIS_RAIZ'],\n"
            "                    'temis', 'tools', 'video_core.py')\n"
            "spec = importlib.util.spec_from_file_location('vc', alvo)\n"
            "vc = importlib.util.module_from_spec(spec)\n"
            "sys.modules['vc'] = vc\n"
            "spec.loader.exec_module(vc)\n"
            "filho = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],\n"
            "                         creationflags=vc._SEM_JANELA)\n"
            "ok = vc.atar_ao_encerramento(filho)\n"
            "print(f'{os.getpid()} {filho.pid} {int(ok)}', flush=True)\n"
            "time.sleep(30)\n")
        env = dict(os.environ, TEMIS_RAIZ=raiz)

        def vivo(pid):
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                               capture_output=True, text=True)
            return str(pid) in r.stdout

        pai = subprocess.Popen([sys.executable, "-c", codigo], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
        pid_filho = None
        try:
            # readline não bloqueia: o pai imprime e dá descarga na hora.
            # A leitura de stderr fica só no ramo de falha, e depois de
            # matar o pai — nunca com ele vivo, senão o read trava até os
            # 30 s acabarem.
            linha = pai.stdout.readline().split()
            if len(linha) != 3:
                pai.kill()
                self.fail("o pai não subiu: " + pai.stderr.read()[:500])
            pid_pai, pid_filho, ok = int(linha[0]), int(linha[1]), linha[2]
            self.assertEqual(ok, "1", "não atou o filho ao job")
            self.assertTrue(vivo(pid_filho), "o filho nem chegou a subir")

            # mata só o pai, à força — é o que uma queda faz
            subprocess.run(["taskkill", "/PID", str(pid_pai), "/F"],
                           capture_output=True)
            morreu = False
            for _ in range(40):
                time.sleep(0.25)
                if not vivo(pid_filho):
                    morreu = True
                    break
            self.assertTrue(
                morreu, "o filho sobreviveu ao pai — Job Object falhou")
        finally:
            try:
                pai.kill()
                pai.communicate(timeout=5)
            except Exception:                                # noqa: BLE001
                pass
            if pid_filho is not None:
                subprocess.run(["taskkill", "/PID", str(pid_filho), "/F",
                                "/T"], capture_output=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
