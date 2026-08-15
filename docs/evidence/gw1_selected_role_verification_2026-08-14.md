# GW1 selected-player role verification — 2026-08-14

Scope: Ben Davies (508), Sean Neave (466), Djordje Petrovic (57), Cody Gakpo (367), Enzo Fernandez (155), Malick Thiaw (445).

Decision rule: only current official-club/league evidence may create a tactical/minutes override. Absence of evidence is not converted into a negative override. A single preseason cameo is not used to hand-tune expected minutes.

## Decision-grade rows added to `data/manual/tactical_roles.csv`

- **Ben Davies (508): evidence only, no minutes override.** Tottenham's official Auckland report shows Davies introduced on 62 minutes. This confirms current senior-squad involvement but is insufficient by itself to infer a new Premier League start probability.
- **Sean Neave (466): minutes/start override.** Newcastle's official Darlington report says the second-half XI was largely U21 players and names Neave in that XI. The evidence supports first-team fringe status, not the production surface's prior 0.613 Premier League start probability. Override: 25 expected minutes, 0.25 start probability, 0.55 appearance probability through the GW1 evidence window.
- **Cody Gakpo (367): evidence only, no minutes override.** Liverpool officially recorded his first preseason training day on 28 July after World Cup rest. The existing model already prices reduced minutes; no stronger penalty is justified without a current official XI.

## Checked but not overridden

- **Djordje Petrovic (57):** Bournemouth official evidence from late 2025/26 confirms he was the established starter, but no sufficiently current 2026/27 official lineup/manager statement was found in this verification pass. Keep the model estimate; do not fabricate a competition penalty.
- **Enzo Fernandez (155):** Chelsea confirms he was at the 2026 World Cup and he was absent from the initial 2026 preseason travelling group, with other first-team players expected to report later. That establishes delayed preseason timing but not a defensible exact GW1 minutes override without a subsequent current official training/lineup statement.
- **Malick Thiaw (445):** Newcastle's official profile describes a solid 2025/26 first season and World Cup involvement. Historical 2025/26 usage was strong, but no current post-World-Cup official preseason XI was found in this pass. Keep the model estimate pending current team evidence.

## Sources

- Tottenham Hotspur, Auckland FC 0-2 Spurs, 26 July 2026: https://www.tottenhamhotspur.com/news/1080047/scarlett-and-richarlison-secure-victory-at-eden-park
- Newcastle United, Newcastle United 3 Darlington 0, August 2026: https://www.newcastleunited.com/en/news/darlington-h-friendly-report-26-27
- Liverpool FC, Gakpo and Van Dijk begin preseason, 28 July 2026: https://www.liverpoolfc.com/news/photos-cody-gakpo-and-virgil-van-dijk-begin-pre-season-axa-training-centre
- Chelsea FC, confirmed 2026 preseason travelling squad: https://www.chelseafc.com/en/news/article/confirmed-chelsea-travelling-squad-for-2026-pre-season-tour
- Chelsea FC, 2026 World Cup call-ups: https://www.chelseafc.com/en/news/article/chelseas-2026-world-cup-call-ups-and-schedules
- Newcastle United, Malick Thiaw profile: https://www.newcastleunited.com/en/teams/mens-team/malick-thiaw-profile
