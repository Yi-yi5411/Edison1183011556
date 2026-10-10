# -*- coding: utf-8 -*-
"""Formula Engine - Excel-style formula parser and evaluator for structured data"""

import re
import math
from datetime import datetime
from typing import List, Dict, Any, Tuple, Callable

# ─────────────── Cell reference parsing ───────────────
_COL_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def col_letter_to_index(letter: str) -> int:
    """Convert column letter(s) to 0-based index. A=0, B=1, ..., Z=25, AA=26, etc."""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def col_index_to_letter(idx: int) -> str:
    """Convert 0-based column index to letter(s). 0=A, 25=Z, 26=AA, etc."""
    result = ""
    idx += 1
    while idx > 0:
        idx -= 1
        result = _COL_LETTERS[idx % 26] + result
        idx //= 26
    return result


def parse_cell_ref(ref: str) -> Tuple[int, int]:
    """Parse "A1" → (row_idx, col_idx) both 0-based. Returns (-1, -1) on failure."""
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref.strip())
    if not m:
        return -1, -1
    col = col_letter_to_index(m.group(1))
    row = int(m.group(2)) - 1
    return row, col


_RANGE_RE = re.compile(r"^([A-Za-z]+\d+):([A-Za-z]+\d+)$")
_CELL_RE = re.compile(r"[A-Za-z]+\d+")


# ─────────────── Formula Engine ───────────────
class FormulaEngine:
    """Evaluates Excel-style formulas against a sheet's data."""

    # ── Built-in functions ──
    @staticmethod
    def _flatten(*args):
        """Flatten args: convert any lists to individual items."""
        result = []
        for a in args:
            if isinstance(a, list):
                result.extend(a)
            else:
                result.append(a)
        return result

    @classmethod
    def _make_funcs(cls):
        return {
            "SUM": lambda *args: sum(float(a) for a in cls._flatten(*args) if _is_number(a)),
            "AVERAGE": lambda *args: _safe_div(
                sum(float(a) for a in cls._flatten(*args) if _is_number(a)),
                max(1, sum(1 for a in cls._flatten(*args) if _is_number(a)))),
            "MIN": lambda *args: min(
                (float(a) for a in cls._flatten(*args) if _is_number(a)), default=0),
            "MAX": lambda *args: max(
                (float(a) for a in cls._flatten(*args) if _is_number(a)), default=0),
            "COUNT": lambda *args: sum(1 for a in cls._flatten(*args) if _is_number(a)),
            "COUNTA": lambda *args: sum(1 for a in cls._flatten(*args) if str(a).strip()),
            "ROUND": lambda v, d=0: round(
                float(cls._flatten(v)[0]) if _is_number(cls._flatten(v)[0] if cls._flatten(v) else 0) else 0, int(d)),
            "ABS": lambda v: abs(float(v) if _is_number(v) and not isinstance(v, list) else float(cls._flatten(v)[0]) if _is_number(cls._flatten(v)[0] if cls._flatten(v) else 0) else 0),
            "INT": lambda v: int(float(v) if _is_number(v) and not isinstance(v, list) else float(cls._flatten(v)[0]) if _is_number(cls._flatten(v)[0] if cls._flatten(v) else 0) else 0),
            "IF": lambda cond, t, f: t if _is_truthy(cond) else f,
            "AND": lambda *args: all(_is_truthy(a) for a in cls._flatten(*args)),
            "OR": lambda *args: any(_is_truthy(a) for a in cls._flatten(*args)),
            "NOT": lambda v: not _is_truthy(v),
            "SQRT": lambda v: math.sqrt(float(v)) if _is_number(v) and float(v) >= 0 and not isinstance(v, list) else 0,
            "POWER": lambda b, e: float(b) ** float(e) if _is_number(b) and _is_number(e) else 0,
            "CONCAT": lambda *args: "".join(str(a) for a in cls._flatten(*args)),
            "UPPER": lambda s: str(s).upper(),
            "LOWER": lambda s: str(s).lower(),
            "TRIM": lambda s: str(s).strip(),
            "LEN": lambda s: len(str(s)),
            "LEFT": lambda s, n=1: str(s)[:int(n)],
            "RIGHT": lambda s, n=1: str(s)[-int(n):],
            "MID": lambda s, start, n: str(s)[int(start)-1:int(start)-1+int(n)],
            "SUMIF": lambda rng, cond, sum_rng=None: cls._sumif(rng, cond, sum_rng),
            "COUNTIF": lambda rng, cond: cls._countif(rng, cond),
            "AVERAGEIF": lambda rng, cond, avg_rng=None: cls._averageif(rng, cond, avg_rng),
            "VLOOKUP": lambda val, table, col, exact=True: cls._vlookup(val, table, col, exact),
            "INDEX": lambda arr, row, col=0: cls._index(arr, row, col),
            "MATCH": lambda val, arr, exact=True: cls._match(val, arr, exact),
            "TEXT": lambda v, fmt: cls._text_fmt(v, fmt),
            "TODAY": lambda: datetime.now().strftime("%Y-%m-%d"),
            "NOW": lambda: datetime.now().strftime("%Y-%m-%d %H:%M"),
            "DATEDIF": lambda d1, d2, unit: cls._datedif(d1, d2, unit),
            "RANK": lambda v, arr, order=0: cls._rank(v, arr, order),
            "STDEV": lambda *args: cls._stdev(*args),
            "MEDIAN": lambda *args: cls._median(*args),
            "MODE": lambda *args: cls._mode(*args),
        }

    FUNCTIONS: Dict[str, Callable] = None  # initialized below

    def __init__(self, sheet_data: Dict[str, List[List[str]]]):
        """
        sheet_data: {item_name: [[cell_values...], ...]}
        """
        self.sheet_data = sheet_data
        self._deps: Dict[str, set] = {}  # cell_key → set of formula cells that depend on it
        if FormulaEngine.FUNCTIONS is None:
            FormulaEngine.FUNCTIONS = FormulaEngine._make_funcs()

    def _cell_key(self, item: str, row: int, col: int) -> str:
        return f"{item}|{row}|{col}"

    def evaluate(self, formula: str, item_name: str, row_idx: int, col_idx: int) -> str:
        """
        Evaluate a formula string (with or without leading =).
        Returns the result as a string, or the original text if not a formula.
        """
        f = formula.strip()
        if not f.startswith("="):
            return formula
        expr = f[1:].strip()
        if not expr:
            return ""

        rows = self.sheet_data.get(item_name, [])
        try:
            result = self._eval_expr(expr, item_name, row_idx, col_idx, rows)
            # Format result as string
            if isinstance(result, bool):
                return "True" if result else "False"
            if isinstance(result, float):
                if abs(result - round(result, 6)) < 1e-10:
                    result = round(result, 6)
                result = f"{result:.4f}".rstrip("0").rstrip(".")
                return result
            if isinstance(result, list):
                # Return first element for display
                return str(result[0]) if result else ""
            return str(result)
        except Exception as e:
            return f"#ERR: {e}"

    def _eval_expr(self, expr: str, item: str, row: int, col: int,
                   rows: List[List[str]]) -> Any:
        """Evaluate a sub-expression (no leading =)."""
        expr = expr.strip()
        if not expr:
            return ""

        # ── String literal ──
        if (expr.startswith('"') and expr.endswith('"')) or \
           (expr.startswith("'") and expr.endswith("'")):
            return expr[1:-1]

        # ── Boolean literal ──
        if expr.upper() == "TRUE":
            return True
        if expr.upper() == "FALSE":
            return False

        # ── Pure number literal ──
        try:
            if "." in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            pass

        # ── Pure function call (entire expr is FUNC(args)) ──
        # Check if entire expr is a single function call with balanced parens
        m = re.match(r"^([A-Z]+)\((.*)\)$", expr, re.IGNORECASE)
        if m:
            args_str = m.group(2)
            # Verify parens are balanced (greedy .* may over-match mixed expressions)
            depth = 0
            balanced = True
            for ch in args_str:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth < 0:
                        balanced = False
                        break
            if balanced and depth == 0:
                func_name = m.group(1).upper()
                args = self._parse_args(args_str, item, row, col, rows)
                if func_name in self.FUNCTIONS:
                    try:
                        return self.FUNCTIONS[func_name](*args)
                    except Exception as e:
                        raise ValueError(f"{func_name}(...): {e}")
                raise ValueError(f"Unknown function: {func_name}")

        # ── Pure range reference (e.g., A1:A10) ──
        m = _RANGE_RE.match(expr)
        if m:
            return self._get_range_values(m.group(1), m.group(2), item, row, col, rows)

        # ── Pure single cell reference ──
        m = _CELL_RE.fullmatch(expr)
        if m:
            return self._get_cell_value(m.group(0), item, row, col, rows)

        # ── Complex expression: resolve all tokens then safe-eval ──
        return self._eval_complex(expr, item, row, col, rows)

    def _get_cell_value(self, ref: str, item: str, row: int, col: int,
                        rows: List[List[str]]) -> Any:
        """Get value of a single cell reference, tracking dependency."""
        ri, ci = parse_cell_ref(ref)
        if ri < 0:
            raise ValueError(f"Invalid cell: {ref}")
        # Track dependency
        dep_key = self._cell_key(item, ri, ci)
        formula_key = self._cell_key(item, row, col)
        if dep_key not in self._deps:
            self._deps[dep_key] = set()
        self._deps[dep_key].add(formula_key)
        if ri < len(rows) and ci < len(rows[ri]):
            return self._to_number(rows[ri][ci])
        return 0

    def _get_range_values(self, ref1: str, ref2: str, item: str, row: int,
                          col: int, rows: List[List[str]]) -> list:
        """Get values of a range reference as a flat list."""
        r1, c1 = parse_cell_ref(ref1)
        r2, c2 = parse_cell_ref(ref2)
        if r1 < 0 or r2 < 0:
            raise ValueError(f"Invalid range: {ref1}:{ref2}")
        vals = []
        for ri in range(min(r1, r2), max(r1, r2) + 1):
            for ci in range(min(c1, c2), max(c1, c2) + 1):
                # Track dependency
                dep_key = self._cell_key(item, ri, ci)
                formula_key = self._cell_key(item, row, col)
                if dep_key not in self._deps:
                    self._deps[dep_key] = set()
                self._deps[dep_key].add(formula_key)
                if ri < len(rows) and ci < len(rows[ri]):
                    vals.append(self._to_number(rows[ri][ci]))
                else:
                    vals.append(0)
        return vals

    def _eval_complex(self, expr: str, item: str, row: int, col: int,
                      rows: List[List[str]]) -> Any:
        """Evaluate complex expressions with cell refs, ranges, functions, and operators."""
        # Step 1: Replace function calls (innermost first) with placeholder values
        resolved = self._resolve_functions(expr, item, row, col, rows)

        # Step 2: Replace range references with list literals
        def _replace_range(m):
            vals = self._get_range_values(m.group(1), m.group(2), item, row, col, rows)
            return f"[{','.join(str(v) for v in vals)}]"
        resolved = _RANGE_RE.sub(_replace_range, resolved)

        # Step 3: Replace cell references with values
        def _replace_cell(m):
            return str(self._get_cell_value(m.group(0), item, row, col, rows))
        resolved = _CELL_RE.sub(_replace_cell, resolved)

        # Step 4: Excel -> Python operator conversions
        # ^ -> ** (power)
        resolved = re.sub(r'\^', '**', resolved)
        # <> -> != (not equal)
        resolved = re.sub(r'<>', '!=', resolved)
        # = -> == (equality, but not inside <=, >=, <>, or function args)
        # Only replace standalone = that's not part of <=, >=, <>, or ==
        resolved = re.sub(r'(?<![<>!=])=(?![=])', '==', resolved)

        # Step 5: Safe evaluate using AST
        try:
            import ast
            tree = ast.parse(resolved, mode="eval")
            return self._safe_eval_ast(tree.body, {
                "sqrt": math.sqrt, "abs": abs, "round": round,
                "int": int, "float": float, "min": min, "max": max,
                "sum": sum, "len": len, "pow": pow,
            })
        except Exception as e:
            raise ValueError(f"Arithmetic error: {e}")

    def _resolve_functions(self, expr: str, item: str, row: int, col: int,
                           rows: List[List[str]]) -> str:
        """Replace all function calls in expr with their evaluated values.

        Handles nested functions by processing innermost first.
        Returns a string with function calls replaced by numeric/string literals.
        """
        # Pattern to find the innermost function call (no nested parens in args)
        func_pattern = re.compile(r'([A-Za-z]+)\(([^()]*)\)')

        max_iterations = 100  # Prevent infinite loops
        for _ in range(max_iterations):
            m = func_pattern.search(expr)
            if not m:
                break
            func_name = m.group(1).upper()
            args_str = m.group(2)

            # Parse and evaluate arguments
            args = self._parse_args(args_str, item, row, col, rows)
            if func_name in self.FUNCTIONS:
                try:
                    result = self.FUNCTIONS[func_name](*args)
                except Exception as e:
                    raise ValueError(f"{func_name}(...): {e}")
            else:
                raise ValueError(f"Unknown function: {func_name}")

            # Convert result to string representation
            if isinstance(result, bool):
                replacement = "True" if result else "False"
            elif isinstance(result, float):
                replacement = repr(result)
            elif isinstance(result, int):
                replacement = str(result)
            elif isinstance(result, list):
                replacement = f"[{','.join(str(v) for v in result)}]"
            else:
                # String - wrap in quotes for safe eval
                replacement = repr(str(result))

            expr = expr[:m.start()] + replacement + expr[m.end():]

        return expr

    def _parse_args(self, args_str: str, item: str, row: int, col: int,
                    rows: List[List[str]]) -> list:
        """Parse comma-separated function arguments, handling nested parens and quotes."""
        args = []
        depth = 0
        in_quote = False
        quote_char = None
        current = ""
        for ch in args_str:
            if in_quote:
                current += ch
                if ch == quote_char:
                    in_quote = False
                continue
            if ch in ('"', "'"):
                in_quote = True
                quote_char = ch
                current += ch
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += ch
        if current.strip():
            args.append(current.strip())

        # Evaluate each argument
        result = []
        for arg in args:
            result.append(self._eval_expr(arg, item, row, col, rows))
        return result

    def _to_number(self, val: str) -> Any:
        """Try to convert string to number; return original if not."""
        if val is None or val == "":
            return 0
        s = str(val).strip()
        try:
            if "." in s:
                return float(s)
            return int(s)
        except ValueError:
            pass
        return s

    def get_dependents(self, item: str, row: int, col: int) -> set:
        """Get set of formula cells that depend on this cell."""
        key = self._cell_key(item, row, col)
        return self._deps.get(key, set())

    def clear_deps(self):
        self._deps.clear()

    @staticmethod
    def _safe_eval_ast(node, names: dict):
        """递归安全评估 AST 节点，仅允许算术运算、比较和已注册函数调用。"""
        import ast as _ast
        if isinstance(node, _ast.Constant):
            return node.value
        # Python < 3.8 兼容（Num/Str 在 3.12 已移除）
        if hasattr(_ast, 'Num') and isinstance(node, _ast.Num):
            return node.n
        if isinstance(node, _ast.BinOp):
            left = FormulaEngine._safe_eval_ast(node.left, names)
            right = FormulaEngine._safe_eval_ast(node.right, names)
            ops = {
                _ast.Add: lambda a, b: a + b,
                _ast.Sub: lambda a, b: a - b,
                _ast.Mult: lambda a, b: a * b,
                _ast.Div: lambda a, b: a / b if b != 0 else 0,
                _ast.FloorDiv: lambda a, b: a // b if b != 0 else 0,
                _ast.Mod: lambda a, b: a % b if b != 0 else 0,
                _ast.Pow: lambda a, b: a ** b,
            }
            op_type = type(node.op)
            if op_type in ops:
                return ops[op_type](left, right)
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        if isinstance(node, _ast.UnaryOp):
            operand = FormulaEngine._safe_eval_ast(node.operand, names)
            if isinstance(node.op, _ast.USub):
                return -operand
            if isinstance(node.op, _ast.UAdd):
                return +operand
            if isinstance(node.op, _ast.Not):
                return not FormulaEngine._is_truthy_val(operand)
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        if isinstance(node, _ast.Compare):
            left = FormulaEngine._safe_eval_ast(node.left, names)
            result = True
            for op, comp_node in zip(node.ops, node.comparators):
                right = FormulaEngine._safe_eval_ast(comp_node, names)
                if isinstance(op, _ast.Gt):
                    result = result and (left > right)
                elif isinstance(op, _ast.Lt):
                    result = result and (left < right)
                elif isinstance(op, _ast.GtE):
                    result = result and (left >= right)
                elif isinstance(op, _ast.LtE):
                    result = result and (left <= right)
                elif isinstance(op, _ast.Eq):
                    result = result and (left == right)
                elif isinstance(op, _ast.NotEq):
                    result = result and (left != right)
                else:
                    raise ValueError(f"Unsupported comparison: {type(op).__name__}")
                left = right
            return result
        if isinstance(node, _ast.BoolOp):
            if isinstance(node.op, _ast.And):
                return all(FormulaEngine._is_truthy_val(FormulaEngine._safe_eval_ast(v, names)) for v in node.values)
            if isinstance(node.op, _ast.Or):
                return any(FormulaEngine._is_truthy_val(FormulaEngine._safe_eval_ast(v, names)) for v in node.values)
            raise ValueError(f"Unsupported bool op: {type(node.op).__name__}")
        if isinstance(node, _ast.Call):
            if not isinstance(node.func, _ast.Name):
                raise ValueError("Only named function calls allowed")
            func_name = node.func.id
            if func_name not in names:
                raise ValueError(f"Unknown function: {func_name}")
            args = [FormulaEngine._safe_eval_ast(a, names) for a in node.args]
            return names[func_name](*args)
        if isinstance(node, _ast.List):
            return [FormulaEngine._safe_eval_ast(e, names) for e in node.elts]
        if isinstance(node, _ast.Name):
            if node.id in names:
                return names[node.id]
            if node.id == "True":
                return True
            if node.id == "False":
                return False
            raise ValueError(f"Unknown name: {node.id}")
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    @staticmethod
    def _is_truthy_val(v):
        """Check if value is truthy for boolean operations."""
        if v is None or v == "" or v == 0 or v is False:
            return False
        if isinstance(v, str) and v.upper() in ("FALSE", "0", "NO"):
            return False
        return True

    # ═══════════ Extended Functions ═══════════
    @staticmethod
    def _flatten_to_list(arg):
        """Flatten arg to list, handling both single values and lists."""
        if isinstance(arg, list):
            result = []
            for a in arg:
                if isinstance(a, list):
                    result.extend(a)
                else:
                    result.append(a)
            return result
        return [arg]

    @staticmethod
    def _sumif(rng, cond, sum_rng=None):
        vals = FormulaEngine._flatten_to_list(rng)
        if sum_rng is not None:
            sum_vals = FormulaEngine._flatten_to_list(sum_rng)
        else:
            sum_vals = vals
        total = 0.0
        cond_str = str(cond)
        for i, v in enumerate(vals):
            vn = float(v) if _is_number(v) else 0
            if cond_str.startswith(">"):
                if vn > float(cond_str[1:]): total += (float(sum_vals[i]) if i < len(sum_vals) and _is_number(sum_vals[i]) else 0)
            elif cond_str.startswith("<"):
                if vn < float(cond_str[1:]): total += (float(sum_vals[i]) if i < len(sum_vals) and _is_number(sum_vals[i]) else 0)
            elif cond_str.startswith(">="):
                if vn >= float(cond_str[2:]): total += (float(sum_vals[i]) if i < len(sum_vals) and _is_number(sum_vals[i]) else 0)
            elif cond_str.startswith("<="):
                if vn <= float(cond_str[2:]): total += (float(sum_vals[i]) if i < len(sum_vals) and _is_number(sum_vals[i]) else 0)
            elif cond_str.startswith("="):
                if vn == float(cond_str[1:]): total += (float(sum_vals[i]) if i < len(sum_vals) and _is_number(sum_vals[i]) else 0)
        return total

    @staticmethod
    def _countif(rng, cond):
        vals = FormulaEngine._flatten_to_list(rng)
        count = 0
        cond_str = str(cond)
        for v in vals:
            vn = float(v) if _is_number(v) else 0
            sv = str(v)
            if cond_str.startswith(">"):
                if vn > float(cond_str[1:]): count += 1
            elif cond_str.startswith("<"):
                if vn < float(cond_str[1:]): count += 1
            elif cond_str.startswith(">="):
                if vn >= float(cond_str[2:]): count += 1
            elif cond_str.startswith("<="):
                if vn <= float(cond_str[2:]): count += 1
            elif cond_str.startswith("="):
                if vn == float(cond_str[1:]): count += 1
            elif cond_str in sv:
                count += 1
        return count

    @staticmethod
    def _averageif(rng, cond, avg_rng=None):
        vals = FormulaEngine._flatten_to_list(rng)
        total, count = 0.0, 0
        if avg_rng is not None:
            avg_vals = FormulaEngine._flatten_to_list(avg_rng)
        else:
            avg_vals = vals
        cond_str = str(cond)
        for i, v in enumerate(vals):
            vn = float(v) if _is_number(v) else 0
            match = False
            if cond_str.startswith(">"): match = vn > float(cond_str[1:])
            elif cond_str.startswith("<"): match = vn < float(cond_str[1:])
            if match and i < len(avg_vals) and _is_number(avg_vals[i]):
                total += float(avg_vals[i])
                count += 1
        return total / count if count > 0 else 0

    @staticmethod
    def _vlookup(val, table, col_idx, exact=True):
        if not isinstance(table, list):
            return "#N/A"
        v = str(val).strip().lower()
        col = int(col_idx) if _is_number(col_idx) else 0
        for row in table:
            if not row:
                continue
            if isinstance(row, list):
                if (exact and str(row[0]).strip().lower() == v) or (not exact and v in str(row[0]).strip().lower()):
                    return row[min(col, len(row)-1)] if col < len(row) else ""
        return "#N/A" if exact else ""

    @staticmethod
    def _index(arr, row, col=0):
        if not isinstance(arr, list):
            return ""
        r = int(row) if _is_number(row) else 0
        c = int(col) if _is_number(col) else 0
        if isinstance(arr[0], list):
            if r < len(arr) and c < len(arr[r]):
                return arr[r][c]
        elif r < len(arr):
            return arr[r]
        return ""

    @staticmethod
    def _match(val, arr, exact=True):
        if not isinstance(arr, list):
            return "#N/A"
        v = str(val).strip().lower()
        for i, item in enumerate(arr):
            if (exact and str(item).strip().lower() == v) or (not exact and v in str(item).strip().lower()):
                return i + 1
        return "#N/A"

    @staticmethod
    def _text_fmt(v, fmt):
        try:
            n = float(v) if _is_number(v) else 0
            if fmt == "0.00": return f"{n:.2f}"
            if fmt == "0.0": return f"{n:.1f}"
            if fmt == "0%": return f"{n*100:.0f}%"
            if fmt == "0.00%": return f"{n*100:.2f}%"
            return str(v)
        except:
            return str(v)

    @staticmethod
    def _datedif(d1, d2, unit):
        try:
            from datetime import datetime
            if isinstance(d1, str): d1 = datetime.strptime(d1.strip()[:10], "%Y-%m-%d")
            if isinstance(d2, str): d2 = datetime.strptime(d2.strip()[:10], "%Y-%m-%d")
            delta = d2 - d1
            if unit.upper() == "D": return delta.days
            if unit.upper() == "M": return delta.days // 30
            if unit.upper() == "Y": return delta.days // 365
            return delta.days
        except:
            return "#VALUE!"

    @staticmethod
    def _rank(v, arr, order=0):
        vals = FormulaEngine._flatten_to_list(arr)
        try:
            n = float(v) if _is_number(v) else 0
            nums = sorted([float(x) for x in vals if _is_number(x)], reverse=(order==0))
            return nums.index(n) + 1 if n in nums else "#N/A"
        except:
            return "#VALUE!"

    @staticmethod
    def _stdev(*args):
        import math
        vals = [float(a) for a in FormulaEngine._flatten(*args) if _is_number(a)]
        if len(vals) < 2: return 0
        mean = sum(vals) / len(vals)
        variance = sum((x - mean)**2 for x in vals) / (len(vals) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _median(*args):
        vals = sorted([float(a) for a in FormulaEngine._flatten(*args) if _is_number(a)])
        if not vals: return 0
        n = len(vals)
        if n % 2 == 0:
            return (vals[n//2-1] + vals[n//2]) / 2
        return vals[n//2]

    @staticmethod
    def _mode(*args):
        vals = [float(a) for a in FormulaEngine._flatten(*args) if _is_number(a)]
        if not vals: return 0
        from collections import Counter
        return Counter(vals).most_common(1)[0][0]


# ─────────────── Helpers ───────────────
def _is_number(v: Any) -> bool:
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _is_truthy(v: Any) -> bool:
    if v is None or v == "" or v == 0 or v is False:
        return False
    if isinstance(v, str) and v.upper() in ("FALSE", "0", "NO"):
        return False
    return True


def _safe_div(a: float, b: float) -> float:
    return a / b if b != 0 else 0


# ─────────────── Test ───────────────
if __name__ == "__main__":
    # Quick sanity test
    sheet = {
        "test": [
            ["10", "20", "30"],
            ["5", "15", "25"],
            ["1", "2", "3"],
        ]
    }
    eng = FormulaEngine(sheet)
    item = "test"

    tests = [
        ("=A1+B1", 0, 0, "30"),       # 10+20
        ("=SUM(A1:A3)", 0, 0, "16"),   # 10+5+1
        ("=AVERAGE(B1:B3)", 0, 0, "12.3333"),  # (20+15+2)/3
        ("=IF(A1>5, C1, C2)", 0, 0, "30"),  # A1=10>5 → C1=30
        ("=ROUND(AVERAGE(A1:C1), 1)", 0, 0, "20"),
        ("=A1*2+B1", 0, 0, "40"),    # 10*2+20
    ]

    for formula, row, col, expected in tests:
        result = eng.evaluate(formula, item, row, col)
        status = "✓" if result == expected else f"✗ (got {result})"
        print(f"{status} {formula} = {result} (expected {expected})")
