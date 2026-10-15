# ZapMCP

Dá ao Claude acesso de leitura ao WhatsApp Desktop do Mac: conversas, imagens, documentos e áudios
transcritos. Tudo roda no próprio Mac. Nada se conecta aos servidores do WhatsApp e a pasta do
WhatsApp nunca é alterada.

## Como funciona

```
WhatsApp Desktop ──cópia──▶ indexador ──▶ índice local ◀── servidor MCP ◀── Claude
```

1. O ZapMCP copia o banco de dados local do WhatsApp e monta um índice próprio, com busca.
2. Um servidor [MCP](https://modelcontextprotocol.io) oferece ao Claude ferramentas para listar
   conversas, ler mensagens de um período, buscar por palavras e abrir imagens e documentos.
3. Os áudios são transcritos no Mac com [whisper.cpp](https://github.com/ggml-org/whisper.cpp).
   Nenhum áudio sai do computador.

Só leitura: o ZapMCP não envia mensagens.

## Como usar

Precisa de macOS com o WhatsApp Desktop logado e do [uv](https://docs.astral.sh/uv/)
(`brew install uv`).

```bash
git clone https://github.com/pedrosoutom/zapmcp.git
cd zapmcp
npx @anthropic-ai/mcpb pack . dist/ZapMCP.mcpb
```

Depois, no Claude Desktop, abra **Ajustes > Extensões** e arraste o `dist/ZapMCP.mcpb` para a página.
Se o macOS negar o acesso à pasta do WhatsApp, libere o Acesso Total ao Disco em **Ajustes do Sistema
> Privacidade e Segurança**.

Para usar no Claude Code, comandos de terminal, ajustes da transcrição e limites conhecidos, veja o
[guia de uso](docs/USO.md).

## Avisos

- O ZapMCP lê um banco interno do WhatsApp, sem documentação; uma atualização do app pode quebrar a
  leitura.
- Projeto independente, sem relação com o WhatsApp ou a Meta.

## Licença

[MIT](LICENSE)
