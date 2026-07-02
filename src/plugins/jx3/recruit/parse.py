from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from src.const.jx3.server import Server


class _TokenKind(Enum):
    TERM = "term"
    AND = "and"
    OR = "or"
    LPAREN = "lparen"
    RPAREN = "rparen"


@dataclass(frozen=True)
class _Token:
    kind: _TokenKind
    value: str = ""


@dataclass(frozen=True)
class Atom:
    term: str


@dataclass(frozen=True)
class OrExpr:
    children: tuple[Expr, ...]


@dataclass(frozen=True)
class AndExpr:
    children: tuple[Expr, ...]


Expr = Atom | OrExpr | AndExpr


_TOKEN_PATTERN = re.compile(
    r"\s+|&&|[&|｜,，()]|[^&|｜,，()\s]+",
    re.UNICODE,
)


def _normalize_query(query: str) -> str:
    query = query.strip()
    query = re.sub(r"\s*&\s*", "&", query)
    query = re.sub(r"\s*\|\s*", "|", query)
    query = re.sub(r"\s*,\s*", ",", query)
    query = re.sub(r"\s+", " ", query)
    return query


def _tokenize(query: str) -> list[_Token]:
    tokens: list[_Token] = []
    for match in _TOKEN_PATTERN.finditer(query):
        raw = match.group()
        if not raw:
            continue
        if raw.isspace():
            if tokens and tokens[-1].kind == _TokenKind.AND:
                continue
            tokens.append(_Token(_TokenKind.AND))
            continue
        if raw == "&&" or raw == "&":
            if tokens and tokens[-1].kind == _TokenKind.AND:
                continue
            tokens.append(_Token(_TokenKind.AND))
        elif raw in {"|", "｜", ",", "，"}:
            tokens.append(_Token(_TokenKind.OR))
        elif raw == "(":
            tokens.append(_Token(_TokenKind.LPAREN))
        elif raw == ")":
            tokens.append(_Token(_TokenKind.RPAREN))
        else:
            tokens.append(_Token(_TokenKind.TERM, raw))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> _Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> _Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def _accept(self, kind: _TokenKind) -> bool:
        token = self._peek()
        if token and token.kind == kind:
            self._advance()
            return True
        return False

    def parse(self) -> Expr | None:
        if not self.tokens:
            return None
        expr = self._parse_and()
        if self._peek() is not None:
            raise ValueError("查询表达式存在无法解析的部分")
        return expr

    def _parse_and(self) -> Expr:
        nodes: list[Expr] = [self._parse_or()]
        while self._accept(_TokenKind.AND):
            nodes.append(self._parse_or())
        if len(nodes) == 1:
            return nodes[0]
        return AndExpr(tuple(nodes))

    def _parse_or(self) -> Expr:
        nodes: list[Expr] = [self._parse_primary()]
        while self._accept(_TokenKind.OR):
            nodes.append(self._parse_primary())
        if len(nodes) == 1:
            return nodes[0]
        return OrExpr(tuple(nodes))

    def _parse_primary(self) -> Expr:
        if self._accept(_TokenKind.LPAREN):
            expr = self._parse_and()
            if not self._accept(_TokenKind.RPAREN):
                raise ValueError("查询表达式缺少右括号")
            return expr
        token = self._peek()
        if token and token.kind == _TokenKind.TERM:
            self._advance()
            return Atom(token.value)
        raise ValueError("查询表达式不完整")


def parse_recruit_query(query: str) -> Expr | None:
    query = _normalize_query(query)
    if not query:
        return None
    return _Parser(_tokenize(query)).parse()


def parse_recruit_args(args: list[str], group_id: int) -> tuple[str | None, str]:
    """解析招募命令参数，返回 (区服, 查询表达式)。"""
    keywords = [arg for arg in args if arg]
    if not keywords:
        return Server(None, group_id).server, ""

    server_probe = Server(keywords[0], group_id)
    if server_probe.server_raw is not None:
        return server_probe.server, " ".join(keywords[1:])

    return Server(None, group_id).server, " ".join(keywords)


def recruit_text(detail: dict) -> str:
    return f"{detail.get('activity', '')}{detail.get('content', '')}"


def matches_expr(detail: dict, expr: Expr | None) -> bool:
    if expr is None:
        return True
    text = recruit_text(detail)
    return _eval_expr(expr, text)


def _eval_expr(expr: Expr, text: str) -> bool:
    if isinstance(expr, Atom):
        return expr.term in text
    if isinstance(expr, OrExpr):
        return any(_eval_expr(child, text) for child in expr.children)
    return all(_eval_expr(child, text) for child in expr.children)


def format_expr_label(expr: Expr | None) -> str:
    if expr is None:
        return "全部"
    if isinstance(expr, Atom):
        return expr.term
    if isinstance(expr, OrExpr):
        parts = [format_expr_label(child) for child in expr.children]
        inner = "|".join(parts)
        return f"({inner})" if len(parts) > 1 else inner
    parts = [format_expr_label(child) for child in expr.children]
    inner = "&".join(parts)
    return f"({inner})" if len(parts) > 1 else inner


def iter_atoms(expr: Expr) -> Iterator[str]:
    if isinstance(expr, Atom):
        yield expr.term
        return
    children = expr.children
    for child in children:
        yield from iter_atoms(child)


def pick_api_keywords(expr: Expr | None) -> list[str]:
    """选择用于 JX3API 预取的关键词。"""
    if expr is None:
        return []
    if isinstance(expr, Atom):
        return [expr.term]
    if isinstance(expr, AndExpr):
        for child in expr.children:
            keywords = pick_api_keywords(child)
            if keywords:
                return keywords
        return []
    result: list[str] = []
    for child in expr.children:
        for keyword in pick_api_keywords(child):
            if keyword not in result:
                result.append(keyword)
    return result


def recruit_identity(detail: dict) -> tuple:
    return (
        detail.get("activity"),
        detail.get("leader"),
        detail.get("createTime"),
        detail.get("content"),
    )
