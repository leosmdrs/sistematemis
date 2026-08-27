# Provas

Prova de comportamento das ferramentas. Coisa diferente do autoteste.

O `run_temis.py --autoteste` responde se **esta instalação está inteira**
— se as bibliotecas vieram, se o FFmpeg está no lugar, se o OCR do
Windows atende em pt-BR. Ele roda na estação de quem instalou e serve ao
suporte. Não responde se uma operação calcula certo.

O que está aqui responde isso, e roda em qualquer máquina:

```bash
python -m unittest discover -s provas -p "prova_*.py" -v
```

Nada aqui abre janela, lê arquivo do disco do usuário nem toca na rede.
São só dados montados no próprio teste e o resultado conferido.

## Por que passaram a ser versionadas

Até a versão 1.7.3 as provas de cada entrega foram escritas fora da
árvore do projeto. Elas provaram o que precisavam provar no dia, e
depois não viajaram com o repositório: quem clonasse em outra máquina
recebia o código sem meio de reconferi-lo, e cada alteração seguinte
partia de confiança em vez de verificação.

Numa ferramenta cujo propósito inteiro é substituir afirmação por
conferência, isso era uma incoerência do projeto consigo mesmo.

## Convenção

* Um arquivo por ferramenta, `prova_<ferramenta>.py`.
* `unittest` da biblioteca padrão — nada a instalar além do que o
  `requirements.txt` já traz.
* O nome de cada prova diz o que ela garante, e não o método que exercita.
