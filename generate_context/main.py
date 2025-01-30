import os
import re
import ast
import pyperclip
from pathlib import Path
import argparse
import fnmatch

PROMPT = """<context>
You are an expert programming AI assistant who prioritizes minimalist, efficient code. You plan before coding, write idiomatic solutions, and accept user preferences even if suboptimal.
</context>

<format_rules>
- Keep responses brief but complete
- You only output full code file, you never cut output
</format_rules>

<input>"""


def load_gitignore_patterns(base_path):
    """Load .gitignore patterns from all .gitignore files in the directory tree."""
    patterns = {}
    for root, dirs, files in os.walk(base_path):
        if ".gitignore" in files:
            gitignore_path = os.path.join(root, ".gitignore")
            with open(gitignore_path, "r") as gitignore_file:
                patterns[gitignore_path] = []
                for line in gitignore_file:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns[gitignore_path].append(line)
    return patterns


def is_ignored(path, patterns):
    """Check if the path matches any of the .gitignore patterns."""
    path_obj = Path(path)
    for gitignore_path, patterns_list in patterns.items():
        gitignore_dir = Path(gitignore_path).parent
        try:
            relative_path = path_obj.relative_to(gitignore_dir)
        except ValueError:
            continue

        for pattern in patterns_list:
            if fnmatch.fnmatch(str(relative_path), pattern):
                return True
            if pattern.endswith("/"):
                if fnmatch.fnmatch(str(relative_path), pattern + "*"):
                    return True
    return False


def count_tokens(text):
    """Count the number of tokens in the text."""
    tokens = re.findall(r"\w+", text)
    return len(tokens)


def get_function_signature(node):
    """Get the function signature from an AST node."""
    params = [arg.arg for arg in node.args.args]
    return f"def {node.name}({', '.join(params)}):"


def extract_function_defs_and_docstrings(file_content):
    """Extract function/class definitions and docstrings from Python file content."""
    result = []
    try:
        tree = ast.parse(file_content)

        def process_node(node, indent=0):
            if isinstance(node, ast.FunctionDef):
                # Function/method definition
                result.append("    " * indent + get_function_signature(node))
                if doc := ast.get_docstring(node):
                    result.append("    " * (indent + 1) + f'"""{doc}"""')

            elif isinstance(node, ast.ClassDef):
                # Class definition
                bases = [ast.unparse(base).strip() for base in node.bases]
                base_str = f"({', '.join(bases)})" if bases else ""
                result.append("    " * indent + f"class {node.name}{base_str}:")
                if doc := ast.get_docstring(node):
                    result.append("    " * (indent + 1) + f'"""{doc}"""')

                # Process class body
                for child in node.body:
                    process_node(child, indent + 1)

            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                # Class-level assignments/annotations
                if isinstance(node, ast.Assign):
                    targets = [ast.unparse(t).strip() for t in node.targets]
                    line = f"{', '.join(targets)} = ..."
                else:  # AnnAssign
                    target = ast.unparse(node.target).strip()
                    annotation = (
                        ast.unparse(node.annotation).strip() if node.annotation else ""
                    )
                    line = (
                        f"{target}: {annotation} = ..."
                        if node.value
                        else f"{target}: {annotation}"
                    )
                result.append("    " * (indent + 1) + line)

        for node in tree.body:
            process_node(node)

    except SyntaxError as e:
        result.append(f"# SyntaxError while parsing: {e}")
    return "\n".join(result)


def build_tree_structure(base_path, patterns, include_ignored, ignore_files):
    """Build a tree structure of the repository."""
    tree = {}
    base_path_name = Path(base_path).name
    tree[base_path_name] = {}

    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file_name in files:
            file_path = Path(root) / file_name
            skip_conditions = (
                not include_ignored
                and (file_name.startswith(".") or is_ignored(file_path, patterns))
            ) or file_name in ignore_files
            if skip_conditions:
                continue
            relative_path = file_path.relative_to(base_path)
            parts = [base_path_name] + list(relative_path.parts)
            current = tree
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = None
    return tree


def format_tree(tree, indent=0):
    """Format the tree structure as a string."""
    lines = []
    for key, value in tree.items():
        if isinstance(value, dict):
            lines.append("│   " * indent + "├── " + str(key) + "/")
            lines.extend(format_tree(value, indent + 1))
        else:
            lines.append("│   " * indent + "├── " + str(key))
    return lines


def dump_repository_structure_and_files(
    base_path,
    no_nest,
    include_ignored,
    filenames=None,
    ignore_files=None,
    include_tree=True,
):
    """Dump the repository structure and file contents with HTML-style blocks."""
    patterns = load_gitignore_patterns(base_path)
    main_gitignore_found = False
    related_repo_roots = []
    total_tokens = 0
    output = [PROMPT]
    ignore_files = ignore_files or []

    if include_tree:
        # Build and add repository structure
        tree = build_tree_structure(base_path, patterns, include_ignored, ignore_files)
        output.append("\n<repository_structure>")
        output.extend(format_tree(tree))
        output.append("\n</repository_structure>\n\n<files_content>")
    else:
        output.append("\n<files_content>")

    if filenames:
        for filename in filenames:
            file_path = Path(base_path) / filename
            resolved_path = file_path.resolve()
            if not resolved_path.is_relative_to(base_path.resolve()):
                raise ValueError(f"File {filename} is outside the base path.")
            if not file_path.exists():
                raise FileNotFoundError(f"Specified file '{filename}' does not exist.")
            with open(file_path, "r") as file:
                content = file.read()
                output.append(f"\nFile: {file_path}\n{content}")
                total_tokens += count_tokens(content)
    else:
        file_contents = {}

        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            if main_gitignore_found and ".gitignore" in files:
                related_repo_roots.append(root)

            if not main_gitignore_found and ".gitignore" in files:
                main_gitignore_found = True

            for file_name in files:
                file_path = Path(root) / file_name
                skip_conditions = (
                    not include_ignored
                    and (file_name.startswith(".") or is_ignored(file_path, patterns))
                ) or file_name in ignore_files
                if skip_conditions:
                    continue

                in_related_repo = any(
                    file_path.is_relative_to(repo_root)
                    for repo_root in related_repo_roots
                )
                if no_nest and in_related_repo:
                    continue

                try:
                    with open(file_path, "r") as file:
                        if file_path.suffix == ".py" and in_related_repo:
                            content = extract_function_defs_and_docstrings(file.read())
                        elif file_path.suffix != ".py":
                            content = []
                            for i, line in enumerate(file):
                                if i >= 500:
                                    break
                                content.append(line)
                            content = "".join(content)
                        else:
                            content = file.read()
                        file_contents[file_path] = content
                except Exception as e:
                    file_contents[file_path] = f"Error reading {file_path}: {e}"

        for file_path, content in file_contents.items():
            output.append(f"\nFile: {file_path}\n{content}")
            total_tokens += count_tokens(content)

    output.append("\n</files_content>")
    output.append("\n</input>")
    output.append("\n<task>\n\n</task>")
    print(f"Total tokens: {total_tokens}")
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Generate repository context file.")
    parser.add_argument(
        "base_path",
        nargs="?",
        default=".",
        help="The base path of the repository (default: current directory)",
    )
    parser.add_argument(
        "users_request",
        nargs="?",
        default="",
        help="The user's request to include in the context",
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        help="The output file for the context (default: {base_path}/context.txt)",
    )
    parser.add_argument(
        "--no-nest",
        action="store_true",
        help="Ignore all related repo files when building the context",
    )
    parser.add_argument(
        "--ignored-filenames",
        action="store_true",
        help="Include ignored filenames in the output",
    )
    parser.add_argument(
        "--filename",
        nargs="*",
        help="Specify one or more files to output with the prompt and content",
    )
    parser.add_argument(
        "--ignore-file",
        nargs="*",
        default=[],
        help="Explicitly ignore files by name",
    )
    parser.add_argument(
        "--no-tree",
        action="store_true",
        help="Omit repository structure from the output",
    )
    args = parser.parse_args()

    base_path = Path(args.base_path).resolve()

    if args.output_file:
        output_file = Path(args.output_file)
        if not output_file.is_absolute():
            output_file = base_path / output_file
    else:
        output_file = base_path / "context.txt"

    context = dump_repository_structure_and_files(
        base_path,
        args.no_nest,
        args.ignored_filenames,
        args.filename,
        args.ignore_file,
        include_tree=not args.no_tree,
    )

    # Safely insert users_request
    safe_request = args.users_request.replace("</task>", "")
    context = context.replace(
        "<task>\n\n</task>",
        f"<task>\n{safe_request}\n</task>",
    )

    with open(output_file, "w") as out_file:
        out_file.write(context)

    try:
        pyperclip.copy(context)
        print(f"Repository context copied to clipboard and saved to {output_file}")
    except Exception as e:
        print(f"Context saved to {output_file} (clipboard copy failed: {e})")


if __name__ == "__main__":
    main()
