import os
import re
import ast
import pyperclip
from pathlib import Path
from collections import Counter

PROMPT = """
YOU ARE A WORLD-CLASS SOFTWARE ENGINEER WITH EXTENSIVE EXPERIENCE IN PYTHON, RECOGNIZED FOR YOUR ABILITY TO DEVELOP HIGHLY OPTIMIZED AND INNOVATIVE SOLUTIONS. YOUR TASK IS TO WRITE PYTHON CODE FOR A GIVEN SET OF REQUIREMENTS USING A PROVIDED REPOSITORY AS YOUR CONTEXTUAL KNOWLEDGE DATABASE. THE MAIN PART OF THE REPOSITORY CONTAINS FULLY IMPLEMENTED CODE, WHILE SOME RELATED CODE INCLUDES ONLY FUNCTION SIGNATURES.

**Key Objectives:**
- ANALYZE AND UNDERSTAND THE PROVIDED REPOSITORY IN **CONTEXT** SECTION to fully grasp the existing codebase and architecture.
- WRITE CLEAN, EFFICIENT, AND ROBUST PYTHON CODE that meets the specified requirements and integrates seamlessly with the existing codebase.
- USE BEST PRACTICES IN SOFTWARE ENGINEERING, including proper use of design patterns, efficient algorithms, and optimal data structures.
- ENSURE CODE IS WELL-DOCUMENTED AND EASILY MAINTAINABLE by other developers.

**Chain of Thoughts:**
1. **Understanding the Repository:**
   - Carefully review the main parts of the repository to understand the full implementations.
   - Examine the function signatures in related code to identify their intended functionalities and interactions.

2. **Planning the Code Implementation:**
   - Outline the functionalities needed to fulfill the task requirements.
   - Determine how new code can leverage the existing functions and classes in the repository.

3. **Writing the Code:**
   - Begin coding by implementing the core functionality.
   - Ensure that new code is modular, reusing existing functions and classes where appropriate.
   - Continuously test the code to ensure it works correctly with the repository.

4. **Refinement and Documentation:**
   - Refine the code for efficiency and clarity.
   - Add comprehensive comments and documentation to make the code easily understandable for future developers.

5. **Final Review and Testing:**
   - Conduct a thorough final review to ensure the code meets all requirements.
   - Perform extensive testing to validate the functionality and integration with the existing codebase.

**What Not To Do:**
- NEVER WRITE CODE THAT IS INEFFICIENT, PRONE TO ERRORS, OR DIFFICULT TO MAINTAIN.
- DO NOT IGNORE THE EXISTING CODEBASE AND ITS ARCHITECTURE.
- AVOID REINVENTING THE WHEEL UNLESS ABSOLUTELY NECESSARY.
- NEVER LEAVE THE CODE UNDOCUMENTED OR POORLY COMMENTED.
- DO NOT FAIL TO TEST THE CODE THOROUGHLY BEFORE FINALIZING.


**CONTEXT**
"""


def load_gitignore_patterns(base_path):
    """Load .gitignore patterns from all .gitignore files in the directory tree."""
    patterns = []
    for root, dirs, files in os.walk(base_path):
        if ".gitignore" in files:
            gitignore_path = os.path.join(root, ".gitignore")
            with open(gitignore_path, "r") as gitignore_file:
                for line in gitignore_file:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(os.path.join(root, line))
    return patterns


def is_ignored(path, patterns):
    """Check if the path matches any of the .gitignore patterns."""
    for pattern in patterns:
        if re.match(re.escape(pattern).replace(r"\*", ".*"), str(path)):
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
                # Add function signature
                result.append(get_function_signature(node))
                # Add function docstring if available
                if ast.get_docstring(node):
                    docstring = ast.get_docstring(node)
                    result.append(f'    """{docstring}"""')
    except SyntaxError as e:
        result.append(f"# SyntaxError while parsing: {e}")
    return "\n".join(result)


def build_tree_structure(base_path, patterns):
    """Build a tree structure of the repository."""
    tree = {}
    for root, dirs, files in os.walk(base_path):
        # Ignore directories starting with '.'
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file_name in files:
            file_path = Path(root) / file_name
            # Ignore files starting with '.' and check .gitignore patterns
            if file_name.startswith(".") or is_ignored(file_path, patterns):
                continue
            # Build the path in the tree
            relative_path = file_path.relative_to(base_path)
            parts = relative_path.parts
            current = tree
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = None
    return tree


def format_tree(tree, indent=0):
    """Format the tree structure as a string."""
    lines = []
    for key, value in tree.items():
        lines.append("    " * indent + str(key))
        if isinstance(value, dict):
            lines.extend(format_tree(value, indent + 1))
    return lines


def dump_repository_structure_and_files(base_path):
    """Dump the repository structure and file contents to an output string, and count tokens."""
    patterns = load_gitignore_patterns(base_path)
    main_gitignore_found = False
    related_repo_roots = []
    total_tokens = 0
    output = []

    # Write the prompt at the beginning of the output
    output.append(PROMPT)
    output.append("\n")

    # Build the tree structure
    tree = build_tree_structure(base_path, patterns)
    tree_lines = format_tree(tree)
    output.append("*Repository Structure:*\n")
    output.extend(tree_lines)
    output.append("\n")
    output.append("*Files content:*\n")

    for root, dirs, files in os.walk(base_path):
        # Ignore directories starting with '.'
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        # Determine if current directory is a related repository
        if main_gitignore_found and ".gitignore" in files:
            related_repo_roots.append(root)

        # Check for main .gitignore file
        if not main_gitignore_found and ".gitignore" in files:
            main_gitignore_found = True

        for file_name in files:
            file_path = Path(root) / file_name

            # Ignore files starting with '.' and check .gitignore patterns
            if file_name.startswith(".") or is_ignored(file_path, patterns):
                continue

            # Check if the file is in a related repository
            in_related_repo = any(
                file_path.is_relative_to(repo_root) for repo_root in related_repo_roots
            )
            if in_related_repo and file_path.suffix not in [".md", ".py"]:
                continue

            # Write the file path
            output.append(f"File: {file_path}\n")
            # Write the file content
            try:
                with open(file_path, "r") as file:
                    content = file.read()
                    if file_path.suffix == ".py" and in_related_repo:
                        # For .py files in related repos, extract function defs and docstrings
                        content = extract_function_defs_and_docstrings(content)
                    elif file_path.suffix != ".py":
                        # For non-.py files, limit to first 500 lines
                        lines = file.readlines()
                        lines_to_write = lines[:500] if len(lines) > 500 else lines
                        content = "".join(lines_to_write)
                    output.append(content)
                    # Count tokens
                    total_tokens += count_tokens(content)
            except Exception as e:
                output.append(f"Error reading {file_path}: {e}\n")
            output.append("\n")

    output.append("**Main task:**")
    print(f"Total tokens: {total_tokens}")
    return "\n".join(output)


def main():
    import argparse

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
    args = parser.parse_args()

    base_path = Path(args.base_path).resolve()
    output_file = args.output_file or base_path / "context.txt"

    context = dump_repository_structure_and_files(base_path)

    # Write to the output file
    with open(output_file, "w") as out_file:
        out_file.write(context)

    # Copy to clipboard
    pyperclip.copy(context)
    print(
        f"Repository context has been dumped to {output_file} and copied to clipboard."
    )


if __name__ == "__main__":
    main()
