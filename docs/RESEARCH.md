# How microdrama apps cut promos, and what Hookline takes from it

A desk-research summary from November 2026, focused on ReelShort and DramaBox with ShortMax, GoodShort and FlexTV as secondary examples.

**Where the evidence comes from:**
- Ad-intelligence vendors: AppGrowing, SocialPeta/Guangdada, Insightrackr, AdMapix.
- A 2023 TikTok for Business deck.
- Practitioner guides to cutting ad creatives.

**What's missing:**
- No app has published hook-rate or thumb-stop data.
- Several trade outlets were paywalled.

Claims marked *inference* are ours, not sourced.

## Context

- **Promos are mostly paid acquisition.** Paid installs were over 60% of 2024 downloads for DramaBox and ShortMax, and 70% for ReelShort ([Sensor Tower](https://sensortower.com/blog/short-drama-redefines-mobile-entertainment-and-challenges-games)).
- **Winners are found by testing volume.** ReelShort says "we launch thousands of creative variations every day" ([Liftoff](https://liftoff.ai/resources/case-study/reelshort/)), and it added roughly 3,600–3,800 new creatives a day in Sep–Oct 2026 ([AppGrowing](https://appgrowing.net/blog/en/dramabox-vs-reelshort-two-short-drama-ad-playbooks-in-the-same-month/)).
  - *Inference:* a tool like this is a candidate generator for that testing loop, not a final judge.

## Hooks (first 1–3 s)

The shared rule is conflict in the first 3 seconds: "a confrontation, a betrayal or a shocking line, never a logo or a slow setup" ([Growthtrait](https://www.growthtrait.com/en/blog/short-drama-ads)).

| Type (Hookline `hook_type`) | Example |
|---|---|
| Public humiliation (`humiliation`) | ReelShort's top 2023 creative opens on a saleswoman "making her kneel down to put on shoes" ([AppGrowing](https://appgrowing.net/blog/reelshort/)) |
| Physical aggression mid-action (`violence`) | "the betrayal, the truck arrival, the slap" ([SDP](https://shortdramapartner.com/blog/reelshort-affiliate-tiktok-guide)) |
| Threat or insult that works on audio alone (`threat_or_insult`) | "I'm gonna make you wish you were never born." ([Insightrackr](https://blog.insightrackr.com/en/docs/ShortMax-Mobile-Advertising-Intelligence-Analysis)) |
| Betrayal discovered (`betrayal`) | Betrayal/rebirth themes make up 18–19% of both brands' top-100 creatives ([AppGrowing](https://appgrowing.net/blog/en/dramabox-vs-reelshort-two-short-drama-ad-playbooks-in-the-same-month/)) |
| Hidden identity or status-reversal tease (`reveal`) | Status reversal is 29% of DramaBox's top 100 ([AppGrowing](https://appgrowing.net/blog/en/dramabox-vs-reelshort-two-short-drama-ad-playbooks-in-the-same-month/)) |
| Danger or mystery in medias res (`danger`), spectacle (`spectacle`) | Werewolf transformations; a woman huddled in a corner on the phone ([Insightrackr](https://blog.insightrackr.com/en/docs/ReelShort-Mobile-Advertising-Intelligence-Analysis)) |
| Romantic ultimatum (`romance`) | "Kiss me now or fire my mother's doctor" ([Real Reel](https://www.real-reel.com/my-drama-holywater/)) |

## Endings

The rule is to stop before the payoff. Promos show "the most explosive scenes and [stop] at a cliffhanger" ([Growthtrait](https://www.growthtrait.com/en/blog/short-drama-ads)).

The craft rule: the last line and action are complete, so the suspense comes from an unresolved event, not a cut-off sentence ([Mojian](https://www.mojianai.com/blog/10088)). Hookline's validator enforces this by never cutting mid-line.

Ending types (Hookline `cliffhanger_type`):
- **Pre-result stop:** cuts just before the answer, blow or reveal lands.
- **Twist line:** cuts right after a line that flips a relationship.
- **Next event:** cuts on the threshold of an arrival or a door opening.
- **Emotional peak.**
- **New question:** answers the opener, then opens a new question.

## Structure, length, pacing

- **Common templates** ([AppGrowing](https://appgrowing.net/blog/reelshort/), [Guangdada](https://guangdada.net/blog/149617), [Mojian](https://www.mojianai.com/blog/10132)):
  - A single-scene arc: conflict, escalation, a hint of reversal, cut.
  - Humiliation, then rescue, cut before the payback.
  - A highlight pre-roll followed by the scene in story order. The body must pay off the pre-roll quickly.
- **Most paid creatives run longer than 60 s.** 84% of DramaBox creatives do ([AppGrowing](https://appgrowing.net/blog/en/dramabox-vs-reelshort-two-short-drama-ad-playbooks-in-the-same-month/)). Standalone trailer cuts in the 20–60 s tier cluster around 46–55 s ([AdMapix](https://www.admapix.com/blog/ad-intelligence/dramabox-ad-strategy-2026)).
  - Hookline's picker targets 35–55 s.
- **Many viewers watch on mute.** Actors overplay so a scene reads without sound, and the opening frames carry a conflict that "reads without any context" ([Palai](https://palai.media/en/articles/iak-pratsiuie-format-short-drama)).
- **Make the setup legible.** Keep the line that states the relationship, and treat ~8 s to understand the opening as a failure ([Mojian](https://www.mojianai.com/blog/10032)).

## Pitfalls

- **Slow openings.**
- **Loud but unreadable:** shouting where you can't tell who is wronged.
- **Over-promising:** a pre-roll stronger than the body.
- **Spoilers:** identity, proof and comeback revealed together.
- **Bad joins:** time running backwards, or roles left unclear ([Mojian](https://www.mojianai.com/blog/10032), [Mojian](https://www.mojianai.com/blog/10088)).
- **Ad policy:** Meta rejects "shocking, sensational or excessively violent content" ([Meta](https://transparency.meta.com/policies/ad-standards/objectionable-content/violent-graphic-content)).
- **Funnel position:** the first paid episode usually falls within the first 5–10% of a series ([TikTok deck](https://www.tkfff.com/119513.html)).
  - *Inference:* a promo built on late-series moments promises something the viewer only reaches deep behind the paywall.

## What Hookline does with this

| Finding | In the tool |
|---|---|
| Conflict in 0–3 s, readable on mute | Hook anchors (`app/config.py`); the judge weighs CAMERA/ACTION lines as well as dialogue |
| Stop before the payoff, with complete lines | Cliffhanger anchors; no-mid-line snapping in `app/timeline.py` |
| The viewer must be able to say what they need next | The blind judge writes the open question itself. If it can't, cliffhanger is capped at 4 in code (`no_open_question` flag) |
| Who is wronged, by whom, within ~8 s | Clarity anchors; the judge's `confusions` become `cold_viewer` flags |
| Pre-rolls must pay off; bad joins confuse | Picker guidance, plus the clarity and momentum anchors on jumps |
| Spoilers, ad policy | Picker `risks` become `spoiler` / `ad_policy` flags, which keep a promo off the "post first" list |
| Testing at volume | One ranked promo per episode gives a 50-promo pool per show, with the alternates kept for audit |
| Funnel position | Not scored. Covered in the posting-order advice in `eval/README.md` |
