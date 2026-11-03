"""Cadeado: o agente só lê uma conversa depois que o dono confirma no Mac."""

import threading
import time

import pytest

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
