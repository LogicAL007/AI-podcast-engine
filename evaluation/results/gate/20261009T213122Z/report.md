# Fact-check gate benchmark

122 labelled claims from https://clickhouse.com/docs/get-started/about/intro

## offline-word-overlap

- Catches 61% of unsupported claims (95% CI 50%-71%, n=87)
- Wrongly flags 17% of supported claims (95% CI 8%-33%, n=35)

| Category | Correct | Rate |
|---|---|---|
| distorted: negation | 0/14 | 0% |
| distorted: other product | 0/5 | 0% |
| distorted: quantifier | 0/6 | 0% |
| distorted: swap rows and columns | 0/8 | 0% |
| fabricated | 9/10 | 90% |
| misattributed | 22/22 | 100% |
| paraphrase | 7/13 | 54% |
| uncited | 22/22 | 100% |
| verbatim | 22/22 | 100% |
