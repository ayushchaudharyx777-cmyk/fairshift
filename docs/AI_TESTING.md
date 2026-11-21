# AI in FairShift: where it is used and how to test it

FairShift uses **Gemini** in four places. Every one has an offline fallback, and the app now tells you honestly which one you got.

| # | Where | What Gemini does | Endpoint |
|---|---|---|---|
| 1 | Worker app > Safety tab (voice orb or typing) | Reads the hazard in any of 9 languages, picks category + severity, writes a one-line summary in English and in the worker's language | `POST /api/v1/worker/safety-reports` |
| 2 | Worker app > Safety tab > "Report with Photo" | Looks at the photo (Gemini Vision), finds the hazard, same output as above | `POST /api/v1/worker/hazard-photo` |
| 3 | Worker app > Payslip tab > "Explain in my language" | Explains the payslip in simple words in the chosen language | `POST /api/v1/worker/payslip/explain` |
| 4 | Payslip tab > "Listen" | Gemini text-to-speech, used when the phone/PC has no voice for that language | `POST /api/v1/worker/speak` |

## Step 0: make sure the key is really working (do this first)
1. Render > your service > **Environment** > `GEMINI_API_KEY` must be set (get a free key from Google AI Studio). Redeploy.
2. Open **/admin** (PIN 4821). The **🤖 Gemini AI Status** card shows `AI: Gemini configured ✓` or `AI: NOT CONFIGURED`.
3. Press **Test AI now**. You want `AI: LIVE ✓ <ms>`. If it says FAILED, the exact reason is shown (wrong key, quota, model name).

## Step 1: test each feature (worker app, login 9876543210 / 1234)
| Test | What to do | Expected |
|---|---|---|
| Typed hazard (English) | Safety tab > type `Scaffolding clamp is loose on 4th floor near the edge` > Submit | Category HAZARD, severity HIGH or CRITICAL, English summary |
| Typed hazard (Hindi) | Pick हिंदी > type `चौथी मंज़िल पर बिजली का तार खुला है` | Summary shown in Hindi, severity HIGH/CRITICAL |
| Mixed language | Type `bhai yaha pe paani bhara hai aur current ka board hai` | Understood as electrical + water hazard, critical |
| Voice | Tap the orb, say a hazard in the selected language (Chrome/Brave, allow microphone) | Text appears, then submit as above |
| Photo | Safety tab > Report with Photo > pick a real site photo (no helmet, loose scaffold) | Category and severity from the picture |
| Payslip | Payslip tab > Explain in my language, then change language | New explanation in the new language automatically |
| Voice playback | Press Listen | Plays in the chosen language (device voice, or Gemini voice if the device has none) |

## How to read the result
* Payslip box badge: `🤖 Gemini Decent-Work Assistant` means a live model answered; `📴 Offline template` means Gemini was not reachable and a built-in template was used.
* Safety cards created by Gemini or the fallback are stored with `ai_source` (`gemini`, `fallback`, `manual` for seed data).
* Failed Gemini calls are **not cached**, so the next try can succeed.

## Tell the judges
"Gemini triages hazards from voice, text and photos in 9 Indian languages, explains pay in the worker's language and speaks it back. If AI is down, a labelled offline template keeps the app working, and every report is hash-chained so it cannot be edited quietly."
