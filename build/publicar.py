"""
Prepara uma versão para publicação.

Uso, a partir da raiz do projeto:

    python build/publicar.py 1.1.0

O que ele faz, nesta ordem:

1. escreve a versão nova em `temis/__init__.py`, `build/installer.iss` e
   `build/version_info.txt` — os três precisam concordar, e mantê-los à
   mão é como nasce um instalador 1.1.0 que se apresenta como 1.0.0;
2. compila o executável e (se o Inno Setup estiver instalado) o
   instalador;
3. calcula o SHA-256 do instalador e dos arquivos do programa e o grava
   em `dist/SHA256SUMS.txt`.

O que se distribui é `dist/SistemaTemis-X.Y.Z-setup.exe`. O sistema não
se atualiza sozinho: a versão nova é anunciada por e-mail, com o resumo
SHA-256 do instalador, e quem a recebe baixa e instala. O resumo sai daqui
para não ser digitado: copiado à mão, um erro faria quem confere achar que
o arquivo foi adulterado.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIST = RAIZ / "dist"

#: Onde o Inno Setup costuma ficar. Se não achar, o passo é pulado com
#: aviso, em vez de interromper a preparação.
INNO = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    # Instalação em escopo de usuário, que é onde o winget o põe quando
    # não há administrador — o caso comum numa estação institucional.
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6"
    / "ISCC.exe",
]


def sha256(caminho: Path) -> str:
    d = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            d.update(bloco)
    return d.hexdigest()


def escrever_versao(versao: str):
    """Deixa os três lugares que declaram a versão de acordo entre si."""
    partes = [int(x) for x in re.findall(r"\d+", versao)][:3]
    while len(partes) < 3:
        partes.append(0)
    quadra = ", ".join(str(x) for x in partes + [0])

    alvo = RAIZ / "temis/__init__.py"
    s = alvo.read_text(encoding="utf-8")
    s = re.sub(r'__version__ = "[^"]*"', f'__version__ = "{versao}"', s)
    alvo.write_text(s, encoding="utf-8")

    alvo = RAIZ / "build/installer.iss"
    s = alvo.read_text(encoding="utf-8")
    s = re.sub(r'#define AppVersion\s+"[^"]*"',
               f'#define AppVersion     "{versao}"', s)
    alvo.write_text(s, encoding="utf-8")

    alvo = RAIZ / "build/version_info.txt"
    s = alvo.read_text(encoding="utf-8")
    s = re.sub(r"filevers=\(\d+, \d+, \d+, \d+\)", f"filevers=({quadra})", s)
    s = re.sub(r"prodvers=\(\d+, \d+, \d+, \d+\)", f"prodvers=({quadra})", s)
    s = re.sub(r"'FileVersion', '[^']*'",
               f"'FileVersion', '{'.'.join(str(x) for x in partes)}.0'", s)
    s = re.sub(r"'ProductVersion', '[^']*'",
               f"'ProductVersion', '{'.'.join(str(x) for x in partes)}.0'", s)
    alvo.write_text(s, encoding="utf-8")
    print(f"versão {versao} escrita nos três arquivos")


def gerar_icone():
    """Desenha o `.ico` que o executável carrega, se ele não existir.

    Fica aqui porque o PUBLICACAO.md promete um comando só, e o ícone é
    derivado — não vai para o Git. Quem clonasse o repositório e rodasse
    a publicação direto perdia quarenta minutos para descobrir, no fim da
    compilação, que faltava um arquivo de 27 KB que o próprio projeto
    sabe desenhar.
    """
    alvo = RAIZ / "build" / "temis.ico"
    if alvo.is_file():
        return
    print("desenhando o ícone…")
    subprocess.run([sys.executable, str(RAIZ / "build" / "make_icon.py")],
                   cwd=RAIZ, check=True)


def compilar_exe():
    gerar_icone()
    print("compilando o executável…")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(DIST), "--workpath", str(RAIZ / "build/_work"),
         str(RAIZ / "build/temis.spec")],
        cwd=RAIZ, check=True)


def compilar_instalador(versao: str) -> Path | None:
    iscc = next((p for p in INNO if p.is_file()), None)
    if iscc is None and shutil.which("iscc"):
        iscc = Path(shutil.which("iscc"))
    if iscc is None:
        print("! Inno Setup não encontrado — compile build/installer.iss "
              "manualmente e rode este script de novo com --so-resumos")
        return None
    print("compilando o instalador…")
    subprocess.run([str(iscc), str(RAIZ / "build/installer.iss")],
                   cwd=RAIZ / "build", check=True)
    return DIST / f"SistemaTemis-{versao}-setup.exe"


def escrever_resumos(instalador: Path, versao: str) -> Path:
    """Grava os resumos SHA-256 no formato do `sha256sum`.

    O do instalador é o que vai no e-mail e na página de download, para
    quem baixa conferir antes de executar. Os dos arquivos do programa
    são os que cada peça imprime como procedência: é contra eles que se
    confronta o que a peça declara.
    """
    linhas = [f"{sha256(instalador)}  {instalador.name}"]
    for nome in ("SistemaTemis.exe", "SistemaTemis.pkg"):
        arquivo = DIST / "SistemaTemis" / nome
        if arquivo.is_file():
            linhas.append(f"{sha256(arquivo)}  SistemaTemis/{nome}")
    alvo = DIST / "SHA256SUMS.txt"
    # Fim de linha LF mesmo no Windows: com CRLF, o `sha256sum -c` toma o
    # \r como parte do nome do arquivo e diz que ele não existe.
    alvo.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
    tamanho = instalador.stat().st_size
    print(f"\nresumos gravados em {alvo}:")
    print("\n".join(f"  {l}" for l in linhas))
    print(f"\nInstalador da versão {versao} pronto para distribuir:")
    print(f"  {instalador} ({tamanho} bytes)")
    print(f"\n  python build/publicar_gitlab.py {versao}")
    return alvo


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara uma versão para publicação")
    ap.add_argument("versao", help="Ex.: 1.1.0")
    ap.add_argument("--so-resumos", action="store_true",
                    help="Não compila nada; só recalcula o SHA256SUMS.txt")
    args = ap.parse_args()

    instalador = DIST / f"SistemaTemis-{args.versao}-setup.exe"
    if not args.so_resumos:
        escrever_versao(args.versao)
        compilar_exe()
        compilado = compilar_instalador(args.versao)
        if compilado is not None:
            instalador = compilado

        # ASSINATURA — se um dia houver certificado de código, o passo
        # entra AQUI, antes dos resumos: assinar altera o arquivo e
        # portanto o seu SHA-256. Veja ASSINATURA.md.

    if not instalador.is_file():
        print(f"! instalador não encontrado em {instalador}")
        return 1

    escrever_resumos(instalador, args.versao)
    return 0


if __name__ == "__main__":
    sys.exit(main())
