# ZapMCP

Servidor MCP local (Python + FastMCP) que dá ao Claude acesso de leitura ao WhatsApp Desktop do Mac:
mensagens, imagens, documentos e áudios transcritos no próprio Mac. Distribuído como extensão `.mcpb`
do Claude Desktop; funciona com outros clientes MCP (stdio), como o Codex. Repositório público, licença MIT: https://github.com/pedrosoutom/zapmcp. v0.3.7 concluída. **Direção: virar um app de desktop open-source** (fora da App
Store; o usuário baixa ou roda o código aberto). **Próximo passo: discutir stack e abordagem desse app.**
Melhorias registradas em [ROADMAP.md](ROADMAP.md).

**Antes de qualquer coisa, leia [docs/CONTEXTO.md](docs/CONTEXTO.md)**: estado atual, arquitetura, o
que sabemos do banco do WhatsApp, decisões, medições, pendências e o ponto de partida do app.

## Comandos

```bash
uv run pytest                                    # testes (banco falso em tests/)
uv run zapmcp sync | chats | export | transcribe | serve
make                                             # compila o lançador (se mudou) e empacota dist/ZapMCP.mcpb
make acesso                                      # abre o Acesso Total ao Disco e mostra o lançador no Finder
```

## Regras

- Conversa em português do Brasil, com explicações simples e honestas; medir antes de afirmar.
- Nunca escrever na pasta do WhatsApp (`~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared`);
  sempre ler uma cópia.
- Não ler nem imprimir conteúdo de mensagens, nomes de contatos ou transcrições sem autorização
  explícita do autor; verificar dados reais com contagens e saídas mascaradas.
- O servidor MCP usa FastMCP (decisão do autor).
- Mudou a montagem das linhas? Subir `NORMALIZER_VERSION` em `src/zapmcp/whatsapp.py`.
- Nada que o trabalhador de transcrição imprima pode chegar ao stdout do servidor.
- A extensão roda pelo lançador `bin/zapmcp` (`launcher/zapmcp.c`), que fica com o Acesso Total ao
  Disco no lugar do `uv`. Recompilá-lo muda a assinatura (ad hoc) e derruba a permissão: só mexer
  nele com motivo e avisar o autor para liberar de novo.
- Depois de mudar o código: testes, reempacotar o `.mcpb` e pedir ao autor para reinstalar. Cada
  pacote novo precisa de versão nova (`manifest.json`, `pyproject.toml` e `uv lock`), senão o Claude
  Desktop não atualiza.
- Lançar uma versão: commit e push na `main` (quando o autor pedir) e `gh release create vX.Y.Z` com as
  novidades. O aviso de versão nova dos usuários lê a última release.
- Commits só quando o autor pedir. O repositório é público: nada de dados reais (nomes, números,
  mensagens, caminhos pessoais) em código, testes ou docs; nos testes, só dados fictícios.
