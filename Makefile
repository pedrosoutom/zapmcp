# Empacota a extensão do Claude Desktop (dist/ZapMCP.mcpb), com o lançador compilado.
# O lançador só é recompilado quando launcher/zapmcp.c muda: um binário novo tem outra assinatura
# (ad hoc) e o macOS pede o Acesso Total ao Disco de novo.

EXTENSAO = $(HOME)/Library/Application Support/Claude/Claude Extensions/local.mcpb.pedro-souto.zapmcp

.PHONY: pack launcher acesso

pack: launcher
	npx -y @anthropic-ai/mcpb pack . dist/ZapMCP.mcpb
	@echo ""
	@echo "Pronto: dist/ZapMCP.mcpb. Próximos passos:"
	@echo "  1. Instale no Claude Desktop: open dist/ZapMCP.mcpb (ou arraste o arquivo em Ajustes > Extensões)."
	@echo "  2. Só na primeira instalação: make acesso, e arraste o zapmcp do Finder para a lista de Acesso Total ao Disco."

launcher: bin/zapmcp

bin/zapmcp: launcher/zapmcp.c
	mkdir -p bin
	clang -O2 -Wall -Wextra -o $@ $<
	codesign --force --sign - --identifier zapmcp $@

# Abre o painel de Acesso Total ao Disco e mostra o lançador instalado no Finder, para arrastar.
acesso:
	@test -e "$(EXTENSAO)/bin/zapmcp" || { echo "A extensão ainda não está instalada no Claude Desktop (passo 1)."; exit 1; }
	open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
	open -R "$(EXTENSAO)/bin/zapmcp"
	@echo "Arraste o zapmcp do Finder para a lista de Acesso Total ao Disco e confira se a chave ficou ligada."
