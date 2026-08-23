# Assinatura de código

O que fazer para que o Windows pare de barrar o instalador, e em que pé
está a candidatura ao SignPath.

---

## O problema

O instalador não é assinado. Isso gera duas reações do Windows, que são
coisas diferentes e costumam ser confundidas:

**SmartScreen** — mostra "O Windows protegeu o seu PC" e deixa prosseguir
por *Mais informações* → *Executar assim mesmo*.

**Smart App Control** — bloqueia, e **não tem lista de exceções**. Não
existe permitir por arquivo, por pasta ou por política de domínio. Ele
libera um programa por assinatura de autoridade certificadora reconhecida
ou por reputação acumulada nos servidores da Microsoft. A avaliação de
reputação é assíncrona, o que explica um comportamento observado na
prática: a mesma instalação, barrada na primeira tentativa, passou na
segunda.

Vale registrar duas informações que costumam circular erradas:

- **Certificado interno não resolve o Smart App Control.** Ele não consulta
  os certificados confiáveis da máquina nem do domínio, e sim a cadeia de
  confiança da própria Microsoft. Certificado emitido por CA interna
  funcionaria para o SmartScreen, não para o SAC.
- **Certificado EV não dá mais reputação imediata.** Esse comportamento foi
  removido em 2024; hoje EV e OV passam pelo mesmo acúmulo. Pagar o prêmio
  do EV só por causa do aviso deixou de se justificar.

## O caminho escolhido: SignPath Foundation

A [SignPath Foundation](https://signpath.org/) assina gratuitamente
projetos de código aberto, com certificado de nível OV. A chave privada
fica no HSM deles e nunca é manuseada por quem publica.

### Condições, e como este projeto as atende

| Condição | Situação |
|---|---|
| Licença aprovada pela OSI | ✅ AGPL-3.0-or-later, em [LICENSE](LICENSE) |
| Nenhum componente proprietário | ✅ inventário em [TERCEIROS.md](TERCEIROS.md) |
| Projeto mantido ativamente | ✅ histórico público de versões |
| Já publicado na forma a ser assinada | ✅ instaladores em Releases |
| Funcionalidade descrita na página de download | ✅ [README.md](README.md) e as notas de cada versão |
| Ausência de malware | ✅ código integralmente público |

### O que falta fazer

1. Candidatar-se em [signpath.org](https://signpath.org/), indicando o
   repositório e a página de download.
2. Aguardar a análise. O certificado é emitido em nome da **SignPath
   Foundation** — é ela que aparece como signatária, não o autor.
3. Ligar a assinatura ao fluxo de publicação: hoje o `build/publicar.py`
   compila e calcula o hash; o passo de assinatura entra entre a
   compilação do instalador e a escrita do `versao.json`, porque **assinar
   altera o arquivo e portanto o seu SHA-256**. Assinar depois de gerar o
   manifesto faria todas as estações recusarem a atualização.

## Alternativas, se a candidatura não prosperar

**Microsoft Store, como pacote MSIX** — a Microsoft assina por você, de
graça, e o Smart App Control confia em aplicativo da Store por construção.
Custa reempacotar como MSIX e submeter à revisão.

**Certificado OV de autoridade certificadora** — de US$ 150 a 300 por ano,
com token físico ou HSM em nuvem obrigatórios desde 2023. Sai em nome de
quem contrata.

**Azure Artifact Signing** — cerca de US$ 9,99/mês e integra bem com
publicação automatizada, mas está limitado a organizações dos Estados
Unidos, Canadá, União Europeia e Reino Unido. **Não atende o Brasil.**
