#!/bin/bash -eu
# Builds the Atheris fuzz targets in tests/fuzz/ (ClusterFuzzLite / OSS-Fuzz)
# against the backend modules, with the backend's hash-locked dependencies.
pip3 install --require-hashes -r "$SRC/kiosk-app/backend/requirements.txt"

for fuzzer in "$SRC"/kiosk-app/tests/fuzz/fuzz_*.py; do
    compile_python_fuzzer "$fuzzer" --paths "$SRC/kiosk-app/backend"
done
