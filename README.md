# Pirate Farm — Fortnite

Automação AFK para farmar o **Pirate Shop Access** (token da Loja Pirata) no
evento Treasure Hunters do Fortnite.

O programa fica no lobby, clica em **JOGAR**, entra na partida e fica AFK. Como
o token é compartilhado com todo o esquadrão no **Squad + Fill**, os
companheiros podem encontrá-lo enquanto você está parado. Quando o token
aparece na tela, o bot espera a partida terminar, volta ao lobby e encerra.
Se o token não aparecer, ele inicia outra partida automaticamente.

> **Aviso:** automação de cliques/teclas pode violar os Termos de Serviço da
> Epic Games. Use por sua conta e risco. O bot não injeta nada no jogo: apenas
> lê o log local, captura a tela e envia cliques/teclas como um usuário.

---

## O que ele faz

1. Detecta que você está no lobby (log + botão JOGAR na tela).
2. Clica em JOGAR e aguarda a partida começar.
3. Fica AFK durante a partida, verificando o banner do token a cada ~1,6 s.
4. Se o esquadrão todo morrer / a partida acabar, aguarda as telas de
   recompensa e volta ao lobby.
5. Se o token foi encontrado, **não inicia outra partida**: espera o fim da
   partida atual, retorna ao lobby, procura a tela de recompensa e clica em
   **CLAIM ALL** (quando ela aparece). Depois disso, fecha o programa.
6. Se o token não foi encontrado, clica em JOGAR novamente e repete o ciclo.

O prêmio é aplicado à conta automaticamente; o clique em **CLAIM ALL** serve
para confirmar a tela de recompensa que o jogo mostra no lobby.

Extras:

- Detecta a tela **“O FORTNITE ESTÁ NO MODO DE SUSPENSÃO”** e clica em
  **CONTINUAR JOGANDO**.
- Impede a **suspensão automática do Windows** enquanto o bot está rodando
  (não impede bloqueio manual com Win+L).
- Atalho global **F8** para parada de emergência.
- Botão **“Já tenho o token”** para encerrar no fim da partida atual, caso você
  veja o token antes do bot.
- Modo **Simulação**, que lê o log e testa a detecção sem clicar no jogo.

---

## Requisitos

- Windows 10/11, **desbloqueado**, com o bloqueio de tela e a suspensão
  automática desativados durante o farm. Com o PC bloqueado, o Fortnite não
  recebe os cliques e a captura de tela não funciona.
- Fortnite em **modo janela sem borda** (windowed fullscreen). O projeto foi
  calibrado em **1920x1080**; as coordenadas se ajustam a outras resoluções,
  mas os templates foram feitos nessa resolução.
- Conta já logada, no **lobby**.
- Modo **Battle Royale** (o evento Treasure Hunters faz parte do BR normal).
- Esquadrão em **Squad + Fill (Preencher)** — é o que dá as 4 chances de token.
- Jogo em **português**. Os templates dos botões “JOGAR” e “CONTINUAR JOGANDO”
  são em português; a detecção do token em si não depende de idioma.

O ambiente virtual (`.venv`) já está pronto nesta pasta. Se precisar recriar:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Como usar

1. Abra o Fortnite e fique no **lobby**.
2. Confirme **Battle Royale** e **Squad + Fill**.
3. Dê dois cliques em **`run.bat`**.
4. Clique em **INICIAR**.
5. **Não use o computador** enquanto o bot estiver rodando. Se o Fortnite
   perder o foco, ele entra em modo de suspensão e a partida não avança.
6. **Desative o bloqueio de tela e a suspensão do Windows** (Configurações >
   Sistema > Energia) e não deixe o PC dormir. O bot impede a suspensão
   automática enquanto roda, mas não impede bloqueio manual (Win+L). Com a
   tela bloqueada, o jogo fica em segundo plano e o bot não captura nem clica.
7. Para parar a qualquer momento, pressione **F8** ou clique em **PARAR**.

Quando o token for detectado:

- o app toca um som e mostra **“TOKEN ENCONTRADO!”**;
- ele espera a partida terminar e voltar ao lobby;
- se a tela de recompensa aparecer, ele clica em **CLAIM ALL**;
- o programa fecha sozinho após **30 segundos**;
- é criado o arquivo **`TOKEN_ENCONTRADO.txt`** na pasta do projeto, e o
  evento fica registrado em `logs\piratefarm_*.log`.

Se você já tiver o token e o bot estiver rodando, clique em
**“Já tenho o token”**: ele espera o fim da partida (se houver) e encerra.

### Primeiro teste (recomendado)

Antes de deixar o bot sozinho:

1. Marque **“Simulação (não clica no jogo)”**.
2. Clique em **INICIAR**.
3. Inicie uma partida manualmente.
4. Acompanhe o registro: o bot deve mostrar “Partida iniciada”, procurar o
   token e detectar o retorno ao lobby, **sem clicar em nada**.
5. Pare com F8 e repita sem a simulação quando estiver confiante.

Você também pode clicar em **“Testar detecção agora”** com o Fortnite em
primeiro plano. Ele salva `logs\teste_tela.png` e informa se encontrou o botão
JOGAR, a tela de suspensão ou o token.

---

## Como funciona

### Log do Fortnite

O arquivo `%LOCALAPPDATA%\FortniteGame\Saved\Logs\FortniteGame.log` é lido em
tempo real. Os eventos usados são:

| Linha do log | Significado |
|---|---|
| `UI State changing ... to [UI.State.Athena.Frontend]` | está no lobby |
| `UI State changing ... to [UI.State.Athena.BattleRoyale]` | entrou na partida |
| `EAthenaGamePhase::EndGame` | a partida terminou |
| `WBP_PostMatchPanelContainer` | tela de pós-partida |
| `OnPlayerPawnDied` | seu personagem morreu (o esquadrão continua) |

O bot não usa o log para detectar o token: ele usa visão computacional.

### Visão computacional

Dois templates foram extraídos das imagens de referência:

- **`assets/coin_inner.png`** — disco dourado com o “F” branco da moeda
  Pirate Shop. Usado nas telas de recompensa.
- **`assets/coin_banner_frame.png`** — quadro dourado do banner que aparece
  durante a partida.

Cada acerto é validado por dois filtros de cor: proporção de dourado e
presença de branco no centro. Isso elimina falsos positivos do lobby (que tem
muitas moedas e ouro no cenário), da tela de suspensão e do desktop. Os testes
estão em `selftest.py`.

### Entrada

- Cliques: `SetCursorPos` + `mouse_event` (nível de sistema, funciona com o
  jogo em windowed fullscreen).
- Foco: `SetForegroundWindow` com o truque da tecla Alt; fallback com
  `AttachThreadInput`.
- ENTER nas telas de recompensa: `pydirectinput` (SendInput).
- F8: `RegisterHotKey` do Windows, sem hooks globais de teclado.

### Telas de suspensão

Se o jogo perder o foco, aparece a tela “O FORTNITE ESTÁ NO MODO DE
SUSPENSÃO”. O bot procura o botão **CONTINUAR JOGANDO** e clica nele. Ainda
assim, o ideal é deixar o jogo em primeiro plano e não mexer no PC.

---

## Configuração (`config.json`)

As coordenadas são sempre relativas a **1920x1080** e são escaladas para o
tamanho real da janela.

```json
{
  "ui": {
    "play_tab": [265, 68],
    "play_button": [265, 938],
    "suspend_continue": [960, 496],
    "postmatch_safe_click": [1710, 1010],
    "claim_button": [965, 992]
  },
  "behavior": {
    "scan_interval_match": 1.6,
    "max_matches": 0,
    "max_runtime_minutes": 0,
    "auto_close_success_seconds": 30,
    "claim_timeout": 20.0,
    "dry_run": false
  }
}
```

- `play_button`: centro do botão JOGAR no lobby.
- `postmatch_safe_click`: clique de segurança caso o ENTER/ESPAÇO não avance a
  tela pós-partida.
- `claim_button`: centro do botão CLAIM ALL da tela de recompensa do token.
- `claim_timeout`: quanto tempo o bot espera a tela de recompensa aparecer no
  lobby depois de uma partida premiada.
- `max_matches`: `0` = sem limite. Útil para testar com poucas partidas.
- `max_runtime_minutes`: `0` = sem limite.
- `auto_close_success_seconds`: tempo até fechar após achar o token. `0` =
  não fecha sozinho.
- `dry_run`: `true` para simulação.

Se o layout do jogo mudar, use **“Testar detecção agora”** e
`logs\teste_tela.png` para recalibrar as coordenadas/templates.

---

## Logs e diagnóstico

- `logs\piratefarm_AAAAAMMDD_HHMMSS.log` — registro completo da sessão.
- `logs\snapshots\` — capturas automáticas do token, da suspensão e do
  pós-partida.
- `logs\teste_tela.png` — última captura do botão “Testar detecção”.
- `TOKEN_ENCONTRADO.txt` — criado quando o token é detectado.
- `selftest.py` — valida templates, falsos positivos, parser e log real:

```bat
.venv\Scripts\python.exe selftest.py
```

Para testar a captura ao vivo (não clica nem foca):

```bat
.venv\Scripts\python.exe selftest.py --live
```

---

## Solução de problemas

**“Janela do Fortnite não encontrada”**
: Abra o Fortnite, deixe em modo janela sem borda e não minimizado.

**O bot não clica em JOGAR**
: Use “Testar detecção agora”. Se o botão não for encontrado, confira a
  resolução e a posição em `config.json`. O bot usa a coordenada calibrada
  como fallback, mas o template é mais confiável.

**O jogo entra em suspensão**
: O Fortnite precisa estar em primeiro plano. Não use o PC durante o farm.
  Se acontecer, o bot tenta clicar em CONTINUAR JOGANDO. Bloqueio de tela ou
  suspensão do Windows também param o jogo: desative os dois antes de iniciar.

**O token não é detectado**
: Verifique as capturas em `logs\snapshots\`. Se o banner do seu jogo for
  diferente das referências, recapture o template. A detecção foi validada
  contra lobby, desktop e tela de suspensão, mas atualizações do jogo podem
  mudar a arte.

**Matchmaking não começa**
: Confirme Squad + Fill e o modo Battle Royale. O bot tenta clicar em JOGAR
  novamente após alguns segundos.

**O bot fechou sem mostrar o token**
: Veja `TOKEN_ENCONTRADO.txt` e o log da sessão. Se o token foi encontrado
  pelo esquadrão mas não apareceu na sua tela, marque “Já tenho o token” na
  próxima execução.

---

## Estrutura

```text
fortnite_pirate_farm/
├── main.py                  # interface gráfica
├── selftest.py              # testes offline
├── config.json              # coordenadas e comportamento
├── run.bat                  # inicia sem console
├── run_debug.bat            # inicia com console
├── piratebot/
│   ├── bot.py               # máquina de estados
│   ├── config.py            # configuração
│   ├── controller.py        # foco, cliques e teclas
│   ├── hotkey.py            # F8 global
│   ├── logwatcher.py        # leitura do log do Fortnite
│   └── vision.py            # captura, templates e detecção
├── assets/
│   ├── coin_inner.png
│   ├── coin_banner_frame.png
│   ├── play_button.png
│   ├── suspend_button.png
│   └── test/                # imagens de referência do autoteste
└── logs/                    # criado em tempo de execução
```

---

## Privacidade

O programa não acessa a internet. Ele lê apenas o log local do Fortnite,
captura a tela do jogo e grava logs/capturas na própria pasta do projeto.
