"""Interface gráfica do Pirate Farm."""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

# Deixa as coordenadas em pixels físicos (importante em telas com escala).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from piratebot import power
from piratebot.bot import PHASE_LABELS, Phase, PirateBot
from piratebot.config import (
    ASSETS,
    LOGS,
    ROOT,
    WebhookConfig,
    load_config,
    save_config,
)
from piratebot.hotkey import HotkeyListener
from piratebot.retention import prune_snapshots
from piratebot.rewards import (
    OcrReader,
    banner_score,
    parse_reward_text,
    reward_badge_score,
)
from piratebot.vision import (
    ScreenGrabber,
    TokenDetector,
    find_game_window,
    imwrite_u,
)
from piratebot.webhook import mask_webhook_url, send_test, validate_webhook_url

APP_TITLE = "Pirate Farm — Fortnite"
APP_VERSION = "1.3.0"

# Paleta do modo escuro.
BG = "#0a0f18"
BG_SOFT = "#0e1624"
CARD = "#101a2a"
CARD_BORDER = "#1e2b40"
SUBTLE = "#162235"
SUBTLE_HOVER = "#1f3049"
TEXT = "#e8eef8"
MUTED = "#94a7c0"
DIM = "#5f728c"
GOLD = "#f4c95d"
GREEN = "#34d399"
GREEN_DARK = "#0f766e"
GREEN_DEEP = "#123c33"
RED = "#f87171"
RED_DARK = "#8f1d1d"
AMBER = "#fbbf24"
BLUE = "#60a5fa"

PHASE_STYLE = {
    Phase.STARTING.value: ("Iniciando...", BLUE),
    Phase.LOBBY.value: ("No lobby", BLUE),
    Phase.QUEUING.value: ("Procurando partida", "#c084fc"),
    Phase.MATCH.value: ("Em partida — AFK", "#2dd4bf"),
    Phase.POSTMATCH.value: ("Fim de partida", AMBER),
    Phase.FINISHED.value: ("TOKEN ENCONTRADO!", "#4ade80"),
    Phase.ERROR.value: ("Erro", RED),
    Phase.STOPPED.value: ("Parado", "#94a3b8"),
}


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class PirateFarmApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = load_config()
        self.ui_queue: "queue.Queue[dict]" = queue.Queue()
        self.stop_event = threading.Event()
        self.manual_token = threading.Event()
        self.bot: PirateBot | None = None
        self.hotkey: HotkeyListener | None = None
        self._logs_opened = False
        self._success_scheduled = False
        self._log_line_count = 0
        self._manual_awake = False
        self._last_power_refresh = 0.0
        self._last_snapshot_refresh = 0.0
        self._build_ui()
        self._start_hotkey()
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry("900x880")
        self.root.minsize(840, 850)
        self.root.configure(bg=BG)

        try:
            icon = tk.PhotoImage(file=str(ASSETS / "logo_256.png"))
            self.root.iconphoto(True, icon)
            self._icon = icon
        except Exception:
            pass

        container = tk.Frame(self.root, bg=BG, padx=20, pady=16)
        container.pack(fill="both", expand=True)

        # ---------------------------------------------------------- cabeçalho
        header = tk.Frame(container, bg=BG)
        header.pack(fill="x", pady=(0, 12))
        try:
            self._header_logo = tk.PhotoImage(file=str(ASSETS / "logo_64.png"))
            tk.Label(header, image=self._header_logo, bg=BG).pack(side="left", padx=(0, 14))
        except Exception:
            self._header_logo = None

        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(
            titles,
            text="Pirate Farm",
            font=("Segoe UI", 23, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(anchor="w")
        tk.Label(
            titles,
            text=f"Farm AFK do token Pirate Shop Access · Fortnite · v{APP_VERSION}",
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BG,
        ).pack(anchor="w", pady=(1, 0))
        tk.Label(
            header,
            text="PT-BR",
            font=("Segoe UI", 8, "bold"),
            fg="#86efac",
            bg=GREEN_DEEP,
            padx=8,
            pady=4,
        ).pack(side="right", anchor="n")

        # --------------------------------------------------------------- abas
        tabbar = tk.Frame(container, bg=BG)
        tabbar.pack(fill="x", pady=(0, 10))
        self._tabs: dict[str, tk.Frame] = {}
        self._tab_buttons: dict[str, tk.Button] = {}
        self._tab_labels = {"farm": "Farm", "webhook": "Webhook"}
        for key in ("farm", "webhook"):
            button = tk.Button(
                tabbar,
                text=f"  {self._tab_labels[key]}  ",
                font=("Segoe UI", 10, "bold"),
                bg=BG,
                fg=MUTED,
                activebackground=SUBTLE_HOVER,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                highlightthickness=0,
                padx=8,
                pady=8,
                cursor="hand2",
                command=lambda k=key: self._show_tab(k),
            )
            button.pack(side="left", padx=(0, 4))
            self._tab_buttons[key] = button
        tk.Label(
            tabbar,
            text="F8 = parada de emergência",
            font=("Segoe UI", 9),
            fg=DIM,
            bg=BG,
        ).pack(side="right")
        self._tabs["farm"] = tk.Frame(container, bg=BG)
        self._tabs["webhook"] = tk.Frame(container, bg=BG)
        self._active_tab = "farm"

        # ------------------------------------------------------------- status
        status_card = tk.Frame(
            self._tabs["farm"],
            bg=CARD,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        status_card.pack(fill="x")

        self.status_label = tk.Label(
            status_card,
            text="Pronto para iniciar",
            font=("Segoe UI", 18, "bold"),
            fg=MUTED,
            bg=CARD,
            anchor="w",
        )
        self.status_label.pack(fill="x")

        self.detail_label = tk.Label(
            status_card,
            text=(
                "Abra o Fortnite no lobby, com Battle Royale e Squad + Fill, "
                "e clique em INICIAR."
            ),
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=CARD,
            anchor="w",
            justify="left",
            wraplength=670,
        )
        self.detail_label.pack(fill="x", pady=(3, 10))

        stats = tk.Frame(status_card, bg=CARD)
        stats.pack(fill="x")
        self.matches_label = tk.Label(
            stats,
            text="Partidas: 0",
            font=("Segoe UI", 10, "bold"),
            fg="#cbd5e1",
            bg=CARD,
        )
        self.matches_label.pack(side="left")
        self.token_label = tk.Label(
            stats,
            text="Token: não",
            font=("Segoe UI", 10, "bold"),
            fg=RED,
            bg=CARD,
        )
        self.token_label.pack(side="left", padx=(24, 0))
        self.reward_label = tk.Label(
            stats,
            text="Recompensas: 0",
            font=("Segoe UI", 10, "bold"),
            fg=MUTED,
            bg=CARD,
        )
        self.reward_label.pack(side="left", padx=(24, 0))
        self.time_label = tk.Label(
            stats,
            text="Tempo: 00:00:00",
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=CARD,
        )
        self.time_label.pack(side="right")

        # ----------------------------------------------------------- controles
        controls = tk.Frame(self._tabs["farm"], bg=BG)
        controls.pack(fill="x", pady=(14, 8))

        self.start_button = tk.Button(
            controls,
            text="INICIAR",
            font=("Segoe UI", 12, "bold"),
            bg="#15803d",
            fg="#ffffff",
            activebackground="#166534",
            activeforeground="#ffffff",
            disabledforeground="#64748b",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=24,
            pady=10,
            cursor="hand2",
            command=self._start_bot,
        )
        self.start_button.pack(side="left")

        self.stop_button = tk.Button(
            controls,
            text="PARAR (F8)",
            font=("Segoe UI", 11, "bold"),
            bg=RED_DARK,
            fg="#ffffff",
            activebackground="#7f1d1d",
            activeforeground="#ffffff",
            disabledforeground="#64748b",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=18,
            pady=10,
            cursor="hand2",
            state="disabled",
            command=lambda: self._stop_bot("Parado pelo usuário."),
        )
        self.stop_button.pack(side="left", padx=(10, 0))

        self.token_button = tk.Button(
            controls,
            text="Já tenho o token",
            font=("Segoe UI", 10, "bold"),
            bg=GOLD,
            fg="#1c1917",
            activebackground="#d97706",
            activeforeground="#1c1917",
            disabledforeground="#64748b",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=15,
            pady=10,
            cursor="hand2",
            state="disabled",
            command=self._mark_token,
        )
        self.token_button.pack(side="left", padx=(10, 0))

        # ------------------------------------------------------------ opções
        options = tk.Frame(self._tabs["farm"], bg=BG)
        options.pack(fill="x", pady=(0, 8))

        self.bg_var = tk.BooleanVar(value=self.config.behavior.background_mode)
        self.sim_var = tk.BooleanVar(value=self.config.behavior.dry_run)
        self.runtime_var = tk.StringVar(
            value=str(self.config.behavior.max_runtime_minutes)
        )
        self.bg_chip = self._chip(
            options, "Segundo plano", self.bg_var, command=self._update_mode_hint
        )
        self.bg_chip.pack(side="left")
        self.sim_chip = self._chip(options, "Simulação", self.sim_var)
        self.sim_chip.pack(side="left", padx=(8, 0))

        runtime_box = tk.Frame(options, bg=BG)
        runtime_box.pack(side="left", padx=(16, 0))
        tk.Label(
            runtime_box,
            text="Limite (min)",
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=BG,
        ).pack(side="left", padx=(0, 5))
        self.runtime_spin = tk.Spinbox(
            runtime_box,
            textvariable=self.runtime_var,
            from_=0,
            to=1440,
            width=5,
            font=("Segoe UI", 9),
            bg="#0a1422",
            fg=TEXT,
            buttonbackground=SUBTLE,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=GOLD,
            justify="center",
        )
        self.runtime_spin.pack(side="left")
        self.runtime_var.trace_add(
            "write", lambda *_args: self._update_mode_hint()
        )

        self.power_button = tk.Button(
            options,
            text="○  Manter PC acordado",
            font=("Segoe UI", 9, "bold"),
            bg=SUBTLE,
            fg=MUTED,
            activebackground=SUBTLE_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=11,
            pady=6,
            cursor="hand2",
            command=self._toggle_keep_awake,
        )
        self.power_button.pack(side="right")
        self.power_label = tk.Label(
            options,
            text="PC acordado: não",
            font=("Segoe UI", 9),
            fg=DIM,
            bg=BG,
        )
        self.power_label.pack(side="right", padx=(0, 10))

        # ---------------------------------------------------- proteção de sessão
        safety_card = tk.Frame(
            self._tabs["farm"],
            bg=CARD,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=16,
            pady=10,
        )
        safety_card.pack(fill="x", pady=(0, 10))
        safety_head = tk.Frame(safety_card, bg=CARD)
        safety_head.pack(fill="x")
        tk.Label(
            safety_head,
            text="PROTEÇÃO DE SESSÃO",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED,
            bg=CARD,
        ).pack(side="left")
        tk.Label(
            safety_head,
            text="sem simular movimento ou presença",
            font=("Segoe UI", 8),
            fg=DIM,
            bg=CARD,
        ).pack(side="right")

        safety_row = tk.Frame(safety_card, bg=CARD)
        safety_row.pack(fill="x", pady=(7, 0))
        self.idle_var = tk.BooleanVar(
            value=self.config.behavior.idle_stop_minutes > 0
        )
        self.afk_var = tk.BooleanVar(
            value=self.config.behavior.stop_on_afk_warning
        )
        self.idle_minutes_var = tk.StringVar(
            value=str(self.config.behavior.idle_stop_minutes or 30)
        )
        self.idle_chip = self._chip(
            safety_row,
            "Parar sem atividade",
            self.idle_var,
            command=self._refresh_safety_controls,
        )
        self.idle_chip.pack(side="left")
        idle_box = tk.Frame(safety_row, bg=CARD)
        idle_box.pack(side="left", padx=(8, 0))
        tk.Label(
            idle_box,
            text="min",
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=CARD,
        ).pack(side="left", padx=(0, 4))
        self.idle_spin = tk.Spinbox(
            idle_box,
            textvariable=self.idle_minutes_var,
            from_=5,
            to=720,
            width=4,
            font=("Segoe UI", 9),
            bg="#0a1422",
            fg=TEXT,
            buttonbackground=SUBTLE,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=GOLD,
            justify="center",
        )
        self.idle_spin.pack(side="left")
        self.afk_chip = self._chip(
            safety_row,
            "Parar em aviso de AFK",
            self.afk_var,
            command=self._update_mode_hint,
        )
        self.afk_chip.pack(side="left", padx=(16, 0))
        tk.Label(
            safety_card,
            text=(
                "O farm para quando o teclado/mouse ficam parados, quando o "
                "Windows bloqueia ou quando o jogo mostra “AINDA ESTÁ AÍ?”/aviso "
                "de inatividade. O app não clica em CONTINUAR JOGANDO nesses casos."
            ),
            font=("Segoe UI", 8),
            fg=DIM,
            bg=CARD,
            anchor="w",
            justify="left",
            wraplength=800,
        ).pack(fill="x", pady=(6, 0))
        self._refresh_safety_controls()

        # ------------------------------------------------------------- tools
        tools = tk.Frame(self._tabs["farm"], bg=BG)
        tools.pack(fill="x", pady=(0, 10))
        self._tool_button(tools, "Testar detecção agora", self._test_detection).pack(
            side="left"
        )
        self._tool_button(tools, "Abrir logs", self._open_logs).pack(
            side="left", padx=(8, 0)
        )
        self._tool_button(tools, "Limpar registro", self._clear_log).pack(
            side="left", padx=(8, 0)
        )

        # -------------------------------------------------------- dica de modo
        self.mode_hint_card = tk.Frame(
            self._tabs["farm"],
            bg="#10243a",
            highlightbackground="#1e3a5f",
            highlightthickness=1,
            padx=13,
            pady=9,
        )
        self.mode_hint_card.pack(fill="x", pady=(0, 10))
        self.mode_hint = tk.Label(
            self.mode_hint_card,
            text="",
            font=("Segoe UI", 9),
            fg="#bfdbfe",
            bg="#10243a",
            anchor="w",
            justify="left",
            wraplength=670,
        )
        self.mode_hint.pack(fill="x")
        self._update_mode_hint()

        # ---------------------------------------------------------- capturas
        self.max_files_var = tk.StringVar(
            value=str(self.config.storage.snapshot_max_files)
        )
        self.max_age_var = tk.StringVar(
            value=str(self.config.storage.snapshot_max_age_days)
        )
        self.min_keep_var = tk.StringVar(
            value=str(self.config.storage.snapshot_min_keep)
        )
        self.grace_var = tk.StringVar(
            value=str(self.config.storage.snapshot_grace_seconds)
        )

        storage_card = tk.Frame(
            self._tabs["farm"],
            bg=CARD,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=16,
            pady=10,
        )
        storage_card.pack(fill="x", pady=(0, 10))
        storage_head = tk.Frame(storage_card, bg=CARD)
        storage_head.pack(fill="x")
        tk.Label(
            storage_head,
            text="CAPTURAS AUTOMÁTICAS",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED,
            bg=CARD,
        ).pack(side="left")
        self.snapshot_label = tk.Label(
            storage_head,
            text="calculando...",
            font=("Segoe UI", 8),
            fg=DIM,
            bg=CARD,
        )
        self.snapshot_label.pack(side="left", padx=(10, 0))
        self._tool_button(
            storage_head, "Abrir pasta", self._open_snapshots
        ).pack(side="right")
        self.clean_button = self._tool_button(
            storage_head, "Limpar agora", self._clean_snapshots
        )
        self.clean_button.pack(side="right", padx=(0, 6))

        storage_fields = tk.Frame(storage_card, bg=CARD)
        storage_fields.pack(fill="x", pady=(7, 0))
        self._spin_field(
            storage_fields, "Máx. arquivos", self.max_files_var, 0, 5000, 6
        )
        self._spin_field(
            storage_fields, "Idade máx. (dias)", self.max_age_var, 0, 365, 5
        )
        self._spin_field(
            storage_fields, "Mínimo a manter", self.min_keep_var, 0, 5000, 6
        )
        self._spin_field(
            storage_fields, "Carência (s)", self.grace_var, 0, 86400, 6
        )
        tk.Label(
            storage_card,
            text=(
                "A limpeza preserva as evidências do token e as capturas mais "
                "recentes. 0 desativa o critério."
            ),
            font=("Segoe UI", 8),
            fg=DIM,
            bg=CARD,
            anchor="w",
        ).pack(fill="x", pady=(5, 0))

        # --------------------------------------------------------------- log
        log_header = tk.Frame(self._tabs["farm"], bg=BG)
        log_header.pack(fill="x")
        tk.Label(
            log_header,
            text="REGISTRO",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED,
            bg=BG,
        ).pack(side="left")
        tk.Label(
            log_header,
            text="tudo é gravado em logs\\piratefarm_*.log",
            font=("Segoe UI", 8),
            fg=DIM,
            bg=BG,
        ).pack(side="right")

        log_frame = tk.Frame(
            self._tabs["farm"],
            bg="#08101d",
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
        )
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap="word",
            bg="#08101d",
            fg="#dbe7f5",
            insertbackground="#dbe7f5",
            selectbackground="#1d4ed8",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=8,
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.tag_config("ts", foreground="#64748b")
        self.log_text.tag_config("info", foreground="#dbe7f5")
        self.log_text.tag_config("success", foreground="#6ee7b7")
        self.log_text.tag_config("warn", foreground="#fbbf24")
        self.log_text.tag_config("error", foreground="#f87171")
        self.log_text.tag_config("debug", foreground="#7c8ba1")
        self.log_text.configure(state="disabled")

        footer = tk.Frame(container, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        tk.Label(
            footer,
            text="Capturas locais · webhook opcional",
            font=("Segoe UI", 8),
            fg=DIM,
            bg=BG,
        ).pack(side="left")
        tk.Label(
            footer,
            text="Squad Fill · interface em português",
            font=("Segoe UI", 8),
            fg=DIM,
            bg=BG,
        ).pack(side="right")

        # A barra de título só aceita o modo escuro depois que a janela é
        # realmente mapeada e ativada pelo Windows; reaplicamos ao mapear e
        # sempre que a janela ganha foco (o DWM descarta a cor no primeiro
        # desenho se ela for definida cedo demais).
        self.root.after(120, self._focus_window)
        self.root.bind(
            "<Map>",
            lambda _event: self.root.after(
                250, lambda: self._apply_dark_titlebar(self.root)
            ),
        )
        self.root.bind(
            "<FocusIn>",
            lambda _event: self._apply_dark_titlebar(self.root),
        )
        for delay in (350, 1500, 3000):
            self.root.after(delay, lambda: self._apply_dark_titlebar(self.root))

        self._build_webhook_tab()
        self._show_tab("farm")
        self._refresh_snapshot_stats()

    # ------------------------------------------------------------- widgets
    def _chip(self, parent, text: str, variable: tk.BooleanVar, command=None):
        button = tk.Button(
            parent,
            font=("Segoe UI", 9, "bold"),
            bg=SUBTLE,
            fg=MUTED,
            activebackground=SUBTLE_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=11,
            pady=6,
            cursor="hand2",
            anchor="w",
        )

        def refresh() -> None:
            selected = bool(variable.get())
            button.config(
                text=("●  " if selected else "○  ") + text,
                bg=GREEN_DEEP if selected else SUBTLE,
                fg="#86efac" if selected else MUTED,
                activebackground=GREEN_DEEP if selected else SUBTLE_HOVER,
                activeforeground="#bbf7d0" if selected else TEXT,
            )

        def toggle() -> None:
            variable.set(not variable.get())
            refresh()
            if command is not None:
                command()

        button.config(command=toggle)
        refresh()
        return button

    def _tool_button(self, parent, text: str, command):
        return tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 9),
            bg=SUBTLE,
            fg="#cbd5e1",
            activebackground=SUBTLE_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=command,
        )

    def _spin_field(
        self,
        parent,
        label: str,
        variable: tk.StringVar,
        minimum: int,
        maximum: int,
        width: int = 6,
    ) -> tk.Spinbox:
        box = tk.Frame(parent, bg=CARD)
        box.pack(side="left", padx=(0, 20))
        tk.Label(
            box,
            text=label,
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=CARD,
            anchor="w",
        ).pack(anchor="w")
        spin = tk.Spinbox(
            box,
            textvariable=variable,
            from_=minimum,
            to=maximum,
            width=width,
            font=("Segoe UI", 9),
            bg="#0a1422",
            fg=TEXT,
            buttonbackground=SUBTLE,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=GOLD,
            justify="center",
        )
        spin.pack(anchor="w", pady=(2, 0))
        return spin

    def _show_tab(self, key: str) -> None:
        if key not in self._tabs:
            return
        self._active_tab = key
        for name, frame in self._tabs.items():
            if name == key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        for name, button in self._tab_buttons.items():
            selected = name == key
            button.config(
                text=("▸  " if selected else "  ") + self._tab_labels[name],
                bg=CARD if selected else BG,
                fg=GOLD if selected else MUTED,
                activebackground=CARD if selected else SUBTLE_HOVER,
                activeforeground=GOLD if selected else TEXT,
            )

    def _build_webhook_tab(self) -> None:
        tab = self._tabs["webhook"]

        intro = tk.Frame(
            tab,
            bg=CARD,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        intro.pack(fill="x")
        tk.Label(
            intro,
            text="Webhook de recompensas",
            font=("Segoe UI", 15, "bold"),
            fg=TEXT,
            bg=CARD,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            intro,
            text=(
                "Sempre que um banner de recompensa aparecer no centro da tela, "
                "o Pirate Farm envia uma captura PNG e o nome identificado. "
                "Discord é detectado automaticamente; outros endereços recebem "
                "multipart/form-data com os campos content, reward, kind e file."
            ),
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=CARD,
            anchor="w",
            justify="left",
            wraplength=800,
        ).pack(fill="x", pady=(4, 0))

        config_card = tk.Frame(
            tab,
            bg=CARD,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        config_card.pack(fill="x", pady=(10, 0))

        self.wh_enabled_var = tk.BooleanVar(value=self.config.webhook.enabled)
        self.wh_shot_var = tk.BooleanVar(value=self.config.webhook.send_screenshot)
        self.wh_token_var = tk.BooleanVar(value=self.config.webhook.send_token)
        self.wh_rewards_var = tk.BooleanVar(value=self.config.webhook.send_rewards)

        chips = tk.Frame(config_card, bg=CARD)
        chips.pack(fill="x")
        self._chip(chips, "Webhook ativado", self.wh_enabled_var).pack(side="left")
        self._chip(chips, "Enviar captura", self.wh_shot_var).pack(
            side="left", padx=(8, 0)
        )
        self._chip(chips, "Token", self.wh_token_var).pack(side="left", padx=(8, 0))
        self._chip(chips, "Outras recompensas", self.wh_rewards_var).pack(
            side="left", padx=(8, 0)
        )

        tk.Label(
            config_card,
            text="URL do webhook",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED,
            bg=CARD,
            anchor="w",
        ).pack(fill="x", pady=(12, 3))
        self.wh_url_var = tk.StringVar(value=self.config.webhook.url)
        self.wh_url_entry = tk.Entry(
            config_card,
            textvariable=self.wh_url_var,
            font=("Consolas", 9),
            bg="#0a1422",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=GOLD,
        )
        self.wh_url_entry.pack(fill="x", ipady=7)
        tk.Label(
            config_card,
            text=(
                "Exemplo: https://discord.com/api/webhooks/…  ·  "
                "a URL é mascarada nos logs."
            ),
            font=("Segoe UI", 8),
            fg=DIM,
            bg=CARD,
            anchor="w",
        ).pack(fill="x", pady=(3, 0))

        identity = tk.Frame(config_card, bg=CARD)
        identity.pack(fill="x", pady=(10, 0))
        tk.Label(
            identity,
            text="Nome exibido",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED,
            bg=CARD,
        ).pack(side="left")
        self.wh_username_var = tk.StringVar(
            value=self.config.webhook.username or "Pirate Farm"
        )
        tk.Entry(
            identity,
            textvariable=self.wh_username_var,
            font=("Segoe UI", 9),
            bg="#0a1422",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=GOLD,
            width=28,
        ).pack(side="left", padx=(10, 0), ipady=5)
        self.wh_status_label = tk.Label(
            identity,
            text="",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED,
            bg=CARD,
            anchor="e",
        )
        self.wh_status_label.pack(side="right")

        actions = tk.Frame(config_card, bg=CARD)
        actions.pack(fill="x", pady=(12, 0))
        self.wh_save_button = tk.Button(
            actions,
            text="Salvar configuração",
            font=("Segoe UI", 10, "bold"),
            bg="#15803d",
            fg="#ffffff",
            activebackground="#166534",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=18,
            pady=8,
            cursor="hand2",
            command=self._save_webhook_settings,
        )
        self.wh_save_button.pack(side="left")
        self.wh_test_button = tk.Button(
            actions,
            text="Testar webhook",
            font=("Segoe UI", 9, "bold"),
            bg=SUBTLE,
            fg="#cbd5e1",
            activebackground=SUBTLE_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=15,
            pady=8,
            cursor="hand2",
            command=self._test_webhook,
        )
        self.wh_test_button.pack(side="left", padx=(8, 0))
        tk.Label(
            actions,
            text="As alterações valem também para o farm em execução.",
            font=("Segoe UI", 8),
            fg=DIM,
            bg=CARD,
        ).pack(side="right")

        ocr_card = tk.Frame(
            tab,
            bg=CARD,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=12,
        )
        ocr_card.pack(fill="x", pady=(10, 0))
        ocr_head = tk.Frame(ocr_card, bg=CARD)
        ocr_head.pack(fill="x")
        tk.Label(
            ocr_head,
            text="Leitura do nome (OCR)",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=CARD,
        ).pack(side="left")
        self.ocr_test_button = tk.Button(
            ocr_head,
            text="Testar OCR na tela",
            font=("Segoe UI", 9),
            bg=SUBTLE,
            fg="#cbd5e1",
            activebackground=SUBTLE_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._test_ocr,
        )
        self.ocr_test_button.pack(side="right")
        self.ocr_status_label = tk.Label(
            ocr_card,
            text="",
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=CARD,
            anchor="w",
            justify="left",
            wraplength=780,
        )
        self.ocr_status_label.pack(fill="x", pady=(5, 0))
        self._refresh_ocr_status()

        preview = tk.Frame(
            tab,
            bg=CARD,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=12,
        )
        preview.pack(fill="x", pady=(10, 0))
        tk.Label(
            preview,
            text="Mensagem de exemplo",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED,
            bg=CARD,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            preview,
            text="🎁  Ferramenta Espírito\nAnexo: captura PNG · Partida: 3 · Tempo: 00:42:10",
            font=("Segoe UI", 9),
            fg="#dbe7f5",
            bg="#0a1422",
            anchor="w",
            justify="left",
            padx=12,
            pady=9,
        ).pack(fill="x", pady=(5, 0))
        tk.Label(
            preview,
            text=(
                "Sem OCR legível, o envio continua com o nome "
                "“Recompensa encontrada”."
            ),
            font=("Segoe UI", 8),
            fg=DIM,
            bg=CARD,
            anchor="w",
        ).pack(fill="x", pady=(5, 0))

        self._refresh_webhook_status()

    def _refresh_webhook_status(self) -> None:
        if not hasattr(self, "wh_status_label"):
            return
        config = self.config.webhook
        if config.enabled and config.url.strip():
            self.wh_status_label.config(
                text=f"Ativo: {mask_webhook_url(config.url)}", fg=GREEN
            )
        elif config.enabled:
            self.wh_status_label.config(text="Falta a URL", fg=AMBER)
        else:
            self.wh_status_label.config(text="Desativado", fg=DIM)

    def _refresh_ocr_status(self) -> None:
        if not hasattr(self, "ocr_status_label"):
            return
        try:
            reader = OcrReader()
            if reader.available():
                self.ocr_status_label.config(
                    text=(
                        "OCR do Windows disponível. O nome é lido no idioma do "
                        "sistema; o texto reconhecido também aparece no registro."
                    ),
                    fg=MUTED,
                )
            else:
                self.ocr_status_label.config(
                    text=(
                        "OCR do Windows indisponível. As capturas continuam sendo "
                        "enviadas com o nome genérico."
                    ),
                    fg=AMBER,
                )
        except Exception as exc:
            self.ocr_status_label.config(
                text=f"OCR indisponível ({exc}). Será usado o nome genérico.",
                fg=AMBER,
            )

    def _refresh_safety_controls(self) -> None:
        if not hasattr(self, "idle_spin"):
            return
        self.idle_spin.config(
            state="normal" if self.idle_var.get() else "disabled"
        )
        self._update_mode_hint()

    def _update_mode_hint(self) -> None:
        if not hasattr(self, "mode_hint"):
            return
        if self.bg_var.get():
            card_bg, border, foreground = "#10243a", "#1e3a5f", "#bfdbfe"
            text = (
                "Segundo plano ativo: você pode usar o PC durante as partidas. "
                "O Fortnite não pode estar minimizado nem em tela cheia exclusiva — "
                "use janela sem borda. O bot traz o jogo à frente por ~1s apenas "
                "para clicar e devolve o foco ao seu programa."
            )
        else:
            card_bg, border, foreground = "#2a2110", "#713f12", "#fde68a"
            text = (
                "Modo primeiro plano: deixe o Fortnite na frente e não use o PC "
                "durante o farm."
            )
            if getattr(self, "afk_var", None) is not None and self.afk_var.get():
                text += (
                    " Se o jogo mostrar “AINDA ESTÁ AÍ?”, o farm para por "
                    "segurança em vez de clicar em CONTINUAR JOGANDO."
                )
            else:
                text += " Se o jogo perder o foco, o bot tenta clicar em CONTINUAR JOGANDO."
        try:
            limit = int(self.runtime_var.get())
        except (TypeError, ValueError):
            limit = self.config.behavior.max_runtime_minutes
        if limit <= 0:
            text += (
                " ATENÇÃO: execução sem limite. Farmar por horas seguidas "
                "aumenta muito o risco de ban por AFK."
            )
        else:
            text += f" Limite de execução: {limit} min."
        if getattr(self, "idle_var", None) is not None:
            if self.idle_var.get():
                try:
                    idle_limit = int(self.idle_minutes_var.get())
                except (TypeError, ValueError):
                    idle_limit = self.config.behavior.idle_stop_minutes or 30
                text += (
                    f" Para após {idle_limit} min sem teclado/mouse."
                )
            else:
                text += " Proteção de inatividade desativada."
        self.mode_hint_card.config(bg=card_bg, highlightbackground=border)
        self.mode_hint.config(text=text, bg=card_bg, fg=foreground)

    def _focus_window(self) -> None:
        """Traz o app para a frente ao abrir e ativa a barra de título escura."""
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _apply_dark_titlebar(self, window: tk.Misc) -> None:
        try:
            window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            dwm = ctypes.windll.dwmapi
            enabled = ctypes.c_int(1)
            for attribute in (20, 19):
                if dwm.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
                ) == 0:
                    break
            caption = ctypes.c_int(0x0020120B)  # COLORREF de #0b1220
            dwm.DwmSetWindowAttribute(
                hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption)
            )
            text = ctypes.c_int(0x00F9EEE6)  # COLORREF de #e6eef9
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), ctypes.sizeof(text))
            border = ctypes.c_int(0x004B3122)  # COLORREF de #22314b
            dwm.DwmSetWindowAttribute(
                hwnd, 34, ctypes.byref(border), ctypes.sizeof(border)
            )
        except Exception:
            pass

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        dialog.update_idletasks()
        width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"+{x}+{y}")

    def _dialog(self, title: str, message: str, confirm: bool = False) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        resultado = {"ok": False}

        body = tk.Frame(dialog, bg=BG, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=title,
            font=("Segoe UI", 13, "bold"),
            fg=TEXT,
            bg=BG,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text=message,
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BG,
            justify="left",
            wraplength=460,
            anchor="w",
        ).pack(fill="x", pady=(8, 18))

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x")

        def close(value: bool) -> None:
            resultado["ok"] = value
            dialog.destroy()

        if confirm:
            tk.Button(
                buttons,
                text="Cancelar",
                font=("Segoe UI", 9, "bold"),
                bg=SUBTLE,
                fg="#cbd5e1",
                activebackground=SUBTLE_HOVER,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                highlightthickness=0,
                padx=16,
                pady=7,
                cursor="hand2",
                command=lambda: close(False),
            ).pack(side="right")
            tk.Button(
                buttons,
                text="Sim, parar",
                font=("Segoe UI", 9, "bold"),
                bg=RED_DARK,
                fg="#ffffff",
                activebackground="#7f1d1d",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=0,
                padx=16,
                pady=7,
                cursor="hand2",
                command=lambda: close(True),
            ).pack(side="right", padx=(0, 8))
        else:
            tk.Button(
                buttons,
                text="OK",
                font=("Segoe UI", 9, "bold"),
                bg=GREEN_DARK,
                fg="#ffffff",
                activebackground="#115e59",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=0,
                padx=20,
                pady=7,
                cursor="hand2",
                command=lambda: close(True),
            ).pack(side="right")

        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        dialog.bind("<Escape>", lambda _event: close(False))
        if not confirm:
            dialog.bind("<Return>", lambda _event: close(True))
        self._center_dialog(dialog)
        dialog.bind(
            "<FocusIn>",
            lambda _event: self._apply_dark_titlebar(dialog),
        )
        dialog.after(80, lambda: self._apply_dark_titlebar(dialog))
        dialog.after(600, lambda: self._apply_dark_titlebar(dialog))
        dialog.wait_window()
        return resultado["ok"]

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log_line_count = 0
        self._log("Registro limpo.", "debug")

    # ------------------------------------------------------------- energia
    def _toggle_keep_awake(self) -> None:
        self._manual_awake = not self._manual_awake
        power.set_awake("manual", self._manual_awake)
        self._refresh_power_ui()
        if self._manual_awake:
            self._log(
                "Prevenção de suspensão ativada: o Windows não vai dormir nem "
                "desligar a tela por inatividade.",
                "success",
            )
        else:
            self._log(
                "Prevenção de suspensão manual desativada. O bot ainda mantém o "
                "PC acordado enquanto estiver rodando.",
                "info",
            )

    def _refresh_power_ui(self) -> None:
        if not hasattr(self, "power_button"):
            return
        selected = bool(self._manual_awake)
        self.power_button.config(
            text=("●  " if selected else "○  ") + "Manter PC acordado",
            bg=GREEN_DEEP if selected else SUBTLE,
            fg="#86efac" if selected else MUTED,
            activebackground=GREEN_DEEP if selected else SUBTLE_HOVER,
            activeforeground="#bbf7d0" if selected else TEXT,
        )
        active = power.is_awake()
        if active:
            reasons = power.reasons()
            if "bot" in reasons and "manual" in reasons:
                origin = "manual + bot"
            elif "bot" in reasons:
                origin = "automático"
            else:
                origin = "manual"
            self.power_label.config(text=f"PC acordado: sim ({origin})", fg=GREEN)
        else:
            self.power_label.config(text="PC acordado: não", fg=DIM)

    def _start_hotkey(self) -> None:
        self.hotkey = HotkeyListener(lambda: self.ui_queue.put({"type": "hotkey"}))
        if not self.hotkey.start():
            error = self.hotkey.error
            self._log(
                f"Não consegui registrar o atalho F8 ({error}). Use o botão PARAR.",
                "warn",
            )

    # --------------------------------------------------------------- ações
    def _start_bot(self) -> None:
        if self.bot is not None and self.bot.is_running():
            return
        self.stop_event.clear()
        self.manual_token.clear()
        self._success_scheduled = False
        if not self._apply_webhook_fields() or not self._apply_storage_fields():
            return
        if not self._apply_runtime_field():
            return
        if not self._apply_safety_fields():
            return
        self.config.behavior.dry_run = bool(self.sim_var.get())
        self.config.behavior.background_mode = bool(self.bg_var.get())
        try:
            save_config(self.config)
        except Exception as exc:
            self._log(f"Não consegui salvar as preferências: {exc}", "debug")

        limit = self.config.behavior.max_runtime_minutes
        if limit <= 0:
            self._log(
                "Aviso: o farm está sem limite de execução. Deixar horas seguidas "
                "aumenta muito o risco de ban por AFK. Recomendado: 120 a 180 min.",
                "warn",
            )
        elif limit > 240:
            self._log(
                f"Aviso: limite de {limit} min é longo. Sessões acima de 4 h "
                "aumentam o risco de ban por AFK.",
                "warn",
            )

        idle_limit = self.config.behavior.idle_stop_minutes
        if idle_limit > 0:
            self._log(
                f"Proteção de presença: o farm para após {idle_limit} min sem "
                "teclado/mouse.",
                "success",
            )
        else:
            self._log(
                "Proteção de inatividade desativada. O farm pode continuar sem "
                "ninguém por perto e aumentar o risco de ban.",
                "warn",
            )
        if self.config.behavior.stop_on_afk_warning:
            self._log(
                "Aviso de AFK: o farm para em “AINDA ESTÁ AÍ?” ou aviso de "
                "inatividade, sem clicar em continuar.",
                "success",
            )
        else:
            self._log(
                "Parada por aviso de AFK desativada: o bot voltará a clicar em "
                "CONTINUAR JOGANDO. Isso aumenta o risco de ban.",
                "warn",
            )

        self.bot = PirateBot(
            self.config,
            self.ui_queue,
            self.stop_event,
            self.manual_token,
        )
        self._log(
            "Bot iniciado"
            + (" em modo SIMULAÇÃO." if self.config.behavior.dry_run else "."),
            "success",
        )
        if not self.config.behavior.dry_run:
            if self.config.behavior.background_mode:
                self._log(
                    "Modo segundo plano ativo: captura sem roubar o foco e foco "
                    "rápido de ~1s apenas para clicar. Não minimize o Fortnite.",
                    "success",
                )
            else:
                self._log(
                    "Modo primeiro plano: não use o PC enquanto o bot estiver rodando.",
                    "warn",
                )
        self.bot.start()
        self._update_buttons()
        self._refresh_power_ui()

    def _stop_bot(self, reason: str) -> None:
        self.stop_event.set()
        if self.bot is not None:
            self.bot.stop()
        self._log(reason, "warn")
        self._set_status(Phase.STOPPED.value, reason)
        self._update_buttons()
        self._refresh_power_ui()

    def _mark_token(self) -> None:
        if self.bot is None or not self.bot.is_running():
            self._log("O bot não está rodando.", "warn")
            return
        self.manual_token.set()
        self._log(
            "Token marcado manualmente. Vou aguardar o fim da partida "
            "(se houver) e encerrar.",
            "success",
        )
        self._set_status(
            Phase.MATCH.value,
            "Token marcado manualmente. Aguardando o fim da partida...",
        )

    def _test_detection(self) -> None:
        use_background = bool(self.bg_var.get())
        mode = "em segundo plano" if use_background else "em primeiro plano"
        self._log(f"Capturando a tela {mode} para testar a detecção...", "info")
        threading.Thread(
            target=self._run_detection_test,
            args=(use_background,),
            name="DetectionTest",
            daemon=True,
        ).start()

    def _run_detection_test(self, use_background: bool) -> None:
        try:
            window = find_game_window(self.config.game.window_title)
            grabber = ScreenGrabber(window)
            detector = TokenDetector(ASSETS, self.config.detection)
            frame = (
                grabber.capture_background()
                if use_background
                else grabber.capture()
            )
            token = detector.detect(frame)
            play = detector.find_play_button(frame)
            suspend = detector.find_suspend_button(frame)
            LOGS.mkdir(parents=True, exist_ok=True)
            path = LOGS / "teste_tela.png"
            imwrite_u(path, frame)
            self.ui_queue.put(
                {
                    "type": "test_result",
                    "token": token.found,
                    "best": token.best,
                    "game_foreground": grabber.is_foreground(),
                    "background": use_background,
                    "play": play,
                    "suspend": suspend,
                    "path": str(path),
                    "size": (frame.shape[1], frame.shape[0]),
                }
            )
        except Exception as exc:
            self.ui_queue.put({"type": "test_error", "text": str(exc)})

    def _open_logs(self) -> None:
        LOGS.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(LOGS))
        except Exception as exc:
            self._log(f"Não consegui abrir a pasta de logs: {exc}", "error")

    # ------------------------------------------------------- capturas/webhook
    def _open_snapshots(self) -> None:
        folder = LOGS / "snapshots"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))
        except Exception as exc:
            self._log(f"Não consegui abrir a pasta de capturas: {exc}", "error")

    def _apply_safety_fields(self) -> bool:
        if self.idle_var.get():
            try:
                minutes = int(self.idle_minutes_var.get())
            except (TypeError, ValueError):
                self._dialog(
                    "Proteção de sessão",
                    "Informe quantos minutos sem teclado/mouse devem encerrar "
                    "o farm, usando apenas números inteiros (5 a 720).",
                )
                return False
            if not 5 <= minutes <= 720:
                self._dialog(
                    "Proteção de sessão",
                    "Use um limite entre 5 e 720 minutos sem atividade.",
                )
                return False
            self.config.behavior.idle_stop_minutes = minutes
            self.idle_minutes_var.set(str(minutes))
        else:
            self.config.behavior.idle_stop_minutes = 0
        self.config.behavior.stop_on_afk_warning = bool(self.afk_var.get())
        return True

    def _apply_runtime_field(self) -> bool:
        try:
            value = int(self.runtime_var.get())
        except (TypeError, ValueError):
            self._dialog(
                "Limite de execução",
                "Informe o limite em minutos usando apenas números inteiros "
                "(0 = sem limite).",
            )
            return False
        value = max(0, min(1440, value))
        self.runtime_var.set(str(value))
        self.config.behavior.max_runtime_minutes = value
        return True

    def _apply_storage_fields(self) -> bool:
        try:
            values = {
                "snapshot_max_files": int(self.max_files_var.get()),
                "snapshot_max_age_days": int(self.max_age_var.get()),
                "snapshot_min_keep": int(self.min_keep_var.get()),
                "snapshot_grace_seconds": int(self.grace_var.get()),
            }
        except (TypeError, ValueError):
            self._dialog(
                "Capturas automáticas",
                "Use apenas números inteiros nos campos de retenção.",
            )
            return False
        for key, value in values.items():
            setattr(self.config.storage, key, max(0, value))
        return True

    def _refresh_snapshot_stats(self) -> None:
        if not hasattr(self, "snapshot_label"):
            return
        folder = LOGS / "snapshots"
        count = 0
        total = 0
        try:
            for path in folder.glob("*.png"):
                try:
                    total += path.stat().st_size
                    count += 1
                except OSError:
                    continue
        except OSError:
            pass
        size = total / (1024 * 1024)
        self.snapshot_label.config(text=f"{count} capturas · {size:.0f} MB")
        self._last_snapshot_refresh = time.time()

    def _clean_snapshots(self) -> None:
        if not self._apply_storage_fields():
            return
        try:
            save_config(self.config)
        except Exception as exc:
            self._log(f"Não consegui salvar a retenção: {exc}", "debug")
        self._log("Limpando capturas antigas...", "info")
        self.clean_button.config(state="disabled", text="Limpando...")

        def run() -> None:
            try:
                result = prune_snapshots(LOGS / "snapshots", self.config.storage)
                self.ui_queue.put(
                    {
                        "type": "prune_result",
                        "removed": result.removed,
                        "freed": result.freed_bytes,
                        "kept": result.kept,
                        "skipped": result.skipped,
                    }
                )
            except Exception as exc:
                self.ui_queue.put({"type": "prune_result", "error": str(exc)})

        threading.Thread(target=run, name="SnapshotCleanup", daemon=True).start()

    def _apply_webhook_fields(self) -> bool:
        if not hasattr(self, "wh_url_var"):
            return True
        enabled = bool(self.wh_enabled_var.get())
        url = self.wh_url_var.get().strip()
        if url:
            try:
                url = validate_webhook_url(url)
            except ValueError as exc:
                self._dialog("Webhook", str(exc))
                return False
        if enabled and not url:
            self._dialog(
                "Webhook",
                "Informe a URL do webhook ou desmarque “Webhook ativado”.",
            )
            return False
        config = self.config.webhook
        config.enabled = enabled
        config.url = url
        config.send_screenshot = bool(self.wh_shot_var.get())
        config.send_token = bool(self.wh_token_var.get())
        config.send_rewards = bool(self.wh_rewards_var.get())
        config.username = self.wh_username_var.get().strip() or "Pirate Farm"
        return True

    def _save_webhook_settings(self) -> None:
        if not self._apply_webhook_fields():
            return
        try:
            save_config(self.config)
        except Exception as exc:
            self._log(f"Não consegui salvar o webhook: {exc}", "error")
            return
        if self.bot is not None and self.bot.is_running():
            self.bot.reload_webhook()
            self._log(
                "Configuração do webhook aplicada ao farm em execução.", "info"
            )
        self._refresh_webhook_status()
        self._log("Configuração do webhook salva.", "success")

    def _test_webhook(self) -> None:
        url = self.wh_url_var.get().strip()
        try:
            url = validate_webhook_url(url)
        except ValueError as exc:
            self._dialog("Teste do webhook", str(exc))
            return
        config = WebhookConfig(
            **{
                **self.config.webhook.__dict__,
                "enabled": True,
                "url": url,
                "send_screenshot": False,
            }
        )
        masked = mask_webhook_url(url)
        self.wh_test_button.config(state="disabled", text="Enviando...")
        self.wh_status_label.config(text="Enviando teste...", fg=AMBER)
        self._log(f"Enviando teste para {masked}...", "info")

        def run() -> None:
            result = send_test(config)
            self.ui_queue.put(
                {
                    "type": "webhook_test",
                    "ok": result.ok,
                    "status": result.status,
                    "detail": result.detail,
                    "url": masked,
                }
            )

        threading.Thread(target=run, name="WebhookTest", daemon=True).start()

    def _test_ocr(self) -> None:
        use_background = bool(self.bg_var.get())
        self.ocr_test_button.config(state="disabled", text="Lendo...")
        self._log("Capturando a tela para testar o OCR...", "info")

        def run() -> None:
            try:
                window = find_game_window(self.config.game.window_title)
                grabber = ScreenGrabber(window)
                frame = (
                    grabber.capture_background()
                    if use_background
                    else grabber.capture()
                )
                score = banner_score(frame)
                badge = reward_badge_score(frame)
                reader = OcrReader()
                text = reader.recognize(frame)
                event = parse_reward_text(text)
                self.ui_queue.put(
                    {
                        "type": "ocr_test",
                        "ok": True,
                        "score": score,
                        "badge": badge,
                        "text": text,
                        "event": event,
                        "size": (frame.shape[1], frame.shape[0]),
                    }
                )
            except Exception as exc:
                self.ui_queue.put({"type": "ocr_test", "ok": False, "error": str(exc)})

        threading.Thread(target=run, name="OcrTest", daemon=True).start()

    # ---------------------------------------------------------------- poll
    def _poll(self) -> None:
        while True:
            try:
                message = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_message(message)
        self._update_buttons()
        now = time.time()
        if now - self._last_power_refresh >= 0.5:
            self._last_power_refresh = now
            self._refresh_power_ui()
        if now - self._last_snapshot_refresh >= 10.0:
            self._refresh_snapshot_stats()
        self.root.after(100, self._poll)

    def _handle_message(self, message: dict) -> None:
        kind = message.get("type")

        if kind == "log":
            self._log(message.get("text", ""), message.get("level", "info"))

        elif kind == "status":
            phase = message.get("phase", Phase.STARTING.value)
            detail = message.get("message", "")
            self._set_status(phase, detail)
            self.matches_label.config(text=f"Partidas: {message.get('matches', 0)}")
            token = bool(message.get("token_found"))
            self.token_label.config(
                text="Token: SIM" if token else "Token: não",
                fg=GREEN if token else RED,
            )
            self.reward_label.config(
                text=f"Recompensas: {message.get('rewards', 0)}"
            )
            self.time_label.config(
                text=f"Tempo: {_format_elapsed(message.get('elapsed', 0))}"
            )

        elif kind == "token":
            self.token_label.config(text="Token: SIM", fg=GREEN)
            self._set_status(
                Phase.MATCH.value,
                "Token detectado! Vou esperar a partida terminar para encerrar.",
            )

        elif kind == "reward":
            self.reward_label.config(
                text=f"Recompensas: {message.get('count', 0)}"
            )
            name = message.get("name", "")
            if name:
                self.reward_label.config(fg=GOLD)

        elif kind == "success":
            text = message.get("text", "Token encontrado!")
            self._set_status(Phase.FINISHED.value, text)
            self.token_label.config(text="Token: SIM", fg=GREEN)
            self._log(text, "success")
            self._write_success_file(text)
            self._schedule_auto_close()

        elif kind == "error":
            text = message.get("text", "Erro desconhecido.")
            self._set_status(Phase.ERROR.value, text)
            self.root.bell()
            try:
                self._dialog("Erro no Pirate Farm", text)
            except Exception:
                pass

        elif kind == "stopped":
            text = message.get("text", "Parado.")
            self._set_status(Phase.STOPPED.value, text)

        elif kind == "hotkey":
            if self.bot is not None and self.bot.is_running():
                self._stop_bot("Parada de emergência (F8).")
            else:
                self._log("F8 pressionado, mas o bot não está rodando.", "info")

        elif kind == "test_result":
            self._handle_test_result(message)

        elif kind == "test_error":
            text = message.get("text", "Falha no teste.")
            self._log(f"Teste de detecção falhou: {text}", "error")
            self._set_status(Phase.ERROR.value, f"Teste falhou: {text}")

        elif kind == "webhook_test":
            self.wh_test_button.config(state="normal", text="Testar webhook")
            status = message.get("status") or "sem resposta"
            if message.get("ok"):
                self.wh_status_label.config(text=f"Teste OK ({status})", fg=GREEN)
                self._log(
                    f"Webhook de teste enviado com sucesso ({status}).", "success"
                )
            else:
                detail = str(message.get("detail", ""))[:300]
                self.wh_status_label.config(text=f"Falha ({status})", fg=RED)
                self._log(
                    f"Teste do webhook falhou ({status}): {detail}", "warn"
                )

        elif kind == "ocr_test":
            self.ocr_test_button.config(state="normal", text="Testar OCR na tela")
            if not message.get("ok"):
                error = message.get("error", "falha desconhecida")
                self._log(f"Teste do OCR falhou: {error}", "error")
            else:
                score = float(message.get("score", 0.0))
                badge = float(message.get("badge", 0.0))
                raw = " ".join(str(message.get("text", "")).split())[:300]
                self._log(
                    f"OCR de teste: banner {score:.2f}; brasão {badge:.2f}; "
                    f"texto: {raw or '(vazio)'}.",
                    "info",
                )
                event = message.get("event")
                if event is not None:
                    self._log(
                        f"Recompensa reconhecida no teste: {event.name}.",
                        "success",
                    )
                else:
                    self._log(
                        "Nenhum cabeçalho de recompensa foi reconhecido no texto.",
                        "info",
                    )

        elif kind == "prune_result":
            self.clean_button.config(state="normal", text="Limpar agora")
            if message.get("error"):
                self._log(
                    f"Falha ao limpar capturas: {message.get('error')}", "error"
                )
            elif message.get("skipped"):
                self._log(
                    "A limpeza já está rodando em outro ponto; tente de novo.",
                    "warn",
                )
            else:
                removed = int(message.get("removed", 0))
                freed = float(message.get("freed", 0)) / (1024 * 1024)
                kept = int(message.get("kept", 0))
                if removed:
                    self._log(
                        f"Limpeza concluída: {removed} captura(s) removida(s), "
                        f"{freed:.1f} MB liberados, {kept} mantida(s).",
                        "success",
                    )
                else:
                    self._log(
                        f"Limpeza concluída: nada para remover; {kept} mantida(s).",
                        "info",
                    )
            self._refresh_snapshot_stats()

    def _handle_test_result(self, message: dict) -> None:
        width, height = message.get("size", (0, 0))
        foreground = message.get("game_foreground")
        background = bool(message.get("background"))
        self._log(f"Captura de teste: {width}x{height}.", "info")
        if background:
            self._log(
                "Captura em segundo plano concluída; o foco do jogo não foi alterado.",
                "info",
            )
        elif not foreground:
            self._log(
                "A janela do Fortnite não estava em primeiro plano; "
                "a captura pode mostrar outra janela.",
                "warn",
            )

        if message.get("token"):
            best = message.get("best")
            if best is not None:
                self._log(
                    f"TOKEN VISÍVEL na tela! ({best.kind}, confiança {best.score:.2f}, "
                    f"{best.w}x{best.h})",
                    "success",
                )
            self._set_status(
                Phase.FINISHED.value,
                "Token visível na tela! Se estiver em partida, o bot vai aguardar o fim.",
            )
        else:
            self._log("Token não visível na captura (normal fora da tela de recompensa).", "info")

        play = message.get("play")
        if play is not None:
            self._log(
                f"Botão JOGAR detectado (confiança {play.score:.2f}) em ({play.x}, {play.y}).",
                "info",
            )
        else:
            self._log("Botão JOGAR não detectado.", "info")

        suspend = message.get("suspend")
        if suspend is not None:
            self._log(
                f"Botão CONTINUAR JOGANDO detectado (confiança {suspend.score:.2f}).",
                "warn",
            )
        else:
            self._log("Tela de suspensão não detectada.", "info")

        self._log(f"Captura salva em {message.get('path')}.", "debug")

        if not message.get("token") and play is None and suspend is None:
            self._set_status(
                Phase.LOBBY.value,
                "Teste concluído: nenhum elemento conhecido na captura. "
                "Traga o Fortnite para a frente e teste de novo.",
            )
        elif play is not None and not message.get("token"):
            self._set_status(
                Phase.LOBBY.value,
                "Teste concluído: lobby detectado. O bot está pronto para jogar.",
            )
        elif suspend is not None:
            self._set_status(
                Phase.STARTING.value,
                "Teste concluído: tela de suspensão detectada.",
            )

    # ------------------------------------------------------------- helpers
    def _set_status(self, phase: str, detail: str) -> None:
        label, color = PHASE_STYLE.get(phase, (PHASE_LABELS.get(phase, phase), MUTED))
        self.status_label.config(text=label, fg=color)
        self.detail_label.config(text=detail)

    def _log(self, text: str, level: str = "info") -> None:
        if not text:
            return
        tag = level if level in ("info", "success", "warn", "error", "debug") else "info"
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] ", "ts")
        self.log_text.insert("end", f"{text}\n", tag)
        self._log_line_count += 1
        if self._log_line_count > 2500:
            self.log_text.delete("1.0", "600.0")
            self._log_line_count -= 599
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_buttons(self) -> None:
        running = bool(self.bot is not None and self.bot.is_running())
        if running:
            self.start_button.config(
                state="disabled",
                bg="#123524",
                fg="#5f7a6b",
                disabledforeground="#5f7a6b",
                cursor="arrow",
            )
            self.stop_button.config(
                state="normal",
                bg=RED_DARK,
                fg="#ffffff",
                cursor="hand2",
            )
            self.token_button.config(
                state="normal",
                bg=GOLD,
                fg="#1c1917",
                cursor="hand2",
            )
        else:
            self.start_button.config(
                state="normal",
                bg="#15803d",
                fg="#ffffff",
                cursor="hand2",
            )
            self.stop_button.config(
                state="disabled",
                bg="#3a1a1a",
                fg="#8a6a6a",
                disabledforeground="#8a6a6a",
                cursor="arrow",
            )
            self.token_button.config(
                state="disabled",
                bg="#3a2f16",
                fg="#8a7a55",
                disabledforeground="#8a7a55",
                cursor="arrow",
            )

    def _write_success_file(self, text: str) -> None:
        try:
            stamp = time.strftime("%d/%m/%Y %H:%M:%S")
            (ROOT / "TOKEN_ENCONTRADO.txt").write_text(
                f"{text}\nDetectado em: {stamp}\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    def _schedule_auto_close(self) -> None:
        if self._success_scheduled:
            return
        self._success_scheduled = True
        seconds = int(self.config.behavior.auto_close_success_seconds)
        if seconds <= 0:
            return
        self._log(f"O programa vai fechar em {seconds} segundos.", "info")
        self.root.after(seconds * 1000, lambda: self._on_close(force=True))

    def _on_close(self, force: bool = False) -> None:
        if not force and self.bot is not None and self.bot.is_running():
            if not self._dialog(
                "Sair do Pirate Farm",
                "O bot está rodando. Deseja parar o farm e sair?",
                confirm=True,
            ):
                return
        self.stop_event.set()
        if self.bot is not None:
            self.bot.stop()
        if self.hotkey is not None:
            self.hotkey.stop()
        power.set_awake("manual", False)
        power.shutdown()
        self.root.destroy()


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    path = LOGS / f"piratefarm_{time.strftime('%Y%m%d_%H%M%S')}.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    return path


def main() -> int:
    log_path = _configure_logging()

    def exception_hook(exc_type, exc_value, exc_traceback):
        logging.error("Falha não tratada", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            messagebox.showerror(
                APP_TITLE,
                f"Ocorreu um erro inesperado:\n\n{exc_value}\n\nLog: {log_path}",
            )
        except Exception:
            pass

    sys.excepthook = exception_hook
    root = tk.Tk()
    app = PirateFarmApp(root)
    app._log(f"Log desta sessão: {log_path}", "debug")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
