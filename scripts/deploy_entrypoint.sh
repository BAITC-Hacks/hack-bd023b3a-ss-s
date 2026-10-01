#!/bin/sh
# Container entrypoint (Dockerfile; operations in docs/DEPLOY.md).
#
#   (no arguments, or uvicorn options)  serve: refresh the published corpus in the data volume,
#                                       run the idempotent bootstrap (the FIRST start seeds
#                                       Level 2 with the runtime number key), then exec ONE
#                                       uvicorn worker; options are passed on to uvicorn.
#   <command> [args]                    run that command instead, e.g. an operations tool:
#                                       docker compose run --rm qorgan python -m qorgan.audit verify
set -eu

# Reports, the audit log and the Level-2 seeds are readable by the service account only.
umask 027

if [ "$#" -gt 0 ] && [ "${1#-}" = "$1" ]; then
    exec "$@"
fi

state_dir="${QORGAN_DATA_DIR:-/app/data}/processed"
mkdir -p "$state_dir"
# The volume holds runtime state next to the published corpus splits the bootstrap expects
# there. The image's copy wins, so a volume created by an older image gets the current,
# scrubbed splits and nothing is fetched from the network. Runtime state is never in this copy.
cp /opt/qorgan/corpus/* "$state_dir"/

python /app/scripts/deploy_bootstrap.py

exec uvicorn qorgan.api:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-server-header "$@"
