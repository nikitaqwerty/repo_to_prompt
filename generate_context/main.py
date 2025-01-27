import os
import re
import ast
import pyperclip
from pathlib import Path
from collections import Counter
import argparse
import fnmatch

PROMPT = """<context>
You are an expert programming AI assistant who prioritizes minimalist, efficient code. You plan before coding, write idiomatic solutions, seek clarification when needed, and accept user preferences even if suboptimal.
</context>

<planning_rules>
- Create 3-step numbered plans before coding
- Display current plan step clearly
- Ask for clarification on ambiguity
- Optimize for minimal code and overhead
</planning_rules>

<format_rules>
- Use code blocks for simple tasks
- Split long code into sections
- Create artifacts for file-level tasks
- Keep responses brief but complete
</format_rules>

OUTPUT: Create responses following these rules. Focus on minimal, efficient solutions while maintaining a helpful, concise style."""


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
    path = str(path)
    for gitignore_path, patterns_list in patterns.items():
        pattern_dir = os.path.dirname(gitignore_path)
        for pattern in patterns_list:
            glob_pattern = os.path.join(pattern_dir, pattern)
            if glob_pattern.endswith(os.sep):
                glob_pattern = glob_pattern.rstrip(os.sep) + "/**"
            if fnmatch.fnmatch(path, glob_pattern):
                return True
    return False


def count_tokens(text):
    """Count the number of tokens in the text."""
    tokens = re.findall(r"\w+", text)
    return len(tokens)


def get_function_signature(node):
    """Get the function signature from an AST node."""
    params = []
    for arg in node.args.args:
        if arg.arg != "self":
            params.append(arg.arg)
    return f"def {node.name}({', '.join(params)}):"


def extract_function_defs_and_docstrings(file_content):
    """Extract function definitions and docstrings from Python file content."""
    result = []
    try:
        tree = ast.parse(file_content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result.append(get_function_signature(node))
                if ast.get_docstring(node):
                    docstring = ast.get_docstring(node)
                    result.append(f'    """{docstring}"""')
    except SyntaxError as e:
        result.append(f"# SyntaxError while parsing: {e}")
    return "\n".join(result)


def build_tree_structure(base_path, patterns, include_ignored=False):
    """Build a tree structure of the repository."""
    tree = {}
    base_path_name = Path(base_path).name
    tree[base_path_name] = {}

    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file_name in files:
            file_path = Path(root) / file_name
            if not include_ignored and (
                file_name.startswith(".") or is_ignored(file_path, patterns)
            ):
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
    base_path, no_nest, include_ignored, filenames=None
):
    """Dump the repository structure and file contents with HTML-style blocks."""
    patterns = load_gitignore_patterns(base_path)
    main_gitignore_found = False
    related_repo_roots = []
    total_tokens = 0
    output = [PROMPT]

    if filenames:
        output.append("\n<files_content>")
        for filename in filenames:
            file_path = Path(base_path) / filename
            if not file_path.exists():
                raise FileNotFoundError(f"Specified file '{filename}' does not exist.")
            with open(file_path, "r") as file:
                content = file.read()
                output.append(f"\nFile: {file_path}\n{content}")
                total_tokens += count_tokens(content)
        output.append("\n</files_content>")
    else:
        tree = build_tree_structure(base_path, patterns, include_ignored)
        output.append("\n<repository_structure>")
        output.extend(format_tree(tree))
        output.append("\n</repository_structure>\n\n<files_content>")

        file_contents = {}

        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            if main_gitignore_found and ".gitignore" in files:
                related_repo_roots.append(root)

            if not main_gitignore_found and ".gitignore" in files:
                main_gitignore_found = True

            for file_name in files:
                file_path = Path(root) / file_name

                if not include_ignored and (
                    file_name.startswith(".") or is_ignored(file_path, patterns)
                ):
                    continue

                in_related_repo = any(
                    file_path.is_relative_to(repo_root)
                    for repo_root in related_repo_roots
                )
                if no_nest and in_related_repo:
                    continue

                if in_related_repo and file_path.suffix not in [".md", ".py"]:
                    continue

                try:
                    with open(file_path, "r") as file:
                        content = file.read()
                        if file_path.suffix == ".py" and in_related_repo:
                            content = extract_function_defs_and_docstrings(content)
                        elif file_path.suffix != ".py":
                            lines = file.readlines()
                            lines_to_write = lines[:500] if len(lines) > 500 else lines
                            content = "".join(lines_to_write)
                        file_contents[file_path] = content
                except Exception as e:
                    file_contents[file_path] = f"Error reading {file_path}: {e}"

        for file_path, content in file_contents.items():
            output.append(f"\nFile: {file_path}\n{content}")
            total_tokens += count_tokens(content)

        output.append("\n</files_content>")

    output.append("\n<main_task>\nMain task:\n</main_task>")
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
    args = parser.parse_args()

    base_path = Path(args.base_path).resolve()
    output_file = args.output_file or base_path / "context.txt"

    context = dump_repository_structure_and_files(
        base_path, args.no_nest, args.ignored_filenames, args.filename
    )

    with open(output_file, "w") as out_file:
        out_file.write(context)

    pyperclip.copy(context)
    print(
        f"Repository context has been dumped to {output_file} and copied to clipboard."
    )


if __name__ == "__main__":
    main()
