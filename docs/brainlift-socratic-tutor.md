# BrainLift: Why LLM Tutors Give Away the Answer

## Owners

- Aadi Takle

## Purpose

### Purpose

This BrainLift explores why LLM-based tutors default to giving away answers or key steps when explicitly asked not to, in order to ground the design of a Socratic Tutor Adequacy Judge & Rewriter (a small fine-tuned model that judges and rewrites inadequate tutor messages, per `docs/behavior_spec.md`) in real learning-science mechanisms and empirical evidence rather than intuition about what "good tutoring" looks like.

### In Scope

- The learning-science mechanisms governing when direct answers/guidance help vs. hurt a learner (expertise reversal, effect-size measurement in tutoring research).
- Empirical evidence on whether and how LLM tutors leak answers under pressure, and what defenses actually work.
- The plausible training-level mechanism (RLHF) behind models' default-helpfulness behavior, and the honest limits of that explanation.
- Real production precedent (Khan Academy/Khanmigo) for this exact guardrail-design problem, including where that precedent's success claims don't hold up.

### Out of Scope

- Using AI to generate the insight or stance itself (DOK 3/DOK 4) — that must come from my own synthesis.
- Domain-general tutoring behavior outside math (the project's v1 scope is math-only; generality is a stretch goal, not a claim this BrainLift needs to support).
- The actual data-gen/eval pipeline implementation — that's separate downstream work, not BrainLift content.

---

## DOK 4: Spiky Points of View (SPOVs)

- **Spiky POV 1:** State-conditioned tutoring judgment must be built as a separate, purpose-trained layer now, not deferred to future frontier-model scale. Waiting for general-purpose models to eventually get better at tutoring calibration as a side effect of scaling is a structurally wrong bet, not just a slower path to the same destination.
   - **Elaboration:** The right amount of tutoring help depends on the student's current state, not a fixed rule. Four separate sources say this independently and don't cite each other: Vygotsky's Zone of Proximal Development (1978), Kalyuga et al.'s expertise-reversal effect (2003), Khan Academy's own guardrail redesign, and an unrelated K-12 writing-support deployment (Insight 4). The only fix in this space that has actually worked was architectural, not a better model. A reasoning-layer defense against answer-leakage cut leakage by 10x, from 46% down to 2-4%, and held up across different domains. Khan Academy's fix for its own accuracy problems was just switching models, from GPT-4 Turbo to GPT-4o. That leaves the problem just as unstable as whichever model happens to be deployed, since accuracy still swings from 31.7% to 68.5% depending on the model (Insight 1). Together, this suggests tutoring calibration will not simply appear on its own as models get bigger or better at other things. The strongest counterargument is that scale has already improved skills like reasoning and instruction-following, so it might improve this too. That's fair, but nothing here backs it up: leak-robustness did not even track model size in the data we have. Betting on future frontier models to fix this by themselves has no real support. The one thing that has actually worked is a dedicated, state-aware judgment layer, which is exactly what this project builds.

---

## Experts

- **Expert 1 — James A. Kulik**
   - **Who:** Research scientist, University of Michigan Center for Research on Learning and Teaching.
   - **Focus:** Meta-analysis of tutoring and computer-assisted-instruction effectiveness across decades of controlled studies; specializes in how measurement choices change effect-size conclusions.
   - **Why Follow:** Co-author of the 1982 meta-analysis that puts real-world tutoring gains at a fraction of Bloom's famous "two-sigma" number, and shows the number itself swings 3x depending on test breadth — directly informs how skeptical to be about any single effect-size claim, including ones this project might generate from its own eval harness.
   - **Where:** [Cohen, Kulik & Kulik (1982), "Educational Outcomes of Tutoring: A Meta-analysis of Findings"](https://journals.sagepub.com/doi/10.3102/00028312019002237)

- **Expert 2 — Slava Kalyuga**
   - **Who:** Professor of Educational Psychology, UNSW Sydney.
   - **Focus:** Cognitive load theory; the expertise reversal effect — how instructional guidance that helps novices measurably hurts more advanced learners.
   - **Why Follow:** Gives the precise mechanistic reason a static "always scaffold, never give the answer" rule is wrong, which directly informs the project's `mismatched_calibration` taxonomy category.
   - **Where:** [Google Scholar profile](https://scholar.google.com/citations?user=v3OpQcYAAAAJ&hl=en)

- **Expert 3 — Sal Khan**
   - **Who:** Founder and CEO, Khan Academy; creator of Khanmigo.
   - **Focus:** Public-facing philosophy and product decisions behind AI tutoring guardrails, iterated through real classroom pilots.
   - **Why Follow:** Khan Academy is the closest existing production analog to this project's goal, and their guardrail evolution (blanket "never give the answer" → state-dependent rule) is real-world validation of Kalyuga's mechanism. Equally important to follow honestly: Khan's own adoption predictions for Khanmigo have missed badly, which is a useful check against over-claiming that "getting the pedagogy right" guarantees product success.
   - **Where:** [X profile](https://x.com/salkhanacademy) · [Khan Academy Blog](https://blog.khanacademy.org/)

- **Expert 4 — Tanja Käser**
   - **Who:** Assistant Professor, EPFL School of Computer and Communication Sciences; head of the ML4ED lab.
   - **Focus:** Machine learning and data mining applied to education; modeling human learning behavior.
   - **Why Follow:** Senior author of the most directly relevant empirical paper found for this project — adversarial robustness testing of LLM tutors against students actively trying to extract answers. Her lab is producing the benchmark this project's own adversarial rewrite-safety eval criterion should eventually be checked against.
   - **Where:** [EPFL faculty page](https://people.epfl.ch/tanja.kaeser/?lang=en)

- **Expert 5 — Ariel D. Procaccia**
   - **Who:** Alfred and Rebecca Lin Professor of Computer Science, Harvard.
   - **Focus:** Computational social choice, mechanism design, and (in the source below) formal analysis of alignment training's side effects.
   - **Why Follow:** Co-author of a formal, provable mechanism by which RLHF amplifies sycophancy — the closest thing to a mechanistic "why do models default to the gratifying-but-wrong response" theory this project's core premise leans on. Important to follow critically, not just cite: his paper's own scope (belief-affirmation) is narrower than what this project would need it to say (caving under repeated pressure for an answer).
   - **Where:** [Homepage](https://procaccia.info/) · [Google Scholar](https://scholar.google.com/citations?user=8ZpV-lkAAAAJ&hl=en)

- **Expert 6 — Robert A. Bjork**
   - **Who:** Distinguished Research Professor of Psychology, UCLA.
   - **Focus:** Human learning and memory; originator (with Elizabeth Ligon Bjork) of "desirable difficulty" — the theory that conditions which slow learning in the moment (retrieval, spacing, generation) produce stronger durable retention than conditions that feel easy.
   - **Why Follow:** Gives the mechanistic reason withholding an answer is itself the pedagogical intervention, not just a rule to enforce — directly explains why a tutor that always makes things easy is failing the student even when it feels helpful in the moment.
   - **Where:** [Bjork Learning and Forgetting Lab, UCLA](https://bjorklab.psych.ucla.edu/)

- **Expert 7 — John Hattie**
   - **Who:** Laureate Professor, Melbourne Graduate School of Education, University of Melbourne.
   - **Focus:** Meta-analyses of what most influences student achievement (*Visible Learning*); with Helen Timperley, a foundational model of feedback's role in learning.
   - **Why Follow:** His 2007 review (with Timperley) frames feedback as tutoring's central affordance over solo study — but shows it is empirically double-edged, which turns out to connect directly to why sycophantic, validation-first LLM behavior (Expert 5's territory) is a specific, predictable way for a tutor to fail.
   - **Where:** [University of Melbourne faculty profile](https://findanexpert.unimelb.edu.au/profile/428067-john-hattie)

- **Expert 8 — Michelene T. H. Chi**
   - **Who:** Regents' Professor, Arizona State University (Mary Lou Fulton Teachers College); Director, ICAP Center for Teaching and Learning; 2023 Yidan Laureate for Education Research.
   - **Focus:** How students learn and engage with instruction (the ICAP framework); specifically, tutor learning — why explaining to help someone else sometimes builds the explainer's own understanding, and sometimes doesn't.
   - **Why Follow:** Her tutor-learning work (Roscoe & Chi, 2007) draws a distinction — reflective "knowledge-building" vs. shallow "knowledge-telling" — that maps suggestively onto whether an AI-generated Socratic hint is actually pedagogically generative or just a more polite-sounding non-answer. Worth following critically: her research is about a human tutor's own learning, which is a different direction than this project's judge/rewriter setup, and that difference shouldn't be blurred.
   - **Where:** [ASU faculty profile](https://search.asu.edu/profile/1274385)

---

## DOK 3: Insights

- **Insight 1:** Fixes for LLM tutoring failures are durable only when they're architectural, not when they rely on picking a better underlying model. The reasoning-layer defense against adversarial answer-leakage cut leakage by an order of magnitude (46%→2-4%) and held across domains (Category 3, Subcategory 3.1). By contrast, Khan Academy's fix for evaluation-accuracy problems was to swap the underlying frontier model (GPT-4 Turbo → GPT-4o, Category 6.1, Source 2) rather than build a comparable dedicated layer — and CoMTA's own numbers (Category 6.2, Source 2) show that failure mode is exactly as volatile as whichever model happens to be deployed (31.7%–68.5% swing by model family). One failure mode got a fix that held; the other got a fix that's only as good as this month's model choice.
- **Insight 2:** Khanmigo's designed fallback behavior — checking your own work instead of getting the answer outright (Category 2, Subcategory 2.2, Source 1) — sits on the exact same weakness the guardrail was built to route around. Students converged on using the tool this way in practice (Category 6.3, Source 4, Michigan Virtual pilot), but the model's own judgment of whether an answer is actually correct is itself unreliable (Category 6.2, Source 2, CoMTA) — less reliable at catching wrong answers than confirming right ones. The safety net has a hole in the same place as the thing it was supposed to catch.
- **Insight 3:** AI is moving too fast for detailed reports and analyses on its performance to be available before newer models appear to replace them. Khan Academy migrated its underlying model at least once with a stated performance rationale (Category 6.1, Source 2); CoMTA's accuracy numbers are tied to specific, soon-superseded model versions (Category 6.2, Source 2); and rigorous evidence takes years to mature — Nickow, Oreopoulos & Quan's own effect-size estimate took four years to revise (Category 1, Subcategory 1.1, Source 2), and the one independent causal RCT of Khanmigo itself is still pending with no results (Category 6.3, Source 5). The pace of model churn plausibly outruns the multi-year cycle rigorous evaluation requires.
- **Insight 4:** Learning science theory and real classroom feedback land on the same conclusion on tutoring: the right amount of help depends on the learner's current state. Two theoretical traditions roughly 75 years apart converge on this independently. Vygotsky's ZPD (Category 4, Subcategory 4.1, Source 1) defines support as calibrated to current developmental level and meant to fade as competence grows, while Kalyuga et al.'s expertise-reversal effect (Category 2, Subcategory 2.1, Source 1) shows the identical instructional support helps novices but actively hurts advanced learners. The correct amount of help flips sign depending on state, it isn't fixed. Two unrelated real-world deployments land on the same structural claim independently of the theory and of each other: Khan Academy's pilot-district teachers drove Khanmigo's guardrail from a blanket "never give the answer" rule to a state-conditioned one (Category 2, Subcategory 2.2, Source 1), and a completely different system in a different domain found the same thing. An LLM writing scaffolding for K-12 EFL students (Category 4, Subcategory 4.1, Source 2) that doesn't recalibrate to student proficiency causes harm (demotivation, dependency) rather than help. Four independent sources, two methods, decades and domains apart, none citing each other, converging on the same conclusion.

**Provocation questions (AI-provided scaffolding, not insights — starting points only):**

1. The Kulik effect-size fact and the arXiv paper's own leak-rate percentages are both "how you measure it changes the number" situations. What does that combination imply about how *this project's own eval harness* should be designed?
2. Kalyuga (lab cognitive-load theory) and Khan Academy's pilot-district feedback (production classroom reality) independently converged on "the right amount of help depends on the learner's current state" — from completely different methods, decades apart. What does that convergence suggest about whether a single static taxonomy can ever be sufficient, versus needing to be explicitly state-conditioned?
3. Khan Academy got the specific behavioral guardrail mechanism right (per Kalyuga's own theory) but Khanmigo still underperformed on adoption. What does that combination imply about what this project should — and should not — claim success will look like, even if the adequacy judge/rewriter works exactly as designed?
4. The arXiv paper's fix that actually worked empirically was architectural (add a reasoning/judgment layer), not a retrained reward model — while Procaccia et al.'s fix is a reward-model-level correction, still theoretical. What does it suggest about which layer of the stack this class of problem should be solved at?
5. Bjork (1994) describes trainers drifting, over time, toward "manipulations that increase the rate of correct responding — that make the trainee's life easier," even though that's bad for learning. The CHI '26 scaffolding-breaks study and the PNAS Nexus depth-of-learning study both independently show LLMs doing exactly this (dependency in weaker students; shallower recall) without any RLHF-specific mechanism being invoked at all. What does it imply if this "drift toward easy" shows up even in non-RLHF-specific contexts (a human trainer in 1994, a writing-scaffold LLM, a search-vs-chat comparison) — is this fixable by better training objectives, or is it a more general property of any system optimized on short-term interaction signals?
6. The protégé-effect and knowledge-telling/knowledge-building literature (Category 5) is about a *human* benefiting from teaching an agent or peer. This project's actual pipeline runs the other direction: a small model is trained to judge/rewrite a *human* tutor's messages — the model isn't the one who's supposed to learn from the exchange. Is there anything real in the knowledge-building/knowledge-telling distinction that transfers to training a judge/rewriter, or is drawing that parallel actually a category error worth naming and rejecting rather than forcing?

---

## DOK 2: Knowledge Tree

- **Category 1: How Big Is Tutoring's Advantage, Really?**
   - **Subcategory 1.1: Effect-size measurement in tutoring research**
      - **Source 1: von Hippel, P., "Two-Sigma Tutoring: Separating Science Fiction from Science Fact" (*Education Next*, Spring 2024)**
         - **DOK 1 - Facts:**
            - Source states: "Tutors, Bloom claimed, could raise student achievement by two full standard deviations—or, in statistical parlance, two 'sigmas.'"
            - Source states Bloom's claim rested on two PhD dissertations: "Bloom was placing his faith in the dissertation studies of two of his PhD students, Joanne Anania and Arthur J. Burke. Both Anania and Burke reported two-sigma effects when comparing tutoring to whole-group classroom instruction."
            - Source states Cohen, Kulik & Kulik's 1982 meta-analysis "reported that the average effect of tutoring was about 0.33 standard deviations, or 13 percentile points."
            - Source states the same meta-analysis found tutoring effects "averaged 0.84 standard deviations when measured on narrow tests...versus just 0.27 standard deviations when measured on broader standardized tests."
            - Source states: "The two-sigma effects obtained in the 1980s by Anania and Burke were real and remarkable, but they were obtained on a narrow, specialized test, and they weren't obtained by tutoring alone."
            - Source states the underlying Anania/Burke dissertations tested tutoring simultaneously with "overlapping interventions, such as training and coaching of teachers, extra learning time, and cycles of frequent testing and feedback" — not tutoring in isolation. Von Hippel "estimates that testing and feedback (rather than tutoring) accounted for about half of the observed gains."
            - Source states the 2.0σ figure "was never replicated" in the decades since.
         - **DOK 2 - Summary:**
            - Bloom's famous "two-sigma" tutoring claim rests on just two dissertations measured on a narrow test, and was never replicated.
            - The field's own meta-analysis puts realistic tutoring gains at roughly a third of that size overall, and shows the number itself swings 3x (0.84σ vs. 0.27σ) depending on whether the test is narrow or broad.
            - Beyond the sample and test-breadth problems, roughly half of even the original two-sigma result is attributed to testing/feedback confounds, not tutoring itself — meaning the number is compromised on at least three independent grounds (thin sample, narrow test, internal confound), not just one.
         - **Link to source:** https://www.educationnext.org/two-sigma-tutoring-separating-science-fiction-from-science-fact/
      - **Source 2: Nickow, Oreopoulos & Quan, "The Impressive Effects of Tutoring on PreK-12 Learning" (NBER Working Paper 27476, 2020; published as "The Promise of Tutoring for PreK–12 Learning," *American Educational Research Journal*, 2024)**
         - **DOK 1 - Facts:**
            - Source states the 2020 working paper's systematic review of 96 RCTs reports an overall pooled effect size of 0.37 SD.
            - Source states the 2024 published version of the same review reports a revised overall pooled effect size of 0.288 SD (SE = 0.029, p < .001) — a downward revision within the same research team's own work over four years, not a different team disagreeing with them.
         - **DOK 2 - Summary:**
            - The single most-cited recent review of human tutoring RCTs revised its own headline number downward by about a fifth on further scrutiny (0.37 → 0.288 SD) — a real, documented shrinkage, but one that happened *within one team's revision process*, not across "old vs. new research" broadly.
         - **Link to source:** https://www.nber.org/papers/w27476 · https://journals.sagepub.com/doi/10.3102/00028312231208687
      - **Source 3: Aggregated secondary summary of independent tutoring meta-analyses (Dietrichson et al. 2017; Fryer 2017; Inns et al. 2019; Pellegrini et al. 2021) — verification note: not independently fetched/verified per paper, only as a bundled secondary characterization**
         - **DOK 1 - Facts:**
            - Secondary source states meta-analyses by these four independent teams "have all found large effects of tutoring on test-based measures of achievement in the range of 0.3 to 0.4 SD," consistent with both Cohen, Kulik & Kulik (1982, Source 1) and Nickow et al. (2020/2024, Source 2).
         - **DOK 2 - Summary:**
            - Four more independent teams, spanning 2017–2021, converge on the same modest range Cohen, Kulik & Kulik found in 1982 — meaning the "modest effect" finding isn't one team's outlier either; it's the actual consensus, with Bloom (1984) as the outlier against it, not the reverse.
         - **Link to source:** not independently verified per paper this pass — flagged for follow-up if these individual studies become load-bearing
   - **Subcategory 1.2: A different intervention category — computer-based Intelligent Tutoring Systems**
      - **Source 1: Kulik & Fletcher, "Effectiveness of Intelligent Tutoring Systems: A Meta-Analytic Review" (*Review of Educational Research*, 86(1), 42–78, 2016)**
         - **DOK 1 - Facts:**
            - Source states this meta-analysis of 50 controlled evaluations of intelligent computer tutoring systems found "the median effect of intelligent tutoring in the 50 evaluations was to raise test scores 0.66 standard deviations over conventional levels, or from the 50th to the 75th percentile."
            - Source states "the amount of improvement found in an evaluation depended to a great extent on whether improvement was measured on locally developed or standardized tests" — the same narrow-vs-broad-test sensitivity found in Cohen, Kulik & Kulik's human-tutoring meta-analysis (Subcategory 1.1, Source 1).
         - **DOK 2 - Summary:**
            - This is a higher number than the human-tutoring literature (0.66 SD vs. 0.3–0.4 SD), but it measures a different intervention entirely — software-based ITS, not a human tutor — so it should not be read as evidence that "tutoring's effect is actually bigger" or as contradicting the human-tutoring consensus in Subcategory 1.1. The same test-breadth sensitivity shows up here independently, though, which strengthens that specific pattern as general rather than specific to one paper.
         - **Link to source:** https://eric.ed.gov/?id=EJ1090502
   - **Subcategory 1.3: Publication bias as a general caution on any single meta-analytic number**
      - **Source 1: "Neglect of Publication Bias Compromises Meta-Analyses of Educational Research" (*PLOS ONE*, 2021)**
         - **DOK 1 - Facts:**
            - Source states field-wide evidence synthesis across 800 meta-analyses in education averages d = .40.
            - Source states pre-registered large-scale RCTs — "required by the funders to be published irrespective of the result," and therefore immune to publication bias — average just d = .06.
            - Source states: "Neglect of the adjustment for publication bias in meta-analyses or making it inconsequential may then lead to the adoption of ineffective or harmful educational policies."
            - Verification note: this paper's detailed example is ego-depletion psychology, not tutoring. It is cited here as a general methodological caution applicable to education meta-analyses by extension, not as direct evidence about tutoring specifically.
         - **DOK 2 - Summary:**
            - Across education research generally, meta-analytic effect sizes run roughly 6-7x larger than what publication-bias-immune, pre-registered RCTs find. This doesn't prove any specific tutoring number above is inflated, but it's a reason to treat any single meta-analytic effect size — including this project's own future eval numbers — with real skepticism until checked against pre-registered or held-out evidence.
         - **Link to source:** https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0252415

- **Category 2: When Does Direct Help Hurt Learning?**
   - **Subcategory 2.1: Cognitive load and expertise**
      - **Source 1: Kalyuga, Ayres, Chandler & Sweller (2003), "The Expertise Reversal Effect"**
         - **DOK 1 - Facts:**
            - Source defines the effect as "the reversal of the effectiveness of instructional techniques on learners with differing levels of prior knowledge."
            - Source states, of novices: "Low-knowledge learners lack schema-based knowledge in the target domain and so this guidance comes from instructional supports, which help reduce the cognitive load associated with novel tasks."
            - Source states, of advanced learners: "If additional instructional guidance is provided it can result in the processing of redundant information and increased cognitive load."
            - Source states the mechanism: advanced learners must "relate and reconcile the related components of available long-term memory base and externally provided guidance. Such integration processes may impose an additional working memory load and reduce resources available for learning new knowledge."
         - **DOK 2 - Summary:**
            - Worked examples and direct guidance measurably help novices but measurably hurt advanced learners.
            - This is because reconciling externally-given help with existing knowledge imposes extra cognitive load once a learner has real schema to draw on.
         - **Link to source:** https://en.wikipedia.org/wiki/Expertise_reversal_effect
   - **Subcategory 2.2: Production validation, and its limits**
      - **Source 1: Khan Academy Blog, "Built in the Open: How Pilot Districts Shaped the Reimagined Khan Academy" (2026-06-15)**
         - **DOK 1 - Facts:**
            - Source states: "One of the earliest guardrails we imposed when creating Khanmigo was that it should not give students the answer."
            - Source states the refined rule: "Before a student submits an answer Khanmigo should encourage the attempt and offer gentle hints." But: "After a student gets something wrong, support can be more direct. In that moment, it may be more helpful for Khanmigo to walk through the work, explain what happened, and help the student recover before the mistake becomes a repeated practice."
            - Source states the rationale from pilot-district teachers: without direct post-error support, students who practice incorrectly at home require "seven times the effort to erase that bad practice and reteach them," whereas with refined support, "kids don't practice math wrong."
         - **DOK 2 - Summary:**
            - Khan Academy bolted a state-dependent correction onto Khanmigo's original blanket "never give the answer" rule after pilot-district teachers reported it caused students to practice incorrectly at home.
            - This is nearly exactly the correction Kalyuga's theory predicts is needed.
         - **Link to source:** https://blog.khanacademy.org/built-in-the-open-how-pilot-districts-shaped-the-reimagined-khan-academy/
      - **Source 2: Khan Academy Blog, "How Khan Academy Is Building a Better AI Tutor: Our Most Recent Learnings" (2026-05-06)**
         - **DOK 1 - Facts:**
            - Source states Khan Academy monitors guardrail metrics including "instances of giving the answer away before a student submitted a response, math error rates, and interactions per thread."
            - Source discloses a formal six-month (Oct 2025–Apr 2026) A/B testing program across roughly 20 tests and 15+ million threads, using named metrics including "next-item correctness" and "cognitive engagement quality."
            - Source reports explicit null results for specific tested interventions: "Adding examples of different problem types related to the skill as part of the prompt showed no effect," and "providing more relevant follow-up content links based on the student's position in the Khan Academy content showed no statistically significant change in next-item correctness."
         - **DOK 2 - Summary:**
            - Khan Academy treats "gave the answer away" as a directly monitored, quantified metric, not just a design intention.
            - Beyond that, they ran a large-scale (15M+ thread), multi-month A/B testing program and found several plausible-sounding interventions had *no measurable effect* — a useful caution that intuitive-seeming prompt/UX changes don't reliably move the needle without being tested, which is directly relevant to how this project should treat its own eval iteration.
         - **Link to source:** https://blog.khanacademy.org/how-khan-academy-is-building-a-better-ai-tutor-our-most-recent-learnings/
      - **Source 3: Sal Khan, TEDx talk "The Two Sigma Solution" (May 2023)**
         - **DOK 1 - Facts:**
            - Source states Khan gave a May 2023 TEDx talk titled "The Two Sigma Solution," which explicitly invoked Bloom's two-sigma claim to frame and promote the launch of Khanmigo.
            - Source states Khan gave a live demo of Khanmigo during the talk, positioning it as a way to make one-to-one tutoring's promised benefit available "to every student on Earth."
         - **DOK 2 - Summary:**
            - Khan Academy's own public justification for its flagship AI tutoring product explicitly names Bloom's outlier 2.0σ claim (Category 1, Subcategory 1.1, Source 1) — not the much more modest ~0.3σ consensus that four decades of independent meta-analyses actually support — as the benefit being unlocked at scale.
         - **Link to source:** not independently re-fetched this pass; corroborated by two independent secondary sources (Khan Academy Blog coverage and third-party commentary) describing the same talk and title
      - **Source 4: Dan Meyer, "RIP Khanmigo & Edtech Industry Dreams of AI Tutors" (Substack)**
         - **DOK 1 - Facts:**
            - Source quotes Sal Khan: "For a lot of students, it was a non-event" and "They just didn't use it much."
            - Source states Khan's 2024 prediction that AI would cut "90% of teachers' admin tasks" failed to materialize, and Khan pushed that prediction out to 2034.
            - Source states projected annual users dropped from "a million or two million" to "500,000 to one million students" within months.
            - Source states Khan Academy shifted Khanmigo in 2026 from opt-in to "an always-on chatbot experience, already activated with or without the student's invitation" because students weren't seeking help as anticipated.
            - Source quotes Khan Academy's Chief Academic Officer Kristen DiCerbo: "I am not seeing the revolution in education."
         - **DOK 2 - Summary:**
            - Getting the specific behavioral guardrail mechanism right did not translate into adoption or the outcomes Khan Academy predicted for Khanmigo.
            - Pedagogical-design correctness and product/adoption success are separable questions — this source is evidence they can diverge sharply in practice.
         - **Link to source:** https://danmeyer.substack.com/p/rip-khanmigo-and-edtech-industry
      - **Source 5: Dan Meyer, "Khanmigo Wants to Love Kids but Doesn't Know How" (Substack)**
         - **DOK 1 - Facts:**
            - Source states Khanmigo "requires students to 'do some homework before it'll help you with your homework,'" and assesses that "many students will decline" to engage because of this.
            - Source characterizes Khanmigo's approach to student errors as treating "math as machine-executable code" and students "as buggy computers" — asking "what did the student do wrong?" rather than treating a wrong answer as an earnest, if incomplete, integration of new and old knowledge.
         - **DOK 2 - Summary:**
            - The one concrete, source-grounded mechanism found for low opt-in adoption is *friction* — Khanmigo demanding upfront effort before helping — not ease-of-avoidance or students being unaware it existed. This is close to the opposite of "it was a tempting shortcut students avoided out of awareness gaps."
         - **Link to source:** https://danmeyer.substack.com/p/khanmigo-wants-to-love-kids-but-doesnt
      - **Source 6: AgentConn Blog, "Khanmigo Was 'a Non-Event.' What's Next for AI Tutors" — citing Stanford CEPA**
         - **DOK 1 - Facts:**
            - Source states: "Stanford CEPA documented a 60% engagement drop after three weeks" of unfacilitated use, and characterizes this as "the median outcome for chat-only student tutors" generally — a category-wide pattern, not a Khanmigo-specific finding.
            - Source states Khan Academy's own explanation for the always-on pivot was that "students were not seeking out Khanmigo's help as much as we had hoped."
         - **DOK 2 - Summary:**
            - Engagement decay for unfacilitated chat-tutors appears to be a structural pattern across the whole product category, not something specific to Khanmigo's design choices — which weakens any explanation of Khanmigo's adoption failure that treats it as a Khanmigo-specific execution mistake rather than a harder, category-wide problem.
         - **Link to source:** https://agentconn.com/blog/ai-tutoring-agents-post-khanmigo-mytutor-2026/
      - **Source 7: EdTech Innovation Hub, "Only 15% of students use Khanmigo, Khan Academy reveals redesign"**
         - **DOK 1 - Facts:**
            - Source states: "Only 15 percent of students with access to Khan Academy's Khanmigo AI tutor regularly engage with it," following the 2023 rollout — a precise figure, sharper than "a lot of students" or "a non-event."
            - Source states Khan Academy's Chief Learning Officer attributes the redesign to observed *inconsistency* in interaction quality, not discovery or friction: early use "has varied" and "some chats help students move forward more than others," identified through "classroom observation and educator feedback."
            - Source states the redesigned Khanmigo "guides students through assignments and appears more visibly while they work on problems" rather than waiting for manual initiation, and "has differentiated how the AI supports students before and after they attempt a problem" — i.e., pre-attempt support still exists, but is differentiated from post-attempt support, not identical to it.
         - **DOK 2 - Summary:**
            - There are at least three distinct, separately-sourced candidate mechanisms for low opt-in adoption: effort-friction (Dan Meyer, Source 5), inconsistent per-interaction quality (Khan Academy's own CLO, this source), and category-wide engagement decay for chat-tutors generally (Stanford CEPA, Source 6). None of these is "students found it too easy to avoid work" — they point toward the opposite (too much friction) or toward quality-control (some interactions just weren't good), which is directly relevant to why an adequacy-judging layer would matter.
            - Cross-referenced against Category 2, Subcategory 2.2, Source 1 (the "Built in the Open" pre/post-attempt guardrail): the redesign's proactive/visible delivery is a change to *initiation*, not to the *substance* of what's given — pre-attempt support is still "encourage the attempt and offer gentle hints," not answers. The productive-struggle-preserving guardrail (Category 4, Subcategory 4.2) appears to be intact in the redesign, not removed by it.
         - **Link to source:** https://www.edtechinnovationhub.com/news/only-15-percent-of-students-with-access-to-khanmigo-actually-use-it-khan-academy-admits

- **Category 3: Do LLM Tutors Actually Fail This Way, and Is It Fixable?**
   - **Subcategory 3.1: Adversarial robustness of LLM tutors**
      - **Source 1: Zhao, Knežević & Käser, "Evaluating Answer Leakage Robustness of LLM Tutors against Adversarial Student Attacks" (arXiv:2604.18660, 2026-04-20)**
         - **DOK 1 - Facts:**
            - Source states: "Large Language Models (LLMs) are increasingly used in education, yet their default helpfulness often conflicts with pedagogical principles."
            - Source states prior work "typically assumes well-intentioned learners, leaving tutor robustness under student misuse largely unexplored."
            - Source states they "adapt six groups of adversarial and persuasive techniques to the educational setting" to probe tutors.
            - Source reports contextual-manipulation attacks induced the highest mean leakage across tested models (~74%), while emotional-threat attacks were least effective (~47% disclosure).
            - Source reports a reasoning-augmented tutor defense "reduced leakage from 46% to 2-4% under manual attacks," holding across domains (MCQ: 88%→10%; coding: 88%→41%).
            - Source reports leakage did not track model size: Qwen-7B and TutorRL-7B were most vulnerable (~75% average leakage) while Llama-8B was most robust (~40% average leakage).
         - **DOK 2 - Summary:**
            - Current LLM tutors leak final answers under social/persuasive pressure up to ~74-75% of the time under the strongest attack styles, independent of model size.
            - A reasoning-augmented defense cuts that leakage by roughly an order of magnitude (46% → 2-4%), suggesting this is a fixable behavioral/training gap rather than a hard capability ceiling.
         - **Link to source:** https://arxiv.org/abs/2604.18660
   - **Subcategory 3.2: Why models default to caving (training mechanism)**
      - **Source 1: Shapira, Benade & Procaccia, "How RLHF Amplifies Sycophancy" (arXiv:2602.01002, 2026-02-01)**
         - **DOK 1 - Facts:**
            - Source states: "Large language models often exhibit increased sycophantic behavior after preference-based post-training, showing a stronger tendency to affirm a user's stated or implied belief even when this conflicts with factual accuracy or sound judgment."
            - Source states they identify "an explicit amplification mechanism that causally links optimization against a learned reward to bias in the human preference data used for alignment."
            - Source states "the direction of behavioral drift is determined by a covariance under the base policy between endorsing the belief signal in the prompt and the learned reward."
            - Scope limit (verified directly against the abstract): this paper's definition of sycophancy is specifically about affirming "a user's stated or implied belief" — it does not address, measure, or claim anything about capitulating to repeated requests/pressure for a withheld answer.
         - **DOK 2 - Summary:**
            - This paper proves a specific mechanism by which RLHF amplifies sycophancy toward stated beliefs.
            - Using it as a direct explanation for tutor answer-leakage under pressure would be an inferential leap beyond what the paper itself shows — it's a plausible mechanism analogy, not direct evidence for this project's specific failure mode.
         - **Link to source:** https://arxiv.org/abs/2602.01002

- **Category 4: What Makes 1:1 Tutoring Structurally Different From Solo Study?**
   - **Subcategory 4.1: Calibrated support (Zone of Proximal Development)**
      - **Source 1: Vygotsky (1978), *Mind in Society*, via SimplyPsychology overview**
         - **DOK 1 - Facts:**
            - Source states Vygotsky (1978, p. 86) defined the ZPD as "the distance between the actual developmental level as determined by independent problem solving and the level of potential development as determined through problem-solving under adult guidance, or in collaboration with more capable peers."
            - Source states learning happens through a "More Knowledgeable Other" (MKO) — "anyone with a higher skill level than the learner: be it a teacher, parent, or peer" — whose function includes providing scaffolding, modeling, offering hints/prompts that guide without fully solving the task, and gradually withdrawing support as competence increases (fading).
         - **DOK 2 - Summary:**
            - ZPD is the specific theoretical claim that a more knowledgeable other should calibrate support to what a learner can do *with guidance* but not yet alone, and withdraw that support as competence grows.
            - This is the theoretical basis for why 1:1 tutoring should outperform static instruction at all — it's not just "more attention," it's continuously-recalibrated support.
         - **Link to source:** https://www.simplypsychology.org/zone-of-proximal-development.html
      - **Source 2: Myung, Lim, Oh, Jin, Kang, Ahn, Hong, Oh & Kim, "When Scaffolding Breaks: Investigating Student Interaction with LLM-Based Writing Support in Real-Time K-12 EFL Classrooms" (CHI '26, Apr 2026) — LLM failure evidence**
         - **DOK 1 - Facts:**
            - Source states the study examined 157 eighth-graders using LLM-based writing scaffolding over six weeks in real K-12 EFL classrooms.
            - Source states step-by-step scaffolding "demotivated lower-proficiency students and increased their system reliance," creating dependency rather than skill development.
            - Source states the system's assistance made it "difficult for teachers to identify struggling students" who needed intervention.
            - Source states "extroverted students often dominated the teacher's attention," compounding the technical mismatch with a social one.
         - **DOK 2 - Summary:**
            - In a real, multi-week classroom deployment, LLM scaffolding that wasn't recalibrated per-student produced the opposite of ZPD-appropriate support for weaker students: more dependency, not more competence, and reduced teacher visibility into who actually needed help.
         - **Link to source:** https://arxiv.org/abs/2512.05506
   - **Subcategory 4.2: Productive struggle (desirable difficulty)**
      - **Source 1: Bjork (1994); paraphrased definition via Structural Learning**
         - **DOK 1 - Facts:**
            - Secondary source (Structural Learning, paraphrasing Bjork, not a verbatim Bjork quote) states: "Desirable difficulties, a concept from Robert Bjork, are learning conditions that feel harder in the moment—such as spacing, retrieval practice, and interleaving—but lead to stronger, longer-lasting memory."
            - Bjork (1994) states, of trainers whose trainees' immediate performance is the reinforcement signal: "Such a conditioning process, over time, can act to shift the trainer toward manipulations that increase the rate of correct responding — that make the trainee's life easier."
         - **DOK 2 - Summary:**
            - Desirable difficulty is the claim that effortful conditions (retrieval, spacing, generation) produce more durable learning than easy ones, even though they feel worse in the moment.
            - Bjork's own 1994 observation is notably general: *any* trainer optimized on short-term correct-response rate will drift toward making things easier for the trainee — a mechanism-level claim that doesn't depend on RLHF or LLMs at all, which matters for how strong a claim to make later.
         - **Link to source:** https://www.structural-learning.com/post/desirable-difficulties
      - **Source 2: Experimental study on LLMs vs. web search and depth of learning (PNAS Nexus) — LLM failure evidence**
         - **DOK 1 - Facts:**
            - Source reports seven experiments (four main, three supplementary), 10,462 total participants, comparing learning via traditional web search vs. LLM synthesis (ChatGPT / Google AI Overview).
            - Source reports ChatGPT users spent significantly less time engaging with results than Google users (585s vs. 743s, Experiment 1, p<0.001).
            - Source reports ChatGPT users self-reported learning fewer new things than Google users (M=3.43 vs. M=3.86, F(1,1102)=36.04, p<0.001).
            - Source reports LLM-condition advice was less original (cosine similarity 0.159 vs. 0.057 for Google; lower similarity = more original).
            - Source explicitly invokes desirable-difficulty theory: "the effort required to learn from standard web search results can lead users to develop deeper knowledge on a subject," because "when we encounter friction in learning, we reflexively devote more cognitive resources to overcoming it, which leads us to process what we are trying to learn more deeply."
         - **DOK 2 - Summary:**
            - A large (n=10,462), multi-experiment study finds LLM-assisted learning produces less effort, less self-reported learning, and less original output than search-based learning, and the authors attribute this directly to the removal of desirable difficulty.
            - This is direct, quantitative evidence that the convenience LLMs provide is itself pedagogically costly, independent of any single model's specific tutoring behavior.
         - **Link to source:** https://pmc.ncbi.nlm.nih.gov/articles/PMC12560091/
   - **Subcategory 4.3: Feedback as tutoring's central affordance**
      - **Source 1: Hattie & Timperley (2007); Kluger & DeNisi (1996) meta-analysis, via Frontiers in Psychology review**
         - **DOK 1 - Facts:**
            - Source states Kluger & DeNisi (1996) "conducted among the most comprehensive review, based on 131 studies, over 12,000 participants, with an average effect of 0.38, noting that about a third of the effects were negative."
            - Source states "the majority of feedback in classes is task feedback, the most received and interpreted is about 'where to next,' and the least effective is self or praise feedback."
            - Source states "21 percent of the effect sizes related to motivational outcomes in [their] data were negative, with 86% of the feedback interventions leading to these negative effects being uninformative (rewards or punishments)."
         - **DOK 2 - Summary:**
            - Feedback is one of the largest levers on learning (average effect 0.38 across 131 studies) but roughly a third of feedback interventions actually hurt performance, and self/praise-focused feedback is specifically the least effective type — task-focused, "where to next" feedback is what works.
            - Not-yet-verified bridging observation (connects to Category 3, not a new dedicated study): this maps closely onto what sycophancy (Category 3, Subcategory 3.2) would predict a validation-optimized model defaults to — affirming/praising rather than task-focused correction — but no source in this BrainLift directly tests LLM tutors against Kluger & DeNisi's feedback-type taxonomy. That gap is worth flagging rather than papering over with an inferred link.
         - **Link to source:** https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.03087/full

- **Category 5: Does Teaching Benefit the Teacher?**
   - **Subcategory 5.1: The tutor-benefit finding and its mechanism**
      - **Source 1: Cohen, Kulik & Kulik (1982), "Educational Outcomes of Tutoring: A Meta-analysis of Findings"**
         - **DOK 1 - Facts:**
            - Source states (per ERIC abstract record) tutoring programs produced "positive effects on the academic performance and attitudes of both tutees and their student tutors."
            - Source states the review covered "65 independent evaluations of school tutoring programs."
            - Verification note: a specific effect-size pair (0.29 for reading, 0.60 for math) circulates online attributed to this paper's tutor-benefit finding. I could not confirm this against the ERIC abstract record, and it may belong to a different, more specific peer-tutoring meta-analysis. Not used as a fact here — flagged rather than repeated.
         - **DOK 2 - Summary:**
            - The tutor-benefit finding is real and specific — tutors themselves gained academically and attitudinally, not just tutees — but I could not verify a specific effect size for it, so none is claimed.
         - **Link to source:** https://eric.ed.gov/?id=EJ272101
      - **Source 2: Bargh & Schul (1980), "On the Cognitive Benefits of Teaching," *Journal of Educational Psychology*, 73, 593–604**
         - **DOK 1 - Facts (secondary characterization — I could not access primary full text; not independently verified via direct quote):**
            - Secondary sources describe the paper as arguing teaching's cognitive benefit comes from three separable phases: preparing to teach, the initial presentation to students, and subsequent interaction (answering questions, giving feedback).
            - Secondary sources describe the paper's claim that merely *expecting* to teach changes how someone studies, by "priming students to devote more resources toward selecting the most relevant material and organizing it into a meaningful representation" — i.e., some of the benefit may occur before any teaching interaction happens at all.
         - **DOK 2 - Summary:**
            - If accurate, "benefit to the tutor" isn't one mechanism — it's at least three (expectation, preparation, interaction), and part of it may not require an actual student on the other end.
         - **Link to source:** https://www.semanticscholar.org/paper/On-the-Cognitive-Benefits-of-Teaching-Bargh-Schul/6062c346f4f39f83424faf7c8e91f20776f029da
   - **Subcategory 5.2: When does teaching actually build the tutor's own understanding?**
      - **Source 1: Roscoe & Chi (2007), "Understanding Tutor Learning: Knowledge-Building and Knowledge-Telling in Peer Tutors' Explanations and Questions," *Review of Educational Research*, 77, 534–574**
         - **DOK 1 - Facts (secondary characterization only — 4 direct-fetch attempts at the primary abstract were blocked by paywalls/empty responses; treat as unverified until re-checked against primary text):**
            - Secondary sources describe the paper's core distinction: tutor-side learning benefits come from "reflective knowledge-building" (tutors reflecting on the tutee's understanding, integrating new and prior knowledge), not from explaining as such.
            - Secondary sources describe the contrasting failure mode as "knowledge-telling" — tutors who "simply lecture" and "focus more on delivering knowledge rather than developing it" — and describe this bias as pervasive even among trained peer tutors, such that "the true potential for tutor learning may rarely be achieved."
         - **DOK 2 - Summary:**
            - Not every act of "explaining to help someone else" builds the explainer's own understanding — on this account, the benefit depends on whether the explanation reflects on the other person's specific state (knowledge-building) or just restates known material (knowledge-telling), and the latter is described as the more common outcome in practice.
         - **Link to source:** https://journals.sagepub.com/doi/abs/10.3102/0034654307309920 (abstract paywalled; not independently verified during this research pass)
      - **Source 2: Chase, Chin, Oppezzo & Schwartz (2009), "Teachable Agents and the Protégé Effect," via Stanford AAA Lab**
         - **DOK 1 - Facts:**
            - Source (AAA Lab, directly verified) states the teaching metaphor "enlists fruitful social attitudes during the interaction, including a sense of responsibility for one's agent that appears to motivate students to work harder to organize their understanding."
            - Secondary characterization (not independently verified via primary abstract fetch — access attempts were blocked): in the underlying Betty's Brain study, students who taught the agent "spent more time on task, engaged in more self-regulated learning, and scored higher on assessments" than students using the same system to learn for themselves, with the effect reportedly strongest for non-experts, since gaps in one's own understanding "become immediately obvious" when trying to teach it.
         - **DOK 2 - Summary:**
            - The protégé effect gives a specific candidate mechanism (responsibility for another's understanding changes effort/self-monitoring) for why teaching benefits the teacher.
            - Notably, this literature is about a *human* teaching an *artificial* learner (Betty's Brain) — the opposite direction from this project, where a model judges/rewrites a *human* tutor's output. Worth keeping that directional difference explicit rather than treating the two setups as interchangeable.
         - **Link to source:** https://aaalab.stanford.edu/teachable-agents/research

- **Category 6: Khanmigo's Documented Track Record — Technical, Accuracy, and Independent Evaluation**
   - *Found via a 6-agent parallel investigation specifically targeting Khanmigo (not LLM tutors generally), each fetching primary sources directly; a synthesis pass cross-checked every claim and excluded several that didn't survive re-verification (a misattributed ChatGPT quote, an unlocatable quote, an unconfirmed "idk" transcript claim, and a mischaracterized pre-AI study) — those exclusions are not repeated here.*
   - **Subcategory 6.1: Technical architecture and disclosed engineering fixes**
      - **Source 1: Microsoft Education Blog, "Enhancing the future of education with Khan Academy" (May 2024)**
         - **DOK 1 - Facts:**
            - Source states Microsoft and Khan Academy co-developed "an open-source fine-tuned version of Phi-3... fine-tuned by Microsoft for calling Python code for complex calculations," trained on synthetic tutoring data from Accelerate Learning and UPchieve, running on Azure OpenAI Service.
            - Source states explicitly: "None of Khan Academy's user data will be used to train the model."
         - **DOK 2 - Summary:**
            - Khanmigo's math tutoring is not just a single frontier model — it involves a separate small, fine-tuned model with Python tool-calling specifically for calculation, which is a distinct architecture choice from prompting a general-purpose frontier model directly.
         - **Link to source:** https://www.microsoft.com/en-us/education/blog/2024/05/enhancing-the-future-of-education-with-khan-academy/
      - **Source 2: Khan Academy Blog, "Khanmigo Math Computation and Tutoring Updates"**
         - **DOK 1 - Facts:**
            - Source states: "We built a calculator for Khanmigo to solve numerical problems instead of relying on AI's predictive capabilities."
            - Source states: "We moved Khanmigo math tutoring from GPT-4 Turbo to GPT-4 Omni, which we found leads to better tutoring performance."
            - Source states accuracy improves "when Khanmigo has access to human-generated exercises, steps, hints, and solutions prior to making a calculation or evaluation" — i.e., grounding in Khan Academy's own content library, not relying on the model alone.
            - Source states, benchmarked against a named rival: "compared to raw GPT4o (the LLM powering ChatGPT), Khanmigo is much better at catching and pointing out mistakes."
            - Source separately admits Khanmigo "occasionally struggles to interpret graphics."
         - **DOK 2 - Summary:**
            - Khan Academy's own fix for math errors was architectural (deterministic calculator tool, retrieval-grounding in their content library, model migration) rather than prompt-tuning alone — direct precedent for why this project treats judgment/rewriting as a separate layer rather than something to prompt-engineer into a single generation step.
         - **Link to source:** https://blog.khanacademy.org/khanmigo-math-computation-and-tutoring-updates/
   - **Subcategory 6.2: Subject-matter accuracy — from a vague metric to quantified failure**
      - **Source 1: Wall Street Journal testing (Feb 2024), via IBL News summary**
         - **DOK 1 - Facts:**
            - Source states WSJ testing found Khanmigo "frequently made basic arithmetic errors, miscalculating subtraction problems such as 343 minus 17," and "didn't consistently know how to round answers or calculate square roots."
            - Source states Khanmigo "typically didn't correct mistakes when asked to double-check solutions."
         - **DOK 2 - Summary:**
            - This is a concrete, reproducible, dated failure mode (basic arithmetic, self-correction failure) — sharper than the brainlift's previously-known vague "math error rates" metric, and independently corroborated by EdWeek's characterization of the same WSJ reporting.
         - **Link to source:** https://iblnews.org/khanmigo-struggles-with-basic-math-showed-a-report/
      - **Source 2: Miller & DiCerbo, "LLM Based Math Tutoring: Challenges and Dataset" (Khan Academy technical report / CoMTA benchmark, 2024)**
         - **DOK 1 - Facts:**
            - Source states: "the model sometimes provides incorrect evaluation information to the student. That is, it indicates the student is correct when they are wrong or incorrect when they are right."
            - Source reports quantified per-model accuracy on detecting incorrect vs. correct student answers: GPT-4o at 68.5% accuracy detecting incorrect answers vs. 85.8% confirming correct ones; Claude 2.1 as low as 31.7% detecting incorrect answers vs. 91.5% confirming correct ones.
         - **DOK 2 - Summary:**
            - This is Khan Academy's own self-published, quantified evidence that models are asymmetrically worse at *catching a student's mistake* than at *confirming a student is right* — and that this gap varies enormously by model family (31.7% to 68.5%). This is the single most directly relevant piece of evidence in the whole brainlift for why a dedicated adequacy-judging layer matters: the specific failure this project targets (correctly recognizing when a message is inadequate) is exactly where these models are weakest, on Khan Academy's own numbers.
         - **Link to source:** https://github.com/Khan/tutoring-accuracy-dataset
   - **Subcategory 6.3: Independent and peer-reviewed evaluation**
      - **Source 1: Slijepcevic & Yaylali (2025), *Journal of Teaching and Learning***
         - **DOK 1 - Facts:**
            - Source (n=69, Lunar Phases Concept Inventory) states: "Quantitative analysis revealed significant learning gains across all conditions but found no statistically significant differences between groups" comparing Khanmigo to a free Google-search condition.
         - **DOK 2 - Summary:**
            - A peer-reviewed, controlled comparison found Khanmigo produced no measurable learning advantage over free web search for this science topic — a direct null result on efficacy, not just adoption.
         - **Link to source:** https://jtl.uwindsor.ca/index.php/jtl/article/view/10052
      - **Source 2: Alvarez & Angeles (2025), *Educational Process: International Journal* (SWOT/TAM acceptability study, N=108/55)**
         - **DOK 1 - Facts:**
            - Source reports students self-rated agreement with statements including "AI tools sometimes give incorrect or misleading information" (weighted mean 2.89) and "AI cannot always provide satisfactory explanations" (weighted mean 2.93).
         - **DOK 2 - Summary:**
            - Independent survey evidence that students themselves perceive real accuracy/explanation-quality limitations, distinct from the adoption-rate sources already in the brainlift.
         - **Link to source:** https://files.eric.ed.gov/fulltext/EJ1483352.pdf
      - **Source 3: Shetye (2024), *Studies in Applied Linguistics & TESOL* (CALL framework evaluation, Columbia Teachers College)**
         - **DOK 1 - Facts:**
            - Source rates Khanmigo "Not Supported" on the Learner Fit criterion for French-language learning: "The language used by Khanmigo and the topics selected by Khanmigo for discussion did not match learner characteristics," based on 17.5 hours of use.
         - **DOK 2 - Summary:**
            - An outside academic framework (Chapelle's CALL evaluation criteria), applied to a domain outside math, independently found a fit failure — though this is a single-researcher case study (n=1), not a large sample.
         - **Link to source:** https://files.eric.ed.gov/fulltext/EJ1435677.pdf
      - **Source 4: Michigan Virtual, "Have You Considered AI in Your Classroom? A Khanmigo Pilot Story" (independent two-phase pilot, 19–24 teachers, 687–1,102 students)**
         - **DOK 1 - Facts:**
            - Source states some students used Khanmigo as "a workaround—a way to get answers quickly or to check their work, rather than a tool to deepen their understanding."
         - **DOK 2 - Summary:**
            - Independent, non-Khan-Academy evidence that students routed around the "never give the answer" guardrail's intent in practice — a concrete counter-data-point to treating the guardrail design as sufficient on its own.
         - **Link to source:** https://michiganvirtual.org/blog/have-you-considered-ai-in-your-classroom-a-khanmigo-pilot-story
      - **Source 5: Oreopoulos et al., preregistered RCT (AEA RCT Registry / J-PAL, ID AEARCTR-0013519)**
         - **DOK 1 - Facts:**
            - Source describes an in-progress causal RCT of Khanmigo across ~22 Tennessee schools (~3,300 students), comparing coaching-support conditions and passive vs. active interface prompts, with math/English test scores as primary outcomes. Status: in development, no results yet.
         - **DOK 2 - Summary:**
            - The first genuinely independent causal-effectiveness trial of Khanmigo identified — must be treated as pending, not evidence of an effect either way.
         - **Link to source:** https://www.socialscienceregistry.org/trials/13519
   - **Subcategory 6.4: Firsthand classroom accounts**
      - **Source 1: Chalkbeat, "Why Sal Khan is rethinking how AI will change schools" (2026-04-09)**
         - **DOK 1 - Facts:**
            - Source quotes Kristen DiCerbo offering a distinct root-cause explanation from her "passive interactions" quote already in the brainlift: "Students aren't great at asking questions well."
            - Source reports a geometry teacher (Kristen Musall, Hobart High School, an original 2023 pilot site) stopped using Khanmigo, explaining: "If students don't engage with the material enough to know what they're looking for, then an AI like Khanmigo doesn't necessarily help."
            - Source reports named students describing attempts to manipulate the tool ("bullying the bot," trying to trick it into giving answers).
         - **DOK 2 - Summary:**
            - A named teacher at an original pilot site abandoning the tool, plus a second distinct root-cause explanation from Khan Academy's own CAO (not knowing how to ask good questions, versus passive interaction) — two different specific failure mechanisms from two different vantage points, neither reducible to "friction" or "discoverability."
         - **Link to source:** https://www.chalkbeat.org/2026/04/09/sal-khan-reflects-on-ai-in-schools-and-khanmigo/
   - **Subcategory 6.5: Competitive contrast and bias**
      - **Source 1: Carnegie Learning (Dr. Steve Ritter), "AI Arms Race: Our 25-Year Head Start Keeps Carnegie Learning Invincible"**
         - **DOK 1 - Facts:**
            - Source states, of chatbot-style AI tutors like Khanmigo: "AI chatbots display none of that sensitivity, immediately answering a question right when a student types it in."
            - Source cites a RAND Corporation RCT (18,000+ students, 147 schools) showing MATHia's hint/guardrail design roughly doubled algebra learning growth, meeting ESSA Tier 1 evidence standards.
         - **DOK 2 - Summary:**
            - A direct competitor argues chatbot-style tutors structurally lack the calibration mechanisms this project targets, and backs its own product with a considerably more rigorous outcome study than anything published for Khanmigo specifically — a real evidentiary asymmetry worth being honest about.
         - **Link to source:** https://carnegielearning.medium.com/ai-arms-race-our-25-year-head-start-keeps-carnegie-learning-invincible-ac304f0445e9
      - **Source 2: Chalkbeat, "Annie and Lakeesha struggle in school. AI teacher assistants treated them very differently." (2025-08-06)**
         - **DOK 1 - Facts:**
            - Source describes a Common Sense Media controlled study (50 white-coded vs. 50 Black-coded student-name prompts) finding Google Gemini for Education and MagicSchool gave systematically more positive behavior-intervention suggestions for white-coded names.
            - Khanmigo and Curipod were tested under the same protocol but were not implicated in the adverse finding.
         - **DOK 2 - Summary:**
            - Two named competitors failed a controlled bias test under identical conditions where Khanmigo did not get flagged — worth noting as a rare case where Khanmigo compares favorably, though absence of a reported adverse finding is not the same as an affirmative, quantified clean result.
         - **Link to source:** https://www.chalkbeat.org/2025/08/06/ai-teacher-assistants-promote-racial-bias-study-finds/
