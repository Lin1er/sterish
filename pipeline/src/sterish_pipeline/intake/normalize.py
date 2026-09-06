"""Normalize the three shapes a skill arrives in into one `SkillManifest`.

A skill reaches Sterish as one of:

* an **Agent Skill** — `SKILL.md`, optionally with YAML frontmatter, plus
  companion markdown files (this is what skills.stellar.org publishes);
* an **MCP server manifest** — the JSON blob that goes in an agent's MCP config,
  carrying server commands and tool definitions;
* **raw source** — a directory that is neither of the above.

Everything downstream (`content_hash`, the audit stages, on-chain submission)
works off the normalized manifest, so this module is the single place that has
to know about source formats.

Capabilities are only ever *declared*, never invented. A markdown skill that
declares nothing gets `tools=[]`, and its risk comes from the text scanner
rather than from a capability we guessed at.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sterish_pipeline.models import Capability, SkillManifest, ToolDef


class SourceKind(StrEnum):
    AGENT_SKILL = "agent-skill"
    MCP_SERVER = "mcp-server"
    RAW_SOURCE = "raw-source"


class NormalizationError(ValueError):
    """The source could not be turned into a manifest."""


@dataclass(frozen=True)
class NormalizedSkill:
    """A manifest plus the bytes it was derived from."""

    manifest: SkillManifest
    kind: SourceKind
    files: dict[str, bytes]
    #: Text spans that are content but live outside the manifest fields —
    #: markdown bodies, MCP env blocks. The injection scanner reads these too.
    extra_text: dict[str, str]


_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)

# A permission string in an MCP/agent manifest mapped to the capability it
# implies. Anything unrecognised is kept as a permission but grants nothing.
_PERMISSION_CAPABILITIES: dict[str, tuple[Capability, ...]] = {
    "wallet": (Capability.WALLET_ACCESS,),
    "wallet_access": (Capability.WALLET_ACCESS,),
    "keys": (Capability.SECRET_READ,),
    "secrets": (Capability.SECRET_READ,),
    "credentials": (Capability.SECRET_READ,),
    "env": (Capability.ENV_READ,),
    "environment": (Capability.ENV_READ,),
    "network": (Capability.NETWORK_OUTBOUND,),
    "net": (Capability.NETWORK_OUTBOUND,),
    "http": (Capability.NETWORK_OUTBOUND,),
    "fetch": (Capability.NETWORK_OUTBOUND,),
    "fs": (Capability.FILE_READ, Capability.FILE_WRITE),
    "filesystem": (Capability.FILE_READ, Capability.FILE_WRITE),
    "file_read": (Capability.FILE_READ,),
    "read": (Capability.FILE_READ,),
    "file_write": (Capability.FILE_WRITE,),
    "write": (Capability.FILE_WRITE,),
}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split leading YAML frontmatter from the markdown body.

    Deliberately a minimal `key: value` reader rather than a YAML parser: skill
    frontmatter in the wild is flat, and pulling in a YAML engine to read
    untrusted files buys an attack surface for no benefit.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text

    fields: dict[str, str] = {}
    key: str | None = None
    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and key:
            # Continuation of the previous folded value.
            fields[key] = f"{fields[key]} {line.strip()}".strip()
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key] = value

    return fields, text[match.end() :]


def _capabilities_from_permissions(permissions: list[str]) -> list[Capability]:
    found: list[Capability] = []
    for permission in permissions:
        for capability in _PERMISSION_CAPABILITIES.get(permission.strip().lower(), ()):
            if capability not in found:
                found.append(capability)
    return found


def _coerce_capabilities(raw: Any) -> list[Capability]:
    """Accept declared capabilities, dropping anything not in the taxonomy."""
    if not isinstance(raw, list):
        return []
    out: list[Capability] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        try:
            capability = Capability(item.strip().upper())
        except ValueError:
            continue
        if capability not in out:
            out.append(capability)
    return out


def _first_paragraph(body: str) -> str:
    for block in body.split("\n\n"):
        stripped = block.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return " ".join(stripped.split())
    return ""


def normalize_agent_skill(
    skill_id: str,
    version: str,
    files: dict[str, bytes],
    entry: str = "SKILL.md",
) -> NormalizedSkill:
    """Normalize a `SKILL.md`-style Agent Skill."""
    if entry not in files:
        markdown = sorted(p for p in files if p.lower().endswith(".md"))
        if not markdown:
            raise NormalizationError(f"no markdown entry point found (looked for {entry})")
        entry = markdown[0]

    text = files[entry].decode("utf-8", errors="replace")
    fields, body = parse_frontmatter(text)

    name = fields.get("name") or ""
    if not name:
        heading = _H1.search(body)
        name = heading.group(1).strip() if heading else skill_id

    description = fields.get("description") or _first_paragraph(body)

    permissions = [
        p.strip() for p in re.split(r"[,\s]+", fields.get("permissions", "")) if p.strip()
    ]

    # A documentation skill declares no tools. That is a real answer, not a gap:
    # its risk lives in the prose, which the injection scanner reads.
    tools: list[ToolDef] = []
    capabilities = _capabilities_from_permissions(permissions)
    if capabilities:
        tools.append(
            ToolDef(
                name=fields.get("name") or skill_id,
                description=description,
                input_schema={},
                capabilities=capabilities,
            )
        )

    extra_text = {
        f"file:{path}": data.decode("utf-8", errors="replace")
        for path, data in sorted(files.items())
        if path.lower().endswith((".md", ".txt", ".json"))
    }

    return NormalizedSkill(
        manifest=SkillManifest(
            skill_id=skill_id,
            name=name,
            description=description,
            version=version,
            permissions=permissions,
            tools=tools,
        ),
        kind=SourceKind.AGENT_SKILL,
        files=files,
        extra_text=extra_text,
    )


def normalize_mcp_server(
    skill_id: str,
    version: str,
    files: dict[str, bytes],
    entry: str | None = None,
) -> NormalizedSkill:
    """Normalize an MCP server manifest.

    Handles both the bare server object and the `{"mcpServers": {...}}` wrapper
    an agent config uses.
    """
    if entry is None:
        candidates = sorted(p for p in files if p.lower().endswith(".json"))
        if not candidates:
            raise NormalizationError("no JSON manifest found for an MCP server")
        entry = candidates[0]

    try:
        document = json.loads(files[entry].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NormalizationError(f"{entry} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise NormalizationError(f"{entry} must contain a JSON object")

    server_name = ""
    if isinstance(document.get("mcpServers"), dict) and document["mcpServers"]:
        server_name, server = next(iter(document["mcpServers"].items()))
        if not isinstance(server, dict):
            raise NormalizationError("mcpServers entry must be an object")
    else:
        server = document

    name = str(server.get("name") or document.get("name") or server_name or skill_id)
    description = str(server.get("description") or document.get("description") or "")

    permissions = [str(p) for p in server.get("permissions", []) if isinstance(p, str)]

    tools: list[ToolDef] = []
    for raw_tool in server.get("tools", []):
        if not isinstance(raw_tool, dict):
            continue
        declared = _coerce_capabilities(raw_tool.get("capabilities"))
        tools.append(
            ToolDef(
                name=str(raw_tool.get("name", "")),
                description=str(raw_tool.get("description", "")),
                input_schema=raw_tool.get("inputSchema") or raw_tool.get("input_schema") or {},
                capabilities=declared,
            )
        )

    # An MCP server that launches a process reaches the network and the
    # filesystem by construction, whatever it declares.
    implied = _capabilities_from_permissions(permissions)
    if server.get("command") or server.get("url"):
        for capability in (Capability.NETWORK_OUTBOUND, Capability.ENV_READ):
            if capability not in implied:
                implied.append(capability)
    if implied:
        tools.append(
            ToolDef(
                name=f"{name}:server",
                description=(
                    "MCP server process. Launching a server grants it whatever its "
                    "command and environment allow, independent of declared tools."
                ),
                input_schema={},
                capabilities=implied,
            )
        )

    # Approval flags and env blocks are prime hiding places; hand them to the
    # scanner as text rather than trying to interpret them here.
    extra_text: dict[str, str] = {}
    for key in ("autoApprove", "auto_approve", "alwaysAllow", "env", "command", "args"):
        if key in server:
            extra_text[f"mcp.{key}"] = json.dumps(server[key], ensure_ascii=False)

    return NormalizedSkill(
        manifest=SkillManifest(
            skill_id=skill_id,
            name=name,
            description=description,
            version=version,
            permissions=permissions,
            tools=tools,
        ),
        kind=SourceKind.MCP_SERVER,
        files=files,
        extra_text=extra_text,
    )


def normalize_raw_source(
    skill_id: str,
    version: str,
    files: dict[str, bytes],
) -> NormalizedSkill:
    """Fallback for a source tree that is neither an Agent Skill nor MCP."""
    readme = next(
        (p for p in sorted(files) if p.lower() in ("readme.md", "readme.txt", "readme")),
        None,
    )
    description = ""
    name = skill_id
    if readme:
        text = files[readme].decode("utf-8", errors="replace")
        _, body = parse_frontmatter(text)
        heading = _H1.search(body)
        if heading:
            name = heading.group(1).strip()
        description = _first_paragraph(body)

    extra_text = {
        f"file:{path}": data.decode("utf-8", errors="replace")
        for path, data in sorted(files.items())
        if path.lower().endswith((".md", ".txt", ".json", ".yaml", ".yml", ".toml"))
    }

    return NormalizedSkill(
        manifest=SkillManifest(
            skill_id=skill_id,
            name=name,
            description=description,
            version=version,
            permissions=[],
            tools=[],
        ),
        kind=SourceKind.RAW_SOURCE,
        files=files,
        extra_text=extra_text,
    )


def detect_kind(files: dict[str, bytes]) -> SourceKind:
    """Guess the source shape from the file names alone."""
    lowered = {p.lower() for p in files}
    if any(p.endswith("skill.md") for p in lowered):
        return SourceKind.AGENT_SKILL
    if any(p.endswith(".json") and ("mcp" in p or "server" in p) for p in lowered):
        return SourceKind.MCP_SERVER
    if any(p.endswith(".md") for p in lowered):
        return SourceKind.AGENT_SKILL
    if any(p.endswith(".json") for p in lowered):
        return SourceKind.MCP_SERVER
    return SourceKind.RAW_SOURCE


def normalize(
    skill_id: str,
    version: str,
    files: dict[str, bytes],
    kind: SourceKind | None = None,
) -> NormalizedSkill:
    """Normalize a skill, detecting the source shape when not told."""
    if not files:
        raise NormalizationError("a skill must contain at least one file")
    resolved = kind or detect_kind(files)
    if resolved is SourceKind.AGENT_SKILL:
        return normalize_agent_skill(skill_id, version, files)
    if resolved is SourceKind.MCP_SERVER:
        return normalize_mcp_server(skill_id, version, files)
    return normalize_raw_source(skill_id, version, files)
