"""确定性的 Context 选择、压缩、隔离和预算实现。"""

from __future__ import annotations

import json
import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from context_lab.models import (
    BudgetReport,
    BuildRequest,
    BuildResult,
    ContextItem,
    ContextManifest,
    DroppedEntry,
    IncludedEntry,
    Layer,
    SourceKind,
)


LAYER_ORDER: dict[Layer, int] = {
    "system": 0,
    "task": 1,
    "runtime": 2,
    "output": 3,
    "domain": 4,
    "retrieved": 5,
    "tool": 6,
    "memory": 7,
}

# 来源优先级必须独立于“文档版本”。否则攻击者只需伪造一个更大的版本号，
# 就可能让普通检索片段覆盖权威指标目录或运行时状态。
DEFAULT_SOURCE_PRECEDENCE: dict[SourceKind, int] = {
    "system_policy": 800,
    "runtime_state": 700,
    "authoritative_catalog": 600,
    "tool_result": 500,
    "retrieval": 400,
    "memory": 300,
    "user_content": 200,
    "unknown": 100,
}

SUSPICIOUS = re.compile(r"(?i)(ignore|disregard).{0,30}(system|instruction)|忽略.{0,20}(系统|指令)")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\b1\d{10}\b")
BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
SK_TOKEN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
NAMED_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|client[_-]?secret|secret)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{8,}[\"']?"
)
SECTION_SEPARATOR = "\n\n"
REQUEST_TASK_ID = "__build_request_task__"
REQUEST_TASK_SOURCE = "BuildRequest.task"
UNTRUSTED_OPEN = "[UNTRUSTED_DATA_JSON_V1]"
UNTRUSTED_CLOSE = "[/UNTRUSTED_DATA_JSON_V1]"


class RequiredContextOverflow(ValueError):
    """必需上下文无法放进整体预算或分层预算。"""


class RequiredContextInvalid(ValueError):
    """必需上下文过期、时钟异常或在冲突中被淘汰。"""


@dataclass(frozen=True)
class PreparedItem:
    item: ContextItem
    content: str
    rendered: str
    tokens: int
    original_tokens: int
    transformations: tuple[str, ...]

    @property
    def truncated_tokens(self) -> int:
        return max(0, self.original_tokens - self.tokens)


def estimate_tokens(text: str) -> int:
    """稳定教学估算：ASCII 约四字符一个 token，中文字符约一个。

    这里追求离线实验可重复，而不是冒充某个具体模型的 tokenizer。生产接入时
    可以替换本函数，但预算、选择和 manifest 的控制流不需要跟着改。
    """

    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_chars = len(text) - chinese
    return max(1, chinese + math.ceil(ascii_chars / 4))


class ContextBuilder:
    def __init__(
        self,
        *,
        min_relevance: float = 0.3,
        max_item_tokens: int = 80,
        source_precedence: dict[SourceKind, int] | None = None,
    ):
        if not 0 <= min_relevance <= 1:
            raise ValueError("min_relevance 必须在 0 到 1 之间")
        if max_item_tokens < 1:
            raise ValueError("max_item_tokens 必须大于 0")
        self.min_relevance = min_relevance
        self.max_item_tokens = max_item_tokens
        self.source_precedence = {**DEFAULT_SOURCE_PRECEDENCE, **(source_precedence or {})}

    def build(self, request: BuildRequest) -> BuildResult:
        dropped: list[DroppedEntry] = []
        visible: list[ContextItem] = []

        if any(item.id == REQUEST_TASK_ID for item in request.items):
            raise ValueError(f"ContextItem.id {REQUEST_TASK_ID!r} 是 Builder 保留标识")

        # 权限和时效要在任何拼接、摘要之前执行；进入过 Context 的秘密无法靠
        # 后续 Prompt 保证模型“忘掉”。
        for item in request.items:
            reason, detail = self._visibility_failure(item, request)
            if reason is None:
                visible.append(item)
                continue
            if item.required:
                # 必需输入无论因权限还是时效不可见，都不能被静默删掉后继续运行；
                # 错误只带 item id 和策略原因，绝不回显原始 content。
                raise RequiredContextInvalid(f"必需上下文 {item.id!r} 不可用：{reason} ({detail})")
            dropped.append(self._drop(item, reason, detail=detail))

        visible = self._resolve_conflicts(visible, dropped)
        visible = self._deduplicate(visible, dropped)
        prepared = [self._prepare(item) for item in visible]

        # BuildRequest.task 不是只供调用方看的备注，而是本次推理的明确目标。
        # 将其转成必需 task 段后，它会参与排序、整体/分层预算和 manifest 审计；
        # 任务放不下时必须失败，不能悄悄让模型在“无目标”状态下运行。
        task_item = ContextItem(
            id=REQUEST_TASK_ID,
            layer="task",
            source=REQUEST_TASK_SOURCE,
            source_kind="user_content",
            content=request.task,
            required=True,
            priority=1_000_000,
        )
        prepared.append(self._prepare(task_item, extra_transformations=("request_task_section",)))
        prepared.sort(key=self._sort_key)

        available = request.token_budget - request.reserved_tokens
        required_by_layer: dict[Layer, int] = {layer: 0 for layer in LAYER_ORDER}
        for prepared_item in prepared:
            if prepared_item.item.required:
                required_by_layer[prepared_item.item.layer] += prepared_item.tokens
        required_count = sum(1 for item in prepared if item.item.required)
        required_tokens = sum(required_by_layer.values()) + max(0, required_count - 1) * estimate_tokens(SECTION_SEPARATOR)
        if required_tokens > available:
            raise RequiredContextOverflow(
                f"必需上下文需要 {required_tokens} tokens，可用输入预算只有 {available}"
            )
        for layer, required_layer_tokens in required_by_layer.items():
            layer_limit = request.layer_budgets.get(layer)
            if layer_limit is not None and required_layer_tokens > layer_limit:
                raise RequiredContextOverflow(
                    f"{layer} 层必需上下文需要 {required_layer_tokens} tokens，分层预算只有 {layer_limit}"
                )

        included: list[PreparedItem] = []
        used = 0
        structural_tokens = 0
        used_by_layer: dict[Layer, int] = {layer: 0 for layer in LAYER_ORDER}
        for prepared_item in prepared:
            item = prepared_item.item
            layer_limit = request.layer_budgets.get(item.layer)
            if layer_limit is not None and used_by_layer[item.layer] + prepared_item.tokens > layer_limit:
                if item.required:
                    raise RequiredContextOverflow(
                        f"{item.layer} 层必需上下文需要 {used_by_layer[item.layer] + prepared_item.tokens} "
                        f"tokens，分层预算只有 {layer_limit}"
                    )
                dropped.append(
                    self._drop(
                        item,
                        "layer_token_budget",
                        estimated_tokens=prepared_item.tokens,
                        detail=f"layer={item.layer}, used={used_by_layer[item.layer]}, limit={layer_limit}",
                    )
                )
                continue
            separator_cost = estimate_tokens(SECTION_SEPARATOR) if included else 0
            if used + separator_cost + prepared_item.tokens > available:
                if item.required:
                    raise RequiredContextOverflow(
                        f"必需上下文加入结构开销后超过输入预算：used={used}, "
                        f"next={prepared_item.tokens}, separator={separator_cost}, available={available}"
                    )
                dropped.append(
                    self._drop(
                        item,
                        "token_budget",
                        estimated_tokens=prepared_item.tokens,
                        detail=f"used={used}, available={available}",
                    )
                )
                continue
            included.append(prepared_item)
            used += separator_cost + prepared_item.tokens
            structural_tokens += separator_cost
            used_by_layer[item.layer] += prepared_item.tokens

        budget = BudgetReport(
            input_limit=request.token_budget,
            reserved_tokens=request.reserved_tokens,
            available_tokens=available,
            used_tokens=used,
            structural_tokens=structural_tokens,
            remaining_tokens=available - used,
            used_by_layer=used_by_layer,
            layer_limits=request.layer_budgets,
        )
        manifest = ContextManifest(
            tenant=request.tenant,
            task_source=REQUEST_TASK_SOURCE,
            # manifest 不重复保存可能敏感的完整任务正文；摘要既能关联审计记录，
            # 也能证明两个同长度但不同内容的 task 不是同一次构建输入。
            task_sha256=hashlib.sha256(request.task.encode("utf-8")).hexdigest(),
            token_budget=request.token_budget,
            total_tokens=used,
            budget=budget,
            included=[
                IncludedEntry(
                    id=value.item.id,
                    layer=value.item.layer,
                    source=value.item.source,
                    source_kind=value.item.source_kind,
                    version=value.item.version,
                    tokens=value.tokens,
                    original_tokens=value.original_tokens,
                    truncated_tokens=value.truncated_tokens,
                    transformations=list(value.transformations),
                    required=value.item.required,
                    priority=value.item.priority,
                    position=position,
                )
                for position, value in enumerate(included)
            ],
            dropped=dropped,
        )
        return BuildResult(context=SECTION_SEPARATOR.join(value.rendered for value in included), manifest=manifest)

    def _visibility_failure(self, item: ContextItem, request: BuildRequest) -> tuple[str | None, str | None]:
        if item.tenant is not None and item.tenant != request.tenant:
            return "permission_tenant", f"item_tenant={item.tenant}"
        if item.allowed_roles and item.allowed_roles.isdisjoint(request.roles):
            return "permission_role", f"required_roles={sorted(item.allowed_roles)}"
        if not item.required and item.relevance < self.min_relevance:
            return "low_relevance", f"relevance={item.relevance}, minimum={self.min_relevance}"

        has_freshness_constraint = item.expires_at is not None or item.max_age_seconds is not None
        if has_freshness_constraint and request.as_of is None:
            # 不偷偷读取当前时间，保证同一输入在测试、回放和审计时得到同一结果。
            return "freshness_unverifiable", "BuildRequest.as_of is required"
        if request.as_of is None:
            return None, None
        if item.updated_at is not None and item.updated_at > request.as_of:
            return "future_timestamp", f"updated_at={item.updated_at.isoformat()}"
        if item.expires_at is not None and item.expires_at <= request.as_of:
            return "expired", f"expires_at={item.expires_at.isoformat()}"
        if item.max_age_seconds is not None and item.updated_at is not None:
            age_seconds = (request.as_of - item.updated_at).total_seconds()
            if age_seconds > item.max_age_seconds:
                return "stale", f"age_seconds={int(age_seconds)}, maximum={item.max_age_seconds}"
        return None, None

    def _prepare(
        self,
        item: ContextItem,
        *,
        extra_transformations: tuple[str, ...] = (),
    ) -> PreparedItem:
        content = item.content.strip()
        original_rendered = self._render_content(item, content)
        original_tokens = self._tokens(item, original_rendered)
        transformations: list[str] = list(extra_transformations)

        if item.sensitive:
            redacted = _redact_sensitive(content)
            if redacted != content:
                content = redacted
                transformations.append("redacted")

        if item.compressible and estimate_tokens(content) > self.max_item_tokens:
            suffix = f"… [原文:{item.source}]"
            content = _truncate_to_budget(content, suffix, self.max_item_tokens)
            transformations.append("compressed_with_source")

        if item.untrusted:
            if SUSPICIOUS.search(content):
                transformations.append("suspicious_instruction_marked")
            content = _encode_untrusted_data(source=item.source, content=content)
            transformations.extend(("json_data_envelope", "isolated_as_data"))

        rendered = self._render_content(item, content)
        return PreparedItem(
            item=item,
            content=content,
            rendered=rendered,
            tokens=self._tokens(item, rendered),
            original_tokens=original_tokens,
            transformations=tuple(transformations),
        )

    @staticmethod
    def _tokens(item: ContextItem, rendered: str) -> int:
        # token_override 只用于稳定地构造预算边界测试；真实运行应统计完整渲染段。
        return item.token_override if item.token_override is not None else estimate_tokens(rendered)

    def _resolve_conflicts(self, items: list[ContextItem], dropped: list[DroppedEntry]) -> list[ContextItem]:
        winners: dict[str, ContextItem] = {}
        without_key: list[ContextItem] = []
        for item in items:
            if item.conflict_key is None:
                without_key.append(item)
                continue
            previous = winners.get(item.conflict_key)
            if previous is None:
                winners[item.conflict_key] = item
                continue
            winner, loser = (item, previous) if self._authority_key(item) > self._authority_key(previous) else (previous, item)
            if loser.required:
                raise RequiredContextInvalid(
                    f"必需上下文 {loser.id!r} 在冲突 {item.conflict_key!r} 中败给 {winner.id!r}"
                )
            winners[item.conflict_key] = winner
            dropped.append(
                self._drop(
                    loser,
                    "conflict_lower_authority",
                    detail=f"winner={winner.id}, winner_source_kind={winner.source_kind}",
                )
            )
        return [*without_key, *winners.values()]

    def _deduplicate(self, items: list[ContextItem], dropped: list[DroppedEntry]) -> list[ContextItem]:
        seen: dict[str, ContextItem] = {}
        result: list[ContextItem] = []
        # required 先保留；其余重复项按来源权威、版本、可信度选择，而不是依赖输入顺序。
        ordered = sorted(items, key=lambda value: (value.required, self._authority_key(value)), reverse=True)
        for item in ordered:
            fingerprint = self._fingerprint(item)
            winner = seen.get(fingerprint)
            if winner is not None:
                dropped.append(
                    self._drop(
                        item,
                        "duplicate_lower_authority",
                        detail=f"winner={winner.id}",
                    )
                )
                continue
            seen[fingerprint] = item
            result.append(item)
        return result

    def _authority_key(self, item: ContextItem) -> tuple[int, int, float, int, int, str]:
        updated = item.updated_at.timestamp() if item.updated_at is not None else float("-inf")
        return (
            self.source_precedence[item.source_kind],
            item.version,
            updated,
            item.trust,
            item.priority,
            item.id,
        )

    def _sort_key(self, item: PreparedItem) -> tuple[object, ...]:
        value = item.item
        return (
            not value.required,
            LAYER_ORDER[value.layer],
            -value.priority,
            -self.source_precedence[value.source_kind],
            -value.relevance,
            -value.trust,
            -value.version,
            value.id,
        )

    @staticmethod
    def _fingerprint(item: ContextItem) -> str:
        if item.dedupe_key:
            return f"explicit:{item.dedupe_key.strip().casefold()}"
        normalized = unicodedata.normalize("NFKC", item.content).casefold()
        normalized = re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
        return f"content:{normalized}"

    @staticmethod
    def _render_content(item: ContextItem, content: str) -> str:
        # JSON 字符串编码让 source 中的引号保持为数据；模型看到的 header 边界不会被伪造。
        rendered_source = json.dumps(item.source, ensure_ascii=False)
        return (
            f"[{item.layer.upper()} source={rendered_source} source_kind={item.source_kind} "
            f"version={item.version}]\n{content}"
        )

    @staticmethod
    def _drop(
        item: ContextItem,
        reason: str,
        *,
        estimated_tokens: int | None = None,
        detail: str | None = None,
    ) -> DroppedEntry:
        return DroppedEntry(
            id=item.id,
            source=item.source,
            reason=reason,
            estimated_tokens=estimated_tokens,
            detail=detail,
        )


def _truncate_to_budget(content: str, suffix: str, max_tokens: int) -> str:
    """二分找到能与来源后缀一起放入内容预算的最长前缀。"""

    if estimate_tokens(suffix) >= max_tokens:
        return suffix
    low, high = 0, len(content)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_tokens(content[:middle] + suffix) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    return content[:low] + suffix


def _redact_sensitive(content: str) -> str:
    """覆盖教学项目里最常见的 PII 与凭据形态。"""

    value = EMAIL.sub("[EMAIL_REDACTED]", content)
    value = PHONE.sub("[PHONE_REDACTED]", value)
    value = BEARER_TOKEN.sub("Bearer [TOKEN_REDACTED]", value)
    value = SK_TOKEN.sub("[SECRET_REDACTED]", value)
    value = AWS_ACCESS_KEY.sub("[SECRET_REDACTED]", value)
    value = NAMED_SECRET.sub(lambda match: f"{match.group(1)}=[SECRET_REDACTED]", value)
    return value


def _encode_untrusted_data(*, source: str, content: str) -> str:
    """把不可信正文编码成单行 JSON 数据，阻断伪造的 Context 控制边界。

    仅用 XML 风格标签包正文并不安全：正文可以自己写 ``</untrusted-data>``，
    随后伪造一个 ``[SYSTEM]`` 段。JSON 会把换行、引号编码为字符串数据；再把
    ``<>[]`` 编成 Unicode 转义，正文里连控制标记的字面形态都不会出现。
    """

    payload = json.dumps(
        {"content": content, "schema": "untrusted-data.v1", "source": source},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for character, escaped in (
        ("<", r"\u003c"),
        (">", r"\u003e"),
        ("[", r"\u005b"),
        ("]", r"\u005d"),
    ):
        payload = payload.replace(character, escaped)
    return f"{UNTRUSTED_OPEN}\n{payload}\n{UNTRUSTED_CLOSE}"
