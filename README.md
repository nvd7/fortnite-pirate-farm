<p align="center">
  <img src="docs/banner.png" alt="Pirate Farm — Farm AFK do token Pirate Shop Access" width="100%">
</p>

<h1 align="center">Pirate Farm</h1>

<p align="center">
  Farm AFK do <strong>Pirate Shop Access</strong> no Fortnite, com interface em português,
  captura em segundo plano e detecção local por visão computacional.
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="#requisitos"><img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white" alt="Windows 10/11"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licen%C3%A7a-MIT-34d399" alt="Licença MIT"></a>
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/vers%C3%A3o-1.2.1-f5c451" alt="Versão 1.2.1"></a>
  <a href="https://github.com/nvd7/fortnite-pirate-farm/actions/workflows/tests.yml"><img src="https://github.com/nvd7/fortnite-pirate-farm/actions/workflows/tests.yml/badge.svg" alt="Testes"></a>
  <img src="https://img.shields.io/badge/idioma-PT--BR-0b1220" alt="Português do Brasil">
</p>

<p align="center">
  <a href="#sobre">Sobre</a> ·
  <a href="#recursos">Recursos</a> ·
  <a href="#instalação">Instalação</a> ·
  <a href="#como-usar">Como usar</a> ·
  <a href="#configuração">Configuração</a> ·
  <a href="#solução-de-problemas">Solução de problemas</a>
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="Interface do Pirate Farm em modo escuro" width="560">
</p>

> [!WARNING]
> **Automação pode violar os Termos de Serviço da Epic Games.** Este projeto é
> experimental e não é afiliado à Epic Games. Use apenas em uma conta que você
> aceita o risco de perder. O programa não injeta código no jogo: ele lê o log
> local, captura a tela e envia cliques/teclas como um usuário. Deixar o farm
> AFK por horas aumenta o risco de ban; use o **limite de execução** (padrão de
> 180 minutos) e não tente burlar a detecção de AFK.

> [!IMPORTANT]
> **Status:** v1.2.1 - identificação do nome das recompensas por OCR, envio
> opcional de cada banner para um webhook, limpeza automática de capturas,
> instalação em um clique e interface com abas **Farm** e **Webhook**. Esta
> versão corrige falsos positivos do fallback visual em telas de espectador. O
> primeiro farm com partidas reais deve ser supervisionado, porque telas de
> recompensa e mudanças de layout do Fortnite podem exigir calibração.

---

## Sobre

O **Pirate Farm** mantém o Fortnite jogando sozinho no modo **Squad + Fill** para
farmar o token **Pirate Shop Access** do evento Treasure Hunters. Como o token é
compartilhado com o esquadrão, seus companheiros podem encontrá-lo enquanto você
fica AFK.

O ciclo é automático:

1. O bot identifica o lobby e clica em **JOGAR**.
2. Entra na partida e fica parado, observando o banner do token.
3. Acompanha os preenchimentos pelo canal de chat do jogo. Quando o último fill
   sai, abre o menu com **ESC**, clica na aba de opções e em **Voltar ao Lobby**
   para procurar outro esquadrão.
4. Ao terminar a partida, clica em **JOGAR NOVAMENTE** na tela de resumo e
   aguarda a fila iniciar a próxima partida. Se não houver esse botão, abre o
   menu com **ESC**, clica na aba de opções e usa **Voltar ao Lobby**.
5. Quando o token aparece, espera a partida acabar, retorna ao lobby, confirma a
   recompensa com **CLAIM ALL** (se a tela aparecer) e encerra.

A automação é **híbrida**: o `FortniteGame.log` informa em que fase o jogo está;
a visão computacional confirma o botão **JOGAR**, a tela de suspensão, o token e
o botão **CLAIM ALL**. Nada é enviado para a internet por padrão; o webhook de
recompensas é opcional e só funciona quando você configura uma URL.

---

## Recursos

- **Modo segundo plano (padrão):** captura o Fortnite mesmo com outra janela na
  frente, usando `PrintWindow` + `PW_RENDERFULLCONTENT`. Você pode usar o PC
  durante as partidas.
- **Foco rápido:** quando é preciso clicar, o jogo vem para a frente por cerca de
  um segundo e o foco anterior (e a posição do cursor) é restaurado em seguida.
- **Detecção robusta do token:** OpenCV com múltiplas escalas e validação de cor,
  testada contra lobby, desktop, tela de suspensão e imagens de referência.
- **Ciclo por log + visão:** lobby, matchmaking, partida, pós-partida e retorno ao
  lobby sem depender de temporizações fixas.
- **Pós-partida por clique visual:** clica em **JOGAR NOVAMENTE** e aguarda a
  fila, ou em **RETORNAR AO LOBBY**; não usa ENTER/ESPAÇO, então o chat do jogo
  não abre.
- **Saída automática do esquadrão:** quando o chat confirma que todos os
  preenchimentos saíram, o bot abre o menu, clica na aba de opções e em
  **Voltar ao Lobby**. A saída é cancelada se algum preenchimento voltar e nunca
  acontece com o token encontrado.
- **CLAIM ALL automático** na tela de recompensa do token.
- **Tela de suspensão do Fortnite:** detecta “O FORTNITE ESTÁ NO MODO DE
  SUSPENSÃO” e clica em **CONTINUAR JOGANDO**.
- **Prevenção de suspensão do Windows:** botão **Manter PC acordado** e proteção
  automática enquanto o bot roda.
- **Interface escura em PT-BR**, com status, contadores, log ao vivo e atalho
  global **F8** para parada de emergência.
- **Modo simulação:** acompanha o log e testa a detecção sem clicar no jogo.
- **Recompensas identificadas por OCR:** o Windows lê o nome no banner
  (“VOCÊ ENCONTROU …”, “YOU FOUND …”) em português, inglês e árabe. Quando o
  texto não é legível, o brasão dourado central é usado como fallback.
- **Webhook opcional:** envia a captura do banner e o nome identificado para um
  webhook do Discord ou para qualquer endpoint que aceite `multipart/form-data`.
- **Limpeza automática:** remove capturas antigas por quantidade, idade ou
  carência, preservando as evidências do token e as capturas mais recentes. O
  consumo de disco aparece na interface.
- **Diagnóstico local:** capturas em `logs\snapshots\`, log da sessão e arquivo
  `TOKEN_ENCONTRADO.txt` quando o token é detectado.
- **Sem telemetria:** nenhum login ou rastreamento. A rede só é usada pelo
  instalador e pelo webhook que você configurar.

---

## Requisitos

| Item | Recomendado |
|---|---|
| Sistema | Windows 10 ou 11, 64 bits |
| Python | **3.11 ou superior** (testado em 3.12 e 3.14) |
| Jogo | Fortnite instalado e conta já logada |
| Modo de vídeo | **Janela sem borda** (windowed fullscreen) |
| Resolução | **1920×1080** como referência (outras resoluções são escaladas) |
| Modo de jogo | Battle Royale com **Squad + Fill (Preencher)** |
| Conta | De preferência uma conta alternativa; veja o aviso no topo |
| Energia | Suspensão do Windows desativada durante o farm |

> [!TIP]
> Para o modo segundo plano ficar fluido, desative nas configurações do Fortnite
> a opção que **suspende o jogo quando ele perde o foco**, se ela existir na sua
> versão. O bot até clica em **CONTINUAR JOGANDO**, mas o jogo suspenso deixa de
> renderizar e a detecção fica mais lenta.

---

## Instalação

### Opção 1 — automática (recomendada)

**Você não precisa instalar o Python manualmente.** O instalador procura uma
versão compatível, baixa o Python 3.12 oficial se necessário, cria a `.venv`,
instala as dependências e deixa um atalho **Pirate Farm** na área de trabalho.

1. Baixe o projeto pelo botão **Code → Download ZIP** no GitHub e extraia a
   pasta em um local fixo (por exemplo `C:\PirateFarm`).
2. Dê dois cliques em **`Instalar.bat`**.
3. Aguarde a mensagem **“Instalação concluída!”**.
4. Abra pelo atalho da área de trabalho ou por **`Iniciar.bat`**.

Se o Windows bloquear o `.bat`, clique com o botão direito → **Propriedades** →
desmarque **Bloqueado** e execute de novo. O instalador precisa de internet;
depois de instalado, o app funciona offline (exceto se você ativar o webhook).

> [!TIP]
> A instalação não exige conhecimentos de Python nem uso do terminal. O
> `Instalar.bat` também pode ser executado novamente para atualizar as
> dependências depois de baixar uma versão nova do projeto.

### Opção 2 — manual

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\pythonw.exe main.py
```

Para ver o console e mensagens de erro:

```powershell
.venv\Scripts\python.exe main.py
```

Dependências: `opencv-python`, `numpy`, `mss`, `pydirectinput`, `pywin32` e
os pacotes `winrt` do OCR do Windows. A internet é usada na instalação e,
opcionalmente, pelo webhook; fora isso o aplicativo roda offline.

---

## Como usar

### Antes de iniciar

1. Abra o Fortnite e faça login.
2. Selecione **Battle Royale**.
3. Selecione **Squad** e ative **Fill / Preencher**.
4. Deixe o jogo no **lobby**, em **janela sem borda**, e **não minimize**.
5. Feche overlays que possam cobrir a tela do jogo (alguns overlays de captura
   também atrapalham o `PrintWindow`).

### Iniciar o farm

1. Dê dois cliques em **`Iniciar.bat`** (ou use o atalho **Pirate Farm**).
2. Confira se a opção **Segundo plano** está marcada (padrão).
3. Clique em **INICIAR**.
4. Pode usar o computador normalmente. O jogo continuará rodando atrás das
   outras janelas; ele **não pode** ser minimizado.
5. Quando o bot precisar clicar, o Fortnite virá para a frente por ~1 s e depois
   devolverá o foco ao seu programa.
6. Para parar a qualquer momento, pressione **F8** ou clique em **PARAR (F8)**.

> [!NOTE]
> O foco rápido é curto, mas pode interromper uma digitação. Se estiver
> trabalhando, prefira usar outro computador/usuário ou aceite esse pequeno
> roubo de foco.

### Primeiro teste (recomendado)

Antes de deixar o bot sozinho:

1. Marque **Simulação**. Nesse modo o bot não clica nem pressiona teclas.
2. Clique em **INICIAR** e comece uma partida manualmente no Fortnite.
3. Acompanhe o registro: o bot deve identificar lobby, partida e pós-partida.
4. Use **Testar detecção agora** com o jogo no lobby: ele salva
   `logs\teste_tela.png` e informa se encontrou **JOGAR**, a tela de suspensão ou
   o token.
5. Pare com **F8** e faça uma partida real supervisionada, com **Simulação**
   desmarcada.

### Quando o token é encontrado

- O app mostra **“TOKEN ENCONTRADO!”** e toca um alerta.
- O bot espera a partida atual terminar e volta ao lobby.
- Se a tela de recompensa aparecer, ele clica em **CLAIM ALL**.
- O arquivo **`TOKEN_ENCONTRADO.txt`** é criado na pasta do projeto.
- O app fecha sozinho após **30 segundos** (configurável).

Se você já tem o token e o bot está rodando, clique em **“Já tenho o token”**:
ele não inicia outra partida e encerra ao voltar ao lobby.

---

## Recompensas e webhook

Sempre que um banner de recompensa aparece no centro da tela, o bot tenta ler o
nome pelo OCR do Windows. O resultado aparece no contador **Recompensas** e no
registro, por exemplo:

```text
Recompensa detectada: Dispositivo Elemental (via OCR, confiança 0.85).
Texto lido: VOCÊ ENCONTROU DISPOSITIVO ELEMENTAL
```

O banner do token é normalizado para **Acesso à Loja Pirata** e também marca o
estado do token, mesmo que a detecção venha do texto e não do template visual.

### Como o baú do token aparece

Relatos públicos mostram que o baú do token fica **dourado, treme por alguns
segundos e demora mais para abrir** antes do banner `YOU FOUND PIRATE SHOP
ACCESS`. Porém, baús e recompensas comuns também podem brilhar em dourado (por
exemplo, o localizador de sprite). Por isso o brilho é usado apenas como
**precue**: ele acelera as próximas capturas por 10 segundos. A confirmação do
token continua vindo da moeda dourada, do banner ou do texto lido pelo OCR.

### Aba Webhook

1. Abra a aba **Webhook**.
2. Cole a URL do webhook (Discord ou outro endpoint).
3. Escolha o que enviar: **captura**, **token** e/ou **outras recompensas**.
4. Clique em **Testar webhook** para enviar uma mensagem de teste.
5. Clique em **Salvar configuração**. Se o farm estiver rodando, a nova URL é
   aplicada na hora, sem reiniciar.

O envio leva a captura PNG do banner e o nome identificado. Para webhooks do
Discord o payload é nativo (`payload_json` + `files[0]`); para os demais
endpoints é usado `multipart/form-data` com os campos `content`, `reward`,
`kind`, `matches`, `elapsed` e `file`. A URL é mascarada nos logs.

Se o OCR não reconhecer o idioma (por exemplo, interface em árabe sem o pacote
de OCR instalado), a captura continua sendo enviada com o nome
**“Recompensa encontrada”** desde que o brasão dourado do banner seja
detectado. O envio não depende do idioma da interface.

> [!NOTE]
> O webhook é totalmente opcional. Sem ele, nenhuma imagem sai do computador.
> Para o OCR identificar nomes em outros idiomas, instale o pacote de idioma
> correspondente em **Configurações → Hora e idioma → Idioma e região**.

## Limpeza automática de capturas

As capturas de diagnóstico ficam em `logs\snapshots\`. Para evitar que a pasta
cresça sem limite, o app aplica a política de retenção na inicialização, a cada
`prune_interval_seconds` e ao encerrar:

| Critério | Padrão | Efeito |
|---|---:|---|
| Máximo de arquivos | `300` | Remove as capturas mais antigas acima do limite |
| Idade máxima | `3` dias | Remove capturas mais velhas que isso |
| Mínimo a manter | `20` | As capturas mais recentes nunca são apagadas |
| Carência | `120` s | Arquivos recém-gravados ficam protegidos |

As evidências do token (`token_*`, `tela_recompensa_*`) nunca são apagadas. Os
banners genéricos (`reward_*`) e as capturas de pós-partida entram na limpeza
normal. A aba **Farm** mostra a quantidade e o tamanho da pasta, com botões
**Limpar agora** e **Abrir pasta**. A limpeza não interrompe uploads em
andamento: o webhook envia os bytes da imagem que já estão em memória.

---

## Modo segundo plano

O modo segundo plano é o padrão e permite usar o PC durante o farm.

| Recurso | Como funciona |
|---|---|
| Captura | `PrintWindow` com `PW_RENDERFULLCONTENT` captura a janela encoberta |
| Foco | O jogo é trazido à frente só para o clique/tecla e o foco anterior é restaurado |
| Cursor | A posição do mouse é salva e devolvida após a ação |
| Limite | A janela **não pode estar minimizada** |
| Limite | **Tela cheia exclusiva** não permite a captura em segundo plano |
| Limite | O jogo precisa continuar renderizando; evite a suspensão do Fortnite |

Se o `PrintWindow` falhar, o bot registra um aviso e tenta novamente. Para voltar
ao modo antigo, desmarque **Segundo plano** na interface — nesse caso, deixe o
Fortnite em primeiro plano e não use o PC durante o farm.

---

## Configuração

As opções ficam em **`config.json`**. A interface salva automaticamente
`background_mode` e `dry_run` quando você clica em **INICIAR**. Coordenadas são
relativas a **1920×1080** e escaladas para o tamanho real da janela.

| Campo | Padrão | Descrição |
|---|---:|---|
| `behavior.background_mode` | `true` | Captura sem roubar o foco e foco rápido para clicar |
| `behavior.dry_run` | `false` | Modo simulação: não clica nem pressiona teclas |
| `behavior.scan_interval_match` | `1.6` | Intervalo (s) entre verificações do token na partida |
| `behavior.max_matches` | `0` | Máximo de partidas; `0` = sem limite |
| `behavior.max_runtime_minutes` | `180` | Tempo máximo em minutos; `0` = sem limite (maior risco de ban) |
| `behavior.auto_close_success_seconds` | `30` | Segundos até fechar após achar o token; `0` = não fecha |
| `behavior.claim_timeout` | `20.0` | Tempo (s) procurando a tela de recompensa |
| `behavior.matchmaking_timeout` | `240.0` | Tempo (s) esperando a partida começar |
| `behavior.postmatch_click_after` | `8.0` | Espera (s) antes de clicar no resumo |
| `behavior.postmatch_click_retry` | `6.0` | Intervalo (s) entre tentativas de clique no resumo |
| `behavior.postmatch_menu_after` | `14.0` | Espera (s) para abrir o menu com ESC quando o resumo não tem botões |
| `behavior.postmatch_timeout` | `180.0` | Tempo (s) máximo nas telas de pós-partida |
| `behavior.squad_leave_delay` | `10.0` | Espera (s) antes de sair quando o esquadrão fica vazio |
| `behavior.squad_leave_retry` | `20.0` | Intervalo (s) entre tentativas de saída |
| `ui.play_button` | `[265, 938]` | Centro do botão JOGAR no lobby |
| `ui.suspend_continue` | `[960, 496]` | Centro de CONTINUAR JOGANDO |
| `ui.claim_button` | `[965, 992]` | Centro do CLAIM ALL |
| `detection.inner_score` | `0.62` | Limiar do template interno do token |
| `detection.inner_score_small` | `0.72` | Limiar para tokens pequenos (banner e ícones) |
| `detection.token_center_min_x` | `0.20` | Início da faixa horizontal aceita para o token |
| `detection.token_center_max_x` | `0.80` | Fim da faixa horizontal aceita para o token |
| `detection.token_center_max_y` | `0.70` | Altura máxima do centro do token (evita texturas do cenário) |
| `detection.white_max_inner` | `0.80` | Branco máximo no centro do disco (evita efeitos dourados) |
| `detection.frame_score` | `0.70` | Limiar do quadro dourado do banner |
| `detection.play_again_score` | `0.65` | Limiar do botão JOGAR NOVAMENTE |
| `detection.return_lobby_score` | `0.65` | Limiar do botão RETORNAR AO LOBBY |
| `detection.voltar_lobby_score` | `0.62` | Limiar do botão Voltar ao Lobby no menu |
| `detection.menu_tab_score` | `0.75` | Limiar da aba de opções do painel social |
| `rewards.ocr_enabled` | `true` | Lê o nome da recompensa com o OCR do Windows |
| `rewards.scan_interval` | `2.0` | Intervalo (s) entre leituras de recompensa |
| `rewards.cooldown_seconds` | `12.0` | Evita repetir a mesma recompensa nesse intervalo |
| `rewards.token_cooldown_seconds` | `3600.0` | Evita repetir o token por uma hora |
| `rewards.fallback_banner_score` | `0.80` | Confiança do brasão dourado para o fallback sem OCR |
| `rewards.chest_precue_enabled` | `true` | Acelera a leitura quando um baú brilha em dourado no centro |
| `rewards.chest_precue_min_gold` | `0.18` | Dourado mínimo na região central para o precue |
| `rewards.chest_precue_delta` | `0.07` | Aumento mínimo do dourado entre capturas para disparar |
| `rewards.chest_precue_watch_seconds` | `10.0` | Tempo de leitura acelerada após o clarão |
| `rewards.chest_precue_cooldown_seconds` | `15.0` | Intervalo mínimo entre dois precues |
| `storage.snapshot_max_files` | `300` | Máximo de capturas mantidas; `0` desativa |
| `storage.snapshot_max_age_days` | `3` | Idade máxima das capturas em dias; `0` desativa |
| `storage.snapshot_min_keep` | `20` | Quantidade de capturas recentes sempre mantidas |
| `storage.snapshot_grace_seconds` | `120` | Carência para arquivos recém-criados |
| `storage.prune_interval_seconds` | `120.0` | Intervalo da limpeza automática |
| `webhook.enabled` | `false` | Ativa o envio de recompensas para a URL configurada |
| `webhook.url` | `""` | URL do Discord ou endpoint `multipart/form-data` |
| `webhook.send_screenshot` | `true` | Anexa a captura PNG ao envio |
| `webhook.send_token` | `true` | Envia o banner do token |
| `webhook.send_rewards` | `true` | Envia as demais recompensas |
| `webhook.username` | `Pirate Farm` | Nome exibido no Discord |
| `webhook.timeout_seconds` | `15.0` | Timeout de cada envio |
| `webhook.max_queue` | `50` | Tamanho máximo da fila de envios |

> [!TIP]
> Para testar com poucas partidas, use `max_matches: 2`. O campo **Limite
> (min)** na aba **Farm** também salva `max_runtime_minutes` (padrão `180`).
> Sessões acima de 4 horas aumentam bastante o risco de ban por AFK.

---

## Como funciona

```text
FortniteGame.log ──► lobby / matchmaking / partida / pós-partida
        │
        └── PrintWindow ──► OpenCV ──► token / JOGAR / CONTINUAR / CLAIM ALL
                                  │
                                  ├── OCR do Windows ──► nome da recompensa
                                  └── brasão dourado ──► fallback sem idioma
                                             │
                                             └── webhook opcional (captura + nome)
```

A máquina de estados, as threads e o fluxo de decisão estão detalhados em
[docs/ARQUITETURA.md](docs/ARQUITETURA.md).

### Log do Fortnite

O arquivo `%LOCALAPPDATA%\FortniteGame\Saved\Logs\FortniteGame.log` é lido de
forma incremental. Entre os eventos usados:

| Evento | Significado |
|---|---|
| `UI State ... [UI.State.Athena.Frontend]` | lobby |
| `UI State ... [UI.State.Athena.BattleRoyale]` | partida |
| `EAthenaGamePhase::EndGame` | fim da partida |
| `Match State Changed ... WaitingPostMatch/LeavingMap` | tela de pós-partida |
| `WBP_PostMatchPanelContainer` | widget do resumo da partida |
| `OnPlayerPawnDied` | seu personagem morreu |
| `LogSocialChatManager ... Pl:/PlayerAdded/PlayerRemoved` | preenchimentos entram e saem do esquadrão |
| `LogSpectateAfterDeathViewTarget ... No teammates available to follow` | o jogo não encontrou alvo para espectar; sozinho não confirma que o esquadrão acabou |

### Visão computacional

- **`assets/coin_inner.png`** — disco dourado com o “F” branco, usado nas telas
  de recompensa.
- **`assets/coin_banner_frame.png`** — quadro dourado do banner do token.
- **`assets/play_button.png`** e **`assets/suspend_button.png`** — botões do
  lobby e da tela de suspensão.
- **`assets/play_again.png`** e **`assets/return_lobby.png`** — botões do resumo
  da partida (**JOGAR NOVAMENTE** e **RETORNAR AO LOBBY**).
- **`assets/voltar_lobby.png`** — botão **Voltar ao Lobby** do menu de pausa
  novo; **`assets/menu_tab.png`** — aba de três linhas que abre esse botão no
  painel social. **`assets/exit_icon.png`** mantém o fluxo da interface antiga
  como fallback.

Cada acerto é validado por proporção de dourado e presença de branco no centro,
o que reduz falsos positivos no lobby e no desktop. O token também precisa estar
no centro-alto da tela; texturas douradas no canto do cenário são descartadas.

Para as recompensas, o **OCR** lê a faixa central e o parser aceita cabeçalhos
em português, inglês e árabe. O texto é filtrado pelas linhas próximas ao
cabeçalho, para que nomes de jogadores e kill feed não entrem no nome. Se o
texto não for legível, `reward_badge_score` confere a estrutura do brasão
(faixa dourada central + ícone emoldurado acima) e libera o envio com o rótulo
genérico. Telas de carregamento e HUD não têm esse par e são descartadas.

### Entrada

- Cliques: `SetCursorPos` + `mouse_event`.
- Foco: `SetForegroundWindow` com fallback por `AttachThreadInput`.
- Teclas: `pydirectinput` (SendInput).
- F8: `RegisterHotKey`, sem hooks globais de teclado.
- Suspensão do Windows: `SetThreadExecutionState` em um worker dedicado.

---

## Testes

O autoteste não abre o jogo nem clica em nada:

```powershell
.venv\Scripts\python.exe selftest.py
```

Para validar também a captura ao vivo (Fortnite aberto, sem focar o jogo):

```powershell
.venv\Scripts\python.exe selftest.py --live
```

O teste cobre templates do token, imagens negativas, botões JOGAR/CONTINUAR,
pós-partida por clique visual, menu **Voltar ao Lobby**, rastreamento dos
preenchimentos, captura em segundo plano, prevenção de suspensão, parser do log
real, OCR/parser de recompensas (incluindo árabe), brasão dourado, deduplicação,
retenção de capturas, payloads de webhook e envio HTTP local. São 117
verificações offline; o workflow de CI roda a compilação, o verificador de links
da documentação e o autoteste no Windows.

Para diagnosticar o resumo da partida ou o menu de pausa sem clicar no jogo:

```powershell
.venv\Scripts\python.exe tools\check_postmatch.py
```

O script mostra a confiança de cada template e salva
`logs\diagnostico_pos_partida.png`. Os fluxos que dependem da tela real estão
no [guia de validação supervisionada](docs/VALIDACAO.md).

Para conferir os links relativos da documentação antes de abrir um pull
request:

```powershell
.venv\Scripts\python.exe tools\check_docs.py
```

---

## Estrutura do projeto

```text
fortnite_pirate_farm/
├── main.py                     # interface Tkinter em modo escuro (abas Farm/Webhook)
├── selftest.py                 # testes offline e ao vivo
├── config.json                 # coordenadas, comportamento, recompensas e webhook
├── Instalar.bat                # instalação em um clique (sem Python manual)
├── Iniciar.bat                 # abre o app pelo terminal
├── Iniciar.vbs                 # abre sem console (usado pelo atalho)
├── run.bat                     # atalho antigo de compatibilidade
├── run_debug.bat               # abre com console para diagnóstico
├── piratebot/
│   ├── bot.py                  # máquina de estados do farm
│   ├── config.py               # leitura/gravação da configuração
│   ├── controller.py           # foco rápido, cliques e teclas
│   ├── hotkey.py               # atalho global F8
│   ├── logwatcher.py           # leitura incremental do log
│   ├── power.py                # prevenção de suspensão do Windows
│   ├── retention.py            # limpeza automática das capturas
│   ├── rewards.py              # OCR, parser e brasão das recompensas
│   ├── squad.py                # rastreamento dos preenchimentos
│   ├── vision.py               # PrintWindow, templates e OpenCV
│   └── webhook.py              # fila e envio multipart para o webhook
├── assets/
│   ├── logo.png                # identidade visual
│   ├── logo.ico                # ícone do instalador/atalho
│   ├── coin_inner.png
│   ├── coin_banner_frame.png
│   ├── play_button.png
│   ├── suspend_button.png
│   ├── play_again.png
│   ├── return_lobby.png
│   ├── voltar_lobby.png
│   ├── menu_tab.png
│   ├── exit_icon.png
│   └── test/                   # imagens de referência do autoteste
├── docs/
│   ├── banner.png
│   ├── screenshot.png
│   ├── social_preview.png
│   ├── ARQUITETURA.md          # máquina de estados e componentes
│   ├── CALIBRAGEM.md           # recaptura e validação de templates
│   ├── VALIDACAO.md            # roteiro de teste supervisionado
│   └── RELEASE.md              # checklist de publicação
├── tools/
│   ├── instalar.ps1            # lógica do instalador automático
│   ├── make_branding.py        # gera logo/banner (requer Pillow)
│   ├── check_bg_capture.py     # diagnóstico da captura em segundo plano
│   └── check_postmatch.py      # diagnose visual do resumo (não clica)
├── .github/workflows/tests.yml # CI de compilação e autoteste
└── logs/                       # criado em tempo de execução
```

---

## Solução de problemas

| Problema | O que fazer |
|---|---|
| **“Janela do Fortnite não encontrada”** | Abra o Fortnite, use janela sem borda e não minimize. Verifique se o título da janela contém `Fortnite`. |
| **“Falha na captura em segundo plano”** | Confirme que o jogo não está minimizado, desative tela cheia exclusiva e a suspensão do Fortnite. Teste **Testar detecção agora**. |
| **O bot não clica em JOGAR** | Use **Testar detecção agora** e veja `logs\teste_tela.png`. Confirme o lobby, o modo Battle Royale e o Squad + Fill. |
| **Token não detectado** | Veja as capturas em `logs\snapshots\`. Atualizações do jogo podem mudar a arte; siga o [guia de calibragem](docs/CALIBRAGEM.md) para recapturar o template. |
| **O jogo entra em suspensão** | O bot tenta **CONTINUAR JOGANDO**, mas o ideal é desativar a suspensão nas configurações do Fortnite e manter a janela sem borda. |
| **O PC dorme ou a tela bloqueia** | Ative **Manter PC acordado** e desative a suspensão/bloqueio automático no Windows. `Win+L` manual não é impedido. |
| **A tela de pós-partida não avança** | Confira as capturas `logs\snapshots\pos_partida_*.png`. Ajuste `postmatch_click_after`/`postmatch_click_retry` e, se o resumo não tiver botões, `postmatch_menu_after`. |
| **O bot para sozinho após algumas horas** | É o limite de execução (padrão `180` min). Ajuste **Limite (min)** na aba **Farm** ou `behavior.max_runtime_minutes`; `0` desativa o limite, mas aumenta o risco de ban por AFK. |
| **Recebi ban por AFK** | O limite de execução reduz a exposição, mas não elimina o risco. Não use movimento automático para burlar a detecção; prefira sessões curtas e supervisionadas. |
| **Não sei qual botão o resumo exibe** | Rode `tools\check_postmatch.py` e veja a confiança de cada template. O diagnóstico não clica no jogo. |
| **Falso positivo de token** | Guarde a captura de `logs\snapshots\` e abra uma issue; não aumente o limiar sem testar as imagens negativas. O detector já exige o token no centro-alto da tela. |
| **Webhook não envia** | Confira **Webhook ativado**, a URL e use **Testar webhook**. Erros de rede aparecem no registro; a URL é mascarada. |
| **Nome da recompensa sempre genérico** | O OCR pode não ter o pacote do idioma da interface. Para português, instale o pacote **Português (Brasil)** em **Idioma e região**; a captura continua sendo enviada pelo fallback do brasão. |
| **As capturas antigas desapareceram** | É a limpeza automática. Ajuste `storage.snapshot_max_files`, `snapshot_max_age_days` ou `snapshot_min_keep` na aba **Farm**. Evidências `token_*` e `tela_recompensa_*` nunca são removidas. |
| **Python não encontrado ao iniciar** | Rode **`Instalar.bat`** de novo; ele baixa e instala o Python 3.12 automaticamente. Não é preciso mexer no PATH. |
| **O app não abre** | Rode **`Instalar.bat`** e depois **`Iniciar.bat`**. Para ver o console, use `run_debug.bat` e envie o erro junto com a versão do Windows. |

---

## Limitações e avisos

- **Somente Windows.** A captura, o foco e os cliques usam APIs nativas do
  Windows.
- **Calibrado em 1920×1080 e interface PT-BR.** Outras resoluções e idiomas podem
  exigir ajustes nos templates/coordenadas.
- **A primeira partida real deve ser supervisionada.** A tela de recompensa e o
  CLAIM ALL ainda podem variar conforme o evento/atualização.
- **Não minimize o Fortnite** e não use tela cheia exclusiva no modo segundo
  plano.
- **Atualizações do Fortnite podem quebrar a detecção.** O projeto é
  experimental e não tem vínculo com a Epic Games.
- **Risco de conta:** automação pode violar os Termos de Serviço. Você é
  responsável pelo uso e por qualquer consequência na sua conta.
- **Sem garantias.** O software é fornecido sob a licença MIT, sem garantia de
  funcionamento ou de obtenção do token.

---

## Privacidade

Por padrão, o aplicativo **não acessa a internet** durante a execução. Ele lê
apenas o log local do Fortnite, captura a janela do jogo e grava logs/capturas
na pasta do projeto. Nenhuma credencial do jogo é solicitada ou armazenada.

Se você ativar o webhook, as capturas dos banners e os nomes identificados são
enviados para a URL que você configurou. A URL fica no `config.json` local e é
mascarada nos logs; não publique essa URL em issues ou capturas de tela. As
imagens de badge do README são carregadas pelo GitHub, não pelo aplicativo.

---

## Contribuindo

Ideias, correções e novos templates são bem-vindos. Leia
[CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir uma issue ou pull request.
Inclua o resultado do `selftest.py`, a resolução do jogo e, quando for um
problema visual, uma captura sem dados pessoais. Quem for publicar uma versão
deve seguir o [checklist de release](docs/RELEASE.md).

---

## Licença

Distribuído sob a licença [MIT](LICENSE). Copyright © 2026 nvd7.

**Pirate Farm não é afiliado, associado ou endossado pela Epic Games.** Fortnite
é uma marca registrada da Epic Games, Inc.
