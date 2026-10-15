# Roadmap

Melhorias registradas para fazer. Nada aqui está implementado ainda. Para o estado atual do projeto,
ver [docs/CONTEXTO.md](docs/CONTEXTO.md).

## Direção: app de desktop open-source

*Registrado em 2026-10-13.*

Hoje o ZapMCP é só código (um servidor MCP e uma extensão do Claude Desktop). A ideia é transformá-lo
num **aplicativo de desktop open-source**. Não vai para a App Store nem para nenhuma loja: o usuário
baixa ou roda o código aberto que disponibilizarmos. A escolha de stack e abordagem é o próximo assunto
(ver a seção 9 do [docs/CONTEXTO.md](docs/CONTEXTO.md)). As melhorias abaixo devem ser pensadas já
dentro desse app.

## 1. Liberar o acesso uma vez só

*Registrado em 2026-10-13.*

**Problema:** o computador e o Claude pedem aprovação várias vezes para o `uv` acessar o sistema e os
arquivos (o banco do WhatsApp). O pedido volta a cada nova sessão ou execução.

**Experiência ideal:** autorizar uma única vez, na instalação, e não ser mais perguntado.

**Para investigar:**
- Hipótese: o macOS (TCC) amarra a permissão ao caminho do executável. Rodando via `uv run`/`uvx`, o
  Python pode trocar de caminho a cada vez (cache ou ambiente temporário), e aí a permissão concedida
  não vale para a próxima execução.
- Saídas possíveis: rodar a partir de um executável com caminho fixo (`uv tool install`, venv fixo ou
  um app assinado) e dar Acesso Total ao Disco a ele uma vez só. Outra opção é ler de uma cópia do
  banco feita por um processo que já tenha permissão.
- Documentar no README esse passo único de configuração e como confirmar que o acesso ficou liberado.

**Pistas já observadas** (a confirmar):
- São dois tipos de pedido diferentes: o do **macOS** (acesso a dados de outro app) e o do **Claude**
  (aprovação de cada tool). Vale separar os dois na investigação.
- O Claude Desktop inicia a extensão assim: `Claude.app/Contents/Helpers/disclaimer --pgroup --
  /opt/homebrew/bin/uv run --directory …/Claude Extensions/local.mcpb.pedro-souto.zapmcp zapmcp serve`.
  O `disclaimer` faz o processo filho responder pelas próprias permissões, então o macOS deve atribuir
  o acesso ao `uv`, e não ao Claude. Isso explicaria o pedido aparecer em nome do `uv`.
- O `uv` do Homebrew é assinado só localmente (ad hoc). Se o macOS identifica o executável pela
  assinatura, cada atualização do `uv` pode contar como um programa novo e perder a permissão.
- O trabalhador de transcrição é outro processo (`python -m zapmcp.cli transcribe`), que também lê a
  pasta de mídias do WhatsApp; ele pode gerar pedidos próprios.

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
