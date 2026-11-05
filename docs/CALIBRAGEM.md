# Calibragem de templates

O bot compara recortes da interface do Fortnite com os arquivos de `assets/`.
Quando o jogo muda um botão, uma fonte ou uma cor, o template antigo pode
deixar de casar. Este guia mostra como recapturar e validar um template sem
quebrar os falsos positivos já cobertos pelo autoteste.

## Quando recalibrar

- O log mostra que o bot encontrou o resumo, mas nenhum botão é detectado.
- A captura em `logs\snapshots\` mostra o botão com aparência diferente.
- O autoteste passa nas imagens antigas, mas falha no jogo atual.
- Uma atualização do Fortnite mudou o idioma, a resolução ou o tema da loja.

## Antes de recortar

1. Deixe o jogo em **1920×1080**, janela sem borda e idioma **PT-BR**.
2. Abra a tela exata que contém o elemento (lobby, resumo ou menu de pausa).
3. Gere uma captura com o diagnóstico, que não clica no jogo:

   ```powershell
   .venv\Scripts\python.exe tools\check_postmatch.py
   ```

4. Abra `logs\diagnostico_pos_partida.png` e confirme que a captura não está
   preta, cortada ou com o jogo minimizado.

Para elementos do lobby, use **Testar detecção agora** no app ou
`tools\check_bg_capture.py`, que salva `logs\teste_bg_capture.png`.

## Recortando

- Recorte apenas o elemento: o texto e o fundo imediato do botão, sem barras
  externas, outros botões ou animações.
- Evite incluir o cursor do mouse, notificações, nomes de jogadores ou
  qualquer dado pessoal.
- Prefira PNG sem perda. JPEG introduz artefatos que reduzem a confiança.
- Mantenha o recorte pequeno. Templates grandes aumentam o custo da busca e
  podem capturar variações indesejadas.
- Salve com o nome esperado pelo detector:

  | Arquivo | Elemento |
  |---|---|
  | `assets/play_button.png` | **JOGAR** no lobby |
  | `assets/suspend_button.png` | **CONTINUAR JOGANDO** na suspensão |
  | `assets/play_again.png` | **JOGAR NOVAMENTE** no resumo |
  | `assets/return_lobby.png` | **RETORNAR AO LOBBY** no resumo |
  | `assets/voltar_lobby.png` | **Voltar ao Lobby** no menu de pausa |
  | `assets/menu_tab.png` | aba de três linhas do painel social |
  | `assets/exit_icon.png` | seta de saída da interface antiga |
  | `assets/coin_inner.png` | disco dourado do token |
  | `assets/coin_banner_frame.png` | quadro dourado do banner |

## Validando

Rode o autoteste completo:

```powershell
.venv\Scripts\python.exe selftest.py
```

O teste coloca o template em uma tela sintética e confere se o centro
encontrado é o esperado. Ele também verifica imagens negativas (lobby,
suspensão e desktop) para garantir que o novo recorte não gera falso positivo.

Se o template for aprovado, abra o jogo e rode o diagnóstico novamente para
ver a confiança no frame real:

```powershell
.venv\Scripts\python.exe tools\check_postmatch.py --json
```

Uma confiança acima do limiar configurado não garante acerto sozinha; confira
também o centro e o tamanho retornados.

## Ajustando limiares

Os limiares ficam em `config.json`, no bloco `detection`:

| Campo | Uso |
|---|---|
| `play_score` | botão JOGAR |
| `suspend_score` | botão CONTINUAR JOGANDO |
| `play_again_score` | botão JOGAR NOVAMENTE |
| `return_lobby_score` | botão RETORNAR AO LOBBY |
| `voltar_lobby_score` | botão Voltar ao Lobby |
| `menu_tab_score` | aba de opções do painel social |
| `exit_icon_score` | seta de saída |
| `inner_score` / `frame_score` | token |

Diminuir o limiar aumenta a sensibilidade e o risco de falso positivo.
Aumentar demais faz o bot ignorar o botão real. Prefira recapturar o template
antes de mexer no valor. Depois de editar `config.json`, reinicie o app.

## Se ainda não funcionar

- Confirme que o Fortnite não está minimizado nem em tela cheia exclusiva.
- Verifique se a captura em segundo plano contém a tela atual; alguns overlays
  aparecem apenas na captura de primeiro plano.
- Compare o tamanho do recorte com o template anterior.
- Anexe a captura de diagnóstico e o resultado do autoteste em uma issue,
  removendo nomes de jogadores e IDs.
