#!/usr/bin/env bash

HELPDIR=$(dirname "$0")
PROJDIR=$(dirname ${HELPDIR})
PROJNAME=$(basename ${PROJDIR})
CURDIR=$(pwd)
VERSION=$(head -1 ${HELPDIR}/VERSION || echo latest)

function createpack() {
    local file=$1/alist-${PROJNAME}_${VERSION}.pyz
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
