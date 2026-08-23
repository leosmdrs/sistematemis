"""
Prepara uma versão para publicação.

Uso, a partir da raiz do projeto:

    python build/publicar.py 1.1.0 --notas notas.txt

O que ele faz, nesta ordem:

1. escreve a versão nova em `temis/__init__.py`, `build/installer.iss` e
   `build/version_info.txt` — os três precisam concordar, e mantê-los à
   mão é como nasce um instalador 1.1.0 que se apresenta como 1.0.0;
2. compila o executável e (se o Inno Setup estiver instalado) o
   instalador;
3. calcula o SHA-256 do instalador e escreve `dist/versao.json`.

Os dois arquivos a publicar são `dist/SistemaTemis-X.Y.Z-setup.exe` e
`dist/versao.json`. O hash sai daqui justamente para não ser digitado: um
hash errado no manifesto faz toda estação recusar a atualização — o que é
o comportamento correto, e seria um enigma para quem estivesse do lado de
lá.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

#: Mesmo endereço configurado em `temis/atualizacao.py`.
REPOSITORIO_PADRAO = "leosmdrs/sistematemis"

RAIZ = Path(__file__).resolve().parents[1]
DIST = RAIZ / "dist"

#: Onde o Inno Setup costuma ficar. Se não achar, o passo é pulado com
#: aviso, em vez de interromper a preparação.
INNO = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
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


def compilar_exe():
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
              "manualmente e rode este script de novo com --so-manifesto")
        return None
    print("compilando o instalador…")
    subprocess.run([str(iscc), str(RAIZ / "build/installer.iss")],
                   cwd=RAIZ / "build", check=True)
    return DIST / f"SistemaTemis-{versao}-setup.exe"


def escrever_manifesto(instalador: Path, versao: str, notas: str,
                       repositorio: str, critica: bool):
    url = (f"https://github.com/{repositorio}/releases/download/"
           f"v{versao}/{instalador.name}")
    manifesto = {
        "versao": versao,
        "publicado": datetime.date.today().strftime("%d/%m/%Y"),
        "url": url,
        "sha256": sha256(instalador),
        "tamanho": instalador.stat().st_size,
        "notas": notas,
        "critica": critica,
    }
    alvo = DIST / "versao.json"
    alvo.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"\nmanifesto escrito em {alvo}")
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    print(f"\nPublique estes dois arquivos na versão v{versao}:")
    print(f"  {instalador}")
    print(f"  {alvo}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara uma versão para publicação")
    ap.add_argument("versao", help="Ex.: 1.1.0")
    ap.add_argument("--notas", default="",
                    help="Arquivo de texto com as novidades da versão")
    ap.add_argument("--repositorio", default=REPOSITORIO_PADRAO,
                    help="usuario/repositorio no GitHub")
    ap.add_argument("--critica", action="store_true",
                    help="Marca a atualização como importante")
    ap.add_argument("--so-manifesto", action="store_true",
                    help="Não compila nada; só recalcula o versao.json")
    args = ap.parse_args()

    notas = ""
    if args.notas:
        notas = Path(args.notas).read_text(encoding="utf-8").strip()

    instalador = DIST / f"SistemaTemis-{args.versao}-setup.exe"
    if not args.so_manifesto:
        escrever_versao(args.versao)
        compilar_exe()
        compilado = compilar_instalador(args.versao)
        if compilado is not None:
            instalador = compilado

        # ASSINATURA — quando houver certificado, o passo entra AQUI, antes
        # do manifesto. Assinar altera o arquivo e portanto o seu SHA-256;
        # assinar depois de escrever o versao.json faria toda estação
        # recusar a atualização, com a mensagem certa e a causa
        # indecifrável. Veja ASSINATURA.md.

    if not instalador.is_file():
        print(f"! instalador não encontrado em {instalador}")
        return 1

    escrever_manifesto(instalador, args.versao, notas, args.repositorio,
                       args.critica)
    return 0


if __name__ == "__main__":
    sys.exit(main())
