# Validação supervisionada

Este guia cobre os fluxos que dependem da tela real do Fortnite. Rode o
autoteste offline antes de começar e faça a primeira validação com o jogo em
**janela sem borda**, no lobby e sem overlays.

```powershell
.venv\Scripts\python.exe selftest.py
.venv\Scripts\python.exe tools\check_postmatch.py
```

O diagnóstico acima não clica em nada: ele apenas captura a janela e mostra a
confiança dos templates do token, do resumo e do menu.

## Antes de iniciar

- [ ] O Fortnite está no lobby, em **Squad + Fill (Preencher)**.
- [ ] A janela está em **1920×1080** ou em uma resolução compatível.
- [ ] A opção **Segundo plano** está marcada.
- [ ] `dry_run` está `false` no `config.json`.
- [ ] O app mostra **v1.3.0** no cabeçalho.
- [ ] O campo **Limite (min)** está em `180` ou menos (evita sessões longas de AFK).
- [ ] **Parar sem atividade** está marcado com `30` min (ou um valor menor).
- [ ] **Parar em aviso de AFK** está marcado.
- [ ] A aba **Webhook** está configurada, se o envio for testado.

## 1. Pós-partida com JOGAR NOVAMENTE

1. Clique em **INICIAR** e deixe a partida terminar.
2. Na tela de resumo, o log deve mostrar:

   ```text
   Fim da partida detectado ...
   Botão JOGAR NOVAMENTE detectado (confiança ...). Clicando...
   JOGAR NOVAMENTE clicado; aguardando a partida iniciar sem abrir o menu.
   Partida iniciada (2) (evento do log). AFK ativado; procurando o token.
   ```

3. O bot deve permanecer na tela de matchmaking até a partida começar. Ele
   **não** deve abrir o menu com **ESC** durante a fila.
4. Confira se o contador **Partidas** aumentou apenas uma vez.

Se o bot não encontrar o botão:

- veja `logs\snapshots\pos_partida_*.png`;
- rode `tools\check_postmatch.py` com o resumo aberto;
- ajuste `detection.play_again_score` ou siga o
  [guia de calibragem](CALIBRAGEM.md) para recapturar o template.

## 2. Pós-partida com token

1. Deixe o token aparecer durante uma partida.
2. Confirme o log:

   ```text
   TOKEN PIRATA DETECTADO!
   ```

3. Ao terminar, o bot deve clicar em **RETORNAR AO LOBBY** e procurar o
   **CLAIM ALL**.
4. O arquivo `TOKEN_ENCONTRADO.txt` deve ser criado e o app deve encerrar após
   `auto_close_success_seconds`.

O bot nunca agenda saída automática depois de encontrar o token.

## 3. Recompensas, OCR e webhook

1. Abra a aba **Webhook**, cole a URL, marque **Webhook ativado** e clique em
   **Testar webhook**. O registro deve confirmar o envio.
2. Clique em **Salvar configuração** e inicie uma partida.
3. Abra um baú ou receba uma recompensa e confira no registro:

   ```text
   Recompensa detectada: Dispositivo Elemental (via OCR, confiança 0.85).
   Texto lido: VOCÊ ENCONTROU DISPOSITIVO ELEMENTAL
   Captura adicionada à fila do webhook.
   ```

4. No Discord (ou no endpoint), a mensagem deve chegar com o nome e a captura
   do banner centralizado.
5. Repita com a interface em outro idioma, se possível. Sem OCR legível, a
   mensagem deve usar **“Recompensa encontrada”**, mas a captura deve continuar
   sendo enviada.
6. Use **Testar OCR na tela** com o banner aberto e confira os valores de
   `banner` e `brasão` no registro.

Checklist:

- [ ] O banner genérico foi enviado com o nome lido.
- [ ] O banner do token foi normalizado para **Acesso à Loja Pirata**.
- [ ] Telas de carregamento, espectador e HUD **não** geraram recompensa.
- [ ] Um clarão dourado de baú acelerou a leitura sem marcar token sozinho.
- [ ] O webhook recebeu a captura PNG e o nome.
- [ ] A URL aparece mascarada no registro.

## 4. Limpeza de capturas

1. Na aba **Farm**, confira a quantidade e o tamanho em **Capturas
   automáticas**.
2. Clique em **Limpar agora** e veja o resultado no registro.
3. Confirme que arquivos `token_*` e `tela_recompensa_*` continuam na pasta.
4. Ajuste os campos de retenção e clique em **Salvar** (ou reinicie) para
   aplicar.

Checklist:

- [ ] A pasta ficou dentro de `snapshot_max_files`.
- [ ] As capturas mais recentes foram preservadas.
- [ ] As evidências do token continuam intactas.
- [ ] Um upload de webhook em andamento não foi interrompido pela limpeza.

## 5. Último sobrevivente (sem botões no resumo)

Esse é o caso em que o resumo não exibe **JOGAR NOVAMENTE** nem **RETORNAR AO
LOBBY**. O bot deve abrir o painel com **ESC**, clicar na aba de três linhas e
só então clicar em **Voltar ao Lobby**.

Sinais esperados no log:

```text
Resumo sem os botões de continuar (último sobrevivente). Abrindo o painel com ESC para chegar em 'Voltar ao Lobby'.
Botão Aba de opções (menu) detectado ... Clicando...
Botão Voltar ao Lobby (menu) detectado ... Clicando...
```

Checklist:

- [ ] O painel social abriu com **ESC**.
- [ ] A aba de três linhas foi clicada antes de **Voltar ao Lobby**.
- [ ] O clique ocorreu em **Voltar ao Lobby** (parte superior direita).
- [ ] O bot voltou ao lobby e reenfileirou.
- [ ] Nenhum ENTER/ESPAÇO foi enviado ao jogo.
- [ ] O painel não foi fechado por um segundo **ESC**.

Se o menu não for encontrado, o bot tenta novamente a cada
`postmatch_click_retry` segundos e desiste em `postmatch_timeout`.

## 6. Saída quando o esquadrão fica vazio

1. Entre em uma partida com fills.
2. Quando o chat confirmar que todos saíram, o log deve mostrar:

   ```text
   Todos os preenchimentos saíram da partida (o último preenchimento saiu (...)). Vou sair em 10s se ninguém voltar.
   Abrindo o menu para sair da partida (tentativa 1).
   Aba de opções detectada ... Abrindo 'Voltar ao Lobby'...
   Botão 'Voltar ao Lobby' detectado ... Clicando...
   Saída enviada. Aguardando o retorno ao lobby.
   ```

3. O bot deve voltar ao lobby e entrar em outra partida.

O evento `No teammates available to follow` pode aparecer com fills vivos e
**não** deve agendar a saída sozinho. Enquanto o chat listar preenchimentos, o
log pode mostrar a mensagem de que o bot continua AFK. Só depois que o
rastreador ficar vazio a saída é agendada.

Teste também o cancelamento: se um fill voltar antes do clique, o log deve
mostrar **Saída automática cancelada** e o bot deve continuar AFK.

## 7. Proteção de presença e AFK

1. Para testar rápido, marque **Parar sem atividade** e use `5` minutos.
2. Inicie o farm e deixe teclado/mouse parados. O log deve mostrar um aviso
   perto da metade do limite e depois:

   ```text
   Resumo da sessão: 00:05:xx de execução, ...
   Sem atividade de teclado/mouse há 5 min (limite: 5 min). O farm parou por segurança...
   ```

3. O app deve voltar para **Parado** e não deve continuar clicando no jogo.
4. Se a tela **“AINDA ESTÁ AÍ?”** aparecer, o log deve mostrar
   **Tela de presença ... O farm parou por segurança e não clicou em CONTINUAR
   JOGANDO.** A captura `presenca_*.png` deve ser salva e **não** deve existir
   um clique em `CONTINUAR JOGANDO`.
5. Se um aviso de AFK/inatividade aparecer, confira `aviso_afk_*.png` e o texto
   lido no registro. O parser também é coberto pelo autoteste, sem depender de
   esperar o jogo exibir o aviso.
6. Depois do teste, ajuste o limite para `30` min ou menos.

> [!IMPORTANT]
> O app não simula movimento nem clica em **CONTINUAR JOGANDO** para burlar o
> AFK. Se você desativar **Parar em aviso de AFK**, o comportamento antigo volta
> e o risco de punição aumenta.

## 8. Falhas e diagnóstico

Se algo não funcionar, guarde:

- o log mais recente em `logs\piratefarm_*.log`;
- as capturas `logs\snapshots\pos_partida_*.png`;
- a captura `logs\diagnostico_pos_partida.png` gerada pelo diagnóstico;
- a resolução do jogo e a versão do app.

Abra uma issue com o template **Falha de detecção** e remova nomes de jogadores,
IDs e outras informações pessoais das capturas antes de anexar.

## Configuração útil

| Campo | Efeito |
|---|---|
| `behavior.postmatch_click_after` | Espera antes de clicar no resumo |
| `behavior.postmatch_click_retry` | Intervalo entre tentativas de clique |
| `behavior.postmatch_menu_after` | Espera para abrir o menu quando não há botões |
| `behavior.matchmaking_timeout` | Limite da fila após JOGAR NOVAMENTE antes de liberar o ESC |
| `behavior.postmatch_timeout` | Limite para concluir o pós-partida |
| `behavior.squad_leave_delay` | Espera antes de sair com o esquadrão vazio |
| `behavior.squad_leave_retry` | Intervalo entre tentativas de saída |
| `behavior.max_runtime_minutes` | Limite da sessão em minutos; `0` desativa (maior risco de ban) |
| `detection.play_again_score` | Limiar do botão JOGAR NOVAMENTE |
| `detection.return_lobby_score` | Limiar do botão RETORNAR AO LOBBY |
| `detection.voltar_lobby_score` | Limiar do botão Voltar ao Lobby |
| `detection.menu_tab_score` | Limiar da aba de opções do painel social |
| `rewards.fallback_banner_score` | Confiança do brasão para o fallback sem OCR |
| `rewards.chest_precue_enabled` | Acelera a leitura após um clarão dourado central |
| `rewards.chest_precue_watch_seconds` | Duração da leitura acelerada |
| `rewards.scan_interval` | Intervalo entre leituras de recompensa |
| `storage.snapshot_max_files` | Máximo de capturas mantidas |
| `storage.snapshot_max_age_days` | Idade máxima das capturas |
| `storage.snapshot_min_keep` | Capturas recentes sempre mantidas |
| `webhook.enabled` / `webhook.url` | Ativação e destino do envio |

Depois de editar `config.json`, reinicie o app para carregar os valores de
detecção, retenção e comportamento. A URL do webhook pode ser alterada pela
própria aba **Webhook** e é aplicada na hora.
