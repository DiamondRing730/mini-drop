.PHONY: build up down clean logs demo demo-before demo-after demo-numeric demo-io unit e2e test

SCENARIO ?= cpu-before

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

clean:
	docker compose down -v

logs:
	docker compose logs -f --tail=120

demo:
	bash scripts/demo.sh $(SCENARIO)

demo-before:
	bash scripts/demo.sh cpu-before

demo-after:
	bash scripts/demo.sh cpu-after

demo-numeric:
	bash scripts/demo.sh numeric

demo-io:
	bash scripts/demo.sh io

unit:
	python -m pytest tests/unit -q

e2e:
	python -m pytest tests/e2e -q

test: unit
