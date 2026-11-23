"""
Assinatura Ed25519, em Python puro.

Serve a uma coisa só: conferir que o manifesto de atualização foi
assinado por quem detém a chave de publicação — e, do outro lado,
produzir essa assinatura na máquina de quem publica.

Por que escrito aqui, e não trazido de uma biblioteca: a conferência
roda em toda estação, a cada abertura do programa, e uma biblioteca de
criptografia inteira no instalador, para verificar uma assinatura por
dia, seria peso e superfície a mais. O algoritmo é o da RFC 8032,
seção 6, transcrito da implementação de referência que a própria norma
publica, e a suíte o confere contra os vetores de teste da norma e
contra uma biblioteca independente.

Sobre o que isto não é: implementação de tempo constante. Não precisa
ser. A conferência só lida com dado público — a chave pública, a
mensagem e a assinatura —, e a assinatura é feita fora de linha, na
máquina de quem guarda a chave, sem ninguém a medir o tempo que leva.
"""

from __future__ import annotations

import hashlib
import os

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_RAIZ_DE_MENOS_UM = pow(2, (_P - 1) // 4, _P)


def _sha512(dados: bytes) -> bytes:
    return hashlib.sha512(dados).digest()


def _inverso(x: int) -> int:
    return pow(x, _P - 2, _P)


# Pontos em coordenadas estendidas (X, Y, Z, T), com x = X/Z, y = Y/Z e
# x*y = T/Z.

def _soma(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _vezes(n: int, ponto):
    resultado = (0, 1, 1, 0)                     # o elemento neutro
    while n > 0:
        if n & 1:
            resultado = _soma(resultado, ponto)
        ponto = _soma(ponto, ponto)
        n >>= 1
    return resultado


def _iguais(a, b) -> bool:
    if (a[0] * b[2] - b[0] * a[2]) % _P != 0:
        return False
    return (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _x_de(y: int, sinal: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inverso(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sinal else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _RAIZ_DE_MENOS_UM % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sinal:
        x = _P - x
    return x


_GY = 4 * _inverso(5) % _P
_GX = _x_de(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _comprimir(ponto) -> bytes:
    zinv = _inverso(ponto[2])
    x, y = ponto[0] * zinv % _P, ponto[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _descomprimir(dados: bytes):
    if len(dados) != 32:
        return None
    y = int.from_bytes(dados, "little")
    sinal = y >> 255
    y &= (1 << 255) - 1
    x = _x_de(y, sinal)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _expandir(semente: bytes):
    if len(semente) != 32:
        raise ValueError("a chave privada tem de ter 32 bytes")
    h = _sha512(semente)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _modl(dados: bytes) -> int:
    return int.from_bytes(_sha512(dados), "little") % _L


# ─────────────────────────────────────────
#  O QUE SE USA DE FORA
# ─────────────────────────────────────────

def nova_semente() -> bytes:
    """32 bytes do gerador de números aleatórios do sistema operacional."""
    return os.urandom(32)


def publica_de(semente: bytes) -> bytes:
    """A chave pública correspondente à chave privada (a semente)."""
    a, _ = _expandir(semente)
    return _comprimir(_vezes(a, _G))


def assinar(semente: bytes, mensagem: bytes) -> bytes:
    """A assinatura da mensagem, com 64 bytes."""
    a, prefixo = _expandir(semente)
    A = _comprimir(_vezes(a, _G))
    r = _modl(prefixo + mensagem)
    R = _comprimir(_vezes(r, _G))
    h = _modl(R + A + mensagem)
    s = (r + h * a) % _L
    return R + int.to_bytes(s, 32, "little")


def confere(publica: bytes, mensagem: bytes, assinatura: bytes) -> bool:
    """A assinatura é desta mensagem, por esta chave? Nunca levanta."""
    try:
        if len(publica) != 32 or len(assinatura) != 64:
            return False
        A = _descomprimir(publica)
        R = _descomprimir(assinatura[:32])
        if A is None or R is None:
            return False
        s = int.from_bytes(assinatura[32:], "little")
        if s >= _L:
            return False
        h = _modl(assinatura[:32] + publica + mensagem)
        return _iguais(_vezes(s, _G), _soma(R, _vezes(h, A)))
    except Exception:                                       # noqa: BLE001
        return False
