# Publicar uma versão do Sistema Têmis

Como uma versão nova chega a quem usa o sistema.

---

## Não há atualização automática

O programa não consulta se existe versão nova, não baixa instalador e não
se reinstala. A distribuição é manual:

1. o instalador novo é publicado na página de Releases do projeto no
   GitLab institucional (`git.prf.gov.br/sistemas-nacionais/temis`);
2. quem usa o sistema recebe um **e-mail** avisando da versão, com o que
   mudou, o endereço de download e o **resumo SHA-256** do instalador;
3. a pessoa baixa, confere o resumo e instala por cima da versão
   anterior. Os casos, o perfil e as sessões ficam onde estavam.

Até a 1.15.2 havia uma consulta automática ao GitHub na abertura. Ela foi
retirada do código: o sistema não abre conexão alguma sem ação do
operador.

---

## Preparar uma versão

Um comando só, da raiz do projeto:

```bash
python build/publicar.py 1.16.0
```

Ele escreve a versão nos três arquivos que a declaram (`temis/__init__.py`,
`build/installer.iss`, `build/version_info.txt`), compila o executável e o
instalador, e grava `dist/SHA256SUMS.txt` com o resumo do instalador e dos
arquivos do programa.

O resumo sai daí de propósito: copiado à mão para o e-mail, um erro de
digitação faria quem confere achar que o arquivo foi adulterado.

Ficam prontos em `dist/`:

- `SistemaTemis-1.16.0-setup.exe`
- `SHA256SUMS.txt`

As novidades da versão vão em `notas.txt`, que vira o texto da release e
serve de base para o e-mail.

### Sem uma máquina montada: compilar no GitHub

O workflow **Instalador** (`.github/workflows/instalador.yml`) faz o mesmo
que o `publicar.py` num Windows do GitHub, com as dependências fixadas no
`requirements.lock`. Ele baixa o FFmpeg e o scrcpy das versões declaradas
no `TERCEIROS.md` e confere cada um pelo SHA-256 antes de empacotar.

1. Suba o commit com a versão nova já escrita nos três arquivos.
2. **Actions → Instalador → Run workflow**, informe a versão. A execução
   recusa se ela não for a de `temis/__init__.py`.
3. Ao fim, baixe o artefato `SistemaTemis-X.Y.Z`: traz o instalador, o
   `SHA256SUMS.txt` e a relação de componentes. O resumo da execução
   mostra o commit, o SHA-256 e o autoteste do pacote.

O workflow não publica nada.

---

## Publicar no GitLab

Com um token pessoal de escopo `api` (papel Developer ou mais no projeto)
na variável `GITLAB_TOKEN`:

```bash
python build/publicar_gitlab.py 1.16.0
```

Com `--conferir`, ele só mostra o que faria. O script confere o SHA-256
do instalador contra o `SHA256SUMS.txt`, envia os dois arquivos ao
registro de pacotes do projeto e cria a release `v1.16.0`, com as notas e
o resumo no texto. No GitLab a release não guarda binário, só aponta para
endereços; por isso o envio ao registro vem antes.

O projeto é interno: a página de download pede o login institucional.

---

## O e-mail da versão

Modelo:

> **Sistema Têmis 1.16.0 disponível**
>
> *(o que mudou, a partir do `notas.txt`)*
>
> Baixe em: `https://git.prf.gov.br/sistemas-nacionais/temis/-/releases/v1.16.0`
>
> Antes de instalar, confira o resumo do arquivo no PowerShell:
> `Get-FileHash SistemaTemis-1.16.0-setup.exe -Algorithm SHA256`
>
> O resultado deve ser: `<SHA-256 do SHA256SUMS.txt>`
>
> Se não conferir, não instale e avise a Corregedoria-Geral.

---

## O aviso do Windows

O instalador não é assinado — a instituição não dispõe de certificado de
assinatura de código —, então o Windows avisa:

- **SmartScreen** ("O Windows protegeu o seu PC") — *Mais informações* →
  *Executar assim mesmo*. Some depois que o arquivo ganha reputação.
- **Smart App Control** — não tem exceção arquivo a arquivo. Onde estiver
  ligado, a instalação pode ser recusada; tentar de novo minutos depois
  costuma funcionar, porque a avaliação de reputação é assíncrona.

Convém dizer no e-mail que o alerta vai aparecer, e que a conferência do
SHA-256 é o que garante que o arquivo é o publicado — para que ninguém
aprenda a clicar em "executar assim mesmo" sem conferir.

Antivírus corporativo que ponha o programa em quarentena é outro caso,
tratado em [ASSINATURA.md](ASSINATURA.md#antivírus-corporativo).
