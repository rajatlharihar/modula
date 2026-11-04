# Modula

A Python project on choosing a modular smartphone with Generative AI, inspired by Google's Project Ara. A person describes how they use a phone. Claude turns that into a nine-axis need vector, and a constrained search picks the modules and places them on the frame.

Claude never chooses hardware. It reads the person and explains the result. The Python search enforces budget, frame space, module dependencies and placement rules.

## Run it

```
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

For live Claude replies, sign in once with `claude auth login` (`claude.exe auth login` in Windows PowerShell). Without that, the examples use saved Claude replies and typed requests use keyword matching. The app says which one it's using.

## Files

- `modula/catalogue.py`: 23 modules, the 2 x 6 frame and pairwise interactions. Prices, masses and power figures are illustrative.
- `modula/engine.py`: configuration vectors, scoring, search and placement.
- `modula/prompts.py`: prompt versions v1, v2 and v3, the explanation prompt and the reply parser.
- `modula/keyword_parser.py`: non-AI baseline and fallback.
- `modula/llm.py`: calls Claude through the Claude Code command line.
- `modula/figures.py`: the phone drawing and vector chart.
- `eval/personas.json`: hand-labelled personas, 8 dev and 16 held-out test.
- `eval/replies/`: the recorded model replies behind the reported results.

## Check the results

```
py -m unittest discover tests
py eval/score.py test
```
