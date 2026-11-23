"""
Publica no GitLab da PRF a versão que o `publicar.py` preparou.

Uso, a partir da raiz do projeto, depois do `publicar.py` e com o commit
da versão já enviado ao `main`:

    $env:GITLAB_TOKEN = "..."        # token pessoal, escopo `api`
    python build/publicar_gitlab.py 1.15.3

O que ele faz, nesta ordem:

1. confere o SHA-256 do instalador contra o `dist/versao.json` — publicar
   um manifesto que não confere faz toda estação recusar a atualização;
2. envia os dois arquivos ao registro de pacotes do projeto, que é onde o
   GitLab guarda binário (release, lá, só aponta para endereços);
3. cria a release `vX.Y.Z` com os dois anexos cadastrados nos caminhos
   `/versao.json` e `/SistemaTemis-X.Y.Z-setup.exe`.

Os caminhos do passo 3 são o que sustenta a atualização: é por eles que
`releases/permalink/latest/downloads/versao.json` responde, e é neles que
o manifesto aponta o instalador. Anexo cadastrado sem caminho aparece na
página e não é achado por estação nenhuma.

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

#: Mesmo endereço configurado em `temis/atualizacao.py`.
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


def endereco_pacote(repositorio: str, versao: str, nome: str) -> str:
    projeto = urllib.parse.quote(repositorio, safe="")
    return (f"{SERVIDOR}/api/v4/projects/{projeto}/packages/generic/"
            f"{PACOTE}/{versao}/{urllib.parse.quote(nome)}")


def corpo_release(repositorio: str, versao: str, notas: str,
                  nomes: list[str]) -> dict:
    """O pedido de criação da release, com os anexos e seus caminhos."""
    return {
        "name": f"Sistema Têmis {versao}",
        "tag_name": f"v{versao}",
        # Só é usado se a etiqueta ainda não existir no servidor.
        "ref": "main",
        "description": notas,
        "assets": {"links": [
            {"name": nome,
             "url": endereco_pacote(repositorio, versao, nome),
             "direct_asset_path": f"/{nome}",
             "link_type": "package"}
            for nome in nomes
        ]},
    }


def enviar_arquivo(caminho: Path, url: str, token: str) -> None:
    """Envia em fluxo: o instalador passa de 280 MB e não cabe na memória
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
        description="Publica a versão preparada no GitLab da PRF")
    ap.add_argument("versao", help="Ex.: 1.15.3")
    ap.add_argument("--repositorio", default=REPOSITORIO_PADRAO,
                    help="grupo/projeto no GitLab da PRF")
    ap.add_argument("--conferir", action="store_true",
                    help="Não envia nada; só confere e mostra o que faria")
    args = ap.parse_args()

    instalador = DIST / f"SistemaTemis-{args.versao}-setup.exe"
    manifesto = DIST / "versao.json"
    for arquivo in (instalador, manifesto):
        if not arquivo.is_file():
            print(f"! não encontrado: {arquivo} — rode o publicar.py antes")
            return 1

    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    if dados.get("versao") != args.versao:
        print(f"! o versao.json é da {dados.get('versao')}, não da "
              f"{args.versao}")
        return 1
    if dados.get("sha256") != sha256(instalador):
        print("! o SHA-256 do instalador não confere com o versao.json")
        return 1
    esperado = (f"{SERVIDOR}/{args.repositorio}/-/releases/"
                f"v{args.versao}/downloads/{instalador.name}")
    if dados.get("url") != esperado:
        print("! o versao.json aponta o instalador para outro endereço:\n"
              f"    {dados.get('url')}\n  e a release vai servi-lo em:\n"
              f"    {esperado}")
        return 1

    corpo = corpo_release(args.repositorio, args.versao,
                          str(dados.get("notas", "")),
                          [instalador.name, manifesto.name])
    if args.conferir:
        print("Conferido. Seria enviado:")
        for arquivo in (instalador, manifesto):
            print(f"  {arquivo}  →  "
                  f"{endereco_pacote(args.repositorio, args.versao, arquivo.name)}")
        print(json.dumps(corpo, ensure_ascii=False, indent=2))
        return 0

    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        print("! defina a variável de ambiente GITLAB_TOKEN com um token "
              "pessoal de escopo `api`")
        return 1

    try:
        for arquivo in (instalador, manifesto):
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
    print("A partir de agora as estações recebem o aviso de atualização.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
