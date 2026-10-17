# M7 concept labelling guide

This guide is for the human labellers: Bilal, who labels every gold window (ADR-0048 Amendment 1), and Fatima, who labels the 10 shared Day 4 windows as a second annotator (Amendment 3). It covers how to label lecture windows for the M7 gold set: concepts, relations and importance. The rules for using the gold set (sample sizes, matching, metrics) are in ADR-0048. The tool is `tools/label_concepts/` (see its README).

The gold set has to be made by people. Do not paste a window into an LLM, do not look at any model's extraction output for the lecture until its gold set is merged, and do not copy labels from any machine-made source. The M7 numbers measure the model against your labels. If your labels come from a model, those numbers mean nothing.

Status: version 1 with its one rule update (17 Oct 2026, "Unnamed concepts"); no further rule changes are planned. The procedure below says when this guide may change, and the changelog at the end records each change.

## What you label

The unit is one window: a fixed 30-second slice of the lecture (ADR-0045). The tool shows the window's transcript text and plays that span of the video. Label only what is said inside this window. Use the audio when the transcript is wrong or unclear. The earlier part of the lecture may be used for one thing only: to identify which concept the window means when it does not say its name (see "Unnamed concepts"). Everything you record still comes from this window's own text: whether a concept is substantive, its aliases, the relations and importance. Do not use anything said after the window.

**Label the text shown in the window, not the audio boundary.** The model receives exactly the text shown, nothing more and nothing less. Whisper splits speech into segments, and each segment belongs to the one window in which it *starts*, even when it runs past the window's end. So the text can start or end a moment away from the 30 s mark:
- **Window 3 (1:30–2:00, a reserved example) shows this.** Its text ends with «کیونکہ to be honest یہ important ہے» ("because, to be honest, this is important"). That segment starts at 1:58.98 and ends at 2:01.38, so "Play window" stops before the speaker finishes it. It still belongs to window 3 and nowhere else, and its cue is labelled in window 3.
- No segment appears in two windows. A sentence can still be split across two windows when Whisper splits it into two segments.
- When a sentence is split, label in each window what that window's own text supports. If both parts name and explain a concept, label it in both windows.
- Use the audio only to read the shown text correctly, not to add words from outside it. 22 of Day 4's 351 segments cross a window edge.

For each window you record:

- **concepts**: each one has a canonical English label and its aliases;
- **relations** between concepts of this window;
- **important**: true or false, plus a cue when it is true.

A window can have no concepts. In that case press "Save this window" so the window counts as labelled. `is_recap` exists in the schema, but it is not labelled (F20 is Exploratory).

## Concepts

A concept is a named technical idea that a student could be quizzed on or could look up. That includes a term, an algorithm, a model, a metric, a technique or a named parameter.

**Label a concept only if this window explains it or uses it substantively.** Each of these counts:

- the window says what the concept is or what it is a kind of;
- the window says how it works or why it is used;
- the window gives a property or a problem of it;
- the window uses it as a working part of the explanation.

These do not count:

- **A passing mention without explanation.** A topic announced by name, an item in a list that is not explained, or a reference to an earlier or later video. Leave these out.
- **General words used in passing**, such as data, model, code, server or machine learning. Label one of these only when this window explains it.
- **Example settings** such as a company, a product or a news story. These are not concepts. Label the technical idea the example illustrates, if the window explains that idea.

A named parameter, such as the learning rate, is its own concept when the window explains it. It is not just an attribute of the algorithm it belongs to.

Label each idea once per window, even if it is said many times. Two names for the same idea are one concept with aliases, not two concepts. Do not merge two ideas because a textbook treats them as related. Merging across windows and across names is M8's job (ADR-0019), not yours.

### Canonical label

The label is the standard English name, as the course textbook uses it (ADR-0029: Géron, *Hands-On Machine Learning*, 2nd edition).

- Write it as the book writes it in running text: lower case unless it is a name or an acronym, and singular. Matching ignores case, punctuation and spaces anyway.
- Prefer the full name over an acronym, and put the acronym in the aliases if the speaker said it. For example, "support vector machine" with the alias "SVM".
- If the book does not cover the idea, use the most common English name for it.
- If the speaker named the idea only in Urdu or Hindi, the label is still the English name.

### Aliases

Aliases hold every other name the speaker actually said for this concept in this window:

- English variants, such as "batch machine learning" next to "batch learning";
- Urdu or Hindi names, copied exactly as the transcript writes them. That is usually Urdu script. If the transcript writes a name in Latin letters (Roman Urdu or Hindi), copy that;
- abbreviations.

Copy the transcript's spelling even when it is odd, because that is the text the model sees. Do not add names the speaker did not say. Do not add your own romanisation of a name the transcript writes in Urdu script. Do not repeat the label as an alias.

Leave the aliases empty when the label is the only name the speaker used.

### Unnamed concepts

If a window explains something substantive about a concept without saying its name (for example, it continues explaining batch learning with 'this' or 'it'), label that concept. Use the earlier part of the lecture only to identify which concept is meant. The substantive test still applies to this window's own text: it must say something about the concept, such as a property, a problem, how it works or why it's used. Don't label a concept just because it is the lecture's overall topic. Aliases come only from this window's text, so an unnamed concept usually has no aliases. Relations still need both concepts labelled in this window.

## Relations

Record only the relations the speaker states or clearly implies inside this window. Do not add relations from your own knowledge, from the textbook, or from other windows. Both ends of a relation must be concepts you labelled in this window. If one end is only in a neighbouring window, leave the relation out.

The four types:

| Type | Meaning | Direction |
|---|---|---|
| `prerequisite_of(A, B)` | A must be understood before B | directed |
| `part_of(A, B)` | A is a component of B | directed |
| `example_of(A, B)` | A is an instance of B | directed |
| `contrasts_with(A, B)` | A and B are set against each other | symmetric: enter it once, either way round |

When you are unsure whether the speaker implies a relation, leave it out. A missing relation costs less than an invented one.

## Importance

Set `important = true` only when the teacher gives an explicit signal. The signal can be in any language:

- the teacher says it is important;
- the teacher says it is exam-relevant, or will come in the exam;
- the teacher says it must be remembered;
- the teacher says "note this" or something equivalent;
- the teacher repeats a point and explicitly signals emphasis, for example "again, I am saying this again because…".

These are not importance signals:

- a definition by itself;
- a summary;
- a long explanation;
- the word "important" used about something inside an example (see invented example B).

When `important` is true, write the cue: a short English note of what the teacher said or did, for example "Says both types are important to understand." When `important` is false, the cue stays empty.

The flag belongs to the window, not to a concept.

## Worked examples

All three come from the Day 4 dev lecture (workspace `sha256-de27cb67c2acbedebd0c2c7416932b8a`). These windows are reserved: they are excluded from the gold sample, and the reason for each is recorded in the sample manifest (`--exclude`). The English text is a gloss of the transcript, not a verbatim translation.

### Window 0 (0:00–0:30): passing mentions, nothing labelled (reserved: "passing mention")

> Gloss: "Hello guys, welcome to my channel. This is 100 days of machine learning, day 4, and today's topic is batch versus online learning. In the previous video we studied types of machine learning, where we saw the different types on the basis of the amount of supervision required to train a machine learning algorithm: supervised, unsupervised, semi-supervised, reinforcement."

```json
{"concepts": [], "relations": [], "important": false, "cue": null}
```

- *Batch learning* and *online learning* are only announced as the day's topic. That is a passing mention.
- *Supervised, unsupervised, semi-supervised* and *reinforcement learning* are a list recalled from the previous video, with no explanation in this window. Do not label them.
- *Machine learning* is the general subject and is not explained here.
- If a later window explains any of these, label it there.

### Window 3 (1:30–2:00): an importance cue, aliases, and a relation (reserved: "importance cue")

> Gloss: "…on your own machine, that is called the development environment. Now, machine learning software behaves, or runs, differently on the server, and on that basis we will study two types of machine learning today. One of them is batch learning, or batch machine learning, which we also call offline learning, and the second one is online machine learning, or online learning. We will study both of them in great detail because, to be honest, this is important."

The cue in the transcript: «ان دونوں کو ہم لوگ بہت detail میں پڑھیں گے کیونکہ to be honest یہ important ہے»

```json
{
  "concepts": [
    {"label": "development environment", "aliases": []},
    {"label": "batch learning", "aliases": ["batch machine learning", "offline learning"]},
    {"label": "online learning", "aliases": ["online machine learning"]}
  ],
  "relations": [
    {"head": "batch learning", "type": "contrasts_with", "tail": "online learning"}
  ],
  "important": true,
  "cue": "Says both types will be studied in detail because they are important."
}
```

- **important**: the teacher says outright that the topic is important. The cue is an English note, not a copy of the transcript.
- **Aliases**: "offline learning" is a name the speaker gives for batch learning ("which we also call…"). It is an alias, not a second concept. The label follows the book ("batch learning").
- **Development environment**: the window says what it is (your own machine), so it is labelled.
- **A concept defined in another window is labelled here only if this window's own text says something substantive about it** (named or not; see "Unnamed concepts"). Being defined elsewhere, or only referred to here, is not enough. A relation still needs both ends labelled in this window.
- **Relation**: the speaker sets up batch and online learning as the two opposite types to be compared. That is a clearly implied `contrasts_with`.
- These two are introduced, not fully explained, but they still count as substantive. The window says what kind of thing each is (a type of machine learning, distinguished by how the model is trained on the server) and gives their alternative names. Window 0 only says the topic's name, and that is the line between the two.

### Window 5 (2:30–3:00): a stated relation, and a definition that is not important (reserved: "stated relation")

> Gloss: "…use to train machine learning, to train the machine learning model. That is, in the batch case, when you train you use all of your data. There is no incremental training. Incremental training means [training] in small pieces, which you don't do here: you train with the whole lot at once. Now since the data, if you are working on a real-world problem, will generally be big, if you go to train very big data on the server…"

```json
{
  "concepts": [
    {"label": "batch learning", "aliases": []},
    {"label": "incremental learning", "aliases": ["incremental training"]}
  ],
  "relations": [
    {"head": "batch learning", "type": "contrasts_with", "tail": "incremental learning"}
  ],
  "important": false,
  "cue": null
}
```

- **Relation**: the speaker states it: in batch learning "there is no incremental training".
- **Incremental learning**: the window explains it (training in small pieces), so it is a concept. The book's wording is "learning incrementally" (not checked against the book for this guide; check it before the review in the procedure). The speaker's "incremental training" is an alias. Do not merge it into online learning, even if you know the book links the two: the speaker does not link them in this window.
- **No alias "batch"**: the speaker says "batch کے case میں" ("in the batch case"), but "batch" alone also names a batch of data. A shorthand that also names something else is not an alias.
- **important = false**: this is a definition with no teacher signal. A definition alone is not important.
- *Data*, *server* and *real-world problem* are general words used in passing, so they are not labelled.

### Invented examples (not from any lecture)

These are marked invented because Day 4 has no named parameter, and its only use of "important" about an example is in a gold window, which cannot be discussed here.

- **A. Named parameter (invented).** "The learning rate decides how big each step of gradient descent is. If it is too big, training jumps around and never settles." Concepts: "learning rate" and "gradient descent". The learning rate is explained, and gradient descent is used substantively, as what the steps belong to. Relation: `part_of(learning rate, gradient descent)`, because the speaker presents the learning rate as a setting of gradient descent. Not important.
- **B. "Important" that is not a teacher signal (invented).** "This news story was important to everyone yesterday, so the feed filled up with it." This is about the example's content, so `important = false`. Compare: "Note this down, it will come in the exam." That is `important = true`, with the cue "Says to note it down for the exam."

## Procedure

Run every command from the repo root. The exact commands are in `tools/label_concepts/README.md`.

Bilal makes the gold set (ADR-0048 Amendment 1). On Day 4, Fatima labels the 10 shared windows as a second annotator (Amendment 3); her labels give the inter-annotator figure and never enter the gold set. Reports describe the gold set as made by one annotator, with a second annotator's labels on the shared windows used for agreement and review.

1. **Sample.** Run `sample` once for the lecture and commit `sample.json`. Never re-run it after labelling has started. (To change who labels which window, use `reassign`, which keeps the same windows.)
2. **First pass.** Label the windows the manifest assigns to you, as `bilal`. Run `validate`, then commit `bilal.json`. (Day 4: done on 15 windows before the reassignment.)
3. **The one rule update** (Day 4 only; done 17 Oct 2026, "Unnamed concepts"). The first pass may change the rules once, with a changelog entry, and never in a way that states what a gold window contains. After it the guide is frozen. The held-out lecture skips this step and is labelled under the frozen guide.
4. **Revise and finish.** Revise all your labels under the updated guide, and label the windows not labelled yet (Day 4: windows 6, 10, 14, 18 and 22). Run `validate` until it reports no problems, then commit `bilal.json`.
5. **Second annotator (Day 4, Amendment 3).** Fatima labels the 10 shared windows (2, 4, 8, 9, 11, 13, 16, 17, 19 and 21), as `fatima`, under this guide as it stands. She labels blind: she does not see `bilal.json` or any of Bilal's labels, and nobody discusses those windows' labels with her until her file is committed. The tool shows her only those 10 windows and only her own labels. Run `validate --labeller fatima`, then commit `fatima.json`.
6. **Inter-annotator agreement.** Run `agreement --a bilal --b fatima` (string rule only). The first run freezes `bilal.json` as `bilal_pre_review.json`, and the figure is always computed on that frozen file. Commit `agreement_bilal_fatima.json` and `bilal_pre_review.json`. This is the inter-annotator figure. It is compared only with the model's string-rule-only concept F1.
7. **Review.** Bilal goes through the disagreements the report lists. He may correct clear errors in his own labels on the shared windows, and only there. Each correction is logged with its reason (`log-correction`) right after it is made in the tool. Disagreements that are matters of reading, not clear errors, stay as they are. The guide does not change: its one rule update is already used. Run `validate --labeller bilal` until it reports no problems (it refuses unlogged changes), then commit `bilal.json` and `corrections_bilal.json`.
8. **Merge.** Run `merge` to write `gold.json` from the reviewed `bilal.json` alone. Commit it.

For the dev lecture (Day 4), the sample is the census of its 20 eligible windows, all Bilal's, 10 of them shared (and labelled by Fatima too). For the held-out lecture it is 40 sampled windows, all Bilal's, 10 of them shared; whether a second annotator labels them is decided in a new ADR amendment before that lecture is sampled.

The `bilal_repeat` self-repeat of Amendment 1 is dropped (Amendment 3). A consensus procedure (both label the shared windows, a discussion agrees a `consensus` version, `merge` takes the shared windows from it) is not used for Day 4 and would need a new ADR amendment.

## Changelog

- v1 (15 Oct 2026): first version, before any labelling.
- v1, addition (15 Oct 2026, still before any labelling): the rule "label the text shown in the window, not the audio boundary". Prompted by the browser check.
- v1, correction (15 Oct 2026, still before any labelling): removed every statement about what a gold window contains. The boundary example is now window 3's last segment (a reserved window). Gloss words filled in from neighbouring windows are replaced by "…". A concept defined in another window is now covered by a general rule instead of a named example.
- v1, procedure change (17 Oct 2026; not the one post-review rule update): one labeller (ADR-0048 Amendment 1). Bilal labels every window; the two-labeller agreement and consensus steps are replaced by a blind repeat of the shared windows at least 2 days later (`bilal_repeat`, the intra-rater consistency figure), a review, the one guide update and a revision of his own labels, which become the gold set. No labelling rule changed.
- v1, rule update (17 Oct 2026; the one rule update, before the repeat and before any model output): new "Unnamed concepts" rule (a window that explains something substantive about a concept without naming it labels that concept; earlier context only identifies which concept is meant). The "Label only what is said inside this window" paragraph now allows that identification while content still comes only from the window, and the window 3 note on concepts defined in another window is reworded to match. Prompted by Bilal's first pass, in which 7 windows explained a concept without naming it.
- v1, procedure order (17 Oct 2026; no rule change): the rule update comes after the first pass. Then you revise and finish all windows, and only after that the blind repeat runs (at least 2 days later), so the repeat is made under the updated guide. The consistency figure is computed on the finished `bilal.json`, and merge follows it with no further revision.
- v1, procedure change (17 Oct 2026, ADR-0048 Amendment 3; no rule change, before any model output): Fatima labels the 10 shared Day 4 windows blind as a second annotator, replacing the `bilal_repeat` self-repeat and the 2-day wait. `agreement` bilal vs fatima (string rule only, on Bilal's frozen pre-review labels) is the inter-annotator figure. Bilal then reviews the disagreements and may correct clear errors in his own shared-window labels, each logged with its reason. Gold stays his labels; the guide's rules do not change.
