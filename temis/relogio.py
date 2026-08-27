"""A hora das peças, e o que se pode afirmar sobre ela.

Termo de cadeia de custódia é cronologia: o percurso do vestígio se
demonstra por instantes, e instante afirmado sem qualificação é
afirmação sem lastro — que é exatamente o que o Superior Tribunal de
Justiça deixou de aceitar da prova digital.

O relógio de uma estação comum não é fonte de tempo confiável. Pode
estar adiantado, atrasado, ou nunca ter sincronizado com servidor
algum. Nesta máquina, ao escrever este módulo, o Windows respondia
"Fonte: Local CMOS Clock" e "Última Sincronização com Êxito: Não
especificado" — configurado para buscar `time.windows.com`, e operando
pelo relógio interno da placa.

Nada disso impede a peça de registrar a hora. Impede que ela a registre
calada. O sistema apura o estado da sincronização e o declara junto do
carimbo, de modo que quem lê saiba o peso do que está lendo — e a peça
não prometa carimbo de tempo certificado, que ela não tem.
"""

from __future__ import annotations

import datetime
import re
import sys

#: Como a hora aparece nas peças.
FORMATO = "%d/%m/%Y às %H:%M:%S"


def agora() -> datetime.datetime:
    """O instante presente, com o fuso da estação junto.

    Sempre consciente de fuso. Instante sem fuso não se compara com
    instante de outra máquina, e comparar instantes é metade do que uma
    cadeia de custódia faz.
    """
    return datetime.datetime.now().astimezone()


def deslocamento(quando: datetime.datetime | None = None) -> str:
    """O fuso, escrito como UTC−03:00."""
    quando = quando or agora()
    bruto = quando.strftime("%z") or "+0000"
    # Hífen comum, e não o sinal de menos tipográfico: o texto da peça é
    # copiado para o SEI, e o U+2212 não sobrevive a toda codificação
    # pelo caminho. Legibilidade que se perde na cópia não é legibilidade.
    sinal = "-" if bruto[0] == "-" else "+"
    return f"UTC{sinal}{bruto[1:3]}:{bruto[3:5]}"


def carimbo(quando: datetime.datetime | None = None) -> str:
    """A hora como ela sai impressa, com o fuso."""
    quando = quando or agora()
    return f"{quando.strftime(FORMATO)} ({deslocamento(quando)})"


def iso(quando: datetime.datetime | None = None) -> str:
    """A mesma hora em forma de máquina, para gravar em roteiro."""
    return (quando or agora()).isoformat(timespec="seconds")


#: O que o Windows respondeu sobre o relógio, apurado uma vez por sessão.
#: Perguntar custa a abertura de um processo, e a resposta não muda entre
#: duas peças emitidas com minutos de diferença.
_ESTADO: list = []


def _configuracao() -> tuple:
    """(tipo, servidor) configurados no serviço de tempo do Windows.

    Lidos do registro, e não da saída do `w32tm`: o registro responde em
    chave fixa, enquanto a saída do comando vem traduzida para o idioma
    do sistema e muda de rótulo entre versões.
    """
    if sys.platform != "win32":
        return "", ""
    try:
        import winreg
        caminho = r"SYSTEM\CurrentControlSet\Services\W32Time\Parameters"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, caminho) as chave:
            tipo = winreg.QueryValueEx(chave, "Type")[0]
            servidor = winreg.QueryValueEx(chave, "NtpServer")[0]
        # O servidor vem com sinalizadores colados: "time.windows.com,0x9".
        return str(tipo), str(servidor).split(",")[0]
    except Exception:                                   # noqa: BLE001
        return "", ""


def _status() -> tuple:
    """(sincronizado, fonte) segundo o próprio Windows.

    `sincronizado` é True, False, ou None quando não se apurou — e None
    não é False: dizer "não sincronizado" sem ter apurado seria a peça
    afirmando defeito que não constatou.

    O indicador de salto é o campo que responde: 0 é relógio em ordem, 3
    é relógio não sincronizado. Vem rotulado em português ou em inglês
    conforme o Windows instalado, e por isso se procura pelos dois.
    """
    if sys.platform != "win32":
        return None, ""
    try:
        import subprocess
        r = subprocess.run(["w32tm", "/query", "/status"],
                           capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
        saida = (r.stdout or "") + (r.stderr or "")
    except Exception:                                   # noqa: BLE001
        return None, ""

    salto = re.search(r"(?:Leap Indicator|Indicador de Salto)\D*?(\d)", saida)
    fonte = re.search(r"(?:^|\n)\s*(?:Source|Fonte):\s*(.+)", saida)
    sincronizado = None
    if salto:
        sincronizado = salto.group(1) == "0"
    return sincronizado, (fonte.group(1).strip() if fonte else "")


def estado() -> dict:
    """O que se sabe do relógio: apurado uma vez, reaproveitado depois."""
    if not _ESTADO:
        sincronizado, fonte = _status()
        tipo, servidor = _configuracao()
        _ESTADO.append({"sincronizado": sincronizado, "fonte": fonte,
                        "tipo": tipo, "servidor": servidor})
    return _ESTADO[0]


def ressalva() -> str:
    """O parágrafo que qualifica a hora impressa na peça.

    Diz três coisas, nesta ordem: de onde vem a hora, em que estado
    estava o relógio, e o que a peça **não** está afirmando. A terceira é
    a que impede que se atribua ao carimbo o peso de um carimbo de tempo
    certificado, que ele não tem.
    """
    e = estado()
    texto = ("As horas registradas nesta peça vêm do relógio desta estação, "
             "no fuso " + deslocamento() + ". ")

    if e["sincronizado"] is True:
        texto += "No momento da emissão, o relógio constava como sincronizado"
        texto += (f' com "{e["fonte"]}"' if e["fonte"] else "")
        texto += ". "
    elif e["sincronizado"] is False:
        # Sem asterisco de ênfase: esta frase é escapada e impressa como
        # texto, e o asterisco sairia literal no meio da peça.
        texto += ("No momento da emissão, o serviço de tempo do Windows "
                  "informava relógio NÃO SINCRONIZADO")
        texto += (f', operando por "{e["fonte"]}"' if e["fonte"] else "")
        if e["servidor"]:
            texto += (", ainda que configurado para sincronizar com "
                      f'"{e["servidor"]}"')
        texto += (". A hora deve ser lida com essa ressalva: pode divergir "
                  "da hora legal. ")
    else:
        texto += ("Não foi possível apurar, na emissão, o estado de "
                  "sincronização do relógio. ")

    return (texto + "Esta peça não constitui carimbo de tempo certificado "
            "por terceira parte, e nada afirma sobre a hora legal.")
