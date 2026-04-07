.DEFAULT_GOAL := help
RABBITMQ_CONTAINER := "prs-rabbitmq"
SWAGGER_CONTAINER := "prs-swagger-ui"

define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

.PHONY: lint
lint: ## Check code style
	@echo "+ $@"
	@ruff check

.PHONY: test
test: export DJANGO_SETTINGS_MODULE = polarrouteserver.settings.test
test: ## Run tests quickly with the default Python
	@echo "+ $@"
	@pytest

.PHONY: test-cov
test-cov: export DJANGO_SETTINGS_MODULE = polarrouteserver.settings.test
test-cov: ## Run tests quickly with the default Python
	@echo "+ $@"
	@pytest --cov=polarrouteserver

.PHONY: cov-badge
cov-badge: ## Generate the coverage badge from .coverage file
	@echo "+ $@"
	@coverage-badge -o coverage.svg

.PHONY: build-docs
build-docs: ## Generate mkdocs HTML documentation
	@echo "+ $@"
	@mkdocs build
	@$(BROWSER) site/index.html

.PHONY: serve-docs
serve-docs: ## Serve docs locally
	@echo "+ $@"
	@mkdocs serve

.PHONY: deploy-docs
deploy-docs: ## Deploy docs to github pages
	@echo "+ $@"
	@mkdocs gh-deploy

.PHONY: migrate
migrate: ## Apply database migrations (or create for first time)
	@echo "+ $@"
	@python manage.py migrate

.PHONY: migrations
migrations: ## Create database migration files from changes to models
	@echo "+ $@"
	@python manage.py makemigrations

.PHONY: start-dev-server
start-dev-server: export DJANGO_SETTINGS_MODULE = polarrouteserver.settings.development
start-dev-server: ## start Django dev server
	@echo "+ $@"
	@python manage.py runserver &

.PHONY: stop-dev-server
stop-dev-server: ## Stop Django dev server
	@echo "+ $@"
	@pkill -9 -f 'python manage.py runserver'

.PHONY: start-django-server
start-django-server: ## Start Django server (gunicorn)
	@echo "+ $@"
	@gunicorn polarrouteserver.wsgi &

.PHONY: stop-django-server
stop-django-server: ## Stop Django dev server
	@echo "+ $@"
	@pkill -9 -f 'gunicorn polarrouteserver.wsgi'

.PHONY: start-celery
start-celery: start-rabbitmq ## Start celery
	@echo "+ $@"
	@DJANGO_SETTINGS_MODULE='polarrouteserver.settings.development' celery -A polarrouteserver  worker --beat --scheduler django --loglevel=info --detach

.PHONY: stop-celery
stop-celery: ## Stop celery
	@echo "+ $@"
	@pkill -9 -f 'celery -A polarrouteserver'

.PHONY: start-rabbitmq
start-rabbitmq: ## Start rabbitmq via docker
	@echo "+ $@"
	@docker run -d -p 5672:5672 --name ${RABBITMQ_CONTAINER} rabbitmq

.PHONY: stop-rabbitmq
stop-rabbitmq: ## Stop rabbitmq docker container
	@echo "+ $@"
	@docker stop ${RABBITMQ_CONTAINER}
	@docker rm ${RABBITMQ_CONTAINER}

.PHONY: serve-dev
export DJANGO_SETTINGS_MODULE=polarrouteserver.settings.development
serve-dev: start-rabbitmq start-celery start-dev-server ## Run all the components for serving a development instance.

.PHONY: stop-serve-dev
export DJANGO_SETTINGS_MODULE=polarrouteserver.settings.development
stop-serve-dev: stop-rabbitmq stop-celery stop-dev-server # stop all dev serve components (rabbitmq, celery, devserver)

.PHONY: build-apischema
build-apischema: ## (Re)Build api schema file from changes to views
	@echo "+ $@"
	@python manage.py spectacular --color --validate --file docs/apischema.yml

.PHONY: start-swagger
start-swagger: ## Start swagger-ui container with API schema
	@echo "+ $@"
	@docker run -d --rm -p 80:8080 -e SWAGGER_JSON=/schema.yml -v ${PWD}/docs/apischema.yml:/schema.yml --name ${SWAGGER_CONTAINER} swaggerapi/swagger-ui
	@python -m webbrowser localhost:80

.PHONY: stop-swagger
stop-swagger: ## Stop swagger-ui docker container
	@echo "+ $@"
	@docker stop ${SWAGGER_CONTAINER}
	@docker rm ${SWAGGER_CONTAINER}

.PHONY: build
build: ## Build package
	@echo "+ $@"
	@python -m build

.PHONY:prep-release
prep-release: ## runs update-pkg-version, (re)builds the apischema, preps the changelog
	@echo "+ $@"
	@if [ -z "$(version)" ]; then \
		echo "ERROR: version is not set."; \
		echo "Usage: make prep-release version=1.2.3"; \
		exit 1; \
	fi

	@echo "...Updating docs/apischema.yml..."
	@sed -i "s/version: .*/version: $(version)/" docs/apischema.yml

	@echo "...Updating CHANGELOG.md..."
	@sed -i "/## \[Unreleased\]/ a\ \n## $(version) - $$(date '+%Y-%m-%d')" CHANGELOG.md

	@echo "Done."

.PHONY: help
help:
	@echo "Note: Remember to activate your virtual environment (if used)."
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

