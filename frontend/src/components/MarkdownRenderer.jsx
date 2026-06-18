import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { CodeBlock } from "./CodeBlock"

export function MarkdownRenderer({ content, children }) {
  const text = content || children || ""
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        pre: ({ children }) => {
          const child = children?.props?.children || children
          const className = children?.props?.className || ""
          return <CodeBlock className={className}>{child}</CodeBlock>
        },
      }}
    >
      {typeof text === "string" ? text : String(text)}
    </ReactMarkdown>
  )
}
