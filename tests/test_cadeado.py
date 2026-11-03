"""Cadeado: o agente só lê uma conversa depois que o dono confirma no Mac."""

import threading
import time

import pytest

from test_zapmcp import wa_dir  # noqa: F401  (fixture compartilhada)
from zapmcp import cadeado, config


def test_nasce_trancado_e_abre_por_conversa():
    pedidos = []
    c = cadeado.Cadeado(pedir=lambda m: pedidos.append(m) or True, minutes=15, wait_seconds=1)
    assert not c.aberto("1") and c.liberados() == set()
    assert c.liberar("1", 'Claude Code quer ler a conversa "Projeto X" (get_messages).') is True
    assert pedidos == ['Claude Code quer ler a conversa "Projeto X" (get_messages).']
    assert c.aberto("1") and c.liberados() == {"1"}
    assert c.liberar("1", "outra") is True and len(pedidos) == 1  # mesma conversa, não pede de novo
    assert not c.aberto("2")  # outra conversa continua trancada


def test_cancelado_fica_trancado():
    c = cadeado.Cadeado(pedir=lambda m: False, minutes=15, wait_seconds=1)
    assert c.liberar("1", "m") is False and not c.aberto("1")


def test_janela_vence(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(cadeado.time, "monotonic", lambda: clock[0])
    c = cadeado.Cadeado(pedir=lambda m: True, minutes=15, wait_seconds=1)
    assert c.liberar("1", "m")
    clock[0] += 15 * 60 - 1
    assert c.aberto("1")
    clock[0] += 2
    assert not c.aberto("1") and c.liberados() == set()


def test_minutos_zero_desliga_o_cadeado():
    c = cadeado.Cadeado(pedir=lambda m: pytest.fail("não devia pedir"), minutes=0, wait_seconds=1)
    assert c.liberar("1", "m") is True and c.aberto("qualquer")


def test_pedido_simultaneo_abre_um_dialogo():
    gate, pedidos = threading.Event(), []

    def pedir(m):
        pedidos.append(m)
        gate.wait(2)
        return True

    c = cadeado.Cadeado(pedir=pedir, minutes=15, wait_seconds=1)
    results = []
    threads = [threading.Thread(target=lambda: results.append(c.liberar("1", "m"))) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.1)
    gate.set()
    for t in threads:
        t.join()
    assert results == [True, True, True] and len(pedidos) == 1


def test_pedir_no_mac_sem_binario(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAPMCP_UNLOCK_BIN", str(tmp_path / "nao-existe"))
    assert cadeado.pedir_no_mac("oi") is False and cadeado.ULTIMO_ERRO == "sem_binario"


def test_pedir_no_mac_codigos(monkeypatch, tmp_path):
    fake = tmp_path / "unlock"
    fake.write_text("#!/bin/sh\nexit $ZAPMCP_FAKE_CODE\n")
    fake.chmod(0o755)
    monkeypatch.setenv("ZAPMCP_UNLOCK_BIN", str(fake))
    for code, ok, erro in ((0, True, None), (1, False, None), (2, False, "sem_binario")):
        monkeypatch.setenv("ZAPMCP_FAKE_CODE", str(code))
        assert cadeado.pedir_no_mac("oi") is ok and cadeado.ULTIMO_ERRO == erro


def test_config_padroes(monkeypatch):
    monkeypatch.delenv("ZAPMCP_UNLOCK_MINUTES", raising=False)
    assert config.unlock_minutes() == 15 and config.unlock_wait_seconds() == 60
    monkeypatch.setenv("ZAPMCP_UNLOCK_MINUTES", "${user_config.unlock_minutes}")
    assert config.unlock_minutes() == 15


# --- servidor MCP ---

import asyncio  # noqa: E402

from fastmcp import Client  # noqa: E402


def _call(tool, args):
    from zapmcp.server import mcp

    async def go():
        async with Client(mcp) as client:
            return await client.call_tool(tool, args, raise_on_error=False)

    return asyncio.run(go())


def _armar(monkeypatch, resposta):
    from zapmcp import server, sync

    sync.run()
    monkeypatch.setenv("ZAPMCP_UNLOCK_MINUTES", "15")
    pedidos = []
    monkeypatch.setattr(server.cadeado, "pedir_no_mac", lambda m: pedidos.append(m) or resposta)
    server.reset_cadeado()
    return server, pedidos


def test_list_chats_com_nome_nao_pede_e_sem_nome_pede(wa_dir, monkeypatch):
    server, pedidos = _armar(monkeypatch, False)
    r = _call("list_chats", {"query": "projeto"})
    assert not r.is_error and "Projeto X" in r.content[0].text and pedidos == []
    r = _call("list_chats", {})
    assert r.is_error and r.content[0].text == server.cadeado.Cadeado.MENSAGEM_TRANCADO
    assert pedidos == ["desconhecido quer listar todas as conversas."]


def test_get_messages_pede_a_conversa_e_trancada_nao_devolve(wa_dir, monkeypatch):
    server, pedidos = _armar(monkeypatch, False)
    r = _call("get_messages", {"chat": "projeto x"})
    assert r.is_error and r.content[0].text == server.cadeado.Cadeado.MENSAGEM_TRANCADO
    assert pedidos == ['desconhecido quer ler a conversa "Projeto X 🚀" (get_messages).']


def test_confirmou_libera_so_aquela_conversa(wa_dir, monkeypatch):
    server, pedidos = _armar(monkeypatch, True)
    assert "Fechamos a entrega" in _call("get_messages", {"chat": "1", "since": "30d"}).content[0].text
    assert "Combinado" in _call("search", {"query": "cliente", "chat": "1"}).content[0].text
    assert len(pedidos) == 1  # a mesma conversa, um pedido só
    _call("get_messages", {"chat": "maria"})
    assert len(pedidos) == 2 and '"Maria Souza"' in pedidos[1]


def test_search_sem_chat_so_nas_liberadas(wa_dir, monkeypatch):
    server, pedidos = _armar(monkeypatch, True)
    r = _call("search", {"query": "cliente"})
    assert r.is_error and r.content[0].text == server.cadeado.Cadeado.MENSAGEM_SEM_LIBERADAS and pedidos == []
    _call("get_messages", {"chat": "maria"})
    r = _call("search", {"query": "cliente"})  # "cliente" só existe no Projeto X, que não foi liberado
    assert not r.is_error and r.content[0].text.startswith("Busca nas conversas liberadas: Maria Souza.")
    assert "Combinado" not in r.content[0].text
    _call("get_messages", {"chat": "1"})
    assert "Combinado" in _call("search", {"query": "cliente"}).content[0].text


def test_anexos_exigem_a_conversa_liberada(wa_dir, monkeypatch):
    server, pedidos = _armar(monkeypatch, False)
    r = _call("view_images", {"ids": [4]})
    assert len(r.content) == 1 and r.content[0].text == server.cadeado.Cadeado.MENSAGEM_TRANCADO
    assert pedidos[-1].endswith("(view_images).")
    r = _call("read_document", {"id": 20})
    assert r.is_error and r.content[0].text == server.cadeado.Cadeado.MENSAGEM_TRANCADO
    r = _call("transcribe_audio", {"ids": [3]})
    assert r.content[0].text.startswith(server.cadeado.Cadeado.MENSAGEM_TRANCADO)


def test_sem_binario_fica_trancado(wa_dir, monkeypatch, tmp_path):
    from zapmcp import server, sync

    sync.run()
    monkeypatch.setenv("ZAPMCP_UNLOCK_MINUTES", "15")
    monkeypatch.setenv("ZAPMCP_UNLOCK_BIN", str(tmp_path / "nao-existe"))
    server.reset_cadeado()
    r = _call("get_messages", {"chat": "1"})
    assert r.is_error and r.content[0].text == server.cadeado.Cadeado.MENSAGEM_SEM_BINARIO


def test_instrucoes_pedem_uso_sob_demanda():
    from zapmcp.server import INSTRUCTIONS

    assert "somente quando o usuário pedir" in INSTRUCTIONS and "liberar no Mac" in INSTRUCTIONS


# --- log de acesso ---


def test_log_uma_linha_por_chamada(wa_dir):
    from zapmcp import acesso

    acesso.registrar("Codex", "search", "query=a|b\nc", "liberado")
    linhas = (config.home() / "logs" / "acesso.log").read_text().splitlines()
    assert len(linhas) == 1 and linhas[0].endswith(" | Codex | search | query=a b c | liberado")


def test_servidor_registra_acesso(wa_dir, monkeypatch):
    server, pedidos = _armar(monkeypatch, True)
    _call("get_messages", {"chat": "1"})
    _call("get_messages", {"chat": "1"})
    log = (config.home() / "logs" / "acesso.log").read_text()
    linhas = log.splitlines()
    assert len(linhas) == 2
    assert "| desconhecido | get_messages | chat=Projeto X 🚀 since=7d until=None | pedido, liberado" in linhas[0]
    assert linhas[1].endswith("| liberado")
    assert "Combinado" not in log and "Fechamos" not in log  # nunca conteúdo

    monkeypatch.setattr(server.cadeado, "pedir_no_mac", lambda m: False)
    server.reset_cadeado()
    _call("search", {"query": "x", "chat": "maria"})
    assert (config.home() / "logs" / "acesso.log").read_text().splitlines()[-1].endswith(
        "| search | query=x chat=Maria Souza | pedido, trancado"
    )
