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
- [ ] O app mostra **v1.1.2** no cabeçalho.

## 1. Pós-partida com JOGAR NOVAMENTE

1. Clique em **INICIAR** e deixe a partida terminar.
2. Na tela de resumo, o log deve mostrar:

   ```text
   Fim da partida detectado ...
   Botão JOGAR NOVAMENTE detectado (confiança ...). Clicando...
   ```

3. O bot deve voltar ao lobby e iniciar a partida seguinte.
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

## 3. Último sobrevivente (sem botões no resumo)

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

## 4. Saída quando o esquadrão fica vazio

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

## 5. Falhas e diagnóstico

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
| `behavior.postmatch_timeout` | Limite para concluir o pós-partida |
| `behavior.squad_leave_delay` | Espera antes de sair com o esquadrão vazio |
| `behavior.squad_leave_retry` | Intervalo entre tentativas de saída |
| `detection.play_again_score` | Limiar do botão JOGAR NOVAMENTE |
| `detection.return_lobby_score` | Limiar do botão RETORNAR AO LOBBY |
| `detection.voltar_lobby_score` | Limiar do botão Voltar ao Lobby |
| `detection.menu_tab_score` | Limiar da aba de opções do painel social |

Depois de editar `config.json`, reinicie o app para carregar os valores.
