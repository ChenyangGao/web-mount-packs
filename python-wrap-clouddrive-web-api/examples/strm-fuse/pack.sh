#!/usr/bin/env bash

PROJDIR=$(dirname "$0")
PROJNAME=$(basename ${PROJDIR})
CURDIR=$(pwd)
VERSION=$(head -1 ${PROJDIR}/VERSION || echo latest)

function createpack() {
    local file=$1/clouddrive-${PROJNAME}_${VERSION}.pyz
    if /usr/bin/env python3 -m zipapp --compress ${PROJDIR} --output ${file}
    then
        echo -e "Create a package file located in \n\t${file}"
    else
        return 1
    fi
}

shopt -s globstar
rm -rf ${PROJDIR}/**/__pycache__
rm -rf ${PROJDIR}/**/.DS_store
rm -rf ${PROJDIR}/**/._*
createpack ${CURDIR} || createpack ${HOME} || createpack ${PROJDIR} || echo Cannot create package file
