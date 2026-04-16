#!/usr/bin/env bash

if [ -f input.zip ]
then
    rm input.zip
fi

zip -r input.zip benchmark server -x '**/__pycache__/*' server/tests/* **/test_* server/**/*.md server/**/*.txt **/AGENTS.md
