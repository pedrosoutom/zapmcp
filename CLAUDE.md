# ZapMCP

Servidor MCP local (Python + FastMCP) que dá ao Claude acesso de leitura ao WhatsApp Desktop do Mac:
mensagens, imagens, documentos e áudios transcritos no próprio Mac. Distribuído como extensão `.mcpb`
do Claude Desktop. Repositório público, licença MIT: https://github.com/pedrosoutom/zapmcp. v0.3.3 concluída. **Direção: virar um app de desktop open-source** (fora da App
Store; o usuário baixa ou roda o código aberto). **Próximo passo: discutir stack e abordagem desse app.**
Melhorias registradas em [ROADMAP.md](ROADMAP.md).

**Antes de qualquer coisa, leia [docs/CONTEXTO.md](docs/CONTEXTO.md)**: estado atual, arquitetura, o
que sabemos do banco do WhatsApp, decisões, medições, pendências e o ponto de partida do app.

## Comandos

```bash
uv run pytest                                    # testes (banco falso em tests/)
uv run zapmcp sync | chats | export | transcribe | serve
npx @anthropic-ai/mcpb pack . dist/ZapMCP.mcpb   # empacota a extensão
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
- Depois de mudar o código: testes, reempacotar o `.mcpb` e pedir ao autor para reinstalar.
- Commits só quando o autor pedir. O repositório é público: nada de dados reais (nomes, números,
  mensagens, caminhos pessoais) em código, testes ou docs; nos testes, só dados fictícios.
