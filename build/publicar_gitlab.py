"""
Publica no GitLab da PRF o instalador que o `publicar.py` preparou.

Uso, a partir da raiz do projeto, depois do `publicar.py` e com o commit
da versão já enviado ao `main`:

    $env:GITLAB_TOKEN = "..."        # token pessoal, escopo `api`
    python build/publicar_gitlab.py 1.16.0

O que ele faz, nesta ordem:

1. confere o SHA-256 do instalador contra o `dist/SHA256SUMS.txt`;
2. envia o instalador e o `SHA256SUMS.txt` ao registro de pacotes do
   projeto, que é onde o GitLab guarda binário (a release, lá, só aponta
   para endereços);
3. cria a release `vX.Y.Z`, com as notas de `notas.txt`, o resumo do
   instalador no texto e os dois arquivos como anexo.

O sistema não consulta este endereço: não há atualização automática. A
release é a página de onde quem recebeu o e-mail da versão nova baixa o
instalador, logado na conta da PRF.

O token não vai em argumento nem em arquivo: fica na variável de ambiente
e some com o terminal. Com `--conferir` nada é enviado; o script só diz o
que faria.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIST = RAIZ / "dist"

SERVIDOR = "https://git.prf.gov.br"
REPOSITORIO_PADRAO = "sistemas-nacionais/temis"

#: Nome do pacote no registro. Um só, com uma versão por lançamento.
PACOTE = "SistemaTemis"


def sha256(caminho: Path) -> str:
    d = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            d.update(bloco)
    return d.hexdigest()


def resumo_declarado(resumos: Path, nome: str) -> str:
    """O SHA-256 que o `SHA256SUMS.txt` declara para `nome`, ou ''."""
    for linha in resumos.read_text(encoding="utf-8").splitlines():
        partes = linha.split(maxsplit=1)
        if len(partes) == 2 and partes[1].strip().lstrip("*") == nome:
            return partes[0].lower()
    return ""


def endereco_pacote(repositorio: str, versao: str, nome: str) -> str:
    projeto = urllib.parse.quote(repositorio, safe="")
    return (f"{SERVIDOR}/api/v4/projects/{projeto}/packages/generic/"
            f"{PACOTE}/{versao}/{urllib.parse.quote(nome)}")


def descricao(notas: str, instalador: str, resumo: str) -> str:
    """Texto da release: as notas e, por último, como conferir o arquivo."""
    return (f"{notas.strip()}\n\n---\n\n"
            f"**SHA-256 de `{instalador}`:**\n\n`{resumo}`\n\n"
            "Para conferir antes de instalar, no PowerShell:\n\n"
            f"```\nGet-FileHash {instalador} -Algorithm SHA256\n```\n")


def corpo_release(repositorio: str, versao: str, texto: str,
                  nomes: list[str]) -> dict:
    """O pedido de criação da release, com os anexos."""
    return {
        "name": f"Sistema Têmis {versao}",
        "tag_name": f"v{versao}",
        # Só é usado se a etiqueta ainda não existir no servidor.
        "ref": "main",
        "description": texto,
        "assets": {"links": [
            {"name": nome,
             "url": endereco_pacote(repositorio, versao, nome),
             "direct_asset_path": f"/{nome}",
             "link_type": "package"}
            for nome in nomes
        ]},
    }


def enviar_arquivo(caminho: Path, url: str, token: str) -> None:
    """Envia em fluxo: o instalador passa de 300 MB e não cabe na memória
    de quem só quer publicar."""
    partes = urllib.parse.urlsplit(url)
    conexao = http.client.HTTPSConnection(partes.netloc, timeout=600)
    try:
        with open(caminho, "rb") as f:
            conexao.request("PUT", partes.path, body=f, headers={
                "PRIVATE-TOKEN": token,
                "Content-Length": str(caminho.stat().st_size),
                "Content-Type": "application/octet-stream",
            })
            resposta = conexao.getresponse()
            texto = resposta.read().decode("utf-8", "replace")
    finally:
        conexao.close()
    if resposta.status not in (200, 201):
        raise RuntimeError(f"o servidor respondeu {resposta.status} ao "
                           f"receber {caminho.name}: {texto[:300]}")


def criar_release(repositorio: str, corpo: dict, token: str) -> str:
    projeto = urllib.parse.quote(repositorio, safe="")
    pedido = urllib.request.Request(
        f"{SERVIDOR}/api/v4/projects/{projeto}/releases",
        data=json.dumps(corpo).encode("utf-8"), method="POST",
        headers={"PRIVATE-TOKEN": token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"o servidor respondeu {e.code} ao criar a "
                           f"release: {texto[:300]}")
    return dados.get("_links", {}).get("self", "")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Publica o instalador preparado no GitLab da PRF")
    ap.add_argument("versao", help="Ex.: 1.16.0")
    ap.add_argument("--repositorio", default=REPOSITORIO_PADRAO,
                    help="grupo/projeto no GitLab da PRF")
    ap.add_argument("--notas", default=str(RAIZ / "notas.txt"),
                    help="Arquivo com as novidades da versão")
    ap.add_argument("--conferir", action="store_true",
                    help="Não envia nada; só confere e mostra o que faria")
    args = ap.parse_args()

    instalador = DIST / f"SistemaTemis-{args.versao}-setup.exe"
    resumos = DIST / "SHA256SUMS.txt"
    for arquivo in (instalador, resumos):
        if not arquivo.is_file():
            print(f"! não encontrado: {arquivo} — rode o publicar.py antes")
            return 1

    resumo = sha256(instalador)
    if resumo_declarado(resumos, instalador.name) != resumo:
        print("! o SHA-256 do instalador não confere com o SHA256SUMS.txt")
        return 1

    notas = ""
    if Path(args.notas).is_file():
        notas = Path(args.notas).read_text(encoding="utf-8")
    corpo = corpo_release(args.repositorio, args.versao,
                          descricao(notas, instalador.name, resumo),
                          [instalador.name, resumos.name])
    if args.conferir:
        print("Conferido. Seria enviado:")
        for arquivo in (instalador, resumos):
            # Sem seta: o console do Windows em cp1252 não a imprime.
            print(f"  {arquivo}\n    para "
                  f"{endereco_pacote(args.repositorio, args.versao, arquivo.name)}")
        print(json.dumps(corpo, ensure_ascii=True, indent=2))
        return 0

    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        print("! defina a variável de ambiente GITLAB_TOKEN com um token "
              "pessoal de escopo `api`")
        return 1

    try:
        for arquivo in (instalador, resumos):
            print(f"enviando {arquivo.name}…")
            enviar_arquivo(
                arquivo,
                endereco_pacote(args.repositorio, args.versao, arquivo.name),
                token)
        print("criando a release…")
        pagina = criar_release(args.repositorio, corpo, token)
    except (RuntimeError, OSError) as e:
        print(f"! {e}")
        return 1

    print(f"\nPublicado: {pagina or 'release criada'}")
    print("Avise por e-mail quem usa o sistema, com o SHA-256 acima.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
