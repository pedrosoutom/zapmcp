# Empacota a extensão do Claude Desktop (dist/ZapMCP.mcpb), com o lançador compilado.
# O lançador só é recompilado quando launcher/zapmcp.c muda: um binário novo tem outra assinatura
# (ad hoc) e o macOS pede o Acesso Total ao Disco de novo.
# bin/ZapMCP.app é o pedido de Touch ID do cadeado (unlock/); recompilar não mexe em permissão nenhuma.

.PHONY: pack launcher

pack: launcher
	npx -y @anthropic-ai/mcpb pack . dist/ZapMCP.mcpb

launcher: bin/zapmcp bin/ZapMCP.app/Contents/MacOS/zapmcp-unlock

bin/zapmcp: launcher/zapmcp.c
	mkdir -p bin
	clang -O2 -Wall -Wextra -o $@ $<
	codesign --force --sign - --identifier zapmcp $@

# O pedido de Touch ID vive num bundle .app: é o que dá nome ("ZapMCP") e ícone ao diálogo do sistema.
APP = bin/ZapMCP.app

$(APP)/Contents/MacOS/zapmcp-unlock: unlock/zapmcp-unlock.swift unlock/Info.plist unlock/icone.py
	mkdir -p $(APP)/Contents/MacOS $(APP)/Contents/Resources
	cp unlock/Info.plist $(APP)/Contents/Info.plist
	uv run python unlock/icone.py $(APP)/Contents/ZapMCP.iconset
	iconutil -c icns -o $(APP)/Contents/Resources/ZapMCP.icns $(APP)/Contents/ZapMCP.iconset
	rm -rf $(APP)/Contents/ZapMCP.iconset
	swiftc -O -framework LocalAuthentication -o $@ $<
	xattr -cr $(APP)
	codesign --force --sign - --identifier dev.zapmcp.unlock $(APP)
