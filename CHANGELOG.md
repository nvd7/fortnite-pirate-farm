# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.
O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto usa versionamento semântico.

## [1.3.0] - 2026-11-09

### Adicionado

- **Proteção de presença:** o farm para após **30 minutos** sem teclado/mouse
  (`behavior.idle_stop_minutes`, configurável) e também quando a sessão do
  Windows está bloqueada. O encerramento registra o resumo da sessão com tempo,
  partidas e recompensas.
- **Parada segura em avisos de AFK:** leitura OCR completa da região central
  reconhece **“AINDA ESTÁ AÍ?”**, avisos de inatividade em português/inglês e
  equivalentes em árabe. O bot salva a captura e encerra a sessão **sem clicar
  em CONTINUAR JOGANDO**.
- Cartão **Proteção de sessão** na aba **Farm**, com limite de inatividade e
  opção de parar em aviso de AFK.
- Campos `behavior.idle_stop_minutes` e `behavior.stop_on_afk_warning` no
  `config.json`, com padrões seguros (`30` e `true`).

### Alterado

- A tela **“AINDA ESTÁ AÍ?”** agora encerra a sessão por padrão em vez de
  simular presença. O clique antigo em **CONTINUAR JOGANDO** só acontece se
  `stop_on_afk_warning` for desativado, e a interface avisa sobre o risco.
- O autoteste passou a cobrir o limite de inatividade, o parser de avisos de
  AFK, a leitura OCR completa, a parada do bot e os novos padrões de
  configuração (**145 verificações**).
- README, arquitetura e roteiro de validação documentam as proteções e o teste
  supervisionado.

> Esta versão **não** adiciona movimento, teclas ou check-in automático para
> burlar AFK. O objetivo é reduzir a exposição, não contornar a detecção.

## [1.2.1] - 2026-11-09

### Corrigido

- Falso positivo do fallback visual em telas de espectador: cenários dourados
  (porta, areia) e nomes de jogador no topo eram confundidos com o brasão de
  recompensa. Agora a faixa precisa ter tamanho compatível com o banner e o
  ícone acima dela deve ser aproximadamente quadrado. As capturas reais de
  espectador passaram a ser ignoradas, enquanto o banner verdadeiro continua
  sendo reconhecido.
- Autoteste ganhou dois casos sintéticos para impedir a regressão (125 testes).

## [1.2.0] - 2026-11-08

### Adicionado

- Leitura do nome das recompensas com o **OCR nativo do Windows**, incluindo
  cabeçalhos em português, inglês e árabe (`VOCÊ ENCONTROU`, `YOU FOUND`,
  `لقد عثرت على`). O nome é normalizado e o token vira **Acesso à Loja Pirata**.
- Aba **Webhook** na interface, com ativação, URL, filtros de token/outras
  recompensas, envio opcional da captura, botão de teste e aplicação imediata
  no farm em execução.
- Envio de cada banner centralizado para Discord (payload nativo) ou para
  qualquer endpoint `multipart/form-data`, com fila, deduplicação, timeout e
  URL mascarada nos logs.
- **Limpeza automática de capturas** por quantidade, idade e carência, com
  estatísticas de disco, botões **Limpar agora**/**Abrir pasta** e proteção
  permanente das evidências do token.
- Instalação em um clique com **`Instalar.bat`** e `tools/instalar.ps1`: baixa
  o Python 3.12 se necessário, cria a `.venv`, instala as dependências e cria o
  atalho **Pirate Farm** na área de trabalho. `Iniciar.bat` e `Iniciar.vbs`
  abrem o app sem console.
- Abas **Farm** e **Webhook**, contador de recompensas, controles de retenção e
  teste de OCR na tela.
- Fallback visual por **brasão dourado central** (faixa + ícone acima), que
  reconhece o banner mesmo sem OCR legível, inclusive em árabe.
- **Precue de baú dourado:** um clarão central acelera a leitura de recompensas
  por alguns segundos. O brilho não confirma o token; a confirmação continua
  sendo feita pela moeda, pelo banner e pelo OCR.
- **Limite de execução** editável na aba **Farm** (padrão de 180 minutos) e
  aviso destacado quando o limite é desativado ou muito longo, reduzindo a
  exposição a bans por AFK.
- Autoteste ampliado para **123 verificações**, com OCR/parser em três idiomas,
  brasão, precue de baú, deduplicação, retenção, payloads e envio HTTP local.

### Corrigido

- Falso “token encontrado” em texturas douradas do cenário: o detector agora
  exige o acerto no centro-alto da tela e usa `inner_score_small=0.72`.
- Falso positivo de recompensa em telas de carregamento, espectador e HUD: o
  fallback genérico exige o par dourado do brasão, não apenas brilho/banner.
- O OCR não mistura mais nomes de jogadores, kill feed e avisos laterais com o
  nome da recompensa; nomes em duas ou três linhas são unidos corretamente.
- Quantidades e pontuação coladas pelo OCR no fim do nome são removidas
  (`Dispositivo Elemental 1.,` vira `Dispositivo Elemental`), preservando
  números de modelo com dois dígitos.
- O estado do token também é marcado quando o texto da recompensa é lido pelo
  OCR, sem depender apenas do template visual.

### Alterado

- `config.json` ganhou os blocos `rewards`, `storage` e `webhook`, e o detector
  passou a aceitar `token_center_min_x`, `token_center_max_x` e
  `token_center_max_y`.
- O padrão de `behavior.max_runtime_minutes` passou de `0` para `180`; a
  interface permite alterar o limite e avisa quando ele fica em `0` ou acima de
  4 horas.
- A retenção protege apenas `token_*` e `tela_recompensa_*`; banners genéricos
  `reward_*` e capturas de pós-partida podem ser removidos.
- A documentação de instalação agora é voltada a usuários sem Python instalado.

### Removido

- `rewards.min_banner_score` e o fallback antigo por brilho genérico.

## [1.1.4] - 2026-11-06

### Corrigido

- Depois de clicar em **JOGAR NOVAMENTE**, o bot espera a tela de matchmaking e
  o início da partida seguinte. Antes, o fallback com **ESC** disparava poucos
  segundos depois do clique e devolvia o jogador ao lobby no meio da fila.
- O fallback com **ESC** só volta a valer se `matchmaking_timeout` estourar sem
  a partida começar.
- A mensagem de parada e a de erro não aparecem mais duplicadas no painel de
  log: o evento da interface não repete o texto já registrado pelo bot.
- O `config.json` de exemplo não limita mais a execução a 30 minutos; o padrão
  passou a ser `0` (sem limite), como já estava documentado.
- A mensagem de limite de tempo agora indica como ajustar
  `max_runtime_minutes`.

### Alterado

- Autoteste ampliado para 84 verificações, cobrindo a espera pela partida após
  **JOGAR NOVAMENTE** e a liberação do fallback quando o matchmaking expira.

## [1.1.3] - 2026-11-05

### Adicionado

- Template `assets/menu_tab.png` e opção `detection.menu_tab_score` para a aba
  de três linhas do painel social.

### Corrigido

- O evento `No teammates available to follow` não agenda mais a saída quando o
  chat ainda lista preenchimentos vivos. Ele só é usado como confirmação depois
  que o rastreamento do esquadrão fica vazio.
- A saída automática agora abre a aba de opções do painel social antes de
  clicar em **Voltar ao Lobby** e não pressiona ESC de novo quando o painel já
  está aberto, evitando fechá-lo por engano.
- O diagnóstico do pós-partida também mostra a confiança da aba de opções.

### Alterado

- Autoteste ampliado para 82 verificações, cobrindo a navegação do painel
  social e o falso sinal de espectador com fills vivos.

## [1.1.2] - 2026-11-05

### Adicionado

- Rastreamento dos preenchimentos pelo canal `BR.Any` do chat do Fortnite.
  O bot identifica quem entrou e quem saiu, ignorando o jogador local.
- Saída automática quando o último preenchimento abandona a partida, com
  cancelamento caso alguém volte e bloqueio quando o token já foi encontrado.
- Detecção dos botões **JOGAR NOVAMENTE**, **RETORNAR AO LOBBY** e **Voltar ao
  Lobby** (menu novo), com templates próprios em `assets/`.
- Fallback **ESC → Voltar ao Lobby** quando o resumo da partida não exibe
  botões, incluindo o caso em que o jogador local morre sem companheiros vivos
  (`No teammates available to follow`).
- Guia de validação supervisionada, mapa da arquitetura, guia de calibragem de
  templates e checklist de release em `docs/`.
- Diagnóstico `tools/check_postmatch.py` para inspecionar o resumo e o menu sem
  clicar no jogo.
- Verificador `tools/check_docs.py` para encontrar links relativos quebrados na
  documentação.

### Alterado

- O pós-partida agora clica visualmente em **JOGAR NOVAMENTE** para reenfileirar
  e em **RETORNAR AO LOBBY** quando o token foi encontrado ou o limite de
  partidas foi atingido. ENTER e ESPAÇO não são mais usados para avançar telas.
- A saída automática usa primeiro o botão **Voltar ao Lobby** do menu novo; a
  seta da interface antiga permanece como fallback.
- Na tela de morte o menu pode já estar aberto; o bot confere antes de pressionar
  ESC, evitando fechar o menu por engano.
- A transição do resumo para a partida seguinte volta a contabilizar a nova
  partida.
- Autoteste ampliado para 75 verificações, cobrindo pós-partida sem ENTER/ESPAÇO,
  menu novo, morte sem companheiros, contagem de partidas, diagnóstico visual e
  links da documentação.
- O workflow de CI agora verifica os links da documentação, salva a saída do
  autoteste e publica os artefatos quando a execução falha.

### Removido

- Opções `postmatch_enter_after`, `postmatch_space_after` e
  `postmatch_safe_click`, substituídas pelo clique visual nos botões do resumo.

## [1.1.1] - 2026-11-05

### Corrigido

- Falso positivo do token causado por personagens e efeitos dourados com muito
  branco no centro. A validação agora limita a proporção máxima de branco do
  disco dourado, além dos limites mínimos já existentes.
- Falso positivo no ícone dourado de "Equipar um Elemental" na tela de resumo
  da partida. O limiar dos templates pequenos subiu de 0,55 para 0,62, faixa
  que ainda aprova todas as capturas reais do token nos testes.
- `config.json` volta a salvar o caminho do log de forma portátil
  (`%LOCALAPPDATA%`), sem gravar o caminho absoluto do usuário.

## [1.1.0] - 2026-11-05

### Adicionado

- Modo **segundo plano**: captura do Fortnite encoberto com `PrintWindow` e
  `PW_RENDERFULLCONTENT`, sem trazer o jogo para a frente.
- **Foco rápido** (~1 s) para cliques e teclas, com restauração da janela em
  primeiro plano e da posição do cursor.
- Botão **Manter PC acordado**, com gerenciamento de motivos (`manual` e
  `bot`) e prevenção de suspensão/desligamento de tela por inatividade.
- Interface em **modo escuro**, barra de título escura no Windows 11,
  diálogos próprios e botão para limpar o registro.
- Identidade visual: logo, banner, social preview e ícone do aplicativo.
- Documentação completa de instalação, uso, configuração e solução de
  problemas.
- Workflow de testes no GitHub Actions.

### Alterado

- Captura em segundo plano é o padrão; o modo primeiro plano continua
  disponível na interface.
- O bot não rouba o foco periodicamente durante a partida no modo segundo
  plano.
- Mensagens de erro de captura são mais claras e incluem janela minimizada.
- Autoteste cobre captura em segundo plano, energia e imagens negativas.

### Corrigido

- Registro do atalho global F8 com a API nativa do Windows.
- Falsos positivos do banner do lobby.
- Barra de título permanecia clara por aplicar o tema antes da janela existir.

## [1.0.0] - 2026-11-05

### Adicionado

- Primeira versão funcional do farm AFK.
- Leitura incremental do `FortniteGame.log` e máquina de estados
  lobby → matchmaking → partida → pós-partida → lobby.
- Detecção visual do token Pirate Shop com OpenCV e validação de cor.
- Clique em JOGAR, CONTINUAR JOGANDO e CLAIM ALL.
- Atalho F8, modo simulação, logs, capturas e arquivo
  `TOKEN_ENCONTRADO.txt`.
