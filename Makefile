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

.PHONY: clean probe-image
# Wave 2 C: remove the probe image, leftover probe containers and probe-labelled volumes only
# (never a global volume prune: that would touch other projects, CLAUDE.md rule 15).
clean:
	-docker rm -f $$(docker ps -aq --filter name=av-probe-) 2>/dev/null
	-docker rmi -f av-probe:latest
	-docker volume prune -f --filter label=av.probe=1

probe-image:
	docker build -t av-probe:latest -f docker/probe.Dockerfile docker
