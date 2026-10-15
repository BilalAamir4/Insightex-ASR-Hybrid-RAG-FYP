# M7 concept labelling guide

This guide is for the two human labellers, Bilal and Fatima. It covers how to label lecture windows for the M7 gold set: concepts, relations and importance. The rules for using the gold set (sample sizes, matching, metrics) are in ADR-0048. The tool is `tools/label_concepts/` (see its README).

The gold set has to be made by people. Do not paste a window into an LLM, do not look at any model's extraction output for the lecture until both of you have finished labelling it, and do not copy labels from any machine-made source. The M7 numbers measure the model against your labels. If your labels come from a model, those numbers mean nothing.

Status: version 1, written before the shared-window discussion. The procedure below says when this guide may change, and the changelog at the end records each change.

## What you label

The unit is one window: a fixed 30-second slice of the lecture (ADR-0045). The tool shows the window's transcript text and plays that span of the video. Label only what is said inside this window. Use the audio when the transcript is wrong or unclear. Do not use anything said before or after the window.

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
- **A concept defined in another window is not labelled here.** Labelling it here would also need a relation with one end in another window, which is not allowed either. Each window is labelled from its own text only.
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
- **Incremental learning**: the window explains it (training in small pieces), so it is a concept. The book's wording is "learning incrementally" (not checked against the book for this guide; check it before the discussion). The speaker's "incremental training" is an alias. Do not merge it into online learning, even if you know the book links the two: the speaker does not link them in this window.
- **No alias "batch"**: the speaker says "batch کے case میں" ("in the batch case"), but "batch" alone also names a batch of data. A shorthand that also names something else is not an alias.
- **important = false**: this is a definition with no teacher signal. A definition alone is not important.
- *Data*, *server* and *real-world problem* are general words used in passing, so they are not labelled.

### Invented examples (not from any lecture)

These are marked invented because Day 4 has no named parameter, and its only use of "important" about an example is in a gold window, which cannot be discussed here.

- **A. Named parameter (invented).** "The learning rate decides how big each step of gradient descent is. If it is too big, training jumps around and never settles." Concepts: "learning rate" and "gradient descent". The learning rate is explained, and gradient descent is used substantively, as what the steps belong to. Relation: `part_of(learning rate, gradient descent)`, because the speaker presents the learning rate as a setting of gradient descent. Not important.
- **B. "Important" that is not a teacher signal (invented).** "This news story was important to everyone yesterday, so the feed filled up with it." This is about the example's content, so `important = false`. Compare: "Note this down, it will come in the exam." That is `important = true`, with the cue "Says to note it down for the exam."

## Procedure

Run every command from the repo root. The exact commands are in `tools/label_concepts/README.md`.

1. **Sample.** Either of you runs `sample` once for the lecture and commits `sample.json`. Never re-run it after labelling has started.
2. **Shared windows first, separately.** You both label the 10 shared windows (marked "shared" in the tool; they come first) without discussing them. Run `validate`.
3. **Agreement.** Run `agreement` on the two files and commit `agreement_<a>_<b>.json`. This is the human agreement ceiling. Do not edit your own files for those windows after this, because they are the record the ceiling was computed from.
4. **Discuss** every disagreement the command lists. Agree a single version of each shared window and enter it with `serve --labeller consensus`.
5. **Update this guide once**, with the rules the discussion changed. Add a changelog entry that names the windows that prompted each change.
6. **Split.** Each of you labels the non-shared windows the manifest assigns to you (alternating in time order), under the updated guide. Run `validate` until it reports no problems.
7. **Merge.** Run `merge` to write `gold.json`: the consensus labels for the shared windows, and each labeller's own windows for the rest. Commit it.

For the dev lecture (Day 4), the sample is the census of its 20 eligible windows: 10 shared and 5 each. For the held-out lecture it is 40 sampled windows: 10 shared and 15 each.

## Changelog

- v1 (15 Oct 2026): first version, before any labelling.
- v1, addition (15 Oct 2026, still before any labelling): the rule "label the text shown in the window, not the audio boundary". Prompted by the browser check.
- v1, correction (15 Oct 2026, still before any labelling): removed every statement about what a gold window contains. The boundary example is now window 3's last segment (a reserved window). Gloss words filled in from neighbouring windows are replaced by "…". A concept defined in another window is now covered by a general rule instead of a named example.
