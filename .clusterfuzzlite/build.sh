#!/bin/bash -eu

# Ensure dependencies are installed in the OSS-Fuzz system Python
uv pip install --system . atheris

# Compile fuzzers
for fuzzer in micboard/fuzzers/fuzz_*.py; do
    fuzzer_basename=$(basename -s .py $fuzzer)
    compile_python_fuzzer $fuzzer $fuzzer_basename
done
