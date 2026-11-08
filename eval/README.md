# Results and quality check: *I Married a Broken Soldier. He was a Duke*

Hookline analyzed all 50 episodes with Gemini 3.8 Flash as both picker and judge. Once a Gemini overload cleared, the run took about 9 minutes and used about 634k tokens, with no failures.

Every episode got one promo that meets the brief's mechanics:
- **Timestamps:** every timestamp comes from the script, and no line is clipped.
- **Length:** each promo runs 20.5–57.2 s (mean 36.6 s).
- **Hook timing:** the hook lands within 3 s.
- **Rule compliance:** 17 episodes needed one repair round, and none ended out of spec.

The full ranked list is in [ranked_promos.md](ranked_promos.md) / [.csv](ranked_promos.csv): every promo with its segments, hook, cliffhanger, why it works, scores and flags.

## 1. What I'd post first

| | Episode | Cut | Hook (first 3 s) | Cliffhanger | Why it works |
|---|---|---|---|---|---|
| 1 | **EP 3**: *A Second Chance at the Altar* (8.83, #1) | 01:00.00–01:04.50 + 01:06.00–01:28.10 + 02:12.70–02:25.75 (39.6 s) | Guards drag the jilted bride out of the church: "Let me go!" | A scarred stranger kneels with a ring: "Lady Juliana… accept my hand." | The whole series' fantasy in 40 s: humiliation, a mysterious rescuer, a proposal left hanging. |
| 2 | **EP 12**: *Planted Evidence & the Gallows* (8.50, #5) | 00:13.90–01:09.50 (55.6 s) | "The proof is in his coat…": her husband framed for theft | "Fail, or refuse, and your husband hangs from the gallows." | A life-or-death ultimatum a stranger understands instantly. |
| 3 | **EP 5**: *Thrown in the Dirt* (8.33, #8) | 00:54.00–01:04.60 + 01:31.00–01:41.50 (21.1 s) | Her mother's book is flung into the mud (reads on mute) | Her husband, quietly: "Choose your next words carefully." | Public humiliation, then the protector's menace; short enough to loop. |

**Why these three and not the raw top 3 (EP 3, 43, 44).**
- **Paid funnel.** Promos are paid acquisition. A new viewer starts at episode 1, and the paywall usually comes within the first 5–10% of episodes ([research](../docs/RESEARCH.md)).
- **Late-series promos.** A promo built on episode 43's villain capture or episode 44's "you were never my Duchess":
  - spoils the payoff
  - promises scenes about 40 episodes behind the paywall.
- **The rule.** "Post first" therefore takes the highest-scoring promos from the first third of the series that have no spoiler, ad-policy, weak-hook or weak-cliffhanger flag.

**Editor tweak for EP 12.** In the blind test (§3), the alternative cut starts on the arrest itself ("You are under arrest", 00:00.00) and reaches the ultimatum by 9 s. The tool's cut opens on a 6.5 s accusation. Use the earlier start.

**Next wave.** These are early, have no blocking flags, and score ≥ 7.8:
- EP 4: mocked as "a penniless nobody", then a proposal. Long at 53 s, and the blind judge preferred a tighter cut.
- EP 2: publicly dumped at the altar.
- EP 1: "He is marrying my sister".
- EP 15: her mother's garden destroyed.

**Hold back.** Keep the late-series payoffs (EP 43, 44, 46, 41, 36, 37, 47) for retargeting existing viewers rather than acquisition. They are strong drama but spoilers.

**EP 18 (*The Burning Ledger*).** The tool's cut plays the rescue through to safety. Use the alternative cut that stops on the rafter splitting above her, or skip it.

## 2. How the picks were checked

1. **Rule checks.** These run on every candidate, in code:
   - Timestamps come from the script's own blocks; the LLM only names block IDs.
   - Cuts snap so no line is clipped.
   - Each promo is 20–60 s, with the hook within 3 s, at most 3 non-overlapping segments, and the cliffhanger in the last segment.
   - Result: all 50 pass.
2. **An independent reference pass.** Two separate agents (Claude) worked from the same brief, each acting as a senior promo editor on 25 episodes, and picked the best promo plus a runner-up. Every timestamp was validated programmatically ([reference_picks_01-25.json](reference_picks_01-25.json), [reference_picks_26-50.json](reference_picks_26-50.json)). Comparison ([comparison.md](comparison.md)):

   | Measure | Result |
   |---|---|
   | Same moment as the reference (time overlap ≥ 50%) | 24 of 50 |
   | Partial overlap / matches the reference runner-up / a different moment | 21 / 3 / 2 |
   | Rank correlation with the reference's scores (Spearman) | 0.48 |
   | Top-10 overlap | 4 of 10 |
   | Stitched (multi-segment) promos, tool vs reference | 23 vs 40 |
   | Mean length, tool vs reference | 36.6 s vs 46.0 s |

3. **A blind A/B test on the worst disagreements.**
   - **Setup:** for the 17 episodes where the two picks overlapped least, a third agent saw both cuts as clip transcripts, with the order randomized and the source hidden. It chose the one it would post ([blind_ab/results.md](blind_ab/results.md)).
   - **Result:** the reference cut was preferred in 14 (7 clearly), the tool's in 1 (clearly: EP 40), and neither was postable in 2.
   - **Caveat on selection:** this is the tool's worst slice by construction, so it is not an overall win rate.
   - **Caveat on bias:** the reference builder and the judge are the same model family, which can favour the reference.
   - **Why it still counts:** the reasons it gave are concrete and checkable against the scripts, and they point to the failure modes below.

## 3. Where Hookline picks badly

Most impactful first. Each item gives the evidence, then what's fixed (**done**) and what's planned (**next**).

1. **It accepts a feeling as a cliffhanger.**
   - **Evidence:**
     - The blind test called 8 cuts "resolved"; 6 of them were the tool's.
     - In EP 9 the fever breaks. EP 17 ends on "Of losing you." EP 18 carries the rescue through to safety. EP 19 ends on an embrace, and EP 20 on "And I am not finished."
     - The tool's own judge scored those endings 7–8.
     - "Emotional peak" is its most common ending type (18 of 50) and the riskiest.
   - **Next:** a rubric change: a vow, confession or embrace after the event has settled caps the cliffhanger score. Then re-run the 17 episodes and repeat the blind test.
2. **The average hides a failed must-have.**
   - **Evidence:** EP 17's hook is a calm hearth shot that scored 2/10, yet the promo still averages 7.0.
   - **Done:** any hook or cliffhanger scored ≤ 4 is now flagged (`weak_hook`, `weak_cliffhanger`; 6 promos) and kept off "post first". The default ranking stays the plain average, as specified.
   - **Next:** gate the composite on hook and cliffhanger.
3. **Scores are compressed.**
   - **Evidence:**
     - The composite's standard deviation is 0.75.
     - 37 of 50 "premise" scores and 31 of 50 "clarity" scores are exactly 8.
     - Episodes are judged independently, so the middle of the ranking sits within the noise.
   - **How to read the ranking:** in tiers (the top ~10, a middle, a flagged bottom), not by exact position.
   - **Next:** a pairwise "which of these two" pass over each show's top 15, which LLMs do more reliably than absolute scores.
4. **It's blind to where an episode sits in the series.**
   - **Evidence:**
     - 7 of the top 10 come from episodes 36–47: the duke's return and the villains' downfall.
     - Spoiler flags are noisy. They miss major payoffs (EP 42 and EP 44 aren't flagged) and over-flag mild ones (EP 37's dungeon, EP 25's ailing Dowager). The picker only sees one episode.
   - **Done:** "post first" prefers the first third of the series and skips spoiler flags.
   - **Next:** give the picker the series' loglines so it judges spoilers in context.
5. **It overrates villain-only scenes.**
   - **Evidence:** EP 40, 48 and 49 have no protagonist on screen and no conflict; they score 7.7–7.8 here, while the reference rates them 5.
   - **Next:** anchor "premise pull" to the protagonist being on screen.
6. **Dead air and talky hooks.**
   - **Evidence:**
     - 18 of 50 promos have more than 6 s without dialogue; EP 41 has 25.8 s, though part of that is the doors exploding.
     - 21 of 50 hooks are a spoken line, and only 8 open on visual humiliation or violence. Talky hooks are weak for viewers on mute.
   - **Done:** a `dead_air` flag.
   - **Next:** penalize silence in the momentum anchors and prefer visual hooks.
7. **Simpler, shorter cuts than an editor's.**
   - **Evidence:** 23 vs 40 stitched promos, and 37 vs 46 s on average. Short isn't wrong for TikTok, but several blind-test losses were cuts that couldn't reach the sting without stitching (EP 12, EP 4).
8. **Text, not footage.**
   - It reads the screenplay, not the edit: it can't see performances, faces, music or final timing.
   - Script typos pass straight through: EP 46's hook quotes "Crown scesion", and estate names drift (Ashburn / Ashbury / Ashworth).
   - The duplicate check compares dialogue, so EP 31 and EP 32 ending on the same visual sting isn't caught.
9. **It grades its own homework.** Picker and judge are the same model by default. Choose a different judge model in Settings to reduce self-preference.

## 4. Next iteration

1. **Rubric v4:** fixes items 1, 5 and 6. Re-run only the 17 disputed episodes (about 40 Gemini calls), then repeat the blind A/B to measure the change.
2. **Pairwise ranking pass** for each show's top 15.
3. **Series context** for spoiler judgments.
4. **Close the loop with real data:** post the top picks, log hook rate and click-through per promo, and fit the dimension weights to what actually performs.

## Reproduce

The app ships with the 50 episodes queued, not analyzed. These results come from one run, snapshotted in [run_promos.json](run_promos.json).

```powershell
python run.py                                  # add a Gemini key in Settings; the 50 episodes analyze (~10 min)
python -m app.seed export                      # snapshot that run to eval/run_promos.json
python eval/compare.py --snapshot              # tool vs reference, from the snapshot
```

LLM output varies between runs, so a new run will not reproduce these exact picks or scores.

The blind A/B inputs are in [blind_ab/](blind_ab/): `packets.md` is what the judge saw, and `verdicts.json` is its raw output.
