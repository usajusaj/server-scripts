#!/bin/bash

if ! command -v pip &> /dev/null
then
    curl -O https://bootstrap.pypa.io/get-pip.py
    python get-pip.py
fi
