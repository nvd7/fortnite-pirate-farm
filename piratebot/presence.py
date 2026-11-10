"""Detecção de presença do usuário no Windows.

O farm AFK só deve continuar enquanto houver alguém por perto. Este módulo
consulta o tempo desde a última entrada de teclado/mouse e verifica se a sessão
do Windows está bloqueada. Quando o limite é atingido, o bot para em vez de
continuar farmando sozinho por horas.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

# A API só existe no Windows; em outros sistemas os testes continuam rodando
# com valores neutros.
if os.name == "nt":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _LastInputInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("dwTime", wintypes.DWORD),
        ]

    _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
    _user32.GetLastInputInfo.restype = wintypes.BOOL
    _user32.OpenInputDesktop.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _user32.OpenInputDesktop.restype = wintypes.HANDLE
    _user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    _user32.CloseDesktop.restype = wintypes.BOOL
    _kernel32.GetTickCount.restype = wintypes.DWORD
else:  # pragma: no cover - o aplicativo é distribuído para Windows
    _user32 = None
    _kernel32 = None
    _LastInputInfo = None

# DESKTOP_SWITCHDESKTOP: necessário para abrir o desktop de entrada.
_DESKTOP_SWITCHDESKTOP = 0x0100


def idle_seconds() -> float:
    """Segundos desde a última entrada de teclado ou mouse."""
    if os.name != "nt" or _user32 is None or _kernel32 is None:
        return 0.0
    info = _LastInputInfo()  # type: ignore[misc]
    info.cbSize = ctypes.sizeof(info)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    now = int(_kernel32.GetTickCount())
    elapsed = (now - int(info.dwTime)) & 0xFFFFFFFF
    return elapsed / 1000.0


def session_locked() -> bool:
    """True quando a sessão do Windows está bloqueada ou sem desktop acessível."""
    if os.name != "nt" or _user32 is None:
        return False
    handle = _user32.OpenInputDesktop(0, False, _DESKTOP_SWITCHDESKTOP)
    if not handle:
        return True
    try:
        return False
    finally:
        _user32.CloseDesktop(handle)


def idle_limit_reached(idle: float, limit_minutes: int) -> bool:
    """Regra pura para testar o limite de inatividade."""
    return limit_minutes > 0 and idle >= limit_minutes * 60.0
