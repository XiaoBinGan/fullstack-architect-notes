#!/bin/bash
# Shared environment for the Strata deployment.
# Everything this deployment reads or writes lives under /workspace/Strata.
set -u

export STRATA_ROOT=/workspace/Strata
export STRATA_DATA_DIR=$STRATA_ROOT/data
export STRATA_BIN_DIR=$STRATA_ROOT/bin
export STRATA_COMPONENTS_DIR=$STRATA_ROOT/components

# Keep every cache/config/temp write inside the deployment folder.
export HOME=$STRATA_ROOT/.home
export XDG_DATA_HOME=$STRATA_ROOT/.xdg/data
export XDG_CONFIG_HOME=$STRATA_ROOT/.xdg/config
export XDG_CACHE_HOME=$STRATA_ROOT/.xdg/cache
export XDG_STATE_HOME=$STRATA_ROOT/.xdg/state
export TMPDIR=$STRATA_ROOT/tmp
export PIP_CACHE_DIR=$STRATA_ROOT/.xdg/cache/pip
export HF_HOME=$STRATA_ROOT/.xdg/cache/huggingface
export HF_HUB_CACHE=$STRATA_ROOT/.xdg/cache/huggingface/hub
export UV_CACHE_DIR=$STRATA_ROOT/.xdg/cache/uv

export PATH=$STRATA_BIN_DIR:$STRATA_ROOT/venv/bin:$PATH
mkdir -p "$HOME" "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_STATE_HOME" \
         "$TMPDIR" "$STRATA_DATA_DIR" "$STRATA_BIN_DIR" "$STRATA_COMPONENTS_DIR" \
         "$STRATA_ROOT/logs" "$STRATA_ROOT/scripts" "$STRATA_ROOT/results"
