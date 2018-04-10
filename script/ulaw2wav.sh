#!/bin/sh
sox -r 8000 -t raw -e u-law -c 1 $1 $2
