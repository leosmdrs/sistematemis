"""Provas do roteiro da Edição de Vídeo.

O termo declarava os parâmetros em prosa — "CRF 20", "720p", "de
00:01:12 a 00:03:40". Prosa se lê e não se executa: um terceiro que
quisesse conferir teria de adivinhar o comando.

O roteiro põe os parâmetros em forma de máquina, e a própria ferramenta
reconstrói o comando a partir deles. A conferência, aqui, é do **arquivo**
e não do conteúdo — ao contrário da censura, e por um motivo que estas
provas medem: as formas que a ferramenta produz saem byte a byte
idênticas quando reexecutadas com o mesmo FFmpeg.

Rodam o FFmpeg de verdade, sobre um clipe minúsculo gerado na hora. Sem
ele instalado, são puladas em vez de falharem: a ausência do binário não
é defeito do roteiro.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis.tools import video_core as vc              # noqa: E402
from temis.tools.hash_core import sha256_file         # noqa: E402


class ComFFmpeg(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if vc.ffmpeg_path() is None:
            raise unittest.SkipTest("FFmpeg não está disponível")

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

    def caminho(self, nome):
        return str(Path(self.pasta.name) / nome)

    def clipe(self, nome="a.mp4", padrao="testsrc"):
        """Um clipe minúsculo, para o FFmpeg rodar em fração de segundo."""
        alvo = self.caminho(nome)
        subprocess.run(
            [str(vc.ffmpeg_path()), "-y", "-f", "lavfi", "-i",
             f"{padrao}=size=160x120:rate=10:duration=1", "-c:v", "libx264",
             "-crf", "30", "-pix_fmt", "yuv420p", alvo, "-loglevel", "error"],
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return alvo


class AsOperacoesReproduzemByteAByte(ComFFmpeg):
    """A medição de que depende o desenho inteiro."""

    def rodar(self, monta):
        resumos = set()
        # Nome novo a cada rodada: a edição não grava sobre arquivo que
        # já existe, e a prova não pode depender de que gravasse.
        self._rodadas = getattr(self, "_rodadas", 0) + 1
        for n in range(2):
            destino = self.caminho(f"s{self._rodadas}-{n}.mp4")
            deu, erro = vc.executar(monta(destino))
            self.assertTrue(deu, erro)
            resumos.add(sha256_file(destino))
        return resumos

    def test_compactar_reproduz(self):
        entrada = self.clipe()
        preset = vc.PRESETS[1]
        resumos = self.rodar(lambda d: vc.cmd_compactar(
            entrada, d, preset, 0, False, "aac"))
        self.assertEqual(len(resumos), 1)

    def test_fatiar_reproduz_copiando_e_recodificando(self):
        entrada = self.clipe()
        for recodificar in (False, True):
            with self.subTest(recodificar=recodificar):
                resumos = self.rodar(lambda d, r=recodificar: vc.cmd_fatiar(
                    entrada, d, 0.2, 0.8, r))
                self.assertEqual(len(resumos), 1)

    def test_mesclar_reproduz(self):
        a, b = self.clipe("a.mp4"), self.clipe("b.mp4")
        lista = vc.escrever_lista_concat([a, b],
                                         Path(self.pasta.name) / "l.txt")
        resumos = self.rodar(lambda d: vc.cmd_mesclar(lista, d, False))
        self.assertEqual(len(resumos), 1)


class ORoteiroGuardaOQuePrecisa(ComFFmpeg):

    def compactar(self):
        entrada = self.clipe()
        saida = self.caminho("out.mp4")
        preset = vc.PRESETS[1]
        deu, erro = vc.executar(
            vc.cmd_compactar(entrada, saida, preset, 0, False, "aac"))
        self.assertTrue(deu, erro)
        roteiro = vc.montar_roteiro(
            "compactar", [entrada],
            {"preset": preset.chave, "altura": 0, "sem_audio": False,
             "codec_audio": "aac"}, saida)
        return entrada, saida, roteiro

    def test_o_roteiro_faz_a_ida_e_a_volta(self):
        _, _, roteiro = self.compactar()
        caminho = self.caminho("r.json")
        vc.salvar_roteiro(roteiro, caminho)
        self.assertEqual(vc.ler_roteiro(caminho).dados(), roteiro.dados())

    def test_guarda_a_versao_do_ffmpeg_que_produziu(self):
        # A identidade byte a byte é prometida para aquele motor. Sem
        # dizer qual, a promessa não tem endereço.
        _, _, roteiro = self.compactar()
        self.assertTrue(roteiro.ffmpeg)
        self.assertEqual(roteiro.ffmpeg, vc.versao_curta())

    def test_o_comando_se_reconstroi_igual_ao_que_rodou(self):
        entrada, _, roteiro = self.compactar()
        refeito = roteiro.comando(self.caminho("z.mp4"))
        original = vc.cmd_compactar(entrada, self.caminho("z.mp4"),
                                    vc.PRESETS[1], 0, False, "aac")
        self.assertEqual(refeito, original)

    def test_re_executar_produz_o_mesmo_arquivo(self):
        _, _, roteiro = self.compactar()
        self.assertEqual(vc.reproduzir(roteiro)[0], "sim")

    def test_origem_alterada_e_impossivel_e_nao_divergencia(self):
        # Original que mudou não é edição que deixou de reproduzir, e
        # chamar uma pela outra seria acusar divergência não constatada.
        entrada, _, roteiro = self.compactar()
        Path(entrada).write_bytes(Path(entrada).read_bytes() + b"x")
        situacao, _, explicacao = vc.reproduzir(roteiro)
        self.assertEqual(situacao, "impossivel")
        self.assertIn("não é mais o mesmo", explicacao)

    def test_origem_que_sumiu_tambem_e_impossivel(self):
        entrada, _, roteiro = self.compactar()
        Path(entrada).unlink()
        self.assertEqual(vc.reproduzir(roteiro)[0], "impossivel")

    def test_resumo_declarado_diferente_nao_reproduz(self):
        _, _, roteiro = self.compactar()
        roteiro.resumo_saida = "0" * 64
        self.assertEqual(vc.reproduzir(roteiro)[0], "nao")

    def test_ffmpeg_de_outra_versao_e_impossivel_e_nao_divergencia(self):
        # Divergência com motor diferente não prova que a edição mudou:
        # prova que a promessa não se aplica.
        _, _, roteiro = self.compactar()
        roteiro.resumo_saida = "0" * 64
        roteiro.ffmpeg = "0.0.0-outro"
        situacao, _, explicacao = vc.reproduzir(roteiro)
        self.assertEqual(situacao, "impossivel")
        self.assertIn("não é o que produziu", explicacao)

    def test_o_roteiro_do_recorte_guarda_o_trecho(self):
        entrada = self.clipe()
        saida = self.caminho("trecho.mp4")
        deu, erro = vc.executar(vc.cmd_fatiar(entrada, saida, 0.2, 0.8, True))
        self.assertTrue(deu, erro)
        roteiro = vc.montar_roteiro(
            "fatiar", [entrada],
            {"inicio": 0.2, "fim": 0.8, "recodificar": True}, saida)
        self.assertEqual(vc.reproduzir(roteiro)[0], "sim")

    def test_a_ordem_da_mesclagem_faz_parte_do_roteiro(self):
        a, b = self.clipe("a.mp4"), self.clipe("b.mp4", padrao="smptebars")
        saida = self.caminho("junto.mp4")
        lista = vc.escrever_lista_concat([a, b], Path(self.pasta.name) / "l.txt")
        deu, erro = vc.executar(vc.cmd_mesclar(lista, saida, True))
        self.assertTrue(deu, erro)
        roteiro = vc.montar_roteiro("mesclar", [a, b],
                                    {"recodificar": True}, saida)
        self.assertEqual(vc.reproduzir(roteiro)[0], "sim")
        # Invertida a ordem, o resultado é outro — e por isso ela é
        # parâmetro declarado, e não detalhe de execução.
        invertido = vc.montar_roteiro("mesclar", [b, a],
                                      {"recodificar": True}, saida)
        self.assertEqual(vc.reproduzir(invertido)[0], "nao")


class OOriginalNuncaEDestino(ComFFmpeg):
    """A edição produz arquivo novo; o original é a prova.

    O FFmpeg era chamado com a ordem de gravar por cima, e nada conferia
    se o destino era um arquivo de entrada: no Windows bastava escolher o
    próprio original com outra caixa de letras. Na compactação em lote,
    dois vídeos de mesmo nome caíam na mesma saída.
    """

    def test_o_mesmo_arquivo_e_reconhecido_por_outro_caminho(self):
        entrada = self.clipe()
        outro = str(Path(self.pasta.name) / "sub" / ".." / "a.mp4")
        Path(self.pasta.name, "sub").mkdir()
        self.assertTrue(vc.mesmo_arquivo(entrada, outro))
        self.assertTrue(vc.coincide_com_entrada(outro, [entrada]))
        self.assertFalse(vc.coincide_com_entrada(self.caminho("b.mp4"),
                                                 [entrada]))

    def test_caixa_diferente_e_o_mesmo_arquivo_onde_o_sistema_assim_trata(self):
        import os
        original = os.path.normcase
        os.path.normcase = lambda p: str(p).lower()   # como no Windows
        self.addCleanup(setattr, os.path, "normcase", original)
        self.assertTrue(vc.mesmo_arquivo(self.caminho("Video.MP4"),
                                         self.caminho("video.mp4")))

    def test_o_ffmpeg_nao_grava_sobre_arquivo_existente(self):
        entrada = self.clipe()
        antes = sha256_file(entrada)
        for cmd in (vc.cmd_fatiar(entrada, entrada, 0, 0.5),
                    vc.cmd_compactar(entrada, entrada, vc.PRESETS[1])):
            self.assertNotIn("-y", cmd)
            deu, _erro = vc.executar(cmd)
            self.assertFalse(deu)
            self.assertEqual(sha256_file(entrada), antes)

    def test_homonimos_nao_caem_na_mesma_saida(self):
        pasta = Path(self.pasta.name)
        primeira = vc.nome_livre(pasta / "X-compactado.mp4")
        segunda = vc.nome_livre(pasta / "X-compactado.mp4", [primeira])
        self.assertNotEqual(primeira, segunda)
        Path(primeira).write_bytes(b"x")
        self.assertNotEqual(vc.nome_livre(pasta / "X-compactado.mp4"),
                            primeira)

    def test_o_nome_livre_nao_e_um_original_da_lista(self):
        # A lista tem "X.mp4" e "X-compactado.mp4": a saída do primeiro
        # não pode ser o segundo.
        pasta = Path(self.pasta.name)
        outro_original = self.clipe("X-compactado.mp4")
        livre = vc.nome_livre(pasta / "X-compactado.mp4", [outro_original])
        self.assertFalse(vc.mesmo_arquivo(livre, outro_original))


class AFilaDeOperacoes(ComFFmpeg):
    """A fila real da ferramenta, rodada no fio da prova."""

    def setUp(self):
        super().setUp()
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        from temis.tools import video as tela
        self.tela = tela

    def rodar(self, tarefas, originais):
        desfecho = []
        fio = self.tela.VideoThread(tarefas, originais=originais)
        fio.concluido.connect(lambda s, e: desfecho.append((s, e)))
        fio.run()
        return desfecho[0]

    def test_o_resultado_so_ocupa_o_nome_depois_de_pronto(self):
        entrada = self.clipe()
        saida = self.caminho("trecho.mp4")
        cmd = vc.cmd_fatiar(entrada, vc.provisorio(saida), 0, 0.5)
        saidas, erros = self.rodar([(cmd, 0.5, "trecho", saida)], [entrada])
        self.assertEqual(erros, [])
        self.assertEqual(saidas, [saida])
        self.assertTrue(Path(saida).is_file())
        self.assertFalse(Path(vc.provisorio(saida)).exists())

    def test_operacao_que_falha_nao_destroi_o_arquivo_que_ia_substituir(self):
        entrada = self.clipe()
        saida = self.caminho("existente.mp4")
        Path(saida).write_bytes(b"arquivo anterior")
        cmd = vc.cmd_fatiar(self.caminho("nao-existe.mp4"),
                            vc.provisorio(saida), 0, 0.5)
        saidas, erros = self.rodar([(cmd, 0.5, "trecho", saida)], [entrada])
        self.assertEqual(saidas, [])
        self.assertTrue(erros)
        self.assertEqual(Path(saida).read_bytes(), b"arquivo anterior")

    def test_original_alterado_durante_a_operacao_e_acusado(self):
        entrada = self.clipe()
        saida = self.caminho("trecho.mp4")
        cmd = vc.cmd_fatiar(entrada, vc.provisorio(saida), 0, 0.5)
        original = vc.executar

        def executar_e_estragar(*a, **k):
            resultado = original(*a, **k)
            with open(entrada, "ab") as f:
                f.write(b"alterado")
            return resultado

        vc.executar = executar_e_estragar
        self.addCleanup(setattr, vc, "executar", original)
        _saidas, erros = self.rodar([(cmd, 0.5, "trecho", saida)], [entrada])
        self.assertTrue(any("não é mais o mesmo" in e for e in erros))

    def test_original_intacto_nao_gera_acusacao(self):
        entrada = self.clipe()
        saida = self.caminho("c.mp4")
        cmd = vc.cmd_compactar(entrada, vc.provisorio(saida), vc.PRESETS[1])
        _saidas, erros = self.rodar([(cmd, 1.0, "c", saida)], [entrada])
        self.assertEqual(erros, [])


class OTermoDescreveOArquivoEntregue(ComFFmpeg):
    """A peça mede o arquivo produzido, em vez de repetir o pedido."""

    def com_som(self, nome, taxa, trilhas=1, legenda=False):
        alvo = self.caminho(nome)
        cmd = [str(vc.ffmpeg_path()), "-y", "-loglevel", "error",
               "-f", "lavfi", "-i",
               "testsrc=size=160x120:rate=10:duration=2"]
        for _ in range(trilhas):
            cmd += ["-f", "lavfi", "-i",
                    f"sine=frequency=1000:sample_rate={taxa}:duration=2"]
        cmd += ["-map", "0:v"]
        for i in range(trilhas):
            cmd += ["-map", f"{i + 1}:a"]
        cmd += ["-c:v", "libx264", "-g", "50", "-pix_fmt", "yuv420p",
                "-c:a", "aac", alvo]
        subprocess.run(cmd, check=True)
        return alvo

    def test_taxas_de_audio_diferentes_exigem_recodificar(self):
        a = vc.sondar(self.com_som("a.mp4", 44100))
        b = vc.sondar(self.com_som("b.mp4", 48000))
        self.assertEqual((a.taxa_audio, b.taxa_audio), (44100, 48000))
        self.assertFalse(a.compativel_com(b))
        self.assertTrue(vc.precisa_recodificar([a, b]))

    def test_arquivos_iguais_seguem_sendo_copiados(self):
        a = vc.sondar(self.com_som("a.mp4", 44100))
        b = vc.sondar(self.com_som("b.mp4", 44100))
        self.assertTrue(a.compativel_com(b))

    def test_o_corte_rapido_declara_a_duracao_que_saiu(self):
        # Um quadro-chave só, no início: pedir de 1,0 a 1,5 s entrega
        # mais do que meio segundo.
        entrada = self.com_som("longo.mp4", 44100)
        saida = self.caminho("trecho.mp4")
        deu, erro = vc.executar(vc.cmd_fatiar(entrada, saida, 1.0, 1.5))
        self.assertTrue(deu, erro)
        linhas = dict(vc.medidas_do_produzido(saida, "fatiar", 0.5))
        real = vc.sondar(saida).duracao
        self.assertEqual(linhas["Duração do arquivo produzido"],
                         vc.formatar_tempo(real))
        if abs(real - 0.5) >= 0.2:
            self.assertIn("Diferença para o trecho pedido", linhas)
            self.assertIn("quadro-chave", linhas[
                "Diferença para o trecho pedido"])

    def test_trilha_que_nao_segue_e_nomeada(self):
        info = vc.sondar(self.com_som("duas.mp4", 44100, trilhas=2))
        self.assertEqual(info.trilhas_audio, 2)
        self.assertIn("1 trilha(s) de áudio além da primeira",
                      info.trilhas_que_ficam_de_fora)
        simples = vc.sondar(self.com_som("uma.mp4", 44100))
        self.assertEqual(simples.trilhas_que_ficam_de_fora, "")


class OProgramaInstaladoSoUsaOFFmpegQueVeioComEle(unittest.TestCase):

    def test_empacotado_nao_recorre_ao_path(self):
        import shutil
        guardado = getattr(sys, "frozen", None)
        original = vc._candidatos
        vc._candidatos = lambda nome: []
        sys.frozen = True

        def repor():
            vc._candidatos = original
            if guardado is None:
                del sys.frozen
            else:
                sys.frozen = guardado

        self.addCleanup(repor)
        if shutil.which("ffmpeg") is None:
            self.skipTest("sem FFmpeg no PATH para tentar")
        self.assertIsNone(vc.localizar("ffmpeg"))


class APecaDizOQueAConferenciaSignifica(unittest.TestCase):

    def test_as_tres_situacoes_tem_redacao_propria(self):
        for situacao, marca in (("sim", "resumo criptográfico idêntico"),
                                ("nao", "não deve ser tratado como"),
                                ("impossivel", "segue possível por quem")):
            with self.subTest(situacao):
                self.assertIn(marca, vc.frase_reproducao(situacao))

    def test_a_promessa_e_condicionada_ao_mesmo_motor(self):
        self.assertIn("mesmo FFmpeg", vc.frase_reproducao("sim"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
