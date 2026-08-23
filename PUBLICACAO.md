# Publicar e atualizar o Sistema Têmis

Como colocar o sistema à disposição dos servidores e como as versões
seguintes chegam até eles.

---

## Como funciona a atualização

Ao abrir, alguns segundos depois de a janela aparecer, o sistema lê um
arquivo `versao.json` num endereço fixo e compara com a versão instalada.

- Se não houver nada novo, ou se a rede falhar, **nada aparece**. Quem
  abriu o sistema quer trabalhar.
- Havendo versão mais nova, abre uma janela com as novidades e três
  saídas: **Atualizar agora**, **Agora não** e **Não avisar mais sobre
  esta versão**. Nada é baixado antes do "sim".
- Autorizado, o instalador é baixado, **conferido pelo SHA-256** que
  consta do manifesto e só então executado. Se o arquivo não conferir, é
  descartado e a instalação não acontece.

A verificação pode ser desligada em **Sobre → Verificar atualizações ao
abrir o sistema**. Nada é enviado da máquina: é a leitura de um arquivo
estático, sem identificação do usuário nem da estação.

---

## Preparar uma versão

Um comando só, da raiz do projeto:

```bash
python build/publicar.py 1.1.0 --notas notas.txt
```

Ele escreve a versão nos três arquivos que a declaram (`temis/__init__.py`,
`build/installer.iss`, `build/version_info.txt`), compila o executável e o
instalador, e gera `dist/versao.json` com o hash calculado.

O hash sai daí de propósito: digitado à mão, um erro faz **toda** estação
recusar a atualização — comportamento correto, mas um enigma para quem
estiver do outro lado.

Ficam prontos dois arquivos em `dist/`:

- `SistemaTemis-1.1.0-setup.exe`
- `versao.json`

---

## Publicar no GitHub

**Uma vez, na primeira publicação:**

1. Crie o repositório que vai hospedar os arquivos.
2. Em `temis/atualizacao.py`, ajuste `URL_MANIFESTO` para o seu
   `usuario/repositorio`.
3. Passe o mesmo `usuario/repositorio` ao `publicar.py` pela opção
   `--repositorio`, ou mude o padrão no próprio script.

**A cada versão:**

1. Rode o `publicar.py`.
2. Crie uma *release* com a tag `v1.1.0` — o "v" importa, é o que o
   manifesto monta na URL.
3. Anexe os **dois** arquivos: o instalador e o `versao.json`.
4. Publique.

O endereço `releases/latest/download/versao.json` passa a apontar sozinho
para a versão nova. Não há nada a mexer no código a cada lançamento.

### O repositório precisa ser público

O download sem credencial só funciona em repositório público. Se o código
não puder ser aberto, a saída é manter **dois** repositórios: o código em
um privado e apenas os artefatos — instalador e manifesto — em um público
de distribuição.

### Quem pode escrever ali, pode instalar código nas estações

Vale dizer sem rodeio: quem tiver acesso de escrita ao repositório de
distribuição consegue fazer chegar um executável a todas as máquinas que
usam o sistema. O SHA-256 protege contra arquivo corrompido ou adulterado
no caminho, e o HTTPS contra interceptação — nenhum dos dois protege
contra o repositório comprometido. Portanto: **2FA obrigatório** na conta,
e acesso de escrita restrito a quem responde pelo sistema.

---

## O aviso do Windows

O instalador não é assinado, então o Windows vai reclamar:

- **SmartScreen** ("O Windows protegeu o seu PC") — clicar em *Mais
  informações* → *Executar assim mesmo*. Some depois que o arquivo ganha
  reputação.
- **Smart App Control** — este **não** tem como contornar arquivo a
  arquivo. Onde estiver ligado, a instalação é recusada de saída. Só sai
  desligando o recurso na estação (o que exige reinstalação do Windows
  para religar) ou assinando o executável.

A solução de verdade é um **certificado de assinatura de código**: resolve
os dois avisos e dá autenticidade real à atualização, porque aí é o
próprio Windows que verifica quem assinou antes de executar. Enquanto não
houver, convém avisar quem for instalar que o alerta vai aparecer — para
que ninguém aprenda a clicar em "executar assim mesmo" por hábito.

---

## Primeira distribuição

A primeira instalação é manual: as pessoas baixam o instalador da página
de releases. Da segunda versão em diante, o próprio sistema avisa.
