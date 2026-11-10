"""策略 DSL 手写词法器 + 递归下降解析器。

语法（EBNF）::

    expr      := 'all' '(' expr (',' expr)* ')'
               | 'any' '(' expr (',' expr)* ')'
               | 'not' '(' expr ')'
               | predicate
    predicate := path op value
               | 'hasKey' '(' path ')'
               | 'count' '(' path ')' op number
               | 'startsWith' '(' path ',' string ')'
               | 'matches' '(' path ',' string ')'
    path      := ident ('.' ident | '[' '*' ']' | '[' number ']' | '[]')*
    op        := '==' | '!=' | '>=' | '<=' | '>' | '<'
    value     := string | number | 'true' | 'false' | 'null'

失败时抛 :class:`DslParseError`，带行号/列号/期望 token 列表与源码片段，
供 API 原样返回给前端做错误定位。**求值不在本模块发生**（见 dsl_eval.py），
且全链路不使用 eval()/exec()。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.config.settings import settings

LOGICAL_FUNCS = ("all", "any", "not")
PREDICATE_FUNCS = ("hasKey", "count", "startsWith", "matches")
ALL_FUNCS = LOGICAL_FUNCS + PREDICATE_FUNCS

_OPS = ("==", "!=", ">=", "<=", ">", "<")
_RELATIONAL = (">=", "<=", ">", "<")

_IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_IDENT_BODY = _IDENT_START | set("0123456789")


@dataclass
class Token:
    type: str
    text: str
    line: int
    column: int
    offset: int
    value: Any = None


@dataclass
class DslParseError(Exception):
    message: str
    line: int
    column: int
    expected: list[str] = field(default_factory=list)
    token_text: str = ""
    offset: int = 0
    source: str = ""

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def snippet(self) -> str:
        lines = self.source.splitlines() or [""]
        if 1 <= self.line <= len(lines):
            raw = lines[self.line - 1]
            caret = " " * max(0, self.column - 1) + "^"
            return f"{raw}\n{caret}"
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "expected": list(self.expected),
            "token": self.token_text,
            "offset": self.offset,
            "snippet": self.snippet(),
        }


class Lexer:
    """逐字符词法分析；只产出 token，不关心语法。"""

    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.pos = 0
        self.line = 1
        self.column = 1

    # ---- 基础游标 ----
    def _peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.source[index] if index < self.length else ""

    def _advance(self) -> str:
        char = self.source[self.pos]
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def _error(self, message: str, expected: list[str]) -> DslParseError:
        char = self._peek()
        return DslParseError(
            message=message,
            line=self.line,
            column=self.column,
            expected=expected,
            token_text=char,
            offset=self.pos,
            source=self.source,
        )

    def tokens(self) -> list[Token]:
        result: list[Token] = []
        while self.pos < self.length:
            char = self._peek()
            if char in " \t\r\n":
                self._advance()
                continue
            if char == "#":
                while self.pos < self.length and self._peek() != "\n":
                    self._advance()
                continue
            line, column, offset = self.line, self.column, self.pos
            if char in _IDENT_START:
                text = self._read_ident()
                result.append(Token("IDENT", text, line, column, offset))
                continue
            if char.isdigit() or (char == "-" and self._peek(1).isdigit()):
                raw = self._read_number_like()
                result.append(Token("NUMBER", raw, line, column, offset))
                continue
            if char in ('"', "'"):
                quote = char
                self._advance()
                text = self._read_string(quote)
                result.append(Token("STRING", text, line, column, offset, value=text))
                continue
            two = char + self._peek(1)
            if two in _OPS:
                self._advance()
                self._advance()
                result.append(Token("OP", two, line, column, offset))
                continue
            if two == "=="[:1] or char in "><":
                self._advance()
                result.append(Token("OP", char, line, column, offset))
                continue
            single_map = {
                "(": "LPAREN",
                ")": "RPAREN",
                "[": "LBRACKET",
                "]": "RBRACKET",
                ".": "DOT",
                ",": "COMMA",
                "*": "STAR",
            }
            if char in single_map:
                self._advance()
                result.append(Token(single_map[char], char, line, column, offset))
                continue
            raise self._error(f"非法字符 {char!r}", ["运算符", "标识符", "字面量", "括号"])
        result.append(Token("EOF", "", self.line, self.column, self.pos))
        return result

    def _read_ident(self) -> str:
        chars = []
        while self.pos < self.length and self._peek() in _IDENT_BODY:
            chars.append(self._advance())
        return "".join(chars)

    def _read_number_like(self) -> str:
        chars = []
        if self._peek() == "-":
            chars.append(self._advance())
        while self.pos < self.length and self._peek().isdigit():
            chars.append(self._advance())
        if self._peek() == "." and self._peek(1).isdigit():
            chars.append(self._advance())
            while self.pos < self.length and self._peek().isdigit():
                chars.append(self._advance())
        if self._peek() in "eE":
            save = self.pos
            candidate = [self._advance()]
            if self._peek() in "+-":
                candidate.append(self._advance())
            if self._peek().isdigit():
                while self.pos < self.length and self._peek().isdigit():
                    candidate.append(self._advance())
                chars.extend(candidate)
            else:
                self.pos = save  # 不是指数，回退
        # K8s quantity 后缀：Ki/Mi/Gi/Ti/m/k/M/G
        suffix = []
        while self.pos < self.length and self._peek().isalpha() and len(suffix) < 2:
            suffix.append(self._advance())
        if suffix:
            chars.append("".join(suffix))
        return "".join(chars)

    def _read_string(self, quote: str) -> str:
        chars = []
        while self.pos < self.length:
            char = self._advance()
            if char == "\\":
                esc = self._advance() if self.pos < self.length else ""
                mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}
                chars.append(mapping.get(esc, esc))
                continue
            if char == quote:
                return "".join(chars)
            chars.append(char)
        raise DslParseError(
            message="字符串缺少结束引号",
            line=self.line,
            column=self.column,
            expected=[quote],
            token_text="",
            offset=self.pos,
            source=self.source,
        )


class Parser:
    """递归下降：一次只向前看一个 token。"""

    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = Lexer(source).tokens()
        self.index = 0
        self.depth = 0
        self.predicate_count = 0
        self.path_count = 0

    # ---- token 工具 ----
    def _peek(self) -> Token:
        return self.tokens[self.index]

    def _next(self) -> Token:
        token = self.tokens[self.index]
        if token.type != "EOF":
            self.index += 1
        return token

    def _error(self, message: str, expected: list[str], token: Token | None = None) -> DslParseError:
        token = token or self._peek()
        return DslParseError(
            message=message,
            line=token.line,
            column=token.column,
            expected=expected,
            token_text=token.text,
            offset=token.offset,
            source=self.source,
        )

    def _expect(self, token_type: str, expected: list[str]) -> Token:
        token = self._peek()
        if token.type != token_type:
            raise self._error(f"期望 {'/'.join(expected)}，实际得到 {token.text or 'EOF'!r}", expected, token)
        return self._next()

    # ---- 入口 ----
    def parse(self) -> dict[str, Any]:
        ast = self._parse_expr()
        if self._peek().type != "EOF":
            raise self._error(
                f"表达式结束后出现多余 token {self._peek().text!r}",
                ["表达式结束（EOF）"],
            )
        return {
            "ast": ast,
            "predicate_count": self.predicate_count,
            "path_count": self.path_count,
            "max_depth": self._max_depth(ast),
            "summary": summarize_ast(ast),
        }

    def _parse_expr(self) -> dict[str, Any]:
        self.depth += 1
        if self.depth > settings.DSL_MAX_DEPTH:
            raise self._error(
                f"表达式嵌套超过 {settings.DSL_MAX_DEPTH} 层", ["更浅的嵌套"]
            )
        try:
            token = self._peek()
            if token.type != "IDENT":
                raise self._error(
                    f"期望谓词或逻辑函数，实际得到 {token.text or 'EOF'!r}",
                    list(LOGICAL_FUNCS),
                    token,
                )
            name = token.text
            next_token = self.tokens[self.index + 1] if self.index + 1 < len(self.tokens) else token
            is_call = next_token.type == "LPAREN"
            if is_call and name not in ALL_FUNCS:
                raise self._error(
                    f"未知函数 {name!r}；策略表达式只支持 "
                    f"all/any/not/hasKey/count/startsWith/matches",
                    list(ALL_FUNCS),
                    token,
                )
            if name in LOGICAL_FUNCS:
                return self._parse_logical(name)
            if name == "hasKey":
                return self._parse_has_key()
            if name == "count":
                return self._parse_count()
            if name in ("startsWith", "matches"):
                return self._parse_string_fn(name)
            if is_call:
                raise self._error(f"未知函数 {name!r}", list(ALL_FUNCS), token)
            return self._parse_compare()
        finally:
            self.depth -= 1

    def _parse_logical(self, name: str) -> dict[str, Any]:
        self._next()  # 函数名
        self._expect("LPAREN", ["("])
        args: list[dict[str, Any]] = []
        if name == "not":
            args.append(self._parse_expr())
            self._expect("RPAREN", [")"])
        else:
            args.append(self._parse_expr())
            while self._peek().type == "COMMA":
                self._next()
                args.append(self._parse_expr())
            self._expect("RPAREN", [")", ","])
        if name == "not" and len(args) != 1:
            raise self._error("not() 只接受 1 个子表达式", [")"])
        return {"type": "logical", "op": name, "args": args}

    def _parse_has_key(self) -> dict[str, Any]:
        self._next()
        self._expect("LPAREN", ["("])
        path = self._parse_path()
        self._expect("RPAREN", [")"])
        self.predicate_count += 1
        return {"type": "hasKey", "path": path}

    def _parse_count(self) -> dict[str, Any]:
        self._next()
        self._expect("LPAREN", ["("])
        path = self._parse_path()
        self._expect("RPAREN", [")"])
        op_token = self._peek()
        if op_token.type != "OP":
            raise self._error(
                f"count() 后需要比较运算符，实际得到 {op_token.text or 'EOF'!r}",
                list(_OPS),
                op_token,
            )
        op = self._next().text
        if op in _RELATIONAL:
            self._require_number_literal(op)
        value = self._parse_value()
        if value["kind"] != "number":
            raise self._error(
                "count() 的比较值必须是数字", ["数字字面量"], op_token
            )
        self.predicate_count += 1
        return {"type": "count", "path": path, "op": op, "value": value}

    def _parse_string_fn(self, name: str) -> dict[str, Any]:
        self._next()
        self._expect("LPAREN", ["("])
        path = self._parse_path()
        self._expect("COMMA", [","])
        literals = self._parse_value()
        if literals["kind"] != "string":
            raise self._error(f"{name}() 第二个参数必须是字符串", ["字符串字面量"])
        if name == "matches":
            self._validate_regex(literals["value"], literals.get("offset"))
        self._expect("RPAREN", [")", ","])
        self.predicate_count += 1
        return {"type": "stringFn", "fn": name, "path": path, "arg": literals["value"]}

    def _validate_regex(self, pattern: str, offset: int | None) -> None:
        if len(pattern) > settings.REGEX_MAX_LENGTH:
            raise self._error(
                f"matches() 正则长度超过 {settings.REGEX_MAX_LENGTH} 字符", ["更短的正则"]
            )
        if re.search(r"\([^)]*[+*][^)]*\)[+*]", pattern):
            raise self._error(
                "matches() 正则不允许嵌套量词（防止灾难性回溯）", ["线性正则"]
            )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise self._error(f"matches() 正则非法：{exc}", ["合法正则"]) from exc

    def _parse_compare(self) -> dict[str, Any]:
        path = self._parse_path()
        op_token = self._peek()
        if op_token.type != "OP":
            raise self._error(
                f"路径 {path['raw']!r} 后需要比较运算符，实际得到 {op_token.text or 'EOF'!r}",
                list(_OPS),
                op_token,
            )
        op = self._next().text
        if op in _RELATIONAL:
            self._require_number_literal(op)
        value = self._parse_value()
        self.predicate_count += 1
        return {"type": "compare", "path": path, "op": op, "value": value}

    def _require_number_literal(self, op: str) -> None:
        token = self._peek()
        if token.type != "NUMBER" and not (
            token.type == "IDENT" and token.text in ("true", "false", "null")
        ):
            raise self._error(
                f"运算符 {op} 只支持数字字面量", ["数字字面量"], token
            )

    def _parse_path(self) -> dict[str, Any]:
        first = self._peek()
        if first.type != "IDENT":
            raise self._error(
                f"路径需要以字段名开始，实际得到 {first.text or 'EOF'!r}",
                ["字段名"],
                first,
            )
        segments: list[dict[str, Any]] = []
        raw_parts: list[str] = []
        segments.append({"kind": "field", "name": self._next().text})
        raw_parts.append(segments[-1]["name"])
        while True:
            token = self._peek()
            if token.type == "DOT":
                self._next()
                name_token = self._peek()
                if name_token.type != "IDENT":
                    raise self._error(
                        f". 后需要字段名，实际得到 {name_token.text or 'EOF'!r}",
                        ["字段名"],
                        name_token,
                    )
                segments.append({"kind": "field", "name": self._next().text})
                raw_parts.append("." + segments[-1]["name"])
            elif token.type == "LBRACKET":
                self._next()
                inner = self._peek()
                if inner.type == "STAR":
                    self._next()
                    self._expect("RBRACKET", ["]"])
                    segments.append({"kind": "wildcard"})
                    raw_parts.append("[*]")
                elif inner.type == "NUMBER" and inner.text.isdigit():
                    self._next()
                    self._expect("RBRACKET", ["]"])
                    segments.append({"kind": "index", "index": int(inner.text)})
                    raw_parts.append(f"[{inner.text}]")
                elif inner.type == "RBRACKET":
                    self._next()
                    segments.append({"kind": "wildcard"})
                    raw_parts.append("[]")
                else:
                    raise self._error(
                        "[] 内只能是 * 或非负整数下标",
                        ["*", "整数", "]"],
                        inner,
                    )
            else:
                break
        self.path_count += 1
        return {"raw": "".join(raw_parts), "segments": segments}

    def _parse_value(self) -> dict[str, Any]:
        token = self._peek()
        if token.type == "STRING":
            self._next()
            return {"kind": "string", "value": token.text, "offset": token.offset}
        if token.type == "NUMBER":
            self._next()
            return {"kind": "number", **self._convert_number(token)}
        if token.type == "IDENT":
            lowered = token.text
            if lowered == "true":
                self._next()
                return {"kind": "bool", "value": True}
            if lowered == "false":
                self._next()
                return {"kind": "bool", "value": False}
            if lowered == "null":
                self._next()
                return {"kind": "null", "value": None}
            raise self._error(
                f"未知字面量 {token.text!r}",
                ["字符串", "数字", "true", "false", "null"],
                token,
            )
        raise self._error(
            f"期望比较值，实际得到 {token.text or 'EOF'!r}",
            ["字符串", "数字", "true", "false", "null"],
            token,
        )

    def _convert_number(self, token: Token) -> dict[str, Any]:
        raw = token.text
        import re as _re

        match = _re.fullmatch(
            r"(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(Ki|Mi|Gi|Ti|Pi|Ei|n|u|m|k|M|G|T|P|E)?",
            raw,
        )
        if not match:
            raise self._error(f"数字字面量非法：{raw!r}", ["数字"], token)
        number_text, unit = match.group(1), match.group(2)
        numeric = float(number_text)
        if unit:
            from src.services.quota import apply_quantity_unit

            numeric = apply_quantity_unit(numeric, unit)
        value: float | int = int(numeric) if numeric == int(numeric) and not unit else numeric
        return {"value": value, "raw": raw}

    def _max_depth(self, node: dict[str, Any]) -> int:
        if node.get("type") == "logical":
            children = node.get("args") or []
            return 1 + max((self._max_depth(child) for child in children), default=0)
        return 1


def summarize_ast(ast: dict[str, Any]) -> str:
    """给前端一行 AST 摘要，例如 all(2 项: hasKey(spec...) …)。"""
    def render(node: dict[str, Any]) -> str:
        node_type = node.get("type")
        if node_type == "logical":
            inner = ", ".join(render(child) for child in node.get("args", []))
            return f"{node['op']}({inner})"
        if node_type == "hasKey":
            return f"hasKey({node['path']['raw']})"
        if node_type == "count":
            return f"count({node['path']['raw']}) {node['op']} {_fmt(node['value'])}"
        if node_type == "stringFn":
            return f"{node['fn']}({node['path']['raw']}, {node['arg']!r})"
        if node_type == "compare":
            return f"{node['path']['raw']} {node['op']} {_fmt(node['value'])}"
        return "?"

    def _fmt(value: dict[str, Any]) -> str:
        kind = value.get("kind")
        if kind == "string":
            return repr(value.get("value"))
        if kind == "null":
            return "null"
        if kind == "bool":
            return "true" if value.get("value") else "false"
        raw = value.get("raw")
        return raw if raw is not None else str(value.get("value"))

    return render(ast)


def parse_dsl(source: str) -> dict[str, Any]:
    """解析入口：返回 ast / 统计 / 摘要；失败抛 DslParseError。"""
    if not source or not source.strip():
        raise DslParseError(
            message="策略 DSL 不能为空",
            line=1,
            column=1,
            expected=["all(...)", "any(...)", "not(...)", "谓词"],
            source=source or "",
        )
    if len(source) > settings.DSL_MAX_LENGTH:
        raise DslParseError(
            message=f"策略 DSL 超过 {settings.DSL_MAX_LENGTH} 字符上限",
            line=1,
            column=1,
            expected=["更短的表达式"],
            source=source,
        )
    return Parser(source).parse()
