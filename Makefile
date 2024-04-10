ifndef VERBOSE
	MAKEFLAGS += --no-print-directory
endif

.PHONY: help

.DEFAULT_GOAL := help

help:
	@echo "All commands from this makefile:"
	@egrep -h '\s##\s' $(MAKEFILE_LIST) |  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

include .envrc
export $(shell sed 's/=.*//' .envrc)


start-dev:  ## start app
	@echo "starting dev app"
	@cd app/src && pipenv run python app.py
