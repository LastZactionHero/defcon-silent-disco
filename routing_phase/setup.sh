#!/usr/bin/env bash
# Reproduce the routing engine environment (KiCadRoutingTools + isolated venv).
# Idempotent. Per-machine (the venv/clone live under ~/.local/share, not in git).
# The badge harness tools (geom/measure_route) use the SYSTEM python3 (pcbnew binding);
# KRT runs in its own venv (numpy/scipy/shapely + the rust grid_router kernel, no pcbnew).
set -euo pipefail

KRTDIR="${KRTDIR:-$HOME/.local/share/defcon-badge-krt}"
PIN="ce5cb2dc5ab9a82aa4cffcb3bb1210d2fa7bad86"   # KRT v0.15.13 (keep in sync with KRT_PINNED_COMMIT.txt)
REPO="https://github.com/drandyhaas/KiCadRoutingTools"

mkdir -p "$KRTDIR"
echo "$PIN" > "$KRTDIR/KRT_PINNED_COMMIT.txt"

# 1. Clone KRT at the pinned commit
if [ ! -d "$KRTDIR/KiCadRoutingTools/.git" ]; then
  git clone "$REPO" "$KRTDIR/KiCadRoutingTools"
fi
git -C "$KRTDIR/KiCadRoutingTools" fetch --depth 50 origin || true
git -C "$KRTDIR/KiCadRoutingTools" checkout "$PIN" 2>/dev/null || \
  echo "WARN: pinned commit $PIN not checked out (using current HEAD)"

# 2. Isolated venv with numpy/scipy/shapely (cp wheels; Python 3.14 OK as of 2026-06)
if [ ! -x "$KRTDIR/venv/bin/python" ]; then
  python3 -m venv "$KRTDIR/venv"
fi
"$KRTDIR/venv/bin/pip" install --quiet --upgrade pip
"$KRTDIR/venv/bin/pip" install --only-binary=:all: numpy scipy shapely

# 3. Build the rust grid_router kernel (downloads a prebuilt .so for the release, else cargo build)
( cd "$KRTDIR/KiCadRoutingTools" && "$KRTDIR/venv/bin/python" build_router.py )

# 4. Smoke test
"$KRTDIR/venv/bin/python" - <<'PY'
import sys; sys.path.insert(0, __import__('os').path.expanduser('~/.local/share/defcon-badge-krt/KiCadRoutingTools/rust_router'))
import grid_router, numpy, scipy, shapely
print("KRT env OK: grid_router + numpy", numpy.__version__, "+ scipy", scipy.__version__, "+ shapely", shapely.__version__)
PY
echo "Done. Run KRT via: $KRTDIR/venv/bin/python $KRTDIR/KiCadRoutingTools/route.py --help"
