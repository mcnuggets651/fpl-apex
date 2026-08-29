import { useEffect, useMemo, useState } from "react";

import type {
  CommandCenterClassicV1,
  EvidenceRowV1,
  OfficialPlayerV1,
  ProjectionRowV1,
} from "../shared/contract";
import { ApexApiError, fetchClassicLatest } from "./api";
import {
  actionLabel,
  actionReason,
  certificationWarnings,
  fixtureLabel,
  isActionCurrent,
  percent,
  playerMap,
  price,
  projectedXiScore,
  projectionMap,
  teamName,
  visiblePlan,
} from "./model";

const NAV = ["HOME", "MY TEAM", "PLAYERS", "PLAN", "REVIEW"] as const;
type Section = (typeof NAV)[number];

type PlayerRow = {
  player: OfficialPlayerV1;
  projection: ProjectionRowV1 | undefined;
};

function formatXp(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(1);
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function StatusPill({ data }: { data: CommandCenterClassicV1 }) {
  const state = data.public_attempt.certification.state;
  const live = isActionCurrent(data);
  const label = live ? "READY" : state;
  return <span className={`status-pill status-${live ? "ready" : state.toLowerCase()}`}>{label}</span>;
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {sub ? <small>{sub}</small> : null}
    </div>
  );
}

function PlayerName({ data, id }: { data: CommandCenterClassicV1; id: number }) {
  const player = playerMap(data).get(id);
  return <>{player?.web_name ?? `Player #${id}`}</>;
}

function Home({ data }: { data: CommandCenterClassicV1 }) {
  const players = useMemo(() => playerMap(data), [data]);
  const h1 = useMemo(() => projectionMap(data, 1), [data]);
  const decision = data.manager?.system_decision ?? null;
  const active = isActionCurrent(data);
  const score = decision ? projectedXiScore(decision, h1) : null;
  const team = data.manager?.team_state;
  const action = actionLabel(decision, players);
  const warnings = certificationWarnings(data);

  return (
    <main className="page-stack">
      <section className={`hero-card ${active ? "hero-ready" : "hero-blocked"}`}>
        <div className="hero-topline">
          <StatusPill data={data} />
          <span>GW{data.public_attempt.target_gameweek}</span>
        </div>
        {active ? (
          <>
            <p className="eyebrow">Apex recommends</p>
            <h1>{action}</h1>
            <p className="hero-copy">{actionReason(decision, data)}</p>
          </>
        ) : (
          <>
            <p className="eyebrow">Canonical action withheld</p>
            <h1>Apex recommendation temporarily unavailable</h1>
            <p className="hero-copy">
              {data.capabilities.reason ?? "A current personalized action did not pass the full production gate."}
            </p>
          </>
        )}
      </section>

      <section className="metric-grid">
        <Metric
          label="Projected XI"
          value={score === null ? "—" : `${score.toFixed(1)} pts`}
          sub="H1 serving xP + captain, before autosub contingency"
        />
        <Metric
          label="Free transfers"
          value={team ? String(team.free_transfers) : "—"}
          sub={team ? "Exact private manager state" : "Private state unavailable"}
        />
        <Metric label="Bank" value={team ? price(team.bank_tenths) : "—"} />
        <Metric
          label="Qualified horizon"
          value={`H${data.public_attempt.max_contiguous_qualified_horizon}`}
          sub="No plan is shown beyond this"
        />
      </section>

      <section className="two-column">
        <article className="panel">
          <header className="panel-header">
            <div>
              <p className="eyebrow">This gameweek</p>
              <h2>Execution</h2>
            </div>
            <span className="muted">Deadline {formatDate(data.public_attempt.certification.valid_until)}</span>
          </header>
          {decision ? (
            <div className="execution-grid">
              <div>
                <span className="label">Captain</span>
                <strong><PlayerName data={data} id={decision.captain_id} /></strong>
              </div>
              <div>
                <span className="label">Vice</span>
                <strong><PlayerName data={data} id={decision.vice_captain_id} /></strong>
              </div>
              <div>
                <span className="label">Hits</span>
                <strong>{decision.transfer_hits ? `-${decision.transfer_hits * 4}` : "0"}</strong>
              </div>
              <div>
                <span className="label">Mode</span>
                <strong>{decision.decision_mode.replaceAll("_", " ")}</strong>
              </div>
            </div>
          ) : (
            <p className="empty-state">No personalized SystemDecision is exposed for this run.</p>
          )}
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <p className="eyebrow">Serving authority</p>
              <h2>Why this is trusted</h2>
            </div>
          </header>
          <div className="trust-list">
            <div><span>Certification</span><strong>{data.public_attempt.certification.state}</strong></div>
            {warnings.length ? <div><span>Degraded because</span><strong>{warnings.join(" · ")}</strong></div> : null}
            <div><span>Serving H1</span><strong>{data.public_attempt.serving_provider_by_horizon["1"] ?? "—"}</strong></div>
            <div><span>Immutable public release</span><strong>{data.public_release.immutable ? "Verified" : "No"}</strong></div>
            <div><span>Private identity</span><strong>{data.manager?.proof.public_identity_match ? "Verified" : "Unavailable"}</strong></div>
            <div><span>Private commitment</span><strong>{data.manager?.proof.commitment_verified ? "Verified" : "Unavailable"}</strong></div>
          </div>
        </article>
      </section>

      <section className="panel">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Current evidence</p>
            <h2>What Apex knows</h2>
          </div>
          <span className="muted">Research context does not override serving xP</span>
        </header>
        <EvidenceFeed rows={data.evidence.rows.slice(0, 8)} data={data} />
      </section>
    </main>
  );
}

function Team({ data }: { data: CommandCenterClassicV1 }) {
  const team = data.manager?.team_state;
  const decision = data.manager?.system_decision;
  const players = useMemo(() => playerMap(data), [data]);
  const h1 = useMemo(() => projectionMap(data, 1), [data]);
  if (!team) {
    return (
      <main className="page-stack">
        <section className="panel empty-large">
          <h1>My Team is private</h1>
          <p>Connect through the protected Apex private manager store to view current pre-deadline squad, exact selling prices, bank and free transfers. Public deadline snapshots are not substituted.</p>
        </section>
      </main>
    );
  }

  const bench = new Set(decision?.bench_order ?? []);
  const xi = new Set(decision?.xi_ids ?? []);
  const sorted = [...team.squad_ids].sort((a, b) => {
    const pa = players.get(a);
    const pb = players.get(b);
    const order = { GK: 0, DEF: 1, MID: 2, FWD: 3 } as const;
    return (pa ? order[pa.position] : 9) - (pb ? order[pb.position] : 9);
  });

  return (
    <main className="page-stack">
      <section className="section-heading">
        <div>
          <p className="eyebrow">Exact private manager state</p>
          <h1>My Team</h1>
        </div>
        <div className="heading-stats">
          <span>{team.free_transfers} FT</span>
          <span>{price(team.bank_tenths)} bank</span>
        </div>
      </section>
      <section className="panel table-panel">
        <div className="responsive-table">
          <table>
            <thead>
              <tr><th>Player</th><th>Role</th><th>Club</th><th>Sell</th><th>Price</th><th>H1 xP</th><th>Start</th><th>Fixture</th></tr>
            </thead>
            <tbody>
              {sorted.map((id) => {
                const p = players.get(id);
                if (!p) return null;
                const row = h1.get(id);
                const role = id === decision?.captain_id ? "C" : id === decision?.vice_captain_id ? "VC" : xi.has(id) ? "XI" : bench.has(id) ? "BENCH" : "SQUAD";
                return (
                  <tr key={id}>
                    <td><strong>{p.web_name}</strong><small>{p.position}</small></td>
                    <td><span className={`role role-${role.toLowerCase()}`}>{role}</span></td>
                    <td>{teamName(data, p.team_id)}</td>
                    <td>{price(team.selling_prices_tenths[String(id)])}</td>
                    <td>{price(p.price_tenths)}</td>
                    <td>{formatXp(row?.expected_points)}</td>
                    <td>{percent(row?.p_start)}</td>
                    <td>{row ? fixtureLabel(data, row.fixture_ids, p.team_id) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function EvidenceFeed({ rows, data }: { rows: EvidenceRowV1[]; data: CommandCenterClassicV1 }) {
  const players = playerMap(data);
  if (!rows.length) return <p className="empty-state">No current evidence records in this sealed run.</p>;
  return (
    <div className="evidence-list">
      {rows.map((row) => (
        <article key={row.evidence_id} className="evidence-item">
          <div>
            <strong>{players.get(row.element_id)?.web_name ?? `#${row.element_id}`}</strong>
            <span>{row.evidence_type.replaceAll("_", " ")} · {row.source_name}</span>
          </div>
          <p>{row.excerpt || "Evidence recorded without a public excerpt."}</p>
          <div className="evidence-meta">
            <span className={row.effect === "HARD_EXCLUDE" ? "danger-text" : "muted"}>{row.effect.replaceAll("_", " ")}</span>
            <span className="muted">Expires {formatDate(row.expires_at)}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function Players({ data }: { data: CommandCenterClassicV1 }) {
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState("ALL");
  const [horizon, setHorizon] = useState(1);
  const projections = useMemo(() => projectionMap(data, horizon), [data, horizon]);
  const rows: PlayerRow[] = useMemo(
    () =>
      data.canonical_forecast.official.players
        .map((player) => ({ player, projection: projections.get(player.element_id) }))
        .filter(({ player }) => position === "ALL" || player.position === position)
        .filter(({ player }) => player.web_name.toLowerCase().includes(query.toLowerCase().trim()))
        .sort((a, b) => (b.projection?.expected_points ?? -1) - (a.projection?.expected_points ?? -1)),
    [data, projections, position, query],
  );
  const evidenceByPlayer = useMemo(() => {
    const map = new Map<number, EvidenceRowV1[]>();
    for (const row of data.evidence.rows) map.set(row.element_id, [...(map.get(row.element_id) ?? []), row]);
    return map;
  }, [data]);

  return (
    <main className="page-stack">
      <section className="section-heading">
        <div><p className="eyebrow">Serving forecast</p><h1>Players</h1></div>
        <span className="muted">All identity and prices are from the same sealed Official snapshot</span>
      </section>
      <section className="filters panel">
        <input aria-label="Search players" placeholder="Search player" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select aria-label="Position" value={position} onChange={(event) => setPosition(event.target.value)}>
          {['ALL','GK','DEF','MID','FWD'].map((value) => <option key={value}>{value}</option>)}
        </select>
        <select aria-label="Horizon" value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
          {Array.from({ length: Math.max(1, data.public_attempt.max_contiguous_qualified_horizon) }, (_, i) => i + 1).map((value) => <option key={value} value={value}>H{value}</option>)}
        </select>
      </section>
      <section className="panel table-panel">
        <div className="responsive-table">
          <table>
            <thead><tr><th>Player</th><th>Club</th><th>Price</th><th>xP H{horizon}</th><th>xMin</th><th>Start</th><th>Appear</th><th>Fixture</th><th>Evidence</th></tr></thead>
            <tbody>
              {rows.map(({ player, projection }) => (
                <tr key={player.element_id}>
                  <td><strong>{player.web_name}</strong><small>{player.position} · {player.status}</small></td>
                  <td>{teamName(data, player.team_id)}</td>
                  <td>{price(player.price_tenths)}</td>
                  <td><strong>{formatXp(projection?.expected_points)}</strong></td>
                  <td>{projection?.expected_minutes === null || projection?.expected_minutes === undefined ? "—" : Math.round(projection.expected_minutes)}</td>
                  <td>{percent(projection?.p_start)}</td>
                  <td>{percent(projection?.p_appearance)}</td>
                  <td>{projection ? fixtureLabel(data, projection.fixture_ids, player.team_id) : "—"}</td>
                  <td>{evidenceByPlayer.get(player.element_id)?.length ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel research-panel">
        <header className="panel-header"><div><p className="eyebrow">Research / non-serving</p><h2>Evidence context</h2></div><span className="muted">These records can enforce hard eligibility rules but are not a second xP model.</span></header>
        <EvidenceFeed rows={data.evidence.rows} data={data} />
      </section>
    </main>
  );
}

function Plan({ data }: { data: CommandCenterClassicV1 }) {
  const plan = visiblePlan(data.manager?.transfer_plan ?? [], data.public_attempt.max_contiguous_qualified_horizon);
  const players = playerMap(data);
  return (
    <main className="page-stack">
      <section className="section-heading"><div><p className="eyebrow">Receding-horizon optimizer</p><h1>Plan</h1></div><span className="muted">Certified only through H{data.public_attempt.max_contiguous_qualified_horizon}</span></section>
      {!data.manager ? (
        <section className="panel empty-large"><h2>Private plan unavailable</h2><p>A personalized plan is never inferred from the public squad snapshot.</p></section>
      ) : plan.length === 0 ? (
        <section className="panel empty-large"><h2>No multi-gameweek plan published</h2><p>The optimizer withheld a transfer horizon or only H1 is qualified. Apex will not manufacture future moves.</p></section>
      ) : (
        <section className="timeline">
          {plan.map((week) => (
            <article className="plan-card" key={week.horizon}>
              <div className="plan-index">H{week.horizon}</div>
              <div className="plan-body">
                <div className="plan-heading"><div><span className="eyebrow">GW{week.gameweek}</span><h2>{week.transfers_in.length ? `${week.transfers_in.length} transfer${week.transfers_in.length === 1 ? "" : "s"}` : "ROLL"}</h2></div><strong>{week.submitted_ev.toFixed(1)} EV</strong></div>
                {week.transfers_in.length ? (
                  <div className="transfer-pairs">
                    {week.transfers_out.map((outId, index) => <div key={`${outId}-${week.transfers_in[index]}`}><span>{players.get(outId)?.web_name ?? `#${outId}`}</span><b>→</b><strong>{players.get(week.transfers_in[index])?.web_name ?? `#${week.transfers_in[index]}`}</strong></div>)}
                  </div>
                ) : <p className="muted">Bank the transfer under the current sealed forecast.</p>}
                <div className="plan-meta"><span>{week.free_transfers} FT entering</span><span>{price(week.bank_tenths)} bank after moves</span><span>{week.hits ? `-${week.hits * 4} hit` : "No hit"}</span></div>
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}

function Review({ data }: { data: CommandCenterClassicV1 }) {
  const metrics = data.review.metrics;
  const outcome = data.review.outcome;
  return (
    <main className="page-stack">
      <section className="section-heading"><div><p className="eyebrow">Prospective scoring</p><h1>Review</h1></div><span className="muted">Evaluation never auto-promotes a provider</span></section>
      {!metrics && !outcome ? (
        <section className="panel empty-large"><h2>Gameweek outcome not sealed yet</h2><p>Review appears only after Official FPL marks the target gameweek finished and Apex publishes immutable outcome/evaluation records.</p></section>
      ) : (
        <>
          <section className="two-column">
            <article className="panel"><p className="eyebrow">Outcome</p><h2>GW{String(outcome?.gameweek ?? data.public_attempt.target_gameweek)}</h2><p className="hero-copy">Official actual points/minutes are bound to this exact production run for no-hindsight evaluation.</p></article>
            <article className="panel"><p className="eyebrow">Governance</p><h2>No automatic promotion</h2><p className="hero-copy">{String(metrics?.note ?? "Provider results are evaluation evidence only.")}</p></article>
          </section>
          <section className="panel"><header className="panel-header"><div><p className="eyebrow">Provider metrics</p><h2>Prospective performance</h2></div></header><pre className="metrics-json">{JSON.stringify(metrics?.providers ?? {}, null, 2)}</pre></section>
        </>
      )}
    </main>
  );
}

function Shell({ data }: { data: CommandCenterClassicV1 }) {
  const [section, setSection] = useState<Section>("HOME");
  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => setSection("HOME")}><span className="brand-mark">A</span><span><strong>FPL APEX</strong><small>Command Center</small></span></button>
        <div className="top-status"><StatusPill data={data} /><span>GW{data.public_attempt.target_gameweek}</span></div>
      </header>
      <nav className="nav-tabs" aria-label="Primary navigation">
        {NAV.map((item) => <button key={item} className={section === item ? "active" : ""} onClick={() => setSection(item)}>{item}</button>)}
      </nav>
      <div className="content-wrap">
        {section === "HOME" ? <Home data={data} /> : null}
        {section === "MY TEAM" ? <Team data={data} /> : null}
        {section === "PLAYERS" ? <Players data={data} /> : null}
        {section === "PLAN" ? <Plan data={data} /> : null}
        {section === "REVIEW" ? <Review data={data} /> : null}
      </div>
      <footer><span>Sealed {formatDate(data.public_attempt.frozen_at)}</span><span>Provider {data.public_attempt.serving_provider_by_horizon["1"] ?? "—"}</span><span>Public attempt {data.public_attempt.public_attempt_id.slice(0, 10)}</span></footer>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<CommandCenterClassicV1 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    setRefreshing(true);
    try {
      const latest = await fetchClassicLatest();
      setData(latest);
      setError(null);
    } catch (failure) {
      setError(failure instanceof ApexApiError ? failure.message : "A current sealed Apex response is unavailable.");
      // Never substitute an older locally persisted action. Existing in-memory
      // data may remain visible only behind a disabled/offline overlay below.
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => { void load(); }, []);

  if (!data && !error) return <div className="loading-screen"><div className="spinner"/><strong>Verifying Apex</strong><span>Checking immutable production state…</span></div>;
  if (!data && error) return <div className="loading-screen error-screen"><span className="brand-mark">A</span><h1>Apex data unavailable</h1><p>{error}</p><button onClick={() => void load()}>Retry verification</button></div>;

  return (
    <>
      {data ? <Shell data={data} /> : null}
      {error && data ? <div className="offline-banner"><div><strong>Live verification failed</strong><span>{error} No cached action is considered current.</span></div><button disabled={refreshing} onClick={() => void load()}>{refreshing ? "Checking…" : "Retry"}</button></div> : null}
    </>
  );
}
