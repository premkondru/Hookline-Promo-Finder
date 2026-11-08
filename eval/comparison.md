# Tool vs reference picks

Episodes compared: 50

| Measure | Value |
|---|---|
| Same moment (IoU >= 0.5) | 24 |
| Partial overlap / same final cut | 21 |
| Tool picked the reference runner-up | 3 |
| Completely different moment | 2 |
| Mean IoU with reference best | 0.41 |
| Same opening (+-3s) / same final cut (+-3s) | 17 / 22 |
| Rank correlation, tool composite vs reference score (Spearman) | 0.48 |
| Top-10 overlap | 4 of 10 |
| Multi-segment promos, tool / reference | 23 / 40 |
| Mean duration, tool / reference | 36.6s / 46.0s |

Tool flags (excluding hook timing): cold_viewer x55, dead_air x18, repaired x10, spoiler x10, ad_policy x5, tail_after_cliffhanger x1

| Ep | Verdict | IoU | Tool cut | Reference cut | Tool composite | Ref score |
|---|---|---|---|---|---|---|
| 1 | partial | 0.42 | 00:32.80-01:19.00 | 00:32.80-00:43.90 + 00:54.60-01:08.80 + 02:04.20-02:18.00 | 7.83 | 9 |
| 2 | partial | 0.38 | 00:00.00-00:06.60 + 00:37.20-00:44.80 + 01:09.30-01:16.50 | 00:00.00-00:12.00 + 00:47.60-00:56.70 + 01:09.30-01:16.50 | 8.00 | 8 |
| 3 | agree | 0.62 | 01:00.00-01:04.50 + 01:06.00-01:28.10 + 02:12.70-02:25.75 | 00:58.20-01:25.50 + 01:56.00-02:25.75 | 8.83 | 9 |
| 4 | partial | 0.15 | 00:03.20-00:55.80 | 00:03.20-00:15.00 + 01:50.00-02:14.80 | 8.17 | 7 |
| 5 | agree | 0.76 | 00:54.00-01:04.60 + 01:31.00-01:41.50 | 00:51.80-01:09.00 + 01:31.00-01:41.50 | 8.33 | 8 |
| 6 | partial | 0.18 | 00:07.20-00:33.70 | 00:24.00-01:01.30 | 6.17 | 4 |
| 7 | agree | 0.59 | 01:05.20-01:28.50 | 00:50.80-01:30.00 | 7.67 | 7 |
| 8 | partial | 0.17 | 00:00.00-00:39.60 | 00:30.10-00:51.30 + 01:00.20-01:04.30 | 4.17 | 5 |
| 9 | matches runner-up | 0.00 | 00:00.00-00:15.20 + 00:58.50-01:14.80 | 01:14.80-01:55.50 | 7.67 | 6 |
| 10 | partial | 0.49 | 00:02.10-00:09.10 + 00:33.20-00:39.20 + 01:11.50-01:34.00 | 00:02.10-00:11.50 + 00:23.00-00:39.20 + 01:03.00-01:26.50 | 7.00 | 7 |
| 11 | agree | 0.52 | 01:26.00-01:52.75 | 00:16.80-00:27.00 + 00:54.00-01:03.80 + 01:21.30-01:52.75 | 7.50 | 8 |
| 12 | partial | 0.32 | 00:13.90-01:09.50 | 00:00.00-00:09.10 + 00:43.70-01:24.70 | 8.50 | 9 |
| 13 | agree | 0.59 | 00:05.10-00:17.30 + 00:54.00-01:20.50 + 01:43.00-01:58.88 | 00:04.20-00:18.80 + 00:53.50-01:29.00 | 7.67 | 9 |
| 14 | partial | 0.43 | 00:05.60-00:40.50 | 00:05.60-00:29.50 + 00:47.00-00:55.50 + 01:16.00-01:27.63 | 7.33 | 6 |
| 15 | agree | 0.71 | 00:47.40-01:26.00 | 00:03.50-00:15.80 + 00:44.20-01:26.00 | 8.00 | 8 |
| 16 | agree | 0.75 | 00:02.10-00:21.80 + 00:40.80-00:55.20 | 00:00.00-00:31.00 + 00:40.80-00:55.20 | 7.33 | 8 |
| 17 | different | 0.00 | 00:39.00-01:02.20 | 00:21.00-00:36.50 + 01:27.50-01:52.00 | 7.00 | 4 |
| 18 | partial | 0.16 | 01:13.50-01:55.50 | 00:00.00-00:09.50 + 00:20.10-00:28.90 + 00:52.50-01:26.50 | 8.17 | 9 |
| 19 | different | 0.00 | 00:00.00-00:04.50 + 01:29.50-01:59.63 | 00:43.00-00:49.20 + 01:10.60-01:29.50 | 6.17 | 7 |
| 20 | partial | 0.12 | 01:06.70-01:28.20 | 00:21.30-00:42.50 + 01:21.00-01:28.20 + 01:39.20-01:54.75 | 7.50 | 6 |
| 21 | partial | 0.43 | 00:03.50-00:35.80 + 01:39.20-01:54.00 | 00:03.50-00:15.00 + 01:10.50-01:16.00 + 01:31.00-01:54.00 | 8.00 | 6 |
| 22 | partial | 0.17 | 01:04.20-01:21.80 + 02:00.80-02:11.00 | 00:06.50-00:14.20 + 00:36.20-00:42.50 + 01:42.00-02:11.00 | 7.67 | 7 |
| 23 | agree | 0.64 | 01:26.00-02:11.50 | 01:18.50-01:40.50 + 01:52.20-02:11.50 | 8.00 | 8 |
| 24 | partial | 0.35 | 00:57.80-01:32.00 | 00:26.80-00:48.50 + 00:57.80-01:03.80 + 01:18.50-01:32.00 | 8.00 | 8 |
| 25 | agree | 0.60 | 00:18.80-01:08.50 | 00:18.80-00:38.50 + 00:46.80-01:03.50 + 01:19.50-01:30.20 | 8.17 | 6 |
| 26 | agree | 0.64 | 00:55.80-01:02.50 + 01:30.20-02:00.88 | 00:55.80-01:07.00 + 01:13.80-02:00.88 | 8.00 | 8 |
| 27 | matches runner-up | 0.00 | 02:02.80-02:30.50 | 00:00.00-00:51.50 | 8.00 | 8 |
| 28 | partial | 0.20 | 00:34.90-00:48.00 + 02:02.00-02:18.50 | 01:10.50-01:22.30 + 01:31.00-01:56.40 + 02:04.90-02:18.50 | 8.00 | 8 |
| 29 | agree | 0.59 | 00:37.70-01:14.30 + 01:36.10-01:56.69 | 00:37.40-01:18.50 | 8.17 | 7 |
| 30 | matches runner-up | 0.00 | 00:08.80-00:47.60 | 01:23.20-01:41.90 + 02:00.00-02:31.21 | 8.00 | 6 |
| 31 | agree | 0.57 | 00:04.20-00:13.80 + 02:10.80-02:40.00 | 01:58.20-02:40.00 | 7.83 | 9 |
| 32 | agree | 0.52 | 01:59.50-02:34.38 | 00:16.00-00:36.40 + 02:05.40-02:34.38 | 7.67 | 8 |
| 33 | agree | 0.50 | 01:04.20-01:19.50 + 02:11.80-02:24.80 | 01:04.20-01:19.50 + 02:03.50-02:44.50 | 8.00 | 7 |
| 34 | partial | 0.08 | 00:01.20-00:15.50 + 01:08.20-01:27.40 | 00:00.00-00:07.80 + 02:22.20-03:10.00 | 8.00 | 8 |
| 35 | agree | 0.54 | 00:37.00-00:55.50 + 02:02.00-02:30.50 | 00:36.50-01:06.00 + 02:14.00-02:37.50 | 8.17 | 8 |
| 36 | agree | 0.50 | 01:39.50-02:36.50 | 01:59.50-02:36.50 + 03:04.00-03:20.75 | 8.33 | 9 |
| 37 | partial | 0.40 | 01:36.00-01:56.50 | 00:18.80-00:34.50 + 01:35.50-01:56.50 + 02:21.50-02:36.47 | 8.50 | 7 |
| 38 | partial | 0.36 | 00:00.00-00:22.00 + 01:10.50-01:27.91 | 00:15.50-00:23.20 + 00:34.50-00:51.00 + 01:00.50-01:27.91 | 7.83 | 7 |
| 39 | agree | 0.53 | 00:32.40-01:08.50 + 01:25.20-01:38.41 | 00:46.80-01:38.41 | 8.00 | 8 |
| 40 | partial | 0.12 | 00:23.00-00:34.20 + 00:55.80-01:17.40 | 01:09.50-01:50.08 | 7.83 | 5 |
| 41 | agree | 0.67 | 00:04.90-00:26.00 + 01:21.00-01:36.09 | 00:08.50-00:28.80 + 00:57.80-01:04.00 + 01:17.50-01:36.09 | 8.50 | 9 |
| 42 | agree | 0.51 | 00:17.90-00:39.90 | 00:10.50-00:39.90 + 01:04.00-01:17.80 | 8.17 | 8 |
| 43 | partial | 0.35 | 01:08.80-01:54.96 | 00:10.50-00:21.80 + 00:57.00-01:11.30 + 01:33.20-01:54.96 | 8.83 | 8 |
| 44 | agree | 0.82 | 00:14.00-01:10.50 | 00:24.40-01:10.50 | 8.67 | 8 |
| 45 | agree | 0.60 | 01:26.50-02:01.75 | 00:09.90-00:27.40 + 01:14.50-01:20.50 + 01:26.50-02:01.75 | 8.17 | 9 |
| 46 | partial | 0.18 | 00:11.00-00:17.20 + 01:41.80-02:04.00 | 01:05.80-01:25.80 + 01:51.80-02:23.88 | 8.67 | 7 |
| 47 | agree | 0.60 | 00:56.80-01:23.50 | 00:56.80-01:41.20 | 8.33 | 8 |
| 48 | partial | 0.30 | 00:34.00-01:13.50 | 00:00.00-00:26.70 + 00:51.50-01:20.00 | 7.67 | 5 |
| 49 | agree | 0.61 | 01:44.20-02:14.50 | 00:33.20-00:41.80 + 01:43.80-02:24.75 | 7.83 | 5 |
| 50 | agree | 0.57 | 00:16.80-00:35.80 + 01:10.50-01:20.00 | 00:00.00-00:35.80 + 01:05.50-01:20.00 | 8.00 | 7 |

## Biggest disagreements

**Episode 9** (matches runner-up, IoU 0.00)
- Tool: 00:00.00-00:15.20 + 00:58.50-01:14.80: "The Midnight Knock". Hook: Heavy, frantic pounding echoes against the heavy wooden cottage door. Cliffhanger: I will tell the village what you did. They will never forget you.
- Reference: 01:14.80-01:55.50. Hook: Alexander, turning from the door after the grateful mother leaves: "You cannot let the whole village start talking about you." (+0.30 s) Cliffhanger: In a fire-lit study, Gerald reports a scarred veteran who "resembles the late Duke"; the lord snaps "Where?", then alone whispers "Impossible." Extreme close-up of his eye. Open question: is the "beggar" husband the dead Duke?

**Episode 17** (different, IoU 0.00)
- Tool: 00:39.00-01:02.20: "Of Losing You". Hook: Medium shot in the warm firelight as Juliana tenderly tends to the fresh cuts on Alexander's hand. Cliffhanger: Of losing you.
- Reference: 00:21.00-00:36.50 + 01:27.50-01:52.00. Hook: Alexander, mid-repair in the wrecked garden: "I would do it again." (+0.50 s), then, kneeling: "As long as I draw breath..." "...no one will hurt you again." Cliffhanger: By the fire she teases that she will "save you from the birds" (his beard). He catches her wrist: "Not yet." Her V.O.: "I know almost nothing about the man I married." Open question: who is he?

**Episode 19** (different, IoU 0.00)
- Tool: 00:00.00-00:04.50 + 01:29.50-01:59.63: "We Have Lost Everything". Hook: "This was our home." Cliffhanger: Slow cinematic push-in on the couple nestled together in the warm lantern glow. Alexander wraps his arm firmly around Juliana as she closes her eyes in exhausted relief, while his piercing gaze stares resolutely into the darkness, determined to reclaim everything that was stolen.
- Reference: 00:43.00-00:49.20 + 01:10.60-01:29.50. Hook: A scarred man steps out of the fog and bows to the "beggar" husband: "Your Grace." (+1.30 s) Cliffhanger: "My mother is a prisoner in her own house." / "And everyone believes you are dead." / "Then let them believe it a little longer." ... "Then Ashburg will remember who it belongs to." Open question: when will the "dead" Duke strike back?

**Episode 27** (matches runner-up, IoU 0.00)
- Tool: 02:02.80-02:30.50: "Framed For Murder". Hook: Medium shot of Lady Catherine turning abruptly to the guard stationed by the open door, pointing with feigned outrage. Cliffhanger: Extreme close-up of Juliana's wide, terrified eyes as she realizes the deadly trap closing around her, cutting abruptly to black.
- Reference: 00:00.00-00:51.50. Hook: Dowager Duchess, gripping Juliana's hand: "This ring..." (+1.3 s), then 'Who gave this to you?' (+3.4 s) Cliffhanger: "What is your husband's name?" Violent pounding, and the doors burst open on the Blond Nobleman, Lady Catherine and a guard. Will she say his name, and what do they want?

**Episode 30** (matches runner-up, IoU 0.00)
- Tool: 00:08.80-00:47.60: "A Rat in the Cellar". Hook: "You have a rat in your cellar, Rupert. And the servants are beginning to smell it." Cliffhanger: "We stop hiding the prisoner."
- Reference: 01:23.20-01:41.90 + 02:00.00-02:31.21. Hook: Catherine: "And if she claims she is a healer?" / Elder Nobleman: "Then call it witchcraft." (+0.0 s / +2.6 s) Cliffhanger: "Tomorrow, she stops being a prisoner. She becomes a witch." Cut to Juliana chained in the dark, looking up at the grate. Can she survive a rigged trial?

**Episode 34** (partial, IoU 0.08)
- Tool: 00:01.20-00:15.50 + 01:08.20-01:27.40: "The False Accusation". Hook: Lady Juliana Ashcroft, you are accused of witchcraft, unlawful healing, and poisoning. Cliffhanger: It was not a ritual!
- Reference: 00:00.00-00:07.80 + 02:22.20-03:10.00. Hook: Judge: "Lady Juliana Ashcroft, you are accused of witchcraft, unlawful healing, and poisoning." (+1.2 s) Cliffhanger: Gavel and "Enough!" The judge rises ("Lady Juliana Ashcroft...") and raises his hand to sentence her; fade out. What is the verdict?

**Episode 40** (partial, IoU 0.12)
- Tool: 00:23.00-00:34.20 + 00:55.80-01:17.40: "The Execution of the Witch". Hook: Imagine Juliana seeing this. Cliffhanger: And its witch will be dead.
- Reference: 01:09.50-01:50.08. Hook: Elder Nobleman, on the balcony: "By sunset, Ashburgh will have its new Duke and Duchess." (+0.3 s), with 'And its witch will be dead.' landing at +5.3 s Cliffhanger: At the altar Catherine purrs: "And you look better in silk than you ever did as an ignored cousin." Conspiratorial smiles as the organ holds. Will they get away with it?

**Episode 20** (partial, IoU 0.12)
- Tool: 01:06.70-01:28.20: "The Fallen Healer's Fight". Hook: If I stop, Seamus, the lung fever in the valley wins. Cliffhanger: And I am not finished.
- Reference: 00:21.30-00:42.50 + 01:21.00-01:28.20 + 01:39.20-01:54.75. Hook: Rupert over tea: "Once my cousin Alexander's death is formally sealed by the Crown..." (+0.00 s) "...the title is mine." Cliffhanger: Catherine: "Once the old Duchess is gone..." "...Ashbury will finally belong to us." "This house will only bow to me." Icy profile hold as the strings swell. Open question: can anyone stop them before the Duchess dies?

**Episode 4** (partial, IoU 0.15)
- Tool: 00:03.20-00:55.80: "A Penniless Nobody". Hook: Look at him. Cliffhanger: You don't have to stand alone now.
- Reference: 00:03.20-00:15.00 + 01:50.00-02:14.80. Hook: Gerald sneers at the kneeling stranger: "Look at him." "A penniless nobody for a discarded bride." (+1.80 s); Clarissa bursts out laughing. Cliffhanger: Seconds after "husband and wife!", Gerald rages "You have thrown yourself away!" "For a penniless nobody!", Juliana cuts him down, and her stepmother screams "You are disowned!" Cut. Open question: she has given up everything for a stranger; who is he really?

**Episode 18** (partial, IoU 0.16)
- Tool: 01:13.50-01:55.50: "The Burning Ledger". Hook: Alexander roaring in terror as the ceiling beam collapses. Cliffhanger: Alexander smashing through the burning window frame with Juliana in his arms.
- Reference: 00:00.00-00:09.50 + 00:20.10-00:28.90 + 00:52.50-01:26.50. Hook: Flames lick under a bedroom door as smoke pours in (+0.00 s); Juliana wakes coughing and screams "Alexander!" Cliffhanger: Clutching the scorched ledger, she looks up as a burning rafter splits directly above her and screams "Alexander!" Cut before the beam falls. Open question: will he reach her in time?

