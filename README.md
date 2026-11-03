# ZapMCP

Dá ao Claude, ao Codex e a outros assistentes compatíveis com MCP acesso de leitura ao WhatsApp
Desktop do Mac: conversas, imagens, documentos e áudios transcritos. O ZapMCP roda no próprio Mac, não
se conecta aos servidores do WhatsApp e nunca altera a pasta do WhatsApp.

A instalação abaixo é a do Claude Desktop, o caminho mais completo e testado. Para outros
assistentes, veja [Outros assistentes](#outros-assistentes-codex-cursor-e-outros).

## O que dá para pedir

- "O que ficou combinado no grupo da obra esta semana?"
- "Resuma os áudios que a Ana me mandou ontem."
- "Ache a mensagem em que falaram do orçamento de março e leia o PDF que veio junto."
- "Quem pediu para remarcar a reunião, e para quando?"

O assistente escolhe as ferramentas: lista as conversas, lê as mensagens de um período, busca por
palavras, abre imagens e documentos e transcreve áudios.

## Como funciona

```
WhatsApp Desktop ──cópia──▶ indexador ──▶ índice local ◀── servidor MCP ◀── Claude, Codex…
```

1. O ZapMCP copia o banco de dados local do WhatsApp e monta um índice próprio, com busca.
2. Um servidor [MCP](https://modelcontextprotocol.io) oferece ao assistente ferramentas para
   consultar esse índice.
3. Os áudios são transcritos no Mac com [whisper.cpp](https://github.com/ggml-org/whisper.cpp).

Só leitura: o ZapMCP não envia mensagens.

## Requisitos

- Mac com Apple Silicon (M1 ou mais novo). Em Mac com Intel não foi testado: a biblioteca de
  transcrição não tem versão pronta para Intel.
- WhatsApp Desktop, o app nativo, com a conta conectada.
- [Claude Desktop](https://claude.ai/download), ou outro assistente com suporte a MCP.
- [uv](https://docs.astral.sh/uv/) e Node.js, pelo [Homebrew](https://brew.sh): `brew install uv node`.
  O Homebrew também instala as ferramentas de linha de comando da Apple, usadas para compilar o
  lançador.

## Instalação

São três passos. O terceiro, liberar o acesso, só é feito na primeira instalação, e sem ele o macOS
fica pedindo permissão.

### 1. Baixar e empacotar

```bash
git clone https://github.com/pedrosoutom/zapmcp.git
cd zapmcp
make
```

O `make` compila o lançador do ZapMCP (um programa pequeno, em `launcher/`), gera
`dist/ZapMCP.mcpb` e mostra os próximos passos.

### 2. Instalar no Claude Desktop

```bash
open dist/ZapMCP.mcpb
```

O Claude Desktop abre a tela da extensão: clique em Instalar. Outro jeito é arrastar o arquivo para
**Ajustes > Extensões**. Nos ajustes da extensão dá para ligar ou desligar a transcrição automática.

### 3. Liberar o acesso uma vez só

A pasta do WhatsApp é protegida pelo macOS. Sem permissão, o macOS pergunta de tempos em tempos se
o `zapmcp` pode "acessar dados de outros apps", e o "Permitir" vale só por um tempo. Para não ser
mais perguntado, dê Acesso Total ao Disco ao lançador do ZapMCP, o arquivo `zapmcp` que veio na
extensão. Ele é quem inicia o servidor, então a permissão fica só com o ZapMCP, e não com o `uv` ou
com o Claude.

```bash
make acesso
```

O comando abre o painel **Ajustes do Sistema > Privacidade e Segurança > Acesso Total ao Disco** e
uma janela do Finder com o arquivo `zapmcp` selecionado. Arraste o arquivo para a lista, confira se a
chave ficou ligada e confirme com sua senha ou o Touch ID. Às vezes o item não aparece na lista, mas
a permissão vale mesmo assim.

Sem o `make`: no painel, clique em **+**, aperte Cmd+Shift+G, cole o caminho abaixo e ligue a chave.

```
~/Library/Application Support/Claude/Claude Extensions/local.mcpb.pedro-souto.zapmcp/bin/zapmcp
```

Se você pular este passo, o ZapMCP percebe e o Claude avisa na conversa como liberar. Deu certo
quando o macOS para de perguntar e o aviso não aparece mais.

## Primeiro uso

Peça algo ao Claude sobre suas conversas. Na primeira vez:

- o Claude Desktop pede para você aprovar as ferramentas do ZapMCP;
- o `uv` baixa o Python e as dependências, então a primeira resposta demora mais;
- se o acesso ainda não foi liberado, o macOS pergunta se o `zapmcp` pode acessar dados de outros
  apps (clique em Permitir) e o Claude explica como liberar de vez;
- o ZapMCP monta o índice (cerca de 10 segundos num M1) e passa a atualizá-lo a cada 5 minutos;
- se a transcrição estiver ligada, o modelo de transcrição (0,6 GB) é baixado uma vez do Hugging
  Face. Depois, os áudios dos últimos 7 dias e cada áudio novo são transcritos em segundo plano,
  enquanto o Claude está aberto. Grupos arquivados ficam de fora e, na bateria, só são transcritos os
  áudios que o Claude pede.

## Atualizar

```bash
git pull
make
```

Instale o novo `dist/ZapMCP.mcpb` no Claude Desktop e clique em atualizar. A permissão continua
valendo, a menos que o lançador tenha mudado (`launcher/zapmcp.c`). Nesse caso, libere de novo.

Quando sai uma versão nova, o assistente avisa na conversa, no máximo uma vez por dia, com o link das
[novidades](https://github.com/pedrosoutom/zapmcp/releases). O aviso pode ser desligado nos ajustes
da extensão ("Avisar sobre versões novas").

## Outros assistentes (Codex, Cursor e outros)

O ZapMCP é um servidor MCP padrão, que roda no Mac e conversa pela entrada e saída do processo
(stdio). Qualquer assistente que aceite servidores MCP locais pode usá-lo com este comando:

```bash
/opt/homebrew/bin/uv --directory /caminho/para/zapmcp run zapmcp serve
```

Ele foi testado com um cliente MCP genérico; com o Codex, ainda não. No Codex, a configuração fica
em `~/.codex/config.toml`, que vale para o Codex no terminal, na extensão do editor e no app:

```toml
[mcp_servers.zapmcp]
command = "/opt/homebrew/bin/uv"
args = ["--directory", "/caminho/para/zapmcp", "run", "zapmcp", "serve"]
startup_timeout_sec = 60
tool_timeout_sec = 120
```

Os tempos maiores que o padrão evitam que o Codex desista: na primeira vez, o servidor instala as
dependências e monta o índice antes de responder, e `transcribe_audio` espera até 90 segundos.

O que muda fora do Claude Desktop:

- O macOS cobra o acesso do app que roda o assistente: o app de terminal, para quem usa o Codex no
  terminal, ou o próprio app, nos assistentes de desktop. O Acesso Total ao Disco vai para esse app
  e vale para tudo o que ele rodar. O lançador só faz diferença no Claude Desktop.
- Os ajustes da extensão viram variáveis de ambiente, como `ZAPMCP_TRANSCRIBE=0`. A lista está no
  [guia de uso](docs/USO.md).
- Nem todo assistente mostra as imagens que o `view_images` devolve. Não testamos fora do Claude.
- Para atualizar, basta `git pull` na pasta do ZapMCP e reiniciar o assistente.

## Privacidade

- O ZapMCP lê uma cópia do banco do WhatsApp e guarda o índice, as transcrições e o modelo em
  `~/Library/Application Support/zapmcp`. Essa pasta não é criptografada.
- Os áudios são transcritos no Mac e não saem dele.
- O que as ferramentas devolvem ao assistente (mensagens, transcrições, imagens, documentos) entra
  na conversa com ele, como qualquer texto que você cola nela.
- Uma vez por dia, o ZapMCP pergunta ao GitHub qual é a última versão. A consulta revela ao GitHub
  só o seu endereço IP e a versão instalada, e pode ser desligada nos ajustes da extensão.

## Desinstalar

1. Remova a extensão em **Ajustes > Extensões** no Claude Desktop.
2. Apague os dados do ZapMCP: `rm -rf ~/Library/Application\ Support/zapmcp`.
3. Se o `zapmcp` aparecer na lista de Acesso Total ao Disco, remova-o.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| O macOS continua perguntando se pode acessar "dados de outros apps" | Falta o Acesso Total ao Disco para o lançador, ou ele foi recompilado. Rode `make acesso` (passo 3). |
| As ferramentas não respondem na primeira vez | Espere a instalação das dependências e reinicie a extensão em **Ajustes > Extensões**. |
| Erro "não encontrei o uv" | Instale com `brew install uv`. |

Para usar no Claude Code ou pelo terminal, ajustar a transcrição e conhecer os limites, veja o
[guia de uso](docs/USO.md).

## Avisos

- O ZapMCP lê um banco interno do WhatsApp, sem documentação. Uma atualização do app pode quebrar a
  leitura.
- Projeto independente, sem relação com o WhatsApp ou a Meta.

## Licença

[MIT](LICENSE)
