type ReviewCard = {
  title: string;
  description: string;
  items: string[];
};

const reviewCards: ReviewCard[] = [
  {
    title: "Ingest Snapshot",
    description: "Confirm the local project inputs before review starts.",
    items: [
      "Project folder and source footage",
      "Transcript and segment extraction status",
      "Preview render target for local playback",
    ],
  },
  {
    title: "Segment Review",
    description: "Inspect the draft cut and focus on segments that need operator judgment.",
    items: [
      "Keep or trim talking-head moments",
      "Check ambiguous cuts before auto-removal",
      "Review confidence notes attached to each segment",
    ],
  },
  {
    title: "Replacement Queue",
    description: "Evaluate candidate swaps instead of applying them silently.",
    items: [
      "B-roll recommendations",
      "Music cue suggestions",
      "Limited TTS alternatives that require approval",
    ],
  },
  {
    title: "Review Flags",
    description: "Surface issues that block export until they are resolved locally.",
    items: [
      "Low-confidence transcript spans",
      "Missing asset references",
      "Preview and export warnings",
    ],
  },
];

export function App() {
  return (
    <div className="app-shell">
      <header className="hero">
        <p className="eyebrow">Local-first operator shell</p>
        <h1>VideoBox Review Dashboard</h1>
        <p className="hero-copy">
          A thin review UI for validating draft edits, candidate replacements,
          and export blockers before the local preview is approved.
        </p>
      </header>

      <main className="dashboard" aria-label="Review dashboard sections">
        <section className="status-panel" aria-labelledby="status-heading">
          <div>
            <p className="section-label">Current flow</p>
            <h2 id="status-heading">Review pipeline</h2>
          </div>
          <div className="status-grid">
            <div className="status-item">
              <span className="status-name">Ingest</span>
              <strong>Ready for review</strong>
            </div>
            <div className="status-item">
              <span className="status-name">Preview</span>
              <strong>Local render pending</strong>
            </div>
            <div className="status-item">
              <span className="status-name">Export gate</span>
              <strong>Wait for operator approval</strong>
            </div>
          </div>
        </section>

        <section aria-labelledby="workspace-heading">
          <div className="section-heading">
            <p className="section-label">Workspace</p>
            <h2 id="workspace-heading">Review areas</h2>
          </div>
          <div className="card-grid">
            {reviewCards.map((card) => (
              <article className="review-card" key={card.title}>
                <h3>{card.title}</h3>
                <p>{card.description}</p>
                <ul>
                  {card.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
