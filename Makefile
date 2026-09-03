.PHONY: lint format typecheck test test-cov ci lite-image full-image up down

BACKEND := backend

lint:
	cd $(BACKEND) && ruff check .

format:
	cd $(BACKEND) && ruff format .

typecheck:
	cd $(BACKEND) && mypy .

test:
	cd $(BACKEND) && pytest -q

test-cov:
	cd $(BACKEND) && pytest --cov=app --cov-report=term-missing

# Everything CI runs, in the same order, so `make ci` reproduces a red
# pipeline locally before you push.
ci: lint typecheck test

lite-image:
	docker build --build-arg SKIP_ML_STACK=true -t bag-counter:lite $(BACKEND)

full-image:
	docker build --build-arg SKIP_ML_STACK=false -t bag-counter:full $(BACKEND)

up:
	docker compose up --build

down:
	docker compose down
