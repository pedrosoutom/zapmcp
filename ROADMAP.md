# Roadmap

Melhorias registradas para fazer. Cada item diz o que já foi feito, se algo foi. Para o estado atual
do projeto, ver [docs/CONTEXTO.md](docs/CONTEXTO.md).

## Direção: app de desktop open-source

*Registrado em 2026-10-13.*

Hoje o ZapMCP é só código (um servidor MCP e uma extensão do Claude Desktop). A ideia é transformá-lo
num **aplicativo de desktop open-source**. Não vai para a App Store nem para nenhuma loja: o usuário
baixa ou roda o código aberto que disponibilizarmos. A escolha de stack e abordagem é o próximo assunto
(ver a seção 9 do [docs/CONTEXTO.md](docs/CONTEXTO.md)). As melhorias abaixo devem ser pensadas já
dentro desse app.

## 1. Liberar o acesso uma vez só

*Registrado em 2026-10-13. Resolvido no modo só-MCP em 2026-10-31 (v0.3.5); falta a assinatura estável.*

**Problema:** o macOS perguntava várias vezes se o `uv` podia acessar "dados de outros apps" (a pasta
do WhatsApp), e o pedido voltava mesmo depois de permitido.

**Causa (medida nos registros do macOS):**
- O Claude Desktop inicia a extensão como processo **responsável** por si mesmo, e o macOS cobra a
  permissão desse processo. No tipo `uv` do manifest, era o `uv`.
- O "Permitir" desse pedido é temporário (de sessão) e vence sozinho. Cada servidor novo, o
  trabalhador de transcrição e o `afconvert` também passam pela checagem.
- O Acesso Total ao Disco evita o pedido, mas dado ao `uv` valeria para qualquer coisa que o Claude
  Desktop rodasse por ele.

**O que foi feito:**
- Lançador em C (`launcher/zapmcp.c`, compilado em `bin/zapmcp` pelo `make`). A extensão passou a
  ser do tipo `binary`: o Claude Desktop inicia o lançador, que inicia o `uv` e espera. O Acesso
  Total ao Disco é dado só ao lançador, uma vez. Testado: sem pedidos, leitura direta.
- O `Makefile` só recompila o lançador quando o fonte muda, porque cada binário novo perde a
  permissão.
- README com o passo único de liberação.

**O que falta:**
- **Assinatura estável do lançador.** Hoje é ad hoc: recompilar exige liberar de novo. Um
  certificado de assinatura (gratuito para uso próprio, Developer ID para distribuir) mantém a
  permissão entre versões.
- **Distribuir o `.mcpb` pronto** (nas Releases): o lançador viria compilado por outra máquina, e não
  sabemos se o Gatekeeper bloqueia um binário dentro de um `.mcpb` baixado. Precisaria ser universal
  (Apple Silicon e Intel). Hoje cada pessoa compila com `make`.
- No tipo `binary`, quem instala precisa ter o `uv` (antes era igual na prática: o Claude Desktop
  usava o `uv` instalado).
- No app de desktop, essa questão passa para o app assinado (ver a seção 9 do
  [docs/CONTEXTO.md](docs/CONTEXTO.md)).

## 2. Dicionário de de-paras (como o Dictionary do Wispr Flow)

*Registrado em 2026-10-13.*

**Problema:** quando peço "a mensagem que o Carlos me mandou", `list_chats("Carlos")` devolve várias conversas
com Carlos, mas nenhuma é a certa. O Carlos que eu quero é o contato salvo como "CB" (chat 123). O Claude
só achou a conversa buscando por palavra-chave.

**Ideia:** um dicionário editável de apelidos que o MCP consulta antes de procurar pelo nome.
- Um arquivo simples (ex.: `dictionary.json`) com entradas como `"Carlos" → chat 123 (CB)`. Deve aceitar
  vários apelidos por contato e funcionar para grupos também.
- Valer em todo lugar que recebe nome de conversa: `list_chats` e o parâmetro `chat` de `search` e
  `get_messages`. O apelido vem primeiro, e os resultados aproximados aparecem depois.
- Ferramentas para gerenciar o dicionário: `add_alias`, `list_aliases` e `remove_alias`. Assim o Claude
  salva o de-para quando eu confirmar ("sim, o Carlos é o CB").
- Mostrar no resultado quando um apelido foi usado (ex.: "Carlos → CB, pelo dicionário"), para eu notar
  se estiver errado.
- Extra: quando o nome for ambíguo e não houver apelido, colocar primeiro as conversas mais ativas e
  recentes.

**Notas de implementação:**
- Onde entra: `store.chats()` e `store.resolve_chat()`, que hoje ordenam por semelhança do nome e, no
  empate, pela última mensagem. Um apelido como "CB" não se parece com "Carlos", então só o dicionário
  resolve esse caso.
- O arquivo é dado pessoal: deve ficar em `~/Library/Application Support/zapmcp/`, fora do repositório.
- Seriam as primeiras tools que **escrevem** algo (só a configuração local; nada no WhatsApp), e por
  isso não podem ser marcadas como somente leitura. Como o Claude lê mensagens de terceiros, que
  podem tentar induzi-lo a criar um apelido errado, vale manter a regra de só salvar quando o usuário
  confirmar e sempre mostrar quando um apelido foi usado.
- Para o "extra": a atividade pode ser medida pela quantidade de mensagens recentes, que o índice já
  calcula em `list_chats`.
