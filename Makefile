.PHONY: bootstrap doctor dev check test infra-up infra-down

bootstrap:
	pnpm bootstrap

doctor:
	pnpm run doctor

dev:
	pnpm dev

check:
	pnpm check

test:
	pnpm test

infra-up:
	pnpm infra:up

infra-down:
	pnpm infra:down
