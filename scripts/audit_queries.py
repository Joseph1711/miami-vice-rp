"""
Deep AST & Execution Auditor for Miami Vice bot database queries.
Checks every file in bot/ for SQL query placeholder count vs parameter count.
"""
import ast
import os
import re
import sys

_DOLLAR_RE = re.compile(r"\$(\d+)")

def analyze_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        src = f.read()

    tree = ast.parse(src, filename=filepath)
    issues = []
    queries_found = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name in ("aexecute", "execute", "afetch_one", "afetch_all", "fetch_one", "fetch_all"):
                queries_found += 1
                args = node.args
                if not args:
                    continue

                # Query argument
                query_node = args[0]
                query_str = None
                if isinstance(query_node, ast.Constant) and isinstance(query_node.value, str):
                    query_str = query_node.value
                elif isinstance(query_node, ast.JoinedStr):
                    # f-string: reconstruct approximate
                    parts = []
                    for part in query_node.values:
                        if isinstance(part, ast.Constant):
                            parts.append(str(part.value))
                        else:
                            parts.append("{var}")
                    query_str = "".join(parts)

                if query_str:
                    matches = _DOLLAR_RE.findall(query_str)
                    dollar_indices = [int(m) for m in matches]
                    max_dollar = max(dollar_indices) if dollar_indices else 0
                    distinct_dollars = len(set(dollar_indices))
                    q_marks = query_str.count("?")

                    # Parameter argument (usually args[1])
                    if len(args) > 1:
                        param_node = args[1]
                        param_count = None
                        if isinstance(param_node, (ast.Tuple, ast.List)):
                            param_count = len(param_node.elts)
                        
                        if param_count is not None:
                            if max_dollar > 0 and param_count != max_dollar:
                                issues.append({
                                    "file": filepath,
                                    "line": node.lineno,
                                    "func": func_name,
                                    "max_dollar": max_dollar,
                                    "distinct_dollars": distinct_dollars,
                                    "param_count": param_count,
                                    "query": query_str.strip()[:100],
                                    "issue": f"Max placeholder is ${max_dollar} but passed {param_count} parameters!"
                                })
                            elif q_marks > 0 and param_count != q_marks:
                                issues.append({
                                    "file": filepath,
                                    "line": node.lineno,
                                    "func": func_name,
                                    "q_marks": q_marks,
                                    "param_count": param_count,
                                    "query": query_str.strip()[:100],
                                    "issue": f"Has {q_marks} '?' placeholders but passed {param_count} parameters!"
                                })
                    else:
                        # No params passed
                        if max_dollar > 0 or q_marks > 0:
                            issues.append({
                                "file": filepath,
                                "line": node.lineno,
                                "func": func_name,
                                "issue": f"Query has placeholders (${max_dollar}/?) but no params argument was passed!",
                                "query": query_str.strip()[:100]
                            })

    return queries_found, issues

def run_audit():
    total_queries = 0
    all_issues = []

    for root, _, files in os.walk("bot"):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                count, issues = analyze_file(path)
                total_queries += count
                all_issues.extend(issues)

    print(f"Audited {total_queries} database queries across all bot/ files.")
    print(f"Found {len(all_issues)} potential parameter mismatch issues:")
    for issue in all_issues:
        print(f"\n[ISSUE] {issue['file']}:{issue['line']} in {issue['func']}")
        print(f"  Reason: {issue['issue']}")
        print(f"  Query: {issue['query']}")

if __name__ == "__main__":
    run_audit()
