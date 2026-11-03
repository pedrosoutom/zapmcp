# ZapMCP — guia de uso

Referência completa: comandos, formas de conectar ao Claude, tools, transcrição de áudios, onde
ficam os dados e limites conhecidos. Para a visão geral, veja o [README](../README.md).

```
WhatsApp (área protegida) ──copia──▶ indexador ──grava──▶ index.db ◀──lê── servidor MCP ◀──tools── Claude
```

## Requisitos

- macOS com o WhatsApp Desktop (app nativo) logado
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)
- Para gerar a extensão: Node.js (`brew install node`), que roda o empacotador `mcpb`, e as
  ferramentas de linha de comando da Apple (`xcode-select --install`; já vêm com o Homebrew), que
  compilam o lançador
- Permissão para ler `~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared`. O macOS cobra o
  programa "responsável" por quem lê a pasta:
  - na extensão do Claude Desktop, é o lançador `bin/zapmcp` (ver [README](../README.md#3-liberar-o-acesso-uma-vez-só));
  - na configuração manual do Claude Desktop, deve ser o programa do `command` (não testado);
  - no terminal, e no Claude Code rodando no terminal, é o app de terminal.

  Sem Acesso Total ao Disco, o macOS pergunta "quer acessar dados de outros apps?", e o "Permitir"
  vale só por um tempo.

## Comandos

```bash
uv run zapmcp sync              # atualiza o índice (a primeira vez lê tudo; depois, só o novo)
uv run zapmcp sync --full       # reconstrói do zero
uv run zapmcp chats "projeto"   # lista conversas; aceita nome aproximado
uv run zapmcp export --chat "projeto x" --since 7d --out ./export/
uv run zapmcp transcribe        # áudios dos últimos 7 dias (--all: histórico; --archived: grupos arquivados)
uv run zapmcp serve             # servidor MCP (stdio)
```

Datas aceitas em `--since`/`--until` e nas tools: `7d`, `24h`, `2w`, `hoje`, `ontem`, `AAAA-MM-DD`,
`AAAA-MM-DD HH:MM`.

## Conectar ao Claude

**Claude Desktop, pela interface (extensão)**

```bash
make    # compila bin/zapmcp (só quando launcher/zapmcp.c muda) e gera dist/ZapMCP.mcpb
```

Depois, em Claude Desktop > Ajustes > Extensões, arraste o `dist/ZapMCP.mcpb` para a página e
clique em Instalar (ou dê dois cliques no arquivo). A extensão instalada é uma cópia: depois de mudar
o código, gere o `.mcpb` de novo e reinstale.

A extensão é do tipo `binary`: o Claude Desktop inicia o lançador `bin/zapmcp`, que inicia
`uv run … zapmcp serve` e fica esperando. O `uv` instala o Python e as dependências na primeira vez.
O lançador existe por causa da permissão: no tipo `uv`, o Claude Desktop inicia o `uv` direto e é o
`uv` que precisa do Acesso Total ao Disco, valendo para qualquer coisa que rode por ele.

**Claude Code**

```bash
claude mcp add --scope user ZapMCP -- /opt/homebrew/bin/uv --directory /caminho/para/zapmcp run zapmcp serve
```

**Claude Desktop, editando a configuração**: em `~/Library/Application Support/Claude/claude_desktop_config.json`, dentro de
`"mcpServers"`:

```json
"ZapMCP": {
  "command": "/opt/homebrew/bin/uv",
  "args": ["--directory", "/caminho/para/zapmcp", "run", "zapmcp", "serve"]
}
```

O caminho absoluto do `uv` é necessário porque o Claude Desktop não herda o `PATH` do terminal.

## Cadeado: cada conversa é liberada por você

O servidor nasce trancado. Regras:

| Chamada | O que acontece |
|---|---|
| `list_chats` com nome (3+ letras) | Devolve id, nome, tipo e contagens das conversas parecidas, sem pedir nada. |
| `list_chats` sem nome, ou com menos de 3 letras | Pede confirmação no Mac para listar todas. Libera só a listagem. |
| `get_messages`, `search` com `chat` | Pede confirmação para **aquela** conversa, uma vez; depois, liberada por `ZAPMCP_UNLOCK_MINUTES` (padrão 15). |
| `search` sem `chat` | Só nas conversas já liberadas nesta sessão; sem nenhuma, pede ao Claude que pergunte qual. |
| `view_images`, `read_document`, `transcribe_audio` | A conversa de cada mensagem precisa estar liberada; se não está, pede. |

- O pedido é o diálogo do sistema (`LAPolicy.deviceOwnerAuthentication`): Touch ID, ou a senha do Mac.
  É mostrado por `bin/ZapMCP.app` (`unlock/zapmcp-unlock.swift`, compilado pelo `make`). Sem o
  binário, o servidor continua fechado e avisa para rodar `make`.
- Negou ou não respondeu: vale para quem já esperava e por 5 segundos; dentro de uma mesma chamada, cada conversa é pedida uma vez (vários anexos da mesma conversa = um pedido). A janela conta em relógio de parede: dormir o Mac não a estica.
- O estado fica só na memória de cada processo servidor: Claude Code, Codex e Claude Desktop pedem
  cada um a sua liberação. Nada em disco; nenhum comando de terminal abre o cadeado.
- `ZAPMCP_UNLOCK_MINUTES=0` desliga o cadeado (tudo liberado, como antes da v0.4).
  `ZAPMCP_UNLOCK_WAIT_SECONDS` (padrão 60) é quanto a tool espera a sua resposta.
  `ZAPMCP_UNLOCK_BIN` aponta para outro binário de liberação (testes).
- A CLI (`zapmcp sync|chats|export|transcribe`) não passa pelo cadeado: é você no terminal.
- Log de acesso em `~/Library/Application Support/zapmcp/logs/acesso.log`, uma linha por chamada:
  `2026-11-03 19:40:01 | Claude Code | get_messages | chat=Ana since=ontem until=None | pedido, liberado`.
  Resultados: `livre` (list_chats por nome), `liberado`, `trancado`, `liberado 2, trancado 1` (vários ids), com `pedido, ` na frente quando o diálogo abriu.
  Nunca contém mensagem nem transcrição.

## Tools

| Tool | Recebe | Devolve |
|---|---|---|
| `list_chats` | nome aproximado, ativa desde, limite | id, nome, grupo ou individual, última mensagem, total |
| `get_messages` | conversa (id ou nome), `since`, `until`, limite | uma linha por mensagem; acima do limite, as mais recentes |
| `search` | palavras (FTS5, ignora acentos), conversa e período opcionais | trechos com as mensagens ao redor |
| `view_images` | até 5 números de imagem | as imagens (lado maior ≤ 1.568 px), com conversa, autor, data e legenda |
| `read_document` | número do documento, parte | o texto em partes de ~15 mil caracteres; páginas escaneadas de PDF como imagem |
| `transcribe_audio` | até 10 números de áudio | a transcrição na hora (espera até ~1,5 min), furando a fila |

Formato das linhas: `[2026-09-25 08:41] Ana Lima: texto`. `Você` é o dono do WhatsApp; `~ Nome` é
o nome de perfil de quem não está na agenda. Menções (`@`) seguem a mesma regra: `@Tatá` (agenda),
`@~Maria` (nome de perfil) ou o número, quando não há nome conhecido.

Anexos que podem ser abertos aparecem com número: `[imagem #184223] legenda`,
`[documento #184230 · 1,2 MB] proposta.pdf`. Sem arquivo no Mac, aparecem como
`[imagem · sem arquivo neste Mac]`. Os arquivos são lidos direto da pasta do WhatsApp, só para
leitura e sem cópia.

Documentos suportados: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), HTML, texto (.txt,
.md, .csv, .json…) e ZIP (só a lista de arquivos). Acima de 60 MB, o documento não é aberto.

## Áudios

Os áudios são transcritos **no próprio Mac**, com whisper.cpp e o modelo large-v3-turbo comprimido
(q5, 0,6 GB), que é baixado uma vez do Hugging Face e conferido pelo hash oficial. Nenhum áudio sai
do Mac.

- Por padrão, a transcrição automática cobre **os áudios dos últimos 7 dias** e cada áudio novo que
  chegar (`ZAPMCP_TRANSCRIBE_DAYS` muda a janela), **fora de grupos arquivados**
  (`ZAPMCP_TRANSCRIBE_ARCHIVED=1` inclui). Os demais são transcritos quando o Claude pede, com
  `transcribe_audio`, ou de uma vez com `zapmcp transcribe --all` / `--archived`. Com um histórico
  grande, isso pode levar horas com a GPU ocupada; por isso fica como escolha do usuário.
- Enquanto o servidor MCP está aberto, um processo separado cuida da fila, dos áudios mais novos para
  os mais antigos. Ele sai sozinho quando o servidor fecha, e só um roda por vez, mesmo com o ZapMCP
  aberto no Claude Desktop e no Claude Code.
- Com o Mac na bateria, só os áudios pedidos pelo Claude são transcritos
  (`ZAPMCP_TRANSCRIBE_ON_BATTERY=1` muda isso). `ZAPMCP_TRANSCRIBE=0` desliga a transcrição.
  No Claude Desktop, essas opções aparecem nos ajustes da extensão.
- A transcrição entra na linha da mensagem (`[áudio 0:37] texto`) e na busca. Áudio sem transcrição
  aparece como `[áudio #123 0:37 · ainda não transcrito]`. A busca não encontra o que foi dito em
  áudios antigos ainda não transcritos.
- O cache é pelo hash do arquivo: um áudio encaminhado em várias conversas é transcrito uma vez, e
  as transcrições sobrevivem quando o índice é refeito.
- Limpeza automática das falhas conhecidas do Whisper: frase repetida em sequência, texto em outro
  alfabeto e as "legendas" que ele inventa em áudio silencioso.
- Velocidade no M1: cerca de 8× o tempo real (1 minuto de áudio em ~8 s). Enquanto transcreve, a GPU
  fica perto de 100%; processador (~6% de um núcleo) e memória (~300 MB) ficam baixos.

Na v1, o próprio servidor atualiza o índice quando ele tem mais de 5 minutos
(`ZAPMCP_AUTO_SYNC_SECONDS`, 0 desliga).

## Aviso de versão nova

Ao iniciar, o servidor consulta a última release no GitHub, no máximo uma vez por dia, em segundo
plano. Se ela for mais nova que a instalada, a primeira resposta do dia de `list_chats`,
`get_messages` ou `search` começa com um aviso para o usuário. Do GitHub só se usa o número da versão;
o texto do aviso é fixo. `ZAPMCP_UPDATE_CHECK=0` desliga (no Claude Desktop, "Avisar sobre versões
novas" nos ajustes da extensão).

## Onde ficam os dados

- `~/Library/Application Support/zapmcp/index.db`: o índice (mensagens + FTS5)
- `~/Library/Application Support/zapmcp/snapshot/`: cópia de trabalho, apagada ao fim de cada sync
- `~/Library/Application Support/zapmcp/transcripts.db`: cache das transcrições, fila de pedidos e falhas
- `~/Library/Application Support/zapmcp/models/`: o modelo de transcrição
- `~/Library/Application Support/zapmcp/logs/transcricao.log`: log do processo de transcrição
- `~/Library/Application Support/zapmcp/logs/acesso.log`: o que o Claude pediu e se foi liberado
- `~/Library/Application Support/zapmcp/atualizacao.json`: última versão vista no GitHub e quando o
  aviso foi mostrado

## Limites conhecidos da v1

- A transcrição erra nomes próprios e termos técnicos (por exemplo, "Claude" vira "Cloud").
- A decodificação de áudio usa o `afconvert` do macOS; no Windows vai precisar de outro caminho.
- Vídeos e figurinhas aparecem só como marcador. Mídias que o WhatsApp Desktop nunca baixou não
  podem ser abertas.
- Parte dos códigos de `ZMESSAGETYPE` ainda não foi mapeada e aparece como `[tipo N]` (cerca de 4%
  das mensagens). Eventos de sistema (tipo 6) ficam fora das respostas.
- Edições e mensagens apagadas só são revistas nas últimas 48 h; para o histórico todo, `sync --full`.
- O schema é interno do WhatsApp e pode mudar numa atualização do app.

## Testes

```bash
uv run pytest
```
