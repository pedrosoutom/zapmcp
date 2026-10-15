"""Fluxo completo sobre um banco falso com o mesmo formato do WhatsApp Desktop."""

import asyncio
import base64
import io
import sqlite3
import zipfile
import time
from contextlib import closing
from datetime import datetime

import docx
import openpyxl
import pytest
from fastmcp import Client
from PIL import Image

from zapmcp import cli, config, store, sync
from zapmcp.dates import parse_when
from zapmcp.whatsapp import APPLE_EPOCH

NOW = int(time.time())
DAY = 86400

WA_SCHEMA = """
CREATE TABLE ZWACHATSESSION (Z_PK INTEGER PRIMARY KEY, ZCONTACTJID TEXT, ZPARTNERNAME TEXT,
    ZSESSIONTYPE INTEGER, ZARCHIVED INTEGER, ZREMOVED INTEGER);
CREATE TABLE ZWAGROUPMEMBER (Z_PK INTEGER PRIMARY KEY, ZMEMBERJID TEXT, ZFIRSTNAME TEXT, ZCONTACTNAME TEXT);
CREATE TABLE ZWAMESSAGE (Z_PK INTEGER PRIMARY KEY, ZCHATSESSION INTEGER, ZMESSAGEDATE REAL, ZISFROMME INTEGER,
    ZMESSAGETYPE INTEGER, ZTEXT TEXT, ZPUSHNAME TEXT, ZGROUPMEMBER INTEGER);
CREATE TABLE ZWAMEDIAITEM (Z_PK INTEGER PRIMARY KEY, ZMESSAGE INTEGER, ZTITLE TEXT, ZMEDIALOCALPATH TEXT,
    ZMOVIEDURATION REAL);
CREATE TABLE ZWAPROFILEPUSHNAME (Z_PK INTEGER PRIMARY KEY, ZJID TEXT, ZPUSHNAME TEXT);
"""

# No app de Mac, o ZPUSHNAME da mensagem vem assim, codificado; o nome de verdade fica em ZWAPROFILEPUSHNAME.
ENCODED = "CIqf4NUGIABIAZABAPABAtgCo+uL2fCMlwM="


def apple(ts: int) -> float:
    return ts - APPLE_EPOCH


def add_message(wa, pk, chat, ts, text=None, *, from_me=0, type_=0, push=None, member=None):
    wa.execute(
        "INSERT INTO ZWAMESSAGE VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (pk, chat, apple(ts), from_me, type_, text, push, member),
    )


def tiny_pdf(text: str) -> bytes:
    """Um PDF mínimo de uma página com texto de verdade (Helvetica)."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def write_media(root):
    """Arquivos de mídia como o WhatsApp guarda em Message/Media."""
    media = root / "Message" / "Media"
    (media / "docs").mkdir(parents=True)
    Image.new("RGB", (2400, 1200), "navy").save(media / "y.jpg")
    (media / "x.opus").write_bytes(b"OggS audio do Bruno")
    (media / "vagas.opus").write_bytes(b"OggS audio de vagas")
    (media / "docs" / "encaminhado.opus").write_bytes(b"OggS audio do Bruno")  # o mesmo áudio, encaminhado
    (media / "docs" / "a.pdf").write_bytes(tiny_pdf("Multa de 10 por cento por atraso"))
    Image.new("RGB", (600, 800), "white").save(media / "docs" / "b.pdf")  # PDF só com imagem: "escaneado"
    word = docx.Document()
    word.add_paragraph("Cláusula de rescisão")
    table = word.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Multa", "10%"
    word.save(media / "docs" / "c.docx")
    book = openpyxl.Workbook()
    book.active.title = "Custos"
    book.active.append(["Mês", "Valor"])
    book.active.append(["Setembro", 1200])
    book.save(media / "docs" / "d.xlsx")
    with zipfile.ZipFile(media / "docs" / "e.zip", "w") as z:
        z.writestr("minha-skill/SKILL.md", "# Skill")
    (media / "docs" / "f.txt").write_text("\n".join(f"linha {i} " + "x" * 90 for i in range(400)))
    (media / "docs" / "g.dmg").write_bytes(b"\0" * 100)


@pytest.fixture
def wa_dir(tmp_path, monkeypatch):
    src = tmp_path / "whatsapp"
    src.mkdir()
    monkeypatch.setenv("ZAPMCP_WA_DIR", str(src))
    monkeypatch.setenv("ZAPMCP_HOME", str(tmp_path / "home"))
    # Nos testes, nada de processo de transcrição de verdade nem espera.
    monkeypatch.setenv("ZAPMCP_TRANSCRIBE", "0")
    monkeypatch.setenv("ZAPMCP_TRANSCRIBE_WAIT_SECONDS", "0")

    with closing(sqlite3.connect(src / "ContactsV2.sqlite")) as c:
        c.execute("CREATE TABLE ZWAADDRESSBOOKCONTACT (Z_PK INTEGER PRIMARY KEY, ZLID TEXT, ZWHATSAPPID TEXT, ZFULLNAME TEXT)")
        c.execute("INSERT INTO ZWAADDRESSBOOKCONTACT VALUES (1, '111@lid', '5511900000001@s.whatsapp.net', 'Ana Lima')")
        c.execute("INSERT INTO ZWAADDRESSBOOKCONTACT VALUES (2, '4455667788990@lid', NULL, 'Tatá')")
        c.commit()

    with closing(sqlite3.connect(src / "ChatStorage.sqlite")) as wa:
        wa.execute("PRAGMA journal_mode = WAL")
        wa.executescript(WA_SCHEMA)
        wa.executemany(
            "INSERT INTO ZWACHATSESSION VALUES (?, ?, ?, ?, 0, 0)",
            [
                (1, "120363@g.us", "Projeto X 🚀", 1),
                (2, "5511900000002@s.whatsapp.net", "Maria Souza", 0),
                (3, "status@broadcast", None, 2),
            ],
        )
        wa.executemany(
            "INSERT INTO ZWAGROUPMEMBER VALUES (?, ?, ?, '')",
            [(10, "111@lid", None), (11, "222@lid", "Bru"), (12, "333@lid", "+CgAQ8pT1zwY=")],
        )
        wa.execute("INSERT INTO ZWAPROFILEPUSHNAME VALUES (1, '222@lid', 'Bruno')")
        wa.execute("INSERT INTO ZWAPROFILEPUSHNAME VALUES (2, '998877665544@lid', 'Zé')")
        t = NOW - 36 * 3600  # dentro da janela de 48 h que o sync revisita
        add_message(wa, 1, 1, t, "Fechamos a entrega para sexta.", member=10, push=ENCODED)
        add_message(wa, 2, 1, t + 60, "Combinado, aviso o cliente.", from_me=1)
        add_message(wa, 3, 1, t + 120, type_=3, member=11, push=ENCODED)
        wa.execute("INSERT INTO ZWAMEDIAITEM VALUES (1, 3, NULL, 'Media/x.opus', 37.2)")
        add_message(wa, 4, 1, t + 180, type_=1, member=10)
        wa.execute("INSERT INTO ZWAMEDIAITEM VALUES (2, 4, 'versão final', 'Media/y.jpg', 0)")
        add_message(wa, 5, 1, t + 240, "222@lid", type_=6)
        add_message(wa, 6, 1, t + 300, type_=59, member=11, push=ENCODED)
        add_message(wa, 29, 1, t + 360, "Oi, gente", member=12, push=ENCODED)  # sem agenda nem perfil
        add_message(wa, 7, 2, NOW - 30 * DAY, "Reunião amanhã\nàs 10h")
        add_message(wa, 8, 3, NOW - DAY, "status de alguém")

        wa.execute("INSERT INTO ZWACHATSESSION VALUES (4, '999@g.us', 'Contratos', 1, 0, 0)")
        docs = [
            (20, "contrato.pdf", "Media/docs/a.pdf"),
            (21, "escaneado.pdf", "Media/docs/b.pdf"),
            (22, "clausulas.docx", "Media/docs/c.docx"),
            (23, "orcamento.xlsx", "Media/docs/d.xlsx"),
            (24, "skill.zip", "Media/docs/e.zip"),
            (25, "longo.txt", "Media/docs/f.txt"),
            (26, "sumiu.pdf", "Media/docs/nao-baixado.pdf"),
            (28, "app.dmg", "Media/docs/g.dmg"),
        ]
        for pk, name, path in docs:
            add_message(wa, pk, 4, NOW - 10 * DAY + pk, name, type_=8, member=10)
            wa.execute("INSERT INTO ZWAMEDIAITEM VALUES (?, ?, NULL, ?, 0)", (pk, pk, path))
        # Grupo arquivado, com um áudio recente: fica fora da transcrição automática.
        wa.execute("INSERT INTO ZWACHATSESSION VALUES (5, '777@g.us', 'Vagas SP', 1, 1, 0)")
        add_message(wa, 32, 5, NOW - 3 * DAY, type_=3, member=10)
        wa.execute("INSERT INTO ZWAMEDIAITEM VALUES (32, 32, NULL, 'Media/vagas.opus', 12)")
        add_message(wa, 33, 4, NOW - 10 * DAY + 33, "bora @4455667788990!!! e @998877665544, cadê @123456789? ana@1234567.com",
                    member=10)
        add_message(wa, 30, 4, NOW - 10 * DAY + 30, type_=3, member=10)  # áudio encaminhado
        wa.execute("INSERT INTO ZWAMEDIAITEM VALUES (30, 30, NULL, 'Media/docs/encaminhado.opus', 37.2)")
        add_message(wa, 31, 4, NOW - 10 * DAY + 31, type_=3, member=10)  # nunca baixado
        wa.execute("INSERT INTO ZWAMEDIAITEM VALUES (31, 31, NULL, 'Media/docs/nao-baixado.opus', 5)")
        # Caminho que tenta sair da pasta de mídias: tem que ser ignorado.
        add_message(wa, 27, 4, NOW - 10 * DAY + 27, type_=1, member=10)
        wa.execute("INSERT INTO ZWAMEDIAITEM VALUES (27, 27, NULL, '../../ContactsV2.sqlite', 0)")
        wa.commit()
    write_media(src)
    return src


def index():
    return closing(store.connect(config.index_path()))


def conversation_lines(chat="projeto"):
    with index() as conn:
        found, _ = store.resolve_chat(conn, chat)
        from zapmcp import format as fmt

        return [fmt.line(m).split("] ", 1)[1] for m in store.messages_in(conn, found.id, 0)]


def test_sync_builds_conversation_lines(wa_dir):
    result = sync.run()
    assert result.full and result.messages == 21  # a do status fica de fora
    assert conversation_lines() == [
        "Ana Lima: Fechamos a entrega para sexta.",
        "Você: Combinado, aviso o cliente.",
        "~ Bruno: [áudio #3 0:37 · ainda não transcrito]",
        "Ana Lima: [imagem #4] versão final",
        "~ Bruno: [tipo 59]",
        "333: Oi, gente",
    ]
    assert conversation_lines("maria") == ["Maria Souza: Reunião amanhã\n    às 10h"]
    assert not list(config.snapshot_dir().glob("*")), "a cópia de trabalho é apagada depois do sync"


def test_incremental_sync_picks_new_and_edited_messages(wa_dir):
    sync.run()
    with closing(sqlite3.connect(wa_dir / "ChatStorage.sqlite")) as wa:
        add_message(wa, 9, 1, NOW, "Contrato assinado!", member=10)
        wa.execute("UPDATE ZWAMESSAGE SET ZTEXT = 'Fechamos a entrega para segunda.' WHERE Z_PK = 1")
        wa.commit()
    result = sync.run()
    assert not result.full
    lines = conversation_lines()
    assert lines[0] == "Ana Lima: Fechamos a entrega para segunda."
    assert lines[-1] == "Ana Lima: Contrato assinado!"
    with index() as conn:
        assert [m["id"] for m in store.search(conn, "sexta")] == []


def test_new_normalizer_version_rebuilds_index(wa_dir, monkeypatch):
    from zapmcp import whatsapp

    sync.run()
    assert not sync.run().full
    monkeypatch.setattr(whatsapp, "NORMALIZER_VERSION", whatsapp.NORMALIZER_VERSION + 1)
    assert sync.run().full


def test_mentions_show_names(wa_dir):
    sync.run()
    assert "Ana Lima: bora @Tatá!!! e @~Zé, cadê @123456789? ana@1234567.com" in conversation_lines("contratos")
    with index() as conn:
        assert [m["id"] for m in store.search(conn, "tata")] == [33]


def test_search_ignores_accents_and_odd_characters(wa_dir):
    sync.run()
    with index() as conn:
        assert [m["id"] for m in store.search(conn, "reuniao")] == [7]
        assert [m["id"] for m in store.search(conn, "Reunião")] == [7]
        assert [m["id"] for m in store.search(conn, "entrega: sexta")] == [1]
        assert [m["id"] for m in store.search(conn, "reuniao", chat_id=1)] == []


def test_chat_names_are_fuzzy(wa_dir):
    sync.run()
    with index() as conn:
        assert store.resolve_chat(conn, "projeto x")[0].id == 1
        assert store.resolve_chat(conn, "PROJETO")[0].id == 1
        assert store.resolve_chat(conn, "maria sousa")[0].id == 2
        assert store.resolve_chat(conn, "1")[0].id == 1
        with pytest.raises(LookupError):
            store.resolve_chat(conn, "condomínio")


def test_mcp_tools(wa_dir):
    from zapmcp.server import mcp

    async def call_all():
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
            chats = await client.call_tool("list_chats", {})
            messages = await client.call_tool("get_messages", {"chat": "projeto x", "since": "7d", "limit": 2})
            found = await client.call_tool("search", {"query": "cliente"})
            missing = await client.call_tool("get_messages", {"chat": "condomínio"}, raise_on_error=False)
            return names, chats, messages, found, missing

    names, chats, messages, found, missing = asyncio.run(call_all())
    assert names == {"list_chats", "get_messages", "search", "view_images", "read_document", "transcribe_audio"}
    assert chats.content[0].text.splitlines()[0].startswith("1 · Projeto X 🚀 · grupo")
    text = messages.content[0].text
    assert text.startswith("# Projeto X 🚀 (grupo · id 1)")
    assert "6 mensagens" in text and "Mostrando as 2 mais recentes" in text
    assert text.rstrip().endswith("333: Oi, gente")
    assert "» [" in found.content[0].text and "Você: Combinado, aviso o cliente." in found.content[0].text
    assert missing.is_error and "Nenhuma conversa" in missing.content[0].text


def test_export_writes_markdown(wa_dir, tmp_path, capsys):
    assert cli.main(["export", "--chat", "projeto", "--since", "7d", "--out", str(tmp_path / "out")]) == 0
    [path] = (tmp_path / "out").glob("*.md")
    assert path.name.startswith("projeto-x_")
    content = path.read_text()
    assert content.startswith("# Projeto X 🚀\n\nGrupo · ")
    assert "· 6 mensagens · 1 áudios" in content
    assert "Ana Lima: Fechamos a entrega para sexta." in content


def test_attachment_markers(wa_dir):
    sync.run()
    lines = conversation_lines("contratos")
    assert "Ana Lima: [documento #20 · 1 KB] contrato.pdf" in lines
    assert "Ana Lima: [documento · sem arquivo neste Mac] sumiu.pdf" in lines
    assert "Ana Lima: [imagem · sem arquivo neste Mac]" in lines  # caminho fora da pasta de mídias


def call(tool, args):
    from zapmcp.server import mcp

    async def go():
        async with Client(mcp) as client:
            return await client.call_tool(tool, args, raise_on_error=False)

    return asyncio.run(go())


def texts(result):
    return "\n".join(c.text for c in result.content if c.type == "text")


def images(result):
    return [Image.open(io.BytesIO(base64.b64decode(c.data))) for c in result.content if c.type == "image"]


def test_view_images(wa_dir):
    sync.run()
    result = call("view_images", {"ids": [4, 1, 999]})
    assert [img.size for img in images(result)] == [(1568, 784)]  # reduzida para o limite do Claude
    text = texts(result)
    assert "#4 · Projeto X 🚀 · Ana Lima ·" in text and "legenda: versão final" in text
    assert "#1 é texto, não imagem." in text
    assert "#999: não encontrei" in text


def test_read_document(wa_dir):
    sync.run()
    pdf = call("read_document", {"id": 20})
    assert "Multa de 10 por cento por atraso" in texts(pdf) and "PDF, 1 página · parte 1 de 1" in texts(pdf)

    scanned = call("read_document", {"id": 21})
    assert "escaneada" in texts(scanned) and len(images(scanned)) == 1

    assert "Cláusula de rescisão" in texts(call("read_document", {"id": 22}))
    assert "Multa | 10%" in texts(call("read_document", {"id": 22}))
    sheet = texts(call("read_document", {"id": 23}))
    assert "## Aba: Custos" in sheet and "Setembro\t1200" in sheet
    assert "minha-skill/SKILL.md" in texts(call("read_document", {"id": 24}))

    first = texts(call("read_document", {"id": 25}))
    assert "parte 1 de 3" in first and "part=2" in first
    assert "parte 3 de 3" in texts(call("read_document", {"id": 25, "part": 3}))

    for args, error in [
        ({"id": 25, "part": 4}, "tem 3 parte(s)"),
        ({"id": 26}, "não está neste Mac"),
        ({"id": 28}, "não suportado"),
        ({"id": 4}, "Use view_images"),
    ]:
        result = call("read_document", args)
        assert result.is_error and error in texts(result), args


class FakeTranscriber:
    name = "fake"

    def __init__(self):
        self.calls = []

    def transcribe(self, path):
        self.calls.append(path.name)
        return "Só preciso do contrato assinado antes."


def test_audio_transcription_flow(wa_dir):
    from zapmcp import transcripts, worker

    sync.run()
    assert "1 áudio(s) sem transcrição" in texts(call("get_messages", {"chat": "projeto x"}))
    assert "Ana Lima: [áudio 0:05 · sem arquivo neste Mac]" in conversation_lines("contratos")

    # O Claude pede o #3: ele fura a fila (o áudio encaminhado #30 é mais novo e viria antes).
    assert "#3: ainda na fila" in texts(call("transcribe_audio", {"ids": [3]}))
    fake = FakeTranscriber()
    assert worker.run_once(fake, limit=1) == 1
    assert "~ Bruno: [áudio 0:37] Só preciso do contrato assinado antes." in conversation_lines()

    # Os áudios da conversa "Contratos" têm 10 dias: ficam fora da transcrição automática (7 dias).
    assert worker.run_once(fake) == 0
    assert "Ana Lima: [áudio #30 0:37 · ainda não transcrito]" in conversation_lines("contratos")
    assert "para os mais antigos, use transcribe_audio" in texts(call("get_messages", {"chat": "contratos", "since": "30d"}))

    # Com --all entram também; o encaminhado reaproveita o cache pelo hash, e o que não está no Mac
    # vira falha, sem laço.
    assert worker.run_once(fake, all_history=True) == 2
    assert fake.calls == ["x.opus"]
    assert "Ana Lima: [áudio 0:37] Só preciso do contrato assinado antes." in conversation_lines("contratos")
    with closing(transcripts.connect()) as cache:
        assert "Media/docs/nao-baixado.opus" in transcripts.recently_failed(cache)

    # Entra na busca e sobrevive a um índice refeito do zero.
    with index() as conn:
        assert {m["id"] for m in store.search(conn, "contrato assinado")} == {3, 30}
    sync.run(full=True)
    assert "~ Bruno: [áudio 0:37] Só preciso do contrato assinado antes." in conversation_lines()
    assert fake.calls == ["x.opus"]

    result = texts(call("transcribe_audio", {"ids": [3, 1, 31]}))
    assert "#3 · Projeto X 🚀 · ~ Bruno ·" in result and "Só preciso do contrato" in result
    assert "#1 é texto, não áudio." in result
    assert "#31: o arquivo não está neste Mac" in result


def test_archived_groups_wait_for_a_request(wa_dir):
    from zapmcp import worker

    sync.run()
    assert "Vagas SP · grupo arquivado" in texts(call("list_chats", {"query": "vagas"}))
    assert worker.run_once(FakeTranscriber(), limit=5, requested_only=False) == 1  # só o #3, do Projeto X
    assert conversation_lines("vagas") == ["Ana Lima: [áudio #32 0:12 · ainda não transcrito]"]
    assert "Este grupo está arquivado" in texts(call("get_messages", {"chat": "vagas"}))

    call("transcribe_audio", {"ids": [32]})  # o pedido do Claude fura a regra
    assert worker.run_once(FakeTranscriber()) == 1
    assert conversation_lines("vagas") == ["Ana Lima: [áudio 0:12] Só preciso do contrato assinado antes."]


def test_transcript_cleanup():
    from zapmcp.transcribe import clean

    assert clean(["Oi, tudo bem?", "Oi, tudo bem?", "Beleza."]) == "Oi, tudo bem? Beleza."
    repeated = "Não daria para a gente fazer essa online? Não daria para a gente fazer essa online?"
    assert clean([repeated]) == "Não daria para a gente fazer essa online?"
    assert clean(["Seria possível? Então ây... Я..."]) == "Seria possível? Então ây... […]"
    assert clean(["Legendas pela comunidade Amara.org"]) == ""
    assert clean(["Tá ligado, tá ligado? Beleza"]) == "Tá ligado, tá ligado? Beleza"  # repetição curta é fala


def test_parse_when():
    now = datetime(2026, 9, 25, 14, 30)
    assert parse_when("7d", now=now) == int(datetime(2026, 9, 18, 14, 30).timestamp())
    assert parse_when("hoje", now=now) == int(datetime(2026, 9, 25).timestamp())
    assert parse_when("ontem", now=now, end_of_day=True) == int(datetime(2026, 9, 25).timestamp())
    assert parse_when("2026-09-20", end_of_day=True) == int(datetime(2026, 9, 21).timestamp())
    assert parse_when("2026-09-20 08:41:30") == int(datetime(2026, 9, 20, 8, 41, 30).timestamp())
    with pytest.raises(ValueError):
        parse_when("semana passada")
