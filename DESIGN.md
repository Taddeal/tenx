# Design Document

## Audience
**Primary:** Friends and peers — young Ethiopian adults (20–30s) who understand both traditional values and modern moral questions. They watch content primarily on phones (vertical video) and share on social media.

**Secondary:** Family members who will appreciate the Amharic narration and the cultural setting. Diaspora Ethiopians who feel nostalgic for village life and family wisdom.

## Intent
By the end of this 60–90 second film, the audience should:
1. **Feel** the weight of choosing between two good values when they conflict
2. **Understand** that respecting elders and standing for truth are not contradictory — they can coexist
3. **Remember** the proverb: "አዛውንቶችን አክብር፤ እውነትን ግን አትካድ።"
4. **Share** the film because it articulates something they've felt but not expressed

## User Test 1: Radio / Rough Cut
**Date:** 2026-11-25  
**Method:** Shared the Phase 1/2 rough cut (`radio_cut.mp4` / `film_16x9.mp4`) with 3 friends from the target audience  
**Participants:**
1. Friend 1 (Ethiopian peer, Addis Ababa) — target audience
2. Friend 2 (Ethiopian peer, Addis Ababa) — target audience
3. Friend 3 (Ethiopian peer, Addis Ababa) — target audience

**Feedback received:**
- **Duration:** All noticed the cut ran too long (`107.6s`, exceeding the 60–90s target) and felt slightly drawn out in the middle (Shots 6 and 9).
- **Personal connection:** Describing the protagonist generically as "the young man" (`ወጣቱ`) felt like an abstract parable rather than a personal family story.
- **Amharic pronunciation / accent:** A few formal or compound words in the Gemini TTS lines sounded slightly stiff or carried unnatural stress/accent (`ወጣቱ`, `የአንድ የተከበረ ሽማግሌ`, `ክብር መንሳት`).

**Changes made because of feedback:**
- **Named the protagonist Addisu (`አዲሱ`)** across `storyboard.json` narration, subtitles, and character sheet so the story feels personal and grounded.
- **Shortened verbose lines & removed `"unhurried"`** from `narration.style` (`"warm, clear, natural Ethiopian storytelling"`), plus turned Shot 8 (the stand-up) into a `3.5s` silent dramatic visual pause — dropping total runtime below 90s while fitting inside the 10-call daily TTS free tier.
- **Rewrote awkward Amharic phrases** into natural spoken Ethiopian Amharic (e.g., `"ሽማግሌውም አዲሱን፣ እባክህ ዝም በል አሉት።"` using respectful plural `"አሉት"` instead of `"ለመነው"`, and `"ማክበር ማለት ስህተትን መደበቅ አይደለም።"`).

## User Test 2: Near-Final Cut
**Date:** [TO BE FILLED]  
**Method:** Showed the near-final film with visuals, narration, and score  
**Participants:**
1. [Name/description]
2. [Name/description]
3. [Name/description]

**Feedback received:**
- [What they said]
- [What worked]
- [What didn't work]

**Changes made because of feedback:**
- [What we changed]

## Shot Reasons
Every shot has a stated purpose:

| Shot | Scene | Reason |
|------|-------|--------|
| 1 | Father's Advice | Establishes the peaceful setting and the father–Addisu bond that drives the entire story |
| 2 | Father's Advice | Delivers the two core teachings directly — the audience must hear and feel their weight |
| 3 | Years Later | Time transition — shows Addisu has grown while his father's teachings remain with him |
| 4 | The Gathering | Sets up the conflict — the family gathering where everything changes |
| 5 | The Accusation | Shows the injustice — creates empathy for the accused and urgency for Addisu to act |
| 6 | Elder's Plea | Humanizes the elder — he is not evil, just afraid. This is where Addisu's dilemma crystallizes |
| 7 | Internal Struggle | The emotional core — the audience feels the weight of Addisu's dilemma before his decision |
| 8 | The Decision | A `3.5s` silent visual pause (`music/room tone only`) — lets a simple physical action carry enormous moral weight |
| 9 | Speaking Truth | The resolution of the dilemma — Addisu finds a way to honor both teachings simultaneously |
| 10 | Resolution | Shows the positive outcome — justice served, the community healed |
| 11 | The Lesson | The moral synthesis — ties opening and closing together beneath the acacia tree |
| 12 | End Card | Delivers the final proverb (`"አዛውንቶችን አክብር፤ እውነትን ግን አትካድ።"`) and `"This film was made with AI"` disclosure |
