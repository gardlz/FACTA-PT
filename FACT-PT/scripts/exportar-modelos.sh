#!/bin/sh
# Copies the models out of the `modelos` volume into a folder, one sub-folder per model at the
# revision pinned in docker-compose.yml, ready to mount at /checkpoints (MODELS.md):
#
#     scripts/exportar-modelos.sh /srv/facta-pt/checkpoints
#
# The hub keeps each file once and links it from the revision's folder; the copy follows the links,
# so the result is plain files. Needs about 3 GB free at the destination. From a Linux or macOS
# shell (or WSL); Git Bash on Windows mangles the container paths.
set -eu

destino=${1:?uso: $0 PASTA_DE_DESTINO}
volume=${VOLUME:-facta-pt_modelos}

mkdir -p "$destino"
destino=$(cd "$destino" && pwd)

docker run --rm -v "$volume":/m:ro -v "$destino":/out alpine sh -eu -c '
for par in \
    amalia-llm/AMALIA-9B-0626-DPO@c4614b9b5c7b4fe303fa20902e692fc7dface640 \
    liaad/facta-pt-qg-amalia-9b-0626-dpo@f8aff451e824fb4800c74385a36fea5f19579cfd \
    liaad/facta-pt-relevance-bertimbau-base@8b6df9f96bda2c5ba3ec15d2e19deb8a1dbbce20 \
    liaad/facta-pt-cee-xlm-roberta-large-xnli@585f4cd2c89fdff1421093f60763a0a67be5174e
do
    repo=${par%@*}
    revisao=${par#*@}
    origem="/m/hub/models--$(echo "$repo" | sed "s|/|--|g")/snapshots/$revisao"
    nome=${repo#*/}
    if [ ! -d "$origem" ]; then
        echo "$repo @ $revisao: não está no volume, fica de fora" >&2
        continue
    fi
    echo "$repo -> $nome"
    rm -rf "/out/$nome.tmp"
    case "$repo" in
        amalia-llm/*|liaad/facta-pt-qg-*)
            # Served by the API: only what the question generator reads here.
            mkdir -p "/out/$nome.tmp"
            for f in "$origem"/tokenizer* "$origem"/special_tokens_map.json "$origem"/config.json \
                     "$origem"/chat_template* "$origem"/checkpoint_info.json; do
                if [ -e "$f" ]; then cp -L "$f" "/out/$nome.tmp/"; fi
            done ;;
        *)
            cp -rL "$origem" "/out/$nome.tmp" ;;
    esac
    rm -rf "/out/$nome"
    mv "/out/$nome.tmp" "/out/$nome"
done
du -sh /out/*
'
