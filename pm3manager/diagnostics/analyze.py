"""Classifica uma coleta já feita. Não abre hardware e não grava arquivo."""

from __future__ import annotations

import re

from pm3manager.diagnostics.models import (
    DISCLAIMER,
    NOT_IDENTIFIED,
    NOT_VERIFIED,
    UNAVAILABLE,
    Check,
    DiagnosticReport,
    Fact,
    Observation,
    Origin,
    Severity,
    Verdict,
)
from pm3manager.diagnostics.sanitize import sanitize
from pm3manager.hardware.identity import parse_identity
from pm3manager.models import Compatibility, Device

_BOOT = re.compile(r"Bootrom\.+\s*(.+)", re.IGNORECASE)
_OS = re.compile(r"^\s*OS\.+\s*(.+)", re.MULTILINE)
_ARCH = re.compile(r"Architecture identifier:\s*(.+)", re.IGNORECASE)
_SRAM = re.compile(r"Internal SRAM size:\s*(.+)", re.IGNORECASE)
_EFLASH = re.compile(r"Embedded flash memory\s+(.+)", re.IGNORECASE)
_EMUL = re.compile(r"Emulator memory[:\.\s]+(\d+\s*bytes)", re.IGNORECASE)
_BIG = re.compile(r"BigBuf_size\.+\s*(\d+)", re.IGNORECASE)
_PING = re.compile(r"Ping response\s+received", re.IGNORECASE)
_DISCONNECT = (
    "could not find proxmark",
    "waiting for proxmark3",
    "no port found",
    "cannot communicate",
    "status command timeout",
)


def analyze(observation: Observation) -> DiagnosticReport:
    facts: list[Fact] = []
    checks: list[Check] = []
    limitations = [
        DISCLAIMER,
        "O diagnóstico não executa compilação, gravação, varredura RFID nem git pull.",
        "Uma característica declarada no Makefile não é tratada como presente no hardware.",
    ]
    if observation.blocked_reason:
        checks.append(
            Check(
                "ocupado",
                "Operação em andamento",
                Severity.WARNING,
                "Não foi possível iniciar o diagnóstico porque outra operação está em andamento. "
                "Compilação e gravação não foram interrompidas.",
                Origin.UNAVAILABLE,
                observation.blocked_reason,
            )
        )
        return _finish(observation, facts, checks, limitations, Verdict.INSUFFICIENT, "")

    _device_facts(observation, facts, checks)
    text = sanitize(observation.client_output, _secrets(observation.selected))
    parsed = _parse_client(observation, text, facts, checks)
    _environment(observation, facts, checks)
    verdict = _compatibility(observation, parsed, facts, checks, limitations)
    summary = _summary(observation, parsed, verdict)
    technical = ""
    if observation.client_attempted and not observation.client_timed_out and not observation.client_cancelled:
        technical = text
    return _finish(
        observation,
        facts,
        checks,
        limitations,
        verdict,
        technical,
        summary=summary,
    )


def _finish(
    observation: Observation,
    facts: list[Fact],
    checks: list[Check],
    limitations: list[str],
    verdict: Verdict,
    technical: str,
    summary: str = "",
) -> DiagnosticReport:
    if not summary:
        summary = "O diagnóstico não foi executado."
    return DiagnosticReport(
        generated_at=observation.generated_at,
        app_version=observation.app_version,
        mode=observation.mode,
        context_key=_context_key(observation),
        verdict=verdict,
        summary=summary,
        facts=facts,
        checks=checks,
        limitations=limitations,
        commands=observation.commands,
        technical=technical,
        cancelled=observation.client_cancelled,
        timed_out=observation.client_timed_out,
        client_attempted=observation.client_attempted,
    )


def _secrets(device: Device | None) -> tuple[str, ...]:
    if device is None or not device.serial_number:
        return ()
    return (device.serial_number,)


def _context_key(observation: Observation) -> str:
    device = observation.selected
    module_id = observation.module.id if observation.module else ""
    if device is None:
        port, vid, pid = "", "", ""
    else:
        port = device.port
        vid = f"{device.vid:04X}" if device.vid is not None else ""
        pid = f"{device.pid:04X}" if device.pid is not None else ""
    return "|".join((port, vid, pid, module_id, observation.git_commit, observation.version_token))


def _add(facts: list[Fact], key: str, label: str, value: str, origin: Origin, why: str) -> None:
    facts.append(Fact(key, label, value, origin, why))


def _check(
    checks: list[Check],
    code: str,
    title: str,
    severity: Severity,
    message: str,
    origin: Origin,
    why: str,
) -> None:
    checks.append(Check(code, title, severity, message, origin, why))


def _device_facts(observation: Observation, facts: list[Fact], checks: list[Check]) -> None:
    device = observation.selected
    if device is None:
        _add(
            facts,
            "connection",
            "Estado da conexão",
            "Desconectado",
            Origin.DETECTED,
            "A enumeração USB/serial não encontrou um Proxmark3 selecionado.",
        )
        _check(
            checks,
            "disconnected",
            "Nenhum Proxmark3 selecionado",
            Severity.INFO,
            "Não há dispositivo conectado para esta leitura. Isso não indica defeito.",
            Origin.DETECTED,
            "Lista de portas classificadas pelo detector existente.",
        )
        return
    vid = f"{device.vid:04X}" if device.vid is not None else NOT_IDENTIFIED
    pid = f"{device.pid:04X}" if device.pid is not None else NOT_IDENTIFIED
    _add(facts, "port", "Porta COM", device.port, Origin.DETECTED, "Porta enumerada pelo Windows.")
    _add(
        facts,
        "vidpid",
        "VID/PID USB",
        f"{vid}:{pid}",
        Origin.DETECTED,
        device.reason or "Identificadores USB da porta enumerada.",
    )
    _add(
        facts,
        "usb_name",
        "Nome e descrição USB",
        " — ".join(part for part in (device.hardware_name, device.description) if part) or NOT_IDENTIFIED,
        Origin.DETECTED,
        "Texto informado pela enumeração serial. Não é o modelo físico confirmado pelo firmware.",
    )
    _add(
        facts,
        "usb_confidence",
        "Confiança da enumeração",
        device.confidence.value,
        Origin.DETECTED,
        device.reason,
    )
    if observation.port_free is False:
        _check(
            checks,
            "port_busy",
            "Porta COM ocupada",
            Severity.WARNING,
            observation.port_message or f"A porta {device.port} está em uso. O cliente não foi aberto.",
            Origin.DETECTED,
            "A porta foi testada sem mantê-la aberta. Nenhum acesso concorrente foi forçado.",
        )
    elif observation.port_free is True:
        _check(
            checks,
            "port_free",
            "Porta COM livre",
            Severity.PASS,
            f"A porta {device.port} pôde ser aberta e foi fechada em seguida.",
            Origin.DETECTED,
            "Teste de ocupação existente, sem sessão permanente.",
        )


def _parse_client(observation: Observation, text: str, facts: list[Fact], checks: list[Check]) -> dict:
    attempted = observation.client_attempted
    usable = attempted and not observation.client_timed_out and not observation.client_cancelled
    result = {
        "usable": usable,
        "communication_ok": False,
        "kind": "",
        "mcu": "",
        "embedded": "",
        "external_flash": "",
        "version_mismatch": False,
        "family_explicit": False,
    }
    if observation.mode == "refresh" and not attempted:
        why = observation.client_error or (
            "Atualizar informações não consulta o cliente e não reaproveita leitura antiga como detecção."
        )
        _add(facts, "client", "Cliente Proxmark3", NOT_VERIFIED, Origin.UNVERIFIED, why)
        _unverified_client(facts, why)
        return result
    if observation.client_cancelled:
        _check(
            checks,
            "cancelled",
            "Diagnóstico cancelado",
            Severity.INFO,
            "A leitura foi cancelada. Trechos parciais não entram como detecção.",
            Origin.UNAVAILABLE,
            "O cancelamento encerra o processo filho.",
        )
        _unverified_client(facts, "Cancelado antes de uma leitura utilizável.")
        return result
    if observation.client_timed_out:
        _check(
            checks,
            "timeout",
            "Tempo esgotado",
            Severity.WARNING,
            "O cliente não respondeu dentro do tempo limite. O processo filho foi encerrado.",
            Origin.UNAVAILABLE,
            observation.client_error or "Timeout da execução segura.",
        )
        _unverified_client(facts, "A leitura expirou. Texto parcial não é tratado como detecção.")
        return result
    if not attempted:
        why = observation.client_error or "O cliente não foi executado."
        _add(facts, "client", "Cliente Proxmark3", NOT_VERIFIED, Origin.UNVERIFIED, why)
        _unverified_client(facts, why)
        return result

    lowered = text.lower()
    disconnected = any(token in lowered for token in _DISCONNECT)
    identity = parse_identity(text, exit_code=observation.client_exit, expected_version=observation.version_file)
    has_hardware = bool(_first(_BOOT, text) or _first(_OS, text) or identity.mcu or "uc:" in lowered)
    if disconnected and not has_hardware:
        _check(
            checks,
            "disconnected_during_read",
            "Dispositivo sem resposta",
            Severity.WARNING,
            "A porta deixou de responder durante a leitura. Isso não classifica o aparelho como defeituoso.",
            Origin.DETECTED,
            "A resposta contém um aviso de comunicação e não trouxe identificação de hardware.",
        )
        _unverified_client(facts, "Sem resposta utilizável do cliente.")
        return result

    result["communication_ok"] = bool(identity.communication_ok and has_hardware)
    result["version_mismatch"] = bool(identity.version_mismatch)
    result["mcu"] = identity.mcu
    kind = identity.firmware_kind
    explicit = kind in {"RDV4", "PM3 GENERIC"}
    result["kind"] = kind if explicit else ""
    result["family_explicit"] = explicit
    result["embedded"] = _clean(_first(_EFLASH, text))
    result["external_flash"] = identity.external_flash if identity.external_flash not in {"", "não informado"} else ""

    _line(facts, "client_version", "Versão do cliente", _client_line(text), usable)
    _line(facts, "firmware_version", "Versão de firmware", _clean(_first(_OS, text)), usable)
    _line(facts, "bootrom_version", "Versão de bootrom", _clean(_first(_BOOT, text)), usable)
    if explicit:
        _add(
            facts,
            "family",
            "Família informada pelo cliente",
            kind,
            Origin.DETECTED,
            "Texto de hw version/hw status. Não foi deduzido do Makefile.",
        )
    else:
        _add(
            facts,
            "family",
            "Família informada pelo cliente",
            NOT_IDENTIFIED,
            Origin.UNVERIFIED,
            "A resposta não nomeou PM3 GENERIC nem RDV4. Firmware desconhecido não é incompatibilidade.",
        )
        _check(
            checks,
            "firmware_unknown",
            "Firmware não identificado",
            Severity.UNKNOWN,
            "A família do firmware não foi identificada. Ela não foi classificada como incompatível.",
            Origin.UNVERIFIED,
            "Ausência de PM3 GENERIC ou RDV4 na resposta.",
        )
    if identity.mcu:
        _add(
            facts,
            "mcu_detected",
            "MCU físico informado pelo cliente",
            identity.mcu,
            Origin.DETECTED,
            "Linha uC de hw version. Não vem do Makefile.",
        )
    else:
        _add(
            facts,
            "mcu_detected",
            "MCU físico informado pelo cliente",
            NOT_IDENTIFIED,
            Origin.UNVERIFIED,
            "hw version não trouxe a linha uC.",
        )
    _line(facts, "architecture", "Arquitetura informada", _clean(_first(_ARCH, text)), usable)
    _line(facts, "sram", "SRAM interna", _clean(_first(_SRAM, text)), usable)
    _line(facts, "embedded_flash", "Flash interna", result["embedded"], usable)
    flash = identity.external_flash if identity.external_flash not in {"", "não informado"} else ""
    if flash:
        size = f" {identity.external_flash_size}" if identity.external_flash_size else ""
        _add(
            facts,
            "spi_detected",
            "Flash SPI informada pelo cliente",
            f"{flash}{size}".strip(),
            Origin.DETECTED,
            "hw version/hw status. PLATFORM_EXTRAS não entra nesta conclusão.",
        )
    else:
        _add(
            facts,
            "spi_detected",
            "Flash SPI informada pelo cliente",
            NOT_IDENTIFIED,
            Origin.UNVERIFIED,
            "A resposta não informou flash externa.",
        )
    _line(facts, "emulator_memory", "Memória do emulador", _clean(_first(_EMUL, text)), usable)
    big = _clean(_first(_BIG, text))
    _line(facts, "bigbuf", "BigBuf disponível", f"{big} bytes" if big else "", usable)
    if identity.smartcard:
        _add(facts, "smartcard", "Leitor de smartcard", identity.smartcard, Origin.DETECTED, "hw status.")
    else:
        _add(facts, "smartcard", "Leitor de smartcard", NOT_IDENTIFIED, Origin.UNVERIFIED, "hw status não informou.")
    if identity.bt_addon:
        _add(facts, "bt_addon", "Add-on Bluetooth", identity.bt_addon, Origin.DETECTED, "hw status.")
    else:
        _add(facts, "bt_addon", "Add-on Bluetooth", NOT_IDENTIFIED, Origin.UNVERIFIED, "hw status não informou.")
    if identity.standalone_banner:
        _add(
            facts,
            "standalone_banner",
            "Texto de modo Standalone",
            identity.standalone_banner,
            Origin.DETECTED,
            "O firmware mostrou esse texto. Ele não comprova o módulo compilado.",
        )
    else:
        _add(
            facts,
            "standalone_banner",
            "Texto de modo Standalone",
            NOT_IDENTIFIED,
            Origin.UNVERIFIED,
            "hw version e hw status não informaram o modo.",
        )
    ping = "respondeu" if _PING.search(text) else ""
    _line(facts, "ping", "hw ping", ping, usable)
    client_line = _client_line(text)
    os_line = _clean(_first(_OS, text))
    if client_line and os_line and _norm(client_line) != _norm(os_line):
        _check(
            checks,
            "client_firmware_diverge",
            "Cliente e firmware divergem",
            Severity.WARNING,
            "A linha do cliente e a linha OS do dispositivo não são iguais.",
            Origin.DETECTED,
            f"Cliente: {client_line}. OS: {os_line}.",
        )
    elif client_line and os_line:
        _check(
            checks,
            "client_firmware_match",
            "Cliente e firmware na mesma leitura",
            Severity.PASS,
            "A linha do cliente e a linha OS coincidem nesta resposta.",
            Origin.DETECTED,
            "Comparação textual das duas linhas, sem inferir o modelo da placa.",
        )
    if not _clean(_first(_BOOT, text)):
        _check(
            checks,
            "bootrom_missing",
            "Bootrom não identificada",
            Severity.UNKNOWN,
            "A resposta não trouxe a linha Bootrom. Isso não é tratado como falha do aparelho.",
            Origin.UNVERIFIED,
            "Regex da linha Bootrom não encontrou valor.",
        )
    if result["communication_ok"]:
        _check(
            checks,
            "communication",
            "Comunicação com o cliente",
            Severity.PASS,
            "O cliente devolveu uma resposta utilizável.",
            Origin.DETECTED,
            identity.summary,
        )
    else:
        _check(
            checks,
            "communication",
            "Comunicação incompleta",
            Severity.WARNING,
            "A resposta do cliente ficou incompleta ou não foi confirmada.",
            Origin.UNVERIFIED,
            identity.summary or observation.client_error,
        )
    if observation.version_file and identity.version_mismatch and identity.communication_ok:
        _check(
            checks,
            "version_unknown",
            "Versão de firmware não confirmada",
            Severity.UNKNOWN,
            "A versão do arquivo local não apareceu na resposta, ou o cliente avisou divergência. "
            "Isso não é classificado automaticamente como incompatível.",
            Origin.UNVERIFIED,
            observation.version_file,
        )
    return result


def _unverified_client(facts: list[Fact], why: str) -> None:
    for key, label in (
        ("client_version", "Versão do cliente"),
        ("firmware_version", "Versão de firmware"),
        ("bootrom_version", "Versão de bootrom"),
        ("family", "Família informada pelo cliente"),
        ("mcu_detected", "MCU físico informado pelo cliente"),
        ("architecture", "Arquitetura informada"),
        ("sram", "SRAM interna"),
        ("embedded_flash", "Flash interna"),
        ("spi_detected", "Flash SPI informada pelo cliente"),
        ("emulator_memory", "Memória do emulador"),
        ("bigbuf", "BigBuf disponível"),
        ("smartcard", "Leitor de smartcard"),
        ("bt_addon", "Add-on Bluetooth"),
        ("standalone_banner", "Texto de modo Standalone"),
        ("ping", "hw ping"),
    ):
        if any(item.key == key for item in facts):
            continue
        _add(facts, key, label, NOT_VERIFIED, Origin.UNVERIFIED, why)


def _line(facts: list[Fact], key: str, label: str, value: str, usable: bool) -> None:
    if value:
        _add(facts, key, label, value, Origin.DETECTED, "Extraído da resposta sanitizada do cliente.")
        return
    _add(
        facts,
        key,
        label,
        NOT_IDENTIFIED if usable else NOT_VERIFIED,
        Origin.UNVERIFIED,
        "A resposta não trouxe esse campo." if usable else "Leitura não concluída.",
    )


def _environment(observation: Observation, facts: list[Fact], checks: list[Check]) -> None:
    if not observation.env_present or not observation.proxspace_present:
        _add(
            facts,
            "proxspace",
            "ProxSpace",
            UNAVAILABLE,
            Origin.UNAVAILABLE,
            "O diretório ProxSpace não estava disponível para leitura.",
        )
        _check(
            checks,
            "proxspace_missing",
            "ProxSpace ausente",
            Severity.WARNING,
            "Sem ProxSpace não é possível confirmar o ambiente de compilação. O dispositivo não foi marcado como defeituoso.",
            Origin.UNAVAILABLE,
            "Leitura do sistema de arquivos, sem instalar nem alterar o ProxSpace.",
        )
    else:
        _add(
            facts,
            "proxspace",
            "ProxSpace",
            "Diretório encontrado",
            Origin.DETECTED,
            "runme64.bat e o shell MSYS foram localizados. O caminho completo do perfil não entra no relatório.",
        )
        _check(
            checks,
            "proxspace_present",
            "ProxSpace encontrado",
            Severity.PASS,
            "Os arquivos essenciais do ProxSpace informados abaixo foram apenas lidos.",
            Origin.DETECTED,
            "Nenhum script de instalação foi executado.",
        )
    if observation.checkout_present:
        _add(
            facts,
            "checkout",
            "Checkout Iceman",
            observation.checkout_name or "Encontrado",
            Origin.DETECTED,
            "Diretório do checkout selecionado.",
        )
    else:
        _add(facts, "checkout", "Checkout Iceman", UNAVAILABLE, Origin.UNAVAILABLE, "Checkout não encontrado.")
        _check(
            checks,
            "checkout_missing",
            "Checkout ausente",
            Severity.WARNING,
            "O checkout Iceman não pôde ser lido.",
            Origin.UNAVAILABLE,
            "Verificação somente leitura.",
        )
    _add(
        facts,
        "version_file",
        "Versão no arquivo do checkout",
        observation.version_file or NOT_VERIFIED,
        Origin.DOCUMENTED if observation.version_file else Origin.UNVERIFIED,
        "Terceiro campo de common/default_version_pm3.c. Não é o Git HEAD.",
    )
    _add(
        facts,
        "version_token",
        "Identificador no arquivo de versão",
        observation.version_token or NOT_VERIFIED,
        Origin.DOCUMENTED if observation.version_token else Origin.UNVERIFIED,
        "Identificador gravado na árvore, distinto do commit Git.",
    )
    for name, present in observation.essential.items():
        _add(
            facts,
            f"file:{name}",
            f"Arquivo {name}",
            "presente" if present else "ausente",
            Origin.DETECTED if present else Origin.UNAVAILABLE,
            "Existência conferida sem abrir o arquivo para edição.",
        )
        if not present:
            _check(
                checks,
                f"missing:{name}",
                f"{name} ausente",
                Severity.WARNING,
                f"O arquivo essencial {name} não foi encontrado.",
                Origin.UNAVAILABLE,
                "Leitura de existência.",
            )
    if observation.toolchain_found is True:
        _add(
            facts,
            "toolchain",
            "Ferramentas de compilação",
            "arm-none-eabi-gcc encontrado",
            Origin.DETECTED,
            "O arquivo foi localizado. O compilador não foi executado e nenhuma compilação foi iniciada.",
        )
    elif observation.toolchain_found is False:
        _add(
            facts,
            "toolchain",
            "Ferramentas de compilação",
            UNAVAILABLE,
            Origin.UNAVAILABLE,
            "arm-none-eabi-gcc não apareceu nos caminhos conhecidos do ProxSpace.",
        )
        _check(
            checks,
            "toolchain_missing",
            "Toolchain não encontrada",
            Severity.WARNING,
            "O compilador não foi localizado nos caminhos conhecidos. Nenhuma compilação foi tentada.",
            Origin.UNAVAILABLE,
            "Busca somente leitura.",
        )
    _git(observation, facts, checks)
    _makefile(observation, facts, checks)
    _preferences(observation, facts, checks)


def _git(observation: Observation, facts: list[Fact], checks: list[Check]) -> None:
    if observation.git_state == "repo":
        _add(
            facts,
            "git_commit",
            "Commit Git do checkout",
            observation.git_commit or NOT_IDENTIFIED,
            Origin.DETECTED if observation.git_commit else Origin.UNVERIFIED,
            "git rev-parse HEAD, somente leitura.",
        )
        if observation.git_shallow is True:
            _add(facts, "git_shallow", "Clone Git", "raso", Origin.DETECTED, "git rev-parse --is-shallow-repository.")
            _check(
                checks,
                "shallow",
                "Checkout raso",
                Severity.INFO,
                "O clone é raso. O histórico completo não está disponível e não foi baixado.",
                Origin.DETECTED,
                "Nenhum fetch foi executado.",
            )
        elif observation.git_shallow is False:
            _add(facts, "git_shallow", "Clone Git", "completo", Origin.DETECTED, "git rev-parse --is-shallow-repository.")
        if observation.git_dirty is True:
            _add(
                facts,
                "git_dirty",
                "Árvore de trabalho",
                f"modificada ({observation.git_dirty_count} caminhos)",
                Origin.DETECTED,
                "git status --porcelain. Os caminhos não são listados no relatório.",
            )
            _check(
                checks,
                "dirty",
                "Checkout com alterações locais",
                Severity.INFO,
                "Há alterações locais. O diagnóstico não as desfaz.",
                Origin.DETECTED,
                "Somente leitura.",
            )
        elif observation.git_dirty is False:
            _add(facts, "git_dirty", "Árvore de trabalho", "limpa", Origin.DETECTED, "git status --porcelain.")
    elif observation.git_state == "not_repo":
        _add(facts, "git_commit", "Commit Git do checkout", UNAVAILABLE, Origin.UNAVAILABLE, "O diretório não é um repositório Git.")
        _check(
            checks,
            "not_git",
            "Checkout não Git",
            Severity.INFO,
            "Não há repositório Git neste checkout. Nenhum comando Git de alteração foi executado.",
            Origin.UNAVAILABLE,
            "git rev-parse --is-inside-work-tree falhou.",
        )
    else:
        _add(facts, "git_commit", "Commit Git do checkout", NOT_VERIFIED, Origin.UNVERIFIED, "O Git não pôde ser consultado.")


def _makefile(observation: Observation, facts: list[Fact], checks: list[Check]) -> None:
    if observation.makefile_present is False:
        _add(
            facts,
            "makefile_platform",
            "PLATFORM no Makefile.platform",
            "arquivo ausente",
            Origin.CONFIGURED,
            "Sem esse arquivo o make desta árvore volta ao padrão PM3RDV4. O diagnóstico não criou o arquivo.",
        )
        _check(
            checks,
            "makefile_absent",
            "Makefile.platform ausente",
            Severity.WARNING,
            "O arquivo efetivo não existe. Isso não foi corrigido automaticamente.",
            Origin.CONFIGURED,
            "Leitura do checkout. Nenhuma escrita.",
        )
    found = observation.makefile or {}

    def configured(key: str, label: str) -> str:
        values = found.get(key) or []
        if not values:
            return "não declarado neste arquivo" if observation.makefile_present else "não lido"
        return " ".join(values)

    for key, label in (
        ("PLATFORM", "PLATFORM no arquivo"),
        ("PLATFORM_EXTRAS", "PLATFORM_EXTRAS no arquivo"),
        ("STANDALONE", "STANDALONE no arquivo"),
        ("LED_ORDER", "LED_ORDER no arquivo"),
        ("PLATFORM_SIZE", "PLATFORM_SIZE no arquivo"),
    ):
        _add(
            facts,
            f"file_{key.lower()}",
            label,
            configured(key, label),
            Origin.CONFIGURED,
            "Atribuição ativa em Makefile.platform. Não é medição do hardware.",
        )
    _add(
        facts,
        "intended_platform",
        "Plataforma que o aplicativo compilaria",
        observation.intended_platform or NOT_VERIFIED,
        Origin.CONFIGURED,
        "Regra atual do aplicativo: somente PM3GENERIC. O diagnóstico não compilou.",
    )
    _add(
        facts,
        "intended_standalone",
        "Módulo que o aplicativo compilaria",
        observation.intended_standalone or "nenhum selecionado",
        Origin.CONFIGURED,
        "Módulo selecionado na interface. Não é o modo detectado no dispositivo.",
    )
    _add(
        facts,
        "intended_extras",
        "PLATFORM_EXTRAS que o aplicativo compilaria",
        observation.intended_extras or "nenhum",
        Origin.CONFIGURED,
        "Depende da confirmação de flash SPI já salva. Não liga FLASH sozinho.",
    )
    _add(
        facts,
        "intended_led",
        "LED_ORDER que o aplicativo compilaria",
        observation.intended_led_order or NOT_VERIFIED,
        Origin.CONFIGURED,
        "PM3GENERIC com LED_ORDER=PM3EASY seleciona suporte AT91SAM7S no make. Não identifica o MCU físico.",
    )
    _add(
        facts,
        "compile_mcu_support",
        "MCU configurado pela compilação",
        "suporte AT91SAM7S declarado por LED_ORDER=PM3EASY" if observation.intended_led_order == "PM3EASY" else NOT_VERIFIED,
        Origin.DOCUMENTED,
        "Metadado conhecido da plataforma deste aplicativo. Não identifica o MCU físico nem a placa como Easy.",
    )
    _add(
        facts,
        "intended_size",
        "PLATFORM_SIZE que o aplicativo compilaria",
        observation.intended_platform_size or "não definido",
        Origin.CONFIGURED,
        "Calculado das preferências já salvas, não da leitura desta sessão.",
    )
    disk_platform = " ".join(found.get("PLATFORM") or [])
    if disk_platform and observation.intended_platform and disk_platform != observation.intended_platform:
        _check(
            checks,
            "platform_diverge",
            "Plataforma do arquivo difere da compilação do aplicativo",
            Severity.WARNING,
            f"O arquivo declara {disk_platform}. O aplicativo compilaria {observation.intended_platform}. "
            "O arquivo não foi alterado.",
            Origin.CONFIGURED,
            "Comparação entre Makefile.platform e a configuração do aplicativo.",
        )


def _preferences(observation: Observation, facts: list[Fact], checks: list[Check]) -> None:
    _add(
        facts,
        "prefs_mcu",
        "MCU guardado na preferência",
        observation.prefs_mcu or "nenhum",
        Origin.CONFIGURED,
        "Leitura anterior salva. Não confirma o aparelho conectado agora.",
    )
    _add(
        facts,
        "prefs_kind",
        "Família guardada na preferência",
        observation.prefs_firmware_kind or "nenhuma",
        Origin.CONFIGURED,
        "Preferência local. Não é a resposta desta sessão.",
    )
    _add(
        facts,
        "prefs_spi",
        "Flash SPI guardada na preferência",
        observation.prefs_external_flash or "nenhuma",
        Origin.CONFIGURED,
        "Preferência local, distinta da linha lida agora no cliente.",
    )
    _add(
        facts,
        "spi_confirmed_pref",
        "Confirmação de flash SPI na interface",
        "marcada" if observation.spi_confirmed else "desmarcada",
        Origin.CONFIGURED,
        "Caixa de confirmação do usuário. Não prova a peça.",
    )
    detected = next((item.value for item in facts if item.key == "mcu_detected" and item.origin is Origin.DETECTED), "")
    if detected and observation.prefs_mcu and _norm(detected) != _norm(observation.prefs_mcu):
        _check(
            checks,
            "mcu_pref_diverge",
            "MCU detectado diferente do valor guardado",
            Severity.WARNING,
            "A leitura atual e a preferência não coincidem. A preferência não foi atualizada por este diagnóstico.",
            Origin.DETECTED,
            f"Detectado: {detected}. Configurado: {observation.prefs_mcu}.",
        )


def _compatibility(
    observation: Observation,
    parsed: dict,
    facts: list[Fact],
    checks: list[Check],
    limitations: list[str],
) -> Verdict:
    module = observation.module
    if module is None:
        _check(
            checks,
            "module_missing",
            "Nenhum módulo selecionado",
            Severity.INFO,
            "Sem módulo selecionado a compatibilidade fica sem esse lado da comparação.",
            Origin.CONFIGURED,
            "Nenhuma ficha foi escolhida.",
        )
        return Verdict.INSUFFICIENT
    _add(
        facts,
        "module_id",
        "Módulo selecionado",
        module.id,
        Origin.CONFIGURED,
        "Seleção da interface. Não é o modo detectado no firmware.",
    )
    _add(
        facts,
        "module_class",
        "Classificação já usada pelo aplicativo",
        module.compatibility.value,
        Origin.CONFIGURED,
        "Classificação existente do catálogo. O diagnóstico não a substitui nem a relaxa.",
    )
    if module.compatibility is Compatibility.INCOMPATIBLE or module.rdv4_only or module.requires_bt or module.requires_smartcard or "_RDV4" in module.id:
        _check(
            checks,
            "module_incompatible",
            "Módulo incompatível com a compilação deste aplicativo",
            Severity.BLOCKING,
            "O catálogo já impede este módulo em PM3GENERIC. O diagnóstico não libera a compilação.",
            Origin.DOCUMENTED,
            "Makefile.hal ou identificador exclusivo, reutilizado do catálogo.",
        )
        return Verdict.INCOMPATIBLE
    if parsed.get("kind") == "RDV4":
        _check(
            checks,
            "rdv4_device",
            "Dispositivo informou RDV4",
            Severity.BLOCKING,
            "O cliente informou RDV4. A imagem PM3GENERIC deste aplicativo não é gravada nesse caso. O aparelho não foi marcado como defeituoso.",
            Origin.DETECTED,
            "Texto de firmware. A gravação existente continua bloqueada.",
        )
        return Verdict.INCOMPATIBLE
    embedded = parsed.get("embedded") or ""
    mcu = parsed.get("mcu") or ""
    small = ("256" in mcu or "256" in embedded) and "512" not in mcu and "512" not in embedded
    large = "512" in mcu or "512" in embedded
    if large and observation.intended_platform_size == "256":
        _check(
            checks,
            "size_conflict",
            "Tamanho configurado diverge da flash interna lida",
            Severity.BLOCKING,
            "A leitura mostra 512 KB e a configuração que seria compilada pede PLATFORM_SIZE=256. Não grave essa imagem.",
            Origin.DETECTED,
            "Comparação entre hw version e a preferência. O Makefile não foi modificado.",
        )
        return Verdict.INCOMPATIBLE
    if small and observation.intended_platform_size != "256":
        _check(
            checks,
            "size_small",
            "MCU de 256 KB sem PLATFORM_SIZE=256 na configuração atual",
            Severity.WARNING,
            "A leitura mostra 256 KB. A preferência atual não força PLATFORM_SIZE=256. O diagnóstico não alterou a preferência.",
            Origin.DETECTED,
            "A gravação existente pode recusar essa combinação.",
        )
    flash_state = parsed.get("external_flash") or ""
    if module.requires_flash and flash_state == "ausente":
        _check(
            checks,
            "spi_absent",
            "Módulo exige flash SPI e o cliente informou ausência",
            Severity.BLOCKING,
            "O Makefile exige WITH_FLASH e a leitura informou flash externa ausente.",
            Origin.DETECTED,
            "STANDALONE_MODES_REQ_FLASH do catálogo e hw status.",
        )
        return Verdict.INCOMPATIBLE
    if module.requires_flash and flash_state != "presente":
        _check(
            checks,
            "spi_unknown",
            "Requisito de flash SPI sem confirmação na leitura",
            Severity.UNKNOWN,
            "O módulo exige flash SPI e esta leitura não confirmou a peça. A compilação existente continua pedindo a confirmação da interface.",
            Origin.UNVERIFIED,
            "Req FLASH conhecido; presença física não verificada.",
        )
        return Verdict.NEEDS_CONFIRMATION
    if module.compatibility is Compatibility.REQUIRES_FLASH and not observation.spi_confirmed:
        _check(
            checks,
            "spi_pref",
            "Flash detectada, confirmação da interface desmarcada",
            Severity.WARNING,
            "A proteção de compilação continua exigindo a caixa de flash SPI. O diagnóstico não a marcou.",
            Origin.CONFIGURED,
            "Preferência spi_flash_confirmada desligada.",
        )
    if module.compatibility is Compatibility.UNCERTAIN and not observation.module_confirmed_uncertain:
        _check(
            checks,
            "module_uncertain",
            "Módulo com compatibilidade incerta",
            Severity.UNKNOWN,
            "O catálogo já pede confirmação manual. O diagnóstico não confirma o módulo sozinho.",
            Origin.CONFIGURED,
            "Compatibility.UNCERTAIN existente.",
        )
        return Verdict.NEEDS_CONFIRMATION
    if observation.client_cancelled or observation.client_timed_out:
        return Verdict.INSUFFICIENT
    if not parsed.get("communication_ok"):
        if observation.selected is None:
            return Verdict.INSUFFICIENT
        if observation.port_free is False:
            return Verdict.NEEDS_CONFIRMATION
        return Verdict.INSUFFICIENT
    if not parsed.get("family_explicit"):
        limitations.append("A família do firmware não foi nomeada pelo cliente. A compatibilidade não foi fechada.")
        return Verdict.PARTIAL
    warnings = [item for item in checks if item.severity in {Severity.WARNING, Severity.UNKNOWN, Severity.BLOCKING}]
    if warnings:
        return Verdict.PARTIAL
    _check(
        checks,
        "module_fit",
        "Módulo dentro das verificações disponíveis",
        Severity.PASS,
        "Nenhuma incompatibilidade foi identificada entre o dispositivo lido, a plataforma e o módulo. Isso não é certificação.",
        Origin.INFERRED,
        "Conjunto das verificações desta execução. Não inclui teste de rádio.",
    )
    return Verdict.COMPATIBLE


def _summary(observation: Observation, parsed: dict, verdict: Verdict) -> str:
    module = observation.module.id if observation.module else "nenhum módulo"
    port = observation.selected.port if observation.selected else "sem dispositivo"
    return f"{port}; {module}; {verdict.value}."


def _client_line(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "[ client ]" in line.lower():
            for follow in lines[index + 1:index + 6]:
                cleaned = follow.strip()
                if cleaned and not cleaned.startswith("["):
                    return cleaned
    return ""


def _first(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("[#]", "")).strip(" []")


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").casefold().strip()
