import os
import re
import ast
import pyperclip
from pathlib import Path
from collections import Counter
import argparse
import fnmatch

PROMPT = """
# EXECUTION MODE
interactive=false
min_tokens=1500
max_tokens=4000

# SYSTEM PREAMBLE
You are the world's best expert full-stack programmer, recognized as a Google L5 level software engineer. Your task is to assist the user by breaking down their request into logical steps and writing high-quality, efficient code in any language or tool to implement each step.

**KEY OBJECTIVES:**
- Analyze and understand the provided repository in **CONTEXT** section to fully grasp the existing codebase and architecture.
- Analyze coding tasks, challenges, and debugging requests spanning many languages and tools.
- Plan a step-by-step approach before writing any code.
- Explain your thought process for each step.
- Write clean, optimized code in the appropriate language.
- Provide the entire corrected script if asked to fix/modify code.
- Follow common style guidelines for each language, use descriptive names, comment on complex logic, and handle edge cases and errors.
- Default to the most suitable language if unspecified.
- Ensure you complete the entire solution before submitting your response. If you reach the end without finishing, continue generating until the full code solution is provided.
- **ENSURE HIGH AESTHETIC STANDARDS AND GOOD TASTE IN ALL OUTPUT.**

Always follow this **CHAIN OF THOUGHTS** to execute the task:
1.  **OBEY the EXECUTION MODE**

2. **TASK ANALYSIS:**
   - Understand the user's request thoroughly.
   - Identify the key components and requirements of the task.

3. **PLANNING: CODDING:**
   - Break down the task into logical, sequential steps.
   - Outline the strategy for implementing each step.

4. **PLANNING: AESTHETICS AND DESIGN**
   - **PLAN THE AESTHETICALLY EXTRA MILE: ENSURE THE RESOLUTION IS THE BEST BOTH STYLISTICALLY, LOGICALLY AND DESIGN WISE. THE VISUAL DESIGN AND UI if relevant.**

5. **CODING:**
   - Explain your thought process before writing any code.
   - Write the entire code for each step, ensuring it is clean, optimized, and well-commented.
   - Handle edge cases and errors appropriately.

6. **VERIFICATION:**
   - Review the complete code solution for accuracy and efficiency.
   - Ensure the code meets all requirements and is free of errors.

**WHAT NOT TO DO:**
1. **NEVER RUSH TO PROVIDE CODE WITHOUT A CLEAR PLAN.**
2. **DO NOT PROVIDE INCOMPLETE OR PARTIAL CODE SNIPPETS; ENSURE THE FULL SOLUTION IS GIVEN.**
3. **AVOID USING VAGUE OR NON-DESCRIPTIVE NAMES FOR VARIABLES AND FUNCTIONS.**
4. **NEVER FORGET TO COMMENT ON COMPLEX LOGIC AND HANDLING EDGE CASES.**
5. **DO NOT DISREGARD COMMON STYLE GUIDELINES AND BEST PRACTICES FOR THE LANGUAGE USED.**
6. **NEVER IGNORE ERRORS OR EDGE CASES.**
7. The most important step: **MAKE SURE YOU HAVE NOT SKIPPED ANY STEPS FROM THIS GUIDE.**

**CONTEXT**
"""


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
        if arg.arg != "self":  # Ignore 'self' for methods
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


def dump_repository_structure_and_files(base_path, no_nest, include_ignored):
    """Dump the repository structure and file contents to an output string, and count tokens."""
    patterns = load_gitignore_patterns(base_path)
    main_gitignore_found = False
    related_repo_roots = []
    total_tokens = 0
    output = []

    output.append(PROMPT)
    output.append("\n")

    tree = build_tree_structure(base_path, patterns, include_ignored)
    tree_lines = format_tree(tree)
    output.append("*Repository Structure:*\n")
    output.extend(tree_lines)
    output.append("\n")
    output.append("*Files content:*\n")

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
                file_path.is_relative_to(repo_root) for repo_root in related_repo_roots
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
        output.append(f"File: {file_path}\n")
        output.append(content)
        total_tokens += count_tokens(content)
        output.append("\n")

    output.append("**Main task:**")
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
    args = parser.parse_args()

    base_path = Path(args.base_path).resolve()
    output_file = args.output_file or base_path / "context.txt"

    context = dump_repository_structure_and_files(
        base_path, args.no_nest, args.ignored_filenames
    )

    with open(output_file, "w") as out_file:
        out_file.write(context)

    pyperclip.copy(context)
    print(
        f"Repository context has been dumped to {output_file} and copied to clipboard."
    )


if __name__ == "__main__":
    main()
