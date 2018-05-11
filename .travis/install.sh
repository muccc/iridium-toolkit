#!/bin/bash

if [[ $TRAVIS_OS_NAME == 'osx' ]]; then

    # Install custom requirements on OS X
    brew install pyenv-virtualenv

    case "${TOXENV}" in
        py27)
            # Install some custom Python 3.2 requirements on OS X
            echo 'Nothing to do'
            ;;
    esac
else
    # Install custom requirements on Linux
    pip install tox-travis
fi