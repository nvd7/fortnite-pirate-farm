# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.
O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto usa versionamento semântico.

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
- Guia de validação supervisionada, mapa da arquitetura e checklist de release
  em `docs/`.
- Diagnóstico `tools/check_postmatch.py` para inspecionar o resumo e o menu sem
  clicar no jogo.

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
- Autoteste ampliado para 72 verificações, cobrindo pós-partida sem ENTER/ESPAÇO,
  menu novo, morte sem companheiros, contagem de partidas e o diagnóstico visual.
- O workflow de CI agora salva a saída do autoteste e publica os artefatos quando
  a execução falha.

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
