import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Render LLM output as formatted text. Raw HTML in the text is not rendered (safe by default). */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
