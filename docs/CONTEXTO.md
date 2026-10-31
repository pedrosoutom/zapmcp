# ZapMCP — contexto do projeto

Documento de passagem de bastão entre sessões. Atualizado em 2026-10-31, versão 0.3.5.
Próximo passo combinado: **discutir stack e abordagem do app de desktop** (seção 9).

## 1. O que é

Servidor MCP local que dá ao Claude acesso de leitura às conversas do WhatsApp Desktop do Mac:
mensagens, imagens, documentos e áudios transcritos. Lê uma **cópia** do banco local do app; não usa
API não oficial, não fala com os servidores do WhatsApp e nunca escreve na pasta do WhatsApp.

Hoje é só MCP (extensão `.mcpb` do Claude Desktop), rodando no Mac do autor. A v1 está concluída e em
uso; o autor ainda vai testar a leitura de documentos na prática.

## 2. Estado atual (v0.3.5)

| Tool | O que faz |
|---|---|
| `list_chats` | lista conversas; nome aproximado; marca "grupo arquivado" |
| `get_messages` | mensagens de uma conversa num período, uma por linha |
| `search` | busca por palavras (SQLite FTS5, ignora acentos), com mensagens ao redor |
| `view_images` | até 5 imagens por número, reduzidas a 1.568 px |
| `read_document` | texto de PDF, Word, Excel, PowerPoint, HTML, texto e lista de ZIP, em partes de ~15 mil caracteres; página escaneada vai como imagem |
| `transcribe_audio` | transcreve na hora áudios ainda não transcritos (fura a fila) |

Formato das linhas: `[2026-09-25 08:41] Ana Lima: texto`. `Você` = dono do WhatsApp; `~ Nome` = nome
de perfil (não está na agenda); menções como `@Nome` (agenda) ou `@~Nome` (perfil). Anexos:
`[imagem #123] legenda`, `[documento #456 · 1,2 MB] nome.pdf`, `[áudio 0:37] transcrição`,
`[áudio #789 1:12 · ainda não transcrito]`, `[imagem · sem arquivo neste Mac]`, `[tipo 59]`.

Transcrição de áudio, no próprio Mac, com whisper.cpp (`pywhispercpp`) e o modelo
large-v3-turbo **q5_0** (574 MB, baixado uma vez do Hugging Face, conferido por SHA-256):
- automática: **últimos 7 dias + cada áudio novo, fora de grupos arquivados**;
- o resto só a pedido (`transcribe_audio`) ou `zapmcp transcribe --all` / `--archived`;
- roda num processo separado do servidor, só um por vez (trava de arquivo), sai junto com o servidor
  (pipe no stdin), na bateria só atende pedidos;
- cache pelo hash do arquivo em `transcripts.db`, que sobrevive à reconstrução do índice;
- limpeza de alucinações: frase repetida em sequência, texto em outro alfabeto, "legendas" em silêncio.

Ajustes na extensão (manifest `user_config`): transcrever áudios, transcrever grupos arquivados,
transcrever também na bateria.

Permissão (v0.3.5): a extensão é do tipo `binary` e o Claude Desktop inicia o **lançador
`bin/zapmcp`**, que inicia o `uv` e fica esperando. O Acesso Total ao Disco é dado uma vez ao
lançador, e o macOS para de perguntar. Detalhes e medições na seção 7.

## 3. Como rodar

```bash
uv sync                          # dependências (Python 3.12)
uv run pytest                    # 15 testes, sobre um banco falso com o formato do WhatsApp
uv run zapmcp sync [--full]      # atualiza o índice
uv run zapmcp chats "nome"
uv run zapmcp export --chat "nome" --since 7d --out ./export/
uv run zapmcp transcribe [--all] [--archived] [--limit N]
uv run zapmcp serve              # servidor MCP (stdio)
make                             # compila o lançador (se mudou) e gera dist/ZapMCP.mcpb
```

Instalação no Claude Desktop: **Ajustes > Extensões**, arrastar o `.mcpb` (ou dois cliques). Não é
pela tela "Add custom connector", que é para servidores remotos por URL. A extensão instalada é uma
cópia: após mudar código, reempacotar e reinstalar. A aba Code do app usa a mesma extensão. Mesmo
número de versão não é tratado como atualização: subir a versão no `manifest.json` (e no
`pyproject.toml`) a cada pacote novo.

## 4. Arquitetura e código

```
Claude Desktop ──inicia──▶ lançador bin/zapmcp (responsável perante o macOS) ──▶ uv ──▶ servidor MCP
WhatsApp (Group Container, protegido) ──cópia──▶ indexador ──▶ index.db ◀── servidor MCP ◀── Claude
                                   └─ mídia lida direto (só leitura) ──▶ tools de anexo
                     trabalhador de transcrição (processo separado) ──▶ transcripts.db + index.db
```

| Módulo | Papel |
|---|---|
| `config.py` | caminhos e variáveis de ambiente |
| `snapshot.py` | copia `ChatStorage.sqlite` e `ContactsV2.sqlite` com `-wal`/`-shm`, confere se o WhatsApp não gravou durante a cópia, apaga no fim |
| `whatsapp.py` | **todo o conhecimento do schema do WhatsApp** e a normalização das linhas; `NORMALIZER_VERSION` |
| `store.py` | índice próprio (SQLite + FTS5): schema, escrita e consultas |
| `sync.py` | indexador: novas mensagens por `Z_PK` + revisão das últimas 48 h; refaz tudo quando `NORMALIZER_VERSION` muda |
| `format.py` | como as mensagens e marcadores aparecem |
| `media.py` | imagens e documentos (Pillow, pypdfium2, python-docx, openpyxl, python-pptx) |
| `transcribe.py` | modelo, decodificação (`afconvert`), whisper.cpp e limpeza |
| `transcripts.py` | cache de transcrições, fila de pedidos, falhas recentes |
| `worker.py` | fila de transcrição em processo próprio |
| `server.py` | servidor FastMCP e as tools |
| `launcher/zapmcp.c` | lançador em C: acha o `uv`, inicia-o como filho, repassa sinais e o código de saída; não escreve no stdout |
| `Makefile` | compila o lançador (só quando o fonte muda; assinatura ad hoc) e empacota o `.mcpb` |
| `cli.py`, `dates.py` | linha de comando; datas como `7d`, `hoje`, `AAAA-MM-DD` |
| `manifest.json`, `.mcpbignore` | extensão MCPB, tipo `binary`: o Claude Desktop roda o lançador, e o `uv` instala Python e dependências |

Dados em `~/Library/Application Support/zapmcp/`: `index.db`, `transcripts.db`,
`models/`, `logs/transcricao.log`, `transcricao.lock`, `snapshot/` (temporária).

Regras de implementação:
- Mudou a forma de montar as linhas (autores, menções, textos)? **Subir `NORMALIZER_VERSION`** em
  `whatsapp.py`; o índice se refaz sozinho (~10 s), sem perder transcrições.
- O trabalhador de transcrição **nunca** pode herdar o stdout do servidor (quebraria o protocolo MCP).
- Uma lista só de strings num `ToolResult` o FastMCP transforma num JSON; usar `TextContent`
  (ver `_blocks` em `server.py`).
- FastMCP 4.x: anotações de tool com nomes do SDK v2 (`read_only_hint`).

## 5. O que sabemos do banco do WhatsApp Desktop (Mac)

Base: `~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/`. Banco Core Data (`Z_PK`),
sem documentação: pode mudar numa atualização do app.

- **`ChatStorage.sqlite` + `-wal`**: as mensagens mais recentes ficam no `-wal` até o checkpoint;
  copiar juntos. Abrir o original, mesmo só leitura, entra no controle de travas do WhatsApp.
- **`ZWACHATSESSION`**: `ZCONTACTJID` (`@g.us` grupo, `@s.whatsapp.net`, `@lid`, `status@broadcast`),
  `ZPARTNERNAME` (nome da conversa), `ZARCHIVED`, `ZREMOVED`, `ZSESSIONTYPE`: 0 individual,
  1 grupo, 2 status, 3 lista de transmissão, 4 grupo de comunidade. Indexamos 0, 1 e 4.
- **`ZWAMESSAGE`**: `ZMESSAGEDATE` em segundos desde 2001 (somar `978307200`), `ZISFROMME`,
  `ZTEXT`, `ZGROUPMEMBER`, `ZMESSAGETYPE`. **`ZPUSHNAME` é um dado codificado (base64 de protobuf),
  não o nome: não usar.**
- **Tipos** (`ZMESSAGETYPE`): 0 texto, 1 imagem, 2 vídeo, 3 áudio, 6 sistema (hipótese forte: nunca
  enviado pelo dono), 7 link, 8 documento, 15 figurinha. Prováveis: 4 contato, 14 mensagem apagada.
  Não mapeados: 10, 11, 12, 42, 59, 66 e raros (~4% das mensagens). Mapear exige ler exemplos, só
  com autorização do autor.
- **`ZWAMEDIAITEM`**: `ZMESSAGE` (1:1 com a mensagem), `ZMEDIALOCALPATH` (relativo a `Message/`),
  `ZTITLE` (legenda de imagem e vídeo), `ZMOVIEDURATION` (segundos). Colunas como `ZVCARDSTRING` e
  `ZLATITUDE` vêm preenchidas em imagens e não significam o que o nome diz.
- **`ZWAGROUPMEMBER`**: `ZMEMBERJID` (99,9% `@lid`), `ZCONTACTNAME` sempre vazio, `ZFIRSTNAME`
  às vezes vem codificado (`+` seguido de base64).
- **`ZWAPROFILEPUSHNAME`**: jid → nome de perfil, limpo. Fonte do `~ Nome`.
- **`ContactsV2.sqlite` / `ZWAADDRESSBOOKCONTACT`**: a cópia da agenda que o WhatsApp sincroniza do
  celular (só contatos com WhatsApp): `ZLID`, `ZWHATSAPPID`, `ZFULLNAME`.
- **`LID.sqlite`**: tabelas vazias no Mac (conferido); não ajuda a resolver `@lid`.
- **Menções**: no texto, `@` + os dígitos do jid (`@lid` ou telefone); resolvidas como os autores.
- **Autor em grupo**: agenda (por `@lid` ou telefone) → nome de perfil → `ZFIRSTNAME` limpo → número.
- **Mídia**: nem tudo foi baixado para o Mac (as mídias antigas, principalmente).
  Áudio é Ogg Opus; o `afconvert` do macOS decodifica, sem ffmpeg.
- **Windows é diferente**: desde 2025-12-09 o app de Windows é o WhatsApp Web dentro de um WebView2;
  os bancos em `LocalState` são criptografados (DPAPI-NG + identificador da máquina) e só ferramentas
  forenses de engenharia reversa os abrem. O caminho seguro a validar no Windows é importar as
  exportações oficiais de conversa (`.zip` do "Exportar conversa").

## 6. Decisões tomadas

- Local, sem API não oficial, sem escrever na pasta do WhatsApp; MCP é o produto, export `.md` é
  secundário.
- Python + uv; servidor com **FastMCP** (escolha explícita do autor).
- Por enquanto **só MCP**, distribuído como extensão `.mcpb`; o app de desktop vem depois.
- **Mac primeiro, Windows depois**; o autor quer o app de Mac em **Swift** (Windows após validar).
- Envio de mensagens **fora**. Se voltar: só rascunho confirmado pelo usuário (link oficial
  `whatsapp://send`), por risco de prompt injection vindo de mensagens de terceiros.
- Imagens e documentos **sob demanda** (número no marcador); vídeo e figurinha só marcador.
- Transcrição: whisper.cpp + **q5** (escolha do autor, pelo tamanho, após os testes da seção 7);
  escopo automático de 7 dias, fora de grupos arquivados.
- Nome **ZapMCP é provisório**. O definitivo deve terminar em "MCP" e mirar público técnico; evitar
  "Zap"/"Whats" (as diretrizes de marca da Meta proíbem variações, citando "ZapZap"). Candidatos
  livres (GitHub, PyPI, npm, .com, .dev) em 2026-09-26: ScrollbackMCP (recomendado), PapoMCP,
  ConvoMCP, GroupchatMCP, ChatlogMCP. Descartados: ThreadMCP (Threads da Meta), InboxMCP, RecapMCP.
- Projeto **open-source** (licença MIT), público em https://github.com/pedrosoutom/zapmcp desde
  2026-10-15. Apple Developer Program só quando houver app assinado para distribuir.
- **Direção do produto (2026-10-13):** transformar o código atual num **aplicativo de desktop
  open-source**. Não vai para a App Store nem para loja nenhuma: o usuário baixa ou roda o código
  aberto que disponibilizarmos.
- **Lançador próprio na extensão (2026-10-31):** em vez de dar Acesso Total ao Disco ao `uv` (que
  valeria para qualquer coisa rodada por ele), a extensão passou a ser do tipo `binary` e o Claude
  Desktop inicia `bin/zapmcp`, que recebe a permissão. Solução para o modo só-MCP; no app, quem
  recebe a permissão é o app assinado.
- **Distribuição do app (pesquisa de 2026-10-31):** os apps open source de Mac que pedem permissões
  (AltTab, Stats, Ice, Maccy, OpenScreen) assinam com Developer ID e notarizam no CI, a cada versão,
  e distribuem por DMG nas Releases e tap próprio do Homebrew. Sem isso: "Abrir Mesmo Assim" nos
  Ajustes (o Control-clique deixou de funcionar no macOS 15), permissão perdida a cada versão e,
  desde 2026-09-01, fora dos casks oficiais do Homebrew. Para desenvolver, certificado gratuito
  (Apple Development ou autoassinado). Atualização automática (Sparkle) é opcional; meio-termo
  considerado: o app só avisar que há versão nova, com link para a página de download.

## 7. Medições (Mac do autor, M1, 8 GB, set/2026; permissões em out/2026, macOS 26.2)

- Índice completo em ~10 s; atualização incremental ~1 s.
- Tools respondem em 2 a 300 ms (imagens e documentos grandes no topo da faixa).
- Transcrição q5: ~8× o tempo real. Durante a transcrição: GPU ~96%, CPU ~6% de um núcleo,
  memória ~300 MB, sem alerta térmico num teste de 1 min.
- Comparativo (30 áudios, sem gabarito; métricas de diferença + leitura com autorização):
  - whisper.cpp original (f16, 1,6 GB): sem alucinações; referência.
  - whisper.cpp q8 (0,9 GB): 2,1% de palavras diferentes do original; 1 frase repetida em 20.
  - whisper.cpp q5 (0,6 GB): 3,6%; 1 frase repetida em 30; diferenças quase todas de estilo.
  - mlx-whisper: 2 de 10 áudios terminaram em lixo; instalação pesada (PyTorch). Descartado.
  - Erro comum a todos: "Claude" vira "Cloud" (termos técnicos e nomes próprios).
- Permissões (registros do TCC, `log show --predicate 'subsystem == "com.apple.TCC"'`):
  - O Claude Desktop inicia extensões com `Claude.app/Contents/Helpers/disclaimer --pgroup -- <comando>`:
    o comando vira o processo **responsável** e os filhos herdam. No tipo `uv`, o Claude ignora o
    `command` do manifest e roda o `uv` direto; no tipo `binary`, roda o `command`.
  - Ler a pasta do WhatsApp sem Acesso Total ao Disco gera o pedido "dados de outros apps"
    (`kTCCServiceSystemPolicyAppData`). O "Permitir" é de sessão: o log marca "Session scoped auth is
    invalid" e a mesma execução pediu de novo 43 min depois. Em 2026-10-21 foram 6 pedidos, todos em
    nome do `uv`, vindos do servidor, do trabalhador de transcrição e do `afconvert`.
  - Antes do pedido, o macOS consulta se o responsável tem Acesso Total ao Disco
    (`kTCCServiceSystemPolicyAllFiles`). Binários ad hoc são identificados pelo caminho e pela
    assinatura; recompilar o lançador gera outro binário (conferido) e a permissão cai.
  - Com o lançador: o pedido saiu em nome do `zapmcp`; com o Acesso Total ao Disco dado a ele, a
    leitura passou sem pedido (`authValue=2`). O item às vezes não aparece na lista dos Ajustes,
    mas a permissão vale. `tccutil reset` só remove itens por identificador de pacote; itens por
    caminho só saem limpando a lista inteira.

## 8. Pendências e ideias em aberto

Melhorias já descritas em detalhe estão no [ROADMAP.md](../ROADMAP.md): o que falta da liberação
do acesso (assinatura estável do lançador) e o dicionário de apelidos para achar conversas.

- **Nome final.**
- **Privacidade do índice**: `index.db` e `transcripts.db` ficam em pasta comum, legíveis por
  qualquer processo do usuário (a pasta do WhatsApp é protegida). Opções: índice só em memória no
  servidor (recomendado para o modo só-MCP) ou criptografia com chave no Keychain.
- **Nomes gravados nas linhas**: renomear um contato só reflete nas mensagens antigas após
  `sync --full`. Correção possível: guardar o jid no índice e resolver o nome na leitura.
- Glossário do usuário como dica para o Whisper (resolveria "Claude" → "Cloud"). Sugerido, não aprovado.
- Mapear os tipos de mensagem desconhecidos (precisa ler amostras, com autorização).
- Publicar no PyPI para `claude mcp add ZapMCP -- uvx zapmcp serve` (precisa de conta do autor).
- Fase 2 de mídia: `list_media`, busca dentro de documentos, quadros de vídeo.
- A transcrição só anda com o Claude aberto (quem inicia o servidor é o Claude).

## 9. Próximo passo: app de desktop

O autor quer começar a próxima sessão **discutindo stack e abordagem** do app. O que já foi dito:

**Objetivo**: o código de hoje vira um **app de desktop open-source**, distribuído só pelo código
aberto (repositório público, e talvez builds prontos nas releases). Fora da App Store. Pontos a levar
para a discussão:
- Quem **compila o próprio app** a partir do código não passa pelo bloqueio do Gatekeeper ("a Apple
  não pôde verificar"), que vale para arquivos baixados. Quem baixar um **build pronto** passa, a menos
  que ele seja assinado com Developer ID e notarizado.
- A permissão de Acesso Total ao Disco fica presa à assinatura: builds com assinatura instável (ad hoc)
  perdem a permissão a cada atualização. Isso conversa direto com o item 1 do [ROADMAP.md](../ROADMAP.md).
- O caminho de instalação precisa ser simples para um público técnico, mas não necessariamente de
  desenvolvedor (ex.: um comando de instalação ou um build pronto, além de "clone e compile").

**Funções previstas para o app**
- Onboarding do Acesso Total ao Disco (o app abre a tela dos Ajustes e detecta a permissão).
- Transcrever o histórico completo como opção, mostrando antes a contagem de áudios e o tempo
  estimado. Base pronta: `zapmcp transcribe --all`.
- Opção para as buscas ignorarem conversas arquivadas.
- Escolher quais conversas o Claude pode ver (lista liberada).
- Status (última atualização, fila de transcrição) na barra de menu.

**Por que um app (argumentos levantados)**
- Permissão: o macOS atribui o acesso ao processo responsável (seção 7). No modo só-MCP, quem lê a
  pasta do WhatsApp é o servidor, e o responsável é o lançador `bin/zapmcp` (antes, o `uv`). Com um
  app, só ele recebe o Acesso Total ao Disco, a permissão sobrevive às atualizações (Developer ID) e
  o servidor MCP lê apenas o índice.
- Atualização por evento (FSEvents no `-wal`) em vez de a cada 5 min, e transcrição sem depender do
  Claude aberto.
- Contra: mais um download e um processo rodando; com público técnico, o modo só-MCP já funciona.

**Arquitetura esboçada para o app em Swift (Mac)**
- App de barra de menu (SwiftUI `MenuBarExtra`, `SMAppService` para abrir no login) que copia o
  banco, indexa e transcreve; grava o `index.db`.
- Servidor MCP continua em Python/FastMCP, só lendo o índice, com `ZAPMCP_AUTO_SYNC_SECONDS=0`.
  O schema do índice vira o contrato entre os dois (versão no `meta`).
- Peças citadas: GRDB.swift (SQLite/FTS5), FSEvents, AVFoundation (Opus), SpeechAnalyzer (macOS 26)
  ou WhisperKit, ou manter whisper.cpp; Sparkle para atualizações; DMG assinado com Developer ID e
  notarizado, fora da Mac App Store (sandbox e revisão dificultam ler dados de outro app).
- Reescrever em Swift: `snapshot.py`, `whatsapp.py`, `sync.py` e a escrita do `store.py`
  (~250 linhas de lógica). Alternativa discutida: o app Swift chamar o indexador Python (evita
  reescrever, mas obriga a embutir e assinar o Python).
- Precisa de Xcode completo (hoje só há Command Line Tools) e, para distribuir, Apple Developer
  Program (US$ 99/ano). Sem assinatura oficial, o macOS bloqueia a primeira abertura e o Acesso
  Total ao Disco se perde a cada atualização.

**Alternativa levantada por causa do Windows**: casca multiplataforma (Tauri) chamando o Python,
porque índice, servidor e whisper.cpp já são multiplataforma e o Windows precisará de outra forma de
ler os dados. O autor, por ora, prefere Swift no Mac.

## 10. Como trabalhar neste projeto

- Conversa em português do Brasil; explicações simples, com tabelas; respostas honestas, medindo
  antes de afirmar.
- **Privacidade**: não ler nem imprimir conteúdo de mensagens, nomes de contatos ou transcrições sem
  autorização explícita. Verificar com dados reais usando contagens e saídas mascaradas.
- Nunca escrever na pasta do WhatsApp; sempre trabalhar sobre a cópia.
- Testar primeiro no banco falso (`tests/`), depois nos dados reais com métricas; reempacotar o
  `.mcpb` e pedir ao autor para reinstalar.
- Commits só quando o autor pedir. `export/` (relatórios com transcrições), `dist/` e `.venv/`
  ficam fora do git.
- O repositório é **público**: nada de dados reais (nomes, números, mensagens, caminhos pessoais) em
  código, testes ou documentos; nos testes, só dados fictícios.
