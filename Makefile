# Wave 1 owns `setup`; Wave 2 C adds `clean`; Wave 2 D adds `demo` (and owns the rest).
.PHONY: setup test

OPA_VERSION := v1.21.0
OPA_SHA256  := 5eef70644868bb04d0556bcc795ee42f2ab379e73f51d1bfa30f83e1305bc9b9
OPA_URL     := https://github.com/open-policy-agent/opa/releases/download/$(OPA_VERSION)/opa_linux_amd64_static

setup: bin/opa
	uv sync

bin/opa:
	mkdir -p bin
	curl -fsSL -o bin/opa.download $(OPA_URL)
	echo "$(OPA_SHA256)  bin/opa.download" | sha256sum -c -
	chmod +x bin/opa.download && mv bin/opa.download bin/opa
	./bin/opa version | head -1

test:
	uv run pytest -q
