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
        for n in range(2):
            destino = self.caminho(f"s{n}.mp4")
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
