# Build the manuscript. Requires a TeX distribution with latexmk.
#   make          -> main.pdf
#   make clean    -> remove build artefacts
#   make regen    -> re-run the experiments, then build

MAIN := main

.PHONY: all regen clean distclean docker

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex refs.bib generated_macros.tex \
             $(wildcard sections/*.tex) $(wildcard tables/*.tex) $(wildcard figures/*.pdf)
	latexmk -pdf -interaction=nonstopmode -halt-on-error $(MAIN).tex

regen:
	cd ../code && python run_experiments.py --dump-artifacts
	$(MAKE) all

docker:
	docker run --rm -v "$(CURDIR)":/w -w /w texlive/texlive:latest \
	    latexmk -pdf -interaction=nonstopmode $(MAIN).tex

clean:
	latexmk -c $(MAIN).tex || true
	rm -f *.aux *.bbl *.blg *.log *.out *.toc *.fls *.fdb_latexmk

distclean: clean
	rm -f $(MAIN).pdf
