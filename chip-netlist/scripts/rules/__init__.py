"""Rule registry for chip netlist."""
from __future__ import annotations

from typing import Any, Callable

RuleFunc = Callable[[dict[str, Any]], list[dict[str, Any]]]

_REGISTRY: dict[str, RuleFunc] = {}


def register(rule_id: str):
    """Decorator to register a rule function."""
    def decorator(func: RuleFunc) -> RuleFunc:
        _REGISTRY[rule_id] = func
        func.rule_id = rule_id
        return func
    return decorator


def get_rule(rule_id: str) -> RuleFunc | None:
    return _REGISTRY.get(rule_id)


def get_all_rules() -> dict[str, RuleFunc]:
    return dict(_REGISTRY)


def get_basic_rules() -> dict[str, RuleFunc]:
    """Rules that don't need datasheet data."""
    from .basic_rules import pin_rules, power_rules, iface_rules, bom_rules  # noqa: F401
    return {
        rid: func for rid, func in _REGISTRY.items()
        if not getattr(func, "needs_datasheet", False)
    }


def get_datasheet_rules() -> dict[str, RuleFunc]:
    """Rules that need datasheet data."""
    from .datasheet_rules import pin_function, param_verify  # noqa: F401
    return {
        rid: func for rid, func in _REGISTRY.items()
        if getattr(func, "needs_datasheet", False)
    }
