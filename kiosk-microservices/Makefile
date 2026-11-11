.PHONY: install lint test check-js manifests up down

install:
	pip install -r requirements-dev.txt -e libs/kiosk_common

lint:
	ruff check .

test:
	pytest -v

check-js:
	node --check frontend/js/*.js

manifests:
	for o in dev prod; do kubectl kustomize deploy/overlays/$$o | kubeconform -strict -summary -ignore-missing-schemas; done

up:
	docker compose up -d --build

down:
	docker compose down
