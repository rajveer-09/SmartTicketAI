import type { ReactNode } from "react";

/**
 * Renders the small Markdown subset the AI writes (headings, bullets, numbered
 * lists, bold, inline code). It builds React elements rather than HTML, so model
 * output can never inject markup.
 */

function inline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${match.index}-${token.length}`;
    if (token.startsWith("**")) {
      parts.push(
        <strong key={key} className="font-semibold text-ink-900">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`")) {
      parts.push(
        <code key={key} className="rounded bg-ink-200/70 px-1 py-0.5 text-[12.5px]">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      parts.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({ children }: { children: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushList = () => {
    if (!list) return;
    const items = list.items.map((item, i) => (
      <li key={i} className="ml-4 list-outside">
        {inline(item)}
      </li>
    ));
    blocks.push(
      list.ordered ? (
        <ol key={blocks.length} className="list-decimal space-y-1">
          {items}
        </ol>
      ) : (
        <ul key={blocks.length} className="list-disc space-y-1">
          {items}
        </ul>
      ),
    );
    list = null;
  };

  for (const rawLine of children.split("\n")) {
    const line = rawLine.trimEnd();

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);

    if (heading) {
      flushList();
      blocks.push(
        <p key={blocks.length} className="mt-3 font-semibold text-ink-900 first:mt-0">
          {inline(heading[2])}
        </p>,
      );
    } else if (bullet || numbered) {
      const ordered = Boolean(numbered);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1]);
    } else if (!line.trim()) {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={blocks.length}>{inline(line)}</p>);
    }
  }
  flushList();

  return <div className="space-y-2 text-[13.5px] leading-relaxed">{blocks}</div>;
}
