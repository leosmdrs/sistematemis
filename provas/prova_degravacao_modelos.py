"""Provas da chegada dos modelos de fala, na Degravação.

Os modelos vêm de repositório de terceiro, uma vez, na primeira
degravação. Eram aceitos como viessem — sem resumo de referência — e o
pacote de um deles era extraído inteiro para o disco, o que deixava ao
pacote a escolha de onde gravar. O termo não dizia qual modelo
reconheceu a fala, e sem isso ninguém repete a degravação.

Nada aqui toca a rede: a resposta do servidor é simulada.
"""

import hashlib
import io
import sys
import tarfile
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temis.tools import transcricao_core as tc        # noqa: E402


def pacote(membros: dict, elo: tuple | None = None) -> bytes:
    saida = io.BytesIO()
    with tarfile.open(fileobj=saida, mode="w:bz2") as t:
        for nome, dados in membros.items():
            info = tarfile.TarInfo(nome)
            info.size = len(dados)
            t.addfile(info, io.BytesIO(dados))
        if elo:
            info = tarfile.TarInfo(elo[0])
            info.type = tarfile.SYMTYPE
            info.linkname = elo[1]
            t.addfile(info)
    return saida.getvalue()


class _Resposta:
    def __init__(self, dados):
        self._dados = dados

    def read(self, n=-1):
        return self._dados if n is None or n < 0 else self._dados[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Base(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.pasta = Path(self._dir.name)
        self._trocar(tc, "pasta_modelos", lambda: self.pasta)

    def _trocar(self, alvo, nome, valor):
        original = getattr(alvo, nome)
        setattr(alvo, nome, valor)
        self.addCleanup(setattr, alvo, nome, original)

    def servir(self, respostas: dict):
        self._trocar(urllib.request, "urlopen",
                     lambda pedido, timeout=0: _Resposta(
                         respostas[pedido.full_url]))


class OPacoteNaoEscolheOndeGravar(Base):

    def test_so_o_modelo_e_lido_e_nada_e_extraido(self):
        dados = pacote({"x/README.md": b"leia",
                        "../../fora.txt": b"saiu da pasta",
                        "x/model.onnx": b"MODELO"},
                       elo=("x/elo", "/etc/passwd"))
        antes = sorted(self.pasta.parent.glob("fora.txt"))
        self.assertEqual(tc._modelo_do_pacote(dados), b"MODELO")
        self.assertEqual(sorted(self.pasta.parent.glob("fora.txt")), antes)
        self.assertEqual(list(self.pasta.rglob("*")), [])

    def test_elo_com_o_nome_do_modelo_nao_e_seguido(self):
        dados = pacote({}, elo=("x/model.onnx", "/etc/passwd"))
        with self.assertRaises(tc.ErroTranscricao):
            tc._modelo_do_pacote(dados)

    def test_pacote_sem_o_modelo_e_recusado(self):
        with self.assertRaises(tc.ErroTranscricao):
            tc._modelo_do_pacote(pacote({"x/outro.onnx": b"y"}))


class OModeloEConferidoAntesDeInstalar(Base):

    def setUp(self):
        super().setUp()
        self.empacotado = pacote({"x/model.onnx": b"SEGMENTACAO"})
        self.voz = b"VOZ" * 100
        self._trocar(tc, "ARQUIVOS_DIARIZACAO", (
            ("segmentacao.onnx", "https://exemplo.test/seg.tar.bz2", 1,
             hashlib.sha256(self.empacotado).hexdigest()),
            ("voz.onnx", "https://exemplo.test/voz.onnx", 1,
             hashlib.sha256(self.voz).hexdigest()),
        ))

    def test_o_que_confere_e_instalado(self):
        self.servir({"https://exemplo.test/seg.tar.bz2": self.empacotado,
                     "https://exemplo.test/voz.onnx": self.voz})
        pasta = tc.baixar_diarizacao()
        self.assertEqual((pasta / "segmentacao.onnx").read_bytes(),
                         b"SEGMENTACAO")
        self.assertEqual((pasta / "voz.onnx").read_bytes(), self.voz)
        self.assertTrue(tc.diarizacao_baixada())

    def test_o_que_nao_confere_nao_e_instalado(self):
        self.servir({"https://exemplo.test/seg.tar.bz2":
                     pacote({"x/model.onnx": b"OUTRO MODELO"}),
                     "https://exemplo.test/voz.onnx": self.voz})
        with self.assertRaises(tc.ErroTranscricao):
            tc.baixar_diarizacao()
        self.assertFalse(tc.diarizacao_baixada())
        self.assertEqual(
            [p.name for p in tc.pasta_diarizacao().iterdir()], [])

    def test_arquivo_maior_que_o_teto_e_recusado(self):
        self._trocar(tc, "LIMITE_MODELO", 10)
        self.servir({"https://exemplo.test/seg.tar.bz2": self.empacotado,
                     "https://exemplo.test/voz.onnx": self.voz})
        with self.assertRaises(tc.ErroTranscricao):
            tc.baixar_diarizacao()

    def test_os_modelos_de_verdade_tem_resumo_de_referencia(self):
        self.doCleanups()                       # volta à tabela real
        for nome, url, _mb, resumo in tc.ARQUIVOS_DIARIZACAO:
            with self.subTest(nome):
                self.assertTrue(url.startswith("https://"))
                self.assertRegex(resumo, r"^[0-9a-f]{64}$")


class OTermoDizQualModeloReconheceu(Base):

    def modelo_em_disco(self, conteudo=b"pesos do modelo"):
        pasta = tc.pasta_do_modelo("small")
        pasta.mkdir(parents=True)
        (pasta / "model.bin").write_bytes(conteudo)
        return pasta / "model.bin"

    def test_o_resumo_e_o_do_arquivo_em_disco(self):
        arquivo = self.modelo_em_disco()
        self.assertEqual(tc.resumo_do_modelo("small"),
                         hashlib.sha256(arquivo.read_bytes()).hexdigest())

    def test_modelo_trocado_muda_o_resumo(self):
        arquivo = self.modelo_em_disco()
        antes = tc.resumo_do_modelo("small")
        arquivo.write_bytes(b"outros pesos, de outro tamanho")
        self.assertNotEqual(tc.resumo_do_modelo("small"), antes)

    def test_sem_modelo_o_resumo_e_vazio(self):
        self.assertEqual(tc.resumo_do_modelo("small"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
