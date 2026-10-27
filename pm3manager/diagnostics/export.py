"""Relatório consultivo em JSON e em texto. A saída já entra sanitizada."""

from __future__ import annotations

import json

from pm3manager.diagnostics.models import (
    DISCLAIMER,
    ORIGIN_LABEL,
    SEVERITY_LABEL,
    DiagnosticReport,
    Severity,
)


def export_payload(report: DiagnosticReport) -> dict:
    groups = {
        "informacoes": [item.export() for item in report.checks_by_severity(Severity.INFO)],
        "verificacoes_aprovadas": [item.export() for item in report.checks_by_severity(Severity.PASS)],
        "avisos": [item.export() for item in report.checks_by_severity(Severity.WARNING)],
        "problemas_impeditivos": [item.export() for item in report.checks_by_severity(Severity.BLOCKING)],
        "desconhecidos": [item.export() for item in report.checks_by_severity(Severity.UNKNOWN)],
    }
    return {
        "disclaimer": DISCLAIMER,
        "generated_at": report.generated_at,
        "app_version": report.app_version,
        "mode": report.mode,
        "context_key": report.context_key,
        "verdict": report.verdict.value,
        "verdict_label": report.verdict_label,
        "summary": report.summary,
        "commands": list(report.commands),
        "cancelled": report.cancelled,
        "timed_out": report.timed_out,
        "client_attempted": report.client_attempted,
        "limitations": list(report.limitations),
        "facts": [item.export() for item in report.facts],
        "checks": groups,
        "technical": report.technical,
    }


def export_json(report: DiagnosticReport) -> str:
    return json.dumps(export_payload(report), ensure_ascii=False, indent=2)


def export_text(report: DiagnosticReport) -> str:
    lines = [
        "Proxmark3 Standalone Manager — diagnóstico",
        DISCLAIMER,
        f"Data: {report.generated_at}",
        f"Aplicativo: {report.app_version}",
        f"Resultado: {report.verdict_label}",
        f"Resumo: {report.summary}",
        "",
        "Fatos",
    ]
    for fact in report.facts:
        lines.append(f"- {fact.label}: {fact.value} [{ORIGIN_LABEL[fact.origin]}]")
        lines.append(f"  {fact.justification}")
    lines.append("")
    lines.append("Verificações")
    for check in report.checks:
        lines.append(f"- {SEVERITY_LABEL[check.severity]} — {check.title}: {check.message}")
    lines.append("")
    lines.append("Limitações")
    lines.extend(f"- {item}" for item in report.limitations)
    if report.commands:
        lines.append("")
        lines.append("Comandos: " + ", ".join(report.commands))
    return "\n".join(lines) + "\n"


def summary_text(report: DiagnosticReport) -> str:
    interesting = [
        fact
        for fact in report.facts
        if fact.key in {
            "port",
            "vidpid",
            "connection",
            "firmware_version",
            "bootrom_version",
            "mcu_detected",
            "family",
            "spi_detected",
            "module_id",
            "compile_mcu_support",
        }
    ]
    lines = [report.verdict_label, report.summary, ""]
    lines.extend(f"{fact.label}: {fact.value} ({ORIGIN_LABEL[fact.origin]})" for fact in interesting)
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)
