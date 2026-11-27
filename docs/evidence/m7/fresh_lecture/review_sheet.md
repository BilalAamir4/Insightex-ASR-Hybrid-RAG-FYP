# Fresh lecture `yt-YyXP7yCfOIU`: blind review sheet, shared-window disagreements

For Bilal's guide-based review (ADR-0048 Amendment 12, decision 7). It covers the 5 shared windows where the two frozen labels differ: 3, 18, 19, 40, 43.

**How this sheet is blind.** In each window, one label is Bilal's (`bilal_pre_review.json`) and one is Fatima's (`fatima.json`). They are shown as **Labeller A** and **Labeller B**, assigned per window by a fixed random seed. The key mapping A/B to names is not in the repository. Judge each label only against the guide. Do not open `bilal.json`, `fatima.json`, `bilal_pre_review.json` or `agreement_bilal_fatima.json` until the marks are done.

**How to mark.** For each difference, tick one box for Labeller A and one for Labeller B. Name the rule when you tick "breaks a guide rule". After the marks are committed, the key is revealed:

- Only marks on Bilal's side can lead to a correction. Fatima's label is never changed.
- A correction is made only where a guide rule is broken. It is edited in `serve` and logged with `log-correction`, with reason text naming Amendment 12.
- Adding relations or importance flags only to meet decision 5's minimums is not a valid reason.

The rule quotes below are the guide's sections that each kind of difference touches. They were chosen by the kind of difference, not by reading the window, and none of them says which label is right.

Inputs: sample manifest sha256 `1307741c2f97c64b4c8f89bfe2abeeb417e11aad2c5a7c5111a44be2c9c1e6fd`; `bilal_pre_review.json` `84aec3fc04a6962bc004c73e5748fc844d6b0d58502d61015314bfb645936845`; `fatima.json` `d24ee89a1a0e851929f65a0865ed68df739f7cf6073371cf548d582c746fe48e`; `agreement_bilal_fatima.json` `d0b681ee0a844c3a06ad8ba475c07168bdaee32abf4501abc404c70e39983c91`; guide `m7_concepts.md` `5a0006fc97c1e8d7767bd3ee3ecc4a47b10cdf62a109e7022d2f737f353e9fd6`. Key file sha256: `2411720a4153f2711711952c54792833e917815164841eea1c96d1d964082de1` (kept outside the repository).

**To play a window:** open the lecture's `video.mp4` (its `normalise` stage folder in the workspace) in any player, and go to the times shown. Do not use `serve`: it shows Bilal's own labels, which would break the blinding.


---

## Window 3 (1:30–2:00)

### Window text

> پہلے پائیتھن کا کورڈ تھوڑا دیکھیں گے ایلانگ ویڈ تھیوری اور اینڈ میں ایکسرسائز ہوگی ہمارے پاس یہ سیمپل ڈیٹا سیٹ ہے اور اس میں سے ہم ایک کلسٹر فائن کرنا ہے کلسٹر فائن کرنے سے ہمیں ڈیٹا سیٹ کا انہرن نیچر پتا چلتا ہے اور وہ کافی ساری یوزفل انفرمیشن ہمیں دیتا ہے جیسے کہ اگر اس میں اگر ایک پوائنٹ اگر فرڈیولنٹ ٹرنجیکشن ہے لیسے ہم سٹور کے کچھ ٹرنجیکشن کو انالیسز کر رہے ہیں اور ایک پوائنٹ اگر وہ فرڈیولنٹ ہے

### Labeller A

- Concept: **K Mean Clustering**; aliases: none
- Relations: 0
- Important: false

### Labeller B

- Concepts: none
- Relations: 0
- Important: false

### Differences

**3.1** Concept **K Mean Clustering** is in Labeller A's label and not in Labeller B's

*Guide, "Concepts" (`m7_concepts.md` lines 29–46):*

> A concept is a named technical idea that a student could be quizzed on or could look up. That includes a term, an algorithm, a model, a metric, a technique or a named parameter.
>
> **Label a concept only if this window explains it or uses it substantively.** Each of these counts:
>
> - the window says what the concept is or what it is a kind of;
> - the window says how it works or why it is used;
> - the window gives a property or a problem of it;
> - the window uses it as a working part of the explanation.
>
> These do not count:
>
> - **A passing mention without explanation.** A topic announced by name, an item in a list that is not explained, or a reference to an earlier or later video. Leave these out.
> - **General words used in passing**, such as data, model, code, server or machine learning. Label one of these only when this window explains it.
> - **Example settings** such as a company, a product or a news story. These are not concepts. Label the technical idea the example illustrates, if the window explains that idea.
>
> A named parameter, such as the learning rate, is its own concept when the window explains it. It is not just an attribute of the algorithm it belongs to.
>
> Label each idea once per window, even if it is said many times. Two names for the same idea are one concept with aliases, not two concepts. Do not merge two ideas because a textbook treats them as related. Merging across windows and across names is M8's job (ADR-0019), not yours.

*Guide, "Unnamed concepts" (`m7_concepts.md` line 71):*

> If a window explains something substantive about a concept without saying its name (for example, it continues explaining batch learning with 'this' or 'it'), label that concept. Use the earlier part of the lecture only to identify which concept is meant. The substantive test still applies to this window's own text: it must say something about the concept, such as a property, a problem, how it works or why it's used. Don't label a concept just because it is the lecture's overall topic. Aliases come only from this window's text, so an unnamed concept usually has no aliases. Relations still need both concepts labelled in this window.

*Guide, "What you label" (`m7_concepts.md` line 11):*

> The unit is one window: a fixed 30-second slice of the lecture (ADR-0045). The tool shows the window's transcript text and plays that span of the video. Label only what is said inside this window. Use the audio when the transcript is wrong or unclear. The earlier part of the lecture may be used for one thing only: to identify which concept the window means when it does not say its name (see "Unnamed concepts"). Everything you record still comes from this window's own text: whether a concept is substantive, its aliases, the relations and importance. Do not use anything said after the window.

**Mark 3.1:**

  - Labeller A: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
  - Labeller B: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)


---

## Window 18 (9:00–9:30)

### Window text

> store کر دیا جس کو ہم data frame بولتے ہیں اب ہمیں data visualization کرنا ہے تاکہ ہمیں پتا چلا ہے کہ ہمارے data set میں چل کیا رہا ہے دیکھو machine learning میں data visualization اور data cleaning یہ دو چیزیں بہت ہی important ہوتی ہیں تو میں یہاں پہ جو df.age اور جو income ہے ان دونوں چیزوں کو میں ابھی یہاں پہ visualize کروں گا تو یہاں پہ scatter plot میں

### Labeller A

- Concept: **Data Visualization**; aliases: none
- Relations: 0
- Important: false

### Labeller B

- Concepts: none
- Relations: 0
- Important: true; cue: "In Machin Learning Data Cleaning & Visualization are important"

### Differences

**18.1** Concept **Data Visualization** is in Labeller A's label and not in Labeller B's

*Guide, "Concepts" (`m7_concepts.md` lines 29–46):*

> A concept is a named technical idea that a student could be quizzed on or could look up. That includes a term, an algorithm, a model, a metric, a technique or a named parameter.
>
> **Label a concept only if this window explains it or uses it substantively.** Each of these counts:
>
> - the window says what the concept is or what it is a kind of;
> - the window says how it works or why it is used;
> - the window gives a property or a problem of it;
> - the window uses it as a working part of the explanation.
>
> These do not count:
>
> - **A passing mention without explanation.** A topic announced by name, an item in a list that is not explained, or a reference to an earlier or later video. Leave these out.
> - **General words used in passing**, such as data, model, code, server or machine learning. Label one of these only when this window explains it.
> - **Example settings** such as a company, a product or a news story. These are not concepts. Label the technical idea the example illustrates, if the window explains that idea.
>
> A named parameter, such as the learning rate, is its own concept when the window explains it. It is not just an attribute of the algorithm it belongs to.
>
> Label each idea once per window, even if it is said many times. Two names for the same idea are one concept with aliases, not two concepts. Do not merge two ideas because a textbook treats them as related. Merging across windows and across names is M8's job (ADR-0019), not yours.

*Guide, "Unnamed concepts" (`m7_concepts.md` line 71):*

> If a window explains something substantive about a concept without saying its name (for example, it continues explaining batch learning with 'this' or 'it'), label that concept. Use the earlier part of the lecture only to identify which concept is meant. The substantive test still applies to this window's own text: it must say something about the concept, such as a property, a problem, how it works or why it's used. Don't label a concept just because it is the lecture's overall topic. Aliases come only from this window's text, so an unnamed concept usually has no aliases. Relations still need both concepts labelled in this window.

*Guide, "What you label" (`m7_concepts.md` line 11):*

> The unit is one window: a fixed 30-second slice of the lecture (ADR-0045). The tool shows the window's transcript text and plays that span of the video. Label only what is said inside this window. Use the audio when the transcript is wrong or unclear. The earlier part of the lecture may be used for one thing only: to identify which concept the window means when it does not say its name (see "Unnamed concepts"). Everything you record still comes from this window's own text: whether a concept is substantive, its aliases, the relations and importance. Do not use anything said after the window.

**Mark 18.1:**

  - Labeller A: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
  - Labeller B: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)

**18.2** Importance: Labeller A false, Labeller B true

*Guide, "Importance" (`m7_concepts.md` lines 90–107):*

> Set `important = true` only when the teacher gives an explicit signal. The signal can be in any language:
>
> - the teacher says it is important;
> - the teacher says it is exam-relevant, or will come in the exam;
> - the teacher says it must be remembered;
> - the teacher says "note this" or something equivalent;
> - the teacher repeats a point and explicitly signals emphasis, for example "again, I am saying this again because…".
>
> These are not importance signals:
>
> - a definition by itself;
> - a summary;
> - a long explanation;
> - the word "important" used about something inside an example (see invented example B).
>
> When `important` is true, write the cue: a short English note of what the teacher said or did, for example "Says both types are important to understand." When `important` is false, the cue stays empty.
>
> The flag belongs to the window, not to a concept.

**Mark 18.2:**

  - Labeller A: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
  - Labeller B: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)


---

## Window 19 (9:30–10:00)

### Window text

> میرے کو clearly تین cluster دیکھ رہے ہیں ایک دو اور تین یہ scatter plot کو زیادہ informative بنانے کے لئے آپ x label اور y label بھی ڈال سکتے ہو میرا x label ہے age اور y label ہے income تو دیکھو یہ x اور y label آگئے ٹھیک ہے تو overall پتا چل گیا ہے کہ یہ تین cluster ہے تو اس لئے میں k-means کا ایک object create کروں گا

### Labeller A

- Concept: **Data Visualization**; aliases: none
- Relations: 0
- Important: true; cue: "In Machine Learning Data Visualization & Data Cleaning is very important"

### Labeller B

- Concepts: none
- Relations: 0
- Important: false

### Differences

**19.1** Concept **Data Visualization** is in Labeller A's label and not in Labeller B's

*Guide, "Concepts" (`m7_concepts.md` lines 29–46):*

> A concept is a named technical idea that a student could be quizzed on or could look up. That includes a term, an algorithm, a model, a metric, a technique or a named parameter.
>
> **Label a concept only if this window explains it or uses it substantively.** Each of these counts:
>
> - the window says what the concept is or what it is a kind of;
> - the window says how it works or why it is used;
> - the window gives a property or a problem of it;
> - the window uses it as a working part of the explanation.
>
> These do not count:
>
> - **A passing mention without explanation.** A topic announced by name, an item in a list that is not explained, or a reference to an earlier or later video. Leave these out.
> - **General words used in passing**, such as data, model, code, server or machine learning. Label one of these only when this window explains it.
> - **Example settings** such as a company, a product or a news story. These are not concepts. Label the technical idea the example illustrates, if the window explains that idea.
>
> A named parameter, such as the learning rate, is its own concept when the window explains it. It is not just an attribute of the algorithm it belongs to.
>
> Label each idea once per window, even if it is said many times. Two names for the same idea are one concept with aliases, not two concepts. Do not merge two ideas because a textbook treats them as related. Merging across windows and across names is M8's job (ADR-0019), not yours.

*Guide, "Unnamed concepts" (`m7_concepts.md` line 71):*

> If a window explains something substantive about a concept without saying its name (for example, it continues explaining batch learning with 'this' or 'it'), label that concept. Use the earlier part of the lecture only to identify which concept is meant. The substantive test still applies to this window's own text: it must say something about the concept, such as a property, a problem, how it works or why it's used. Don't label a concept just because it is the lecture's overall topic. Aliases come only from this window's text, so an unnamed concept usually has no aliases. Relations still need both concepts labelled in this window.

*Guide, "What you label" (`m7_concepts.md` line 11):*

> The unit is one window: a fixed 30-second slice of the lecture (ADR-0045). The tool shows the window's transcript text and plays that span of the video. Label only what is said inside this window. Use the audio when the transcript is wrong or unclear. The earlier part of the lecture may be used for one thing only: to identify which concept the window means when it does not say its name (see "Unnamed concepts"). Everything you record still comes from this window's own text: whether a concept is substantive, its aliases, the relations and importance. Do not use anything said after the window.

**Mark 19.1:**

  - Labeller A: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
  - Labeller B: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)

**19.2** Importance: Labeller A true, Labeller B false

*Guide, "Importance" (`m7_concepts.md` lines 90–107):*

> Set `important = true` only when the teacher gives an explicit signal. The signal can be in any language:
>
> - the teacher says it is important;
> - the teacher says it is exam-relevant, or will come in the exam;
> - the teacher says it must be remembered;
> - the teacher says "note this" or something equivalent;
> - the teacher repeats a point and explicitly signals emphasis, for example "again, I am saying this again because…".
>
> These are not importance signals:
>
> - a definition by itself;
> - a summary;
> - a long explanation;
> - the word "important" used about something inside an example (see invented example B).
>
> When `important` is true, write the cue: a short English note of what the teacher said or did, for example "Says both types are important to understand." When `important` is false, the cue stays empty.
>
> The flag belongs to the window, not to a concept.

**Mark 19.2:**

  - Labeller A: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
  - Labeller B: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)


---

## Window 40 (20:00–20:30)

### Window text

> ایک دو تین fc بڑھاتے رہتے اور ہر ایک کے لئے ssc calculate کرتے ہیں بعد میں یہ plot کرتے ہیں تو ہمیں ssc calculate کرنی ہے k means model بنانے کے بعد میں اس کو fit کروں گا fit مطلب training کروں گا ہمارے standard دو ہی feature ہے age اور income اس کے اگر میں میں نے training کر دی اور اس کے بعد میں km dot inertia جو ہے

### Labeller A

- Concept: **Elbow Technique**; aliases: none
- Relations: 0
- Important: false

### Labeller B

- Concepts: none
- Relations: 0
- Important: false

### Differences

**40.1** Concept **Elbow Technique** is in Labeller A's label and not in Labeller B's

*Guide, "Concepts" (`m7_concepts.md` lines 29–46):*

> A concept is a named technical idea that a student could be quizzed on or could look up. That includes a term, an algorithm, a model, a metric, a technique or a named parameter.
>
> **Label a concept only if this window explains it or uses it substantively.** Each of these counts:
>
> - the window says what the concept is or what it is a kind of;
> - the window says how it works or why it is used;
> - the window gives a property or a problem of it;
> - the window uses it as a working part of the explanation.
>
> These do not count:
>
> - **A passing mention without explanation.** A topic announced by name, an item in a list that is not explained, or a reference to an earlier or later video. Leave these out.
> - **General words used in passing**, such as data, model, code, server or machine learning. Label one of these only when this window explains it.
> - **Example settings** such as a company, a product or a news story. These are not concepts. Label the technical idea the example illustrates, if the window explains that idea.
>
> A named parameter, such as the learning rate, is its own concept when the window explains it. It is not just an attribute of the algorithm it belongs to.
>
> Label each idea once per window, even if it is said many times. Two names for the same idea are one concept with aliases, not two concepts. Do not merge two ideas because a textbook treats them as related. Merging across windows and across names is M8's job (ADR-0019), not yours.

*Guide, "Unnamed concepts" (`m7_concepts.md` line 71):*

> If a window explains something substantive about a concept without saying its name (for example, it continues explaining batch learning with 'this' or 'it'), label that concept. Use the earlier part of the lecture only to identify which concept is meant. The substantive test still applies to this window's own text: it must say something about the concept, such as a property, a problem, how it works or why it's used. Don't label a concept just because it is the lecture's overall topic. Aliases come only from this window's text, so an unnamed concept usually has no aliases. Relations still need both concepts labelled in this window.

*Guide, "What you label" (`m7_concepts.md` line 11):*

> The unit is one window: a fixed 30-second slice of the lecture (ADR-0045). The tool shows the window's transcript text and plays that span of the video. Label only what is said inside this window. Use the audio when the transcript is wrong or unclear. The earlier part of the lecture may be used for one thing only: to identify which concept the window means when it does not say its name (see "Unnamed concepts"). Everything you record still comes from this window's own text: whether a concept is substantive, its aliases, the relations and importance. Do not use anything said after the window.

**Mark 40.1:**

  - Labeller A: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
  - Labeller B: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)


---

## Window 43 (21:30–22:00)

### Window text

> کو تو یہ plot کرنے سے ہمیں یہ elbow plot مل گیا اور یہ elbow plot میں آپ کلیرلی دیکھ سکتے ہو کہ k equal to three کی جو ہے value وہاں پہ میرا elbow ہے تو k equal to three is the most appropriate value to start with اب ہم سب سے انٹرسٹنگ جو part ہے اس tutorial کا اس میں مو کرتے ہیں اور وہ ہے exercise ہم نے iris flower data set کا use پہلے بھی کیا ہے یہ اسکی لرن لیبری میں یہ data set آپ کو ready میں مل جاتا ہے

### Labeller A

- Concept: **Finding K using Elbow Plot**; aliases: none
- Relations: 0
- Important: false

### Labeller B

- Concept: **Elbow Technique**; aliases: none
- Relations: 0
- Important: false

### Differences

**43.1** Concepts that do not match under the string rule: Labeller A **Finding K using Elbow Plot** / Labeller B **Elbow Technique**

*Guide, "Concepts" (`m7_concepts.md` lines 29–46):*

> A concept is a named technical idea that a student could be quizzed on or could look up. That includes a term, an algorithm, a model, a metric, a technique or a named parameter.
>
> **Label a concept only if this window explains it or uses it substantively.** Each of these counts:
>
> - the window says what the concept is or what it is a kind of;
> - the window says how it works or why it is used;
> - the window gives a property or a problem of it;
> - the window uses it as a working part of the explanation.
>
> These do not count:
>
> - **A passing mention without explanation.** A topic announced by name, an item in a list that is not explained, or a reference to an earlier or later video. Leave these out.
> - **General words used in passing**, such as data, model, code, server or machine learning. Label one of these only when this window explains it.
> - **Example settings** such as a company, a product or a news story. These are not concepts. Label the technical idea the example illustrates, if the window explains that idea.
>
> A named parameter, such as the learning rate, is its own concept when the window explains it. It is not just an attribute of the algorithm it belongs to.
>
> Label each idea once per window, even if it is said many times. Two names for the same idea are one concept with aliases, not two concepts. Do not merge two ideas because a textbook treats them as related. Merging across windows and across names is M8's job (ADR-0019), not yours.

*Guide, "Canonical label" (`m7_concepts.md` lines 50–55):*

> The label is the standard English name, as the course textbook uses it (ADR-0029: Géron, *Hands-On Machine Learning*, 2nd edition).
>
> - Write it as the book writes it in running text: lower case unless it is a name or an acronym, and singular. Matching ignores case, punctuation and spaces anyway.
> - Prefer the full name over an acronym, and put the acronym in the aliases if the speaker said it. For example, "support vector machine" with the alias "SVM".
> - If the book does not cover the idea, use the most common English name for it.
> - If the speaker named the idea only in Urdu or Hindi, the label is still the English name.

*Guide, "Aliases" (`m7_concepts.md` lines 59–67):*

> Aliases hold every other name the speaker actually said for this concept in this window:
>
> - English variants, such as "batch machine learning" next to "batch learning";
> - Urdu or Hindi names, copied exactly as the transcript writes them. That is usually Urdu script. If the transcript writes a name in Latin letters (Roman Urdu or Hindi), copy that;
> - abbreviations.
>
> Copy the transcript's spelling even when it is odd, because that is the text the model sees. Do not add names the speaker did not say. Do not add your own romanisation of a name the transcript writes in Urdu script. Do not repeat the label as an alias.
>
> Leave the aliases empty when the label is the only name the speaker used.

*Guide, "Unnamed concepts" (`m7_concepts.md` line 71):*

> If a window explains something substantive about a concept without saying its name (for example, it continues explaining batch learning with 'this' or 'it'), label that concept. Use the earlier part of the lecture only to identify which concept is meant. The substantive test still applies to this window's own text: it must say something about the concept, such as a property, a problem, how it works or why it's used. Don't label a concept just because it is the lecture's overall topic. Aliases come only from this window's text, so an unnamed concept usually has no aliases. Relations still need both concepts labelled in this window.

**Mark 43.1:**

  - Labeller A: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
  - Labeller B: [ ] no guide rule broken  [ ] breaks a guide rule: ________ (name the rule)
