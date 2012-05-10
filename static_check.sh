#!/bin/sh

for filename in `find src/collective/facebook/portlets -iname "*.py"`; do
    pep8 $filename
    pyflakes $filename
done
