# ZapMCP

Dá ao Claude acesso de leitura ao WhatsApp Desktop do Mac: conversas, imagens, documentos e áudios
transcritos. O ZapMCP roda no próprio Mac, não se conecta aos servidores do WhatsApp e nunca altera a
pasta do WhatsApp.

## O que dá para pedir

- "O que ficou combinado no grupo da obra esta semana?"
- "Resuma os áudios que a Ana me mandou ontem."
- "Ache a mensagem em que falaram do orçamento de março e leia o PDF que veio junto."
- "Quem pediu para remarcar a reunião, e para quando?"

O Claude escolhe as ferramentas: lista as conversas, lê as mensagens de um período, busca por
palavras, abre imagens e documentos e transcreve áudios.

## Como funciona

```
WhatsApp Desktop ──cópia──▶ indexador ──▶ índice local ◀── servidor MCP ◀── Claude
```

1. O ZapMCP copia o banco de dados local do WhatsApp e monta um índice próprio, com busca.
2. Um servidor [MCP](https://modelcontextprotocol.io) oferece ao Claude ferramentas para consultar
   esse índice.
3. Os áudios são transcritos no Mac com [whisper.cpp](https://github.com/ggml-org/whisper.cpp).

Só leitura: o ZapMCP não envia mensagens.

## Requisitos

- Mac com Apple Silicon (M1 ou mais novo). Em Mac com Intel não foi testado: a biblioteca de
  transcrição não tem versão pronta para Intel.
- WhatsApp Desktop, o app nativo, com a conta conectada.
- [Claude Desktop](https://claude.ai/download).
- [uv](https://docs.astral.sh/uv/) e Node.js, pelo [Homebrew](https://brew.sh): `brew install uv node`.
  O Homebrew também instala as ferramentas de linha de comando da Apple, usadas para compilar o
  lançador.

## Instalação

### 1. Baixar e empacotar

```bash
git clone https://github.com/pedrosoutom/zapmcp.git
cd zapmcp
make
```

O `make` compila o lançador do ZapMCP (um programa pequeno, em `launcher/`) e gera
`dist/ZapMCP.mcpb`.

### 2. Instalar no Claude Desktop

Abra **Ajustes > Extensões** e arraste o `dist/ZapMCP.mcpb` para a página, ou dê dois cliques no
arquivo. Nos ajustes da extensão dá para ligar ou desligar a transcrição automática.

### 3. Liberar o acesso uma vez só

A pasta do WhatsApp é protegida pelo macOS. Sem permissão, o macOS pergunta de tempos em tempos se
pode liberar o acesso, e o "Permitir" vale só por um tempo. Para não ser mais perguntado, dê Acesso
Total ao Disco ao lançador do ZapMCP. Ele é quem inicia o servidor, então a permissão fica só com o
ZapMCP, e não com o `uv` ou com o Claude.

```bash
open -R ~/Library/Application\ Support/Claude/Claude\ Extensions/local.mcpb.pedro-souto.zapmcp/bin/zapmcp
```

O comando mostra o arquivo `zapmcp` no Finder. Arraste-o para a lista em **Ajustes do Sistema >
Privacidade e Segurança > Acesso Total ao Disco** e, se a chave aparecer desligada, ligue. Às vezes o
item não aparece na lista, mas a permissão vale mesmo assim.

## Quem libera é você

O Claude só lê uma conversa depois que você confirma no Mac. Funciona assim:

- Você pede algo de uma conversa ("resume os áudios da Ana de ontem"). O Claude acha a conversa pelo
  nome, sem confirmação, e aí aparece o pedido do sistema: **"Claude quer ler a conversa Ana (get_messages)"**,
  com Touch ID (ou a senha do Mac, se não houver sensor).
- Confirmou, aquela conversa fica liberada por 15 minutos (ajustável nos ajustes da extensão). Outras
  conversas continuam fechadas até você confirmar cada uma.
- Negou ou ignorou, o Claude recebe só "acesso fechado" e nada da conversa.
- Buscas sem conversa definida só olham as conversas que você já liberou. Listar todas as conversas
  também pede confirmação.
- Cada chamada fica registrada em `~/Library/Application Support/zapmcp/logs/acesso.log` (quem, qual
  ferramenta, qual conversa, liberado ou não), nunca o conteúdo.

O pedido é feito por um programa pequeno (`bin/zapmcp-unlock`) que o `make` compila; nenhum comando
de terminal abre o cadeado. O Claude Code e o Codex rodando no terminal passam pelo mesmo cadeado.

## Primeiro uso

Peça algo ao Claude sobre suas conversas. Na primeira vez:

- o Claude Desktop pede para você aprovar as ferramentas do ZapMCP;
- o `uv` baixa o Python e as dependências, então a primeira resposta demora mais;
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

Quando sai uma versão nova, o Claude avisa na conversa, no máximo uma vez por dia, com o link das
[novidades](https://github.com/pedrosoutom/zapmcp/releases). O aviso pode ser desligado nos ajustes
da extensão ("Avisar sobre versões novas").

## Privacidade

- O ZapMCP lê uma cópia do banco do WhatsApp e guarda o índice, as transcrições e o modelo em
  `~/Library/Application Support/zapmcp`. Essa pasta não é criptografada.
- Os áudios são transcritos no Mac e não saem dele.
- O que as ferramentas devolvem ao Claude (mensagens, transcrições, imagens, documentos) entra na
  conversa com o Claude, como qualquer texto que você cola nela.
- Uma vez por dia, o ZapMCP pergunta ao GitHub qual é a última versão. A consulta revela ao GitHub
  só o seu endereço IP e a versão instalada, e pode ser desligada nos ajustes da extensão.

## Desinstalar

1. Remova a extensão em **Ajustes > Extensões** no Claude Desktop.
2. Apague os dados do ZapMCP: `rm -rf ~/Library/Application\ Support/zapmcp`.
3. Se o `zapmcp` aparecer na lista de Acesso Total ao Disco, remova-o.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| O macOS continua perguntando se pode acessar "dados de outros apps" | Falta o Acesso Total ao Disco para o lançador, ou ele foi recompilado. Libere de novo. |
| As ferramentas não respondem na primeira vez | Espere a instalação das dependências e reinicie a extensão em **Ajustes > Extensões**. |
| Erro "não encontrei o uv" | Instale com `brew install uv`. |
| O Claude diz que o acesso está fechado e nenhum pedido de Touch ID apareceu | O `bin/zapmcp-unlock` não foi compilado: rode `make` na pasta do ZapMCP e reinstale a extensão. |
| O pedido de Touch ID aparece toda hora | Cada conversa é liberada por 15 minutos; aumente em **Minutos de liberação** nos ajustes da extensão. |

Para usar no Claude Code ou pelo terminal, ajustar a transcrição e conhecer os limites, veja o
[guia de uso](docs/USO.md).

## Avisos

- O ZapMCP lê um banco interno do WhatsApp, sem documentação. Uma atualização do app pode quebrar a
  leitura.
- Projeto independente, sem relação com o WhatsApp ou a Meta.

## Licença

[MIT](LICENSE)
