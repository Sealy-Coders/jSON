.PHONY: help web batch demo doctor test eval noise docker docker-batch clean

help:
	@echo "make web      – interfejs WWW (http://127.0.0.1:8000)"
	@echo "make batch    – input/**/*.pdf → output/**/*.json"
	@echo "make demo     – wbudowana sprawa demo (bez PDF i OCR)"
	@echo "make doctor   – diagnostyka środowiska (Python, pakiety, Tesseract+pol)"
	@echo "make test     – pytest"
	@echo "make eval     – F1 vs gold/ + odporność na szum"
	@echo "make docker   – UI w Dockerze (CPU, z Tesseractem pol)"
	@echo "make docker-batch – przetwarzanie input/ → output/ w Dockerze"

web:
	./run.sh web
batch:
	./run.sh batch
demo:
	./run.sh demo --noise 0.1
doctor:
	./run.sh doctor
test:
	./run.sh test
eval:
	./run.sh eval
noise:
	RATES=0,0.05,0.1,0.2 ./run.sh eval
docker:
	docker compose up --build web
docker-batch:
	docker compose run --rm batch
clean:
	rm -rf .venv .pytest_cache reports
