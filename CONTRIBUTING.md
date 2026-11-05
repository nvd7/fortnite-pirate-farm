# Contribuindo com o Pirate Farm

Obrigado pelo interesse! Este projeto é uma automação local para Windows, com
interface em português e foco em simplicidade e transparência.

## Antes de abrir uma issue

1. Rode o autoteste e anexe o resultado:

   ```bat
   .venv\Scripts\python.exe selftest.py
   ```

2. Se o problema for visual, anexe a captura relevante de `logs\snapshots\`.
   Remova qualquer informação pessoal antes de publicar.
3. Informe a resolução do jogo, se está em janela sem borda, a versão do
   Windows e se o modo segundo plano estava ativo.

## Ambiente de desenvolvimento

```bat
git clone https://github.com/nvd7/fortnite-pirate-farm.git
cd fortnite-pirate-farm
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` inclui o Pillow, usado apenas para gerar a identidade
visual (`tools\make_branding.py`). O aplicativo não precisa dele em execução.

## Padrões do projeto

- Interface e mensagens em **português do Brasil**.
- Python 3.10+ com `from __future__ import annotations`.
- Evite dependências novas sem necessidade; o app deve continuar leve e local.
- Não adicione chamadas de rede. O bot lê apenas o log e a tela do jogo.
- Preserve o modo simulação e os fallbacks de detecção/teclado.
- Capturas e logs de execução não entram no repositório (veja `.gitignore`).

## Testes antes do pull request

```bat
.venv\Scripts\python.exe selftest.py
.venv\Scripts\python.exe selftest.py --live
```

O teste `--live` precisa do Fortnite aberto. Ele não clica nem rouba o foco.

## Commits e pull requests

- Use mensagens curtas e descritivas, por exemplo:
  `fix: evita falso positivo no banner do lobby`.
- Um pull request deve explicar o problema, a solução e como validou.
- Mudanças de template ou coordenada devem incluir a captura usada na
  calibração (sem dados pessoais) e o resultado do autoteste.

## Licença

Ao contribuir, você concorda que a contribuição será distribuída sob a licença
MIT deste repositório.
