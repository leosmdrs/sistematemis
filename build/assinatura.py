"""
A chave de publicação e a assinatura do manifesto de atualização.

Quem publica o sistema guarda uma chave privada **fora do repositório** —
num pendrive, por exemplo. A chave pública correspondente vai embutida no
programa. A cada versão, assina-se com a privada a versão, o resumo
SHA-256 e o tamanho do instalador; a estação só aceita a atualização se
a assinatura conferir. Com isso, ter escrita no repositório deixa de
bastar para fazer um instalador chegar às estações.

Uso, a partir da raiz do projeto. Nada aqui usa a rede, e nada precisa
ser instalado além do Python.

Gerar a chave (uma vez; repita para ter uma de reserva):

    python build/assinatura.py gerar-chave E:\\temis-publicacao.chave

Assinar uma versão (os três valores saem no resumo da compilação):

    python build/assinatura.py assinar --chave E:\\temis-publicacao.chave ^
        --versao 1.16.0 --sha256 <resumo> --tamanho <bytes>

Conferir uma assinatura contra as chaves registradas no programa:

    python build/assinatura.py conferir --versao 1.16.0 --sha256 <resumo> ^
        --tamanho <bytes> --assinatura <assinatura>

Ver a chave pública de um arquivo de chave, ou registrá-la no programa:

    python build/assinatura.py publica E:\\temis-publicacao.chave
    python build/assinatura.py registrar E:\\temis-publicacao.chave
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from temis import atualizacao, ed25519                 # noqa: E402

FONTE = RAIZ / "temis" / "atualizacao.py"

CABECALHO = (
    "# Sistema Têmis — CHAVE PRIVADA de publicação.\n"
    "#\n"
    "# Quem tiver este arquivo pode anunciar uma atualização a todas as\n"
    "# estações. Guarde-o fora do computador de uso diário, nunca o envie\n"
    "# por e-mail ou mensagem, e nunca o ponha no repositório.\n"
    "#\n"
    "# Perdê-lo é tão grave quanto vazá-lo: sem ele, e sem a chave de\n"
    "# reserva, nenhuma estação volta a se atualizar por este canal.\n"
)


# ─────────────────────────────────────────
#  A CHAVE EM DISCO
# ─────────────────────────────────────────

def ler_chave(caminho) -> bytes:
    """A chave privada (32 bytes) guardada num arquivo de chave."""
    try:
        linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise SystemExit(f"Não foi possível ler a chave: {e}")
    for linha in linhas:
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            try:
                semente = bytes.fromhex(linha)
            except ValueError:
                break
            if len(semente) == 32:
                return semente
            break
    raise SystemExit(f"{caminho} não é um arquivo de chave deste sistema.")


def gravar_chave(caminho, semente: bytes) -> None:
    alvo = Path(caminho)
    if alvo.exists():
        # Gravar por cima seria destruir uma chave em uso.
        raise SystemExit(
            f"{alvo} já existe. Escolha outro nome: uma chave nunca é "
            "gravada por cima de outra.")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(CABECALHO + semente.hex() + "\n", encoding="utf-8")
    try:
        alvo.chmod(0o600)
    except OSError:
        pass


# ─────────────────────────────────────────
#  O REGISTRO DA CHAVE PÚBLICA NO PROGRAMA
# ─────────────────────────────────────────

_BLOCO = re.compile(
    r"(# <chaves-publicas>\n)(.*?)(# </chaves-publicas>\n)", re.S)


def _onde() -> str:
    try:
        return str(FONTE.relative_to(RAIZ))
    except ValueError:
        return str(FONTE)


def chaves_registradas(fonte: Path | None = None) -> list:
    fonte = fonte or FONTE
    m = _BLOCO.search(fonte.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"{fonte} não tem o bloco de chaves públicas.")
    return re.findall(r'"([0-9a-fA-F]{64})"', m.group(2))


def registrar(publica_hex: str, fonte: Path | None = None) -> bool:
    """Acrescenta a chave pública ao programa. False se já estava."""
    fonte = fonte or FONTE
    chaves = chaves_registradas(fonte)
    if publica_hex.lower() in (c.lower() for c in chaves):
        return False
    chaves.append(publica_hex.lower())
    corpo = "CHAVES_PUBLICAS: tuple = (\n" + "".join(
        f'    "{c}",\n' for c in chaves) + ")\n"
    texto = fonte.read_text(encoding="utf-8")
    fonte.write_text(
        _BLOCO.sub(lambda m: m.group(1) + corpo + m.group(3), texto, count=1),
        encoding="utf-8")
    return True


# ─────────────────────────────────────────
#  ASSINAR E CONFERIR
# ─────────────────────────────────────────

def assinar(semente: bytes, versao: str, sha256: str, tamanho: int) -> str:
    """A assinatura, como vai no manifesto (base64)."""
    if not atualizacao.versao_valida(versao):
        raise SystemExit(f"“{versao}” não é uma versão válida (ex.: 1.16.0).")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256 or ""):
        raise SystemExit("O resumo SHA-256 tem de ter 64 caracteres "
                         "hexadecimais.")
    if int(tamanho) <= 0:
        raise SystemExit("O tamanho do instalador, em bytes, é obrigatório.")
    mensagem = atualizacao.conteudo_assinado(versao, sha256, int(tamanho))
    return base64.b64encode(ed25519.assinar(semente, mensagem)).decode("ascii")


# ─────────────────────────────────────────
#  COMANDOS
# ─────────────────────────────────────────

def cmd_gerar(a) -> int:
    semente = ed25519.nova_semente()
    gravar_chave(a.arquivo, semente)
    publica = ed25519.publica_de(semente).hex()
    print(f"Chave privada gravada em {a.arquivo}")
    print(f"Chave pública: {publica}")
    if a.nao_registrar:
        print("\nA chave pública NÃO foi registrada no programa. Para "
              "registrar:\n  python build/assinatura.py registrar "
              f"{a.arquivo}")
    else:
        registrar(publica)
        print(f"\nA chave pública foi registrada em {_onde()}."
              "\nFaça o commit dessa alteração: a partir da versão que a "
              "levar, as estações só aceitam atualização assinada.")
    print("\nGuarde o arquivo da chave fora deste computador, e faça uma "
          "segunda chave, de reserva, guardada em outro lugar.")
    return 0


def cmd_registrar(a) -> int:
    publica = ed25519.publica_de(ler_chave(a.arquivo)).hex()
    if registrar(publica):
        print(f"Chave pública {publica} registrada em "
              f"{_onde()}. Faça o commit.")
    else:
        print(f"A chave pública {publica} já estava registrada.")
    return 0


def cmd_publica(a) -> int:
    print(ed25519.publica_de(ler_chave(a.arquivo)).hex())
    return 0


def cmd_assinar(a) -> int:
    semente = ler_chave(a.chave)
    assinatura = assinar(semente, a.versao, a.sha256, a.tamanho)
    publica = ed25519.publica_de(semente).hex()
    registradas = [c.lower() for c in chaves_registradas()]
    if publica not in registradas:
        print("ATENÇÃO: a chave usada não está registrada nesta cópia do "
              "programa. As estações vão recusar esta assinatura, a menos "
              "que a versão instalada nelas tenha esta chave.",
              file=sys.stderr)
    print(f"Versão:   {a.versao}", file=sys.stderr)
    print(f"SHA-256:  {a.sha256.lower()}", file=sys.stderr)
    print(f"Tamanho:  {int(a.tamanho)} bytes", file=sys.stderr)
    print("Assinatura (cole no campo “assinatura” ao publicar):",
          file=sys.stderr)
    print(assinatura)
    return 0


def cmd_conferir(a) -> int:
    chaves = chaves_registradas()
    if not chaves:
        print("Nenhuma chave pública registrada: o programa não exige "
              "assinatura.")
        return 0 if not a.assinatura else 1
    if atualizacao.assinatura_confere(a.versao, a.sha256, int(a.tamanho),
                                      a.assinatura, chaves):
        print("A assinatura confere com uma chave registrada.")
        return 0
    print("A assinatura NÃO confere: as estações recusariam esta versão.")
    return 1


def cmd_exige(_a) -> int:
    """Sai com 0 se o programa exige assinatura, 1 se não exige."""
    return 0 if chaves_registradas() else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Chave de publicação e assinatura do manifesto")
    sub = ap.add_subparsers(dest="comando", required=True)

    g = sub.add_parser("gerar-chave", help="gera uma chave nova")
    g.add_argument("arquivo")
    g.add_argument("--nao-registrar", action="store_true",
                   help="não acrescenta a chave pública ao programa")
    g.set_defaults(func=cmd_gerar)

    r = sub.add_parser("registrar",
                       help="acrescenta a chave pública ao programa")
    r.add_argument("arquivo")
    r.set_defaults(func=cmd_registrar)

    p = sub.add_parser("publica", help="mostra a chave pública")
    p.add_argument("arquivo")
    p.set_defaults(func=cmd_publica)

    for nome, func, com_chave in (("assinar", cmd_assinar, True),
                                  ("conferir", cmd_conferir, False)):
        c = sub.add_parser(nome)
        if com_chave:
            c.add_argument("--chave", required=True)
        c.add_argument("--versao", required=True)
        c.add_argument("--sha256", required=True)
        c.add_argument("--tamanho", required=True, type=int)
        if not com_chave:
            c.add_argument("--assinatura", default="")
        c.set_defaults(func=func)

    e = sub.add_parser("exige",
                       help="código 0 se há chave registrada, 1 se não")
    e.set_defaults(func=cmd_exige)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
