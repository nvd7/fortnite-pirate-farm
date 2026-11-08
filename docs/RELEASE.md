# Checklist de release

Este documento descreve o processo de publicação de uma versão do Pirate
Farm. O projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/):
`MAJOR` para mudanças incompatíveis de configuração ou fluxo, `MINOR` para
recursos novos e `PATCH` para correções.

## 1. Preparar a versão

- [ ] A árvore de trabalho está limpa (`git status`).
- [ ] `APP_VERSION` em `main.py` foi atualizada.
- [ ] O badge de versão em `README.md` foi atualizado.
- [ ] O `CHANGELOG.md` tem uma seção `[x.y.z] - AAAA-MM-DD` com as mudanças.
- [ ] `config.json` continua com valores portáveis e sem caminhos absolutos.
- [ ] `config.json` não contém URL real de webhook nem outra credencial.
- [ ] Nenhum log, captura ou dado pessoal entrou no commit.

## 2. Validar localmente

```powershell
.venv\Scripts\python.exe -m compileall -q main.py selftest.py piratebot tools
.venv\Scripts\python.exe tools\check_docs.py
.venv\Scripts\python.exe selftest.py
```

- [ ] O verificador de links não encontrou nenhum destino ausente.
- [ ] O autoteste terminou com **todos os N testes passaram**.
- [ ] Se houver Fortnite aberto, rode também `selftest.py --live`.
- [ ] Abra o app e confirme a versão no cabeçalho.
- [ ] Rode `Instalar.bat -NoShortcut` e confirme que as dependências carregam.
- [ ] Rode `Instalar.bat` e confira o atalho da área de trabalho e o ícone.
- [ ] Faça uma validação supervisionada seguindo
  [VALIDACAO.md](VALIDACAO.md), quando a mudança afetar o jogo.

## 3. Publicar

```powershell
git add -A
git commit -m "chore: prepara a versao x.y.z"
git push origin main
git tag -a vx.y.z -m "Pirate Farm vx.y.z"
git push origin vx.y.z
```

- [ ] O workflow **testes** passou no commit da tag.
- [ ] A tag `vx.y.z` aponta para o commit validado.
- [ ] A release foi criada no GitHub com as notas da versão.
- [ ] O texto da release cita os destaques e a versão mínima do Python.

## 4. Depois da release

- [ ] Baixe o código da tag em uma pasta limpa e rode o autoteste.
- [ ] Confira se o `README.md` e o `CHANGELOG.md` renderizam no GitHub.
- [ ] Verifique se os links de documentação e as imagens abrem.
- [ ] Abra issues para qualquer limitação conhecida que ficou fora da versão.

## Notas da release

Use o próprio `CHANGELOG.md` como base. Uma nota curta e útil responde:

1. O que mudou para quem usa o app?
2. O que precisa ser reconfigurado ou recalibrado?
3. Quais fluxos ainda exigem validação supervisionada?

Evite prometer detecção perfeita: templates dependem da interface do jogo e
podem mudar a cada atualização do Fortnite.

## Se algo falhar

- Cancele a release antes de divulgá-la se o workflow falhar.
- Corrija o problema em um commit novo; não reescreva uma tag já publicada.
- Mova a tag somente enquanto ela não tiver sido distribuída:

  ```powershell
  git tag -f vx.y.z
  git push --force origin vx.y.z
  ```

- Registre a causa e a correção no `CHANGELOG.md`.
