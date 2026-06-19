.PHONY: build up down clean logs demo unit e2e test

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
	bash scripts/demo.sh

unit:
	python -m pytest tests/unit -q

e2e:
	python -m pytest tests/e2e -q

test: unit
