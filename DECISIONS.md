# Decisions

## src layout instead of a flat package

Package lives in src/evalgate and is used via `pip install -e .`.
Alternative: evalgate/ at the repo root, importable straight from the working directory.
Chosen because a flat layout lets tests pass against the working-directory copy while the
installed package is broken (file missing from the wheel, bad entry point). src forces every
import through the installed package, so packaging mistakes fail in CI, not on a user's machine.
