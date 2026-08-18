# FPL specialist evidence policy — 2026-08-18

## Purpose

Add Fantasy Football Scout and AllAboutFPL as independent FPL-specialist corroboration sources and Fabrizio Romano as transfer-specialist intelligence, without allowing editorial reporting to silently become canonical data or direct expected-points input.

## Source hierarchy

1. Official FPL remains canonical for player identity, club, position, price, status/chance and fixtures.
2. Official club / official league evidence remains authoritative for material availability and verified deadline-specific role evidence.
3. Existing quantitative experts such as AIrsenal remain independent projection comparators under their governed contracts.
4. Fantasy Football Scout and AllAboutFPL use the `fpl_specialist` tier. They are corroboration and anomaly-detection sources, not projection authorities.
5. Fabrizio Romano uses the `transfer_specialist` tier. His reporting is used for transfer-risk detection and escalation only; official club/FPL confirmation remains authoritative for canonical state.

## What specialist evidence may do

FPL-specialist evidence may trigger review flags for:

- predicted-XI disagreement;
- expected-minutes / start-probability disagreement;
- tactical-role disagreement;
- penalty, corner and free-kick role disagreement;
- preseason participation or role observations;
- injury / return interpretation that should be checked against an official source;
- unusually strong or weak FPL community/model consensus around an Apex outlier.

Transfer-specialist evidence may trigger review flags for:

- reported club-to-club agreements;
- `Here we go` / agreement-level reports;
- medicals booked or underway;
- advanced negotiations or a player being set to leave;
- exploratory interest where a selected or optimiser-sensitive player could become deadline risk.

A specialist flag is particularly important when Apex is optimiser-sensitive: selected in the canonical XV, close to the selection boundary, captaincy relevant, or materially divergent from Official FPL / AIrsenal.

## What specialist evidence must not do

Neither `fpl_specialist` nor `transfer_specialist` evidence may directly override:

- canonical player identity, club, position or price;
- official availability/status;
- expected minutes or start probability;
- tactical role multipliers;
- set-piece shares;
- raw or canonical xP;
- optimiser objective weights.

Material tactical/minutes overrides continue to require a source tier accepted by `src/apex_fpl/data/tactical.py`. Both specialist tiers are deliberately excluded from that allow-list and regression-tested.

## Disagreement and transfer-risk policy

When both FPL-specialist sources agree against Apex on a material selected-player assumption, Apex should raise an evidence-review flag. The analyst must seek current official club/league evidence or another high-quality source before changing a projection input. If no authoritative resolution exists, uncertainty should remain explicit; specialist consensus alone must not be converted into a hidden xP adjustment.

When the two FPL-specialist sources disagree with each other, record the disagreement rather than averaging it into a pseudo-probability.

For Fabrizio Romano, agreement/medical-level reporting on a selected or optimiser-sensitive player is a high-priority transfer review. Advanced reports are also escalated. Exploratory interest remains a lower-priority watch. In every case, official club/FPL confirmation is required before canonical club identity, availability, minutes or xP inputs are changed.

## Freshness

Lineup, injury, role, set-piece and transfer evidence is deadline-sensitive. Only evidence with a verifiable publication timestamp should be eligible for decision review. Index-page retrieval time is not publication time. Existing news collection already preserves this distinction.

## Configured sources

- Fantasy Football Scout — https://www.fantasyfootballscout.co.uk/ — `fpl_specialist`
- AllAboutFPL — https://allaboutfpl.com/ — `fpl_specialist`
- Fabrizio Romano official Telegram mirror — https://t.me/s/fabrizioromanotg — `transfer_specialist`

The official Romano channel links back to his verified public social accounts. The transfer source is intentionally kept separate from `trusted_media` so transfer reports cannot qualify as direct tactical/minutes overrides.

## Structured diagnostics

`src/apex_fpl/services/specialist_disagreement.py` emits the per-player FPL-specialist predicted-XI disagreement surface.

`src/apex_fpl/services/transfer_intelligence.py` classifies transfer-specialist signals into exploratory, advanced and agreement/medical states. The classifier emits review priority and always requires official confirmation for recognised transfer-specialist evidence; it does not mutate projection inputs.
