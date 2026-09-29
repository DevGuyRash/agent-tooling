IMAGE := web:$(shell git rev-parse --short HEAD)

test:
	./scripts/run-tests.sh unit integration

build:
	docker build -t $(IMAGE) .

deploy:
	./scripts/deploy.sh $(ENV) $(IMAGE)

rollback:
	./scripts/rollback.sh $(ENV)

.PHONY: test build deploy rollback
