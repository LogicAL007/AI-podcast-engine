# AI-Powered Podcast Creation with Dynamic Content: presenter's guide

This folder holds the COMP 5112 research methodology proposal deck, [AI_Podcast_Proposal.pptx](AI_Podcast_Proposal.pptx). This guide covers it page by page: what each slide shows, what to say, and what the cited research found and why it supports that slide.

- **Length:** 25 slides, 22 of them presented, plus 3 reference pages. The scripts below total about 1,570 words: about 10½ minutes read at 150 words a minute, or 12 to 14 minutes with pauses and slide changes.
- **Speaker notes:** each slide's script is also in its notes, so presenter view shows it.
- **Design:** white pages, near-black Arial text and one muted green accent. There is one message per page. The three research questions are named by topic (Accuracy, Format, Trust), never by number.
- **References:** 30 sources in APA style, each cited on the slide it supports.

## Before you present

- **NotebookLM:** the comparison on page 6 rests on Google's 2024 launch post. If NotebookLM has since added claim checking or automatic refresh, change that row.
- **Ethics review:** ask the instructor whether COMP 5112 holds an approved teaching protocol. If the data will feed your thesis, it cannot use one; see page 19.
- **Dates:** set the week numbers on page 20 to the course calendar.
- **Planned, not built:** page 10 describes two things the current code does not do yet: giving the rewrite its neighbouring lines as fixed context, and crossfading at segment joins. Present them as planned, which is how the slide words them.

---

## Page 1 · Title

**What it shows.** The title, the one-line description, the two authors with their student IDs (Saidul Alam's is still blank), then program, university and term. A quiet waveform sits on the right.

**Script.**
> Good morning. My name is Ayomide Omotosho, and this is my research proposal for COMP 5112. The project is a system that makes podcast episodes from live, changing sources: it finds the sources, writes a two-host conversation that cites them, checks every claim, voices it, and publishes it. When the sources change, it updates only the parts of the episode that are affected.

**Research behind it.** None on this page; the claims are developed and cited from page 3 on.

## Page 2 · What this proposal covers

**What it shows.** Four numbered parts: Motivation, Methodology, Timeline, References.

**Script.**
> The talk has four parts. First, why this is worth doing and what already exists. Second, how I will do it: the research design, the three studies, how Ontario's accessibility and human rights law shapes them, and ethics. Third, a twelve-week plan with three checkpoints. Last, the thirty sources behind the proposal.

**Research behind it.** None; this page follows the COMP 5112 proposal structure: motivation, methodology, timeline and bibliography.

## Page 3 · Audio opens written knowledge to more people

**What it shows.** Three figures: 1.3 billion people, 27% of Canadians, and 2.2 billion people. The takeaway is that audio is a second route into text, and every episode ships with a transcript.

**Script.**
> Start with who this is for. The World Health Organization estimates that 1.3 billion people, about one in six, live with a significant disability. In Canada, Statistics Canada counts 27 percent of people aged 15 and over. And 2.2 billion people worldwide have a vision impairment. Audio gives many of them another way into written knowledge. It is a second route, not a replacement, so every episode also comes with a transcript.

**Research behind it.**
- **World Health Organization (2022), *Global report on health equity for persons with disabilities*.** It estimates that 1.3 billion people, 16% of the world's population, experience significant disability. It documents how they face worse access to health and information. This is the global scale of the audience.
- **Statistics Canada (2023), *New data on disability in Canada, 2022*.** The Canadian Survey on Disability found that 27% of Canadians aged 15 and over, about 8.0 million people, had one or more disabilities. Seeing disabilities were reported by 7.4%, up 2.0 points since 2017. This grounds the audience in the Canadian context where the study runs.
- **World Health Organization (2019), *World report on vision*.** At least 2.2 billion people have a near or distance vision impairment. This group gains the most from an audio alternative to print.
- **Why the transcript matters:** the transcript keeps the episodes usable for Deaf and hard-of-hearing people. Page 15 ties this to WCAG.

## Page 4 · Sourced podcasts are slow to make and go stale

**What it shows.** Three problems, one line each: slow, stale, unsourced.

**Script.**
> The trouble is that sourced podcasts are hard to make. Research, scripting, recording and editing take hours for every episode. News and research change daily, so an episode can be out of date by the time it is released. And text-to-speech tools only read an article aloud: they do not produce a conversation, and they do not cite anything.

**Research behind it.** This page states the problem the project addresses. The supporting evidence is on the next two pages: page 5 for how current podcasts are, and page 6 for what existing tools do.

## Page 5 · Written knowledge far outweighs current audio

**What it shows.** A bar chart: 271.3 million written works in OpenAlex against 123.2 million episodes on Apple Podcasts. Beside it, the fact that only 16% of Apple Podcasts shows published an episode in the last 90 days.

**Script.**
> Here is the size of the gap. OpenAlex indexes about 271 million written works, against about 123 million podcast episodes on Apple Podcasts, and the written works come with citation data. Podcasts also go quiet: only 16 percent of Apple Podcasts shows published an episode in the last 90 days. The verified knowledge is in text. The audio form is smaller, less current, and nothing guarantees its sources.

**Research behind it.**
- **Borrego & Urbano (2025), "OpenAlex: Features, advantages and limitations…".** The paper describes OpenAlex, an open index of scholarly outputs: articles, books, reports and their citation links. It gives the count of about 271 million works (November 2025), and discusses the database's coverage limits.
- **Gray (2026), *The Podcast Host*, podcast statistics 2026.** An industry compilation. It gives about 123.2 million episodes on Apple Podcasts, and 482,930 shows (about 16%) active in the last 90 days, as of June 2026.
- **Caveat to say if asked:** the two counts come from different sources and dates, and "works" is broader than articles. The ratio shows scale; it is not a precise comparison. The slide says so.

## Page 6 · What exists already, and what is missing

**What it shows.** A comparison table of one-pass tools against this project:
- **Sources:** a fixed set of documents, versus sources watched for changes.
- **Claims:** no claim-level check reported, versus each claim checked against its source.
- **Updates:** regenerate the whole episode, versus only the segments that changed.

**Script.**
> Tools that turn documents into two-host audio already exist: Google's NotebookLM Audio Overviews, and research systems such as PodAgent and MoonCast. They work in one pass from a fixed set of documents. None of them reports checking each claim against its source, or refreshing an episode when the sources change. Google itself says its hosts sometimes introduce inaccuracies. The building blocks, retrieval, neural speech and claim-level scoring, are mature. What is missing is a pipeline that watches its sources, checks its claims, and updates only what changed.

**Research behind it.**
- **B. Wang (2024), "NotebookLM now lets you listen to a conversation about your sources", Google.** This post launched Audio Overview: two AI hosts discuss the user's uploaded sources. Google called it experimental and said the hosts "sometimes introduce inaccuracies". It describes the output as a reflection of the uploaded sources, not an objective view of the topic. This is the baseline a reviewer will ask about.
- **Xiao et al. (2025), PodAgent (ACL Findings).** A multi-agent framework for podcast generation. Host, guest and writer agents draft the conversation, a voice pool matches voices to roles, and LLM-guided synthesis makes the speech expressive. It targets content and voice quality, not source verification or updates.
- **Ju et al. (2025), MoonCast (NeurIPS).** Zero-shot podcast generation. A script module turns source knowledge into spontaneous-sounding dialogue, and a long-context speech model voices several speakers. Again: one pass, no claim checks.
- **Lewis et al. (2020), retrieval-augmented generation (RAG).** This paper combined a language model with a retrieved document index, improving factual, knowledge-intensive tasks. It is the basis for grounding scripts in sources.
- **Gao et al. (2023), RAG survey.** It surveys RAG designs and their evaluation, and supports the choice of retrieval as the grounding method.
- **Ji et al. (2023), survey of hallucination in natural language generation.** It defines and classifies hallucination: fluent text that is unsupported by, or contradicts, its source. This is the core risk the fact-check gate addresses.
- **Kim et al. (2021), VITS, and C. Wang et al. (2023), VALL-E.** VITS is end-to-end neural text-to-speech with natural-sounding output. VALL-E, a codec language model, clones a voice from a few seconds of audio. Together they show that natural, distinct host voices are now practical, and that cloning needs safeguards (page 19).
- **Min et al. (2023), FActScore.** It splits long text into atomic facts and scores the share supported by a knowledge source. This is the model for checking every claim.

## Page 7 · Three questions

**What it shows.** The gap in one sentence, then three questions named Accuracy, Format and Trust.

**Script.**
> That gives three questions. Accuracy: does grounding the script in retrieved sources reduce unsupported claims, compared with writing without retrieval? Format: do listeners understand more from a two-host conversation than from a single narrator? Trust: how do listeners rate AI-made episodes against human-made ones, on naturalness, trust and usefulness?

**Research behind it.** The gap comes from page 6. Each question maps to one study on page 12, and the analysis plan on page 16 says how each answer is measured.

## Page 8 · Design science, with experiments

**What it shows.** The six design-science steps, with why design science and why mixed methods.

**Script.**
> The method is design science: I build an artifact, the pipeline, and evaluate it. I follow the six activities of Peffers and colleagues, from problem to communication, with Hevner's guidelines for building and evaluating an artifact. The evaluation is mixed methods: the numbers show how much accuracy or understanding changes, and listeners' comments help explain why.

**Research behind it.**
- **Peffers et al. (2007), design science research methodology.** It sets out six activities: identify the problem, define objectives, design and develop, demonstrate, evaluate, communicate. The slide's six boxes are these activities.
- **Hevner et al. (2004), "Design science in information systems research".** It gives guidelines for research that builds an artifact. The artifact must address a relevant problem, be rigorously evaluated, and add to the knowledge base. This is why building the pipeline counts as research, not only engineering.
- **Creswell & Creswell (2018), *Research design*.** The standard text on quantitative, qualitative and mixed-methods designs. It justifies combining scores (how much) with thematic analysis of comments (why).

## Page 9 · The instrument: an eight-stage pipeline

**What it shows.** Eight stages, left to right: ingest, index, retrieve and plan, script, fact-check, voice, assemble, publish. A loop runs from fact-check back to script: rewrite at most twice, then human review.

**Script.**
> This is the instrument. Eight stages: ingest the sources, index them, retrieve and plan the segments, write the script, fact-check it, voice it, assemble the audio, and publish it. The fact-check stage is a gate. Any claim without support goes back to the script stage. That happens at most twice; after that, the episode waits for a person to review it, so the loop always ends.

**Research behind it.** The stages put the building blocks from page 6 together: retrieval (Lewis et al., 2020), claim checking (Min et al., 2023) and neural speech. The two-rewrite limit is a design choice in the project's code, there so an ambiguous source cannot cause endless retries.

## Page 10 · Keeping episodes current

**What it shows.** Four steps: Watch, Detect, Rewrite, Blend. Below them, a seam check.

**Script.**
> Staying current works in four steps. The system watches feeds and pages on a schedule. A changed content hash marks a changed source. Only the segments that used that source are rewritten, and the rewrite sees the neighbouring lines as fixed context, so transitions still make sense. The new audio uses the same voices, joins with short crossfades, and the whole episode is normalized again. A seam check compares a refreshed episode with one regenerated from scratch.

**Research behind it.** This page answers a likely objection. In a two-host conversation, a rewritten segment spliced into old audio can sound stitched in: the transitions break and the voices shift. Four planned measures address this:
- **Context:** the rewrite gets the last lines of the segment before and the first lines of the segment after, so transitions and back-references still make sense.
- **Same voices:** each host keeps the same reference voice and random seed.
- **Joins:** boundary turns are crossfaded.
- **Loudness:** the whole episode is normalized again.

Loudness normalization follows ITU-R (2015), page 16.

## Page 11 · Planned tools

**What it shows.** One tool or set of tools per stage.

**Script.**
> These are the planned tools, so the twelve-week plan is concrete. Standard libraries for reading feeds, web pages and PDFs. Small open embeddings stored in PostgreSQL with pgvector. Gemini 3.8 Flash writes the script, and a second call judges each claim. Chatterbox voices the hosts, one consented voice each. Assembly and publishing use pydub, pyloudnorm and feedgen, and Celery runs each stage as its own job.

**Research behind it.** Each of these is supported in the project's codebase, so "doable in 12 weeks" rests on named components. The code's out-of-the-box defaults are offline stand-ins for testing: hashing embeddings, no model calls, and a placeholder voice. The study runs use the components below:
- **Ingest:** feedparser, trafilatura and PyMuPDF. Each item gets a SHA-256 content hash.
- **Index:** BAAI/bge-small-en-v1.5 embeddings, 384 dimensions, in PostgreSQL 16 with pgvector.
- **Script and fact-check:** Gemini 3.8 Flash. A claim with no citation fails automatically.
- **Voice:** Chatterbox (open source). One host is a clone of your own recorded voice, made with your written consent; the other is Chatterbox's built-in voice.
- **Assembly:** pydub and pyloudnorm. Publishing uses feedgen for the RSS feed.
- **Orchestration:** Celery on Redis, S3-compatible object storage and FastAPI.

Model versions are logged for reproducibility (page 17).

## Page 12 · Three studies

**What it shows.** One study per question, each with what it compares, what it measures and how it runs.

**Script.**
> Each question gets its own study. For accuracy, thirty grounded and thirty ungrounded scripts on the same topics, with two raters labelling every claim. For format, about thirty people per group hear the same content as two hosts or as one narrator, then take a quiz. For trust, listeners rate matched three-to-five-minute clips, AI-made and human-made, with music removed and loudness matched. That study is blind: listeners learn which clips were AI-made at the debriefing, so expectations do not drive the ratings.

**Research behind it.**
- **ITU-T (1996), Recommendation P.800.** It defines subjective listening tests, including absolute category rating on a five-point scale. The mean of those ratings is the mean opinion score (MOS). The trust study's 1-to-5 ratings follow this format.
- **Why matched, blind clips:** full human podcasts carry studio sound design, music and years of host rapport. Comparing them with AI episodes would mix up the script, the voices and the production value. Short matched excerpts with music removed isolate the script and the voices. Blinding stops anti-AI expectations from lowering trust ratings. The ethics of this partial disclosure are covered on page 19.

## Page 13 · Sampling and data collection

**What it shows.** 30 scripts per condition, 30 participants per group, and 4 instruments.

**Script.**
> In numbers: thirty scripts per condition, about thirty participants per group, and four instruments: a claim audit sheet, a listening survey, a comprehension quiz, and the pipeline's own logs. The same topics are used in every condition so comparisons are fair. Participants are recruited by convenience sampling, which I list as a limitation.

**Research behind it.** The sizes follow the study design on page 12. Convenience sampling and about 30 per group are limitations, named on page 18. The listening survey uses the five-point format of ITU-T (1996).

## Page 14 · Ontario law that shapes the study

**What it shows.** Two columns, the Human Rights Code and the AODA, with four points each.

**Script.**
> Because the project is about access, two Ontario laws shape the method. The Human Rights Code protects against discrimination, including on the ground of disability, and it takes priority over other Ontario laws. It requires accommodation for each person's needs, up to undue hardship, and complaints go to the Human Rights Tribunal of Ontario. The AODA works ahead of complaints: it sets enforceable standards for customer service, information and communications, employment, transportation and public spaces. Meeting the AODA does not replace duties under the Code, so the team is trained on both.

**Research behind it.**
- **Human Rights Code, R.S.O. 1990, c. H.19.** It guarantees equal treatment in services, goods, facilities, employment and other areas, without discrimination, including because of disability. It takes priority over other Ontario laws unless a law expressly says otherwise. Accommodation is individual, up to undue hardship. The Ontario Human Rights Commission notes that undue hardship is judged only on cost, outside funding, and health and safety, with objective evidence. Complaints are heard by the Human Rights Tribunal of Ontario. For the study, recruitment and participation must not discriminate, and anyone who asks gets an accommodation fitted to their needs.
- **Accessibility for Ontarians with Disabilities Act, 2005, S.O. 2005, c. 11.**
  - **Purpose (s. 1):** to develop, implement and enforce accessibility standards for goods, services, facilities, accommodation, employment, buildings and premises.
  - **Other duties stay (s. 3):** nothing in the Act or its regulations "diminishes in any way" obligations under other laws. That is why meeting the AODA does not satisfy the Code on its own.
- **Integrated Accessibility Standards, O. Reg. 191/11.** The regulation that holds the AODA's standards: information and communications, employment, transportation, design of public spaces, and customer service. It is the source of the training duty and the web accessibility rule used on page 15.

## Page 15 · How the study applies them

**What it shows.** Five rows: recruitment, accommodation, materials, team and evaluation.

**Script.**
> Here is what that means for the study. Recruitment: no one is turned away because of a disability, and where a task needs hearing, a transcript-based version is offered. Accommodation: on request, for each person, such as screen-reader-ready surveys, extra time or breaks. Materials: the web player, transcripts and surveys meet WCAG 2.0 Level AA, the web standard under the AODA's information and communications rules. Team: AODA and Code training before recruiting. And the evaluation adds an accessibility check of what the pipeline publishes.

**Research behind it.**
- **O. Reg. 191/11, s. 7 (training).** Organizations must train staff and others who act for them on the accessibility standards and on the Human Rights Code as it relates to persons with disabilities. That is the "team" row.
- **O. Reg. 191/11, s. 12 (accessible formats and communication supports).** These must be provided on request. That is the "accommodation" row.
- **O. Reg. 191/11, s. 14 (websites and web content).** Public sector and large organizations' websites must meet WCAG 2.0, now at Level AA. Live captions and pre-recorded audio description are excepted. Lakehead is a public sector organization, so study materials hosted for it should meet this. That is the "materials" row.
- **World Wide Web Consortium (2008), WCAG 2.0.** The web accessibility standard: content must be perceivable, operable, understandable and robust, at conformance levels A, AA and AAA. Success criterion 1.2.1 requires a text alternative, such as a transcript, for prerecorded audio. That is why every episode ships with a transcript.
- **Human Rights Code.** Individual accommodation up to undue hardship, which is the "recruitment" and "accommodation" rows. A blanket rule excluding people with hearing loss could be discriminatory, so listening tasks also have a transcript version.

## Page 16 · Analysis plan

**What it shows.** Each measure, its analysis method and the source that justifies it.

**Script.**
> The analysis pairs each measure with an established method. Accuracy is the share of claims supported by a cited source, as in FActScore. Rater agreement is Cohen's kappa, read with Landis and Koch's bands. Group differences use t-tests, or Mann-Whitney U when data are not normal, with effect sizes. Listener comments get thematic analysis. Intelligibility is the word error rate of a Whisper transcript. Audio is checked for loudness near minus 16 LUFS, and the published pages are checked against WCAG.

**Research behind it.**
- **Min et al. (2023), FActScore.** Factual precision is the share of atomic claims supported by a source. It is the main accuracy measure.
- **Cohen (1960).** The kappa coefficient: agreement between two raters on categories, corrected for chance. It shows whether the claim labels can be trusted.
- **Landis & Koch (1977).** Widely used bands for reading kappa: slight (0 to .20), fair (.21 to .40), moderate (.41 to .60), substantial (.61 to .80) and almost perfect (.81 to 1).
- **Mann & Whitney (1947).** The U test compares two independent groups without assuming normal data. It is the fallback to the t-test for quiz scores and ratings.
- **Braun & Clarke (2006).** Six-phase thematic analysis: familiarize, code, search for themes, review, define and name, write up. It is used for the open listener comments.
- **Radford et al. (2023), Whisper.** Speech recognition trained on 680,000 hours of weakly supervised audio, robust across accents and noise. Transcribing an episode and comparing it with its script gives a word error rate, a measure of intelligibility.
- **ITU-R (2015), BS.1770-4.** The standard way to measure loudness (LUFS) and true peak. The target is about −16 LUFS, a common level for podcasts.
- **W3C (2008), WCAG 2.0.** The checklist for the accessibility check of the player, show notes and transcripts.

## Page 17 · Validity and reliability

**What it shows.** Validity: internal, construct, external. Reliability: inter-rater, repeatable, replicable.

**Script.**
> Validity: the conditions use the same topics, prompts and model, and the trust study is blind and in random order. The claim audit and the five-point ratings measure what the questions ask about. Findings apply to the topics and voices tested, and I say so. Reliability: two raters work independently and kappa is reported; prompts, model versions and seeds are logged for every episode; and the methods are described so someone else can rerun them.

**Research behind it.** These follow Creswell & Creswell (2018) on validity and reliability, using kappa from Cohen (1960) for inter-rater reliability. Blinding and matched clips (page 12) are the main defence of internal validity in the trust study.

## Page 18 · Limitations

**What it shows.** Six limits: small samples, model drift, narrow scope, imperfect checks, source bias and a short timeline.

**Script.**
> The limits: about thirty people per group limits statistical power, and convenience sampling limits generalization. Hosted models change over time, so versions are logged. The study covers a limited set of topics and one language. Speech recognition and model-based checks make errors, so manual audits anchor the results. The choice of sources shapes what episodes say. And twelve weeks, with ethics review inside them, limits how much can be built and tested.

**Research behind it.** Naming limits is part of a rigorous method (Creswell & Creswell, 2018). Source bias echoes Bender et al. (2021): what a language system says reflects what it was given.

## Page 19 · Ethics

**What it shows.** Two columns. Participants, under TCPS 2: approval, consent, a blind study with debriefing, and anonymized data. Synthetic audio: the AI label, consented voices, and licensed sources.

**Script.**
> Ethics follows TCPS 2. At Lakehead, graduate course-based research goes to the full Research Ethics Board, so the application goes in at the end of week 2 and no participant study starts before approval. Participants give informed consent and can withdraw. Because the trust study is blind, the AI origin is explained at the debriefing, which the board must approve. Data is anonymized and stored securely. For the audio itself: every published episode is labelled AI-generated, voices are cloned only with written consent, and only licensed or open sources are used.

**Research behind it.**
- **CIHR, NSERC & SSHRC (2022), TCPS 2.** Canada's research ethics policy. Its core principles are respect for persons, concern for welfare, and justice. It requires ethics board review before research with people begins. It allows partial disclosure only when the board approves it and participants are debriefed (Article 3.7A). That covers the blind trust study.
- **Lakehead's REB procedure for course-based research (revised October 3, 2025).** Not on the slides; it is the source of the timing. The full REB reviews graduate-level teaching protocols. Data that later counts toward a Master's degree cannot use a teaching protocol and needs its own REB approval. Review takes weeks, which is why approval is planned for week 7, not week 2.
- **C. Wang et al. (2023), VALL-E.** It shows convincing voice cloning from a few seconds of speech, and its authors warn about spoofing and impersonation. That is why voices are cloned only with written consent: here, your own voice.
- **Bender et al. (2021), "On the dangers of stochastic parrots".** Large language models can produce fluent text that seems authoritative while reflecting the biases and gaps of their data. This supports the AI-generated label and the use of licensed, vetted sources only.

## Page 20 · Twelve weeks, three checkpoints

**What it shows.** A Gantt chart of five phases, with checkpoints at the ends of weeks 2, 7 and 10.

**Script.**
> The plan runs twelve weeks in five phases, with three checkpoints. By the end of week 2, the questions are fixed and the ethics application is in. By the end of week 7, the pipeline makes a full episode end to end, and ethics approval is in hand; that checkpoint matters most, because without both there is nothing to evaluate. By the end of week 10, the study data is collected and cleaned. If approval is late, the accuracy study, which needs no participants, goes ahead, and the two listener studies shrink to a pilot.

**Research behind it.** The timing follows from the ethics process on page 19: the application is submitted early, and the build runs while it is reviewed. The fallback plan works because the accuracy study needs no participants.

## Page 21 · Expected contributions

**What it shows.** Importance, novelty and implication, then the deliverables.

**Script.**
> What this delivers. Importance: evidence on whether AI-made podcasts can be accurate enough to trust, which any real use needs first. Novelty: grounding, claim checking and refresh tested together in one working pipeline. Implication: guidance for creators and organizations on when AI-made audio is appropriate, what safeguards it needs, and how to make it accessible. The deliverables are the pipeline, the evaluation data and a final report.

**Research behind it.** The novelty claim rests on page 6: none of the published one-pass systems (NotebookLM, PodAgent, MoonCast) reports claim-level checking or segment-level refresh. The accessibility point rests on pages 14 and 15.

## Page 22 · Thank you

**What it shows.** A three-line summary (problem, approach, evidence) and an invitation to ask questions.

**Script.**
> To sum up: podcasts are slow to make, go stale, and rarely cite sources. I propose a grounded, refreshable pipeline with a fact-check gate, built and evaluated with design science, and three studies on accuracy, format and trust. Thank you. I welcome your questions and feedback.

## Pages 23 to 25 · References

**What they show.** All 30 references in APA 7 style, alphabetical. Every one is cited on a content slide.

**Script.**
> These are the thirty references, in APA style. I will leave this up during questions.

---

## Likely questions

| Question | Short answer |
|---|---|
| How is this different from NotebookLM? | NotebookLM makes audio once from fixed documents and reports no claim-level check. This pipeline watches its sources, checks every claim against the passage it cites, and regenerates only the segments whose sources changed. |
| What if the fact-check keeps failing? | At most two rewrites. After that, the episode is held for human review, so it never loops forever. |
| Won't refreshed segments sound spliced in? | The rewrite gets the neighbouring lines as fixed context. The voices and seeds stay the same, the joins are crossfaded, and loudness is normalized again. A seam check tests this against a full regeneration. |
| Isn't the trust study biased against AI? | It is blind, with matched short clips and the music removed, so ratings reflect the script and voices, not studio production. The AI origin is disclosed at debriefing. |
| Is ethics approval realistic in twelve weeks? | The application goes in at week 2, and approval is needed by week 7. If it is late, the accuracy study, which has no participants, still runs, and the listener studies become a pilot. |
| Why the Human Rights Code and the AODA? | The project is about access for people with disabilities. The Code governs how participants are treated and accommodated. The AODA's standards govern the materials, such as WCAG 2.0 AA, and staff training. |

## Key terms

| Term | Meaning |
|---|---|
| Dynamic content | Episode material assembled at generation time from current sources, not from a fixed script. |
| Grounding | Tying each claim in a script to a retrieved source passage. |
| Hallucination | Fluent generated text that is unsupported by, or conflicts with, the source. |
| Multi-host dialogue | A scripted conversation between two or more synthetic hosts instead of one narrator. |
| Mean opinion score (MOS) | The average listener rating on a five-point scale (ITU-T, 1996). |
| Undue hardship | The limit of the duty to accommodate under the Human Rights Code, judged on cost, outside funding, and health and safety. |
| WCAG 2.0 AA | The web accessibility level Ontario's Integrated Accessibility Standards require of public sector websites. |

## References

1. *Accessibility for Ontarians with Disabilities Act, 2005*, S.O. 2005, c. 11. https://www.ontario.ca/laws/statute/05a11
2. Bender, E. M., Gebru, T., McMillan-Major, A., & Shmitchell, S. (2021). On the dangers of stochastic parrots: Can language models be too big? *Proceedings of the 2021 ACM Conference on Fairness, Accountability, and Transparency*, 610-623.
3. Borrego, A., & Urbano, C. (2025). OpenAlex: Features, advantages and limitations of an open database for retrieving and analysing scholarly outputs. *arXiv*:2512.16434.
4. Braun, V., & Clarke, V. (2006). Using thematic analysis in psychology. *Qualitative Research in Psychology*, 3(2), 77-101.
5. Canadian Institutes of Health Research, Natural Sciences and Engineering Research Council of Canada, & Social Sciences and Humanities Research Council. (2022). *Tri-Council policy statement: Ethical conduct for research involving humans (TCPS 2, 2022)*. Government of Canada.
6. Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement*, 20(1), 37-46.
7. Creswell, J. W., & Creswell, J. D. (2018). *Research design: Qualitative, quantitative, and mixed methods approaches* (5th ed.). SAGE.
8. Gao, Y., et al. (2023). Retrieval-augmented generation for large language models: A survey. *arXiv*:2312.10997.
9. Gray, C. (2026, June 22). Podcast statistics & industry trends 2026: Listens, gear, & more. *The Podcast Host*. https://www.thepodcasthost.com/listening/podcast-industry-stats/
10. Hevner, A. R., March, S. T., Park, J., & Ram, S. (2004). Design science in information systems research. *MIS Quarterly*, 28(1), 75-105.
11. *Human Rights Code*, R.S.O. 1990, c. H.19. https://www.ontario.ca/laws/statute/90h19
12. *Integrated Accessibility Standards*, O. Reg. 191/11. https://www.ontario.ca/laws/regulation/110191
13. ITU-R. (2015). *Recommendation ITU-R BS.1770-4: Algorithms to measure audio programme loudness and true-peak audio level*. International Telecommunication Union.
14. ITU-T. (1996). *Recommendation ITU-T P.800: Methods for subjective determination of transmission quality*. International Telecommunication Union.
15. Ji, Z., et al. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys*, 55(12), Article 248.
16. Ju, Z., et al. (2025). MoonCast: High-quality zero-shot podcast generation. *Advances in Neural Information Processing Systems*, 38.
17. Kim, J., Kong, J., & Son, J. (2021). Conditional variational autoencoder with adversarial learning for end-to-end text-to-speech. *Proceedings of the 38th International Conference on Machine Learning*, PMLR 139, 5530-5540.
18. Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics*, 33(1), 159-174.
19. Lewis, P., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems*, 33, 9459-9474.
20. Mann, H. B., & Whitney, D. R. (1947). On a test of whether one of two random variables is stochastically larger than the other. *The Annals of Mathematical Statistics*, 18(1), 50-60.
21. Min, S., et al. (2023). FActScore: Fine-grained atomic evaluation of factual precision in long form text generation. *Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing*, 12076-12100.
22. Peffers, K., Tuunanen, T., Rothenberger, M. A., & Chatterjee, S. (2007). A design science research methodology for information systems research. *Journal of Management Information Systems*, 24(3), 45-77.
23. Radford, A., et al. (2023). Robust speech recognition via large-scale weak supervision. *Proceedings of the 40th International Conference on Machine Learning*, PMLR 202, 28492-28518.
24. Statistics Canada. (2023, December 1). *New data on disability in Canada, 2022* (Catalogue no. 11-627-M). https://www150.statcan.gc.ca/pub/11-627-m/11-627-m2023063-eng.htm
25. Wang, B. (2024, September 11). NotebookLM now lets you listen to a conversation about your sources. *The Keyword*. Google. https://blog.google/technology/ai/notebooklm-audio-overviews/
26. Wang, C., et al. (2023). Neural codec language models are zero-shot text to speech synthesizers. *arXiv*:2301.02111.
27. World Health Organization. (2019). *World report on vision*. World Health Organization.
28. World Health Organization. (2022). *Global report on health equity for persons with disabilities*. World Health Organization.
29. World Wide Web Consortium. (2008). *Web Content Accessibility Guidelines (WCAG) 2.0*. W3C Recommendation. https://www.w3.org/TR/WCAG20/
30. Xiao, Y., He, L., Guo, H., Xie, F.-L., & Lee, T. (2025). PodAgent: A comprehensive framework for podcast generation. *Findings of the Association for Computational Linguistics: ACL 2025*, 23923-23937.

The Lakehead REB procedure cited on page 19 is background for the timeline and is not in the 30: *Teaching Protocols involving human participants for course-based research*, Research Ethics Board Standard Operating Procedure, Lakehead University, revised October 3, 2025.
