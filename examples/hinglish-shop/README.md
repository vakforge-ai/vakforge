# Example: a Hinglish electronics shop

A small, entirely synthetic dataset for a two-shop electronics retailer in Jaipur, in the shape a real project starts with: an FAQ in Hinglish with a Devanagari section, two database exports, and a WhatsApp support chat. No audio, no real people.

Run `inspect` and `recommend` on it to see what vakforge does before any model is involved:

```bash
vakforge inspect examples/hinglish-shop/data -o inspect.json
vakforge recommend inspect.json -o recommend.json
```

The locale comes from `vakforge.yaml`, so no `--locale` flag is needed.

## What to look for

- `inspect` finds three languages in the FAQ (`hi-Latn`, `en-IN`, `hi`), a phone number and an email address, and turns the two CSV exports into tool candidates such as `lookup_orders_by_order_id`. The wrapped address in the chat is kept with its message rather than dropped.
- `recommend` names `tools` as the primary problem, routes the FAQ to retrieval, the tables to tools and the chat to a behaviour fine-tune, and then says fine-tuning is `blocked` for now: sixteen messages are below the floor. It says which paper or heuristic each bar comes from, and its first next step is to measure the prompt-plus-retrieval baseline, not to train.

## Expected output

`expected/inspect.json` and `expected/recommend.json` are what the current version produces. A test diffs them on every run, so a change in either is deliberate and reviewed, and the files double as a readable spec of both reports.
