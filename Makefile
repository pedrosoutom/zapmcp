# Empacota a extensão do Claude Desktop (dist/ZapMCP.mcpb), com o lançador compilado.
# O lançador só é recompilado quando launcher/zapmcp.c muda: um binário novo tem outra assinatura
# (ad hoc) e o macOS pede o Acesso Total ao Disco de novo.
# bin/zapmcp-unlock é o pedido de Touch ID do cadeado (unlock/zapmcp-unlock.swift); recompilar não
# mexe em permissão nenhuma.

.PHONY: pack launcher

pack: launcher
	npx -y @anthropic-ai/mcpb pack . dist/ZapMCP.mcpb

launcher: bin/zapmcp bin/zapmcp-unlock

bin/zapmcp: launcher/zapmcp.c
	mkdir -p bin
	clang -O2 -Wall -Wextra -o $@ $<
	codesign --force --sign - --identifier zapmcp $@

bin/zapmcp-unlock: unlock/zapmcp-unlock.swift
	mkdir -p bin
	swiftc -O -framework LocalAuthentication -o $@ $<
	codesign --force --sign - --identifier zapmcp-unlock $@
