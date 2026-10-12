"""
stage_gate_validator.py  -  Stage 14.3: Stage Gate Validation System
======================================================================
StageGateValidator: deterministic read-only validation gate that must
pass before any stage is considered complete.

Checks (strict order):
  1. syntax       - every src/ .py file parses without error
  2. imports      - core portfolio modules import cleanly
  3. api_contract - required exports exist with correct types
  4. drift        - forbidden symbols / cross-layer imports absent

Design rules:
  - stdlib only: ast, importlib, inspect, logging, pathlib, os
  - NO trading / execution / strategy / risk / broker dependencies
  - NO side effects - read-only filesystem and import inspection only
  - deterministic: same codebase always produces the same result
  - fail fast: syntax failure short-circuits remaining checks

drift key semantics (differs from other check keys):
  drift: False  -> no drift detected  (GOOD - gate passes this check)
  drift: True   -> drift was detected (BAD  - gate fails this check)
All other keys: True = passed, False = failed.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import logging
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API contract specification
# Each tuple: (module_dotted_path, symbol_name, expected_kind)
# expected_kind: "function" | "class" | "any"
# "any" skips kind check - used for GenericAlias type aliases
# ---------------------------------------------------------------------------

_REQUIRED_EXPORTS: list[tuple[str, str, str]] = [
    ("src.portfolio.reconciler",     "reconcile",              "function"),
    ("src.portfolio.reconciler",     "DriftReport",            "any"),
    ("src.portfolio.reconciler",     "DriftEntry",             "any"),
    ("src.portfolio.alpaca_adapter", "AlpacaStateAdapter",     "class"),
    ("src.portfolio.alpaca_adapter", "AlpacaAdapterError",     "class"),
    ("src.portfolio.snapshot",       "PortfolioStateSnapshot", "class"),
    ("src.portfolio.snapshot",       "PositionSnapshot",       "class"),
    ("src.portfolio.snapshot",       "OrderSnapshot",          "class"),
    ("src.portfolio.snapshot",       "AccountSnapshot",        "class"),
    ("src.portfolio.snapshot",       "TradeSnapshot",          "class"),
]

# Symbols that MUST NOT exist - their presence signals architecture drift
_FORBIDDEN_EXPORTS: list[tuple[str, str, str]] = [
    ("src.portfolio.reconciler", "PortfolioReconciler", "class"),
]

# Import prefixes banned inside the portfolio layer (isolation boundary)
_FORBIDDEN_CROSS_LAYER_PREFIXES: tuple[str, ...] = (
    "src.execution",
    "src.strategies",
    "src.risk",
    "src.brokers",
    "src.orchestration",
    "src.runtime",
)

# Portfolio source files to scan for cross-layer violations
_PORTFOLIO_SOURCE_RELPATHS: tuple[str, ...] = (
    "portfolio/__init__.py",
    "portfolio/snapshot.py",
    "portfolio/alpaca_adapter.py",
    "portfolio/reconciler.py",
)

# Modules that must import cleanly
_REQUIRED_IMPORT_MODULES: tuple[str, ...] = (
    "src.portfolio.snapshot",
    "src.portfolio.alpaca_adapter",
    "src.portfolio.reconciler",
)

# Directories to skip during syntax scan
_SKIP_DIRS: frozenset[str] = frozenset(
    {"venv", ".venv", "__pycache__", ".git", "node_modules"}
)

# ---------------------------------------------------------------------------
# Internal result type and builder
# ---------------------------------------------------------------------------

ValidationResult = dict[str, Any]


def _build_result(
    stage: str,
    status: str,
    checks: dict[str, Any],
    errors: list[str],
    drift_report: dict[str, Any],
) -> ValidationResult:
    result: ValidationResult = {
        "status":       status,
        "stage":        stage,
        "timestamp":    datetime.now(tz=timezone.utc).isoformat(),
        "checks":       checks,
        "drift_report": drift_report,
    }
    if errors:
        result["errors"] = errors
    return result


# ---------------------------------------------------------------------------
# Check 1: Syntax
# ast.parse() every .py under src_root, skipping venv / __pycache__.
# Returns (passed, error_list).
# ---------------------------------------------------------------------------

def _check_syntax(src_root: pathlib.Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    scanned = 0
    for py_file in sorted(src_root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in py_file.parts):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            ast.parse(source, filename=str(py_file))
            scanned += 1
        except SyntaxError as exc:
            try:
                rel = py_file.relative_to(src_root.parent)
            except ValueError:
                rel = py_file
            errors.append(
                f"SyntaxError in {rel} line {exc.lineno}: {exc.msg}"
            )
        except Exception as exc:
            try:
                rel = py_file.relative_to(src_root.parent)
            except ValueError:
                rel = py_file
            errors.append(f"ParseError in {rel}: {exc}")
    if scanned == 0 and not errors:
        errors.append(
            f"No .py files found under {src_root} - verify src_root path"
        )
    return len(errors) == 0, errors

# ---------------------------------------------------------------------------
# Check 2: Imports
# importlib.import_module() for each required module.
# Returns (all_passed, error_list).
# ---------------------------------------------------------------------------

def _check_imports() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for mod_path in _REQUIRED_IMPORT_MODULES:
        try:
            importlib.import_module(mod_path)
        except ImportError as exc:
            errors.append(f"ImportError [{mod_path}]: {exc}")
        except Exception as exc:
            errors.append(
                f"UnexpectedError importing [{mod_path}]: "
                f"{type(exc).__name__}: {exc}"
            )
    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Check 3: API Contract
# Verify required exports exist with the correct types.
# Returns (all_passed, error_list).
# ---------------------------------------------------------------------------

def _symbol_kind(obj: Any) -> str:
    """Classify an object as 'class', 'function', or 'other'."""
    if inspect.isclass(obj):
        return "class"
    if inspect.isfunction(obj) or inspect.isbuiltin(obj) or inspect.ismethod(obj):
        return "function"
    return "other"


def _check_api_contract() -> tuple[bool, list[str]]:
    errors: list[str] = []
    cache: dict[str, Any] = {}

    for mod_path, symbol, expected_kind in _REQUIRED_EXPORTS:
        if mod_path not in cache:
            try:
                cache[mod_path] = importlib.import_module(mod_path)
            except Exception as exc:
                cache[mod_path] = None
                errors.append(
                    f"Cannot import [{mod_path}] for contract check: {exc}"
                )
        mod = cache[mod_path]
        if mod is None:
            continue  # import failure already recorded
        if not hasattr(mod, symbol):
            errors.append(
                f"Missing export: {mod_path}.{symbol} (expected {expected_kind})"
            )
            continue
        if expected_kind == "any":
            continue  # GenericAlias / type alias - existence is sufficient
        actual_kind = _symbol_kind(getattr(mod, symbol))
        if actual_kind != expected_kind:
            errors.append(
                f"Type mismatch: {mod_path}.{symbol} "
                f"is {actual_kind!r}, expected {expected_kind!r}"
            )

    return len(errors) == 0, errors

# ---------------------------------------------------------------------------
# Check 4: Architecture Drift Detection
# Three sub-detectors - all run independently and results are merged.
# Returns (no_violations, violation_list, drift_report_dict).
# no_violations=True means the check PASSED (nothing bad found).
# ---------------------------------------------------------------------------

def _detect_forbidden_symbols() -> list[str]:
    """Check no forbidden symbol has been re-introduced into a module."""
    violations: list[str] = []
    cache: dict[str, Any] = {}
    for mod_path, symbol, forbidden_kind in _FORBIDDEN_EXPORTS:
        if mod_path not in cache:
            try:
                cache[mod_path] = importlib.import_module(mod_path)
            except Exception:
                cache[mod_path] = None
        mod = cache[mod_path]
        if mod is None or not hasattr(mod, symbol):
            continue  # absent = correct
        actual_kind = _symbol_kind(getattr(mod, symbol))
        if forbidden_kind == "any" or actual_kind == forbidden_kind:
            violations.append(
                f"Forbidden symbol reintroduced: {mod_path}.{symbol} "
                f"({actual_kind}) - architecture drift detected"
            )
    return violations


def _detect_cross_layer_imports(src_root: pathlib.Path) -> list[str]:
    """
    AST-scan portfolio source files for imports reaching into forbidden layers.
    Covers both 'import src.execution' and 'from src.execution import ...' forms.
    """
    violations: list[str] = []
    for rel in _PORTFOLIO_SOURCE_RELPATHS:
        abs_path = src_root / rel.replace("/", os.sep)
        if not abs_path.exists():
            continue
        try:
            source = abs_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(abs_path))
        except Exception:
            continue  # syntax errors already caught in check 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in _FORBIDDEN_CROSS_LAYER_PREFIXES:
                        if (alias.name == prefix
                                or alias.name.startswith(prefix + ".")):
                            violations.append(
                                f"Cross-layer import in src/{rel}: "
                                f"'import {alias.name}' "
                                f"violates portfolio isolation"
                            )
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                for prefix in _FORBIDDEN_CROSS_LAYER_PREFIXES:
                    if mod_name == prefix or mod_name.startswith(prefix + "."):
                        violations.append(
                            f"Cross-layer import in src/{rel}: "
                            f"'from {mod_name} import ...' "
                            f"violates portfolio isolation"
                        )
    return violations


def _detect_reconcile_rename() -> list[str]:
    """
    Belt-and-suspenders guard: verify reconcile() has not been renamed
    or converted to a class between the contract check and drift check.
    """
    violations: list[str] = []
    try:
        mod = importlib.import_module("src.portfolio.reconciler")
    except Exception:
        return violations  # import failure already reported in check 2
    if not hasattr(mod, "reconcile"):
        violations.append(
            "reconcile() missing from reconciler - "
            "possible rename or deletion (architecture drift)"
        )
    elif _symbol_kind(getattr(mod, "reconcile")) != "function":
        violations.append(
            "reconcile exists but is not a function - "
            "possible class conversion (architecture drift)"
        )
    return violations


def _check_drift(
    src_root: pathlib.Path,
) -> tuple[bool, list[str], dict[str, Any]]:
    all_violations: list[str] = []
    all_violations.extend(_detect_forbidden_symbols())
    all_violations.extend(_detect_cross_layer_imports(src_root))
    all_violations.extend(_detect_reconcile_rename())

    n = len(all_violations)
    if n == 0:
        severity = "clean"
    elif n == 1:
        severity = "medium"
    elif n <= 3:
        severity = "high"
    else:
        severity = "critical"

    drift_report: dict[str, Any] = {
        "violations": all_violations,
        "severity":   severity,
    }
    return n == 0, all_violations, drift_report

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class StageGateValidator:
    """
    Deterministic validation gate for stage completion.

    All methods are classmethods. No instantiation required.
    No mutable state is held between calls.

    Usage
    -----
        result = StageGateValidator.run(stage="14.3")
        if result["status"] != "PASS":
            raise RuntimeError(result.get("errors", []))

    Short-circuit rules
    -------------------
    Syntax failure  -> checks 2 / 3 / 4 skipped (imports cannot work)
    Import failure  -> checks 3 / 4   skipped (contract cannot be inspected)
    Contract + Drift -> both always run even if one fails (independent)

    Return schema
    -------------
    Always a dict with keys:
        status       : "PASS" | "FAIL"
        stage        : stage id string
        timestamp    : UTC ISO-8601 string
        checks       : { syntax, imports, api_contract, drift }
        drift_report : { violations: list, severity: str }
        errors       : list[str]  (present only when status=="FAIL")
    """

    @classmethod
    def run(
        cls,
        stage: str = "unknown",
        src_root: str | None = None,
    ) -> ValidationResult:
        """
        Execute all four validation checks and return a structured result.

        Parameters
        ----------
        stage    : stage identifier, e.g. "14.3"
        src_root : absolute path to the src/ directory.
                   Auto-detected from __file__ location when omitted.

        Returns
        -------
        ValidationResult dict - never raises.
        Check result["status"] == "PASS" to gate stage completion.
        """
        # Resolve src/ root (this file is at src/core/stage_gate_validator.py)
        if src_root is None:
            _src = pathlib.Path(__file__).resolve().parent.parent
        else:
            _src = pathlib.Path(src_root).resolve()

        all_errors: list[str] = []
        checks: dict[str, Any] = {
            "syntax":       False,
            "imports":      False,
            "api_contract": False,
            "drift":        False,   # False=no drift(GOOD), True=drift(BAD)
        }
        drift_report: dict[str, Any] = {
            "violations": [],
            "severity":   "unknown",
        }

        logger.info("[StageGate] -- Starting stage %s validation --", stage)

        # ── 1. Syntax ─────────────────────────────────────────────────────
        syntax_ok, syntax_errors = _check_syntax(_src)
        checks["syntax"] = syntax_ok
        if not syntax_ok:
            all_errors.extend(syntax_errors)
            logger.error(
                "[StageGate] SYNTAX FAIL (%d error(s)) - aborting",
                len(syntax_errors),
            )
            return _build_result(
                stage, "FAIL", checks, all_errors,
                {"violations": syntax_errors, "severity": "critical"},
            )
        logger.info("[StageGate] PASS  syntax (%s)", _src)

        # ── 2. Imports ────────────────────────────────────────────────────
        imports_ok, import_errors = _check_imports()
        checks["imports"] = imports_ok
        if not imports_ok:
            all_errors.extend(import_errors)
            logger.error(
                "[StageGate] IMPORTS FAIL (%d error(s)) - aborting",
                len(import_errors),
            )
            return _build_result(
                stage, "FAIL", checks, all_errors,
                {"violations": import_errors, "severity": "critical"},
            )
        logger.info("[StageGate] PASS  imports")

        # ── 3. API Contract ───────────────────────────────────────────────
        contract_ok, contract_errors = _check_api_contract()
        checks["api_contract"] = contract_ok
        if not contract_ok:
            all_errors.extend(contract_errors)
            logger.warning(
                "[StageGate] API CONTRACT FAIL (%d error(s))",
                len(contract_errors),
            )
        else:
            logger.info("[StageGate] PASS  api_contract")

        # ── 4. Drift Detection ────────────────────────────────────────────
        no_drift, violations, drift_report = _check_drift(_src)
        drift_detected = not no_drift
        checks["drift"] = drift_detected  # False=clean(GOOD), True=drift(BAD)
        if drift_detected:
            all_errors.extend(violations)
            logger.warning(
                "[StageGate] DRIFT FAIL (%d violation(s)) severity=%s",
                len(violations), drift_report["severity"],
            )
        else:
            logger.info("[StageGate] PASS  drift (no violations)")

        # ── Final verdict ─────────────────────────────────────────────────
        overall = syntax_ok and imports_ok and contract_ok and not drift_detected
        status = "PASS" if overall else "FAIL"

        if overall:
            logger.info(
                "[StageGate] ALL CHECKS PASSED - stage %s complete", stage
            )
        else:
            logger.error(
                "[StageGate] FAILED - stage %s (%d total error(s))",
                stage, len(all_errors),
            )

        return _build_result(stage, status, checks, all_errors, drift_report)

if __name__ == "__main__":
    validator = StageGateValidator()
    result = validator.run()

    print("\n=== STAGE GATE RESULT ===")
    print(result)
