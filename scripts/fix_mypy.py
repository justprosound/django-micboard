import re
from pathlib import Path


def fix_file(filepath: str, errors: list[str]):  # noqa: C901
    try:
        path = Path(filepath)
        content = path.read_text().splitlines()

        needs_any = False
        errors.sort(key=lambda x: int(x.split(":")[1]), reverse=True)

        for err in errors:
            parts = err.split(":")
            line_num = int(parts[1]) - 1
            msg = ":".join(parts[2:])

            if "[type-arg]" in msg:
                match = re.search(r'Missing type parameters for generic type "([^"]+)"', msg)
                if match:
                    gen_type = match.group(1)
                    if gen_type in ["list", "dict", "tuple", "set", "QuerySet", "type"]:
                        needs_any = True
                        if gen_type == "dict":
                            content[line_num] = re.sub(
                                rf"\b{gen_type}\b(?!\[)", f"{gen_type}[Any, Any]", content[line_num]
                            )
                        else:
                            content[line_num] = re.sub(
                                rf"\b{gen_type}\b(?!\[)", f"{gen_type}[Any]", content[line_num]
                            )

        if needs_any:
            has_typing_any = any("from typing import" in line and "Any" in line for line in content)
            if not has_typing_any:
                insert_idx = 0
                for i, line in enumerate(content):
                    if line.startswith("from __future__"):
                        insert_idx = i + 1
                    elif line.startswith('"""') and i == 0:
                        # Skip docstring if it's the first line
                        pass
                content.insert(insert_idx, "from typing import Any")

        path.write_text("\n".join(content) + "\n")
    except Exception:
        import logging

        logging.exception("Failed to fix %s", filepath)


def main():
    with open(".mypy_errors.txt") as f:
        lines = f.readlines()

    file_errors = {}
    for line in lines:
        if not line.startswith("micboard/"):
            continue
        filepath = line.split(":")[0]
        if filepath not in file_errors:
            file_errors[filepath] = []
        file_errors[filepath].append(line.strip())

    for filepath, errors in file_errors.items():
        fix_file(filepath, errors)


if __name__ == "__main__":
    main()
