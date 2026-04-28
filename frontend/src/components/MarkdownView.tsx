/**
 * Renders markdown-source text with the platform's prose styling.
 * Used by chat assistant messages and dashboard markdown tiles.
 *
 * Renderer: `lib/markdown.renderMarkdown` — escapes HTML before applying
 * syntax, so it's safe to dangerouslySetInnerHTML the result.
 */

import { renderMarkdown } from "../lib/markdown";

const PROSE_CLASSES = [
  "max-w-none text-fg",
  "[&_a]:text-accent [&_a]:underline",
  "[&_code]:rounded [&_code]:bg-bg-subtle [&_code]:px-1 [&_code]:font-mono [&_code]:text-[0.9em]",
  "[&_strong]:font-semibold [&_strong]:text-fg",
  "[&_em]:italic",
  "[&_h1]:mt-0 [&_h1]:mb-2 [&_h1]:text-xl [&_h1]:font-semibold",
  "[&_h2]:mt-3 [&_h2]:mb-1.5 [&_h2]:text-base [&_h2]:font-semibold",
  "[&_h3]:mt-2 [&_h3]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold",
  "[&_li]:my-0.5",
  "[&_p]:my-1",
  "[&_p]:leading-relaxed",
  "[&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-5",
].join(" ");

export function MarkdownView({ source, className }: { source: string; className?: string }) {
  const html = renderMarkdown(source);
  return (
    <div
      className={className ? `${PROSE_CLASSES} ${className}` : PROSE_CLASSES}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
