import re
from collections.abc import Generator
from typing import Any

from mapchar.generator.exceptions import ExprError
from mapchar.generator.nodes import BindDefNode, BindRefNode, FileNode, Node
from mapchar.utils.classes import pattern_repl


class MapcharGenerator:
    BRACES_RE = re.compile(r"\{(\d+)(?:\s*,\s*(\d+))?\}")
    RANGE_RE = re.compile(r"\s*([0-9]+)\s*-\s*([0-9]+)\s*(?::\s*([+-]?\d+)\s*)?$")

    def _unreachable_error(self, token: str) -> ExprError:
        """Create a standardized 'unreachable token' error."""
        return ExprError(f"Pattern does not produce word {token!r}")

    def _find_closing(self, s: str, start: int, closer: str) -> int:
        i = start
        n = len(s)
        while i < n:
            ch = s[i]
            if ch == "\\":
                i += 2
                continue
            if ch == closer:
                return i
            i += 1
        return -1

    def _find_binding_close(self, s: str, start: int) -> int:
        """Find the closing '>' of a <@...> binding, correctly skipping nested brackets."""
        i = start
        n = len(s)
        depth_square = 0
        depth_paren = 0
        depth_brace = 0
        while i < n:
            ch = s[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "[":
                depth_square += 1
            elif ch == "]":
                if depth_square > 0:
                    depth_square -= 1
            elif ch == "(":
                depth_paren += 1
            elif ch == ")":
                if depth_paren > 0:
                    depth_paren -= 1
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                if depth_brace > 0:
                    depth_brace -= 1
            elif (
                ch == ">"
                and depth_square == 0
                and depth_paren == 0
                and depth_brace == 0
            ):
                return i
            i += 1
        return -1

    def _parse_range(self, pattern: str, start_idx: int) -> tuple[list[str], int]:
        end_pos = self._find_closing(pattern, start_idx, "]")
        if end_pos == -1:
            raise ExprError(
                "Unclosed range (missing ']')", error_pos=(pattern, start_idx)
            )
        inner = pattern[start_idx:end_pos]
        m = self.RANGE_RE.match(inner)
        if not m:
            raise ExprError(
                "Invalid range syntax (expected '#[START-END[:STEP]]')",
                error_pos=(pattern, start_idx),
            )
        r_start = int(m.group(1))
        r_end = int(m.group(2))
        step_str = m.group(3)
        step = int(step_str) if step_str else (1 if r_start <= r_end else -1)
        if step == 0:
            raise ExprError("Range step cannot be zero", error_pos=(pattern, start_idx))
        if r_start < 0 or r_end < 0:
            raise ExprError(
                "Range bounds must be non-negative", error_pos=(pattern, start_idx)
            )
        if (step > 0 and r_start > r_end) or (step < 0 and r_start < r_end):
            raise ExprError("Invalid range sequence", error_pos=(pattern, start_idx))
        if step > 0:
            rng = range(r_start, r_end + 1, step)
        else:
            rng = range(r_start, r_end - 1, step)
        choices = [str(x) for x in rng]
        if not choices:
            raise ExprError("Range produced no values", error_pos=(pattern, start_idx))
        return choices, end_pos + 1

    def _parse_class(
        self, pattern: str, start_idx: int, literal_mode: bool
    ) -> tuple[list[str], int]:
        closer = ")" if literal_mode else "]"
        end_pos = self._find_closing(pattern, start_idx, closer)
        if end_pos == -1:
            raise ExprError(
                f"Unclosed character class (missing {closer!r})",
                error_pos=(pattern, start_idx),
            )
        inner = pattern[start_idx:end_pos]
        if not inner:
            raise ExprError(
                "Empty character class is not allowed", error_pos=(pattern, start_idx)
            )
        if literal_mode:
            return [inner], end_pos + 1
        if "|" not in inner:
            choices: list[str] = []
            escape = False
            for ch in inner:
                if escape:
                    choices.append(ch)
                    escape = False
                elif ch == "\\":
                    escape = True
                else:
                    choices.append(ch)
            if not choices:
                raise ExprError(
                    "Invalid character class contents", error_pos=(pattern, start_idx)
                )
            return choices, end_pos + 1

        segments: list[str] = []
        buf: list[str] = []
        escape = False
        for ch in inner:
            if escape:
                buf.append(ch)
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "|":
                segments.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        segments.append("".join(buf))
        choices = [s.strip() for s in segments if s.strip()]
        if not choices:
            raise ExprError(
                "Invalid character class contents", error_pos=(pattern, start_idx)
            )
        return choices, end_pos + 1

    def _tokenize_raw(self, pattern: str) -> list[tuple[str, Any]]:
        """Core tokenization loop (pattern_repl must already have been applied)."""
        i = 0
        n = len(pattern)
        tokens: list[tuple[str, Any]] = []
        pr = pattern
        BR = self.BRACES_RE
        while i < n:
            c = pr[i]
            if c == "\\":
                if i + 1 >= n:
                    raise ExprError(
                        "Invalid escape sequence (trailing backslash)",
                        error_pos=(pattern, i + 1),
                    )
                tokens.append(("LIT", pr[i + 1]))
                i += 2
                continue
            if c == "<":
                if i + 1 < n and pr[i + 1] == "@":
                    end = self._find_binding_close(pr, i + 2)
                    if end == -1:
                        raise ExprError(
                            "Unclosed binding (missing '>')", error_pos=(pattern, i + 1)
                        )
                    inner = pr[i + 2 : end]
                    eq_pos = inner.find("=")
                    if eq_pos == -1:
                        name = inner.strip()
                        if not name.isidentifier():
                            raise ExprError(
                                f"Invalid binding name {name!r}",
                                error_pos=(pattern, i + 1),
                            )
                        tokens.append(("BIND_REF", name))
                    else:
                        name = inner[:eq_pos].strip()
                        expr = inner[eq_pos + 1 :]
                        if not name.isidentifier():
                            raise ExprError(
                                f"Invalid binding name {name!r}",
                                error_pos=(pattern, i + 1),
                            )
                        inner_tokens = self._tokenize_raw(expr)
                        tokens.append(("BIND_DEF", (name, inner_tokens)))
                    i = end + 1
                    continue
                tokens.append(("LIT", "<"))
                i += 1
                continue
            if c == "#":
                if i + 1 < n and pr[i + 1] == "[":
                    choices, new_i = self._parse_range(pr, i + 2)
                    tokens.append(("RANGE", choices))
                    i = new_i
                else:
                    tokens.append(("LIT", "#"))
                    i += 1
                continue
            if c == "(":
                choices, new_i = self._parse_class(pr, i + 1, literal_mode=True)
                tokens.append(("CLASS", choices))
                i = new_i
                continue
            if c == "[":
                choices, new_i = self._parse_class(pr, i + 1, literal_mode=False)
                tokens.append(("CLASS", choices))
                i = new_i
                continue
            if c == "?":
                tokens.append(("QMARK", None))
                i += 1
                continue
            if c == "^":
                tokens.append(("FILE", None))
                i += 1
                continue
            if c == "{":
                m = BR.match(pr[i:])
                if m:
                    a = int(m.group(1))
                    b = int(m.group(2)) if m.group(2) is not None else a
                    if a > b:
                        raise ExprError(
                            "Invalid repetition range (min > max)",
                            error_pos=(pattern, i + 1),
                        )
                    tokens.append(("BRACES", (a, b)))
                    i += m.end()
                    continue
                else:
                    raise ExprError(
                        "Invalid repetition syntax", error_pos=(pattern, i + 1)
                    )
            tokens.append(("LIT", c))
            i += 1
        return tokens

    def tokenize(self, pattern: str) -> list[list[tuple[str, Any]]]:
        pr = pattern_repl(pattern)
        expressions: list[str] = []
        buf: list[str] = []
        i = 0
        n = len(pr)
        depth_square = 0
        depth_paren = 0
        depth_brace = 0
        depth_bind = 0

        while i < n:
            ch = pr[i]
            if ch == "\\":
                buf.append(ch)
                if i + 1 < n:
                    buf.append(pr[i + 1])
                    i += 2
                else:
                    i += 1
                continue

            if ch == "[":
                depth_square += 1
            elif ch == "]":
                if depth_square > 0:
                    depth_square -= 1
            elif ch == "(":
                depth_paren += 1
            elif ch == ")":
                if depth_paren > 0:
                    depth_paren -= 1
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                if depth_brace > 0:
                    depth_brace -= 1
            elif ch == "<":
                if i + 1 < n and pr[i + 1] == "@":
                    depth_bind += 1
            elif ch == ">":
                if (
                    depth_bind > 0
                    and depth_square == 0
                    and depth_paren == 0
                    and depth_brace == 0
                ):
                    depth_bind -= 1
            elif ch == "|" and i + 1 < n and pr[i + 1] == "|":
                if (
                    depth_square == 0
                    and depth_paren == 0
                    and depth_brace == 0
                    and depth_bind == 0
                ):
                    expressions.append("".join(buf))
                    buf = []
                    i += 2
                    continue

            buf.append(ch)
            i += 1

        expressions.append("".join(buf))
        return [self._tokenize_raw(expr) for expr in expressions]

    def _parse_tokens(
        self,
        tokens: list[tuple[str, Any]],
        file_groups: list[list[str]],
        file_idx: int,
    ) -> tuple[list, int]:
        """Parse a flat token list into nodes, returning (nodes, updated_file_idx)."""
        nodes: list = []
        i = 0
        length = len(tokens)
        while i < length:
            kind, val = tokens[i]
            min_rep = 1
            max_rep = 1
            if i + 1 < length:
                next_k, next_v = tokens[i + 1]
                if next_k == "QMARK":
                    min_rep, max_rep = 0, 1
                    i += 1
                elif next_k == "BRACES":
                    min_rep, max_rep = next_v
                    i += 1
            if kind == "LIT":
                if (
                    nodes
                    and type(nodes[-1]) is Node
                    and nodes[-1].min_rep == 1
                    and nodes[-1].max_rep == 1
                    and len(nodes[-1].base) == 1
                    and min_rep == 1
                    and max_rep == 1
                ):
                    nodes[-1].base[0] += val
                else:
                    nodes.append(Node(val, min_rep, max_rep))
            elif kind == "CLASS" or kind == "RANGE":
                nodes.append(Node(val, min_rep, max_rep))
            elif kind == "FILE":
                if file_idx >= len(file_groups):
                    raise ExprError("Insufficient file assignments")
                nodes.append(FileNode(file_groups[file_idx], min_rep, max_rep))
                file_idx += 1
            elif kind == "BIND_DEF":
                name, inner_tokens = val
                inner_nodes, file_idx = self._parse_tokens(
                    inner_tokens, file_groups, file_idx
                )
                nodes.append(BindDefNode(name, inner_nodes, min_rep, max_rep))
            elif kind == "BIND_REF":
                nodes.append(BindRefNode(val, min_rep, max_rep))
            else:
                raise ExprError(f"Unexpected token {kind!r}")
            i += 1
        return nodes, file_idx

    def _count_file_tokens(self, tokens: list[tuple[str, Any]]) -> int:
        """Recursively count FILE tokens, including those inside BIND_DEF inner_tokens."""
        count = 0
        for kind, val in tokens:
            if kind == "FILE":
                count += 1
            elif kind == "BIND_DEF":
                _, inner_tokens = val
                count += self._count_file_tokens(inner_tokens)
        return count

    def parse(
        self, tokens_multi: list[list[tuple[str, Any]]], files: list[str] | None = None
    ) -> list[list[Any]]:
        nodes: list[list[Any]] = []
        files = files or []
        file_idx = 0
        for tokens in tokens_multi:
            count_ft = self._count_file_tokens(tokens)
            if count_ft:
                if len(files) - file_idx < count_ft:
                    raise ExprError(
                        f"Pattern requires {count_ft} files but {(len(files) - file_idx)} were provided"
                    )
                file_groups = [[f] for f in files[file_idx : file_idx + count_ft]]
                file_idx += count_ft
            else:
                file_groups = []
            expr_nodes, _ = self._parse_tokens(tokens, file_groups, 0)
            nodes.append(expr_nodes)

        return nodes

    def _combine_resume(
        self,
        nodes: list,
        idx: int,
        start_token: str | None,
        bindings: dict[str, str] | None = None,
    ) -> Generator[str]:
        """recursive word combination generator with resume logic and binding support."""
        if bindings is None:
            bindings = {}
        ln = len(nodes)
        if idx >= ln:
            if not start_token:
                yield ""
            return
        cur = nodes[idx]

        if isinstance(cur, BindDefNode):
            if cur.min_rep == 1 and cur.max_rep == 1:
                inner_vals_gen = self._combine_resume(cur.inner_nodes, 0, None, {})
            else:
                base_vals = list(self._combine_resume(cur.inner_nodes, 0, None, {}))

                def _rep_gen(base: list[str], mn: int, mx: int) -> Generator[str]:
                    for r in range(mn, mx + 1):
                        for val in base:
                            yield val * r if r > 0 else ""

                inner_vals_gen = _rep_gen(base_vals, cur.min_rep, cur.max_rep)
            for val in inner_vals_gen:
                new_bindings = {**bindings, cur.name: val}
                for suffix in self._combine_resume(nodes, idx + 1, None, new_bindings):
                    yield val + suffix
            return

        if isinstance(cur, BindRefNode):
            if cur.name not in bindings:
                raise ExprError(f"Undefined variable {cur.name!r}")
            val_base = bindings[cur.name]
            for r in range(cur.min_rep, cur.max_rep + 1):
                val = val_base * r if r > 0 else ""
                if start_token is None:
                    next_target = None
                elif start_token.startswith(val):
                    next_target = start_token[len(val) :]
                elif val.startswith(start_token):
                    next_target = None
                else:
                    continue
                for suffix in self._combine_resume(
                    nodes, idx + 1, next_target, bindings
                ):
                    yield val + suffix
            return

        if start_token is None:
            for part in cur.expand():
                for suffix in self._combine_resume(nodes, idx + 1, None, bindings):
                    yield part + suffix
            return

        for part, remainder, is_full_mode in cur.expand_resume(start_token):
            next_target = None if is_full_mode else remainder
            for suffix in self._combine_resume(nodes, idx + 1, next_target, bindings):
                yield part + suffix

    def generate(
        self,
        nodes: list[list[Node | FileNode]],
        start_token: str | None = None,
        end_token: str | None = None,
    ) -> Generator[str]:
        """starts the wordlist generation, optionally bounded by start_token and end_token."""
        found_start = start_token is None

        for expr_nodes in nodes:
            if not found_start:
                if start_token is not None:
                    try:
                        self._calculate_skipped_stats(expr_nodes, start_token)
                        found_start = True
                        iterator = self._combine_resume(expr_nodes, 0, start_token)
                    except ExprError:
                        continue
                else:
                    found_start = True
                    iterator = self._combine_resume(expr_nodes, 0, None)
            else:
                iterator = self._combine_resume(expr_nodes, 0, None)

            for item in iterator:
                yield item

                if end_token and item == end_token:
                    return

    def _get_suffix_capacity(self, nodes: list[Node | FileNode], start_idx: int) -> int:
        """calculates total combinations of subsequent nodes."""
        total = 1
        for i in range(start_idx, len(nodes)):
            total *= nodes[i].cardinality
        return total

    def _calculate_skipped_stats(self, nodes: list, target: str) -> tuple[int, int]:
        """calculates how many (words, bytes) exist strictly before 'target'."""
        skipped_count = 0
        skipped_bytes = 0
        current_target = target
        current_prefix_len = 0
        bindings: dict[str, str] = {}
        local_binding_stats: dict[str, tuple[int, int]] = {}

        for i, node in enumerate(nodes):
            if isinstance(node, BindDefNode):
                inner_bytes, inner_count = self._stats_single(
                    node.inner_nodes, delimiter_len=0, binding_stats=local_binding_stats
                )
                avg_len = inner_bytes // inner_count if inner_count > 0 else 0
                local_binding_stats[node.name] = (inner_count, avg_len)

            suffix_bytes, suffix_count = self._stats_single(
                nodes[i + 1 :], delimiter_len=0, binding_stats=local_binding_stats
            )

            if isinstance(node, BindDefNode):
                inner_idx = 0
                inner_bytes_skipped = 0
                found_val: str | None = None

                for val in self._combine_resume(node.inner_nodes, 0, None, bindings):
                    val_b = len(val.encode("utf-8"))
                    if current_target.startswith(val):
                        found_val = val
                        break
                    inner_idx += 1
                    inner_bytes_skipped += val_b

                if found_val is None:
                    raise self._unreachable_error(target)

                skipped_count += inner_idx * suffix_count
                skipped_bytes += (
                    (inner_bytes_skipped * suffix_count)
                    + (inner_idx * suffix_count * current_prefix_len)
                    + (inner_idx * suffix_bytes)
                )

                bindings[node.name] = found_val
                val_b = len(found_val.encode("utf-8"))
                current_prefix_len += val_b
                current_target = current_target[val_b:]

            elif isinstance(node, BindRefNode):
                if node.name not in bindings:
                    raise ExprError(f"Undefined variable {node.name!r}")
                val = bindings[node.name]
                val_b = len(val.encode("utf-8"))

                if node.min_rep != node.max_rep:
                    found_r = None
                    for r in range(node.min_rep, node.max_rep + 1):
                        out = val * r if r > 0 else ""
                        out_b = len(out.encode("utf-8"))
                        if current_target.startswith(out):
                            found_r = r
                            break
                        skipped_count += suffix_count
                        skipped_bytes += suffix_bytes + (
                            suffix_count * (current_prefix_len + out_b)
                        )

                    if found_r is None:
                        raise self._unreachable_error(target)

                    current_prefix_len += len((val * found_r).encode("utf-8"))
                    current_target = current_target[len(val * found_r) :]
                else:
                    out = val * node.min_rep if node.min_rep > 0 else ""
                    if not current_target.startswith(out):
                        raise self._unreachable_error(target)
                    current_prefix_len += len(out.encode("utf-8"))
                    current_target = current_target[len(out) :]

            else:
                n_count, n_bytes, remainder = node.get_skipped_stats(
                    current_target, current_prefix_len
                )

                skipped_count += n_count * suffix_count
                skipped_bytes += (n_bytes * suffix_count) + (n_count * suffix_bytes)

                if remainder is None:
                    raise self._unreachable_error(target)

                consumed = current_target[: len(current_target) - len(remainder)]
                current_prefix_len += len(consumed.encode("utf-8"))
                current_target = remainder

        if current_target != "":
            raise self._unreachable_error(target)

        return skipped_count, skipped_bytes

    def _calculate_skipped_stats_multi(
        self, nodes: list[list[Any]], target: str
    ) -> tuple[int, int]:
        skipped_count = 0
        skipped_bytes = 0
        for expr_nodes in nodes:
            try:
                c, b = self._calculate_skipped_stats(expr_nodes, target)
                return skipped_count + c, skipped_bytes + b
            except ExprError:
                full_b, full_c = self._stats_single(expr_nodes, delimiter_len=0)
                skipped_count += full_c
                skipped_bytes += full_b
        raise self._unreachable_error(target)

    def get_word_at_index(self, nodes: list, index: int) -> str:
        """retrieves the word at a specific index."""
        result: list[str] = []
        bindings: dict[str, str] = {}
        for i, node in enumerate(nodes):
            suffix_cap = self._get_suffix_capacity(nodes, i + 1)
            if isinstance(node, BindDefNode):
                inner_vals = list(self._combine_resume(node.inner_nodes, 0, None, {}))
                node_idx = index // suffix_cap
                index %= suffix_cap
                val = inner_vals[node_idx]
                bindings[node.name] = val
                result.append(val)
            elif isinstance(node, BindRefNode):
                if node.name not in bindings:
                    raise ExprError(f"Undefined variable {node.name!r}")
                val_base = bindings[node.name]
                if node.min_rep != node.max_rep:
                    node_idx = index // suffix_cap
                    index %= suffix_cap
                    r = node.min_rep + node_idx
                    result.append(val_base * r if r > 0 else "")
                else:
                    result.append(val_base * node.min_rep if node.min_rep > 0 else "")
            else:
                node_idx = index // suffix_cap
                index %= suffix_cap
                result.append(node.get_item_at(node_idx))
        return "".join(result)

    def get_word_at_index_multi(self, nodes: list[list[Any]], index: int) -> str:
        word, _ = self.get_word_and_expr_at_index(nodes, index)
        return word

    def get_word_and_expr_at_index(
        self, nodes: list[list[Any]], index: int
    ) -> tuple[str, int]:
        for idx, expr_nodes in enumerate(nodes):
            _, full_c = self._stats_single(expr_nodes, delimiter_len=0)
            if index < full_c:
                return self.get_word_at_index(expr_nodes, index), idx
            index -= full_c
        raise ExprError("Index out of bounds")

    def _stats_single(
        self,
        nodes: list,
        delimiter_len: int = 1,
        binding_stats: dict[str, tuple[int, int]] | None = None,
    ) -> tuple[int, int]:
        total_count = 1
        total_bytes = 0
        if binding_stats is None:
            binding_stats = {}
        else:
            binding_stats = dict(binding_stats)

        for node in nodes:
            if isinstance(node, BindDefNode):
                inner_bytes, inner_count = self._stats_single(
                    node.inner_nodes, delimiter_len=0
                )
                node_count = 0
                node_bytes = 0
                min_r, max_r = node.min_rep, node.max_rep

                for r in range(min_r, max_r + 1):
                    node_count += inner_count
                    node_bytes += r * inner_bytes

                avg_len = node_bytes // node_count if node_count > 0 else 0
                binding_stats[node.name] = (node_count, avg_len)
            elif isinstance(node, BindRefNode):
                if node.name not in binding_stats:
                    raise ExprError(f"Undefined variable {node.name!r}")
                _, avg_len = binding_stats[node.name]
                min_r, max_r = node.min_rep, node.max_rep
                node_count = max_r - min_r + 1
                node_bytes = sum(r * avg_len for r in range(min_r, max_r + 1))
            elif isinstance(node, FileNode):
                k, sum_len = node.stats_info()
                node_count = 0
                node_bytes = 0
                min_r = node.min_rep
                max_r = node.max_rep
                if min_r == 0 and max_r == 0:
                    node_count = 1
                    node_bytes = 0
                else:
                    for r in range(min_r, max_r + 1):
                        if r == 0:
                            node_count += 1
                        else:
                            node_count += k**r
                            node_bytes += r * (k ** (r - 1)) * sum_len
            else:
                choices = node.base
                k = len(choices)
                cached = node._sum_len
                if cached is None:
                    s = sum(len(str(s_item).encode("utf-8")) for s_item in choices)
                    node._sum_len = s
                    sum_len = s
                else:
                    sum_len = cached
                node_count = 0
                node_bytes = 0
                min_r = node.min_rep
                max_r = node.max_rep
                if min_r == 0 and max_r == 0:
                    node_count = 1
                    node_bytes = 0
                else:
                    for r in range(min_r, max_r + 1):
                        if r == 0:
                            node_count += 1
                        else:
                            node_count += k**r
                            node_bytes += r * (k ** (r - 1)) * sum_len
            total_count, total_bytes = (
                total_count * node_count,
                (total_bytes * node_count) + (node_bytes * total_count),
            )

        full_total_bytes = int(total_bytes + (delimiter_len * total_count))
        full_total_count = int(total_count)
        return full_total_bytes, full_total_count

    def stats(
        self,
        nodes: list[list[Any]],
        delimiter_len: int = 1,
        start_token: str | None = None,
        end_token: str | None = None,
    ) -> tuple[int, int]:
        actual_count = 0
        actual_bytes = 0

        start_found = start_token is None
        end_found = False

        for expr_nodes in nodes:
            full_b, full_c = self._stats_single(expr_nodes, delimiter_len=delimiter_len)

            expr_start_c = 0
            expr_start_b = 0
            expr_end_c = full_c
            expr_end_b = full_b

            if not start_found:
                if start_token is not None:
                    try:
                        c, b = self._calculate_skipped_stats(expr_nodes, start_token)
                        expr_start_c = c
                        expr_start_b = b + (c * delimiter_len)
                        start_found = True
                    except ExprError:
                        continue
                else:
                    start_found = True

            if not end_found and end_token is not None:
                try:
                    c, b = self._calculate_skipped_stats(expr_nodes, end_token)
                    expr_end_c = c + 1
                    end_word_size = len(end_token.encode("utf-8"))
                    expr_end_b = b + (c * delimiter_len) + end_word_size + delimiter_len
                    end_found = True
                except ExprError:
                    # end_token is not in this expression
                    pass

            if start_found:
                count = expr_end_c - expr_start_c
                bytes_val = expr_end_b - expr_start_b

                if count > 0:
                    actual_count += count
                    actual_bytes += bytes_val

            if end_found:
                break

        if start_token and not start_found:
            raise self._unreachable_error(start_token)
        if end_token and not end_found:
            raise self._unreachable_error(end_token)

        if actual_count < 0:
            actual_count = 0
            actual_bytes = 0

        return int(actual_bytes), int(actual_count)
