import type { ReactNode } from "react";

/* ===========================================================================
   The building blocks every docs section is made of.
   ---------------------------------------------------------------------------
   A reference is only skimmable if one heading shape, one measure and one set of
   primitives is used everywhere. These wrap the CSS classes the About page
   already proved out (`.ds-section`, `.ds-h2`, `.ds-subhead`, `.ds-table-wrap`)
   so a section reads as `<DocsSection>` and its subheads as `<DocsSub>`, and the
   anchor ids the rails track are minted in one place rather than retyped.
   ========================================================================= */

/**
 * One numbered chapter. The `id` lands on the `<h2>` itself, because that is the
 * element the scroll-spy looks up and the target a `#hash` deep link should
 * reach; `scroll-margin-top` in the stylesheet keeps it clear of the fixed nav.
 */
export function DocsSection({
  n,
  id,
  eyebrow,
  title,
  children,
}: {
  n: number;
  id: string;
  eyebrow: string;
  title: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="ds-section" aria-labelledby={id}>
      <div className="ds-section-inner">
        <div className="ds-docs-body">
          <p className="ds-docs-kicker">
            <span className="ds-docs-kicker-n">{n}</span>
            {eyebrow}
          </p>
          <h2 className="ds-h2" id={id}>
            {title}
          </h2>
          {children}
        </div>
      </div>
    </section>
  );
}

/** A subheading the right rail indexes. Its id is the href the rail lists. */
export function DocsSub({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h3 className="ds-subhead" id={id}>
      {children}
    </h3>
  );
}

/** The opening sentence under a heading, in the lede voice. */
export function Lead({ children }: { children: ReactNode }) {
  return <p className="ds-lede">{children}</p>;
}

/** Body copy. Kept as a component so the measure class is applied once. */
export function P({ children }: { children: ReactNode }) {
  return <p className="ds-paragraph">{children}</p>;
}

/** An inline identifier or value: keeps its monospace face inside a sentence. */
export function Code({ children }: { children: ReactNode }) {
  return <code className="ds-inline-code">{children}</code>;
}

/** A callout that must not read as body copy. */
export function Note({
  label = "Note",
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  return (
    <aside className="ds-note">
      <span className="ds-note-label">{label}</span>
      {children}
    </aside>
  );
}

/**
 * A scrollable table with a real `<caption>`. The wrapper is focusable so a
 * keyboard reader can reach the columns that overflow the measure.
 */
export function DocTable({
  caption,
  head,
  children,
  wide = false,
}: {
  caption: string;
  head: readonly string[];
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="ds-table-wrap" tabIndex={0} role="region" aria-label={caption}>
      <table className={wide ? "ds-table ds-table-2" : "ds-table"}>
        <caption className="ds-sr-only">{caption}</caption>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
